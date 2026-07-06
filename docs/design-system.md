# Video Archive Design System

Video Archive's UI should feel compact, quiet, and unhurried: a slim top bar, small icon-only buttons for secondary actions, and a card grid that stays readable at a glance. This document defines that visual language, the two supported theme presets, and the responsive rules that keep the interface consistent from desktop down to mobile widths. It expands on [Specification Section 11](./specification.md#11-user-interface-and-interaction-model).

## 1. Reference Inspiration

The style direction is inspired by reference screenshots of another application (a document-archive tool) shared for this project. It is a density and restraint style guide, not a template to copy pixel-for-pixel — Video Archive keeps its own entities (folders, videos, jobs, conversion profiles) but borrows the same structural habits:

| Observed pattern | Video Archive equivalent |
| --- | --- |
| Slim top bar: logo + title, small icon-only buttons top-right (tasks, theme, language, settings) | Same top bar, icon buttons for Jobs, Preview Visibility, Theme, and Settings. Language selection lives inside Settings rather than as its own top-bar button (see [§4](#4-localization-presentation)) |
| Centered search bar with pill-shaped filter buttons beneath it (Search / AI / Year / Language) | Compact, non-dominant search field at the edge of the toolbar with tag autocomplete; pill filters for scope, status, tags. Search is deliberately smaller than in the reference — it is a secondary convenience, not a central element |
| Card grid: thumbnail, small type-icon badge top-left, category badge top-right, title + date caption | File/folder cards: thumbnail or preview collage, conversion/preview status badges, name + modified date |
| Modal with left icon-rail navigation (Indexing, AI settings, Log, Usage, Backup) and stat tiles in a grid | Settings screen and Jobs modal reuse the same icon-rail + stat-tile pattern |
| Right-side sliding details panel with tabs (Details / Recognized text / Dev) and pinned actions at the bottom | Video Details modal: tabs for metadata / job history, actions pinned at the bottom |

Colors, copy, and iconography are not copied — only the density, spacing, and information hierarchy.

## 2. Theme Presets

### 2.1 Strict (default)

- Dark neutral background, muted surface colors, one accent color reserved for primary actions and status.
- No decorative motion beyond standard, functional transitions (opening/closing modals, loading states).
- This is the theme described in Specification Section 11.1 and is what all screens are designed against first.

### 2.2 Playful

- Same layout, navigation, and information structure as Strict — nothing moves, nothing new appears.
- Warmer, more saturated accent palette; more expressive iconography; optional gradient or glow treatment on primary buttons.
- May add small, purely decorative animations (hover lift, soft pulse on primary actions, subtle transitions), per Specification Section 11.10.
- Must respect `prefers-reduced-motion` and must never delay or block the completion of an action.

### 2.3 Shared Rules

- Theme preset is a persisted setting (see [Settings Specification Section 9](./settings-spec.md#9-interface-settings)).
- Switching theme is instantaneous and does not reload the page.
- The theme toggle is one of the small icon-only buttons in the top bar, matching the other global controls.

## 3. Animation Guidelines (Playful preset)

- Keep durations short: roughly 100-250ms.
- Animate only `transform` and `opacity`; avoid animating layout-affecting properties.
- No animation should gate or delay user input or the visible result of an action.
- No sound, confetti, or full-screen effects — animations stay small and localized to the element interacted with.
- Strict preset does not use these animations by default.

## 4. Localization Presentation

- The language control lives in **Settings**, not the top bar: the top bar only exposes the Settings icon button that opens it. Language is a one-time-per-session-ish preference, not something switched constantly, so it doesn't need to occupy prime top-bar real estate the way the preview visibility toggle does ([§4.1](#41-preview-visibility-toggle)).
- Inside Settings, under an "Interface" section, language is a small labelled option group (e.g. "English" / "Русский" buttons, current selection highlighted) rather than an icon — Settings has room for a text label, so clarity wins over the icon-only compactness rule that applies to the top bar ([§4.2](#42-icon-only-buttons-for-self-evident-actions)).
- Switching language does not reload the page and does not change layout — only text content and locale-specific formatting (dates, numbers) — and the Settings surface itself re-renders in the new language immediately.
- See [Specification Section 11.9](./specification.md#119-localization) and [Settings Specification Section 9](./settings-spec.md#9-interface-settings).

### 4.1 Preview Visibility Toggle

- A small, always-visible icon button sits in the top bar next to the Settings button: it shows or hides all preview thumbnails and collages across the current view.
- Toggling is instant and purely client-side/front-end state: no backend call, no regeneration of assets, no page reload, and no change to layout or navigation.
- This is a display preference for the current session, not a data-changing action — preview files on disk are untouched.

### 4.2 Icon-Only Buttons for Self-Evident Actions

- Every button, everywhere in the UI, must have an icon from the shared icon set — labelled or not. A text-only button with no icon is an exception, not the default, and should only happen when no icon in the set reasonably represents the action (e.g. a plain "Cancel" in a dialog).
- Icons are drawn from **Lucide** (`lucide-react`) — a thin-stroke, outline icon set used across many modern dashboard/SaaS UIs — imported directly as React components (e.g. `<Settings />`, `<Eye />`). Chosen over emoji (inconsistent, low-fidelity across OSes — e.g. flag emoji rendering as bare letter codes on Windows) and over filled/Material-style icon sets, which read heavier and less consistent with this app's quiet, muted Strict theme.
- Beyond just having an icon, prefer dropping the text label entirely when the icon alone is self-evident (delete, save, play/run, theme, jobs, settings, preview visibility): a compact icon-only button, no visible text, just the icon plus an accessible name (`aria-label`/`title`) for assistive tech and tooltips. Aim for icon-only to be the common case — roughly half or more of the buttons in a given screen — not the exception; only keep a visible label where the icon alone would be ambiguous or the action is unusual/high-consequence enough that a label adds real clarity (see [§4](#4-localization-presentation) for why Settings' language control keeps a label instead of an icon).
- Destructive actions (for example, delete) use a small icon in the danger/red accent color instead of a labelled button — the icon and color communicate the action, so no confirmation text is needed in the button itself (a confirmation step may still gate the action).
- This keeps the top bar and card actions dense, consistent with the overall density/restraint direction in [Section 1](#1-reference-inspiration).

## 5. Responsive Breakpoints

| Range | Layout |
| --- | --- |
| `< 640px` (mobile) | Single-column card grid; directory tree becomes a drawer opened from the top bar; modals become full-screen sheets; secondary icon buttons collapse into an overflow menu; search stays visible. |
| `640px - 1024px` (tablet) | Two-column card grid; directory tree available as a collapsible panel. |
| `> 1024px` (desktop) | Full multi-pane layout: persistent directory tree, multi-column card grid, side-panel details view. |

Additional rules:

- Touch targets (icon buttons, cards, list rows) must be at least 40x40 logical pixels on mobile widths.
- The same component tree and navigation structure is reused across all breakpoints; there is no separate mobile-only screen set, so the same interface can later become the basis for a dedicated mobile application (see [Specification Section 11.11](./specification.md#1111-responsive-and-mobile-support)).
- Layouts are designed mobile-first, with portrait orientation as the primary small-screen case (most phones are used vertically). Mobile-first foundations are established from [Roadmap Stage 1](./roadmap.md#stage-1--skeleton), not deferred to a later polish pass.

## 6. Non-Goals

- Not a pixel-perfect clone of the reference screenshots.
- Not a native mobile application for V1.
- No heavy, branded, or attention-grabbing effects (confetti, sound, full-screen takeovers) in either theme preset.
