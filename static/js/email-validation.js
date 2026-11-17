(() => {
    document.querySelectorAll('input[type="email"]').forEach(input => {
        const error = document.getElementById(input.getAttribute('aria-describedby'));
        if (!error) return;
        const field = input.closest('.m3e-text-field');
        let touched = input.getAttribute('aria-invalid') === 'true';
        const display = message => {
            error.textContent = message;
            error.hidden = !message;
            input.setAttribute('aria-invalid', String(Boolean(message)));
            field?.classList.toggle('m3e-text-field--error', Boolean(message));
        };
        const validate = (show = false) => {
            input.setCustomValidity('');
            const address = input.value.trim();
            const [local = '', domain = ''] = address.split('@');
            let message = '';
            if (!address && input.required) {
                message = 'Enter an email address.';
            } else if (address && (input.validity.typeMismatch || address.length > 254 ||
                local.length > 64 || local.startsWith('.') || local.endsWith('.') ||
                local.includes('..') || !domain.includes('.'))) {
                message = 'Enter a valid email address, such as name@example.com.';
            }
            input.setCustomValidity(message);
            if (show) display(message);
        };
        input.addEventListener('input', () => validate(touched));
        for (const event of ['blur', 'invalid']) {
            input.addEventListener(event, () => {
                if (event === 'blur' && input.closest('dialog:not([open])')) return;
                touched = true;
                validate(true);
            });
        }
        input.addEventListener('centromail:email-reset', () => {
            touched = false;
            display('');
            validate();
        });
        validate();
    });
})();
