# @kyralabs/m3e-react

Material 3 Expressive React components built on React Aria (behavior, accessibility) and Motion
(springs). They render the same classes as `@kyralabs/m3e-css`. Client-side rendering only.

```sh
npm install @kyralabs/m3e-react @kyralabs/m3e-css @kyralabs/m3e-tokens react react-dom
```

## Usage

```tsx
import '@kyralabs/m3e-tokens/fonts.css';
import '@kyralabs/m3e-tokens/tokens.css';
import '@kyralabs/m3e-tokens/theme.css';
import '@kyralabs/m3e-tokens/material-symbols.css'; // icons; without it they render as text
import '@kyralabs/m3e-css/index.css';
import { Button } from '@kyralabs/m3e-react';

export function Save() {
  return (
    <Button variant="tonal" size="m" onPress={() => console.log('saved')}>
      Save
    </Button>
  );
}
```

Peer dependencies: `react` and `react-dom` 18.3+ or 19.

Client-side rendering only (D6): the components carry no `'use client'` directive and are not
supported under server rendering or React Server Components. In Astro, mount them with
`client:only="react"`.

## Components and hooks

Every runtime export, grouped as in COMPONENT_SPEC. Each one renders the m3e-css classes of its
component (the same DOM as the matching `<m3e-*>` element, where there is one); props follow
React Aria (`on<Event>`, `is<State>`). The docs site, <https://m3epg.kyralabs.dev>, shows each one
next to its CSS and element versions. Prop types are exported as `<Name>Props`.

### Primitives

- `Icon`: a Material Symbols icon (`.m3e-icon`) with `fill`, `weight`, `grade` and `opticalSize`.
- `Surface`: a `<div>` with the `.m3e-surface` classes (container, variant, elevation, shape).
- `useStateLayer`: drives the state-layer ripple on your own element, as m3e-elements'
  `attachRipple` does.

### Buttons

- `Button`: the expressive button (filled, tonal, elevated, outlined, text; XS–XL), the press
  morph on a spring, or a link with `href`.
- `ToggleButton`: a button with `aria-pressed` whose shape morphs when selected.
- `IconButton`: icon button (standard, filled, tonal, outlined; sizes, widths, shapes); a toggle
  with `isSelected` or `defaultSelected`.
- `IconToggleButton`: icon toggle button; the selected icon is filled.
- `ButtonGroup`: standard or connected button group, with optional single or multiple
  selection.
- `ButtonGroupItem`: one button of a `ButtonGroup` (rendered by the group).
- `SplitButton`: a leading action button and a trailing button that opens a `menu`.
- `Fab`: floating action button (baseline, medium, large) in six color styles.
- `ExtendedFab`: extended FAB (small, medium, large); `isExpanded={false}` collapses it to the
  icon.
- `useExtendedFabScroll`: scroll-driven `isExpanded` for an `ExtendedFab`.
- `FabMenu`: a toggle FAB that opens a menu of 2–6 actions.

### Loading and progress

- `LoadingIndicator`: the shape-morphing loading indicator, contained or not, indeterminate or
  determinate.
- `LinearProgress`: linear progress indicator, flat or wavy.
- `CircularProgress`: circular progress indicator, flat or wavy.

### Toolbars, app bars and search

- `FloatingToolbar`: horizontal or vertical floating toolbar, optionally with a FAB, expanding and
  collapsing on springs.
- `DockedToolbar`: docked toolbar (Compose `FlexibleBottomAppBar`) with roving focus and the
  exit-always scroll behavior.
- `BottomAppBar`: **deprecated (D4)**, use `DockedToolbar`. The legacy bottom app bar.
- `TopAppBar`: small, center-aligned, medium and large flexible and two-rows top app bars, with
  the pinned, enter-always and exit-until-collapsed scroll behaviors.
- `SearchBar`: a search field that expands into a full-screen or docked view of results.
- `SearchResult`: one result row of a `SearchBar`.
- `AppBarWithSearch`: a top app bar holding a `SearchBar` between the navigation icon and the
  actions.

### Navigation

- `ShortNavigationBar`: the short navigation bar (vertical or horizontal items, badges).
- `WideNavigationRail`: the wide navigation rail, collapsed or expanded, animated between the two.
- `ModalWideNavigationRail`: a wide navigation rail that opens as a modal over a scrim when
  expanded.
- `NavigationDrawer`: permanent, dismissible or modal navigation drawer.
- `NavigationSuiteScaffold`: one set of destinations shown as a bar, rail or drawer by window size
  class (below).
- `NavigationBar`: **deprecated (D4)**, use `ShortNavigationBar`. The legacy 80dp navigation bar.
- `NavigationRail`: **deprecated (D4)**, use `WideNavigationRail`. The legacy 80dp navigation
  rail.
- `Tabs`: primary or secondary, fixed or scrollable tabs with their panels.
- `Tab`: declares one tab as a child of `Tabs` (instead of `items`).
- `TabPanel`: the content of one tab, a child of `Tabs`.

### Layout

- `useWindowSizeClass`: the window size class of the viewport or of an element (below).
- `ListDetailPaneScaffold`: the list-detail canonical layout (below).
- `useListDetailPaneScaffoldNavigator`: the navigator for a `ListDetailPaneScaffold`.
- `SupportingPaneScaffold`: the supporting-pane canonical layout.
- `useSupportingPaneScaffoldNavigator`: the navigator for a `SupportingPaneScaffold`.
- `FeedLayout`: the feed canonical layout, a CSS-only grid of items.

### Containment

- `Card`: filled, elevated or outlined card.
- `CardAction`: the primary action that makes a `Card` interactive.
- `List`: a list, static or with selection (`selectionMode`) or actions (`onAction`).
- `ListItem`: the expressive list item (one to three lines, leading and trailing content). Its
  `headlineContent` form, the non-expressive list item, is **deprecated (D4)**.
- `SegmentedListItem`: a list item on its own surface, 2dp from its neighbors.
- `Carousel`: multi-browse, uncontained, hero or full-screen carousel.
- `CarouselItem`: one item of a `Carousel`.
- `Badge`: a dot or a small count or label.
- `BadgedBox`: places a `Badge` on the top-end corner of its anchor.

### Chips

- `AssistChip`: assist chip, flat or elevated; a button or a link.
- `FilterChip`: filter chip, a checkbox, flat or elevated.
- `InputChipGroup`: a group of input chips with keyboard navigation and removal.
- `InputChip`: one input chip of an `InputChipGroup`.
- `SuggestionChip`: suggestion chip, a button or a link.
- `ChipSet`: a group of chips with one tab stop and arrow keys between them.

### Menus

- `Menu`: the expressive vertical menu (standard or vibrant colors, sections) or the baseline
  dropdown menu.
- `MenuItem`: a menu item: an action, or checkable when the menu has a `selectionMode`.
- `MenuSection`: a group of menu items on its own surface.
- `MenuTrigger`: opens a `Menu` from a button.

### Selection and text inputs

- `Checkbox`: checkbox with the indeterminate and error states.
- `RadioGroup`: a group of `Radio` buttons; arrow keys move the selection.
- `Radio`: one radio button of a `RadioGroup`.
- `Switch`: switch, with optional icons.
- `Slider`: slider (standard, centered, vertical; stops, sizes XS–XL, inset icon).
- `RangeSlider`: a slider with two thumbs.
- `TextField`: filled or outlined text field (icons, prefix and suffix, counter, multiline).
- `SingleChoiceSegmentedButtonRow`: **deprecated (D4)**, use a connected `ButtonGroup` with
  `selectionMode="single"`.
- `MultiChoiceSegmentedButtonRow`: **deprecated (D4)**, use a connected `ButtonGroup` with
  `selectionMode="multiple"`.
- `SegmentedButton`: **deprecated (D4)**, use `ButtonGroupItem` in a connected `ButtonGroup`.

### Pickers

- `DatePicker`: date picker (calendar and year grid, or the date input).
- `DateRangePicker`: date range picker.
- `DockedDatePicker`: a date field whose calendar drops down below it.
- `DatePickerDialog`: a date picker with dismiss and confirm actions in a dialog.
- `TimePicker`: time picker with a clock dial.
- `TimeInput`: time picker with two text fields.
- `TimeScroll`: time picker with two scroll wheels.
- `TimePickerDialog`: a time picker with its title, mode toggle and actions in a dialog.
- `VibrantTimePickerDialog`: the vibrant time picker dialog (no title, tighter padding).
- `TimePickerModeToggle`: the icon button that switches a time picker dialog's mode.

### Dialogs, sheets and feedback

- `AlertDialog`: alert dialog with an optional icon, a headline, text and actions.
- `BasicAlertDialog`: a modal dialog with custom content.
- `FullScreenDialog`: full-screen dialog below 600px, a basic dialog from 600px.
- `ModalBottomSheet`: modal bottom sheet over a scrim.
- `BottomSheet`: standard bottom sheet, fixed to the bottom of its container.
- `SideSheet`: standard, modal or adaptive side sheet.
- `Snackbar`: one snackbar (text, action, dismiss button).
- `SnackbarHost`: shows a queue's snackbars one at a time at the bottom of the window.
- `useSnackbarHostState`: the queue for a `SnackbarHost` (`showSnackbar(…)` resolves with the
  outcome).
- `TooltipTrigger`: attaches a tooltip to an anchor (hover, focus, long press).
- `PlainTooltip`: a short description of its anchor.
- `RichTooltip`: a subhead, supporting text and an optional action.
- `PullToRefresh`: pull down at the top of its content to refresh.

### Class-name helpers

`buttonClassName`, `iconButtonClassName`, `fabClassName`, `extendedFabClassName`,
`fabMenuClassName`, `floatingToolbarClassName`, `dockedToolbarClassName`, `assistChipClassName`,
`filterChipClassName`, `inputChipClassName` and `suggestionChipClassName` return the m3e-css
classes of a component, to style your own element (for example a router link) as one.

## Deprecated

The D4 components above and the small FAB (`<Fab size="small">`, use `size="baseline"`) ship until
2.0 and warn once in development. These props were renamed in 1.8; the old names still work, warn
once in development and are removed in 2.0:

- `ExtendedFab`, `FloatingToolbar`, `SearchBar`: `expanded` → `isExpanded`.
- `FabMenu`: `open` → `isOpen`.
- `FloatingToolbar`, `DockedToolbar`: `scrollBehavior="exitAlways"` → `"exit-always"`.
- `DatePicker`, `DateRangePicker`: `headline` → `showHeadline`.

## Window size classes

```tsx
import { paneScaffoldDirective } from '@kyralabs/m3e-motion'; // or the umbrella / m3e-elements
import { useWindowSizeClass } from '@kyralabs/m3e-react';

export function Inbox() {
  const sizeClass = useWindowSizeClass(); // the viewport, like @media
  const panes = paneScaffoldDirective(sizeClass).maxHorizontalPartitions;
  return panes > 1 ? <ListDetail /> : <List />;
}
```

`useWindowSizeClass({ target?, largeAndExtraLargeWidth?, initial? })` returns `{ widthClass,
heightClass, minWidth, minHeight }` and re-renders only when a class changes. Without `target`
the first render already reads the viewport; with a `target` ref it classifies that element's
content box (like `@container`) and returns `initial` (default compact × compact) until the
element is measured. The classification helpers (`windowSizeClass`, `isWidthAtLeastBreakpoint`,
`paneScaffoldDirective`, `navigationSuiteType`, …) come from `@kyralabs/m3e-motion`, a dependency
of this package, and are re-exported by `@kyralabs/m3e-elements` and `@kyralabs/m3exp-web`.

## Navigation suite scaffold

```tsx
import { NavigationSuiteScaffold } from '@kyralabs/m3e-react';

<NavigationSuiteScaffold
  aria-label="Main"
  items={[
    { key: 'home', icon: 'home', label: 'Home', href: '/' },
    { key: 'search', icon: 'search', label: 'Search', href: '/search' },
  ]}
  selectedKey={route}
  onSelectionChange={navigate}
  style={{ blockSize: '100dvh' }}
>
  <main>…</main>
</NavigationSuiteScaffold>;
```

The navigation follows the viewport's window size class: a short navigation bar below 600px
(horizontal items under 480px tall), a collapsed wide navigation rail from 600px, the expanded
rail from 1200px (`expandedFrom`, default `'large'`; `null` keeps Compose's rule; `expandedType:
'navigation-drawer'` for a drawer). `layoutType` fixes the type; `navigationSuiteType` replaces the
rule with a function of the size class. `isNavigationHidden` runs Compose's show / hide spring;
`primaryAction` (e.g. a `<Fab>`) floats above the bar or heads the rail / drawer. The selection,
the item elements (bar ↔ rail) and keyboard focus survive a switch.

## Canonical layouts

```tsx
import { ListDetailPaneScaffold, useListDetailPaneScaffoldNavigator } from '@kyralabs/m3e-react';

const navigator = useListDetailPaneScaffoldNavigator<number>();
<ListDetailPaneScaffold
  navigator={navigator}
  paneLabels={{ list: 'Inbox', detail: 'Message' }}
  hasDragHandle
  listPane={<Inbox onOpen={(id) => navigator.navigateTo('detail', id)} />}
  detailPane={<Message id={navigator.currentDestination?.contentKey} onBack={() => navigator.navigateBack()} />}
  style={{ blockSize: '100%' }}
/>;
```

`ListDetailPaneScaffold` / `SupportingPaneScaffold` (Compose's names) with
`useListDetailPaneScaffoldNavigator` / `useSupportingPaneScaffoldNavigator` (Compose
`remember…PaneScaffoldNavigator`): one pane below 840px of the layout's own width, two from 840px,
three from 1600px (m3.material.io; `paneRule="compose"`: from 1200px, as Compose). The navigator re-renders on each
change (`scaffoldValue`, `currentDestination`, `isExpanded(pane)`, `canNavigateBack()`). `FeedLayout`
is the CSS-only feed grid.

Apache-2.0; see `LICENSE` and `NOTICE`.
