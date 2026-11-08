# @kyralabs/m3e-elements

Zero-dependency Material 3 Expressive custom elements, for the behavior CSS alone can't provide.
Each element renders the `@kyralabs/m3e-css` DOM contract, so load that CSS too.

```sh
npm install @kyralabs/m3e-elements @kyralabs/m3e-css @kyralabs/m3e-tokens
```

## Usage

```js
// Plus the m3e-tokens stylesheets listed in the @kyralabs/m3e-css README.
import '@kyralabs/m3e-css/index.css';
import '@kyralabs/m3e-elements/icon.js';
import '@kyralabs/m3e-elements/loading-indicator.js';
```

```html
<m3e-icon name="favorite" fill></m3e-icon>
<m3e-loading-indicator contained aria-label="Loading"></m3e-loading-indicator>
```

Each `@kyralabs/m3e-elements/<element>.js` entry registers one element; `.` registers all of
them, and `./base.js` exports the `M3eElement` base class without registering anything.
Registration is skipped outside the browser.

Events are kebab-case `CustomEvent`s with a `detail`; a native event of an inner control with the
same name (`input`, `change`, `select`) does not reach the host. Each element with events exports an
`M3e<Name>EventMap`, and its `addEventListener` / `removeEventListener` are typed from it
(type-only), so `document.querySelector('m3e-dialog')?.addEventListener('open-change', (e) =>
e.detail.open)` needs no cast. Shared detail types: `OpenChangeDetail`, `ExpandedChangeDetail`,
`ValueDetail<T>`, `SelectionChangeDetail`. Helper functions and constants tagged `@internal` are
exported for m3e-react and are not part of the public API.

## FAB menu

`import '@kyralabs/m3e-elements/fab-menu.js'` registers `<m3e-fab-menu>` (and its data child
`<m3e-fab-menu-item>`): a toggle FAB that opens a menu of 2–6 actions with Compose's springs,
focus handling and light dismiss. It fires `open-change` (`detail.open`) and, on the item,
`action` (`detail.value`).

```html
<m3e-fab-menu label="Share" icon="share">
  <m3e-fab-menu-item icon="mail" value="email">Email</m3e-fab-menu-item>
  <m3e-fab-menu-item icon="link" value="link">Copy link</m3e-fab-menu-item>
</m3e-fab-menu>
```

## Menus

```js
import '@kyralabs/m3e-elements/menu.js';
```

```html
<button id="more" class="m3e-icon-button m3e-icon-button--standard" aria-label="More">
  <span class="m3e-icon" aria-hidden="true">more_vert</span>
</button>
<m3e-menu anchor="more" variant="vibrant">
  <m3e-menu-item value="edit" icon="edit" trailing-text="⌘E">Edit</m3e-menu-item>
  <m3e-menu-group label="View" divider>
    <m3e-menu-item type="checkbox" value="grid" checked-icon="check" checked>Grid</m3e-menu-item>
  </m3e-menu-group>
</m3e-menu>
```

`<m3e-menu>` renders the `.m3e-menu` popover from its `<m3e-menu-item>` / `<m3e-menu-group>`
children, wires its `anchor` (a click toggles it; Enter, Space and the arrow keys open it), places
it like Compose's `DropdownMenuPositionProvider` and springs it open and closed. It emits `action`
(on the item, `detail: { value, checked }`) and `open-change`. `variant`: `standard` (default),
`vibrant`, `baseline`. Items: `type="checkbox" | "radio"`, `checked`, `disabled`, `icon`,
`checked-icon`, `supporting-text`, `trailing-icon`, `trailing-text`, `submenu="<menu id>"`. The
`menu-popup.js` entry exports `MenuPopup` (placement and springs only) for other components.

## Button group

```js
import '@kyralabs/m3e-elements/button-group.js';
```

```html
<m3e-button-group variant="connected" selection-mode="single" label="View">
  <m3e-button-group-item value="day" selected>Day</m3e-button-group-item>
  <m3e-button-group-item value="week">Week</m3e-button-group-item>
</m3e-button-group>
```

`<m3e-button-group>` renders the `.m3e-button-group` contract from its `<m3e-button-group-item>`
children. Standard groups (default) grow a pressed button by Compose's `ExpandedRatio` while its
neighbors shrink, on an interruptible fast spatial spring; connected groups only morph the pressed
or selected button's corners. Attributes: `variant` (`standard` | `connected`), `size` (`xs`–`xl`),
`shape` (`round` | `square`), `button-variant`, `selection-mode` (`none` | `single` | `multiple`),
`disallow-empty-selection` (keeps one selected; `selection-required` is its deprecated name),
`overflow` (trailing items collapse into a "More options" menu; loads
`<m3e-menu>` on first use), `overflow-label`, `label`, `disabled`. Items: `value`, `icon`,
`selected`, `disabled`, `variant`, `label` (icon-only). Events: `selection-change` on the
group (`detail: { value, selected, values }`; the deprecated `change` carries the same detail) and
`action` on the item (`detail: { value }`). Arrow keys,
Home and End move focus (one tab stop). The `button-group-layout.js` entry exports
`ButtonGroupLayout` (springs, overflow measurement and roving focus for a rendered group), which
m3e-react's `<ButtonGroup>` uses too.

## Split button

```js
import '@kyralabs/m3e-elements/menu.js';
import '@kyralabs/m3e-elements/split-button.js';
```

```html
<m3e-split-button label="Send" icon="mail" menu-label="More send options" variant="tonal">
  <m3e-menu>
    <m3e-menu-item value="schedule">Schedule send</m3e-menu-item>
    <m3e-menu-item value="draft">Save draft</m3e-menu-item>
  </m3e-menu>
</m3e-split-button>
```

`<m3e-split-button>` renders the `.m3e-split-button` contract (a leading and a trailing
`.m3e-button`; load m3e-css `button.css` and `split-button.css`) and makes the trailing button the
anchor of its `<m3e-menu>` child (or the menu whose id `menu` names), which then handles the press,
the keys, Escape and `aria-expanded`. While the menu is open the trailing button's inner corners
spring to full and its icon turns 180°. `variant`: `filled` (default), `tonal`, `elevated`,
`outlined`; `size`: `xs`, `s` (default), `m`, `l`, `xl`; `trailing-icon` (default
`keyboard_arrow_down`); `disabled`. It emits `press` when the leading button is activated.

## Floating toolbar

```js
import '@kyralabs/m3e-elements/floating-toolbar.js';
```

```html
<m3e-floating-toolbar expanded label="Formatting" scroll-behavior="exit-always">
  <button class="m3e-icon-button" slot="leading" aria-label="Done">…</button>
  <button class="m3e-icon-button" aria-label="Bold">…</button>
  <button class="m3e-icon-button" aria-label="Italic">…</button>
  <button class="m3e-fab" slot="fab" aria-label="Add">…</button>
</m3e-floating-toolbar>
```

`<m3e-floating-toolbar>` renders the `.m3e-floating-toolbar` contract (`role="toolbar"`) and moves
its children into it: `slot="leading"` / `slot="trailing"` items show only while `expanded`,
`slot="fab"` makes the with-FAB toolbar (collapsed, the toolbar folds into the FAB). Attributes:
`expanded`, `orientation` (`horizontal` | `vertical`), `color-style` (`standard` | `vibrant`),
`label`, `fab-position` (`end` | `start`), `scroll-behavior` (`exit-always` hides it on scroll
down; `collapse` collapses it on scroll down and fires `expanded-change`), `exit-direction`,
`scroll-target` (the scrolling element's id). The expand/collapse springs, hidden parts made
`inert`, roving focus and the scroll behaviors come from the `floating-toolbar-layout.js` entry
(`FloatingToolbarLayout`), which m3e-react's `<FloatingToolbar>` uses too. Position it with
`inset`/margins: the exit offset uses `translate`.

The `roving-focus.js` entry exports `RovingFocus`, the toolbar keyboard helper (one tab stop,
arrows along the orientation mirrored in RTL, Home/End, no wrapping; `tabbable = false` takes the
widget out of the tab order) for other composite widgets such as the docked toolbar.

## Docked toolbar

```js
import '@kyralabs/m3e-elements/docked-toolbar.js';
```

```html
<m3e-docked-toolbar label="Actions" arrangement="center" scroll-behavior="exit-always">
  <button class="m3e-icon-button" aria-label="Back">…</button>
  <button class="m3e-icon-button" aria-label="Add">…</button>
  <button class="m3e-icon-button" aria-label="Edit">…</button>
</m3e-docked-toolbar>
```

`<m3e-docked-toolbar>` (Compose `FlexibleBottomAppBar`) renders the `.m3e-docked-toolbar`
contract (`role="toolbar"`) and moves its children into it. Attributes: `arrangement` (`spread`
default, `center`, `space-around`, `space-evenly`), `color-style` (`standard` | `vibrant`),
`label`, `scroll-behavior` (`exit-always` hides it on scroll down and brings it back on scroll up;
a partly hidden bar snaps on the fast spatial spring when scrolling stops), `scroll-target` (the
scrolling element's id). Roving focus and the scroll behavior come from the
`docked-toolbar-layout.js` entry (`DockedToolbarLayout`), which m3e-react's `<DockedToolbar>` and
deprecated `<BottomAppBar>` use too. Dock it yourself (`position: fixed` / `sticky` /
`absolute`, `inset-block-end: 0`): the exit offset uses `translate`. The deprecated legacy bottom
app bar (D4) has no element; use m3e-css `bottom-app-bar.css` or m3e-react `<BottomAppBar>`.

## Progress indicators

```js
import '@kyralabs/m3e-elements/linear-progress.js';
import '@kyralabs/m3e-elements/circular-progress.js';
```

```html
<m3e-linear-progress value="0.4" aria-label="Loading news article"></m3e-linear-progress>
<m3e-linear-progress shape="wavy" aria-label="Loading my episodes"></m3e-linear-progress>
<m3e-circular-progress shape="wavy" thickness="thick" value="0.7" aria-label="Downloading">
</m3e-circular-progress>
```

`<m3e-linear-progress>` and `<m3e-circular-progress>` render the `.m3e-linear-progress` /
`.m3e-circular-progress` contracts (load m3e-css `linear-progress.css` / `circular-progress.css`).
`value` (0–1) makes them determinate (`aria-valuenow` 0–100); without it they are indeterminate.
`shape="wavy"` draws Compose's wave every frame (it holds still with `prefers-reduced-motion`);
`thickness="thick"` is the 8dp sample configuration; `amplitude` (0–1), `wavelength` (px) and
`wave-speed` (px/s) override the wave. Value changes spring on Compose's progress spring. The
host's `aria-label` (or `label`) names the progress bar. Flat indicators also work without JS
(markup in the m3e-css files).

## Top app bar

```js
import { attachTopAppBarScroll } from '@kyralabs/m3e-elements/top-app-bar.js';

const controller = new AbortController();
attachTopAppBarScroll(document.querySelector('.m3e-top-app-bar'), {
  behavior: 'exit-until-collapsed',
  signal: controller.signal,
});
```

```html
<header class="m3e-top-app-bar m3e-top-app-bar--medium-flexible">
  <div class="m3e-top-app-bar__navigation">…menu button…</div>
  <div class="m3e-top-app-bar__headline" aria-hidden="true">
    <p class="m3e-top-app-bar__title">Inbox</p>
  </div>
  <div class="m3e-top-app-bar__actions">…icon buttons…</div>
  <div class="m3e-top-app-bar__expanded">
    <div class="m3e-top-app-bar__headline"><p class="m3e-top-app-bar__title">Inbox</p></div>
  </div>
</header>
```

There is no top app bar element: the bars (small, center-aligned, medium and large flexible,
two-rows) are m3e-css markup (load `top-app-bar.css`), and the `top-app-bar.js` entry registers
nothing. `attachTopAppBarScroll(bar, { behavior, target, signal })` adds Compose's scroll
behaviors: `pinned` (default; only the container color reacts), `enter-always` (the bar, or a
two-rows bar's `__expanded` row, collapses on scroll down and returns on any scroll up) or
`exit-until-collapsed` (it expands again when the content comes back to its start). `target` is
the scrolling element (default: the window); aborting `signal` detaches it and clears what it
wrote. It writes `data-scroll-behavior`, `data-scrolled` (content scrolled under the bar) and the
private height offset and title fractions m3e-css reads; a partly collapsed bar snaps open or
closed when scrolling stops, and opens when focus moves into a hidden part. On a two-rows bar (one
with an `__expanded` row) the top row's headline is the collapsed title: mark it `aria-hidden`, as
above; the function moves `aria-hidden` to whichever headline Compose hides. Custom two-rows
heights (Compose's `collapsedHeight` / `expandedHeight`) are public custom properties on the bar
or an ancestor: `--m3e-comp-top-app-bar-container-collapsed-height` and
`--m3e-comp-top-app-bar-container-expanded-height` (the private `--_m3e-top-app-bar-*-height`
still work and are deprecated since 1.8). m3e-react's `<TopAppBar scrollBehavior>` calls the same
function.

## Search

```js
import '@kyralabs/m3e-elements/search.js';
```

```html
<m3e-search variant="docked" placeholder="Search mail" label="Search mail">
  <m3e-search-result icon="history" supporting-text="Recent">Inbox</m3e-search-result>
  <m3e-search-result icon="history">Drafts</m3e-search-result>
  <button class="m3e-icon-button" aria-label="Voice search">…</button>
</m3e-search>
```

`<m3e-search>` (Compose `SearchBar` + `SearchBarDefaults.InputField`) renders the `.m3e-search`
contract (load m3e-css `search.css`): a `role="search"` landmark around a combobox input and a
listbox of its `<m3e-search-result>` children (`value`, `icon`, `supporting-text`,
`trailing-icon`, `disabled`); other children go to the trailing slot. `variant` picks the expanded
view: `full-screen` (default, `ExpandedFullScreenSearchBar`), `full-screen-contained`, `docked`
or `docked-with-gap`. A click on the field, typing or ArrowDown expands it (the view moves into the
top layer on the variant's springs); ArrowDown / ArrowUp move the active result
(`aria-activedescendant`), Enter selects it or searches, Escape, the back button or a light dismiss
collapse it. Full-screen views trap Tab. Events: `expanded-change`, `search` and `select`
(cancelable). The behavior lives in the `search-layout.js` entry (`SearchLayout`), which m3e-react's
`<SearchBar>` uses too. AppBarWithSearch is markup: put the search between the navigation and
actions of a `.m3e-top-app-bar.m3e-top-app-bar--search` and call
`attachTopAppBarScroll(bar, { behavior: 'enter-always' })` for its scroll behavior.

## Window size classes

```js
import { observeWindowSizeClass, paneScaffoldDirective } from '@kyralabs/m3e-elements';

const controller = new AbortController();
observeWindowSizeClass(
  (sizeClass) => {
    // { widthClass: 'compact' | 'medium' | 'expanded' | 'large' | 'extra-large',
    //   heightClass: 'compact' | 'medium' | 'expanded', minWidth, minHeight }
    document.body.dataset.panes = String(paneScaffoldDirective(sizeClass).maxHorizontalPartitions);
  },
  { signal: controller.signal },
);
```

`observeWindowSizeClass(callback, { signal, target?, largeAndExtraLargeWidth? })` calls back right
away and then whenever the width or height class changes (FOUNDATIONS §9; androidx
`WindowSizeClass`, Compose `currentWindowAdaptiveInfoV2()`). Without `target` it follows the
viewport through one `matchMedia('(min-width: …px)')` query per breakpoint, so it classifies
exactly like an `@media` rule and wakes only when a breakpoint is crossed; with `target` it
follows that element's content box through a ResizeObserver, like an `@container` query.
`currentWindowSizeClass(options?)` reads the class once. Both do nothing (`null`) without a DOM.
The entry (`@kyralabs/m3e-elements/window-size-class.js`, registers nothing) also re-exports the
m3e-motion classification: `windowSizeClass`, `windowWidthSizeClass`, `windowHeightSizeClass`,
`isWidthAtLeastBreakpoint`, `isHeightAtLeastBreakpoint`, `isAtLeastBreakpoint`,
`paneScaffoldDirective` (Compose `calculatePaneScaffoldDirective`), `navigationSuiteType`
(`NavigationSuiteScaffoldDefaults.navigationSuiteType`) and `WINDOW_WIDTH_BREAKPOINTS` /
`WINDOW_HEIGHT_BREAKPOINTS`. For CSS queries use the px values in the m3e-tokens README.

## Navigation bar and rails

```js
import '@kyralabs/m3e-elements/short-navigation-bar.js';
import '@kyralabs/m3e-elements/wide-navigation-rail.js';
import '@kyralabs/m3e-elements/modal-wide-navigation-rail.js';
```

```html
<m3e-wide-navigation-rail label="Main" selected="inbox">
  <button class="m3e-icon-button" aria-label="Expand" onclick="this.closest('m3e-wide-navigation-rail').toggle()">…</button>
  <m3e-navigation-item value="inbox" icon="inbox" href="/inbox">Inbox</m3e-navigation-item>
  <m3e-navigation-item value="sent" icon="send" href="/sent">Sent</m3e-navigation-item>
</m3e-wide-navigation-rail>
```

`<m3e-short-navigation-bar>` (Compose `ShortNavigationBar`; `layout="horizontal"`),
`<m3e-wide-navigation-rail>` (`WideNavigationRail`) and `<m3e-modal-wide-navigation-rail>`
(`ModalWideNavigationRail`) render the m3e-css `.m3e-short-navigation-bar` /
`.m3e-wide-navigation-rail` / `.m3e-modal-wide-navigation-rail` contracts (load
`short-navigation-bar.css` / `wide-navigation-rail.css`) from their `<m3e-navigation-item>` children
(`value`, `icon`, `href` for a link, `disabled`, `label-hidden`); other rail children go to the
header. `selected` marks one item `aria-current="page"`; a press fires a cancelable
`selection-change`. On the rails, `expanded` (or `expand()` / `collapse()` / `toggle()`) animates
width, items and labels on Compose's springs, one layout per frame and interruptible. The modal
rail opens over a scrim as a `dialog` (focus trapped, Escape or the scrim collapse it with a
cancelable `expanded-change`, focus returns to the opener); `hide-on-collapse` slides it in from the
edge instead of expanding a collapsed rail. The behavior lives in the `wide-navigation-rail-layout.js`
entry (`WideNavigationRailLayout`), which m3e-react's `<WideNavigationRail>` /
`<ModalWideNavigationRail>` use too. The deprecated legacy bar and rail (D4) get no elements.

## Navigation drawer

```js
import '@kyralabs/m3e-elements/navigation-drawer.js';
```

```html
<m3e-navigation-drawer variant="modal" label="Main" selected="inbox">
  <h2 class="m3e-navigation-drawer__headline">Mail</h2>
  <m3e-navigation-item value="inbox" icon="inbox" href="/inbox" badge="24">Inbox</m3e-navigation-item>
  <m3e-navigation-item value="sent" icon="send" href="/sent">Sent</m3e-navigation-item>
  <hr class="m3e-navigation-drawer__divider" />
  <m3e-navigation-item value="trash" icon="delete" href="/trash">Trash</m3e-navigation-item>
</m3e-navigation-drawer>
```

`<m3e-navigation-drawer>` (Compose `PermanentNavigationDrawer` / `DismissibleNavigationDrawer` /
`ModalNavigationDrawer`) renders the `.m3e-navigation-drawer` contract (load
`navigation-drawer.css`): a `<nav>` sheet of `.m3e-navigation-drawer-item`s from its
`<m3e-navigation-item>` children (`value`, optional `icon`, `href`, `badge`); other children move
into the sheet in their order. `variant`: `permanent` (default; place it in a flex row before the
content), `dismissible` (in the layout, shown with `open`; the content beside it moves) or `modal`
(opens over a scrim as a `dialog`: focus moves in and is trapped, Escape or the scrim close it,
focus returns to the opener). `open` (or `show()` / `close()` / `toggle()`) animates on Compose's
springs; a drag on the open sheet or scrim closes it past Compose's thresholds; ArrowDown / ArrowUp
move between items. Events: `selection-change`, `open-change` (`detail: { open }`, cancelable when
Escape, the scrim or a drag ask). The behavior lives in the `navigation-drawer-layout.js` entry
(`NavigationDrawerLayout`), which m3e-react's `<NavigationDrawer>` uses too.

## Navigation suite

```js
import '@kyralabs/m3e-elements/navigation-suite.js';
```

```html
<m3e-navigation-suite label="Main" selected="home" style="block-size: 100dvh">
  <m3e-navigation-item value="home" icon="home" href="/">Home</m3e-navigation-item>
  <m3e-navigation-item value="search" icon="search" href="/search">Search</m3e-navigation-item>
  <button slot="primary-action" class="m3e-fab" aria-label="Compose">
    <span class="m3e-icon" aria-hidden="true">edit</span>
  </button>
  <main>…</main>
</m3e-navigation-suite>
```

`<m3e-navigation-suite>` (Compose `NavigationSuiteScaffold`) renders the `.m3e-navigation-suite`
contract (load `navigation-suite.css`): its `<m3e-navigation-item>` children as the navigation the
viewport's window size class calls for — a short navigation bar below 600px (horizontal items when
the window is under 480px tall), a collapsed wide navigation rail from 600px, the expanded rail
from 1200px — and every other child in the content area (`slot="primary-action"`: above the bar,
the rail's header, the drawer's first entry). Switching keeps the selection, the item elements
(bar ↔ rail) and keyboard focus. `layout-type` fixes the type (`short-navigation-bar-compact`,
`short-navigation-bar-medium`, `wide-navigation-rail-collapsed`, `wide-navigation-rail-expanded`,
`navigation-drawer`, `none`); `expanded-from` (`large` default, a class or px bound, `none` for
Compose's rule) and `expanded-type` (`navigation-drawer`) tune the default rule; the
`navigationSuiteType` property replaces it with a function of the window size class. The read-only
`type` is the type shown. `navigation-hidden` (or `hideNavigation()` / `showNavigation()` /
`toggleNavigation()`) runs Compose's show / hide spring. Events: `selection-change`,
`navigation-hidden-change`, `navigation-suite-type-change` (`detail: { type }`). The behavior lives
in the `navigation-suite-layout.js` entry (`NavigationSuiteLayout`), which m3e-react's
`<NavigationSuiteScaffold>` uses too.

## Tabs

```js
import '@kyralabs/m3e-elements/tabs.js';
```

```html
<m3e-tabs label="Media" selected="photos">
  <m3e-tab value="videos" icon="videocam">Videos</m3e-tab>
  <m3e-tab value="photos" icon="photo">Photos</m3e-tab>
  <m3e-tab-panel value="videos">…</m3e-tab-panel>
  <m3e-tab-panel value="photos">…</m3e-tab-panel>
</m3e-tabs>
```

`<m3e-tabs>` (Compose `PrimaryTabRow` / `SecondaryTabRow` / `PrimaryScrollableTabRow` /
`SecondaryScrollableTabRow` with `Tab` / `LeadingIconTab`) renders the `.m3e-tabs` contract (load
`tabs.css`): a `role="tablist"` of `.m3e-tab`s from its `<m3e-tab>` children (`value`, optional
`icon`, `disabled`, `label-hidden`), and makes each `<m3e-tab-panel value>` child the matching
`role="tabpanel"` (labelled by its tab, hidden unless selected). `variant`: `primary` (default) or
`secondary`; `scrollable`; `icon-position="leading"` puts icons before labels; `label` names the
tablist; the host `id` prefixes the tab and panel ids. Activation is manual (Compose,
m3.material.io): the arrow keys (mirrored in RTL), Home and End move the focus without wrapping,
a press, Enter or Space selects. Selecting slides the indicator on Compose's spring and a
scrollable row scrolls the selected tab to the centre. Event: `selection-change`
(`detail: { value }`, cancelable). The behavior lives in the `tabs-layout.js` entry
(`TabsLayout`), which m3e-react's `<Tabs>` uses too.

## Checkbox

```js
import '@kyralabs/m3e-elements/checkbox.js';
```

```html
<m3e-checkbox name="mail" value="daily" checked>Daily</m3e-checkbox>
<m3e-checkbox indeterminate>Receive emails</m3e-checkbox>
```

`<m3e-checkbox>` renders the m3e-css `.m3e-checkbox` contract around a native
`<input type="checkbox">`, which submits with its form and fires the native `input` / `change`
events. It exists for what plain HTML cannot declare: the `indeterminate` attribute sets the input
property, `data-from` keeps the previous state (a dash entered from unchecked draws instead of
morphing from a check, as Compose does) and the ripple presses on Space or a pointer on the label.
Attributes: `checked`, `indeterminate`, `disabled`, `invalid` (`aria-invalid`, error colors),
`required` (`aria-required`), `name`, `value`, `label` (the input's `aria-label` when there is no
text). A user toggle updates `checked` and clears `indeterminate`.

## Chip set

```js
import '@kyralabs/m3e-elements/chip-set.js';
```

```html
<m3e-chip-set label="Recipients">
  <div class="m3e-input-chip" data-value="ada">
    <div class="m3e-input-chip__cell">
      <img class="m3e-input-chip__avatar" src="ada.jpg" alt="" />
      <span class="m3e-input-chip__label">Ada Lovelace</span>
      <button class="m3e-input-chip__remove">
        <span class="m3e-icon" aria-hidden="true">close</span>
      </button>
    </div>
  </div>
</m3e-chip-set>
```

`<m3e-chip-set>` renders the m3e-css `.m3e-chip-set` (load `chip-set.css` and the chip files) inside
itself and moves its children, chips in the m3e-css markup, into it. The set is one tab stop with
the arrow keys (mirrored in RTL, wrapping at the ends as React Aria's TagGroup does), Home and End
between its chips (a filter chip's native checkbox, an assist or suggestion chip, an input chip).
With input chips it is a `role="grid"` of `role="row"` chips wired as React Aria's TagGroup
(m3e-react `<InputChipGroup>` renders the same DOM): Backspace or Delete on a focused input chip, or
a press on its remove button (labelled "Remove <label>"), emits `remove` (`detail: { value, chip }`,
cancelable; `value` is `data-value`, else the label); unless canceled, the chip is removed and the
focus moves to the next chip. Attributes: `label` (the set's accessible name), `single-line` (one
scrolling row). Filter, assist and suggestion chips need no element: a filter chip is a native
checkbox. The behavior lives in the `chip-set-layout.js` entry (`ChipSetLayout`), which m3e-react's
`<ChipSet>` uses too.

## Slider

```js
import '@kyralabs/m3e-elements/slider.js';
```

```html
<m3e-slider label="Volume" value="0.4"></m3e-slider>
<m3e-slider label="Percent" max="100" step="10" value="40" size="m" icon="volume_up"></m3e-slider>
<m3e-slider label="Price" range max="100" start-value="20" end-value="80"></m3e-slider>
<m3e-slider label="Balance" variant="centered" min="-50" max="50"></m3e-slider>
<m3e-slider label="Brightness" orientation="vertical" style="block-size: 200px"></m3e-slider>
```

`<m3e-slider>` renders the m3e-css `.m3e-slider` (load `slider.css`) inside itself, one native
`<input type="range">` per thumb (its role, value, labels and form `name`), and adds pointer
presses and drags on the track (a range slider moves the closer thumb; the thumbs meet but never
cross), the keyboard (arrows by one `step`, or 1 % of the range without one; Shift + arrow and
Page Up / Page Down by a page; Home / End; horizontal arrows mirror in RTL, and a vertical slider's
minimum is at the bottom), the handle shrink and value indicator while dragged (`data-dragging`),
and `input` / `change` events (`detail: { value }`, a range `{ start, end }`; `change` when a drag,
press or key ends). Attributes: `min` (0), `max` (1), `step`, `value`, `range` with `start-value` /
`end-value` (thumbs labelled `start-label` / `end-label`, default "Range start" / "Range end"),
`variant` (`standard` | `centered`), `orientation` (`horizontal` | `vertical`; the booleans
`centered` and `vertical` are deprecated), `size` (`xs` default, `s`, `m`, `l`, `xl`), `icon` (an inset icon, M–XL),
`disabled`, `label`, `name`. The value math is m3e-motion's port of Compose's `Slider.kt`; the
`slider-layout.js` entry (class names, custom properties, input attributes, value text) is shared
with m3e-react's `<Slider>` / `<RangeSlider>`, which render the same DOM.

## Text field

```js
import '@kyralabs/m3e-elements/text-field.js';
```

```html
<m3e-text-field label="Email" name="email" type="email"></m3e-text-field>
<m3e-text-field variant="outlined" label="Bio" maxlength="20" supporting-text="Public"></m3e-text-field>
<m3e-text-field label="User" invalid error-text="Already taken" required></m3e-text-field>
<m3e-text-field variant="outlined" label="Notes" multiline></m3e-text-field>
```

`<m3e-text-field>` renders the m3e-css `.m3e-text-field` (load `text-field.css`) inside itself
around a native `<input>` (or, with `multiline`, a `<textarea>`) that takes part in forms and fires
the native `input` / `change` events. The label float, colors and outlined notch need no script
(the plain markup works without this element); the element adds the live character counter
(`maxlength`: "n/max", read as "Character count, n/max") and grows the textarea where CSS
`field-sizing: content` is missing. Attributes: `variant` (`filled` default, `outlined`), `label`,
`label-position` (`above`), `value`, `placeholder`, `type`, `name`, `autocomplete`, `inputmode`,
`supporting-text`, `error-text` (shown instead while `invalid`, with the "alert" role), `invalid`,
`disabled`, `readonly`, `required`, `maxlength`, `multiline`, `leading-icon`, `trailing-icon`,
`prefix-text`, `suffix-text`, `counter-label`. The `text-field-layout.js` entry (class names,
counter text, describedby, textarea growth) is shared with m3e-react's `<TextField>`, which renders
the same DOM.

## List

```html
<m3e-list label="Pets" selection-mode="single">
  <div class="m3e-list-item" data-value="cat">
    <span class="m3e-list-item__content"><span class="m3e-list-item__headline">Cat</span></span>
  </div>
  <div class="m3e-list-item" data-value="dog" aria-selected="true">
    <span class="m3e-list-item__content"><span class="m3e-list-item__headline">Dog</span></span>
  </div>
</m3e-list>
```

Static lists need no script (`<ul class="m3e-list">` of `<li class="m3e-list-item">`, load
`list.css`). `<m3e-list>` renders an interactive `.m3e-list` inside itself and moves its
`.m3e-list-item` children (m3e-css markup; `data-value` keys them, `aria-selected="true"` and
`aria-disabled="true"` set the initial state) into it: a `role="listbox"` of options with one tab
stop, arrow keys that wrap (Down / Right next, Up / Left previous), Home / End and typeahead.
`selection-mode="single" | "multiple"` (`selection` is its deprecated name): click, Space or Enter toggles an option and emits
`selection-change` (`detail: { values, value }`, cancelable); a checkbox, radio button or switch in
a slot is made inert and shows the option's state. `selection-mode="none"` (the default): click or Enter
emits `action` (`detail: { value }`). Also `label`, `disallow-empty-selection` and the
`selectedValues` property. The `list-layout.js` entry (ListLayout, item class names, the indicator
markup) is shared with m3e-react's `<List>`, which renders the same DOM.

## Tooltip

```html
<button id="fav" class="m3e-icon-button" aria-label="Favorite">…</button>
<m3e-tooltip anchor="fav">Add to favorites</m3e-tooltip>

<m3e-tooltip anchor="info" variant="rich" subhead="Permissions" action="Request access" persistent>
  Configure permissions for selected service accounts.
</m3e-tooltip>
```

`<m3e-tooltip>` renders a `.m3e-tooltip` popover inside itself, moves its own child nodes into it
as the text and adds its id to the anchor's `aria-describedby`. It runs Compose's `TooltipBox`
behavior: mouse hover shows it at once; it stays while the anchor or the tooltip is hovered and hides
1.5s after the pointer leaves both (m3.material.io); a
touch long press shows it until the press ends (at least `--m3e-comp-tooltip-duration`); keyboard
focus shows it until focus leaves; Escape and a click outside hide it; one tooltip shows at a time.
`position` (`above` | `below` | `left` | `right` | `start` | `end`, Compose
`TooltipAnchorPosition`), `caret`, `persistent` (stays until a click outside or Escape), `manual`
(no hover / focus / long press), `open` (reflected), `show()` (hides again after the duration
unless persistent) and `hide()`. A rich tooltip with an `action` is a non-modal `role="dialog"`
that Tab from the anchor moves into; the action emits a cancelable `action` event and hides the
tooltip. Events: `open-change` (`detail: { open }`). The `tooltip-popup.js` entry
(`TooltipController`, `TooltipPopup`) is shared with m3e-react's `<TooltipTrigger>`, which renders
the same DOM.

## Dialog

```html
<button class="m3e-button m3e-button--filled" onclick="discard.show()">Discard</button>
<m3e-dialog id="discard" headline="Discard draft?" icon="delete">
  This permanently deletes the draft.
  <button class="m3e-button m3e-button--text" slot="actions">Cancel</button>
  <button class="m3e-button m3e-button--text" slot="actions">Discard</button>
</m3e-dialog>

<m3e-dialog variant="full-screen" headline="New event">
  …form…
  <button class="m3e-button m3e-button--text" slot="actions">Save</button>
</m3e-dialog>
```

`<m3e-dialog>` renders a native `<dialog class="m3e-dialog">` inside itself (the alert dialog has
`role="alertdialog"`, named by `headline` and described by the text) and moves its own child nodes
into it: `slot="actions"` children into the actions row (the dismiss button first), the rest into
the content. `variant`: `alert` (default; Compose `AlertDialog`, with an optional `icon`),
`custom` (Compose `BasicAlertDialog`: the children draw their own surface; named by `label`,
default "Dialog") or `full-screen` (m3.material.io: a header with a close button, named by
`close-label`, default "Close"; full-screen below 600px, a basic dialog from 600px). `open`
(reflected), `show()`, `close()`. It opens with `showModal()` (the page inert, the scroll locked, Tab
kept inside, focus on the first control and back on the opener when it closes) and animates in and
out; Escape, the scrim, the close button and browser close requests emit a cancelable
`open-change` (`detail: { open }`; `preventDefault()` keeps the dialog open). The
`dialog-layout.js` entry (`DialogLayout`) is shared with m3e-react's `<AlertDialog>`,
`<BasicAlertDialog>` and `<FullScreenDialog>`, which render the same DOM.

## Snackbar

```html
<m3e-snackbar-host id="snackbars"></m3e-snackbar-host>
<script type="module">
  const result = await snackbars.showSnackbar({ message: 'Message archived', actionLabel: 'Undo' });
  if (result === 'action-performed') undoArchive();
  snackbars.showSnackbar('Saved'); // 4s, no action
</script>
```

`<m3e-snackbar-host>` renders a `.m3e-snackbar-host` inside itself: a polite live region
(`role="status"`) fixed to the bottom center of the window (raise it above a FAB with
`--m3e-comp-snackbar-host-bottom-offset`) that shows one snackbar at a time (Compose
`SnackbarHost`). `showSnackbar(message | { message, actionLabel, withDismissAction, duration,
signal })` queues one and resolves with `'action-performed'` or `'dismissed'`; `duration` is
`short` (4s, the default without an action), `long` (10s) or `indefinite` (the default with an
action). The timer pauses while the snackbar is hovered or focused, Escape in it dismisses it, and
`focus()` moves focus to its action (bind it to a shortcut of your app). The dismiss button
(`withDismissAction`, named by `dismiss-label`, default "Dismiss") has the plain tooltip Compose
builds in. `action-on-new-line` puts the action under the text. `hostState` is the queue (a
`SnackbarHostState`, which can also be shared or driven from code); the `snackbar-layout.js` entry
(`SnackbarHostState`, `SnackbarHostController`) is shared with m3e-react's `<SnackbarHost>`, which
renders the same DOM.

## Bottom sheet

```html
<button class="m3e-button m3e-button--filled" onclick="sheet.show()">Show bottom sheet</button>
<m3e-bottom-sheet id="sheet" variant="modal">…content…</m3e-bottom-sheet>

<div style="position: relative; block-size: 480px">
  <main>…</main>
  <m3e-bottom-sheet value="partially-expanded" peek-height="128" skip-hidden-state label="Details">
    …content…
  </m3e-bottom-sheet>
</div>
```

`<m3e-bottom-sheet>` (Compose `BottomSheet` / `ModalBottomSheet`) renders a `.m3e-bottom-sheet`
inside itself (load m3e-css `bottom-sheet.css`); its child nodes are the content. `variant`:
`standard` (default; fixed to the bottom of its positioned container, a region named `label`) or
`modal` (a native `<dialog>` over a scrim: the page inert, Tab kept inside, focus back on the
opener when it hides). `value` (reflected): `hidden` (default), `partially-expanded` or
`expanded`; `open` (reflected) is whether `value` is not `hidden`, and setting it shows or hides
the sheet like `show()` / `hide()`. `skip-partially-expanded` drops the partially expanded state;
`peek-height` (px, standard only; empty: 56) shows that much of the sheet when partially expanded
(Compose `sheetPeekHeight`) and `skip-hidden-state` then drops `hidden`. `no-drag-handle`,
`drag-handle-label` (default "Drag handle"; the handle has the plain tooltip Compose builds in),
`gestures-disabled` and `label` (default "Bottom Sheet"). Methods `show()`, `hide()`, `expand()`,
`partialExpand()`. When the sheet asks to move (the handle, a drag, Escape, the scrim, a method)
it fires a cancelable `value-change` (`detail: { value }`; `preventDefault()` keeps the current
value) and then, when that shows or hides it, a cancelable `open-change` (`detail: { open }`), as
the other modal elements do; setting `value` or `open` fires nothing. The behavior lives in the
`bottom-sheet-layout.js` entry (`BottomSheetLayout`), imported when the element first renders
(`ready` resolves once it runs) and shared with m3e-react's `<BottomSheet>` and
`<ModalBottomSheet>`, which render the same DOM.

## Side sheet

```html
<div style="display: flex; block-size: 100dvh">
  <main style="flex: 1; min-inline-size: 0">…</main>
  <m3e-side-sheet id="details" headline="Details" open>…</m3e-side-sheet>
</div>

<m3e-side-sheet id="filters" variant="modal" headline="Filters" back-button detached divider>
  …filters…
  <button class="m3e-button m3e-button--filled" slot="actions">Save</button>
  <button class="m3e-button m3e-button--outlined" slot="actions">Cancel</button>
</m3e-side-sheet>
```

`<m3e-side-sheet>` (D8: m3.material.io only) renders a `.m3e-side-sheet` inside itself and moves
its own child nodes into it: `slot="actions"` children into the bottom actions, the rest into the
content, which scrolls on its own. `variant`: `standard` (default; an `<aside>` that, as the last
child of a flex row, takes the sheet's width from the row while open, so the content beside it
shrinks), `modal` (a native `<dialog>` at the window's end edge over a scrim: the page inert, the
scroll locked, Tab kept inside, focus on its first button and back on the opener when it closes)
or `adaptive` (modal below 600px, the medium window size class, standard from it; it switches when
the window crosses 600px and stays open). The header has the close button m3.material.io requires
(`close-label`, default "Close"), the `headline` (it names the sheet; without one, `label`, default
"Side sheet") and, with `back-button` (deprecated name: `back`), a back button (`back-label`, default "Back") that fires `back`.
`detached` insets it by 16px with all corners rounded; `divider` draws the standard sheet's line
along its start edge, or the modal sheet's line above its actions. `open` (reflected), `show()`,
`close()`, `toggle()`; the close button, Escape and the scrim emit a cancelable `open-change`
(`detail: { open }`). It opens on the default spatial spring and closes on the fast effects spring
(the navigation drawer's motion, mirrored). The `side-sheet-layout.js` entry (`SideSheetLayout`)
is shared with m3e-react's `<SideSheet>`, which renders the same DOM.

## Carousel

```html
<m3e-carousel label="Featured" item-width="186" item-spacing="8" content-padding="16">
  <m3e-carousel-item><img src="1.jpg" alt="…" /></m3e-carousel-item>
  <m3e-carousel-item href="/albums/2"><img src="2.jpg" alt="…" /></m3e-carousel-item>
  <m3e-carousel-item action label="Play the third"><img src="3.jpg" alt="…" /></m3e-carousel-item>
</m3e-carousel>
```

`<m3e-carousel>` renders a `.m3e-carousel` inside itself and moves each `<m3e-carousel-item>`'s
child nodes into an item's mask. `layout`: `multi-browse` (default), `uncontained`, `hero`,
`centered-hero` (Compose's keylines: items grow and shrink as they scroll and stay pinned
together) or `full-screen` (one item per screen, scrolling vertically). `item-width` (px) is the
preferred large item width (multi-browse, hero; hero without it fills the carousel but for the
small items) or the item width (uncontained). Items snap natively one at a time (the uncontained
layout does not snap); every item is a tab stop and the arrow keys, Home and End move between them,
scrolling the focused item into place. `href` items are links, `action` items buttons (activating one
dispatches `action` with `detail: { index }` from the item, bubbling through the carousel; the
carousel's `item-click` is deprecated). `label` names the carousel; items are named "n of N"
(`label` on an item, or `itemLabel`). `scrollToItem(index)`, `currentItem`; `ready` resolves once
the `carousel-layout.js` entry (`CarouselLayout`, imported on first render) runs. It is shared with
m3e-react's `<Carousel>`, which renders the same DOM.

## Pull to refresh

```html
<button type="button" aria-label="Trigger Refresh" id="refresh">…</button>
<m3e-pull-to-refresh id="feed">
  <ul>…</ul>
</m3e-pull-to-refresh>
<script type="module">
  const feed = document.getElementById('feed');
  feed.addEventListener('refresh', async () => {
    feed.refreshing = true;
    await load();
    feed.refreshing = false;
  });
  document.getElementById('refresh').addEventListener('click', () => feed.refresh());
</script>
```

`<m3e-pull-to-refresh>` renders a `.m3e-pull-to-refresh` inside itself (it fills its container's
height) and moves its child nodes into the scroll container, under Compose's pull indicator. A
touch or pen pull down at the top of the content brings the indicator down (half the drag, slowing
past the 80dp threshold); a release past the threshold fires `refresh`. Mouse drags and wheels never
pull: give keyboard and mouse users a visible Refresh button that calls `refresh()` (the same
event). `refreshing` (reflected) is the app's state: the indicator rests at the threshold and spins
meanwhile. `indicator="loading-indicator"` uses contained `<m3e-loading-indicator>`s, whose entry
it imports on first use; `disabled`, `threshold` (px), `indicator-label` (default "Refresh"),
`distanceFraction`. The `pull-to-refresh-layout.js` entry (`PullToRefreshLayout`) is shared with
m3e-react's `<PullToRefresh>`, which renders the same DOM.

## Time pickers

```html
<m3e-time-picker hour="9" minute="41" hour-cycle="12"></m3e-time-picker>
<m3e-time-input hour="21" minute="30" vibrant></m3e-time-input>
<m3e-time-scroll hour="6" minute="45" uncontained></m3e-time-scroll>
<script type="module">
  document.querySelector('m3e-time-picker').addEventListener('change', (e) => {
    console.log(e.detail.hour, e.detail.minute);
  });
</script>
```

Compose's `TimePicker` (the dial), `TimeInput` and `TimeScroll`. Each renders a `<div>` inside
itself (the host is `display: contents`) with the m3e-css contract. Attributes: `hour` (0–23),
`minute`, `hour-cycle="12|24"` (default: the locale's, from the nearest `lang`), `selection="hour|minute"`,
`vibrant`; the dial adds `layout="auto|vertical|horizontal"` (auto: horizontal in a landscape
window), the input and the wheels `uncontained` (a side column with AM, PM and a mode toggle that
fires `mode-toggle`). Property `labels` overrides the English strings. Events: `change`
(`detail: { hour, minute }`; the inputs' native `input` / `change` stop inside) and
`selection-change` (`detail: { value }`; its `selection` key is deprecated). The dial takes taps,
drags and arrow keys (Enter picks); the input fields and the wheels are spin buttons (Up / Down).
For a dialog, put a picker in a `.m3e-time-picker-dialog` surface inside
`<m3e-dialog variant="custom">`. The `time-picker-layout.js` entry (`TimePickerLayout`,
`TimeInputLayout`, `TimeScrollLayout`) is shared with m3e-react.

## Date pickers

```html
<m3e-date-picker value="2025-08-17"></m3e-date-picker>
<m3e-date-range-picker start="2025-08-10" end="2025-08-20"></m3e-date-range-picker>
<m3e-docked-date-picker value="2025-08-17" label="Date"></m3e-docked-date-picker>
<script type="module">
  document.querySelector('m3e-date-picker').addEventListener('change', (e) => {
    console.log(e.detail.value); // "2025-08-05", or null
  });
</script>
```

Compose's `DatePicker` (calendar, year grid, date input) and `DateRangePicker`, and
m3.material.io's docked date picker. Each renders a `<div>` inside itself (the host is
`display: contents`) and imports its layout entry on first render (`ready` resolves once it has
rendered); the input mode's `date-field` entry loads the first time it shows. Dates are ISO
(`YYYY-MM-DD`, UTC). Attributes: `value` (range: `start`, `end`), `displayed-month` (`YYYY-MM`),
`year-range="1900-2100"`, `display-mode="picker|input"`, `hide-mode-toggle`, `no-title`,
`no-headline`; docked: `value`, `label`, `year-range` and `show()` / `close()`. Properties
`selectableDates` (`{ isSelectableDate(utcMillis), isSelectableYear(year) }`) and `labels`.
Events: `change` (`detail: { value }`, range `{ start, end }`; the date fields' native `input` /
`change` stop inside), `display-mode-change`,
`displayed-month-change`. The first day of the week, names, digits and the input's pattern come
from `Intl` for the nearest `lang`; the input takes the pattern's digits and shows the delimiters
as they come (Compose's transformations). Show the range picker in `<m3e-dialog variant="full-screen">` and
the picker in `<m3e-dialog variant="custom">` around a `.m3e-date-picker-dialog` surface.

## Ripple for plain HTML

m3e-css draws hover, focus and pressed overlays without JS; the press ripple needs a little.
One import adds it to every plain-HTML button, icon button, chip (assist, filter, input, suggestion), FAB, extended FAB, FAB menu item, `.m3e-state-layer`,
interactive card (pressed through `.m3e-card__action`, drawn on the card), interactive list item, navigation item
(drawn on `.m3e-navigation-item__state`), navigation drawer item, tab, checkbox, radio button and
switch (pressed through the label or the input, drawn on the 40dp `__state` circle; a switch's
moves with its handle) in the document,
including ones added later:

```js
import '@kyralabs/m3e-elements/ripple.js';
```

It uses one set of delegated pointer and keyboard listeners on `document` and writes the same
contract as `attachRipple`: the first press on a host sets `data-ripple`, which stays, and each
press toggles `data-pressed` and writes `--_m3e-ripple-x/-y/-radius`. Hosts carrying a
`data-ripple` it did not set (m3e-react components and `attachRipple` hosts) are skipped, as are
disabled ones. Enter and Space press from the center (links: Enter only; checkboxes, filter
chips, radio buttons and switches: Space only, as they toggle or select). To scope it or stop it,
call `attachAutoRipple(root, signal)` from the package root instead; that import has no side
effect, and aborting the signal removes the attributes and variables it wrote.

## Canonical layouts

```js
import '@kyralabs/m3e-elements/list-detail-layout.js'; // or supporting-pane-layout.js
```

```html
<m3e-list-detail-layout list-label="Inbox" detail-label="Message" drag-handle style="block-size: 100%">
  <div slot="list">
    <button data-pane-navigate="detail" data-content-key="42">Brunch this weekend?</button>
  </div>
  <div slot="detail">
    <button data-pane-navigate="back" aria-label="Back">…</button>
    …
  </div>
  <div slot="extra">…</div>
</m3e-list-detail-layout>
```

`<m3e-list-detail-layout>` and `<m3e-supporting-pane-layout>` (Compose `ListDetailPaneScaffold` /
`SupportingPaneScaffold` with their navigators) render the `.m3e-layout > .m3e-pane-scaffold`
contract (load `layout.css`) and size themselves by their own width: one pane below 840px, two
from 840px, three (with an extra pane) from 1600px (m3.material.io) — `pane-rule="compose"`
shows three from 1200px (Compose's `calculatePaneScaffoldDirective`). `navigateTo(pane, contentKey?)` (`list` / `detail` / `extra`, `main` / `supporting` /
`extra`), `navigateBack(behavior?)`, `canNavigateBack()` and the `navigator` property (an m3e-motion
`ThreePaneScaffoldNavigator`) drive them; a click on `[data-pane-navigate]` does too, and
`[data-pane-navigate="back"]` hides while there is nothing to go back to. Panes move on Compose's
pane motion, focus follows the destination, and `drag-handle` adds the pane expansion handle.
Event: `scaffold-value-change`. The behavior is the `pane-scaffold-layout.js` entry
(`PaneScaffoldLayout`, also used by m3e-react); the elements load the `pane-motion.js` and
`pane-expansion.js` entries lazily.

Apache-2.0; see `LICENSE` and `NOTICE`.
