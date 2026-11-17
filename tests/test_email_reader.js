/* Run with: node --test tests/test_email_reader.js */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');

function reader() {
    const callbacks = [], observers = [], listeners = {};
    const body = {
        style: {setProperty() {}}, scrollHeight: 980,
        getBoundingClientRect: () => ({height: 40}),
        addEventListener: (name, callback) => {listeners[name] = callback;},
    };
    const frame = {isConnected: true, style: {}, contentDocument: {body, documentElement: {style: body.style}}};
    const context = {
        requestAnimationFrame: callback => callbacks.push(callback),
        ResizeObserver: class {
            constructor(callback) { this.callback = callback; observers.push(this); }
            observe() {}
            disconnect() { this.disconnected = true; }
        },
    };
    const source = readFileSync('static/js/components.js', 'utf8');
    vm.runInNewContext(source.slice(source.indexOf('const frameObservers ='), source.indexOf('let tooltipModule;')) +
        '\nthis.watchEmailSize = watchEmailSize;', context);
    context.watchEmailSize(frame);
    const flush = () => { while (callbacks.length) callbacks.shift()(); };
    return {frame, body, observers, listeners, flush, watch: context.watchEmailSize};
}

test('visible overflow fits even when the body box is short', () => {
    const {frame, body, observers, flush} = reader();
    assert.equal(frame.style.height, '982px');
    body.scrollHeight = 1200; // narrower reader causes wrapping
    observers[0].callback(); flush();
    assert.equal(frame.style.height, '1202px');
    body.scrollHeight = 20; // a short message can shrink again
    observers[0].callback(); flush();
    assert.equal(frame.style.height, '64px');
});

test('delayed images resize overflow that does not change the body box', () => {
    const {frame, body, listeners, flush} = reader();
    body.scrollHeight = 1500;
    listeners.load(); flush();
    assert.equal(frame.style.height, '1502px');
    body.scrollHeight = 980;
    listeners.error(); flush();
    assert.equal(frame.style.height, '982px');
});

test('old documents and removed readers cannot apply queued sizes', () => {
    const {frame, body, observers, listeners, flush, watch} = reader();
    body.scrollHeight = 2000;
    listeners.load();
    frame.contentDocument = {body: {...body, scrollHeight: 80}, documentElement: {style: body.style}};
    watch(frame); flush();
    assert.equal(observers[0].disconnected, true);
    assert.equal(frame.style.height, '82px');
    frame.isConnected = false;
    frame.contentDocument.body.scrollHeight = 5000;
    observers[1].callback(); flush();
    assert.equal(frame.style.height, '82px');
    watch(frame);
    assert.equal(observers[1].disconnected, true);
});
