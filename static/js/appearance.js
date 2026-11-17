(() => {
    const root = document.documentElement;
    const definitions = (window.CentroMailPreferenceGroups || []).flatMap(group => group.settings);
    const byKey = new Map(definitions.map(item => [item.key, item]));
    const valid = (item, value) => item.type === 'color' ? /^#[0-9a-f]{6}$/i.test(value) : item.type === 'switch' ? ['true', 'false'].includes(value) : item.choices.some(choice => choice.value === value);
    const get = key => {
        const item = byKey.get(key);
        if (!item) return null;
        let value; try { value = localStorage.getItem('centromail-' + key); } catch {}
        return valid(item, value) ? value : item.default;
    };
    const fontStacks = {
        system: '"Google Sans Flex", Roboto, system-ui, sans-serif', 'google-sans': '"Google Sans Flex", Roboto, system-ui, sans-serif',
        roboto: 'Roboto, system-ui, sans-serif', 'open-sans': '"Open Sans", system-ui, sans-serif', lato: 'Lato, system-ui, sans-serif',
        montserrat: 'Montserrat, system-ui, sans-serif', inter: 'Inter, system-ui, sans-serif', poppins: 'Poppins, system-ui, sans-serif',
        nunito: 'Nunito, system-ui, sans-serif', 'playfair-display': '"Playfair Display", Georgia, serif', merriweather: 'Merriweather, Georgia, serif',
    };
    const deviceTheme = matchMedia('(prefers-color-scheme: dark)');
    const apply = () => {
        for (const item of definitions) root.dataset['cm' + item.key.split('-').map(word => word[0].toUpperCase() + word.slice(1)).join('')] = get(item.key);
        const theme = get('theme'); root.dataset.theme = theme === 'system' ? (deviceTheme.matches ? 'dark' : 'light') : theme;
        root.dataset.corners = get('corners'); root.dataset.cmMotionStyle = get('motion-style');
        root.classList.toggle('reduce-motion', get('reduce-motion') === 'true');
        const variables = {'text-scale':'--cm-font-scale','line-height':'--cm-line-height','letter-spacing':'--cm-letter-spacing',
            'body-weight':'--cm-body-weight','heading-weight':'--cm-heading-weight','heading-scale':'--cm-heading-scale',
            'spacing':'--cm-spacing','content-width':'--cm-content-width','sidebar-width':'--cm-sidebar-width','card-padding':'--cm-card-padding',
            'border-width':'--cm-border-width','button-height':'--cm-button-height','icon-size':'--cm-icon-size','icon-fill':'--cm-icon-fill',
            'focus-width':'--cm-focus-width','motion-speed':'--cm-motion-speed','motion-intensity':'--cm-motion-intensity','loader-size':'--cm-loader-size',
            'reader-width':'--cm-reader-width','reader-text-size':'--cm-reader-text-size','reader-line-height':'--cm-reader-line-height','logo-size':'--cm-logo-size'};
        for (const [key, variable] of Object.entries(variables)) {
            const unit = ['content-width','sidebar-width','card-padding','border-width','button-height','icon-size','focus-width','loader-size','reader-width','reader-text-size'].includes(key) ? 'px' : key === 'letter-spacing' ? 'em' : '';
            root.style.setProperty(variable, get(key) + unit);
        }
        for (const token of ['default-spatial', 'default-effects', 'fast-spatial', 'fast-effects', 'slow-spatial', 'slow-effects']) {
            for (const field of ['duration', 'easing', 'damping-ratio', 'stiffness']) {
                root.style.setProperty(`--m3e-sys-motion-spring-${token}-${field}`, `var(--m3e-sys-motion-spring-${get('motion-style')}-${token}-${field})`);
            }
            const stiffness = parseFloat(getComputedStyle(root).getPropertyValue(`--m3e-sys-motion-spring-${get('motion-style')}-${token}-stiffness`));
            if (Number.isFinite(stiffness)) root.style.setProperty(`--m3e-sys-motion-spring-${token}-stiffness`, String(stiffness / Number(get('motion-speed')) ** 2));
        }
        for (const role of ['primary', 'primary-dim', 'surface-tint', 'on-primary']) root.style.removeProperty('--m3e-sys-color-' + role);
        const font = get('font'); root.style.setProperty('--cm-font-family', fontStacks[font]);
        if (!['system','google-sans'].includes(font) && !document.querySelector(`link[data-cm-font="${font}"]`)) {
            const link = document.createElement('link'); link.rel = 'stylesheet'; link.dataset.cmFont = font;
            link.href = `https://fonts.googleapis.com/css2?family=${font.split('-').map(word => word[0].toUpperCase()+word.slice(1)).join('+')}:wght@400;500;600;700&display=swap`; document.head.append(link);
        }
        document.querySelector('.gmail-app')?.classList.toggle('compact-mail', get('density') === 'compact');
        document.dispatchEvent(new Event('centromail-appearance-change'));
    };
    const set = (key, value) => {
        const item = byKey.get(key);
        if (!item || !valid(item, String(value))) throw new Error('Invalid preference: ' + key);
        localStorage.setItem('centromail-' + key, String(value)); apply();
    };
    const reset = keys => { keys.forEach(key => localStorage.removeItem('centromail-' + key)); apply(); };
    window.CentroMailAppearance = {apply, get, set, reset, valid, definitions};
    document.addEventListener('submit', event => {
        const form = event.target.closest('form[data-confirm]');
        if (form && get('confirm-actions') === 'true' && !confirm(form.dataset.confirm)) event.preventDefault();
    }, true);
    deviceTheme.addEventListener('change', () => { if (get('theme') === 'system') apply(); });
    window.addEventListener('storage', event => { if (event.key === null || event.key.startsWith('centromail-')) apply(); });
    document.addEventListener('DOMContentLoaded', () => {
        apply();
        document.querySelectorAll('.flash').forEach(notice => {
            const close = document.createElement('button'); close.className = 'm3e-icon-button m3e-icon-button--standard'; close.type = 'button'; close.setAttribute('aria-label','Dismiss notification');
            close.innerHTML = '<span class="m3e-icon" aria-hidden="true">close</span>'; close.addEventListener('click', () => notice.remove()); notice.append(close);
            const seconds = Number(get('notice-duration'));
            if (seconds && !notice.classList.contains('flash-error')) setTimeout(() => notice.remove(), seconds * 1000);
        });
    });
    apply();
})();
