/* Run with: node --test tests/test_telegram_feed_media.js */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');

async function feed(messages) {
    const element = tag => ({tag, children: [], listeners: {}, attributes: {},
        append(...items) { this.children.push(...items); },
        replaceChildren(...items) { this.children = items; },
        setAttribute(name, value) { this.attributes[name] = value; },
        addEventListener(name, callback) { this.listeners[name] = callback; },
        load() { this.loads = (this.loads || 0) + 1; },
    });
    const panel = {...element('div'), dataset: {integrationFeed: '/api/integrations/telegram/messages'}};
    const context = {document: {querySelectorAll: () => [panel], createElement: element},
        AbortController, setTimeout: () => 1, clearTimeout() {},
        fetch: async () => ({ok: true, json: async () => ({messages})}),
    };
    vm.runInNewContext(readFileSync('static/js/integration-feeds.js', 'utf8'), context);
    await new Promise(resolve => setImmediate(resolve));
    return panel.children[0].children;
}

test('photos keep captions as text and load lazily through the private URL', async () => {
    const url = '/api/integrations/telegram/chats/-123/messages/5/media';
    const [row] = await feed([{sender: 'Friend', text: '<script>caption</script>', time: 'Today',
        media: {kind: 'photo', url, mime_type: 'image/jpeg'}}]);
    const copy = row.children[1];
    assert.equal(copy.children[1].textContent, '<script>caption</script>');
    const wrapper = copy.children[2], link = wrapper.children[0], photo = link.children[0];
    assert.equal(photo.tag, 'img');
    assert.equal(photo.src, url);
    assert.equal(photo.loading, 'lazy');
    assert.equal(photo.alt, 'Photo from Friend');
    assert.equal(link.href, url);
    assert.equal(link.rel, 'noopener');
    photo.listeners.error();
    assert.equal(wrapper.children[1].hidden, false);
    wrapper.children[1].children[1].listeners.click();
    assert.equal(photo.hidden, false);
    assert.equal(wrapper.children[1].hidden, true);
});

test('media-only video messages have native controls and a working retry', async () => {
    const url = '/api/integrations/telegram/chats/-123/messages/6/media';
    const [row] = await feed([{sender: 'Friend', text: '', time: 'Today',
        media: {kind: 'video', url, mime_type: 'video/mp4'}}]);
    const copy = row.children[1];
    assert.equal(copy.children.length, 2);
    const wrapper = copy.children[1], video = wrapper.children[0], source = video.children[0];
    assert.equal(video.tag, 'video');
    assert.equal(video.controls, true);
    assert.equal(video.playsInline, true);
    assert.equal(video.preload, 'none');
    assert.equal(video.attributes['aria-label'], 'Video from Friend');
    assert.equal(source.src, url);
    assert.equal(source.type, 'video/mp4');
    source.listeners.error();
    assert.equal(wrapper.children[1].hidden, false);
    wrapper.children[1].children[1].listeners.click();
    assert.equal(video.loads, 1);
    video.listeners.loadedmetadata();
    assert.equal(wrapper.children[1].hidden, true);
});

test('text messages and unsupported attachments keep their existing copy', async () => {
    const rows = await feed([{sender: 'One', text: 'Plain message', time: '', media: null},
        {sender: 'Two', text: 'Document', time: '', media: {kind: 'document'}}]);
    assert.deepEqual(rows.map(row => row.children[1].children[1].textContent), ['Plain message', 'Document']);
    assert.ok(rows.every(row => row.children[1].children.length === 2));
});

test('oversized media displays its limit without requesting the asset', async () => {
    const [row] = await feed([{sender: 'Friend', text: '', time: '',
        media: {kind: 'video', available: false, size: 70 * 1024 * 1024, url: '/large-video'}}]);
    const copy = row.children[1];
    assert.equal(copy.children.length, 2);
    assert.equal(copy.children[1].tag, 'p');
    assert.equal(copy.children[1].textContent, 'Open Telegram for media larger than 64 MB.');
});
