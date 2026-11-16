(() => {
    const init = () => {
        if (!Element.prototype.animate) return;
        const root = document.documentElement;
        const deviceMotion = matchMedia('(prefers-reduced-motion: reduce)');
        const reduced = () => {
            let saved = false;
            try { saved = localStorage.getItem('centromail-reduce-motion') === 'true'; } catch {}
            return deviceMotion.matches || root.classList.contains('reduce-motion') || saved;
        };
        const active = new Map();
        const seen = new WeakSet();
        const observed = new WeakSet();
        const feedbackTimes = new WeakMap();
        const entrances = '[data-landing-enter], .dashboard-welcome, .dashboard-purpose, .dashboard-stat, .dashboard-panel, .dashboard-tip, .dashboard-integrations, .settings-section, .settings-danger, .integration-heading, .integration-card, .form-panel, .message-page .reader-message, .legal-page';
        const rows = '.message, .cm-connected-item, .cm-teams-message';
        const panels = '.account-menu, .quick-menu, .profile-menu, .compose-window, dialog';
        const feedback = '.flash, #settings-feedback, #mail-feedback';
        const visible = element => element.isConnected && !element.closest('[hidden], template') && element.getClientRects().length > 0;
        const duration = () => (root.dataset.cmMotionStyle === 'standard' ? 220 : 340) * Number(root.dataset.cmMotionSpeed || 1);
        const easing = () => root.dataset.cmMotionStyle === 'standard' ? 'cubic-bezier(.2,0,0,1)' : 'cubic-bezier(.16,1,.3,1)';
        const animate = (element, keyframes, options = {}) => {
            if (reduced() || !visible(element)) return;
            active.get(element)?.cancel();
            const animation = element.animate(keyframes, {duration: duration(), easing: easing(), fill: 'backwards', ...options});
            active.set(element, animation);
            const clean = () => { if (active.get(element) === animation) active.delete(element); };
            animation.onfinish = clean;
            animation.oncancel = clean;
        };
        const enter = (element, delay = 0) => root.dataset.cmEntranceMotion !== 'false' && animate(element, [
            {opacity: 0, translate: '0 12px'}, {opacity: 1, translate: '0 0'},
        ], {delay});
        const observer = new IntersectionObserver(entries => {
            let index = 0;
            for (const entry of entries) {
                if (!entry.isIntersecting || !visible(entry.target)) continue;
                if (!seen.has(entry.target)) {
                    seen.add(entry.target);
                    enter(entry.target, Math.min(index++ * 35, 140));
                }
                observer.unobserve(entry.target);
            }
        }, {threshold: .08});
        const scan = container => {
            const elements = [...container.querySelectorAll(`${entrances}, ${rows}`)];
            if (container.matches?.(`${entrances}, ${rows}`)) elements.unshift(container);
            for (const element of elements) {
                if (observed.has(element) || seen.has(element) || element.closest('template')) continue;
                observed.add(element);
                observer.observe(element);
            }
        };
        const openPanel = element => {
            if (!visible(element) || (element.matches('dialog') && !element.open)) return;
            animate(element, [{opacity: 0, scale: '.96', translate: '0 6px'}, {opacity: 1, scale: '1', translate: '0 0'}], {duration: Math.min(duration(), 260)});
        };
        // Share the available width while opening, rather than snapping the inbox
        // to its narrow layout before the reading pane fades in.
        const cancelReaderLayout = () => {
            for (const element of document.querySelectorAll('.gmail-app .inbox, #mail-reader, #reader-content')) active.get(element)?.cancel();
        };
        const readerLayout = update => {
            const inbox = document.querySelector('.gmail-app .inbox');
            const reader = document.querySelector('#mail-reader');
            const from = inbox?.getBoundingClientRect().width;
            const opening = reader?.hidden;
            cancelReaderLayout();
            update();
            if (!opening || !from || reader.hidden || reduced() || root.dataset.cmEntranceMotion === 'false') return;
            const to = inbox.getBoundingClientRect().width;
            const paneWidth = reader.getBoundingClientRect().width;
            const paneStyle = getComputedStyle(reader);
            animate(inbox, [
                {flexBasis: `${from}px`, flexGrow: 0, flexShrink: 0},
                {flexBasis: `${to}px`, flexGrow: 0, flexShrink: 0},
            ]);
            animate(reader, [
                {flexBasis: '0px', flexGrow: 0, flexShrink: 0, marginRight: '0px', borderWidth: '0px', opacity: 0},
                {flexBasis: `${paneWidth}px`, flexGrow: 0, flexShrink: 0, marginRight: paneStyle.marginRight, borderWidth: paneStyle.borderTopWidth, opacity: 1},
            ]);
        };
        window.addEventListener('resize', cancelReaderLayout);
        const feedbackChanged = element => {
            if (!visible(element) || !element.textContent.trim()) return;
            const now = performance.now();
            if (now - (feedbackTimes.get(element) ?? -Infinity) < 500) return;
            feedbackTimes.set(element, now);
            animate(element, [{opacity: .3}, {opacity: 1}], {duration: 180});
        };
        // Newly fetched email rows animate once; existing cached rows keep their place.
        const mutations = new MutationObserver(records => {
            for (const record of records) {
                const element = record.target;
                if (record.type === 'childList') {
                    record.addedNodes.forEach(node => { if (node.nodeType === Node.ELEMENT_NODE) scan(node); });
                    const notice = element.closest(feedback);
                    if (notice) feedbackChanged(notice);
                } else if (record.attributeName === 'hidden' || record.attributeName === 'open') {
                    if (element.matches(panels)) {
                        if (visible(element)) openPanel(element);
                        else active.get(element)?.cancel();
                    }
                    if (element.matches(feedback)) feedbackChanged(element);
                    if (!element.hidden) scan(element);
                } else if (element.matches('.star-button') && element.classList.contains('starred')) {
                    const icon = element.querySelector('.material-symbols-rounded');
                    if (icon) animate(icon, [{scale: '.8', rotate: '-12deg'}, {scale: '1.25', rotate: '8deg', offset: .55}, {scale: '1', rotate: '0deg'}], {duration: 280});
                }
            }
            for (const [element, animation] of active) if (!element.isConnected) animation.cancel();
        });
        mutations.observe(document.body, {subtree: true, childList: true, attributes: true, attributeFilter: ['hidden', 'open', 'class']});
        document.addEventListener('toggle', event => {
            const details = event.target;
            if (!details.matches?.('details[open]')) return;
            [...details.children].filter(child => child.tagName !== 'SUMMARY').forEach((element, index) => enter(element, Math.min(index * 20, 80)));
            scan(details);
        }, true);
        const cancelMotion = () => { if (reduced()) for (const animation of active.values()) animation.cancel(); };
        deviceMotion.addEventListener('change', cancelMotion);
        new MutationObserver(cancelMotion).observe(root, {attributes: true, attributeFilter: ['class']});
        window.addEventListener('storage', cancelMotion);
        document.addEventListener('visibilitychange', () => { if (document.hidden) for (const animation of active.values()) animation.cancel(); });
        const start = () => {
            const page = document.querySelector('.page-content, .auth-wrapper');
            if (page) animate(page, [{opacity: 0}, {opacity: 1}], {duration: 220});
            scan(document.body);
            document.querySelectorAll(panels).forEach(openPanel);
        };
        Promise.race([document.fonts?.ready || Promise.resolve(), new Promise(resolve => setTimeout(resolve, 600))]).then(start);
        window.CentroMailMotion = {enabled: () => !reduced(), readerLayout, readerContent: element => enter(element)};
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
    else init();
})();
