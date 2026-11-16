(() => {
    const status = document.createElement('p');
    status.className = 'sr-only';
    status.setAttribute('role', 'status');
    document.body.append(status);
    const pendingReads = new WeakSet();
    const markOpenedEmails = () => document.querySelectorAll('[data-mark-email-read="true"]').forEach(async article => {
        if (pendingReads.has(article) || article.closest('[hidden]')) return;
        pendingReads.add(article);
        try {
            const response = await fetch(article.dataset.readUrl, {method:'POST',body:new URLSearchParams({
                action:'read',account:article.dataset.readAccount,folder:article.dataset.readFolder,
                message_ids:article.dataset.readMessageId,csrf_token:article.dataset.readCsrf,
            })});
            if (response.redirected) { location.assign(response.url); return; }
            if (!response.ok) throw new Error('Read status could not be saved.');
            article.dataset.markEmailRead = 'false';
            document.querySelectorAll('.message').forEach(row => {
                if (row.dataset.messageId !== article.dataset.readMessageId) return;
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
