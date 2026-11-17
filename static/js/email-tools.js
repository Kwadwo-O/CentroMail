(() => {
    const status = document.createElement('p');
    status.className = 'sr-only';
    status.setAttribute('role', 'status');
    document.body.append(status);
    const pendingReads = new WeakSet();
    const markOpenedEmails = () => document.querySelectorAll('[data-mark-email-read="true"]').forEach(async article => {
        if (pendingReads.has(article) || article.closest('[hidden], details:not([open])')) return;
        pendingReads.add(article);
        try {
            const response = await fetch(article.dataset.readUrl, {method:'POST',body:new URLSearchParams({
                action:'read',account:article.dataset.readAccount,folder:article.dataset.readFolder,
                message_ids:article.dataset.readMessageId,csrf_token:article.dataset.readCsrf,
            })});
            if (response.redirected) { location.assign(response.url); return; }
            if (!response.ok) throw new Error('Read status could not be saved.');
            article.dataset.markEmailRead = 'false';
            article.closest('details')?.querySelector('.conversation-unread')?.remove();
            document.querySelectorAll('.message').forEach(row => {
                const account = row.dataset.mailAccount || document.querySelector('.gmail-app')?.dataset.account;
                if (row.dataset.messageId !== article.dataset.readMessageId || account !== article.dataset.readAccount) return;
                row.classList.remove('unread');
                row.querySelector('.message-read-state').textContent = '';
            });
            document.dispatchEvent(new CustomEvent('centromail-mail-read', {detail:{account:article.dataset.readAccount}}));
            status.textContent = 'Email marked as read.';
        } catch {
            const warning = document.createElement('p'); warning.className = 'reply-unavailable'; warning.setAttribute('role','status');
            warning.textContent = 'Email opened, but its read status could not be saved. Use Mark as read in the inbox to try again.';
            article.querySelector('.reader-actions').append(warning);
        }
    });
    markOpenedEmails();
    new MutationObserver(markOpenedEmails).observe(document.body, {childList:true,subtree:true});
    const pendingConversations = new WeakSet();
    const loadConversation = async section => {
        if (pendingConversations.has(section)) return;
        pendingConversations.add(section);
        const current = section.querySelector('.reader-message');
        const notice = document.createElement('p');
        notice.className = 'conversation-status'; notice.setAttribute('role', 'status');
        notice.textContent = 'Loading conversation…';
        section.querySelector('.conversation-status')?.remove(); section.prepend(notice);
        try {
            const response = await fetch(section.dataset.conversationUrl, {signal:AbortSignal.timeout(25000)});
            if (response.redirected) { location.assign(response.url); return; }
            if (!response.ok) throw new Error('Conversation unavailable');
            const data = await response.json();
            if (!section.isConnected) return;
            if (!data.html) { notice.remove(); return; }
            const fragment = document.createRange().createContextualFragment(data.html);
            const scroller = section.closest('.reader-content');
            const preservePosition = scroller ? scroller.scrollTop > 0 : window.scrollY > 0;
            const previousTop = current.getBoundingClientRect().top;
            fragment.querySelector('[data-current-message]').replaceWith(current);
            section.replaceChildren(fragment);
            const delta = current.getBoundingClientRect().top - previousTop;
            if (scroller) scroller.scrollTop = preservePosition ? scroller.scrollTop + delta : 0;
            else if (preservePosition) window.scrollBy({top:delta, behavior:'instant'});
        } catch {
            if (!section.isConnected) return;
            pendingConversations.delete(section);
            notice.textContent = 'Conversation could not be loaded. ';
            const retry = document.createElement('button');
            retry.type = 'button'; retry.className = 'm3e-button m3e-button--text';
            retry.dataset.retryConversation = ''; retry.textContent = 'Retry'; notice.append(retry);
        }
    };
    const loadConversations = () => document.querySelectorAll('[data-conversation-url]').forEach(section => {
        if (!section.querySelector('[data-retry-conversation]')) loadConversation(section);
    });
    const pendingMessages = new WeakSet();
    const loadConversationMessage = async details => {
        if (!details.open || pendingMessages.has(details)) return;
        if (!details.dataset.conversationMessageUrl) return;
        pendingMessages.add(details);
        const body = details.querySelector('.conversation-body');
        body.textContent = 'Loading email…'; body.setAttribute('aria-busy', 'true');
        try {
            const response = await fetch(details.dataset.conversationMessageUrl, {signal:AbortSignal.timeout(25000)});
            if (response.redirected) { location.assign(response.url); return; }
            if (!response.ok) throw new Error('Email unavailable');
            const html = await response.text();
            if (!details.isConnected) return;
            body.replaceChildren(document.createRange().createContextualFragment(html));
        } catch {
            if (!details.isConnected) return;
            pendingMessages.delete(details);
            body.textContent = 'Email could not be loaded. ';
            const retry = document.createElement('button');
            retry.type = 'button'; retry.className = 'm3e-button m3e-button--text';
            retry.dataset.retryConversationMessage = ''; retry.textContent = 'Retry'; body.append(retry);
        } finally { body.removeAttribute('aria-busy'); }
    };
    document.addEventListener('toggle', event => {
        if (!event.target.matches('[data-conversation-message]')) return;
        loadConversationMessage(event.target); markOpenedEmails();
    }, true);
    document.addEventListener('click', event => {
        const display = event.target.closest('[data-expand-conversation], [data-collapse-conversation]');
        if (display) {
            const expanded = display.hasAttribute('data-expand-conversation');
            display.closest('[data-conversation-url]').querySelectorAll('[data-conversation-message]').forEach(details => {
                details.open = expanded;
                if (expanded) loadConversationMessage(details);
            });
            markOpenedEmails();
        }
        if (event.target.closest('[data-retry-conversation]')) loadConversation(event.target.closest('[data-conversation-url]'));
        if (event.target.closest('[data-retry-conversation-message]')) loadConversationMessage(event.target.closest('details'));
    });
    loadConversations();
    new MutationObserver(loadConversations).observe(document.body, {childList:true,subtree:true});
    document.addEventListener('click', async event => {
        const button = event.target.closest('[data-copy-code]');
        if (!button) return;
        const value = button.dataset.copyCode;
        try {
            if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(value);
            else {
                const field = document.createElement('textarea');
                field.value = value;
                field.style.cssText = 'position:fixed;opacity:0;pointer-events:none';
                document.body.append(field);
                field.select();
                const copied = document.execCommand('copy');
                field.remove();
                button.focus({preventScroll:true});
                if (!copied) throw new Error('Copy unavailable');
            }
            status.textContent = 'Verification code copied.';
            const icon = button.querySelector('.m3e-icon');
            icon.textContent = 'check';
            setTimeout(() => { if (icon.isConnected) icon.textContent = 'content_copy'; }, 1800);
        } catch {
            status.textContent = 'Could not copy automatically. Select the code and copy it.';
            const code = button.querySelector('code');
            const range = document.createRange();
            range.selectNodeContents(code);
            getSelection().removeAllRanges();
            getSelection().addRange(range);
        }
    });
})();
