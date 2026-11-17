(() => {
    const pane = document.querySelector('#telegram-workspace');
    if (!pane) return;
    const workspace = document.querySelector('#workspace-apps');
    const conversations = document.querySelector('#telegram-conversations');
    const chatSelect = document.querySelector('#telegram-chat-select');
    const topicPicker = document.querySelector('#telegram-topic-picker');
    const topicSelect = document.querySelector('#telegram-topic-select');
    const topicSearch = document.querySelector('#telegram-topic-search');
    const thread = document.querySelector('#telegram-thread');
    const status = document.querySelector('#telegram-chat-status');
    const loading = document.querySelector('#telegram-chat-loading');
    const form = document.querySelector('#telegram-send-form');
    const field = document.querySelector('#telegram-message');
    const send = document.querySelector('#telegram-send-button');
    const sendStatus = document.querySelector('#telegram-send-status');
    const older = document.querySelector('#telegram-load-older');
    const drafts = new Map(), selectedTopics = new Map(), photos = new Map();
    let chats = [], chatId, topicId, topicQuery = '', nextBefore, latestSeen, controller, poll, sending = false, canSend = false;
    let photoController, photoBusy = false;
    const photoQueue = [];
    const active = () => !pane.hidden && !workspace.hidden && !document.hidden;
    const key = () => `${chatId}:${topicId || ''}`;
    const chatUrl = (id, topic) => {
        const url = new URL(pane.dataset.chatUrl.replace('CHAT', id), location.origin);
        if (topic) url.searchParams.set('topic', topic);
        if (topicQuery) url.searchParams.set('topic_search', topicQuery);
        return url;
    };
    const readJson = async response => {
        if (response.redirected) { location.assign(response.url); throw new Error('Sign in again.'); }
        if (!response.headers.get('Content-Type')?.includes('application/json')) throw new Error('Could not load Telegram. Try Refresh.');
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Telegram is unavailable. Try again.');
        return data;
    };
    const syncComposer = () => {
        field.disabled = !canSend || sending;
        send.disabled = !canSend || sending || !field.value.trim();
        send.setAttribute('aria-busy', String(sending));
        send.querySelector('[data-telegram-send-label]').textContent = sending ? 'Sending…' : 'Send message';
    };
    const schedule = () => {
        clearTimeout(poll);
        if (active() && chatId && !sending) poll = setTimeout(() => loadChat(), 10000);
    };
    const fetchPhotos = async () => {
        if (photoBusy || !active()) return;
        photoBusy = true;
        try {
            while (photoQueue.length && active()) {
                const [element, id] = photoQueue.shift();
                if (!element.isConnected) continue;
                if (!photos.has(id)) {
                    photoController = new AbortController();
                    const timeout = setTimeout(() => photoController.abort(), 25000);
                    try {
                        const response = await fetch(pane.dataset.photoUrl.replace('CHAT', id), {signal:photoController.signal});
                        if (response.ok && response.headers.get('Content-Type') === 'image/jpeg') photos.set(id, URL.createObjectURL(await response.blob()));
                        else photos.set(id, null);
                    } catch { /* Keep initials when Telegram hides or cannot load a photo. */ }
                    finally { clearTimeout(timeout); }
                }
                if (photos.get(id)) {
                    const image = document.createElement('img');
                    image.src = photos.get(id); image.alt = ''; image.width = 40; image.height = 40;
                    element.replaceChildren(image);
                }
            }
        } finally { photoBusy = false; if (photoQueue.length && active()) fetchPhotos(); }
    };
    const photoObserver = new IntersectionObserver(entries => {
        entries.filter(entry => entry.isIntersecting).forEach(entry => {
            photoObserver.unobserve(entry.target);
            photoQueue.push([entry.target, entry.target.dataset.chatPhoto]);
        });
        fetchPhotos();
    });
    const avatar = (name, id) => {
        const element = document.createElement('span');
        element.className = 'telegram-avatar'; element.setAttribute('aria-hidden', 'true');
        element.textContent = name.slice(0, 2).toUpperCase(); element.dataset.chatPhoto = id;
        photoObserver.observe(element);
        return element;
    };
    const renderMessages = (messages, prepend) => {
        const atBottom = thread.scrollHeight - thread.scrollTop - thread.clientHeight < 80;
        const oldHeight = thread.scrollHeight, oldTop = thread.scrollTop;
        const fragment = document.createDocumentFragment();
        for (const message of messages) {
            if (thread.querySelector(`[data-telegram-message="${CSS.escape(message.id)}"]`)) continue;
            const row = document.createElement('article');
            row.className = 'apps-feed-message telegram-message';
            row.classList.toggle('is-outgoing', message.outgoing);
            row.dataset.telegramMessage = message.id;
            for (const [tag, value] of [['strong', message.sender], ['time', message.time], ['p', message.text]]) {
                if (tag === 'p' && !value) continue;
                const element = document.createElement(tag); element.textContent = value || ''; row.append(element);
            }
            if (message.media) {
                const media = message.media;
                const container = document.createElement('div'); container.className = 'telegram-message-media';
                if (media.available === false) {
                    container.textContent = 'Open Telegram for media larger than 64 MB.';
                } else {
                    const asset = document.createElement(media.kind === 'video' ? 'video' : 'img');
                    if (media.kind === 'video') {
                        asset.controls = true; asset.preload = 'none'; asset.playsInline = true;
                        asset.setAttribute('aria-label', `Video from ${message.sender}`);
                    } else {
                        asset.alt = `Photo from ${message.sender}`; asset.loading = 'lazy'; asset.decoding = 'async';
                    }
                    asset.src = media.url;
                    const failure = document.createElement('p'); failure.className = 'telegram-media-error'; failure.hidden = true;
                    failure.append('Media could not be loaded. ');
                    const retry = document.createElement('button'); retry.type = 'button'; retry.className = 'm3e-button m3e-button--text'; retry.textContent = 'Retry';
                    retry.addEventListener('click', () => {
                        failure.hidden = true; asset.hidden = false;
                        asset.src = media.url;
                        if (media.kind === 'video') asset.load();
                    });
                    failure.append(retry);
                    asset.addEventListener('error', () => { asset.hidden = true; failure.hidden = false; });
                    asset.addEventListener(media.kind === 'video' ? 'loadedmetadata' : 'load', () => {
                        if (atBottom && !prepend) thread.scrollTop = thread.scrollHeight;
                    });
                    container.append(asset, failure);
                }
                row.append(container);
            }
            fragment.append(row);
        }
        if (prepend) { thread.prepend(fragment); thread.scrollTop = oldTop + thread.scrollHeight - oldHeight; }
        else { thread.append(fragment); if (atBottom) thread.scrollTop = thread.scrollHeight; }
    };
    const loadChat = async ({reset = false, before = null} = {}) => {
        if (!chatId || !active() || (controller && !reset)) return;
        clearTimeout(poll);
        controller?.abort();
        const pending = new AbortController(); controller = pending;
        const timeout = setTimeout(() => pending.abort(), 30000);
        const destination = key();
        let moreIncoming = false;
        if (reset) { thread.replaceChildren(); canSend = false; syncComposer(); status.textContent = 'Loading messages…'; loading.hidden = false; }
        thread.setAttribute('aria-busy', 'true'); older.disabled = true;
        const url = chatUrl(chatId, topicId);
        if (before) url.searchParams.set('before', before);
        else if (!reset && latestSeen) url.searchParams.set('after', latestSeen);
        try {
            const data = await readJson(await fetch(url, {signal:pending.signal}));
            if (controller !== pending || key() !== destination) return;
            topicPicker.hidden = !data.forum;
            const options = JSON.stringify(data.topics);
            if (topicSelect.dataset.options !== options) {
                topicSelect.dataset.options = options;
                topicSelect.replaceChildren();
                for (const topic of data.topics) {
                    const option = document.createElement('option'); option.value = topic.id;
                    option.textContent = topic.title + (topic.closed ? ' · Closed' : topic.hidden ? ' · Hidden' : '');
                    topicSelect.append(option);
                }
            }
            if (data.forum && !topicId) {
                topicId = selectedTopics.get(chatId) || data.topics.find(topic => !topic.hidden)?.id;
                if (!data.topics.some(topic => topic.id === topicId)) topicId = data.topics[0]?.id;
                if (topicId) { controller = null; field.value = drafts.get(key())?.text || ''; loadChat({reset:true}); return; }
            }
            topicSelect.value = topicId || '';
            canSend = data.can_send;
            renderMessages(data.messages, Boolean(before));
            if (!before) latestSeen = data.latest_seen || latestSeen;
            moreIncoming = data.has_more_new;
            if (before || reset) nextBefore = data.next_before;
            older.hidden = !nextBefore;
            status.textContent = thread.children.length ? 'Up to date · Checks for new messages every 10 seconds.' : data.forum && !topicId ? 'No topics are available.' : 'No messages in this part of the conversation yet.';
            if (!sending) sendStatus.textContent = canSend ? 'Enter for a new line. Ctrl or ⌘ + Enter to send.' : 'This conversation or topic is read-only.';
            syncComposer();
        } catch (error) {
            if (controller === pending) status.textContent = error.name === 'AbortError' ? 'Loading took too long. Try Refresh.' : error.message;
        } finally {
            clearTimeout(timeout);
            if (controller === pending) {
                controller = null; thread.removeAttribute('aria-busy'); older.disabled = false; loading.hidden = true;
                if (moreIncoming && active()) poll = setTimeout(() => loadChat(), 0);
                else schedule();
            }
        }
    };
    const chooseChat = id => {
        chatId = id; topicId = null; topicQuery = ''; topicSearch.value = ''; nextBefore = null; latestSeen = null; older.hidden = true; topicPicker.hidden = true;
        conversations.querySelectorAll('button').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.chatId === id)));
        chatSelect.value = id;
        const chat = chats.find(item => item.chat_id === id);
        document.querySelector('#telegram-chat-title').textContent = chat.sender;
        document.querySelector('#telegram-chat-kind').textContent = {forum:'Forum group · Topics enabled',group:'Group chat · Topics disabled',private:'Private conversation',channel:'Channel'}[chat.kind] || 'Conversation';
        document.querySelector('#telegram-chat-avatar').replaceChildren(avatar(chat.sender, id));
        field.value = drafts.get(key())?.text || '';
        loadChat({reset:true});
    };
    field.addEventListener('input', () => {
        const requestId = [...crypto.getRandomValues(new Uint8Array(16))].map(value => value.toString(16).padStart(2, '0')).join('');
        drafts.set(key(), {text:field.value, requestId}); syncComposer();
    });
    field.addEventListener('keydown', event => {
        if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) { event.preventDefault(); if (!send.disabled) form.requestSubmit(); }
    });
    topicSelect.addEventListener('change', () => {
        topicId = topicSelect.value; selectedTopics.set(chatId, topicId); nextBefore = null; latestSeen = null; older.hidden = true;
        field.value = drafts.get(key())?.text || ''; loadChat({reset:true});
    });
    document.querySelector('#telegram-topic-search-form').addEventListener('submit', event => {
        event.preventDefault(); topicQuery = topicSearch.value.trim(); topicId = null;
        nextBefore = null; latestSeen = null; older.hidden = true; loadChat({reset:true});
    });
    chatSelect.addEventListener('change', () => chooseChat(chatSelect.value));
    older.addEventListener('click', () => loadChat({before:nextBefore}));
    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (sending || !canSend || !field.value.trim()) return;
        const destination = key(), draft = drafts.get(destination);
        if (!draft) { field.dispatchEvent(new Event('input')); form.requestSubmit(); return; }
        const url = chatUrl(chatId, topicId);
        sending = true; clearTimeout(poll); syncComposer(); sendStatus.textContent = 'Sending message…';
        const pending = new AbortController(), timeout = setTimeout(() => pending.abort(), 30000);
        try {
            await readJson(await fetch(url, {method:'POST',signal:pending.signal,body:new URLSearchParams({text:draft.text,request_id:draft.requestId,csrf_token:pane.dataset.csrf})}));
            if (drafts.get(destination) === draft) drafts.delete(destination);
            if (key() === destination) { field.value = ''; sendStatus.textContent = 'Message sent.'; window.CentroMailMotion?.feedback(send, 'send'); loadChat(); }
        } catch (error) {
            if (key() === destination) sendStatus.textContent = error.name === 'AbortError' ? 'Send confirmation took too long. Your draft is kept; Refresh to check before retrying.' : error.message;
        } finally { clearTimeout(timeout); sending = false; syncComposer(); schedule(); }
    });
    const visibility = () => {
        if (!active()) { clearTimeout(poll); controller?.abort(); controller = null; thread.removeAttribute('aria-busy'); loading.hidden = true; }
        else { loadChat(); fetchPhotos(); }
    };
    document.addEventListener('visibilitychange', visibility);
    new MutationObserver(visibility).observe(workspace, {attributes:true,attributeFilter:['hidden']});
    window.CentroMailTelegram = {
        close() { pane.hidden = true; clearTimeout(poll); controller?.abort(); controller = null; photoController?.abort(); photoObserver.disconnect(); photoQueue.length = 0; },
        open(items) {
            pane.hidden = false; chats = items; conversations.replaceChildren(); chatSelect.replaceChildren();
            for (const chat of chats) {
                const button = document.createElement('button'); button.type = 'button'; button.className = 'm3e-button m3e-button--text telegram-conversation';
                button.dataset.chatId = chat.chat_id; button.setAttribute('aria-pressed','false'); button.setAttribute('aria-controls','telegram-thread');
                const copy = document.createElement('span'), name = document.createElement('strong'), preview = document.createElement('small');
                name.textContent = chat.sender; preview.textContent = (chat.unread ? `${chat.unread} unread · ` : '') + (chat.text || (chat.media?.kind === 'video' ? 'Video' : chat.media ? 'Photo' : ''));
                copy.append(name,preview); button.append(avatar(chat.sender,chat.chat_id),copy);
                button.addEventListener('click', () => chooseChat(chat.chat_id)); conversations.append(button);
                const option = document.createElement('option'); option.value = chat.chat_id; option.textContent = chat.sender; chatSelect.append(option);
            }
            const account = document.querySelector('[data-app-provider="telegram"] img');
            if (account && !account.parentElement.querySelector('.telegram-avatar')) account.replaceWith(avatar('Telegram','me'));
            const accountAvatar = document.querySelector('[data-app-provider="telegram"] .telegram-avatar');
            if (accountAvatar && !accountAvatar.querySelector('img')) photoObserver.observe(accountAvatar);
            if (chats.length) chooseChat(chats.some(chat => chat.chat_id === chatId) ? chatId : chats[0].chat_id);
            else { chatId = null; thread.replaceChildren(); canSend = false; syncComposer(); status.textContent = 'No recent Telegram conversations yet.'; }
            fetchPhotos();
        },
    };
})();
