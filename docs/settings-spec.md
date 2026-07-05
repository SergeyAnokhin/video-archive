# Video Archive Settings Specification

## Overview

This document defines the settings structure for Video Archive. Settings are divided into user-editable groups and secret-bearing provider configuration.

## Settings Areas

- source connection
- conversion profiles
- preview
- playback
- tagging
- AI providers
- backup
- maintenance

## 1. Source Connection Settings

Fields:

- source name
- protocol
- host
- port
- remote path
- username
- password or secret reference

Rules:

- Only one active source at a time.
- Secrets should be stored outside the main metadata database when possible.

## 2. Conversion Profile Settings

Each saved profile should expose:

- name
- codec
- container
- maximum dimension
- quality mode
- quality value
- drop audio toggle
- advanced encoder parameters

The settings UI should allow:

- create profile
- edit profile
- duplicate profile
- delete profile
- mark recommended default profile

## 3. Preview Settings

Preview settings should include:

- total sampled frame count
- large tile count
- layout preset
- timeline flow mode
- identity diversity toggle
- live preview

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

- playback mode
- embedded modal playback option
- external opening option

Supported strategies:

- embedded playback in-app
- external opening through path or link when the environment supports it

## 5. Tagging Settings

Tagging settings should include:

- allowed tag vocabulary
- sampled frame count
- whether to combine multiple frames into one image for classification
- top tag count target
- confidence handling preferences if needed later

Default expectation:

- sampled frame count default is `9`

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

- Provider config must be exportable and importable by explicit user action.
- API keys must not be stored in the main metadata database.

## 7. Backup Settings

Backup settings should include:

- retention count
- backup destination if configurable

Default:

- retention count `5`

## 8. Maintenance Settings

Maintenance actions should include:

- full rescan
- subtree rescan
- stale record cleanup
- local database optimize/compact

## Export and Import

Settings export should support full provider configuration, including API keys, models, and enabled providers, because that behavior was explicitly requested.

Import should validate:

- source settings structure
- profile definitions
- preview settings payload
- provider entries
- backup settings

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
  "maintenance": {}
}
```
