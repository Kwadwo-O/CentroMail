const assert = require('node:assert/strict');
const {test} = require('node:test');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');

class Control {
    constructor(dataset = {}) {
        this.dataset = dataset; this.attributes = new Map(); this.events = {}; this.hidden = false;
        this.value = ''; this.classList = {toggle() {}};
    }
    addEventListener(name, handler) { this.events[name] = handler; }
    setAttribute(name, value) { this.attributes.set(name, value); }
    getAttribute(name) { return this.attributes.get(name); }
    removeAttribute(name) { this.attributes.delete(name); }
    focus() { this.focused = true; }
    closest() { return null; }
    fire(name, event = {}) { return this.events[name]?.(event); }
}
function fixture(initialApp = '') {
    const page = new Control({openIntegration:initialApp}), search = new Control(), connected = new Control();
    connected.setAttribute('aria-pressed', 'false');
    const categories = ['all', 'email', 'messages', 'social'].map(key => new Control({integrationCategory:key}));
    const cards = [new Control({integrationApp:'gmail', search:'gmail email', category:'email', connected:'true'}),
        new Control({integrationApp:'telegram', search:'telegram messages', category:'messages', connected:'true'}),
        new Control({integrationApp:'tiktok', search:'tiktok profile', category:'social', connected:'false'})];
    const reset = new Control(), empty = new Control(), results = new Control(), opener = new Control({integrationOpen:'telegram'});
    const refresh = new Control({url:'/integrations'}), refreshButton = new Control(), mobile = new Control();
    mobile.matches = true;
    const dialog = new Control(), title = new Control(), close = new Control(), form = new Control({confirm:'Disconnect?'});
    dialog.querySelector = selector => selector === 'h2' ? title : close;
    dialog.close = () => { dialog.open = false; dialog.fire('close'); };
    dialog.showModal = () => { dialog.open = true; };
    const check = new Control({integrationCheck:'/api/integrations/telegram/check', csrf:'test-token'});
    const status = new Control(), loader = new Control();
    check.closest = () => ({querySelector: () => status});
    check.parentElement = {querySelector: () => loader};
    page.querySelector = selector => ({'#integration-search':search, '#integration-connected-filter':connected,
        '#integration-results':results, '#integration-empty':empty, '#integration-reset':reset,
        '#integration-refresh-button':refreshButton, 'dialog[open]':dialog.open ? dialog : null})[selector];
    page.querySelectorAll = selector => ({'[data-integration-app]':cards, '[data-integration-category]':categories,
        '[data-integration-open]':[opener], 'dialog':[dialog], 'form[data-confirm]':[form], '[data-integration-check]':[check]})[selector];
    const requests = [], navigations = [], window = new Control();
    window.confirm = () => false;
    window.location = {assign: url => navigations.push(url)};
    const context = {document:{querySelector: selector => selector === '#integration-refresh' ? refresh : page, getElementById: () => dialog},
        window, matchMedia: () => mobile, customElements:{whenDefined: () => Promise.resolve()}, requestAnimationFrame: callback => callback(), URLSearchParams, AbortController, setTimeout, clearTimeout,
        fetch:async (url, options) => {
            requests.push({url, options});
            return {ok:!context.fail, json:async () => context.fail ? {error:'Reconnect Telegram.'} : {message:'Access confirmed.'}};
        }};
    vm.runInNewContext(readFileSync('static/js/integrations.js', 'utf8'), context);
    return {page, search, connected, categories, cards, reset, empty, results, opener, dialog, title, close, form, check, status, loader, requests, context, refresh, refreshButton, mobile, navigations};
}

test('pull and button refresh use GET navigation once and recover on browser back', () => {
    const f = fixture();
    f.refresh.fire('refresh');
    f.refreshButton.fire('click');
    assert.deepEqual(f.navigations, ['/integrations']);
    assert.equal(f.refresh.refreshing, true);
    assert.equal(f.refreshButton.disabled, true);
    assert.equal(f.refreshButton.getAttribute('aria-busy'), 'true');
    assert.equal(f.requests.length, 0);
    f.context.window.fire('pageshow');
    assert.equal(f.refresh.refreshing, false);
    assert.equal(f.refreshButton.disabled, false);
    assert.equal(f.refreshButton.getAttribute('aria-busy'), undefined);
    f.refreshButton.fire('click');
    assert.deepEqual(f.navigations, ['/integrations', '/integrations']);
});

test('pulls are enabled on mobile and paused while setup dialogs are open', () => {
    const f = fixture();
    assert.equal(f.refresh.disabled, false);
    f.opener.fire('click', {preventDefault() {}});
    assert.equal(f.refresh.disabled, true);
    f.close.fire('click');
    assert.equal(f.refresh.disabled, false);
    f.mobile.matches = false;
    f.mobile.fire('change');
    assert.equal(f.refresh.disabled, true);
    f.mobile.matches = true;
    f.mobile.fire('change');
    assert.equal(f.refresh.disabled, false);
});

test('unfinished sign-in opens after the refresh component is ready', async () => {
    const f = fixture('telegram');
    assert.equal(f.dialog.open, undefined);
    await Promise.resolve();
    assert.equal(f.dialog.open, true);
    assert.equal(f.title.focused, true);
    assert.equal(f.refresh.disabled, true);
});

test('category, search, and connected filters combine and reset together', () => {
    const f = fixture();
    const visible = () => f.cards.filter(card => !card.hidden).map(card => card.dataset.integrationApp);
    f.categories[2].fire('click');
    assert.deepEqual(visible(), ['telegram']);
    f.search.value = 'Gmail'; f.search.fire('input');
    assert.deepEqual(visible(), []); assert.equal(f.empty.hidden, false);
    f.reset.fire('click'); assert.equal(f.search.value, ''); assert.equal(f.search.focused, true);
    f.connected.fire('click'); assert.deepEqual(visible(), ['gmail', 'telegram']);
    f.categories[3].fire('click'); assert.deepEqual(visible(), []);
    f.connected.fire('click'); assert.deepEqual(visible(), ['tiktok']);
    assert.equal(f.results.textContent, '1 app');
});

test('dialogs manage focus and cancelled disconnects do not submit', () => {
    const f = fixture(); let prevented = false;
    f.opener.fire('click', {preventDefault() { prevented = true; }});
    assert.equal(prevented, true); assert.equal(f.dialog.open, true); assert.equal(f.title.focused, true);
    f.close.fire('click'); assert.equal(f.dialog.open, false); assert.equal(f.opener.focused, true);
    prevented = false;
    f.form.fire('submit', {preventDefault() { prevented = true; }});
    assert.equal(prevented, true);
});

test('checks are explicit, protect CSRF, and recover after API errors', async () => {
    const f = fixture(); assert.equal(f.requests.length, 0);
    const pending = f.check.fire('click');
    assert.equal(f.check.disabled, true); assert.equal(f.loader.hidden, false);
    await pending;
    assert.equal(f.requests[0].url, '/api/integrations/telegram/check');
    assert.equal(f.requests[0].options.method, 'POST');
    assert.equal(f.requests[0].options.body.get('csrf_token'), 'test-token');
    assert.equal(f.status.textContent, 'Access confirmed.');
    f.context.fail = true; await f.check.fire('click');
    assert.equal(f.status.dataset.error, 'true'); assert.equal(f.status.textContent, 'Reconnect Telegram.');
    assert.equal(f.check.disabled, false); assert.equal(f.loader.hidden, true);
});
