(() => {
    const form = document.getElementById('signupForm');
    if (!form) return;
    const password = form.elements.password;
    const confirmation = form.elements.confirm_password;
    const rulesList = document.getElementById('passwordRules');
    const guide = document.getElementById('passwordGuide');
    const progress = document.getElementById('passwordProgress');
    const touched = new Set();
    const commonPasswords = new Set(['password','password1','password12','password123','password1234','passw0rd','p@ssw0rd','p@ssword','passwort','motdepasse','contrasena','123456','1234567','12345678','123456789','1234567890','123456789a','qwerty','qwerty123','qwertyuiop','abc123','abcd1234','letmein','letmein123','welcome','welcome1','welcome123','admin','admin123','administrator','iloveyou','sunshine','monkey','dragon','football','baseball','princess','trustno1','master','shadow','superman','batman','starwars','whatever','freedom','changeme','secret','login','access','flower','hello123','charlie','donald','hunter2']);
    const rules = {
        length: value => [...value].length >= 12 && [...value].length <= 1024,
        uppercase: value => /[A-Z]/.test(value),
        digit: value => /[0-9]/.test(value),
        special: value => /[^A-Za-z0-9]/.test(value),
        common: value => {
            const lowered = value.toLowerCase();
            return !commonPasswords.has(lowered) && !commonPasswords.has(lowered.replace(/^[^a-z]+|[^a-z]+$/g, ''));
        },
        personal: value => [form.elements.name.value.trim(), form.elements.email.value.trim().split('@')[0]]
            .every(token => [...token].length < 4 || !value.toLowerCase().includes(token.toLowerCase())),
    };
    const messages = {
        length: 'Use between 12 and 1024 characters for your password.',
        uppercase: 'Your password needs at least one uppercase letter.',
        digit: 'Your password needs at least one number.',
        special: 'Your password needs at least one special character.',
        common: 'That password is too common. Choose something harder to guess.',
        personal: 'Do not include your name or email address in your password.',
    };
    const renderError = (input, message) => {
        const error = document.getElementById(input.id + 'Error');
        error.textContent = touched.has(input) ? message : '';
        error.hidden = !error.textContent;
        input.setAttribute('aria-invalid', String(!error.hidden));
        input.closest('.m3e-text-field').classList.toggle('m3e-text-field--error', !error.hidden);
    };
    const update = () => {
        const value = password.value;
        let passwordError = '';
        let met = 0;
        for (const [rule, test] of Object.entries(rules)) {
            const passed = test(value);
            if (!passed && !passwordError) passwordError = messages[rule];
            const item = rulesList.querySelector(`[data-rule="${rule}"]`);
            const satisfied = Boolean(value) && passed;
            item.classList.toggle('is-met', satisfied);
            item.querySelector('[data-rule-icon]').textContent = satisfied ? 'check_circle' : 'cancel';
            item.querySelector('[data-rule-state]').textContent = satisfied ? 'Met' : 'Needed';
            const segment = progress.querySelector(`[data-rule-segment="${rule}"]`);
            if (segment) {
                segment.classList.toggle('is-met', satisfied);
                if (satisfied) met++;
            } else {
                item.hidden = !value || passed;
            }
        }
        progress.setAttribute('aria-valuenow', String(met));
        progress.setAttribute('aria-valuetext', `${met} of 4 core password requirements met`);
        password.setCustomValidity(passwordError);
        renderError(password, passwordError);
        const confirmationError = !confirmation.value ? 'Confirm your password.' :
            confirmation.value !== value ? 'Passwords must match.' : '';
        confirmation.setCustomValidity(confirmationError);
        renderError(confirmation, confirmationError);
    };
    const showGuide = () => { guide.hidden = false; };
    for (const type of ['focus', 'input', 'invalid']) password.addEventListener(type, showGuide);
    for (const input of [password, confirmation]) {
        input.addEventListener('input', update);
        for (const type of ['blur', 'invalid']) {
            input.addEventListener(type, () => { touched.add(input); update(); });
        }
    }
    for (const input of [form.elements.name, form.elements.email]) input.addEventListener('input', update);
    form.addEventListener('submit', event => {
        update();
        const firstInvalid = [password, confirmation].find(input => !input.checkValidity());
        if (firstInvalid) {
            event.preventDefault();
            firstInvalid.focus();
        }
    });
    window.addEventListener('pageshow', update);
    update();
})();
