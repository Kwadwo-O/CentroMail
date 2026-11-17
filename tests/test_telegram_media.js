/* Run with: node --test tests/test_telegram_media.js */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');

function history() {
    const create = tag => ({tag, children: [], dataset: {}, events: {}, attributes: {},
        classList: {toggle() {}}, append(...items) { this.children.push(...items.flatMap(item => item.tag === 'fragment' ? item.children : [item])); },
        querySelector(selector) { return this.children.find(child => child.dataset?.messageText !== undefined && selector === '[data-message-text]') || null; },
        prepend(fragment) { this.children.unshift(...fragment.children); },
        setAttribute(name, value) { this.attributes[name] = value; },
        addEventListener(name, callback) { this.events[name] = callback; },
        load() { this.loaded = true; }});
    const thread = {...create('thread'), scrollHeight: 200, scrollTop: 0, clientHeight: 200,
        querySelector(selector) { return this.children.find(row => selector.includes('"' + row.dataset.telegramMessage + '"')) || null; }};
    const context = {thread, renderMessageActions() {}, CSS: {escape: value => value}, document: {createElement: create,
        createDocumentFragment: () => create('fragment')}};
    const source = readFileSync('static/js/telegram-chat.js', 'utf8');
    vm.runInNewContext(source.slice(source.indexOf('const renderMessages ='), source.indexOf('const loadChat =')) +
        '\nthis.render = renderMessages;', context);
    return {thread, render: context.render};
}

function assets(node, tag) {
    return node.children.flatMap(child => typeof child === 'object' ?
        [...(child.tag === tag ? [child] : []), ...assets(child, tag)] : []);
}

test('chat photos and media-only videos render with captions and native controls', () => {
    const {thread, render} = history();
    render([{id: '1', sender: 'Friend', time: 'Today', text: '<Photo caption>',
        media: {kind: 'photo', url: '/private/photo'}},
        {id: '2', sender: 'Friend', time: 'Today', text: '', media: {kind: 'video', url: '/private/video'}}]);
    const image = assets(thread, 'img')[0], video = assets(thread, 'video')[0];
    assert.equal(image.loading, 'lazy');
    assert.equal(image.alt, 'Photo from Friend');
    assert.equal(image.src, '/private/photo');
    assert.equal(video.controls, true);
    assert.equal(video.preload, 'none');
    assert.equal(video.playsInline, true);
    assert.equal(assets(thread.children[0], 'p')[0].textContent, '<Photo caption>');
    assert.equal(assets(thread.children[1], 'p').filter(element => !element.hidden).length, 0);
    render([{id: '1', sender: 'Friend', text: '', media: {kind: 'photo', url: '/private/photo'}}]);
    assert.equal(thread.children.length, 2);
});

test('failed media has a visible retry and oversized files avoid loading', () => {
    const {thread, render} = history();
    render([{id: '1', sender: 'Friend', text: '', media: {kind: 'video', url: '/private/video'}},
        {id: '2', sender: 'Friend', text: 'Large clip', media: {kind: 'video', available: false, url: '/large'}}]);
    const video = assets(thread, 'video')[0], retry = assets(thread, 'button')[0];
    const error = assets(thread.children[0], 'p')[1];
    video.events.error();
    assert.equal(video.hidden, true);
    assert.equal(error.hidden, false);
    retry.events.click();
    assert.equal(video.hidden, false);
    assert.equal(error.hidden, true);
    assert.equal(video.loaded, true);
    assert.equal(assets(thread.children[1], 'video').length, 0);
    assert.equal(thread.children[1].children.at(-1).textContent, 'Open Telegram for media larger than 64 MB.');
});
