(() => {
    const pane = document.querySelector('#google-chat-workspace');
    if (!pane) return;
    const workspace = document.querySelector('#workspace-apps');
    const list = pane.querySelector('#google-chat-conversations'), select = pane.querySelector('#google-chat-select');
    const thread = pane.querySelector('#google-chat-thread'), status = pane.querySelector('#google-chat-status');
    const form = pane.querySelector('#google-chat-send-form'), field = pane.querySelector('#google-chat-text');
    const file = pane.querySelector('#google-chat-file'), send = pane.querySelector('#google-chat-send'), sendStatus = pane.querySelector('#google-chat-send-status');
    const replyStatus = pane.querySelector('#google-chat-reply-status'), cancelReply = pane.querySelector('#google-chat-cancel-reply');
    const older = pane.querySelector('#google-chat-older'), more = pane.querySelector('#google-chat-more-spaces');
    const dialog = pane.querySelector('#google-chat-action-dialog'), actionForm = pane.querySelector('#google-chat-action-form');
    const actionStatus = pane.querySelector('#google-chat-action-status'), actionSave = pane.querySelector('#google-chat-action-save');
    const edit = pane.querySelector('#google-chat-edit'), emoji = pane.querySelector('#google-chat-emoji');
    const newDialog = pane.querySelector('#google-chat-new-dialog'), newForm = pane.querySelector('#google-chat-new-form');
    const newStatus = pane.querySelector('#google-chat-new-status'), newSave = pane.querySelector('#google-chat-new-save');
    const drafts = new Map();
    let rooms = [], current, controller, poll, nextOlder, nextSpaces, incomingCursor, latest, sending = false, actionContext, actionBusy = false, creating = false, createId;
    const identity = () => [...crypto.getRandomValues(new Uint8Array(16))].map(value => value.toString(16).padStart(2,'0')).join('');
    const active = () => !pane.hidden && !workspace.hidden && !document.hidden;
    const messageUrl = id => pane.dataset.spacesUrl + '/' + encodeURIComponent(id.split('/')[1]) + '/messages';
    const draft = () => drafts.get(current?.id) || {};
    const saveDraft = changes => { if (current) drafts.set(current.id, {...draft(), ...changes, requestId:identity()}); syncComposer(); };
    const read = async (url, options = {}) => {
        const response = await fetch(url, options);
        if (response.redirected) { location.assign(response.url); throw new Error('Sign in again.'); }
        if (!response.headers.get('Content-Type')?.includes('application/json')) throw new Error('Google Chat could not confirm the request. Keep your draft and try Refresh.');
        const data = await response.json(); if (!response.ok) throw new Error(data.error || 'Google Chat is unavailable. Try Refresh.'); return data;
    };
    const syncComposer = () => {
        const value = draft();
        field.disabled = file.disabled = !current || sending;
        send.disabled = !current || sending || !(field.value.trim() || value.file);
        send.setAttribute('aria-busy',String(sending)); send.querySelector('[data-google-chat-send-label]').textContent = sending ? 'Sending…' : 'Send message';
        replyStatus.hidden = cancelReply.hidden = !value.reply;
        replyStatus.textContent = value.reply ? `Replying to ${value.reply.sender}: ${value.reply.text || 'Attachment'}` : '';
        pane.querySelector('#google-chat-file-status').textContent = value.file ? value.file.name : '';
        pane.querySelector('#google-chat-remove-file').hidden = !value.file;
        pane.querySelector('#google-chat-remove-file').disabled = cancelReply.disabled = sending;
    };
    const schedule = () => { clearTimeout(poll); if (active() && current && !sending) poll = setTimeout(() => loadMessages(), incomingCursor ? 0 : 10000); };
    const apply = (room, data) => {
        if (current?.id !== room) return;
        if (data.deleted) {
            thread.querySelector(`[data-google-message="${CSS.escape(data.id)}"]`)?.remove();
            if (draft().reply?.id === data.id) saveDraft({reply:null});
        } else if (data.message) render([data.message]);
    };
    const openAction = (action, message) => {
        actionContext = {room:current.id, action, id:message.id, original:message.text};
        pane.querySelector('#google-chat-action-title').textContent = {edit:'Edit message',reaction:'React to message',delete:'Delete message'}[action];
        pane.querySelector('#google-chat-edit-fields').hidden = action !== 'edit';
        pane.querySelector('#google-chat-reaction-fields').hidden = action !== 'reaction';
        pane.querySelector('#google-chat-delete-fields').hidden = action !== 'delete';
        pane.querySelector('#google-chat-delete-replies').checked = false;
        edit.value = message.text; emoji.value = ''; actionStatus.textContent = ''; actionSave.disabled = false; actionSave.textContent = action === 'delete' ? 'Delete' : 'Save changes';
        dialog.showModal(); (action === 'edit' ? edit : action === 'reaction' ? emoji : actionSave).focus();
    };
    const render = (messages, prepend = false) => {
        const height = thread.scrollHeight, top = thread.scrollTop, bottom = height - top - thread.clientHeight < 80;
        const focused = document.activeElement;
        for (const message of messages) {
            if (message.deleted) { apply(current.id, {deleted:true,id:message.id}); continue; }
            let row = thread.querySelector(`[data-google-message="${CSS.escape(message.id)}"]`);
            if (row && JSON.stringify(row.chatMessage) === JSON.stringify(message)) continue;
            if (!row) {
                row = document.createElement('article'); row.className = 'apps-feed-message google-chat-message'; row.dataset.googleMessage = message.id;
                for (const tag of ['strong','time','p']) row.append(document.createElement(tag));
                thread.append(row);
            }
            row.chatMessage = message; row.classList.toggle('is-outgoing',message.outgoing); row.dataset.time = message.time;
            row.querySelector('strong').textContent = message.sender;
            row.querySelector('time').textContent = message.time ? new Date(message.time).toLocaleString() : '';
            row.querySelector('p').textContent = message.text;
            row.querySelector('.chat-message-footer')?.remove(); row.querySelector('.google-chat-attachments')?.remove();
            const attachments = document.createElement('div'); attachments.className = 'google-chat-attachments';
            for (const attachment of message.attachments || []) if (attachment.url) { const link = document.createElement('a'); link.className = 'm3e-button m3e-button--text'; link.href = attachment.url; link.textContent = attachment.name; link.target = '_blank'; link.rel = 'noreferrer'; attachments.append(link); }
            row.append(attachments);
            const footer = document.createElement('div'); footer.className = 'chat-message-footer';
            const meta = document.createElement('small'); meta.className = 'chat-message-meta'; meta.textContent = [message.updated ? 'Edited' : '',message.thread_reply ? 'Thread reply' : '',...(message.reactions || []).map(item => `${item.emoji} ${item.count}`)].filter(Boolean).join(' · '); footer.append(meta);
            const button = document.createElement('button'); button.type = 'button'; button.className = 'm3e-icon-button m3e-icon-button--standard'; button.id = 'google-chat-actions-' + message.id.split('/messages/')[1]; button.setAttribute('aria-label','Actions for message from ' + message.sender);
            const icon = document.createElement('span'); icon.className = 'm3e-icon'; icon.setAttribute('aria-hidden','true'); icon.textContent = 'more_horiz'; button.append(icon);
            const menu = document.createElement('m3e-menu'); menu.setAttribute('anchor',button.id); menu.setAttribute('label','Message actions');
            for (const [action,title,available] of [['reply','Reply',true],['copy','Copy text',Boolean(message.text)],['reaction','React',true],['edit','Edit',message.can_edit],['delete','Delete',message.can_delete]]) if (available) { const item = document.createElement('m3e-menu-item'); item.setAttribute('value',action); item.textContent = title; menu.append(item); }
            menu.addEventListener('action', async event => {
                const value = row.chatMessage, action = event.detail.value;
                if (action === 'reply') { saveDraft({reply:{id:value.id,sender:value.sender,text:value.text}}); field.focus(); }
                else if (action === 'copy') { try { await navigator.clipboard.writeText(value.text); status.textContent = 'Copied to clipboard.'; window.CentroMailMotion?.feedback(button,'copy'); } catch { status.textContent = 'Could not copy. Select the message text and copy it.'; } }
                else openAction(action,value);
            });
            footer.append(button,menu); row.append(footer);
        }
        const ordered = [...thread.children].sort((a,b) => a.dataset.time.localeCompare(b.dataset.time) || a.dataset.googleMessage.localeCompare(b.dataset.googleMessage));
        ordered.forEach((row,index) => { if (thread.children[index] !== row) thread.insertBefore(row,thread.children[index] || null); });
        if (thread.contains(focused) && document.activeElement !== focused) focused.focus({preventScroll:true});
        if (prepend) thread.scrollTop = top + thread.scrollHeight - height;
        else if (bottom) thread.scrollTop = thread.scrollHeight;
    };
    const loadMessages = async ({reset = false, before = null} = {}) => {
        if (!current || !active() || (controller && !reset)) return;
        clearTimeout(poll); controller?.abort(); const pending = new AbortController(); controller = pending;
        const room = current.id, timeout = setTimeout(() => pending.abort(),30000);
        if (reset) { thread.replaceChildren(); latest = incomingCursor = nextOlder = null; status.textContent = 'Loading messages…'; }
        thread.setAttribute('aria-busy','true'); older.disabled = true;
        const url = new URL(messageUrl(room),location.origin);
        if (before) url.searchParams.set('cursor',before);
        else if (!reset) {
            if (incomingCursor) url.searchParams.set('cursor',incomingCursor);
            else if (latest) url.searchParams.set('after',latest);
            const known = [...thread.children].slice(-50).map(row => row.dataset.googleMessage.split('/messages/')[1]);
            if (known.length) url.searchParams.set('known_ids',known.join(','));
        }
        try {
            const data = await read(url,{signal:pending.signal}); if (controller !== pending || current?.id !== room) return;
            render(data.messages || [],Boolean(before)); render(data.updated_messages || []);
            for (const message of data.messages || []) if (!latest || message.time > latest) latest = message.time;
            if (reset || before) nextOlder = data.next_cursor;
            else incomingCursor = data.incoming_page ? data.next_cursor : null;
            older.hidden = !nextOlder; status.textContent = thread.children.length ? 'Up to date · Checks for new messages every 10 seconds.' : 'No messages yet.';
        } catch (error) { if (controller === pending) status.textContent = error.name === 'AbortError' ? 'Loading took too long. Try Refresh.' : error.message; }
        finally { clearTimeout(timeout); if (controller === pending) { controller = null; thread.removeAttribute('aria-busy'); older.disabled = false; schedule(); } }
    };
    const choose = id => {
        current = rooms.find(room => room.id === id); if (!current) return;
        select.value = id; list.querySelectorAll('button').forEach(button => button.setAttribute('aria-pressed',String(button.dataset.room === id)));
        pane.querySelector('#google-chat-title').textContent = current.name;
        const open = pane.querySelector('#google-chat-open'); open.href = current.url; open.hidden = false;
        field.value = draft().text || ''; file.value = ''; syncComposer(); sendStatus.textContent = 'Enter adds a line break. Ctrl or ⌘ + Enter sends.'; loadMessages({reset:true});
    };
    const renderRooms = (data, append = false) => {
        if (!append) { rooms = []; list.replaceChildren(); select.replaceChildren(); }
        for (const room of data.conversations || []) if (!rooms.some(item => item.id === room.id)) {
            rooms.push(room); const button = document.createElement('button'); button.type = 'button'; button.className = 'cm-teams-conversation m3e-button m3e-button--text m3e-button--square'; button.dataset.room = room.id; button.textContent = room.name; button.setAttribute('aria-pressed',String(current?.id === room.id)); button.addEventListener('click',() => choose(room.id)); list.append(button);
            const option = document.createElement('option'); option.value = room.id; option.textContent = room.name; select.append(option);
        }
        nextSpaces = data.next_cursor; more.hidden = !nextSpaces;
    };
    field.addEventListener('input',() => saveDraft({text:field.value}));
    field.addEventListener('keydown',event => { if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) { event.preventDefault(); if (!send.disabled) form.requestSubmit(); } });
    file.addEventListener('change',() => { if (file.files[0]?.size > 64 * 1024 * 1024) { file.value = ''; sendStatus.textContent = 'Choose a file of up to 64 MB.'; return; } saveDraft({file:file.files[0] || null,attachmentToken:null}); });
    cancelReply.addEventListener('click',() => { saveDraft({reply:null}); field.focus(); });
    pane.querySelector('#google-chat-remove-file').addEventListener('click',() => { file.value = ''; saveDraft({file:null,attachmentToken:null}); });
    select.addEventListener('change',() => choose(select.value)); older.addEventListener('click',() => loadMessages({before:nextOlder}));
    more.addEventListener('click',async () => {
        more.disabled = true; const pending = new AbortController(), timeout = setTimeout(() => pending.abort(),30000);
        try { const url = new URL(pane.dataset.spacesUrl,location.origin); url.searchParams.set('cursor',nextSpaces); renderRooms(await read(url,{signal:pending.signal}),true); }
        catch (error) { status.textContent = error.name === 'AbortError' ? 'Loading took too long. Try again.' : error.message; }
        finally { clearTimeout(timeout); more.disabled = false; }
    });
    form.addEventListener('submit',async event => {
        event.preventDefault(); if (send.disabled || sending || !current) return;
        if (!draft().requestId) saveDraft({text:field.value});
        const room = current.id, value = draft(); sending = true; clearTimeout(poll); syncComposer(); sendStatus.textContent = 'Sending message…';
        const pending = new AbortController(), timeout = setTimeout(() => pending.abort(),90000);
        try {
            if (value.file && !value.attachmentToken) {
                sendStatus.textContent = 'Uploading attachment…'; const body = new FormData(); body.append('file',value.file); body.append('csrf_token',pane.dataset.csrf);
                const attachment = await read(messageUrl(room).replace(/\/messages$/,'/attachments'),{method:'POST',body,signal:pending.signal}); value.attachmentToken = attachment.attachment_token;
            }
            const data = await read(messageUrl(room),{method:'POST',signal:pending.signal,body:new URLSearchParams({text:value.text || '',request_id:value.requestId,reply:value.reply?.id || '',attachment_token:value.attachmentToken || '',csrf_token:pane.dataset.csrf})});
            if (drafts.get(room) === value) drafts.delete(room);
            if (current?.id === room) { field.value = draft().text || ''; file.value = ''; apply(room,data); sendStatus.textContent = 'Message sent.'; window.CentroMailMotion?.feedback(send,'send'); loadMessages(); }
        } catch (error) { if (current?.id === room) sendStatus.textContent = error.name === 'AbortError' ? 'Send confirmation took too long. Your draft and attachment are kept; Refresh before retrying.' : error.message; }
        finally { clearTimeout(timeout); sending = false; syncComposer(); schedule(); }
    });
    pane.querySelectorAll('[data-google-chat-emoji]').forEach(button => button.addEventListener('click',() => { emoji.value = button.dataset.googleChatEmoji; }));
    pane.querySelector('#google-chat-action-cancel').addEventListener('click',() => { if (!actionBusy) dialog.close(); });
    dialog.addEventListener('cancel',event => { if (actionBusy) event.preventDefault(); });
    actionForm.addEventListener('submit',async event => {
        event.preventDefault(); if (actionBusy || !actionContext) return;
        const context = actionContext; actionBusy = true; actionSave.disabled = true; actionForm.setAttribute('aria-busy','true'); actionStatus.textContent = 'Applying changes…';
        actionForm.querySelectorAll('input,textarea,button').forEach(element => { element.disabled = true; });
        const pending = new AbortController(), timeout = setTimeout(() => pending.abort(),30000);
        try {
            const url = messageUrl(context.room) + '/' + encodeURIComponent(context.id.split('/messages/')[1]) + '/actions';
            const data = await read(url,{method:'POST',signal:pending.signal,body:new URLSearchParams({action:context.action,text:edit.value,original:context.original,emoji:emoji.value.trim(),force:String(pane.querySelector('#google-chat-delete-replies').checked),csrf_token:pane.dataset.csrf})});
            apply(context.room,data); dialog.close(); if (current?.id === context.room) status.textContent = data.deleted ? 'Message deleted.' : 'Message updated.';
        } catch (error) { actionStatus.textContent = error.name === 'AbortError' ? 'The action was not confirmed. Your edit is kept; Refresh before retrying.' : error.message; }
        finally { clearTimeout(timeout); actionBusy = false; actionForm.querySelectorAll('input,textarea,button').forEach(element => { element.disabled = false; }); actionForm.removeAttribute('aria-busy'); }
    });
    pane.querySelector('#google-chat-new').addEventListener('click',() => { createId = identity(); newStatus.textContent = ''; newDialog.showModal(); pane.querySelector('#google-chat-new-members').focus(); });
    pane.querySelector('#google-chat-new-kind').addEventListener('change',event => { const named = event.target.value === 'SPACE'; pane.querySelector('#google-chat-new-name').hidden = pane.querySelector('#google-chat-new-name-label').hidden = !named; });
    for (const element of newForm.querySelectorAll('input,select')) element.addEventListener('input',() => { createId = identity(); });
    pane.querySelector('#google-chat-new-cancel').addEventListener('click',() => { if (!creating) newDialog.close(); });
    newDialog.addEventListener('cancel',event => { if (creating) event.preventDefault(); });
    newForm.addEventListener('submit',async event => {
        event.preventDefault(); if (creating) return; creating = true; newSave.disabled = true; newStatus.textContent = 'Creating conversation…';
        newForm.querySelectorAll('input,select,button').forEach(element => { element.disabled = true; });
        const pending = new AbortController(), timeout = setTimeout(() => pending.abort(),30000);
        try {
            const data = await read(pane.dataset.spacesUrl,{method:'POST',signal:pending.signal,body:new URLSearchParams({kind:pane.querySelector('#google-chat-new-kind').value,title:pane.querySelector('#google-chat-new-name').value,members:pane.querySelector('#google-chat-new-members').value,request_id:createId,csrf_token:pane.dataset.csrf})});
            const cursor = nextSpaces; renderRooms({conversations:[data.conversation],next_cursor:cursor},true); newDialog.close(); choose(data.conversation.id);
        } catch (error) { newStatus.textContent = error.name === 'AbortError' ? 'Creation was not confirmed. Refresh the conversation list before retrying.' : error.message; }
        finally { clearTimeout(timeout); creating = false; newForm.querySelectorAll('input,select,button').forEach(element => { element.disabled = false; }); }
    });
    const visibility = () => { if (!active()) { clearTimeout(poll); controller?.abort(); controller = null; thread.removeAttribute('aria-busy'); } else loadMessages(); };
    document.addEventListener('visibilitychange',visibility); new MutationObserver(visibility).observe(workspace,{attributes:true,attributeFilter:['hidden']});
    window.CentroMailGoogleChat = {
        close() { pane.hidden = true; if (!actionBusy) dialog.close(); if (!creating) newDialog.close(); clearTimeout(poll); controller?.abort(); controller = null; },
        open(data) { pane.hidden = false; renderRooms(data); if (rooms.length) choose(rooms.some(room => room.id === current?.id) ? current.id : rooms[0].id); else { current = null; thread.replaceChildren(); syncComposer(); status.textContent = 'No conversations yet. Start a new conversation.'; } },
        refresh() { loadMessages({reset:true}); },
    };
})();
