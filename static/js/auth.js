(() => {
    const loading = document.querySelector('.auth-loading');
    if (!loading) return;
    const root = document.documentElement;
    try {
        root.classList.toggle('reduce-motion', localStorage.getItem('centromail-reduce-motion') === 'true');
        root.dataset.cmMotionStyle = localStorage.getItem('centromail-motion-style') || 'expressive';
    } catch {}
    const label = loading.querySelector('[data-auth-loading-label]');
    const spinner = loading.querySelector('.auth-progress');
    const cancel = loading.querySelector('[data-auth-cancel]');
    const content = document.querySelector('.auth-wrapper');
    let timeout, returnFocus;
    const reset = () => {
        const restoreFocus = !loading.hidden && loading.contains(document.activeElement);
        clearTimeout(timeout);
        loading.hidden = true;
        spinner.hidden = false;
        document.body.classList.remove('auth-page-exit');
        content?.setAttribute('aria-busy', 'false');
        if (restoreFocus && returnFocus?.isConnected) returnFocus.focus();
    };
    const show = message => {
        reset();
        returnFocus = document.activeElement;
        label.textContent = message;
        loading.hidden = false;
        cancel.focus();
        content?.setAttribute('aria-busy', 'true');
        timeout = setTimeout(() => {
            spinner.hidden = true;
            label.textContent = 'Sign-in is taking longer than expected. You can cancel and try again.';
            content?.setAttribute('aria-busy', 'false');
        }, 15000);
    };
    document.addEventListener('click', event => {
        const link = event.target.closest('a[href]');
        if (!link || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || link.target || link.download) return;
        const url = new URL(link.href, location.href);
        if (url.origin === location.origin && url.pathname.startsWith('/auth/')) {
            show(url.pathname.endsWith('/google') ? 'Connecting to Google…' : 'Connecting to Microsoft…');
        }
    });
    document.addEventListener('submit', event => {
        if (!event.defaultPrevented && event.target.matches('.auth-form')) {
            show(document.body.classList.contains('page-register') ? 'Creating account…' : 'Signing in…');
        }
    });
    cancel.addEventListener('click', () => { window.stop(); reset(); });
    window.addEventListener('pageshow', reset);
    window.addEventListener('pagehide', reset);
    reset();
})();
