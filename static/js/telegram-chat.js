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
    const replyStatus = document.querySelector('#telegram-reply-status'), cancelReply = document.querySelector('#telegram-cancel-reply');
    const actionDialog = document.querySelector('#telegram-message-dialog'), actionForm = document.querySelector('#telegram-action-form');
    const actionStatus = document.querySelector('#telegram-action-status'), actionSave = document.querySelector('#telegram-action-save');
    const editText = document.querySelector('#telegram-edit-text'), forwardChat = document.querySelector('#telegram-forward-chat');
    const forwardTopic = document.querySelector('#telegram-forward-topic'), reaction = document.querySelector('#telegram-reaction');
    const replies = new Map();
    let actionContext, actionBusy = false, forwardController;
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
        const reply = replies.get(key());
        replyStatus.hidden = cancelReply.hidden = !reply;
        cancelReply.disabled = sending;
        replyStatus.textContent = reply ? `Replying to ${reply.sender}: ${reply.text || 'Media message'}` : '';
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
    const messageAction = async (context, action, values = {}) => {
        const url = chatUrl(context.chat, context.topic);
        url.searchParams.delete('topic_search');
        url.pathname += `/messages/${encodeURIComponent(context.id)}/actions`;
        const pending = new AbortController(), timeout = setTimeout(() => pending.abort(), 30000);
        try {
            return await readJson(await fetch(url, {method:'POST', signal:pending.signal,
                body:new URLSearchParams({action, topic:context.topic || '', csrf_token:pane.dataset.csrf, ...values})}));
        } finally { clearTimeout(timeout); }
    };
    const applyAction = (context, data) => {
        if (key() !== context.key) return;
        const row = thread.querySelector(`[data-telegram-message="${CSS.escape(context.id)}"]`);
        if (data.deleted) { row?.remove(); if (replies.get(key())?.id === context.id) replies.delete(key()); syncComposer(); }
        else if (data.message) renderMessages([data.message]);
    };
    const loadForwardTopics = async () => {
        forwardController?.abort();
        const pending = new AbortController(); forwardController = pending;
        const chat = chats.find(item => item.chat_id === forwardChat.value);
        document.querySelector('#telegram-forward-topic-picker').hidden = chat?.kind !== 'forum';
        forwardTopic.replaceChildren();
        if (chat?.kind !== 'forum') { actionSave.disabled = false; return; }
        actionSave.disabled = true; actionStatus.textContent = 'Loading destination topics…';
        const timeout = setTimeout(() => pending.abort(), 30000);
        try {
            const url = chatUrl(chat.chat_id); url.searchParams.delete('topic_search');
            const data = await readJson(await fetch(url, {signal:pending.signal}));
            if (forwardController !== pending) return;
            for (const topic of data.topics.filter(item => !item.closed && !item.hidden)) {
                const option = document.createElement('option'); option.value = topic.id; option.textContent = topic.title; forwardTopic.append(option);
            }
            actionSave.disabled = !forwardTopic.options.length;
            actionStatus.textContent = actionSave.disabled ? 'No writable topics are available.' : '';
        } catch (error) { if (forwardController === pending) actionStatus.textContent = error.name === 'AbortError' ? 'Topic loading took too long. Choose the destination again.' : error.message; }
        finally { clearTimeout(timeout); }
    };
    const openAction = (context, action, message) => {
        actionContext = {...context, action, original:message.text, requestId:[...crypto.getRandomValues(new Uint8Array(16))].map(value => value.toString(16).padStart(2,'0')).join('')};
        document.querySelector('#telegram-edit-fields').hidden = action !== 'edit';
        document.querySelector('#telegram-forward-fields').hidden = action !== 'forward';
        document.querySelector('#telegram-reaction-fields').hidden = action !== 'reaction';
        document.querySelector('#telegram-action-title').textContent = {edit:'Edit message', forward:'Forward message', reaction:'React to message'}[action];
        actionSave.textContent = action === 'forward' ? 'Forward' : 'Save changes'; actionSave.disabled = false; actionStatus.textContent = '';
        editText.value = message.text || ''; editText.maxLength = message.edit_limit || 4096;
        reaction.value = message.reactions?.find(item => item.chosen)?.emoji || '';
        if (action === 'forward') {
            forwardChat.replaceChildren();
            for (const chat of chats) { const option = document.createElement('option'); option.value = chat.chat_id; option.textContent = chat.sender; forwardChat.append(option); }
            loadForwardTopics();
        }
        actionDialog.showModal();
        (action === 'edit' ? editText : action === 'reaction' ? reaction : forwardChat).focus();
    };
    const renderMessageActions = (row, message) => {
        const footer = document.createElement('div'); footer.className = 'chat-message-footer';
        const meta = document.createElement('span'); meta.className = 'chat-message-meta';
        meta.textContent = [message.edited ? 'Edited' : '', message.pinned ? 'Pinned' : '', ...(message.reactions || []).map(item => `${item.emoji} ${item.count}`)].filter(Boolean).join(' · ');
        footer.append(meta);
        const button = document.createElement('button'); button.type = 'button'; button.className = 'm3e-icon-button m3e-icon-button--standard';
        button.id = `telegram-actions-${message.id}`; button.setAttribute('aria-label', `Actions for message from ${message.sender}`);
        const icon = document.createElement('span'); icon.className = 'm3e-icon'; icon.setAttribute('aria-hidden','true'); icon.textContent = 'more_horiz'; button.append(icon);
        const menu = document.createElement('m3e-menu'); menu.setAttribute('anchor', button.id); menu.setAttribute('label','Message actions');
        const actions = [['reply','Reply',canSend],['copy','Copy text',Boolean(message.text)],['link','Copy message link',Boolean(message.link)],
            ['edit','Edit',message.can_edit],['forward','Forward',message.can_forward],['reaction','React',message.can_react],
            [message.pinned ? 'unpin' : 'pin',message.pinned ? 'Unpin' : 'Pin',message.can_pin],
            ['delete','Delete for everyone',message.can_delete],['delete-for-me','Delete for me',message.can_delete_for_me]];
        for (const [value, title, available] of actions) if (available) {
            const item = document.createElement('m3e-menu-item'); item.setAttribute('value',value); item.textContent = title; menu.append(item);
        }
        menu.addEventListener('action', async event => {
            const action = event.detail.value, current = row.telegramMessage;
            const context = {key:key(), chat:chatId, topic:topicId, id:current.id};
            try {
                if (action === 'reply') { replies.set(key(), {id:current.id, sender:current.sender, text:current.text}); field.dispatchEvent(new Event('input')); syncComposer(); field.focus(); return; }
                if (action === 'copy' || action === 'link') { await navigator.clipboard.writeText(action === 'copy' ? current.text : current.link); status.textContent = 'Copied to clipboard.'; window.CentroMailMotion?.feedback(button,'copy'); return; }
                if (['edit','forward','reaction'].includes(action)) { openAction(context, action, current); return; }
                if (row.getAttribute('aria-busy') === 'true') return;
                if (action.startsWith('delete') && window.CentroMailAppearance.get('confirm-actions') !== 'false' && !confirm(action === 'delete' ? 'Delete this message for everyone? This cannot be undone.' : 'Delete this message only for you?')) return;
                row.setAttribute('aria-busy','true');
                const data = await messageAction(context, action.startsWith('delete') ? 'delete' : action, {revoke:String(action !== 'delete-for-me')});
                applyAction(context, data); if (key() === context.key) status.textContent = action.startsWith('delete') ? 'Message deleted.' : action === 'pin' ? 'Message pinned.' : 'Message unpinned.';
            } catch (error) { if (key() === context.key) status.textContent = error.name === 'AbortError' ? 'The action was not confirmed. Refresh before retrying.' : error.message; }
            finally { row.removeAttribute('aria-busy'); }
        });
        footer.append(button, menu);
        if (message.media?.available && message.media.url) {
            const download = document.createElement('a'); download.className = 'm3e-button m3e-button--text'; download.textContent = 'Download'; download.href = message.media.url;
            download.download = message.media.name || `telegram-${message.id}.${message.media.kind === 'video' ? 'mp4' : 'jpg'}`; footer.append(download);
        }
        row.append(footer);
    };
    const renderMessages = (messages, prepend) => {
        const atBottom = thread.scrollHeight - thread.scrollTop - thread.clientHeight < 80;
        const oldHeight = thread.scrollHeight, oldTop = thread.scrollTop;
        const fragment = document.createDocumentFragment();
        for (const message of messages) {
            const existing = thread.querySelector(`[data-telegram-message="${CSS.escape(message.id)}"]`);
            if (existing) {
                if (JSON.stringify(existing.telegramMessage) === JSON.stringify(message)) continue;
                const text = existing.querySelector('[data-message-text]'); text.textContent = message.text || ''; text.hidden = !message.text;
                existing.telegramMessage = message;
                existing.querySelector('.chat-message-footer')?.remove(); renderMessageActions(existing, message); continue;
            }
            const row = document.createElement('article');
            row.className = 'apps-feed-message telegram-message';
            row.classList.toggle('is-outgoing', message.outgoing);
            row.dataset.telegramMessage = message.id;
            row.telegramMessage = message;
            for (const [tag, value] of [['strong', message.sender], ['time', message.time], ['p', message.text]]) {
                const element = document.createElement(tag); element.textContent = value || '';
                if (tag === 'p') { element.dataset.messageText = ''; element.hidden = !value; }
                row.append(element);
            }
            if (message.media) {
                const media = message.media;
                const container = document.createElement('div'); container.className = 'telegram-message-media';
                if (media.available === false) {
                    container.textContent = 'Open Telegram for media larger than 64 MB.';
                } else if (media.kind === 'file') {
                    container.textContent = media.name || 'Attachment';
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
            renderMessageActions(row, message); fragment.append(row);
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
        if (!reset && !before && thread.children.length) url.searchParams.set('known_ids', [...thread.children].slice(-50).map(row => row.dataset.telegramMessage).join(','));
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
            renderMessages(data.updated_messages || []);
            for (const id of data.deleted_ids || []) { thread.querySelector(`[data-telegram-message="${CSS.escape(id)}"]`)?.remove(); if (replies.get(key())?.id === id) replies.delete(key()); }
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
    cancelReply.addEventListener('click', () => { replies.delete(key()); field.dispatchEvent(new Event('input')); syncComposer(); field.focus(); });
    forwardChat.addEventListener('change', loadForwardTopics);
    document.querySelectorAll('[data-telegram-reaction]').forEach(button => button.addEventListener('click', () => { reaction.value = button.dataset.telegramReaction; }));
    document.querySelector('#telegram-action-cancel').addEventListener('click', () => { if (!actionBusy) actionDialog.close(); });
    actionDialog.addEventListener('cancel', event => { if (actionBusy) event.preventDefault(); });
    actionForm.addEventListener('submit', async event => {
        event.preventDefault(); if (actionBusy || !actionContext) return;
        const context = actionContext;
        const values = context.action === 'edit' ? {text:editText.value, original:context.original} : context.action === 'forward' ? {destination:forwardChat.value, destination_topic:forwardTopic.value || '', request_id:context.requestId} : {emoji:reaction.value.trim()};
        actionBusy = true; actionSave.disabled = true; actionForm.setAttribute('aria-busy','true'); actionStatus.textContent = 'Applying changes…';
        actionForm.querySelectorAll('input,textarea,select,button').forEach(element => { element.disabled = true; });
        try { const data = await messageAction(context, context.action, values); applyAction(context, data); actionDialog.close(); if (key() === context.key) status.textContent = context.action === 'forward' ? 'Message forwarded.' : 'Message updated.'; }
        catch (error) { actionStatus.textContent = error.name === 'AbortError' ? 'The action was not confirmed. Your edit is kept; refresh before retrying.' : error.message; }
        finally { actionBusy = false; actionForm.querySelectorAll('input,textarea,select,button').forEach(element => { element.disabled = false; }); actionForm.removeAttribute('aria-busy'); }
    });
    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (sending || !canSend || !field.value.trim()) return;
        const destination = key(), draft = drafts.get(destination);
        if (!draft) { field.dispatchEvent(new Event('input')); form.requestSubmit(); return; }
        const url = chatUrl(chatId, topicId);
        sending = true; clearTimeout(poll); syncComposer(); sendStatus.textContent = 'Sending message…';
        const pending = new AbortController(), timeout = setTimeout(() => pending.abort(), 30000);
        try {
            await readJson(await fetch(url, {method:'POST',signal:pending.signal,body:new URLSearchParams({text:draft.text,request_id:draft.requestId,reply_id:replies.get(destination)?.id || '',csrf_token:pane.dataset.csrf})}));
            if (drafts.get(destination) === draft) drafts.delete(destination);
            if (!drafts.has(destination)) replies.delete(destination);
            if (key() === destination) { field.value = drafts.get(destination)?.text || ''; sendStatus.textContent = 'Message sent.'; window.CentroMailMotion?.feedback(send, 'send'); loadChat(); }
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
        close() { pane.hidden = true; if (!actionBusy) actionDialog.close(); forwardController?.abort(); clearTimeout(poll); controller?.abort(); controller = null; photoController?.abort(); photoObserver.disconnect(); photoQueue.length = 0; },
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
