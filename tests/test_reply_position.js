const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');

function page(saved, navigation = {}) {
    const listeners = {}, windowEvents = {}, stored = new Map(saved ? [['centromail-reply-position', saved]] : []);
    const classes = new Set(), styles = {}, timers = [];
    let observer, reset, captured;
    const wrapper = {
        classList: {add: value => classes.add(value), remove: value => classes.delete(value)},
        style: Object.assign(styles, {removeProperty: key => delete styles[key]}),
        append: control => { reset = control; },
        querySelector: selector => selector === '[data-email-reply]' ? button : reset,
        getBoundingClientRect: () => ({left: parseFloat(styles.left) || 500, top: parseFloat(styles.top) || 250,
            width: classes.has('is-positioned') ? 156 : 104, height: 52}),
    };
    const button = {
        dataset: {}, disabled: false, classList: {add() {}, remove() {}},
        setAttribute(name, value) { this[name] = value; },
        removeAttribute(name) { if (name === 'data-reply-movable') delete this.dataset.replyMovable; },
        closest(selector) {
            if (selector === '.reply-button-wrap') return wrapper;
            if (selector === '[data-email-reply]') return this;
            if (selector === '[data-reply-movable]' && 'replyMovable' in this.dataset) return this;
            return null;
        },
        setPointerCapture: id => { captured = id; },
        hasPointerCapture: id => captured === id,
        releasePointerCapture: () => { captured = null; }, focus() {},
    };
    const context = {innerWidth: 1000, innerHeight: 800,
        getComputedStyle: () => ({getPropertyValue: name => navigation[name] || '0px'}),
        document: {documentElement: {}, body: {append() {}}, querySelectorAll: () => [button],
            createElement: () => ({dataset: {}, setAttribute() {}, append() {}}),
            addEventListener(name, callback) { (listeners[name] ??= []).push(callback); }},
        localStorage: {getItem: key => stored.get(key) || null,
            setItem: (key, value) => stored.set(key, value), removeItem: key => stored.delete(key)},
        window: {addEventListener: (name, callback) => { windowEvents[name] = callback; }},
        MutationObserver: class {constructor(callback) { observer = callback; } observe() {}},
        setTimeout: callback => timers.push(callback),
    };
    vm.runInNewContext(readFileSync('static/js/reply-position.js', 'utf8'), context);
    const event = (name, values = {}) => {
        const data = {target: button, pointerId: 1, button: 0, isPrimary: true, clientX: 550, clientY: 270,
            preventDefault() { this.prevented = true; }, stopPropagation() {},
            stopImmediatePropagation() { this.stopped = true; }, ...values};
        for (const callback of listeners[name] || []) callback(data);
        return data;
    };
    return {context, button, wrapper, event, stored, classes, windowEvents,
        sync: () => observer(), flush: () => timers.splice(0).forEach(callback => callback())};
}

test('click still replies, while a drag saves the position and suppresses its generated click', () => {
    const p = page();
    p.event('pointerdown'); p.event('pointerup');
    assert.equal(p.event('click').prevented, undefined);
    assert.equal(p.stored.size, 0);
    p.event('pointerdown');
    p.event('pointermove', {clientX: 552, clientY: 271});
    assert.equal(p.classes.has('is-positioned'), false);
    p.event('pointermove', {clientX: 350, clientY: 420}); p.event('pointerup');
    assert.deepEqual(JSON.parse(p.stored.get('centromail-reply-position')), {x: 300, y: 400});
    assert.equal(p.event('click').stopped, true);
    p.flush();
    assert.equal(p.event('click').prevented, undefined);
});

test('saved and keyboard positions stay in the viewport and Alt+Home restores the normal button', () => {
    const p = page(JSON.stringify({x: 950, y: 790}));
    assert.equal(p.wrapper.style.left, '836px');
    assert.equal(p.wrapper.style.top, '740px');
    assert.equal(p.event('keydown', {altKey: true, key: 'ArrowLeft'}).prevented, true);
    assert.equal(p.wrapper.style.left, '820px');
    p.context.innerWidth = 400; p.context.innerHeight = 300; p.windowEvents.resize();
    assert.deepEqual(JSON.parse(p.stored.get('centromail-reply-position')), {x: 236, y: 240});
    p.event('keydown', {altKey: true, key: 'Home'});
    assert.equal(p.classes.has('is-positioned'), false);
    assert.equal(p.stored.size, 0);
});

test('disabled replies keep their position unavailable and invalid saved coordinates are ignored', () => {
    const p = page(JSON.stringify({x: 'wrong', y: null}));
    assert.equal(p.classes.has('is-positioned'), false);
    p.button.disabled = true; p.sync();
    assert.equal('replyMovable' in p.button.dataset, false);
    p.event('pointerdown'); p.event('pointermove', {clientX: 300}); p.event('pointerup');
    assert.equal(p.stored.has('centromail-reply-position'), true); // invalid preference is never applied
    assert.equal(p.classes.has('is-positioned'), false);
});

test('movable Reply stays clear of navigation and adapts when its location changes', () => {
    const navigation = {'--cm-nav-right':'240px', '--cm-nav-bottom':'80px'};
    const p = page(JSON.stringify({x:950, y:790}), navigation);
    assert.equal(p.wrapper.style.left, '596px');
    assert.equal(p.wrapper.style.top, '660px');
    navigation['--cm-nav-right'] = '0px';
    navigation['--cm-nav-left'] = '240px';
    navigation['--cm-nav-top'] = '80px';
    p.event('keydown', {altKey:true, shiftKey:true, key:'ArrowLeft'});
    p.event('pointerdown');
    p.event('pointermove', {clientX:0, clientY:0});
    p.event('centromail-navigation-change');
    assert.equal(p.wrapper.style.left, '248px');
    assert.equal(p.wrapper.style.top, '390px');
});
