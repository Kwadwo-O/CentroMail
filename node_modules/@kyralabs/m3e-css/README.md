# @kyralabs/m3e-css

Framework-free Material 3 Expressive component classes. No JavaScript. The styles reference the
`--m3e-*` custom properties from `@kyralabs/m3e-tokens`.

```sh
npm install @kyralabs/m3e-css @kyralabs/m3e-tokens
```

## Usage

```css
@import '@kyralabs/m3e-tokens/fonts.css';
@import '@kyralabs/m3e-tokens/tokens.css';
@import '@kyralabs/m3e-tokens/theme.css';
@import '@kyralabs/m3e-tokens/material-symbols.css';
@import '@kyralabs/m3e-css/index.css';
```

```html
<button type="button" class="m3e-button m3e-button--filled m3e-button--size-m">Save</button>

<button type="button" class="m3e-icon-button m3e-icon-button--filled" aria-label="Search">
  <span class="m3e-icon" aria-hidden="true">search</span>
</button>
```

Canonical layouts (`layout.css`): `.m3e-layout` is a size container; inside it
`.m3e-pane-scaffold--list-detail` / `--supporting-pane` show one, two or three panes by its width
(m3.material.io's counts: three from 1600px; add `--compose` for Compose's, three from 1200px;
`data-destination` picks the single pane) and `.m3e-feed` is the feed grid.

Import a single component with `@kyralabs/m3e-css/<component>.css` (for example `button.css`).
Classes follow `.m3e-<component>`, `__<part>` and `--<modifier>`.

## Components

`index.css` imports every file below. Each also works on its own as
`@kyralabs/m3e-css/<file>`. "Needs JS" marks components whose behavior (opening, positioning,
dragging, springs) comes from `@kyralabs/m3e-elements` or `@kyralabs/m3e-react`; the CSS still
draws them at rest. The pressed ripple on plain HTML needs `ripple.js` from m3e-elements (see its
README).

Primitives:

- `surface.css`: `.m3e-surface`, tonal surface containers, elevation and shapes.
- `icon.css`: `.m3e-icon`, a Material Symbols ligature (load a Material Symbols stylesheet too).
- `state-layer.css`: `.m3e-state-layer`, the hover, focus, pressed and dragged overlays.
- `focus-ring.css`: `.m3e-focus-ring`, the keyboard focus ring (`--inward` draws inside).

Components:

- `button.css`: `.m3e-button`, button and toggle button.
- `icon-button.css`: `.m3e-icon-button`, icon button and icon toggle button.
- `button-group.css`: `.m3e-button-group`, standard and connected button groups (needs JS for the
  press width changes and overflow).
- `split-button.css`: `.m3e-split-button`, a leading button and a trailing menu button (needs JS
  for the menu).
- `fab.css`: `.m3e-fab` and `.m3e-extended-fab`, FAB and extended FAB.
- `fab-menu.css`: `.m3e-fab-menu`, a toggle FAB and its menu items (needs JS for focus and light
  dismiss).
- `loading-indicator.css`: `.m3e-loading-indicator`, the loading indicator (needs JS for the shape
  morph; CSS alone rotates a fallback).
- `linear-progress.css`: `.m3e-linear-progress`, linear progress, flat (wavy needs JS).
- `circular-progress.css`: `.m3e-circular-progress`, circular progress, flat (wavy needs JS).
- `floating-toolbar.css`: `.m3e-floating-toolbar`, floating toolbar, with or without a FAB.
- `docked-toolbar.css`: `.m3e-docked-toolbar`, docked toolbar.
- `top-app-bar.css`: `.m3e-top-app-bar`, small, center-aligned, flexible and two-rows top app
  bars (scroll behaviors need JS).
- `search.css`: `.m3e-search`, search bar and its expanded views (needs JS to expand).
- `short-navigation-bar.css`: `.m3e-short-navigation-bar`, short navigation bar.
- `wide-navigation-rail.css`: `.m3e-wide-navigation-rail` and `.m3e-modal-wide-navigation-rail`,
  wide navigation rail (the modal rail needs JS).
- `navigation-item.css`: `.m3e-navigation-item`, the destination inside a navigation bar or rail.
- `navigation-drawer.css`: `.m3e-navigation-drawer`, permanent, dismissible and modal drawers
  (opening needs JS).
- `navigation-suite.css`: `.m3e-navigation-suite`, bar, rail or drawer by window size.
- `tabs.css`: `.m3e-tabs` and `.m3e-tab`, primary and secondary tabs (switching needs JS).
- `assist-chip.css`: `.m3e-assist-chip`, assist chip.
- `filter-chip.css`: `.m3e-filter-chip`, filter chip (a native checkbox).
- `input-chip.css`: `.m3e-input-chip`, input chip (needs JS for keyboard navigation and removal).
- `suggestion-chip.css`: `.m3e-suggestion-chip`, suggestion chip.
- `chip.css`: no class of its own; the base the four chip files import.
- `chip-set.css`: `.m3e-chip-set`, a wrapping or single-line group of chips.
- `card.css`: `.m3e-card`, filled, elevated and outlined cards.
- `list.css`: `.m3e-list` and `.m3e-list-item`, lists and segmented list items.
- `menu.css`: `.m3e-menu`, expressive and baseline menus (needs JS to open and position).
- `checkbox.css`: `.m3e-checkbox`, checkbox.
- `radio-button.css`: `.m3e-radio-button` and `.m3e-radio-group`, radio buttons.
- `switch.css`: `.m3e-switch`, switch.
- `slider.css`: `.m3e-slider`, slider and range slider (dragging needs JS).
- `text-field.css`: `.m3e-text-field`, filled and outlined text fields.
- `date-picker.css`: `.m3e-date-picker`, `.m3e-docked-date-picker` and
  `.m3e-date-picker-dialog`, date pickers (needs JS).
- `time-picker.css`: `.m3e-time-picker`, `.m3e-time-input`, `.m3e-time-scroll` and
  `.m3e-time-picker-dialog`, time pickers (needs JS).
- `dialog.css`: `.m3e-dialog`, alert, custom and full-screen dialogs (motion and focus need JS).
- `bottom-sheet.css`: `.m3e-bottom-sheet`, standard and modal bottom sheets (needs JS to drag and
  animate).
- `side-sheet.css`: `.m3e-side-sheet`, standard and modal side sheets (motion and the modal need
  JS).
- `snackbar.css`: `.m3e-snackbar` and `.m3e-snackbar-host`, snackbar (the queue needs JS).
- `tooltip.css`: `.m3e-tooltip`, plain and rich tooltips (showing them needs JS, or a popover).
- `badge.css`: `.m3e-badge` and `.m3e-badged-box`, badge.
- `divider.css`: `.m3e-divider`, horizontal and vertical dividers.
- `carousel.css`: `.m3e-carousel`, carousel (keyline sizing needs JS; CSS alone snaps).
- `pull-to-refresh.css`: `.m3e-pull-to-refresh`, pull to refresh (the pull needs JS).
- `layout.css`: `.m3e-layout`, `.m3e-pane-scaffold` and `.m3e-feed`, canonical layouts (above).
- `vertical-drag-handle.css`: `.m3e-vertical-drag-handle`, the pane scaffold's drag handle bar.

Deprecated (D4), shipped until 2.0 with no new features:

- `bottom-app-bar.css`: `.m3e-bottom-app-bar`, legacy bottom app bar; use `docked-toolbar.css`.
- `navigation-bar.css`: `.m3e-navigation-bar`, legacy navigation bar; use
  `short-navigation-bar.css`.
- `navigation-rail.css`: `.m3e-navigation-rail`, legacy navigation rail; use
  `wide-navigation-rail.css`.
- `segmented-button.css`: `.m3e-segmented-button`, segmented button; use the connected button
  group (`.m3e-button-group--connected`).
- In `fab.css`, `.m3e-fab--size-small`; use the baseline FAB. In `list.css`,
  `.m3e-list-item--baseline` (the non-expressive list item); use the expressive list item.

The components respect `prefers-reduced-motion` and `forced-colors`.

Apache-2.0; see `LICENSE` and `NOTICE`.
