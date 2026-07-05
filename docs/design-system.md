# Video Archive Design System

Video Archive's UI should feel compact, quiet, and unhurried: a slim top bar, small icon-only buttons for secondary actions, and a card grid that stays readable at a glance. This document defines that visual language, the two supported theme presets, and the responsive rules that keep the interface consistent from desktop down to mobile widths. It expands on [Specification Section 11](./specification.md#11-user-interface-and-interaction-model).

## 1. Reference Inspiration

The style direction is inspired by reference screenshots of another application (a document-archive tool) shared for this project. It is a density and restraint style guide, not a template to copy pixel-for-pixel — Video Archive keeps its own entities (folders, videos, jobs, conversion profiles) but borrows the same structural habits:

| Observed pattern | Video Archive equivalent |
| --- | --- |
| Slim top bar: logo + title, small icon-only buttons top-right (tasks, theme, language, settings) | Same top bar, icon buttons for Jobs, Theme, Language, Settings |
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

- The language toggle lives among the small icon buttons in the top bar, next to the theme toggle.
- Switching language does not reload the page and does not change layout — only text content and locale-specific formatting (dates, numbers).
- See [Specification Section 11.9](./specification.md#119-localization) and [Settings Specification Section 9](./settings-spec.md#9-interface-settings).

## 5. Responsive Breakpoints

| Range | Layout |
| --- | --- |
| `< 640px` (mobile) | Single-column card grid; directory tree becomes a drawer opened from the top bar; modals become full-screen sheets; secondary icon buttons collapse into an overflow menu; search stays visible. |
| `640px - 1024px` (tablet) | Two-column card grid; directory tree available as a collapsible panel. |
| `> 1024px` (desktop) | Full multi-pane layout: persistent directory tree, multi-column card grid, side-panel details view. |

Additional rules:

- Touch targets (icon buttons, cards, list rows) must be at least 40x40 logical pixels on mobile widths.
- The same component tree and navigation structure is reused across all breakpoints; there is no separate mobile-only screen set, so the same interface can later become the basis for a dedicated mobile application (see [Specification Section 11.11](./specification.md#1111-responsive-and-mobile-support)).

## 6. Non-Goals

- Not a pixel-perfect clone of the reference screenshots.
- Not a native mobile application for V1.
- No heavy, branded, or attention-grabbing effects (confetti, sound, full-screen takeovers) in either theme preset.
