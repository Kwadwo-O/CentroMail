/* Run with: node --test --test-isolation=none tests/test_motion.js */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');

async function motion(preferences = {}) {
    const listeners = {}, observers = [], calls = [];
    class Element {
        constructor(selector = '') {
            this.selectors = new Set(selector.split(',').map(s => s.trim()));
            this.children = []; this.isConnected = true; this.hidden = false; this.nodeType = 1;
            this.classes = new Set(); this.classList = {contains: key => this.classes.has(key)};
            this.width = 600; this.attributes = {};
        }
        matches(selectors) { return selectors.split(',').some(s => this.selectors.has(s.trim()) || (s.trim() === '[hidden]' && this.hidden)); }
        closest(selectors) { return this.matches(selectors) ? this : this.parent?.closest(selectors) || null; }
        append(child) { this.children.push(child); child.parent = this; return child; }
        querySelectorAll(selectors) { return this.children.flatMap(child => [...(child.matches(selectors) ? [child] : []), ...child.querySelectorAll(selectors)]); }
        querySelector(selectors) { return this.querySelectorAll(selectors)[0] || null; }
        getClientRects() { return this.hidden ? [] : [{}]; }
        getBoundingClientRect() { return {width: this.width}; }
        getAttribute(name) { return this.attributes[name] || null; }
        animate(frames, options) {
            const animation = {cancelled: false, cancel() {this.cancelled = true; this.oncancel?.();}};
            calls.push({element: this, frames, options, animation}); return animation;
        }
    }
    const root = new Element(); root.dataset = preferences;
    const body = new Element('body');
    const device = {matches: false, addEventListener: (name, fn) => {device.changed = fn;}};
    const io = {targets: new Set(), fire(elements) {this.callback(elements.map(target => ({target, isIntersecting: true})));}};
    const queries = new Map();
    const document = {documentElement: root, body, hidden: false, readyState: 'complete', fonts: {ready: Promise.resolve()},
        querySelector: selector => queries.get(selector) || body.querySelector(selector),
        querySelectorAll: selectors => selectors.split(',').flatMap(selector => queries.has(selector.trim()) ? [queries.get(selector.trim())] : body.querySelectorAll(selector)),
        getElementById: id => queries.get('#' + id),
        addEventListener: (name, fn) => {(listeners[name] ||= []).push(fn);}};
    const context = {Element, Node: {ELEMENT_NODE: 1}, document, window: {addEventListener() {}}, matchMedia: () => device,
        performance: {now: () => 1000}, setTimeout() {}, getComputedStyle: () => ({marginRight: '16px', borderTopWidth: '1px', backgroundColor: 'white',
            borderRadius: '24px', boxShadow: 'none', getPropertyValue: name => name.endsWith('-duration') ? '420ms' : name.endsWith('-easing') ? 'linear(0, 1)' : ''}),
        IntersectionObserver: class {constructor(callback) {io.callback = callback;} observe(el) {io.targets.add(el);} unobserve(el) {io.targets.delete(el);}},
        MutationObserver: class {constructor(callback) {this.callback = callback; observers.push(this);} observe(target) {this.target = target;}}};
    vm.runInNewContext(readFileSync('static/js/motion.js', 'utf8'), context);
    await new Promise(resolve => setImmediate(resolve));
    const event = (name, detail = {}) => listeners[name]?.forEach(fn => fn(detail));
    const mutations = records => observers.find(observer => observer.target === body).callback(records);
    return {api: context.window.CentroMailMotion, root, body, document, device, calls, Element, queries, io, event, mutations};
}

test('families switch independently and respect shared speed and intensity', async () => {
    const m = await motion({cmCopyMotion: 'false', cmSendMotion: 'true', cmMotionSpeed: '1.4', cmMotionIntensity: '1.5'});
    const button = new m.Element(), icon = button.append(new m.Element('.m3e-icon'));
    m.api.feedback(button, 'copy');
    assert.equal(m.calls.length, 0);
    m.api.feedback(button, 'send');
    assert.equal(m.calls.length, 1);
    assert.equal(m.calls[0].element, icon);
    assert.equal(m.calls[0].options.duration, 588);
    assert.equal(m.calls[0].options.easing, 'linear(0, 1)', 'uses the installed M3E spring curve');
    assert.equal(m.calls[0].frames[1].translate, '15px -9px');
    m.root.dataset.cmMotionStyle = 'standard';
    m.api.feedback(button, 'send');
    assert.equal(m.calls[1].frames[1].translate, '7.5px -4.5px');
    assert.equal(m.calls[0].animation.cancelled, true, 'repeated actions replace the previous animation');
});

test('preferences, device reduced motion and hidden tabs stop active effects', async () => {
    const m = await motion();
    const button = new m.Element();
    m.api.feedback(button, 'copy');
    m.event('centromail-appearance-change');
    assert.equal(m.calls[0].animation.cancelled, true);
    m.api.feedback(button, 'copy');
    m.device.matches = true; m.device.changed();
    assert.equal(m.calls[1].animation.cancelled, true);
    m.api.feedback(button, 'copy');
    assert.equal(m.calls.length, 2);
    m.device.matches = false; m.api.feedback(button, 'copy');
    m.document.hidden = true; m.event('visibilitychange');
    assert.equal(m.calls[2].animation.cancelled, true);
    m.api.feedback(button, 'send');
    assert.equal(m.calls.length, 3);
    m.document.hidden = false; m.root.classes.add('reduce-motion');
    assert.equal(m.api.enabled(), false);
});

test('new rows animate once, section entrances remain independently disabled, and stagger is bounded', async () => {
    const m = await motion({cmEntranceMotion: 'false', cmListMotion: 'true'});
    const rows = Array.from({length: 20}, () => m.body.append(new m.Element('.message')));
    const section = m.body.append(new m.Element('.dashboard-panel'));
    m.mutations([{type:'childList', target:m.body, addedNodes:[...rows, section]}]);
    m.io.fire([...rows, section]);
    assert.equal(m.calls.length, 20);
    assert.equal(Math.max(...m.calls.map(call => call.options.delay)), 150);
    m.mutations([{type:'childList', target:m.body, addedNodes:rows}]);
    m.io.fire(rows);
    assert.equal(m.calls.length, 20, 'cached rows do not replay on every refresh');
});

test('reader updates happen with motion disabled and opening or closing never transforms Reply ancestors', async () => {
    const m = await motion({cmReaderMotion: 'false'});
    const inbox = new m.Element(), reader = new m.Element(); reader.hidden = true;
    m.queries.set('.gmail-app .inbox', inbox); m.queries.set('#mail-reader', reader);
    let updates = 0;
    m.api.readerLayout(() => {updates++; reader.hidden = false; inbox.width = 300;});
    assert.equal(updates, 1); assert.equal(m.calls.length, 0);
    m.root.dataset.cmReaderMotion = 'true';
    m.api.readerLayout(() => {updates++; reader.hidden = true; inbox.width = 600;});
    assert.equal(m.calls.length, 1, 'closing animates the remaining inbox width');
    m.api.readerLayout(() => {updates++; reader.hidden = false; inbox.width = 300;});
    assert.equal(updates, 3); assert.equal(m.calls.length, 3);
    for (const {frames} of m.calls) for (const frame of frames) {
        assert.equal(frame.transform, undefined); assert.equal(frame.translate, undefined); assert.equal(frame.scale, undefined);
    }
    assert.equal(m.calls[0].animation.cancelled, true, 'reopening cancels the previous layout animation');
});

test('media only reveals after loading and disables independently from notifications', async () => {
    const m = await motion({cmMediaMotion: 'false'});
    const photo = new m.Element('.telegram-message-media img');
    m.event('load', {target: photo}); assert.equal(m.calls.length, 0);
    m.root.dataset.cmMediaMotion = 'true';
    m.event('load', {target: photo}); m.event('load', {target: photo});
    assert.equal(m.calls.length, 1);
    photo.isConnected = false;
    m.mutations([]);
    assert.equal(m.calls[0].animation.cancelled, true);
});

test('each preview uses its family switch, including disabled copy feedback', async () => {
    const m = await motion({cmCopyMotion: 'false'});
    const preview = new m.Element();
    for (const sample of ['view', 'panel', 'copy', 'send', 'row']) {
        const element = preview.append(new m.Element(`[data-motion-sample="${sample}"]`));
        element.append(new m.Element('.m3e-icon, .motion-preview-avatar'));
    }
    preview.append(new m.Element('#motion-preview-status'));
    m.api.preview(preview, 'copy'); assert.equal(m.calls.length, 0);
    for (const family of ['entrance', 'list', 'navigation', 'panel', 'reader', 'expand', 'selection', 'send', 'notification', 'focus', 'control', 'theme', 'drag', 'media', 'loading', 'hover', 'press']) {
        const before = m.calls.length;
        m.api.preview(preview, family);
        assert.ok(m.calls.length > before, family);
        m.root.dataset[`cm${family[0].toUpperCase()}${family.slice(1)}Motion`] = 'false';
        const after = m.calls.length;
        m.api.preview(preview, family); assert.equal(m.calls.length, after, family + ' disabled');
    }
});
