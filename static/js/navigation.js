const panel = document.querySelector('#cm-navigation-panel');
if (panel) {
    const appearance = window.CentroMailAppearance;
    const root = document.documentElement;
    const suite = document.querySelector('#cm-navigation-suite');
    const host = document.querySelector('#cm-navigation-host');
    const dialog = document.querySelector('#cm-navigation-dialog');
    const toggle = document.querySelector('#cm-navigation-toggle');
    const header = document.querySelector('.site-header');
    const items = [...suite.querySelectorAll('m3e-navigation-item')];
    let module, frame;
    const geometry = () => {
        const placement = root.dataset.cmNavigationPlacement;
        const box = panel.getBoundingClientRect();
        for (const side of ['top', 'bottom', 'left', 'right']) {
            root.style.setProperty('--cm-nav-' + side, placement === side ? (['top', 'bottom'].includes(side) ? box.height : box.width) + 'px' : '0px');
        }
        const style = getComputedStyle(header);
        root.style.setProperty('--cm-header-offset', style.position === 'sticky' ? header.getBoundingClientRect().height + (parseFloat(style.top) || 0) + 'px' : '0px');
        document.dispatchEvent(new Event('centromail-navigation-change'));
    };
    const scheduleGeometry = () => {
        cancelAnimationFrame(frame);
        frame = requestAnimationFrame(geometry);
    };
    const layout = () => {
        if (appearance.get('navigation-style') === 'current') return;
        const type = suite.type;
        if (!type) return;
        const kind = type.startsWith('short-navigation-bar') ? 'bar' : type === 'navigation-drawer' ? 'drawer' : 'rail';
        const modal = (kind === 'drawer' && innerWidth < 1000) || (kind === 'rail' && innerWidth < 600);
        const parent = modal ? dialog : host;
        if (panel.parentElement !== parent) {
            if (dialog.open) dialog.close();
            parent.append(panel);
        }
        root.dataset.cmNavigationLayout = kind;
        root.dataset.cmNavigationPlacement = modal ? 'modal' : appearance.get(kind === 'bar' ? 'navigation-bar-position' : 'navigation-side');
        root.dataset.cmNavigationActive = 'true';
        panel.hidden = false;
        toggle.hidden = !modal;
        for (const item of items) {
            const labels = appearance.get('navigation-labels');
            item.labelHidden = kind !== 'drawer' && (labels === 'icons' || (labels === 'selected' && item.value !== suite.selected));
        }
        scheduleGeometry();
    };
    const apply = async () => {
        const style = appearance.get('navigation-style');
        if (style === 'current') {
            if (dialog.open) dialog.close();
            host.append(panel);
            panel.hidden = true;
            toggle.hidden = true;
            root.dataset.cmNavigationActive = 'false';
            root.dataset.cmNavigationPlacement = 'none';
            scheduleGeometry();
            return;
        }
        try {
            module ??= import('../vendor/m3e/navigation-suite/index.js');
            await module;
            if (style !== appearance.get('navigation-style')) return;
            suite.layoutType = style === 'adaptive' ? null : style === 'bar' ?
                (appearance.get('navigation-bar-layout') === 'vertical' ? 'short-navigation-bar-compact' : 'short-navigation-bar-medium') :
                style === 'rail' ? 'wide-navigation-rail-' + appearance.get('navigation-rail-size') : 'navigation-drawer';
            requestAnimationFrame(layout);
        } catch {
            module = null;
            root.dataset.cmNavigationActive = 'false';
            const feedback = document.querySelector('#settings-feedback');
            if (feedback) feedback.textContent = 'Navigation could not load. Reload the page to try again.';
        }
    };
    suite.addEventListener('navigation-suite-type-change', layout);
    suite.addEventListener('selection-change', () => { if (dialog.open) dialog.close(); });
    toggle.addEventListener('click', () => {
        dialog.showModal();
        toggle.setAttribute('aria-expanded', 'true');
        document.querySelector('#cm-navigation-close').focus();
    });
    document.querySelector('#cm-navigation-close').addEventListener('click', () => dialog.close());
    dialog.addEventListener('close', () => {
        toggle.setAttribute('aria-expanded', 'false');
        if (!toggle.hidden) toggle.focus({preventScroll: true});
    });
    dialog.addEventListener('click', event => {
        const box = dialog.getBoundingClientRect();
        if (event.target === dialog && (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom)) dialog.close();
    });
    new ResizeObserver(scheduleGeometry).observe(panel);
    new ResizeObserver(scheduleGeometry).observe(header);
    window.addEventListener('resize', () => { layout(); scheduleGeometry(); });
    document.addEventListener('centromail-appearance-change', apply);
    apply();
}
