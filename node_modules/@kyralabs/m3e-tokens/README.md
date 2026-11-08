# @kyralabs/m3e-tokens

Material 3 Expressive design tokens generated from the pinned androidx Compose Material3 sources:
CSS custom properties, JS token objects, color theming and self-hosted fonts (Google Sans Flex and
Material Symbols).

```sh
npm install @kyralabs/m3e-tokens
```

## Usage

```css
@import '@kyralabs/m3e-tokens/fonts.css'; /* Google Sans Flex */
@import '@kyralabs/m3e-tokens/tokens.css'; /* --m3e-sys-* typescale, shape, motion, … */
@import '@kyralabs/m3e-tokens/theme.css'; /* baseline color scheme, light + dark */

.headline {
  font: var(--m3e-sys-typescale-headline-medium);
  color: var(--m3e-sys-color-on-surface);
}
```

Generate a theme from a seed color:

```ts
import { createTheme } from '@kyralabs/m3e-tokens/theme';

const { cssText } = createTheme({ seed: '#6750A4', variant: 'expressive' });
```

or from the command line:

```sh
npx m3e-theme --seed "#6750A4" --variant expressive > theme.css
```

Optional core colors replace the palettes the variant would derive from the seed, like Material
Theme Builder's: `secondary`, `tertiary`, `neutral`, `neutralVariant` and `error`. Each palette
keeps the given color's hue and chroma (`TonalPalette.fromInt`); the variant still maps the roles
to tones. For example, a red primary on grey surfaces:

```ts
createTheme({
  seed: '#d84848',
  variant: 'fidelity',
  coreColors: { neutral: '#808080', neutralVariant: '#808080' },
});
```

```sh
npx m3e-theme --seed "#d84848" --variant fidelity --neutral "#808080" --neutral-variant "#808080"
```

The CLI flags are `--secondary`, `--tertiary`, `--neutral`, `--neutral-variant` and `--error`.
With spec 2025 (the `tonalSpot`, `neutral`, `vibrant` and `expressive` variants) the outline and
surface-variant roles come from the neutral palette, so `neutralVariant` has no effect there.

## Window size classes

The breakpoints come from androidx window-core `WindowSizeClass` (the lower bounds Compose
Material3 adaptive classifies with) and match m3.material.io's Breakpoints page. Each value is the
**min-width / min-height** of its class, in CSS px:

| Class | Width | Height |
|---|---|---|
| compact | < 600 | < 480 |
| medium | 600–839 (`--m3e-sys-window-width-medium: 600px`) | 480–899 (`--m3e-sys-window-height-medium: 480px`) |
| expanded | 840–1199 (`--m3e-sys-window-width-expanded: 840px`) | ≥ 900 (`--m3e-sys-window-height-expanded: 900px`) |
| large | 1200–1599 (`--m3e-sys-window-width-large: 1200px`) | — |
| extra-large | ≥ 1600 (`--m3e-sys-window-width-extra-large: 1600px`) | — |

CSS custom properties cannot appear in `@media` or `@container` conditions, so queries write the
px value from the table; the variables are for sizes (`max-inline-size:
var(--m3e-sys-window-width-expanded)`) and for reading from JS:

```css
@media (min-width: 840px) {
  /* expanded and up */
}
.layout {
  container-type: inline-size;
}
@container (min-width: 600px) {
  /* the container is medium or wider */
}
```

```ts
import { windowBreakpoints } from '@kyralabs/m3e-tokens';

windowBreakpoints.width.expanded; // 840
```

To classify a size or follow the window at runtime, use `windowSizeClass()` and
`observeWindowSizeClass()` from `@kyralabs/m3e-elements` or `useWindowSizeClass()` from
`@kyralabs/m3e-react`.

## Font profiles

Import exactly one Google Sans Flex profile. Each registers the same `"Google Sans Flex"` family,
so the others are drop-in replacements for `fonts.css`, imported instead of it, not beside it.

| Entry               | Variable axes                | Latin chunk | All chunks |
| ------------------- | ---------------------------- | ----------- | ---------- |
| `./fonts.css`       | wght, opsz (default)         | 138.8 KiB   | 328.5 KiB  |
| `./fonts-rond.css`  | wght, opsz, ROND             | 205.2 KiB   | 468.1 KiB  |
| `./fonts-full.css`  | wght, opsz, ROND, wdth, slnt | 1020.8 KiB  | 2026.8 KiB |

Axes a profile drops are fixed at their defaults (wdth 100, ROND 0, slnt 0), so every profile
renders the typescale identically. Browsers download only the chunks a page's text needs.
`fonts-rond.css` adds roundness (0–100, default 0), which CSS can set only through
`font-variation-settings`; that property replaces any inherited value rather than merging with it,
so repeat other axes you set in the same declaration:

```css
@import '@kyralabs/m3e-tokens/fonts-rond.css'; /* instead of fonts.css */

.playful {
  font-variation-settings: 'ROND' 100;
}
```

The typescale tokens do not use ROND, wdth or slnt (no Material source specifies values).

Other entries: `./components/<name>.css` (component tokens), `./material-symbols.css` (Rounded;
`-outlined` and `-sharp` too), and JS token objects from `.` and `./components`.

Apache-2.0; see `LICENSE` and `NOTICE`. The bundled fonts carry their own licenses in `fonts/`.
