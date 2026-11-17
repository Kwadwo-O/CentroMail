/* Run with: node --test tests/test_reader_resize.js */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const source = readFileSync('static/js/mail.js', 'utf8');

function classes() {
    const values = new Set();
    return {add: value => values.add(value), remove: value => values.delete(value),
        contains: value => values.has(value), toggle(value, enabled) { enabled ? values.add(value) : values.delete(value); }};
}

function readingPane({width = 640, height = 500, space = 1100, viewport = 1440, stored = null} = {}) {
    const listeners = {}, windowListeners = {}, attributes = new Map(), capture = new Set();
    let resizeCallback;
    const storage = new Map(stored === null ? [] : [['centromail-reader-width-custom', String(stored)]]);
    const resizer = {hidden: true, classList: classes(), style: {},
        addEventListener(type, callback) { listeners[type] = callback; },
        setAttribute(name, value) { attributes.set(name, value); }, getAttribute: name => attributes.get(name),
        setPointerCapture: id => capture.add(id), hasPointerCapture: id => capture.has(id),
        releasePointerCapture(id) { capture.delete(id); listeners.lostpointercapture?.({pointerId: id}); },
    };
    const reader = {hidden: false, getBoundingClientRect: () => ({width: reader.hidden ? 0 : width,
        height: reader.hidden ? 0 : height,
        right: context.innerWidth - 16, left: context.innerWidth - 16 - width})};
    const inbox = {getBoundingClientRect: () => ({width: reader.hidden ? space : space - width})};
    const body = {classList: classes()};
    const context = {
        app: {classList: classes(), style: {setProperty(name, value) { assert.equal(name, '--cm-reader-width'); width = parseFloat(value); }}},
        document: {body, querySelector: selector => ({'#reader-resizer': resizer, '#inbox': inbox})[selector]},
        window: {addEventListener: (type, callback) => { windowListeners[type] = callback; }},
        reader, desktop: {matches: true}, innerWidth: viewport,
        ResizeObserver: class {
            constructor(callback) { resizeCallback = callback; }
            observe(element) { assert.equal(element, reader); }
        },
        localStorage: {getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value)},
    };
    const start = source.indexOf('// Resizable reading pane');
    const end = source.indexOf('const closeReader =', start);
    vm.runInNewContext(source.slice(start, end) +
        'this.syncResizer = syncResizer; this.setReaderOpen = setReaderOpen;', context);
    context.syncResizer();
    const emit = (type, fields = {}) => {
        let prevented = false;
        const event = {button: 0, pointerId: 1, clientX: 800, preventDefault() { prevented = true; }, ...fields};
        if (type === 'lostpointercapture') capture.delete(event.pointerId);
        listeners[type]?.(event);
        return prevented;
    };
    return {context, reader, resizer, capture, body, attributes, storage, emit,
        width: () => width, saved: () => storage.get('centromail-reader-width-custom'),
        resizeReader(nextHeight) { height = nextHeight; resizeCallback(); },
        resize(nextSpace, nextViewport = context.innerWidth) { space = nextSpace; context.innerWidth = nextViewport; windowListeners.resize(); }};
}

test('divider matches reading pane height as content changes and the pane reopens', () => {
    const view = readingPane({height: 360});
    assert.equal(view.resizer.style.height, '360px');
    view.resizeReader(620);
    assert.equal(view.resizer.style.height, '620px');
    view.context.setReaderOpen(false);
    view.resizeReader(0);
    assert.equal(view.resizer.hidden, true);
    view.resizeReader(480);
    view.context.setReaderOpen(true);
    assert.equal(view.resizer.hidden, false);
    assert.equal(view.resizer.style.height, '480px');
});

test('drag starts without a jump and follows pointer distance in both directions', () => {
    const view = readingPane();
    assert.equal(view.emit('pointerdown'), true);
    view.emit('pointermove');
    assert.equal(view.width(), 640);
    view.emit('pointermove', {clientX: 740});
    assert.equal(view.width(), 700);
    view.emit('pointermove', {clientX: 740});
    assert.equal(view.width(), 700);
    view.emit('pointermove', {clientX: 860});
    assert.equal(view.width(), 580);
    view.emit('pointerup');
    assert.equal(view.saved(), '580');
    assert.equal(view.attributes.get('aria-valuenow'), '580');
    assert.equal(view.capture.size, 0);
});

test('drag limits reserve usable inbox space and keep the saved width within bounds', () => {
    const view = readingPane();
    assert.equal(view.attributes.get('aria-valuemin'), '320');
    assert.equal(view.attributes.get('aria-valuemax'), '820');
    view.emit('pointerdown');
    view.emit('pointermove', {clientX: -5000});
    assert.equal(view.width(), 820);
    view.emit('pointermove', {clientX: 5000});
    assert.equal(view.width(), 320);
    view.emit('pointerup');
    assert.equal(view.saved(), '320');
});

test('keyboard arrows, larger steps, Home and End resize and persist the reader', () => {
    const view = readingPane();
    assert.equal(view.emit('keydown', {key: 'ArrowLeft'}), true);
    assert.equal(view.width(), 665);
    view.emit('keydown', {key: 'ArrowRight'});
    assert.equal(view.width(), 640);
    view.emit('keydown', {key: 'ArrowLeft', shiftKey: true});
    assert.equal(view.width(), 740);
    view.emit('keydown', {key: 'Home'});
    assert.equal(view.width(), 320);
    view.emit('keydown', {key: 'End'});
    assert.equal(view.width(), 820);
    assert.equal(view.saved(), '820');
    assert.equal(view.emit('keydown', {key: 'Tab'}), false);
});

test('saved widths and viewport changes obey the available layout and cancel an active drag', () => {
    const view = readingPane({stored: 780});
    assert.equal(view.width(), 780);
    view.emit('pointerdown');
    view.resize(850, 1200);
    assert.equal(view.width(), 570);
    assert.equal(view.saved(), '570');
    assert.equal(view.attributes.get('aria-valuenow'), '570');
    assert.equal(view.attributes.get('aria-valuemax'), '570');
    assert.equal(view.capture.size, 0);
    assert.equal(view.body.classList.contains('is-resizing-reader'), false);
    view.emit('pointermove', {clientX: 0});
    assert.equal(view.width(), 570);
});

test('closing, cancellation and lost capture clean up resizing state', () => {
    for (const finish of ['pointerup', 'pointercancel', 'lostpointercapture', 'close']) {
        const view = readingPane();
        view.emit('pointerdown');
        view.emit('pointermove', {clientX: 750});
        if (finish === 'close') view.context.setReaderOpen(false);
        else view.emit(finish);
        assert.equal(view.saved(), '690');
        assert.equal(view.capture.size, 0);
        assert.equal(view.resizer.classList.contains('is-dragging'), false);
        assert.equal(view.body.classList.contains('is-resizing-reader'), false);
        if (finish === 'close') assert.equal(view.resizer.hidden, true);
    }
});

test('secondary clicks and unavailable reading panes cannot start a drag', () => {
    const view = readingPane();
    assert.equal(view.emit('pointerdown', {button: 2}), false);
    view.reader.hidden = true;
    assert.equal(view.emit('pointerdown'), false);
    view.reader.hidden = false;
    view.context.desktop.matches = false;
    assert.equal(view.emit('pointerdown'), false);
    assert.equal(view.capture.size, 0);
    assert.equal(view.width(), 640);
});
