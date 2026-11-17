(() => {
    const pane = document.querySelector('#teams-chat-pane');
    if (!pane) { window.CentroMailTeams = {close() {}}; return; }
    const source = pane.querySelector('#teams-source'), teams = pane.querySelector('#teams-team');
    const list = pane.querySelector('#teams-conversations'), thread = pane.querySelector('#teams-thread');
    const status = pane.querySelector('#teams-chat-status'), listStatus = pane.querySelector('#teams-list-status');
    const loading = pane.querySelector('#teams-chat-loading'), more = pane.querySelector('#teams-more-conversations');
    const older = pane.querySelector('#teams-older-messages'), moreTeams = pane.querySelector('#teams-more-teams');
    const form = pane.querySelector('#teams-send-form'), field = pane.querySelector('#teams-message-text');
    const send = pane.querySelector('#teams-send-button'), sendStatus = pane.querySelector('#teams-send-status');
    const replyStatus = pane.querySelector('#teams-reply-status'), cancelReply = pane.querySelector('#teams-cancel-reply');
    const drafts = new Map(), replyRequests = new Set();
    let rooms = [], current, reply, listCursor, teamCursor, messageCursor, listController, messageController, sending = false;
    const draftKey = () => JSON.stringify([current?.key, reply || null]);
    const keepDraft = () => { if (current) drafts.set(draftKey(), {text: field.value, warning: drafts.get(draftKey())?.warning}); };
    const node = (tag, className, text) => {
        const element = document.createElement(tag); element.className = className; if (text != null) element.textContent = text; return element;
    };
    const url = (kind, cursor, team) => {
        const value = new URL(pane.dataset.conversationsUrl, location.origin);
        value.searchParams.set('kind', kind);
        if (cursor) value.searchParams.set('cursor', cursor);
        if (team) value.searchParams.set('team', team);
        return value;
    };
    const messageUrl = (room = current) => pane.dataset.conversationsUrl + '/' + encodeURIComponent(room.key) + '/messages';
    const read = async (url, controller, options = {}) => {
        const timer = setTimeout(() => controller.abort(), 30000);
        try {
            const response = await fetch(url, {...options, signal: controller.signal});
            if (response.redirected) { location.assign(response.url); throw new Error('Sign in again to continue.'); }
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Teams could not complete the request.');
            return data;
        } finally { clearTimeout(timer); }
    };
    const syncComposer = () => {
        field.disabled = !current || sending; send.disabled = !current || sending || !field.value.trim();
        send.setAttribute('aria-busy', String(sending));
        send.querySelector('[data-teams-send-label]').textContent = sending ? 'Sending…' : reply ? 'Send reply' : current?.kind === 'channel' ? 'Post to channel' : 'Send message';
    };
    const restoreDraft = () => {
        field.value = drafts.get(draftKey())?.text || '';
        sendStatus.textContent = drafts.get(draftKey())?.warning || 'Enter for a new line. Ctrl or ⌘ + Enter to send.';
        replyStatus.hidden = !reply; cancelReply.hidden = !reply;
        replyStatus.textContent = reply ? 'Replying in this channel thread.' : '';
        syncComposer();
    };
    const renderMessage = (message, room, isReply = false) => {
        const row = node('article', 'cm-teams-message' + (message.outgoing ? ' is-outgoing' : ''));
        row.dataset.messageId = message.id;
        const header = node('header', ''), date = new Date(message.time);
        header.append(node('strong', '', message.sender), node('time', '', Number.isNaN(date.getTime()) ? message.time : date.toLocaleString()));
        row.append(header);
        if (message.subject) row.append(node('strong', '', message.subject));
        row.append(node('p', '', message.text || (message.attachments?.length ? 'Attachment' : 'System message')));
        if (message.attachments?.length) row.append(node('p', '', message.attachments.join(', ')));
        if (message.url) {
            const link = node('a', '', 'Open in Teams'); link.href = message.url; link.target = '_blank'; link.rel = 'noreferrer'; row.append(link);
        }
        if (room.kind === 'channel' && !isReply) {
            const replyButton = node('button', 'm3e-button m3e-button--text', 'Reply in thread'); replyButton.type = 'button';
            replyButton.addEventListener('click', () => { if (current?.key !== room.key) return; keepDraft(); reply = message.id; restoreDraft(); field.focus(); });
            row.append(replyButton);
            const details = node('details', 'cm-teams-replies'), body = node('div', '');
            details.append(node('summary', '', 'View replies'), body);
            let loaded = false, pending = false, cursor;
            const loadReplies = async () => {
                if (pending) return; pending = true;
                const controller = new AbortController(); replyRequests.add(controller);
                const target = new URL(messageUrl(room), location.origin); target.searchParams.set('reply', message.id);
                if (cursor) target.searchParams.set('cursor', cursor);
                body.setAttribute('aria-busy', 'true');
                try {
                    const data = await read(target, controller);
                    if (controller.signal.aborted || !details.isConnected) return;
                    if (!loaded) body.replaceChildren();
                    data.messages.sort((a,b) => a.time.localeCompare(b.time)).forEach(item => body.append(renderMessage(item, room, true)));
                    loaded = true; cursor = data.next_cursor;
                    if (!body.children.length) body.textContent = 'No replies yet.';
                    if (cursor) {
                        const next = node('button', 'm3e-button m3e-button--text', 'More replies'); next.type = 'button';
                        next.addEventListener('click', () => { next.remove(); loadReplies(); }); body.append(next);
                    }
                } catch (error) {
                    if (!controller.signal.aborted) { body.textContent = error.message; loaded = false; }
                } finally { pending = false; replyRequests.delete(controller); body.removeAttribute('aria-busy'); }
            };
            details.addEventListener('toggle', () => { if (details.open && !loaded) loadReplies(); }); row.append(details);
        }
        return row;
    };
    const loadMessages = async (append = false) => {
        if (!current) return;
        messageController?.abort(); replyRequests.forEach(controller => controller.abort());
        const controller = new AbortController(), room = current; messageController = controller;
        const target = new URL(messageUrl(room), location.origin);
        if (append && messageCursor) target.searchParams.set('cursor', messageCursor);
        loading.hidden = false; older.disabled = true; thread.setAttribute('aria-busy', 'true');
        status.textContent = 'Loading messages…';
        try {
            const data = await read(target, controller);
            if (messageController !== controller || current?.key !== room.key) return;
            if (!append) thread.replaceChildren();
            const known = new Set([...thread.children].map(row => row.dataset.messageId));
            const fragment = document.createDocumentFragment();
            data.messages.sort((a,b) => a.time.localeCompare(b.time)).forEach(message => { if (!known.has(message.id)) fragment.append(renderMessage(message, room)); });
            if (append) { const height = thread.scrollHeight; thread.prepend(fragment); thread.scrollTop += thread.scrollHeight - height; }
            else { thread.append(fragment); thread.scrollTop = thread.scrollHeight; }
            messageCursor = data.next_cursor; older.hidden = !messageCursor;
            status.textContent = thread.children.length ? `${thread.children.length} ${thread.children.length === 1 ? 'message' : 'messages'} loaded.` : 'No messages yet.';
        } catch (error) {
            if (messageController === controller) status.textContent = error.name === 'AbortError' ? 'Loading took too long. Try Refresh.' : error.message;
        } finally {
            if (messageController === controller) { loading.hidden = true; older.disabled = false; thread.removeAttribute('aria-busy'); }
        }
    };
    const choose = room => {
        keepDraft(); current = room; reply = null; messageCursor = null;
        list.querySelectorAll('button').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.key === room.key)));
        pane.querySelector('#teams-chat-title').textContent = room.name;
        thread.replaceChildren(); restoreDraft(); loadMessages();
    };
    const renderRooms = (data, append = false, preserve = false) => {
        listCursor = data.next_cursor; more.hidden = !listCursor;
        if (!append) { rooms = []; list.replaceChildren(); }
        for (const room of data.conversations) {
            if (rooms.some(item => item.key === room.key)) continue;
            rooms.push(room);
            const button = node('button', 'cm-teams-conversation m3e-state-layer'); button.type = 'button'; button.dataset.key = room.key;
            button.append(node('strong', '', room.name), node('small', '', room.detail));
            button.setAttribute('aria-pressed', String(current?.key === room.key)); button.addEventListener('click', () => choose(room)); list.append(button);
        }
        listStatus.textContent = rooms.length ? `${rooms.length} ${source.value === 'chats' ? 'chats' : 'channels'}.` : 'No conversations are available.';
        if (!append) {
            const previous = preserve && rooms.find(room => room.key === current?.key);
            if (previous || rooms[0]) choose(previous || rooms[0]);
            else { keepDraft(); current = null; thread.replaceChildren(); status.textContent = 'Choose another team or refresh.'; syncComposer(); }
        }
    };
    const loadList = async ({append = false, preserve = false, teamPage = false} = {}) => {
        keepDraft(); listController?.abort();
        if (!append && !preserve && !teamPage) {
            current = null; reply = null; messageController?.abort(); messageController = null;
            thread.replaceChildren(); field.value = ''; syncComposer();
            pane.querySelector('#teams-chat-title').textContent = 'Choose a conversation';
        }
        const controller = new AbortController(); listController = controller;
        more.disabled = true; moreTeams.disabled = true; listStatus.textContent = 'Loading conversations…';
        try {
            if (source.value === 'channels' && (!teams.value || teamPage)) {
                const data = await read(url('teams', teamPage ? teamCursor : null), controller);
                if (listController !== controller) return;
                if (!teamPage) teams.replaceChildren();
                data.conversations.forEach(team => { const option = node('option', '', team.name); option.value = team.key; teams.append(option); });
                teamCursor = data.next_cursor; moreTeams.hidden = !teamCursor;
                if (!teams.value) { renderRooms({conversations:[],next_cursor:null}); listStatus.textContent = 'No teams found for this account.'; return; }
                if (teamPage) return;
            }
            const data = await read(url(source.value, append ? listCursor : null, source.value === 'channels' ? teams.value : null), controller);
            if (listController === controller) renderRooms(data, append, preserve);
        } catch (error) {
            if (listController === controller) listStatus.textContent = error.name === 'AbortError' ? 'Loading took too long. Try Refresh.' : error.message;
        } finally { if (listController === controller) { more.disabled = false; moreTeams.disabled = false; } }
    };
    source.addEventListener('change', () => { pane.querySelector('#teams-team-picker').hidden = source.value !== 'channels'; teams.replaceChildren(); loadList(); });
    teams.addEventListener('change', () => loadList());
    more.addEventListener('click', () => loadList({append:true})); moreTeams.addEventListener('click', () => loadList({teamPage:true}));
    older.addEventListener('click', () => loadMessages(true));
    cancelReply.addEventListener('click', () => { keepDraft(); reply = null; restoreDraft(); field.focus(); });
    field.addEventListener('input', () => { keepDraft(); syncComposer(); });
    field.addEventListener('keydown', event => { if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) { event.preventDefault(); if (!send.disabled) form.requestSubmit(); } });
    form.addEventListener('submit', async event => {
        event.preventDefault(); if (sending || !current || !field.value.trim()) return;
        keepDraft(); const destination = draftKey(), room = current, text = field.value, replyId = reply;
        sending = true; syncComposer(); sendStatus.textContent = 'Sending message…';
        try {
            await read(messageUrl(room), new AbortController(), {method:'POST', body:new URLSearchParams({csrf_token:pane.dataset.csrf, text, ...(replyId ? {reply:replyId} : {})})});
            drafts.delete(destination);
            if (draftKey() === destination) { field.value = ''; sendStatus.textContent = 'Message sent.'; window.CentroMailMotion?.feedback(send, 'send'); loadMessages(); }
        } catch (error) {
            const warning = error.name === 'AbortError' ? 'Send confirmation took too long. Your draft is kept; check Teams before retrying.' : error.message;
            drafts.set(destination, {text, warning}); if (draftKey() === destination) sendStatus.textContent = warning;
        } finally { sending = false; syncComposer(); }
    });
    window.CentroMailTeams = {
        close() { keepDraft(); pane.hidden = true; listController?.abort(); messageController?.abort(); listController = messageController = null; replyRequests.forEach(controller => controller.abort()); loading.hidden = true; },
        open(data) { pane.hidden = false; source.value = 'chats'; pane.querySelector('#teams-team-picker').hidden = true; renderRooms(data, false, true); },
        refresh() { loadList({preserve:true}); },
    };
})();
