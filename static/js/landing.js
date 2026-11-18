(() => {
    const button = document.querySelector('#landing-theme');
    if (!button) return;
    const root = document.documentElement;
    const update = () => {
        const dark = root.dataset.theme === 'dark';
        button.setAttribute('aria-label', `Switch to ${dark ? 'light' : 'dark'} theme`);
        button.querySelector('.m3e-icon').textContent = dark ? 'light_mode' : 'dark_mode';
    };
    button.addEventListener('click', () => {
        window.CentroMailAppearance.set('theme', root.dataset.theme === 'dark' ? 'light' : 'dark');
    });
    document.addEventListener('centromail-appearance-change', update);
    update();
})();
