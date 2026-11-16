(() => {
    const status = document.createElement('p');
    status.className = 'sr-only';
    status.setAttribute('role', 'status');
    document.body.append(status);
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
