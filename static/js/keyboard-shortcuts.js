/* CentroMail keyboard shortcuts.
 *
 * Global helpers (`?` for help, `/` for search, `g` sequences) live here so
 * every page shares them. Page scripts register their own actions through
 * `CentroMailShortcuts.register(combo, handler, description, section)`.
 */
(() => {
    const EDITABLE = 'input, textarea, select, [contenteditable="true"]';
    const registry = new Map();
    const sections = new Map();
    let prefix = null;
    let prefixTimer = null;

    let dialog;
    const createDialog = () => {
        const panel = document.createElement('dialog');
        panel.className = 'keyboard-shortcuts-dialog';
        panel.setAttribute('aria-labelledby', 'keyboard-shortcuts-title');
        panel.innerHTML = `
        <div class="reader-toolbar keyboard-shortcuts-header">
            <h2 id="keyboard-shortcuts-title">Keyboard shortcuts</h2>
            <button class="icon-button m3e-icon-button m3e-icon-button--standard" type="button" data-close-shortcuts aria-label="Close shortcuts">
                <span class="material-symbols-rounded" aria-hidden="true">close</span>
            </button>
        </div>
        <p class="keyboard-shortcuts-hint">Press <kbd>?</kbd> anywhere to open this list again. Press <kbd>Esc</kbd> to close it.</p>
        <div class="keyboard-shortcuts-list" id="keyboard-shortcuts-list"></div>`;
        document.body.append(panel);
        panel.querySelector('[data-close-shortcuts]').addEventListener('click', () => panel.close());
        panel.addEventListener('click', event => { if (event.target === panel) panel.close(); });
        return panel;
    };

    const render = () => {
        const list = dialog.querySelector('#keyboard-shortcuts-list');
        list.replaceChildren(...[...sections.entries()].map(([title, items]) => {
            const group = document.createElement('section');
            group.className = 'keyboard-shortcuts-section';
            const heading = document.createElement('h3');
            heading.textContent = title;
            const table = document.createElement('dl');
            table.className = 'keyboard-shortcuts-grid';
            items.forEach(({keys, description}) => {
                const term = document.createElement('dt');
                const key = document.createElement('kbd');
                key.textContent = keys;
                term.append(key);
                const detail = document.createElement('dd');
                detail.textContent = description;
                table.append(term, detail);
            });
            group.append(heading, table);
            return group;
        }));
    };

    window.CentroMailShortcuts = {
        register(combo, handler, description, section = 'Global') {
            registry.set(combo, {handler, description});
            if (!sections.has(section)) sections.set(section, []);
            sections.get(section).push({keys: combo, description});
            if (dialog?.open) render();
        },
        show() {
            dialog ??= createDialog();
            if (dialog.open) return;
            render();
            dialog.showModal();
        },
    };

    const clearPrefix = () => { prefix = null; clearTimeout(prefixTimer); };
    const isEditable = target => target.closest?.(EDITABLE) || target.isContentEditable;
    const focusSearch = () => {
        const search = document.querySelector('#mail-search, .settings-search input, #settings-search, input[type="search"]');
        if (search) { search.focus(); search.select?.(); }
    };

    CentroMailShortcuts.register('?', CentroMailShortcuts.show, 'Show keyboard shortcuts');
    CentroMailShortcuts.register('/', focusSearch, 'Focus search');
    CentroMailShortcuts.register('g i', () => location.assign('/inbox'), 'Go to Inbox', 'Mail');
    CentroMailShortcuts.register('g s', () => location.assign('/inbox?folder=starred'), 'Go to Starred', 'Mail');
    CentroMailShortcuts.register('g d', () => location.assign('/inbox?folder=drafts'), 'Go to Drafts', 'Mail');
    CentroMailShortcuts.register('g t', () => location.assign('/inbox?folder=sent'), 'Go to Sent', 'Mail');
    CentroMailShortcuts.register('g a', () => location.assign('/inbox?folder=all'), 'Go to All mail', 'Mail');

    document.addEventListener('keydown', event => {
        if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey) return;
        if (isEditable(event.target)) return;
        const key = event.key;
        const openDialog = document.querySelector('dialog[open]');
        if (key === 'Escape') {
            clearPrefix();
            if (openDialog) { event.preventDefault(); openDialog.close(); }
            return;
        }
        if (openDialog) return; // Let modal dialogs handle their own keys.
        const combo = prefix ? `${prefix} ${key.toLowerCase()}` : key.toLowerCase();
        const entry = registry.get(combo);
        if (entry) {
            event.preventDefault();
            clearPrefix();
            entry.handler(event);
            return;
        }
        if (key.toLowerCase() === 'g' && !prefix) {
            prefix = 'g';
            clearTimeout(prefixTimer);
            prefixTimer = setTimeout(clearPrefix, 1200);
            return;
        }
        clearPrefix();
    });
})();
