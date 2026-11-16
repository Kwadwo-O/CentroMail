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
