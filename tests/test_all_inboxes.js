/* Run with: node --test tests/test_all_inboxes.js */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const source = readFileSync('static/js/mail.js', 'utf8');
const section = (start, end) => source.slice(source.indexOf(start), source.indexOf(end));

function classes(...initial) {
    const values = new Set(initial);
    return {contains: name => values.has(name), toggle(name, value) { if (value) values.add(name); else values.delete(name); }};
}

function message(account, id, folder = 'inbox') {
    const checkbox = {checked: true};
    const star = {disabled: false, classList: classes(), setAttribute() {}};
    const state = {textContent: 'Unread: '};
    const row = {dataset: {mailAccount: account, messageId: id, mailFolder: folder}, classList: classes('unread'),
        contains: () => false, remove() { this.removed = true; },
        querySelector: selector => ({'.message-check': checkbox, '.star-button': star, '.message-read-state': state,
            '.message-subject': {textContent: 'Test email'}})[selector],
    };
    return {row, checkbox, star, state};
}

function inbox(messages, failures = {}) {
    const feedback = [], calls = [], listeners = {};
    const empty = {};
    const context = {
        app: {dataset: {account: 'all', csrf: 'fixture', actionsUrl: '/api/mail/action', messagesUrl: '/api/mail/messages'}},
        folder: 'inbox', actionPending: false, changeGeneration: 0, statusController: null,
        rows: () => messages.filter(message => !message.row.removed).map(message => message.row),
        window: {CentroMailAppearance: {get: () => 'false'}, location: {assign() {}}},
        document: {activeElement: {closest: () => null}, body: {}, querySelector: () => empty,
            addEventListener: (type, listener) => { listeners[type] = listener; }},
        list: {focus() {}}, selectAll: {}, updateSelection() {}, closeReader() {},
        selected: () => messages.filter(message => !message.row.removed && message.checkbox.checked),
        showFeedback: (text, reconnect) => feedback.push({text, reconnect}),
        loadCounts: () => { context.countRefreshes++; }, countRefreshes: 0,
        URLSearchParams,
        fetch: async (url, options) => {
            const account = options.body.get('account');
            calls.push({account, folder: options.body.get('folder'), ids: options.body.getAll('message_ids'), action: options.body.get('action')});
            return {ok: !failures[account], headers: {get: () => 'application/json'},
                json: async () => failures[account] || {}};
        },
    };
    vm.runInNewContext(section('const messageKey =', 'const clearFocusedRow =') +
        section('const readJson =', 'const updateSelection =') +
        section('const performAction =', "list.addEventListener('click'") +
        'this.performAction = performAction; this.messageKey = messageKey;', context);
    return {context, feedback, calls, listeners};
}

test('mixed selection sends each real account and folder only its own message IDs', async () => {
    const messages = [message('gmail', 'shared'), message('gmail', 'second'),
        message('email:imap:work', 'shared'), message('email:imap:work', 'deleted', 'trash')];
    const {context, calls} = inbox(messages);
    await context.performAction('read', messages.map(message => message.row));
    assert.deepEqual(calls, [
        {account: 'gmail', folder: 'inbox', ids: ['shared', 'second'], action: 'read'},
        {account: 'email:imap:work', folder: 'inbox', ids: ['shared'], action: 'read'},
        {account: 'email:imap:work', folder: 'trash', ids: ['deleted'], action: 'read'},
    ]);
    for (const item of messages) {
        assert.equal(item.row.classList.contains('unread'), false);
        assert.equal(item.checkbox.checked, false);
    }
    assert.equal(context.countRefreshes, 1);
});

test('one failed account keeps its selection and star state while healthy accounts finish', async () => {
    const messages = [message('gmail', 'shared'), message('email:imap:work', 'shared'), message('email:google:other', 'shared')];
    const {context, calls, feedback} = inbox(messages, {'email:imap:work': {error: 'Reconnect your email account.', reconnect: true}});
    await context.performAction('star', messages.map(message => message.row));
    assert.equal(calls.length, 3);
    assert.equal(messages[0].star.classList.contains('starred'), true);
    assert.equal(messages[2].star.classList.contains('starred'), true);
    assert.equal(messages[1].star.classList.contains('starred'), false);
    assert.equal(messages[1].checkbox.checked, true);
    assert.equal(messages[1].star.disabled, false);
    assert.match(feedback.at(-1).text, /2 messages updated\. 1 message could not be updated/);
    assert.equal(feedback.at(-1).reconnect, true);
});

test('aggregate rows missing a real account cannot submit an action', async () => {
    const item = message('', 'shared');
    const {context, calls, feedback} = inbox([item]);
    await context.performAction('trash', [item.row]);
    assert.equal(calls.length, 0);
    assert.equal(item.checkbox.checked, true);
    assert.match(feedback.at(-1).text, /Refresh the inbox/);
});

test('existing single-account rows can use the page account', async () => {
    const item = message('', 'shared');
    const {context, calls} = inbox([item]);
    context.app.dataset.account = 'gmail';
    await context.performAction('read', [item.row]);
    assert.equal(calls[0].account, 'gmail');
    assert.equal(item.checkbox.checked, false);
});

test('read events from any connected account refresh aggregate counts', () => {
    const {context, listeners} = inbox([]);
    vm.runInNewContext(section("document.addEventListener('centromail-mail-read'", 'const syncGmailStatus ='), context);
    listeners['centromail-mail-read']({detail: {account: 'email:imap:work'}});
    assert.equal(context.countRefreshes, 1);
    context.app.dataset.account = 'gmail';
    listeners['centromail-mail-read']({detail: {account: 'email:imap:work'}});
    assert.equal(context.countRefreshes, 1);
});

test('pagination preserves matching IDs from different accounts and displays partial-load warnings', async () => {
    const messages = [message('gmail', 'shared')];
    const {context, feedback} = inbox(messages);
    const incoming = [message('gmail', 'shared'), message('email:imap:work', 'shared'),
        message('email:imap:work', 'shared'), message('email:imap:work', 'second')];
    const fragment = {querySelectorAll: () => incoming.filter(message => !message.row.removed).map(message => message.row)};
    const element = () => ({hidden: false, setAttribute() {}, removeAttribute() {}});
    Object.assign(context, {
        cursor: 'next', hasMore: true, loading: false, failed: false, generation: 0, statusOffset: 0,
        controller: null, search: {value: ''}, status: {}, loadingIndicator: element(), more: element(),
        location: {origin: 'http://localhost'}, URL, AbortController,
        setTimeout: () => 1, clearTimeout() {}, clearFocusedRow() {}, sortMessages() {},
        setRefreshBusy() {}, updateSelection() {}, syncGmailStatus() {},
        fetch: async () => ({ok: true, headers: {get: () => 'application/json'}, json: async () =>
            ({html: fragment, next_cursor: null, total: 3, warning: 'Some accounts could not be loaded.'})}),
    });
    context.document.querySelector = selector => selector === '.inbox-tab.active' ? null : element();
    context.document.createRange = () => ({createContextualFragment: html => html});
    context.list.setAttribute = () => {};
    context.list.append = () => messages.push(...incoming.filter(message => !message.row.removed));
    vm.runInNewContext(section('const loadMessages =', '// Resizable reading pane') + 'this.loadMessages = loadMessages;', context);
    await context.loadMessages();
    assert.equal(messages.length, 3);
    assert.notEqual(context.messageKey(messages[0].row), context.messageKey(messages[1].row));
    assert.equal(feedback.at(-1).text, 'Some accounts could not be loaded.');
});
