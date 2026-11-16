if (document.querySelector('m3e-menu')) {
    await import('../vendor/m3e/menu/index.js');
    const account = document.querySelector('[data-account-menu]');
    if (account) {
        const theme = account.querySelector('[data-account-theme-menu]');
        const sync = () => {
            const dark = document.documentElement.dataset.theme === 'dark';
            theme.setAttribute('icon', dark ? 'light_mode' : 'dark_mode');
            theme.textContent = dark ? 'Light theme' : 'Dark theme';
        };
        account.addEventListener('action', event => {
            if (event.detail.value === 'theme') window.CentroMailAppearance.set('theme', document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
            else if (event.detail.value === 'settings') window.location.assign(account.dataset.settingsUrl);
            else if (event.detail.value === 'logout') document.querySelector('#account-menu-logout').requestSubmit();
        });
        document.addEventListener('centromail-appearance-change', sync);
        sync();
    }
    document.querySelectorAll('[data-nav-menu]').forEach(menu => menu.addEventListener('action', event => window.location.assign(event.detail.value)));
}
