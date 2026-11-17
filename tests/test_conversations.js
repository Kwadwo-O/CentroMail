/* Run with: node --test tests/test_conversations.js */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');

function conversations({scrollTop = 0, failEmail = false} = {}) {
    const listeners = {}, requests = [], scroller = {scrollTop};
    const element = () => ({children: [], dataset: {}, setAttribute() {}, removeAttribute() {}, remove() {},
        append(child) { this.children.push(child); }});
    const first = {open: false, isConnected: true, dataset: {conversationMessageUrl: '/first'},
        body: {...element(), replaceChildren(fragment) { this.fragment = fragment; }},
        querySelector() { return this.body; }};
    const selected = {...first, open: true, dataset: {}};
    let inserted = false;
    const current = {getBoundingClientRect: () => ({top: inserted ? 200 : 0})};
    const section = {isConnected: true, dataset: {conversationUrl: '/conversation'},
        querySelector: selector => selector === '.reader-message' ? current : null,
        querySelectorAll: () => [first, selected], closest: () => scroller, prepend() {},
        replaceChildren() { inserted = true; }};
    const document = {
        body: {append() {}}, createElement: element,
        querySelectorAll: selector => selector === '[data-conversation-url]' ? [section] : [],
        createRange: () => ({createContextualFragment: html => ({html,
            querySelector: () => ({replaceWith(value) { assert.equal(value, current); }})})}),
        addEventListener(name, callback) { (listeners[name] ||= []).push(callback); },
    };
    const context = {document, WeakSet, URLSearchParams, AbortSignal, setTimeout,
        location: {assign() {}}, window: {scrollY: 0},
        MutationObserver: class {observe() {}},
        fetch: async url => {
            requests.push(url);
            if (url === '/conversation') return {ok: true, json: async () => ({html: 'thread'})};
            return {ok: !failEmail, text: async () => 'Earlier email body'};
        },
    };
    vm.runInNewContext(readFileSync('static/js/email-tools.js', 'utf8'), context);
    const settled = () => new Promise(resolve => setImmediate(resolve));
    const display = async expanded => {
        const control = {hasAttribute: name => name === 'data-expand-conversation' && expanded,
            closest: () => section};
        const target = {closest: selector => selector === '[data-expand-conversation], [data-collapse-conversation]' ? control : null};
        for (const callback of listeners.click) callback({target});
        await settled();
    };
    const toggle = async details => {
        details.matches = selector => selector === '[data-conversation-message]';
        for (const callback of listeners.toggle) callback({target: details});
        await settled();
    };
    return {first, selected, requests, scroller, display, toggle, settled};
}

test('opening a thread reveals its heading but keeps an existing scroll position', async () => {
    const initial = conversations();
    await initial.settled();
    assert.equal(initial.scroller.scrollTop, 0);
    const reading = conversations({scrollTop: 75});
    await reading.settled();
    assert.equal(reading.scroller.scrollTop, 275);
});

test('expand all loads earlier bodies once and collapse all includes the selected email', async () => {
    const view = conversations();
    await view.settled();
    await view.display(true);
    await view.toggle(view.first);
    await view.toggle(view.selected);
    assert.equal(view.first.open, true);
    assert.equal(view.selected.open, true);
    assert.equal(view.first.body.fragment.html, 'Earlier email body');
    assert.deepEqual(view.requests, ['/conversation', '/first']);
    await view.display(false);
    assert.equal(view.first.open, false);
    assert.equal(view.selected.open, false);
    await view.display(true);
    assert.deepEqual(view.requests, ['/conversation', '/first']);
});

test('a failed earlier email displays a retry control and can be loaded again', async () => {
    const view = conversations({failEmail: true});
    await view.settled();
    await view.display(true);
    assert.equal(view.first.body.textContent, 'Email could not be loaded. ');
    assert.equal(view.first.body.children[0].dataset.retryConversationMessage, '');
    await view.display(false);
    await view.display(true);
    assert.deepEqual(view.requests, ['/conversation', '/first', '/first']);
});

test('opening an email only marks the matching account row as read', async () => {
    const article = {dataset: {markEmailRead: 'true', readUrl: '/read', readAccount: 'gmail',
        readFolder: 'inbox', readMessageId: 'same-id', readCsrf: 'fixture'}, closest: () => null};
    const rows = ['gmail', 'email:gmail:second'].map(account => ({
        dataset: {messageId: 'same-id', mailAccount: account}, read: false,
        classList: {remove() { rows.find(row => row.dataset.mailAccount === account).read = true; }},
        querySelector: () => ({textContent: 'Unread'}),
    }));
    const document = {
        body: {append() {}}, createElement: () => ({setAttribute() {}}),
        querySelectorAll: selector => selector === '[data-mark-email-read="true"]' ? [article] : selector === '.message' ? rows : [],
        addEventListener() {}, dispatchEvent() {},
    };
    vm.runInNewContext(readFileSync('static/js/email-tools.js', 'utf8'), {
        document, WeakSet, URLSearchParams, CustomEvent: class {},
        MutationObserver: class {observe() {}}, fetch: async () => ({ok: true}),
    });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(rows[0].read, true);
    assert.equal(rows[1].read, false);
});
