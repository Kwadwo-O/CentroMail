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
        root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
        localStorage.setItem('centromail-theme', root.dataset.theme);
        update();
    });
    update();
})();
