import '../vendor/m3e/ripple/index.js';

// Give the same press feedback to navigation links styled as buttons.
document.querySelectorAll('.nav-link, .mail-nav-link, .dashboard-nav-link').forEach(link => link.classList.add('m3e-state-layer'));
if (document.querySelector('.gmail-app')) {
    document.querySelectorAll('.site-header .nav-link').forEach(link => link.classList.add('m3e-button', 'm3e-button--text'));
}

const restoreSenderInitials = image => {
    const fallback = image.dataset.logoFallback;
    if (fallback) {
        delete image.dataset.logoFallback;
        image.referrerPolicy = 'no-referrer';
        image.src = fallback;
        return;
    }
    image.parentElement.classList.remove('has-sender-logo');
    image.remove();
};
document.addEventListener('error', event => {
    if (event.target.matches?.('img.sender-logo')) restoreSenderInitials(event.target);
}, true);
const checkSenderLogo = image => {
    if (image.complete && !image.naturalWidth) restoreSenderInitials(image);
};
document.querySelectorAll('img.sender-logo').forEach(checkSenderLogo);
const messageList = document.querySelector('#message-list');
if (messageList) new MutationObserver(records => {
    for (const {addedNodes} of records) {
        for (const node of addedNodes) node.querySelectorAll?.('img.sender-logo').forEach(checkSenderLogo);
    }
}).observe(messageList, {childList: true});

// Generate paired Material roles for custom accents, including light/dark contrast.
let themeModule, lastTheme;
const themeOptions = () => {
    const appearance = window.CentroMailAppearance;
    return {seed: appearance.get('accent'), mode: document.documentElement.dataset.theme,
        motionScheme: appearance.get('motion-style'), variant: appearance.get('palette'), contrast: appearance.get('contrast'), selector: ':root[data-theme]'};
};
const syncTheme = async () => {
    const options = themeOptions();
    const useCustom = localStorage.getItem('centromail-accent') || options.variant !== 'tonalSpot' || options.contrast !== 'standard';
    if (!useCustom) { document.querySelector('#cm-custom-theme')?.remove(); lastTheme = null; return; }
    const key = JSON.stringify(options);
    if (key === lastTheme) return;
    themeModule ??= import('../vendor/m3e/theme.js');
    const {createTheme} = await themeModule;
    if (key !== JSON.stringify(themeOptions()) || !(localStorage.getItem('centromail-accent') || options.variant !== 'tonalSpot' || options.contrast !== 'standard')) return;
    let style = document.querySelector('#cm-custom-theme');
    if (!style) { style = document.createElement('style'); style.id = 'cm-custom-theme'; document.head.append(style); }
    style.textContent = createTheme(options).cssText; lastTheme = key;
};
const originalFrames = new WeakMap();
const frameObservers = new Map();
const watchEmailSize = frame => {
    frameObservers.get(frame)?.disconnect();
    if (!frame.isConnected) { frameObservers.delete(frame); return; }
    const body = frame.contentDocument?.body;
    if (!body) return;
    // Email templates may force viewport heights, clipping their overflowing content.
    for (const root of [frame.contentDocument.documentElement, body]) {
        root.style.setProperty('height', 'auto', 'important');
        root.style.setProperty('min-height', '0', 'important');
        root.style.setProperty('max-height', 'none', 'important');
    }
    const fit = () => {
        if (!frame.isConnected || frame.contentDocument?.body !== body) return;
        const height = Math.min(100000, Math.max(64,
            Math.ceil(Math.max(body.getBoundingClientRect().height, body.scrollHeight)) + 2));
        if (frame.style.height !== `${height}px`) frame.style.height = `${height}px`;
    };
    let scheduled = false;
    const scheduleFit = () => {
        if (scheduled) return;
        scheduled = true;
        requestAnimationFrame(() => {
            scheduled = false;
            fit();
        });
    };
    const observer = new ResizeObserver(scheduleFit);
    observer.observe(body);
    body.addEventListener('load', scheduleFit, true);
    body.addEventListener('error', scheduleFit, true);
    frameObservers.set(frame, observer);
    fit();
};
let tooltipModule;
const syncTooltips = () => {
    if (document.querySelector('m3e-tooltip')) tooltipModule ??= import('../vendor/m3e/tooltip/index.js');
};
document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    const tooltip = document.querySelector('m3e-tooltip[open]');
    if (tooltip?.hide) { tooltip.hide(); event.preventDefault(); event.stopPropagation(); }
}, {capture:true});
const reader = document.querySelector('#reader-content, .message-page');
const syncReaderText = () => {
    if (!reader) return;
    for (const [frame, observer] of frameObservers) {
        if (!frame.isConnected) { observer.disconnect(); frameObservers.delete(frame); }
    }
    const size = window.CentroMailAppearance.get('reader-text-size');
    const spacing = window.CentroMailAppearance.get('reader-line-height');
    const style = `<style>body{font-size:${size}px!important;line-height:${spacing}!important}</style>`;
    reader.querySelectorAll('.email-body-frame').forEach(frame => {
        let email = originalFrames.get(frame);
        if (!email) {
            email = {source: frame.getAttribute('srcdoc')};
            originalFrames.set(frame, email);
            // Email scripts remain sandboxed; only the parent measures the document.
            frame.addEventListener('load', () => watchEmailSize(frame));
            watchEmailSize(frame);
        }
        if (email.style !== style) {
            email.style = style;
            frame.setAttribute('srcdoc', email.source.replace('</head>', style + '</head>'));
        }
    });
};
document.addEventListener('centromail-appearance-change', () => { syncTheme(); syncReaderText(); });
new MutationObserver(syncTheme).observe(document.documentElement, {attributes: true, attributeFilter: ['data-theme']});
if (reader) new MutationObserver(() => {
    syncReaderText();
    syncTooltips();
    reader.querySelectorAll('img.sender-logo').forEach(checkSenderLogo);
}).observe(reader, {childList: true, subtree: true});
syncTheme(); syncReaderText(); syncTooltips();

const messagePage = document.querySelector('.message-page');
if (messagePage) {
    const navigation = document.querySelector('.site-header');
    const syncReaderToolbar = () => {
        const style = getComputedStyle(navigation);
        messagePage.style.setProperty('--message-nav-height', style.position === 'sticky' ? `${navigation.getBoundingClientRect().height + (parseFloat(style.top) || 0)}px` : '0px');
    };
    new ResizeObserver(syncReaderToolbar).observe(navigation);
    document.addEventListener('centromail-appearance-change', syncReaderToolbar);
    document.addEventListener('centromail-navigation-change', syncReaderToolbar);
    syncReaderToolbar();
}

// Stop indeterminate morphs when an indicator is hidden or motion is reduced.
const indicators = [...document.querySelectorAll('m3e-loading-indicator')];
if (indicators.length) {
    const indicatorMotion = matchMedia('(prefers-reduced-motion: reduce)');
    const root = document.documentElement;
    const syncIndicators = () => {
        const still = indicatorMotion.matches || root.classList.contains('reduce-motion') || root.dataset.cmLoadingMotion === 'false';
        for (const indicator of indicators) {
            if (still || indicator.closest('[hidden]')) indicator.setAttribute('progress', '0');
            else indicator.removeAttribute('progress');
        }
    };
    indicatorMotion.addEventListener('change', syncIndicators);
    document.addEventListener('centromail-appearance-change', syncIndicators);
    new MutationObserver(syncIndicators).observe(document.querySelector('main'), {
        subtree: true, attributes: true, attributeFilter: ['hidden'],
    });
    syncIndicators();
}

await Promise.all([
    indicators.length && import('../vendor/m3e/loading-indicator/index.js'),
    document.querySelector('m3e-linear-progress') && import('../vendor/m3e/linear-progress/index.js'),
    document.querySelector('m3e-snackbar-host') && import('../vendor/m3e/snackbar-host/index.js'),
    document.querySelector('m3e-pull-to-refresh') && import('../vendor/m3e/pull-to-refresh/index.js'),
]);
