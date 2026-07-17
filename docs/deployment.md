# Deployment — k3s cluster via GitHub Actions + GHCR + ArgoCD

The app runs in two modes from the same repository: the unchanged local dev loop (`npm run dev` at the repo root, see [README.md](../README.md#local-run)) and a containerized deployment onto the home k3s cluster, shipped through a GitOps loop — push to `main`, GitHub Actions builds the images into GHCR and bumps the Helm tag on the `deploy` branch, ArgoCD syncs it onto the cluster. Deployment is additive: nothing about the local run changed except that all mutable backend state honors one optional env var. The platform itself (cluster facts, conventions) is described in the portable spec [docs/spec/k3s-platform-deployment.md](spec/k3s-platform-deployment.md); this document is the video-archive-specific narrative.

```text
git push (main) ──► GitHub Actions ──► GHCR images (tag = short SHA)
                        │                  ghcr.io/sergeyanokhin/video-archive/{backend,frontend}
                        └─► bump image tags in Helm values ──► force-push branch `deploy`
                                                                    │
                                              ArgoCD (tracks `deploy`) ──► k3s namespace `video-archive`
```

## File map

| File | Role |
| --- | --- |
| [`.github/workflows/build.yml`](../.github/workflows/build.yml) | CI: build both images → push GHCR → yq-bump tags in values → force-push `deploy` branch (`[skip ci]`, source-paths trigger filter — loop-safe) |
| [`backend/Dockerfile`](../backend/Dockerfile) | python:3.12-slim + ffmpeg, uvicorn on :8000; context = `backend/` |
| [`frontend/Dockerfile`](../frontend/Dockerfile) + [`frontend/nginx.conf`](../frontend/nginx.conf) | Vite production build → nginx with SPA fallback; context = `frontend/` |
| [`deploy/helm/video-archive/`](../deploy/helm/video-archive/) | Helm chart: backend (stateful, Recreate, PVC) + frontend + Traefik ingress with cert-manager TLS. CI rewrites only `values.yaml` `image.*.tag` |
| [`deploy/argocd/application.yaml`](../deploy/argocd/application.yaml) | ArgoCD Application, `targetRevision: deploy`; applied once by a human (§ checklist) |

## State: one env var, one PVC

Locally every piece of mutable backend state lives where it always did (`backend/video_archive.db`, `backend/secrets.env`, `backend/preview_cache/`, `backend/models/`, repo-root `logs/`). On the cluster the Deployment sets **`VIDEO_ARCHIVE_STATE_DIR=/data/state`** (see [`backend/app/config.py`](../backend/app/config.py)) and mounts a single `local-path` PVC (`video-archive-state`, 20Gi by default) there — DB, secrets, preview cache, detection models, and logs all move onto the volume. Unset locally → nothing changes.

Notes that follow from this:

- **No k8s Secrets are needed.** Provider API keys and SMB credentials are entered through the app's own Settings UI and stored in `secrets.env` — which now sits on the PVC, never in the image or the chart.
- **The video library comes from the app's own `smb` source type.** In a pod, a `local` source would point at the container filesystem — useless. Connect the Synology share (`//192.168.1.91/<share>`) as an `smb` source from Settings; the backend speaks SMB directly (`smbprotocol`), so the SMB CSI driver is **not** required for this app.
- **Detection models** (~39 MB) auto-download into the state volume on first preview generation and persist across pod restarts.

## Backend node placement — the switch

`backend.computeNode` in [`values.yaml`](../deploy/helm/video-archive/values.yaml):

- `false` (default) — the backend schedules on the general-purpose node (`k3s`, 192.168.1.97).
- `true` — the backend is pinned to the powerful node (`ubuntu-server`) via `nodeSelector: {role: compute}` + a toleration for the `role=compute:NoSchedule` taint. Worth it for heavy ffmpeg conversion batches. Requires the one-time node label/taint (checklist step 2).

**Caveat — the PVC pins the pod to a node.** k3s `local-path` volumes are node-local: the PV is created on whichever node the pod first runs on, and from then on the pod can only schedule there. Flipping `computeNode` after the first deploy therefore leaves the pod `Pending` (volume node affinity conflict). To actually move the backend:

1. In the app, run a metadata **backup** (Settings → Backups) — it lands in the source's own `.video-archive/backups/` on the NAS, not on the PVC.
2. Flip `backend.computeNode`, push to `main`, let ArgoCD sync.
3. Delete the stranded PVC/PV: `kubectl -n video-archive delete pvc video-archive-state` (delete the pod too so the new one rebinds); a fresh PV is created on the new node.
4. In the app, reconnect the source — the automatic restore-from-backup recovers tags/settings; preview cache and models regenerate/redownload on demand.

Also note: `ubuntu-server` may be powered off. If the backend lives there while it's off, the app is down (expected); if that bothers ArgoCD health, the optional `argocd-cm` Lua health override from the platform spec (§6.2) applies.

## Human-only checklist (once)

The agent cannot touch the cluster, GHCR visibility, or ArgoCD. Run top to bottom on a machine with `kubectl` access:

1. **First build:** push to `main` (or run the `build-and-push` workflow manually) and wait for green — this creates the GHCR packages and the `deploy` branch. Then make both packages public: GitHub → repo → Packages → `backend`/`frontend` → Package settings → Change visibility → Public. (Or keep them private and create a `ghcr-creds` pull secret + set `imagePullSecrets` in values.)
2. **Powerful-node pinning** (only if you plan to use `backend.computeNode: true`), once ever:
   ```bash
   kubectl label node ubuntu-server role=compute
   kubectl taint nodes ubuntu-server role=compute:NoSchedule
   ```
3. **Register with ArgoCD:**
   ```bash
   kubectl apply -f deploy/argocd/application.yaml
   kubectl -n argocd get application video-archive   # wait for SYNCED / HEALTHY
   ```
4. **DNS:** nothing to do — `video-archive.192.168.1.97.nip.io` resolves via public DNS.
5. **HTTPS:** devices that already trust the `home-ca` root need nothing. A new device: export and install the CA cert (platform spec §6.7).
6. **In the app:** open `https://video-archive.192.168.1.97.nip.io`, go to Settings → Source, connect the NAS share as an `smb` source, re-enter provider API keys (state starts empty on the cluster — it is a separate instance from your local one).

## Verify & troubleshoot

```bash
kubectl -n video-archive get pods -o wide     # both Running; node placement as expected
kubectl -n video-archive get pvc,ingress
kubectl -n video-archive logs deploy/video-archive-backend
helm template video-archive deploy/helm/video-archive -n video-archive   # local render, no cluster
```

| Symptom | Likely cause |
| --- | --- |
| `ImagePullBackOff` | GHCR packages still private (checklist 1) |
| Backend `Pending` after flipping `computeNode` | PVC node-affinity conflict — see "the switch" above; or node not labelled/tainted |
| `/api` calls 404 through the ingress | something re-introduced StripPrefix — the backend serves routes under `/api` already; the ingress must forward `/api` as-is |
| ArgoCD `OutOfSync` forever | it tracks `deploy`, not `main` — check the Actions run pushed the bump |
| App up but library empty | expected on first run — connect an `smb` source in Settings (cluster state is separate from local) |
