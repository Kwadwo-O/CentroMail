(() => {
    const appearance = window.CentroMailAppearance;
    const feedback = document.querySelector('#settings-feedback');
    if (!feedback) return;
    const groups = window.CentroMailPreferenceGroups;
    const controls = [...document.querySelectorAll('[data-preference]')];
    const sync = () => {
        controls.forEach(control => { const value = appearance.get(control.dataset.preference); if (control.type === 'checkbox') control.checked = value === 'true'; else control.value = value; });
        document.querySelectorAll('[data-accent]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.accent === appearance.get('accent'))));
    };
    const change = action => { try { action(); sync(); feedback.textContent = 'Preferences saved on this browser.'; } catch (error) { feedback.textContent = 'Could not save preferences: ' + error.message; } };
    controls.forEach(control => control.addEventListener(control.type === 'color' ? 'input' : 'change', () => change(() => appearance.set(control.dataset.preference, control.type === 'checkbox' ? String(control.checked) : control.value))));
    document.querySelectorAll('[data-accent]').forEach(button => button.addEventListener('click', () => change(() => appearance.set('accent', button.dataset.accent))));
    const sections = [...document.querySelectorAll('[data-settings-section]')];
    const links = [...document.querySelectorAll('[data-settings-nav]')];
    const search = document.querySelector('#settings-search');
    const clearSearch = document.querySelector('#clear-settings-search');
    const categoryMenu = document.querySelector('#settings-category-menu');
    const categoryButton = document.querySelector('#settings-category-button');
    const mobileSettings = matchMedia('(max-width: 900px)');
    const preview = document.querySelector('.settings-preview');
    const page = document.querySelector('.settings-page');
    const header = document.querySelector('.site-header');
    const syncHeader = () => page.style.setProperty('--settings-header-offset', getComputedStyle(header).position === 'sticky' ? header.getBoundingClientRect().height + 'px' : '0px');
    new ResizeObserver(syncHeader).observe(header);
    document.addEventListener('centromail-appearance-change', syncHeader);
    syncHeader();
    const syncLayout = () => {
        preview.open = !mobileSettings.matches;
        if (!mobileSettings.matches) categoryMenu.removeAttribute('open');
    };
    mobileSettings.addEventListener('change', syncLayout);
    syncLayout();
    const show = () => {
        const query = search.value.trim().toLowerCase();
        clearSearch.hidden = !search.value;
        const requested = location.hash.replace('#settings-', '');
        const category = sections.some(section => section.dataset.settingsSection === requested) ? requested : 'colours';
        let matches = 0;
        sections.forEach(section => {
            const rows = [...section.querySelectorAll('[data-setting-search]')];
            rows.forEach(row => { row.hidden = !!query && !row.dataset.settingSearch.includes(query); if (!row.hidden) matches++; });
            const sectionMatch = query && !rows.length && section.textContent.toLowerCase().includes(query);
            if (sectionMatch) matches++;
            section.hidden = query ? !(sectionMatch || rows.some(row => !row.hidden)) : section.dataset.settingsSection !== category;
        });
        links.forEach(link => { if (!query && link.dataset.settingsNav === category) link.setAttribute('aria-current','location'); else link.removeAttribute('aria-current'); });
        const categoryItems = [...categoryMenu.querySelectorAll('m3e-menu-item')];
        categoryItems.forEach(item => {
            const selected = !query && item.getAttribute('value') === category;
            item.toggleAttribute('checked', selected);
            item.setAttribute('trailing-icon', selected ? 'check' : '');
        });
        const current = categoryItems.find(item => item.getAttribute('value') === category);
        const label = query ? 'Search results' : current.textContent.trim();
        categoryButton.querySelector('[data-settings-category-label]').textContent = label;
        categoryButton.querySelector('[data-settings-category-icon]').textContent = query ? 'search' : current.getAttribute('icon');
        categoryButton.setAttribute('aria-label', 'Settings category: ' + label);
        document.querySelector('#settings-empty').hidden = !query || matches > 0;
    };
    categoryMenu.addEventListener('action', event => {
        search.value = '';
        location.hash = 'settings-' + event.detail.value;
        show();
    });
    categoryMenu.addEventListener('focusin', event => { if (event.target.matches('.m3e-menu__item')) event.target.scrollIntoView({block: 'nearest', inline: 'nearest'}); });
    links.forEach(link => link.addEventListener('click', () => { search.value = ''; }));
    search.addEventListener('input', show); window.addEventListener('hashchange', show);
    clearSearch.addEventListener('click', () => { search.value = ''; show(); search.focus(); });
    search.addEventListener('keydown', event => { if (event.key === 'Escape' && search.value) { event.preventDefault(); search.value = ''; show(); } });
    document.querySelectorAll('[data-reset-group]').forEach(button => button.addEventListener('click', () => change(() => appearance.reset(groups.find(group => group.key === button.dataset.resetGroup).settings.map(item => item.key)))));
    document.querySelector('#reset-customization').addEventListener('click', () => change(() => appearance.reset(appearance.definitions.filter(item => !['confirm-actions','auto-refresh','refresh-interval'].includes(item.key)).map(item => item.key))));
    document.querySelector('#clear-settings-storage').addEventListener('click', () => change(() => appearance.reset(appearance.definitions.map(item => item.key))));
    document.querySelector('#export-preferences').addEventListener('click', () => {
        const preferences = Object.fromEntries(appearance.definitions.map(item => [item.key, appearance.get(item.key)]));
        const url = URL.createObjectURL(new Blob([JSON.stringify({version:1,preferences}, null, 2)], {type:'application/json'}));
        const link = document.createElement('a'); link.href = url; link.download = 'centromail-preferences.json'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
    document.querySelector('#import-preferences').addEventListener('change', async event => {
        try {
            const file = event.target.files[0]; if (!file) return;
            if (file.size > 32768) throw new Error('The preferences file is too large.');
            const data = JSON.parse(await file.text());
            if (data.version !== 1 || !data.preferences || typeof data.preferences !== 'object' || Array.isArray(data.preferences)) throw new Error('Choose a CentroMail preferences export.');
            const entries = Object.entries(data.preferences);
            for (const [key,value] of entries) { const item = appearance.definitions.find(item => item.key === key); if (!item || !appearance.valid(item,value)) throw new Error('Invalid preference: '+key); }
            for (const [key,value] of entries) localStorage.setItem('centromail-'+key,value);
            appearance.apply(); sync(); feedback.textContent = 'Preferences imported.';
        } catch (error) { feedback.textContent = 'Could not import preferences: '+error.message; }
        event.target.value = '';
    });
    document.querySelector('#preview-button').addEventListener('click', () => { feedback.textContent = 'Your buttons use these preferences throughout CentroMail.'; });
    document.querySelector('#preview-icon').addEventListener('click', event => { const button = event.currentTarget; button.setAttribute('aria-pressed',String(button.getAttribute('aria-pressed') !== 'true')); });
    document.addEventListener('centromail-appearance-change', sync);
    sync(); show();
})();
