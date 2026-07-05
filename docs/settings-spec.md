# Video Archive Settings Specification

## Overview

This document defines the settings structure for Video Archive. Settings are divided into user-editable groups stored in the local database and secrets stored in a local `.env`-style file (see [Tech Stack](./tech-stack.md)).

## Settings Areas

- source connection
- conversion profiles
- preview
- playback
- tagging (including tag vocabulary)
- AI providers
- backup
- maintenance
- interface

## 1. Source Connection Settings

Fields:

- source name
- protocol (`local | smb`; `webdav` optional later)
- host (protocol sources only)
- port (protocol sources only)
- remote path (protocol sources only)
- username (protocol sources only)
- password (protocol sources only)
- local path (local source only), given as an absolute path or as a path relative to the backend working directory

Rules:

- Only one active source at a time.
- Username and password are written to the secrets file; the database keeps only key references.
- A `local` source does not require authentication and is not subject to reconnect/network-refresh behavior.
- Changing the source is destructive: the UI must warn that all local library metadata will be wiped, and after connecting the new source, offer to restore any backups found in its technical folder (see [Specification Section 5.2](./specification.md#52-source-switching)).

## 2. Conversion Profile Settings

Each saved profile should expose:

- name
- codec (default `h265`)
- container (default `mp4`)
- maximum dimension (empty = never resize)
- CRF quality value (default `26`; lower = better quality/larger file; practical range 22–32)
- drop audio toggle (default **on** — audio is not needed in this archive)
- advanced encoder parameters

The settings UI should allow:

- create profile
- edit profile
- duplicate profile
- delete profile
- mark recommended default profile

Job-level defaults (shown in conversion dialogs, not stored per profile):

- skip already-converted files: default **on**
- test mode (preserve originals): default **off**

## 3. Preview Settings

Preview settings should include:

- grid dimensions (rows × columns)
- enlarged tile count, sizes (2×2 or 3×3 spans), and placement (grid must stay fully covered)
- layout preset (built-in gallery + user presets + quick save/load slots)
- timeline flow mode (`row | column | shuffle`)
- identity diversity toggle (default **on**)
- folder-preview frame count (default `4`)
- live preview

Collage appearance is fixed for V1 (not settings): black background, thin gaps between tiles, file-name caption inside the collage (see [Specification Section 9.2.1](./specification.md#921-collage-appearance)).

Default expectations:

- identity diversity enabled by default
- identity diversity may be disabled when speed matters more than face uniqueness

Preview settings should also support:

- save preset
- load preset
- fill layout
- clear layout

## 4. Playback Settings

Playback settings should include:

- playback mode (`stream | direct_link`)
- embedded modal playback option (backend streaming proxy with Range support)
- external opening option (direct file path or protocol link)

Both strategies must remain available and switchable, because target devices are not yet known.

## 5. Tagging Settings

Tagging settings should include:

- **tag vocabulary management**: add, rename, deactivate, and delete tags; tags are arbitrary user-defined words or phrases
- sampled frame count (default `9`)
- whether to combine sampled frames into one collage image for classification (default **on**, 3×3)
- top tag count to store per video (default `10`)
- provider/model selection shortcut

Behavior notes:

- The vocabulary is the closed set the AI scores against; the model does not invent tags.
- Results are relevance scores 0–100 per tag, shown as percentages; only the top-N are stored.
- The same vocabulary feeds search autocomplete (prefix suggestions).

## 6. AI Provider Settings

Supported providers:

- OpenRouter
- Google Gemini
- FAL
- Mistral

Each provider entry may include:

- enabled flag
- API key
- default vision model
- optional default text model
- batch mode preferences if available

Rules:

- API keys are stored only in the local secrets file (`backend/secrets.env`), never in the database.
- The secrets file is git-ignored and human-readable, so the user can copy or back it up by hand.
- Provider config must be exportable and importable by explicit user action, including API keys.

## 7. Backup Settings

Backup settings should include:

- retention count (default `5`)
- backup destination: fixed to the source's technical folder `.video-archive/backups/` for V1

## 8. Maintenance Settings

Maintenance actions should include:

- full rescan
- subtree rescan
- stale record cleanup
- local database optimize/compact

## 9. Interface Settings

Interface settings should include:

- UI language (`en | ru`)
- theme preset (`strict | playful`)

Default expectations:

- default UI language matches the browser/OS locale when recognized, falling back to English
- default theme preset is `strict`

Rules:

- Interface settings changes must apply immediately, without a page reload.
- Interface settings are persisted the same way as other settings groups.

## Export and Import

Settings export should support full provider configuration, including API keys, models, and enabled providers, because that behavior was explicitly requested.

Import should validate:

- source settings structure
- profile definitions
- preview settings payload
- provider entries
- backup settings
- tag vocabulary

## Recommended Settings Shape

```json
{
  "source": {},
  "profiles": [],
  "preview": {},
  "playback": {},
  "tagging": {},
  "providers": [],
  "backup": {},
  "maintenance": {},
  "interface": {}
}
```
