if (document.querySelector('m3e-loading-indicator')) await import('../vendor/m3e/loading-indicator/index.js');

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
let tooltipModule;
const syncTooltips = () => {
    if (document.querySelector('m3e-tooltip')) tooltipModule ??= import('../vendor/m3e/tooltip/index.js');
};
document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    const tooltip = document.querySelector('m3e-tooltip[open]');
    if (tooltip) { tooltip.hide(); event.preventDefault(); event.stopPropagation(); }
}, {capture:true});
const syncReaderText = () => document.querySelectorAll('.email-body-frame').forEach(frame => {
    if (!originalFrames.has(frame)) originalFrames.set(frame, frame.getAttribute('srcdoc'));
    const size = window.CentroMailAppearance.get('reader-text-size');
    const spacing = window.CentroMailAppearance.get('reader-line-height');
    const content = originalFrames.get(frame).replace('</head>', `<style>body{font-size:${size}px!important;line-height:${spacing}!important}</style></head>`);
    if (frame.getAttribute('srcdoc') !== content) frame.setAttribute('srcdoc', content);
});
document.addEventListener('centromail-appearance-change', () => { syncTheme(); syncReaderText(); });
new MutationObserver(syncTheme).observe(document.documentElement, {attributes: true, attributeFilter: ['data-theme']});
new MutationObserver(() => { syncReaderText(); syncTooltips(); }).observe(document.documentElement, {childList: true, subtree: true});
syncTheme(); syncReaderText(); syncTooltips();

// Stop indeterminate morphs when an indicator is hidden or motion is reduced.
const indicatorMotion = matchMedia('(prefers-reduced-motion: reduce)');
const syncIndicators = () => document.querySelectorAll('m3e-loading-indicator').forEach(indicator => {
    const still = indicatorMotion.matches || document.documentElement.classList.contains('reduce-motion') || !!indicator.closest('[hidden]');
    if (still) indicator.setAttribute('progress', '0');
    else indicator.removeAttribute('progress');
});
indicatorMotion.addEventListener('change', syncIndicators);
syncIndicators();
new MutationObserver(syncIndicators).observe(document.documentElement, {subtree: true, attributes: true, attributeFilter: ['hidden', 'class']});
