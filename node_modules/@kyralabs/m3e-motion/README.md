# @kyralabs/m3e-motion

Spring math for m3exp-web: TypeScript ports of Compose's `SpringSimulation` and spring duration
estimate (float32-exact against the JVM), `FloatSpringSpec` helpers, a CSS `linear()` sampler and
the top app bar scroll state. Mostly used by the other `@kyralabs` packages; no DOM access.

```sh
npm install @kyralabs/m3e-motion
```

## Usage

```ts
import { springDurationMillis, springToLinear, springValue } from '@kyralabs/m3e-motion';

const spec = { dampingRatio: 0.9, stiffness: 700 };
springValue(spec, 100, 0, 1); // position after 100 ms, animating 0 → 1
springDurationMillis(spec, 0, 1); // settle time in ms
springToLinear(spec); // CSS linear() easing plus its duration
```

Window size classes (ports of androidx window-core `WindowSizeClass` and Compose Material3
adaptive; sizes in CSS px):

```ts
import {
  isWidthAtLeastBreakpoint,
  navigationSuiteType,
  paneScaffoldDirective,
  windowSizeClass,
} from '@kyralabs/m3e-motion';

const sizeClass = windowSizeClass({ width: 1280, height: 800 });
// { widthClass: 'large', heightClass: 'medium', minWidth: 1200, minHeight: 480 }
isWidthAtLeastBreakpoint(sizeClass, 'expanded'); // true
paneScaffoldDirective(sizeClass).maxHorizontalPartitions; // 3 (calculatePaneScaffoldDirective)
navigationSuiteType(sizeClass); // 'wide-navigation-rail-collapsed' (Compose's default rule)
navigationSuiteType(sizeClass, { expandedFrom: 'large' }); // 'wide-navigation-rail-expanded'
```

`expandedFrom` (a width class or px bound) expands the collapsed rail from that width (the
navigation suite scaffold's default is `NAVIGATION_SUITE_EXPANDED_FROM`, `'large'`), to the expanded
rail or, with `expandedType: 'navigation-drawer'`, a drawer. `NavigationSuiteScaffoldAnimation`
ports Compose's `NavigationSuiteScaffoldState` show / hide with its layout progress.

`windowWidthSizeClass` / `windowHeightSizeClass` classify one axis; `{ largeAndExtraLargeWidth:
false }` keeps Compose's V1 width set (every width from 840 is `expanded`).

Three-pane scaffolds (ports of Compose Material3 adaptive `ThreePaneScaffold`, the list-detail and
supporting-pane scaffolds and their navigator): `calculateThreePaneScaffoldValue`,
`ThreePaneScaffoldNavigator` (`navigateTo`, `navigateBack` with the four back behaviors),
`threePaneScaffoldDirective` (m3.material.io's pane counts by default, two at large;
`paneRule: 'compose'` keeps Compose's three),
`threePaneScaffoldLayout` (pane bounds), `calculatePaneMotion` / `paneTransitions` /
`ThreePaneScaffoldAnimation` (pane motion) and the pane expansion anchors.

Apache-2.0; see `LICENSE` and `NOTICE`.
