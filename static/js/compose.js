(() => {
    const composer = document.querySelector('#compose-window');
    if (!composer) return;
    const form = composer.querySelector('form');
    const title = composer.querySelector('#compose-title');
    const fields = form.elements;
    const send = form.querySelector('[type="submit"]');
    const sendLabel = send.innerHTML;
    let returnFocus;

    const clearDraft = () => {
        for (const name of ['to', 'subject', 'body', 'reply_id']) fields[name].value = '';
        title.textContent = 'New message';
    };
    const open = (trigger, reply) => {
        const replyId = reply ? trigger.dataset.replyId : '';
        if (fields.reply_id.value !== replyId) {
            if (fields.body.value.trim() && !confirm('Discard the current draft and start this message?')) return;
            clearDraft();
        }
        if (reply && !fields.reply_id.value) {
            fields.reply_id.value = replyId;
            fields.to.value = trigger.dataset.replyTo;
            fields.subject.value = trigger.dataset.replySubject;
            fields.account.value = trigger.dataset.replyAccount;
            fields.folder.value = trigger.dataset.replyFolder;
            title.textContent = 'Reply';
        }
        returnFocus = trigger;
        document.dispatchEvent(new Event('centromail:compose-open'));
        composer.showModal();
        fields[reply ? 'body' : 'to'].focus();
    };
    document.addEventListener('click', event => {
        const trigger = event.target.closest('#open-compose, [data-email-reply]');
        if (trigger) open(trigger, trigger.hasAttribute('data-email-reply'));
    });
    composer.querySelector('#close-compose').addEventListener('click', () => composer.close());
    composer.querySelector('#discard-compose').addEventListener('click', () => {
        clearDraft();
        composer.close();
    });
    composer.addEventListener('close', () => {
        const visible = returnFocus?.isConnected && returnFocus.getClientRects().length &&
            !returnFocus.closest('[inert]') && getComputedStyle(returnFocus).visibility !== 'hidden';
        const fallback = document.querySelector('.mobile-menu, #open-compose, .reader-back');
        (visible ? returnFocus : fallback)?.focus();
    });
    form.addEventListener('submit', () => {
        send.disabled = true;
        send.textContent = 'Sending…';
        form.setAttribute('aria-busy', 'true');
    });
    window.addEventListener('pageshow', () => {
        send.disabled = false;
        send.innerHTML = sendLabel;
        form.removeAttribute('aria-busy');
    });
    if (composer.hasAttribute('data-compose-draft')) {
        composer.showModal();
        fields.body.focus();
    }
})();
