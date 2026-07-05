# Video Archive UI Screens

## Overview

This document defines the main screens, modals, and interaction surfaces for Video Archive. The UI is dark by default and should remain visually light, clear, and minimally cluttered.

## Global UX Rules

- Dark theme by default
- Prioritize browsing and quick actions over advanced tuning controls
- Move rare or advanced controls into settings, modals, or secondary panels
- Show warning or incomplete indicators, but hide success-only indicators

## 1. Main Library Screen

Purpose:

- browse folders
- browse files
- inspect recursive status
- launch common actions

Main regions:

- directory tree
- current folder contents
- toolbar
- optional preview visibility toggle

Directory actions:

- convert recursively
- preview recursively
- tag recursively
- rescan recursively

File actions:

- open details
- open playback
- convert
- preview
- tag
- tune

Indicators:

- conversion indicator
- preview indicator

Indicators appear only for incomplete, running, or failed states.

## 2. Video Details Modal

Purpose:

- inspect one video in detail
- view preview assets if available
- launch file-specific jobs

Actions:

- open playback
- convert file
- preview file
- tag file
- tune file

Possible content:

- metadata summary
- preview collage
- assigned tags with confidence
- recent job history

## 3. Jobs Modal

Purpose:

- monitor and control jobs

Sections:

- queued jobs
- running jobs
- completed jobs
- failed jobs

Actions:

- cancel job
- restart job where supported
- remove job from visible list where supported

## 4. Log Viewer

Purpose:

- inspect near-real-time backend activity from the UI

Features:

- streaming updates
- filtering by job
- filtering by file
- filtering by level

The log viewer complements backend console logs rather than replacing them.

## 5. Preview Settings Screen

Purpose:

- configure preview generation behavior
- preview layouts before running full jobs

Controls:

- sampled frame count
- large tile count
- layout preset picker
- timeline flow mode
- identity diversity toggle
- fill / clear layout actions
- save preset
- load preset

Live preview:

- shows layout geometry immediately
- may show representative frames or placeholders

## 6. Conversion Profiles Screen

Purpose:

- manage reusable conversion profiles

Actions:

- create profile
- edit profile
- duplicate profile
- delete profile
- mark default profile

Fields:

- codec
- container
- maximum dimension
- quality parameters
- drop audio toggle
- advanced encoder args

## 7. Tagging Settings Screen

Purpose:

- define tagging vocabulary and tagging behavior

Controls:

- allowed tag list
- sampled frame count
- top tag count
- frame combination preferences
- provider/model selection shortcuts where useful

## 8. Playback Settings Screen

Purpose:

- choose how videos open from the library

Modes:

- embedded modal playback
- external opening by path or link

## 9. Source Settings Screen

Purpose:

- configure the active remote source

Fields:

- protocol
- host
- port
- root path
- username
- password

Actions:

- test connection
- save source
- reconnect

## 10. Provider Settings Screen

Purpose:

- configure OpenRouter, Gemini, FAL, and Mistral integrations

Per-provider controls:

- enabled flag
- API key
- vision model
- optional text model
- batch preferences if available

## 11. Backup and Maintenance Screen

Purpose:

- protect and maintain local metadata

Backup controls:

- create backup
- restore backup
- list backups
- retention count

Maintenance controls:

- full rescan
- subtree rescan entry point or redirect
- stale record cleanup
- database optimize

## 12. Tuning Flow

Tuning should be initiated from a file, not from the main folder toolbar.

The tuning UI should support:

- parameter sweeps over dimensions
- parameter sweeps over quality values
- parameter sweeps over codec variants
- comparison of generated outputs
- promotion of a successful tuning result into a reusable conversion profile
