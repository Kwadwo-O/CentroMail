(() => {
    const init = () => {
        if (!Element.prototype.animate) return;
        const root = document.documentElement;
        const deviceMotion = matchMedia('(prefers-reduced-motion: reduce)');
        const reduced = () => deviceMotion.matches || root.classList.contains('reduce-motion');
        const enabled = family => !reduced() && (!family || root.dataset[`cm${family[0].toUpperCase()}${family.slice(1)}Motion`] !== 'false');
        const active = new Map();
        const seen = new WeakSet(), observed = new WeakSet(), loadedMedia = new WeakSet();
        const feedbackTimes = new WeakMap();
        const copyIcons = new WeakMap();
        const entrances = '[data-landing-enter], .dashboard-welcome, .dashboard-purpose, .dashboard-stat, .dashboard-panel, .dashboard-tip, .dashboard-integrations, .settings-danger, .integration-heading, .integration-card, .form-panel, .legal-page';
        const rows = '.message, .cm-connected-item, .cm-teams-message, .cm-teams-conversation, .apps-feed-message, .telegram-message, .telegram-conversation';
        const panels = '.account-menu, .quick-menu, .profile-menu, .compose-window, dialog';
        const views = '.workspace-view, .settings-section, #telegram-workspace, #teams-chat-pane';
        const notices = '.flash, #settings-feedback, #mail-feedback, #mail-load-status, #apps-feed-status, #telegram-chat-status, #telegram-send-status, .telegram-media-error';
        const media = '.telegram-message-media img, .telegram-message-media video, img.sender-logo, img.telegram-avatar';
        const visible = element => element?.isConnected && !element.closest('[hidden], template') && element.getClientRects().length > 0;
        const speed = () => Number(root.dataset.cmMotionSpeed || 1);
        const intensity = () => Number(root.dataset.cmMotionIntensity || 1) * (root.dataset.cmMotionStyle === 'standard' ? .5 : 1);
        const timing = family => {
            const token = ['copy', 'send', 'selection', 'hover', 'press', 'drag'].includes(family) ? 'fast-spatial' : ['notification', 'media', 'focus', 'theme', 'control'].includes(family) ? 'fast-effects' : 'default-spatial';
            const style = getComputedStyle(root);
            const raw = style.getPropertyValue?.(`--m3e-sys-motion-spring-${token}-duration`).trim() || '340ms';
            return {duration: parseFloat(raw) * (raw.endsWith('ms') ? 1 : 1000), easing: style.getPropertyValue?.(`--m3e-sys-motion-spring-${token}-easing`).trim() || 'cubic-bezier(.2,0,0,1)'};
        };
        const animate = (element, family, keyframes, options = {}) => {
            if (!enabled(family) || !visible(element) || document.hidden) return;
            active.get(element)?.animation.cancel();
            const spring = timing(family);
            const animation = element.animate(keyframes, {
                easing: spring.easing, fill: 'backwards', ...options,
                duration: (options.duration ?? spring.duration) * speed(),
                delay: (options.delay || 0) * speed(),
            });
            active.set(element, {animation, family});
            const clean = () => { if (active.get(element)?.animation === animation) active.delete(element); };
            animation.onfinish = clean;
            animation.oncancel = clean;
            return animation;
        };
        const reveal = (element, family, delay = 0, moving = true) => animate(element, family, [
            {opacity: .15, ...(moving ? {translate: `0 ${12 * intensity()}px`} : {})},
            {opacity: 1, ...(moving ? {translate: '0 0'} : {})},
        ], {delay});
        const feedback = (element, family = 'selection') => {
            if (family === 'drag') {
                animate(element, family, [{boxShadow: '0 0 0 4px var(--highlight)'}, {boxShadow: '0 0 0 0 transparent'}], {duration: 260});
                return;
            }
            const icon = element?.querySelector('.m3e-icon, .material-symbols-rounded') || element;
            if (family === 'copy' && icon && icon !== element) {
                const previous = copyIcons.get(icon);
                clearTimeout(previous?.timer);
                const original = previous?.original ?? icon.textContent;
                icon.textContent = 'check';
                const timer = setTimeout(() => {
                    if (icon.isConnected) icon.textContent = original;
                    copyIcons.delete(icon);
                }, 1800);
                copyIcons.set(icon, {original, timer});
            }
            const amount = intensity();
            const frames = family === 'send' ? [
                {translate: '0 0', opacity: 1}, {translate: `${10 * amount}px 0`, opacity: 0, offset: .55},
                {translate: `${-6 * amount}px 0`, opacity: 0, offset: .56}, {translate: '0 0', opacity: 1},
            ] : [
                {scale: String(1 - .18 * amount), rotate: `${-8 * amount}deg`},
                {scale: String(1 + .18 * amount), rotate: `${5 * amount}deg`, offset: .55},
                {scale: '1', rotate: '0deg'},
            ];
            animate(icon, family, frames);
        };
        const mediaLoaded = element => {
            if (!element.matches?.(media) || loadedMedia.has(element)) return;
            if (animate(element, 'media', [{opacity: .2}, {opacity: 1}], {duration: 260})) loadedMedia.add(element);
        };
        document.addEventListener('load', event => mediaLoaded(event.target), true);
        document.addEventListener('loadeddata', event => mediaLoaded(event.target), true);
        const observer = new IntersectionObserver(entries => {
            let index = 0;
            for (const entry of entries) {
                if (!entry.isIntersecting || !visible(entry.target)) continue;
                if (!seen.has(entry.target)) {
                    seen.add(entry.target);
                    reveal(entry.target, entry.target.matches(rows) ? 'list' : 'entrance', Math.min(index++ * 30, 150));
                }
                observer.unobserve(entry.target);
            }
        }, {threshold: .08});
        const scan = container => {
            const elements = [...container.querySelectorAll(`${entrances}, ${rows}`)];
            if (container.matches?.(`${entrances}, ${rows}`)) elements.unshift(container);
            for (const element of elements) {
                if (observed.has(element) || seen.has(element) || element.closest('template')) continue;
                observed.add(element); observer.observe(element);
            }
            container.querySelectorAll(media).forEach(element => {
                if (element.naturalWidth || element.readyState >= 2) mediaLoaded(element);
            });
            if (container.matches?.(media) && (container.naturalWidth || container.readyState >= 2)) mediaLoaded(container);
        };
        const openPanel = element => {
            if (!element || (element.matches('dialog') && !element.open)) return;
            const amount = intensity();
            animate(element, 'panel', [
                {opacity: 0, scale: String(1 - .04 * amount), translate: `0 ${6 * amount}px`},
                {opacity: 1, scale: '1', translate: '0 0'},
            ]);
        };
        const cancelReaderLayout = () => {
            for (const element of document.querySelectorAll('.gmail-app .inbox, #mail-reader, #reader-content')) active.get(element)?.animation.cancel();
        };
        const readerLayout = update => {
            const inbox = document.querySelector('.gmail-app .inbox');
            const reader = document.querySelector('#mail-reader');
            cancelReaderLayout();
            const from = inbox?.getBoundingClientRect().width;
            update();
            if (!from || !reader || !enabled('reader')) return;
            const to = inbox.getBoundingClientRect().width;
            // Only animate width here: transforms would move the fixed Reply button with its ancestors.
            animate(inbox, 'reader', [
                {flexBasis: `${from}px`, flexGrow: 0, flexShrink: 0},
                {flexBasis: `${to}px`, flexGrow: 0, flexShrink: 0},
            ]);
            if (reader.hidden) return;
            const paneWidth = reader.getBoundingClientRect().width;
            const paneStyle = getComputedStyle(reader);
            animate(reader, 'reader', [
                {flexBasis: '0px', flexGrow: 0, flexShrink: 0, marginRight: '0px', borderWidth: '0px', opacity: 0},
                {flexBasis: `${paneWidth}px`, flexGrow: 0, flexShrink: 0, marginRight: paneStyle.marginRight, borderWidth: paneStyle.borderTopWidth, opacity: 1},
            ]);
        };
        window.addEventListener('resize', cancelReaderLayout);
        const feedbackChanged = element => {
            if (!visible(element) || !element.textContent.trim()) return;
            const now = performance.now();
            if (now - (feedbackTimes.get(element) ?? -Infinity) < 400) return;
            feedbackTimes.set(element, now);
            reveal(element, 'notification', 0, false);
        };
        const mutations = new MutationObserver(records => {
            const changedNotices = new Set();
            for (const record of records) {
                const element = record.target;
                if (record.type === 'childList') {
                    record.addedNodes.forEach(node => { if (node.nodeType === Node.ELEMENT_NODE) scan(node); });
                    const notice = element.closest(notices);
                    if (notice) changedNotices.add(notice);
                } else if (record.attributeName === 'hidden' || record.attributeName === 'open') {
                    if (!visible(element)) { active.get(element)?.animation.cancel(); continue; }
                    if (element.matches(panels)) openPanel(element);
                    if (element.matches(views)) reveal(element, 'navigation', 0, false);
                    if (element.matches('.mail-selection-actions')) reveal(element, 'selection');
                    if (element.matches(notices)) changedNotices.add(element);
                    if (!element.hidden) scan(element);
                } else if (record.attributeName === 'aria-selected' && element.getAttribute('aria-selected') === 'true' && record.oldValue !== 'true') {
                    feedback(element, 'navigation');
                    const target = document.getElementById(element.getAttribute('aria-controls'));
                    if (target) reveal(target, 'navigation', 0, false);
                } else if (record.attributeName === 'class') {
                    const before = (record.oldValue || '').split(/\s+/);
                    if (element.matches('.star-button') && element.classList.contains('starred') && !before.includes('starred')) feedback(element);
                    if (before.includes('is-dragging') && !element.classList.contains('is-dragging')) feedback(element, 'drag');
                }
            }
            changedNotices.forEach(feedbackChanged);
            for (const [element, {animation}] of active) if (!visible(element)) animation.cancel();
        });
        mutations.observe(document.body, {subtree: true, childList: true, attributes: true, attributeOldValue: true, attributeFilter: ['hidden', 'open', 'class', 'aria-selected']});
        document.addEventListener('toggle', event => {
            const details = event.target;
            if (!details.matches?.('details[open]')) return;
            [...details.children].filter(child => child.tagName !== 'SUMMARY').forEach((element, index) => reveal(element, 'expand', Math.min(index * 20, 80)));
            scan(details);
        }, true);
        document.addEventListener('change', event => {
            const control = event.target;
            if (control.matches?.('input[type=checkbox], input[type=radio]') && control.closest('.message')) feedback(control.closest('.checkbox-wrap, .message'), 'selection');
            if (control.matches?.('select')) reveal(control, 'control', 0, false);
        });
        const cancelMotion = () => { for (const {animation, family} of active.values()) if (!enabled(family)) animation.cancel(); };
        deviceMotion.addEventListener('change', cancelMotion);
        document.addEventListener('centromail-appearance-change', () => { for (const {animation} of active.values()) animation.cancel(); });
        new MutationObserver(cancelMotion).observe(root, {attributes: true});
        document.addEventListener('visibilitychange', () => { if (document.hidden) for (const {animation} of active.values()) animation.cancel(); });
        const start = () => {
            const page = document.querySelector('.page-content, .auth-wrapper');
            if (page) reveal(page, 'entrance', 0, false);
            scan(document.body);
            document.querySelectorAll(panels).forEach(openPanel);
        };
        Promise.race([document.fonts?.ready || Promise.resolve(), new Promise(resolve => setTimeout(resolve, 600))]).then(start);
        window.CentroMailMotion = {
            enabled, readerLayout, readerContent: element => reveal(element, 'reader', 0, false), feedback,
            preview: (container, family = 'all') => {
                const view = container.querySelector('[data-motion-sample="view"]');
                const panel = container.querySelector('[data-motion-sample="panel"]');
                const copy = container.querySelector('[data-motion-sample="copy"]');
                const send = container.querySelector('[data-motion-sample="send"]');
                if (family === 'all') {
                    reveal(view, 'navigation');
                    container.querySelectorAll('[data-motion-sample="row"]').forEach((row, index) => reveal(row, 'list', index * 50));
                    openPanel(panel); feedback(copy, 'copy'); feedback(send, 'send');
                } else if (family === 'list') {
                    container.querySelectorAll('[data-motion-sample="row"]').forEach((row, index) => reveal(row, family, index * 50));
                } else if (family === 'panel') openPanel(panel);
                else if (family === 'copy' || family === 'send' || family === 'selection') feedback(family === 'send' ? send : copy, family);
                else if (family === 'drag') feedback(panel, family);
                else if (family === 'hover' || family === 'press') {
                    const style = getComputedStyle(copy);
                    const frames = family === 'press' ? [{borderRadius: style.borderRadius},
                        {borderRadius: style.getPropertyValue?.('--m3e-comp-button-small-container-shape-pressed') || '8px', offset: .5}, {borderRadius: style.borderRadius}] :
                        [{boxShadow: style.boxShadow}, {boxShadow: style.getPropertyValue?.('--_m3e-button-shadow-hovered') || '0 1px 3px var(--highlight)', offset: .5}, {boxShadow: style.boxShadow}];
                    animate(copy, family, frames);
                } else if (family === 'loading') {
                    reveal(container.querySelector('[data-motion-sample="loading"]') || send.querySelector('.m3e-icon'), family, 0, false);
                } else if (family === 'theme' || family === 'focus') {
                    const style = getComputedStyle(panel);
                    animate(panel, family, family === 'theme' ? [{backgroundColor: 'var(--highlight)'}, {backgroundColor: style.backgroundColor}] :
                        [{boxShadow: '0 0 0 3px var(--highlight)'}, {boxShadow: '0 0 0 0 transparent'}]);
                } else if (family === 'reader') {
                    animate(panel, family, [{clipPath: 'inset(0 100% 0 0)', opacity: .15}, {clipPath: 'inset(0 0 0 0)', opacity: 1}]);
                } else {
                    const target = family === 'media' ? view.querySelector('.motion-preview-avatar') : family === 'notification' ? container.querySelector('#motion-preview-status') : family === 'control' ? copy : family === 'expand' ? panel : view;
                    reveal(target, family, 0, !['navigation', 'media', 'notification', 'control'].includes(family));
                }
            },
        };
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
    else init();
})();
