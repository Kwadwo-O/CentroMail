# @kyralabs/m3exp-web

Material 3 Expressive for the web, matched to Jetpack Compose Material3 1.5.0-beta01. This
umbrella package re-exports every layer: tokens, CSS classes, custom elements and React
components.

```sh
npm install @kyralabs/m3exp-web
```

## Usage

```tsx
// Fonts, tokens, the baseline theme and every component class.
import '@kyralabs/m3exp-web/css/index.css';
import { Button } from '@kyralabs/m3exp-web/react';

export function Save() {
  return (
    <Button variant="filled" onPress={() => console.log('saved')}>
      Save
    </Button>
  );
}
```

Without React, use the classes directly or the custom elements:

```html
<button type="button" class="m3e-button m3e-button--filled">Save</button>

<script type="module">
  import '@kyralabs/m3exp-web/elements';
</script>
<m3e-loading-indicator aria-label="Loading"></m3e-loading-indicator>
```

Entry points: `.` (everything), `./tokens`, `./theme`, `./elements`, `./react` and
`./css/index.css`. React is an optional peer dependency (`react` and `react-dom` 18.3+ or 19).
Client-side rendering only.

`./css/index.css` includes the default Google Sans Flex profile (`fonts.css`, wght + opsz). To use
the roundness profile (`fonts-rond.css`, adds ROND) or the full profile (`fonts-full.css`, every
axis) instead, import that profile from `@kyralabs/m3e-tokens` together with its `tokens.css` and
`theme.css` and `@kyralabs/m3e-css/index.css`, in place of `./css/index.css`. Import one profile,
not two: they all register the same family.

See the [repository](https://github.com/kyra-labs/m3exp-web) for docs. Apache-2.0; see `LICENSE`
and `NOTICE`.
