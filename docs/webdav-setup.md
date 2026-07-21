# WebDAV Source Setup (Synology DSM)

This document walks through configuring a Synology NAS's WebDAV Server so it can be added as a `webdav` source in this app (Settings → Source), and lists the connection details the app's form expects. For the code-level shape of the `webdav` backend (`httpx`-based, no third-party WebDAV library, no direct-access fast path, optional `verify_ssl` opt-out), see the "Sources layer" section and the `webdav` row of the conventions table in [`architecture.md`](architecture.md).

## Prerequisites

- A Synology NAS running DSM 6 or 7, with a shared folder already holding (or ready to hold) your video library.
- Admin access to DSM to install a package and manage users/permissions.
- The NAS reachable from the machine running this app (same LAN, or a VPN/tunnel — WebDAV itself has no built-in remote-access helper the way QuickConnect does for some other Synology apps).

## 1. Enable the WebDAV Server package on DSM

1. Open **Package Center** in DSM.
2. Search for **WebDAV Server** and install it (it's a small official Synology package, not a third-party one).
3. Open the **WebDAV Server** app once installed and enable the checkbox(es) for **HTTP** and/or **HTTPS**.

Nothing is reachable until at least one of HTTP/HTTPS is turned on here — installing the package alone does not start the service.

## 2. Choose HTTP or HTTPS, and the port

The WebDAV Server app lets you enable HTTP and HTTPS independently, each with its own port field. Synology's own defaults are:

| Protocol | Default port |
| --- | --- |
| HTTP | 5005 |
| HTTPS | 5006 |

These are **not** the standard web ports (80/443) — the app's Source form has a separate `port` field precisely because a WebDAV server's port is rarely the scheme's default, so always fill it in explicitly rather than relying on an implicit default.

Recommendation:

- On a trusted LAN where you don't want to deal with certificates, HTTP is the simplest option.
- Over anything less trusted (a VPN into your home network, a tunnel, etc.), use HTTPS — see [Self-signed HTTPS certificates](#self-signed-https-certificates-and-the-verify-tls-certificate-checkbox) below for what that means for this app.

## 3. Create a dedicated DSM user and folder permissions

Don't reuse your DSM admin account for this app — create a scoped-down user instead:

1. **Control Panel → User & Group → Create** — make a new user (e.g. `videoarchive`) with a strong password. It does not need to be in the `administrators` group.
2. **Control Panel → Shared Folder** — select the shared folder your video library lives in (or will live in) → **Edit → Permissions** → grant this user **Read/Write** access.
3. Still in **User & Group**, open the user's own **Edit → Applications** tab and confirm **WebDAV** (and/or **File Station**, which some DSM versions group it with) isn't explicitly denied — DSM's per-user application permissions can silently block a service even when the shared-folder permission itself is correct, which is a common source of a "403 Forbidden"/authentication-looking failure that isn't actually a bad password.

## 4. Find your connection details (host, port, path)

Synology's WebDAV Server exposes each shared folder the connecting user has access to as a top-level folder under the WebDAV root — the same shared folders visible in File Station, not a separate WebDAV-only namespace. So for a shared folder named `video`, the path you'd browse to over WebDAV is `/video`, optionally with a subpath (`/video/archive`) exactly like the app's SMB source uses `share[/subpath]`.

> This layout is Synology's documented behavior but hasn't been verified against a live DSM box in this environment (no real Synology NAS is reachable here, the same constraint the SMB source's own tests work around with an in-memory fake — see [`development.md`](development.md)). If your NAS exposes the share differently, adjust the **Path** field below to match what you see when connecting with a WebDAV client, and consider updating this note.

You'll need:

- **Host** — the NAS's IP or hostname, e.g. `192.168.1.50` or `nas.local`. You may include the scheme directly (`https://192.168.1.50`); if you don't, the app assumes `https://`.
- **Port** — `5005` (HTTP) or `5006` (HTTPS) unless you changed it in step 2.
- **Path** — the shared folder name, optionally with a subpath, e.g. `video` or `video/archive`.
- **Username / Password** — the dedicated user created in step 3.

## 5. Configure the source in this app's Settings

1. Open **Settings → Source**.
2. Set **Protocol** to **WebDAV**.
3. Fill in **Host**, **Port**, **Path** (the "remote path" field), **Username**, **Password** from step 4.
4. If you're using HTTPS with DSM's default self-signed certificate (i.e. you haven't installed a trusted certificate on the NAS — see below), check **Verify TLS certificate** *off*; leave it on if you have a trusted certificate or you're using plain HTTP.
5. Click **Test connection** first — a failure here surfaces the actual error (wrong host/port, bad credentials, TLS certificate rejected, path not found) before anything is saved.
6. Click **Connect** to save the source and start the initial scan.

## Troubleshooting

- **Test connection fails with a TLS/certificate error** — you're using HTTPS against DSM's default self-signed certificate. Either turn off **Verify TLS certificate** in the source form (see the warning below), switch to HTTP on a trusted LAN, or install a proper certificate on the NAS (DSM supports free Let's Encrypt certificates under **Control Panel → Security → Certificate**, though WebDAV Server may need its own binding — check DSM's certificate-binding settings if a Let's Encrypt cert doesn't seem to apply to the WebDAV Server port).
- **Test connection fails with an authentication error despite correct credentials** — recheck step 3's per-user Applications permissions; DSM can reject a WebDAV connection at the account level even with correct shared-folder permissions.
- **"Path is not a directory" / 404-style failure** — double check the **Path** field against step 4: it should be the shared folder's name (and optional subpath), not a filesystem path like `/volume1/video`.
- **Connection works but is slow** — WebDAV has no direct-access fast path the way this app's `smb` source does (no OS-level UNC redirector to fall back to); every read/write is a plain HTTP request. This is expected and not a misconfiguration.

## Self-signed HTTPS certificates and the "Verify TLS certificate" checkbox

DSM's WebDAV Server, when HTTPS is enabled, uses whatever certificate is bound to it in DSM — by default this is DSM's own self-signed certificate, not one signed by a public certificate authority. A normal HTTPS client (including this app, by default) rejects a self-signed certificate as untrusted, so connecting over HTTPS to an out-of-the-box DSM will fail **Test connection** with a TLS error until you do one of:

- Turn **off** the **Verify TLS certificate** checkbox on the source form. This makes the app accept *any* certificate the server presents, including a self-signed one — convenient, but it means the connection can no longer detect a machine-in-the-middle impersonating your NAS. Only do this on a network you trust (e.g. your own home LAN), never over the open internet or an untrusted network.
- Install a certificate DSM's WebDAV Server can present that your system already trusts (a Let's Encrypt certificate via DSM's own certificate manager, or your own internal CA's certificate if you run one), and leave verification on.
- Use plain HTTP instead, on a trusted LAN — sidesteps certificate trust entirely, at the cost of the connection (including credentials) being unencrypted on the wire.
