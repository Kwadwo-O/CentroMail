/* Run with: node --test tests/test_preferences.js */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const groups = JSON.parse(readFileSync('static/preferences.json', 'utf8'));

function preferences(saved = {}) {
    const storage = new Map(Object.entries(saved));
    const root = {dataset: {}, style: {setProperty() {}, removeProperty() {}}, classList: {toggle() {}}};
    const listeners = {};
    const context = {
        window: {CentroMailPreferenceGroups: groups, addEventListener() {}},
        document: {documentElement: root, querySelector: () => null, querySelectorAll: () => [], head: {append() {}},
            addEventListener: (type, fn) => {listeners[type] = fn;}, dispatchEvent() {}, createElement: () => ({dataset: {}})},
        localStorage: {getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key)},
        matchMedia: () => ({matches: true, addEventListener() {}}), Event: class {}, confirm: () => false,
        getComputedStyle: () => ({getPropertyValue: () => '800'}),
    };
    vm.runInNewContext(readFileSync('static/js/appearance.js', 'utf8'), context);
    return {appearance: context.window.CentroMailAppearance, root, storage, listeners};
}

test('corrupt saved preferences fall back to usable defaults', () => {
    const {appearance, root} = preferences({'centromail-theme': 'broken', 'centromail-accent': 'javascript:bad', 'centromail-text-scale': '999', 'centromail-confirm-actions': 'no'});
    assert.equal(root.dataset.theme, 'dark'); // device theme
    assert.equal(appearance.get('accent'), '#50745c');
    assert.equal(appearance.get('text-scale'), '1');
    assert.equal(appearance.get('confirm-actions'), 'true');
    assert.throws(() => appearance.set('text-scale', '999'));
    assert.throws(() => appearance.set('unknown-setting', 'true'));
});

test('group resets preserve other preferences and unrelated browser data', () => {
    const {appearance, storage, root} = preferences({'centromail-theme': 'light', 'centromail-auto-refresh': 'false', 'other-app': 'retained'});
    appearance.set('text-scale', '1.2');
    appearance.reset(groups.find(g => g.key === 'typography').settings.map(s => s.key));
    assert.equal(appearance.get('text-scale'), '1');
    assert.equal(appearance.get('auto-refresh'), 'false');
    assert.equal(root.dataset.theme, 'light');
    assert.equal(storage.get('other-app'), 'retained');
});

test('old reply-first preferences default to chronological sorting and direction is saved', () => {
    for (const old of ['replyable','noreply']) {
        const {appearance,storage} = preferences({'centromail-mail-sort':old});
        assert.equal(appearance.get('mail-sort'),'newest');
        assert.equal(appearance.get('mail-sort-direction'),'desc');
        appearance.set('mail-sort-direction','asc');
        assert.equal(storage.get('centromail-mail-sort-direction'),'asc');
    }
});

test('confirmation preference controls shared destructive form submission', () => {
    const {appearance, listeners} = preferences();
    let cancelled = false;
    const event = {target: {closest: () => ({dataset: {confirm: 'Delete?'}})}, preventDefault: () => {cancelled = true;}};
    listeners.submit(event);
    assert.equal(cancelled, true);
    cancelled = false;
    appearance.set('confirm-actions', 'false');
    listeners.submit(event);
    assert.equal(cancelled, false);
});

test('animation choices persist, validate and reset together without changing inbox preferences', () => {
    const {appearance, root, storage} = preferences();
    const keys = groups.find(group => group.key === 'motion').settings.map(item => item.key);
    for (const key of keys.filter(key => key.endsWith('-motion') && key !== 'reduce-motion')) {
        appearance.set(key, 'false');
        assert.equal(storage.get('centromail-' + key), 'false');
        assert.equal(appearance.get(key), 'false');
    }
    appearance.set('motion-speed', '1.4'); appearance.set('motion-intensity', '1.5');
    assert.equal(root.dataset.cmMotionIntensity, '1.5');
    assert.throws(() => appearance.set('motion-intensity', '10'));
    appearance.set('reading-pane', 'page');
    appearance.reset(keys);
    assert.equal(appearance.get('motion-intensity'), '1');
    assert.equal(appearance.get('copy-motion'), 'true');
    assert.equal(appearance.get('reading-pane'), 'page');
});

test('navigation choices validate, persist and reset as one group', () => {
    const {appearance, root, storage} = preferences({'centromail-navigation-style':'unknown', 'centromail-reading-pane':'page'});
    assert.equal(appearance.get('navigation-style'), 'current');
    const navigation = groups.find(group => group.key === 'navigation');
    for (const item of navigation.settings) {
        for (const choice of item.choices) {
            appearance.set(item.key, choice.value);
            assert.equal(storage.get('centromail-' + item.key), choice.value);
        }
        assert.throws(() => appearance.set(item.key, 'invalid'));
    }
    appearance.set('navigation-style', 'adaptive');
    appearance.set('navigation-side', 'right');
    assert.equal(root.dataset.cmNavigationStyle, 'adaptive');
    assert.equal(root.dataset.cmNavigationSide, 'right');
    appearance.reset(navigation.settings.map(item => item.key));
    assert.equal(appearance.get('navigation-style'), 'current');
    assert.equal(appearance.get('navigation-side'), 'left');
    assert.equal(appearance.get('reading-pane'), 'page');
});
