(() => {
    const app = document.querySelector('.gmail-app');
    if (!app) return;
    const navigation = document.querySelector('.site-header');
    const masthead = app.querySelector('.gmail-header');
    const syncHeaders = () => {
        for (const [element, property] of [[navigation, '--mail-nav-height'], [masthead, '--mail-search-height']]) {
            const style = getComputedStyle(element);
            app.style.setProperty(property, style.position === 'sticky' ? element.getBoundingClientRect().height + (element === navigation ? parseFloat(style.top) || 0 : 0) + 'px' : '0px');
        }
    };
    const headerObserver = new ResizeObserver(syncHeaders);
    headerObserver.observe(navigation);
    headerObserver.observe(masthead);
    document.addEventListener('centromail-appearance-change', syncHeaders);
    document.addEventListener('centromail-navigation-change', syncHeaders);
    syncHeaders();
    const folder = app.dataset.folder;
    const list = document.querySelector('#message-list');
    const search = document.querySelector('#mail-search');
    const status = document.querySelector('#mail-load-status');
    const loadingIndicator = document.querySelector('#mail-loading-indicator');
    const feedback = document.querySelector('#mail-feedback');
    const more = document.querySelector('#load-more-mail');
    const refresh = document.querySelector('#refresh-mail');
    const selectAll = document.querySelector('#select-all');
    const reader = document.querySelector('#mail-reader');
    const readerContent = document.querySelector('#reader-content');
    const readerStatus = document.querySelector('#reader-status');
    const desktop = window.matchMedia('(min-width: 1200px)');
    let cursor = null, hasMore = true, loading = false, failed = false, loadedTotal = null;
    let generation = 0, controller, searchTimer, readerController;
    let actionPending = false, readerMessageKey;
    let statusController, statusOffset = 0, changeGeneration = 0;
    let focusedIndex = -1;
    const rows = () => [...list.querySelectorAll('.message')];
    const visibleRows = () => rows().filter(row => !row.hidden);
    const messageKey = row => JSON.stringify([row.dataset.mailAccount || app.dataset.account, row.dataset.messageId]);
    const clearFocusedRow = () => {
        focusedIndex = -1;
        list.querySelectorAll('.message.is-focused').forEach(row => row.classList.remove('is-focused'));
    };
    const sort = document.querySelector('#mail-sort');
    const direction = document.querySelector('#mail-sort-direction');
    const filters = [...document.querySelectorAll('.mail-filter-fields select')];
    // shortcut: Sorting and filters cover loaded rows; add provider queries if full-mailbox filtering is needed.
    const sortMessages = () => {
        const active = document.activeElement;
        const ascending = window.CentroMailAppearance.get('mail-sort-direction') === 'asc';
        const text = row => row.querySelector(sort.value === 'sender' ? '.message-sender' : '.message-subject').textContent;
        const sorted = rows().sort((a, b) => {
            const date = (Number(a.dataset.messageTime) || 0) - (Number(b.dataset.messageTime) || 0);
            if (sort.value === 'newest') return ascending ? date : -date;
            const name = text(a).localeCompare(text(b), undefined, {sensitivity:'base', numeric:true});
            return (ascending ? name : -name) || -date;
        });
        sorted.forEach((row, index) => {
            if (list.children[index] !== row) list.insertBefore(row, list.children[index] || null);
        });
        if (list.contains(active) && document.activeElement !== active) active.focus({preventScroll: true});
    };
    const applyFilters = () => {
        const values = Object.fromEntries(filters.map(field => [field.id, field.value]));
        const count = filters.filter(field => field.value !== 'all').length;
        const today = new Date(); today.setHours(0,0,0,0);
        const date = values['mail-filter-date'];
        if (date !== 'all' && date !== 'today') today.setDate(today.getDate() - Number(date) + 1);
        for (const row of rows()) {
            const read = values['mail-filter-read'], star = values['mail-filter-star'], reply = values['mail-filter-reply'];
            const unread = row.classList.contains('unread'), starred = row.querySelector('.star-button').classList.contains('starred');
            const timestamp = Number(row.dataset.messageTime) || 0;
            row.hidden = (read !== 'all' && unread !== (read === 'unread')) ||
                (star !== 'all' && starred !== (star === 'starred')) ||
                (reply === 'replyable' && row.dataset.canReply !== 'true') || (reply === 'noreply' && row.dataset.noReply !== 'true') ||
                (date !== 'all' && (timestamp < today.getTime() || timestamp > Date.now()));
            if (row.hidden) {
                row.querySelector('.message-check').checked = false;
                if (row.contains(document.activeElement)) list.focus({preventScroll:true});
                row.classList.remove('is-focused');
            }
        }
        focusedIndex = visibleRows().indexOf(list.querySelector('.message.is-focused'));
        const shown = visibleRows().length, loaded = rows().length;
        const badge = document.querySelector('#mail-filter-count'); badge.hidden = count === 0; badge.textContent = String(count);
        document.querySelector('#mail-filter-status').textContent = count ? `${shown} of ${loaded} loaded messages match. Load more to include older emails.` : 'Filters apply to loaded emails. Load more to include older messages.';
        document.querySelector('#mail-page-count').textContent = count ? `${shown} of ${loaded} loaded` : hasMore ? `${loaded} loaded${loadedTotal == null ? '' : ` · about ${loadedTotal} total`}` : `${loaded} messages`;
        const empty = document.querySelector('#empty-state'); empty.hidden = shown > 0;
        empty.textContent = count && loaded ? 'No loaded messages match these filters. Load more or clear filters.' : search.value.trim() ? 'No messages match your search.' : 'No messages in this folder.';
        updateSelection();
    };
    const syncSort = () => {
        sort.value = window.CentroMailAppearance.get('mail-sort');
        const ascending = window.CentroMailAppearance.get('mail-sort-direction') === 'asc';
        const date = sort.value === 'newest';
        const label = date ? (ascending ? 'Oldest first' : 'Newest first') : (ascending ? 'A to Z' : 'Z to A');
        const next = date ? (ascending ? 'newest first' : 'oldest first') : (ascending ? 'Z to A' : 'A to Z');
        direction.querySelector('[data-sort-direction-label]').textContent = label;
        direction.querySelector('.m3e-icon').textContent = ascending ? 'arrow_upward' : 'arrow_downward';
        direction.setAttribute('aria-label', `${label}. Switch to ${next}`);
        direction.title = `Switch to ${next}`;
        sortMessages();
    };
    sort.addEventListener('change', () => window.CentroMailAppearance.set('mail-sort', sort.value));
    direction.addEventListener('click', () => window.CentroMailAppearance.set('mail-sort-direction', window.CentroMailAppearance.get('mail-sort-direction') === 'asc' ? 'desc' : 'asc'));
    filters.forEach(field => field.addEventListener('change', applyFilters));
    document.querySelector('#clear-mail-filters').addEventListener('click', () => { filters.forEach(field => { field.value = 'all'; }); applyFilters(); });
    document.addEventListener('centromail-appearance-change', syncSort);
    const selected = () => visibleRows().filter(row => row.querySelector('.message-check').checked);
    const showFeedback = (message, reconnect = false) => {
        feedback.textContent = message;
        feedback.hidden = !message;
        if (reconnect) {
            const link = document.createElement('a');
            link.href = app.dataset.googleUrl;
            link.textContent = ' Reconnect account';
            feedback.append(link);
        }
    };
    const readJson = async response => {
        if (response.redirected) {
            window.location.assign(response.url);
            throw new Error('Please sign in again.');
        }
        if (response.headers && !response.headers.get('Content-Type')?.includes('application/json')) {
            throw new Error('Could not complete the request. Reload the page and try again.');
        }
        const data = await response.json();
        if (!response.ok) throw Object.assign(new Error(data.error || 'Please try again.'), {reconnect: data.reconnect});
        return data;
    };
    const updateSelection = () => {
        const count = selected().length;
        document.querySelector('.mail-selection-actions').hidden = count === 0;
        selectAll.checked = visibleRows().length > 0 && count === visibleRows().length;
        selectAll.indeterminate = count > 0 && count < visibleRows().length;
        selectAll.disabled = visibleRows().length === 0 || actionPending;
        document.querySelector('#mail-selection-count').textContent = count > 1000 ? 'Select up to 1,000 messages' : (count ? `${count} selected` : '');
        document.querySelectorAll('[data-mail-action]').forEach(button => {
            button.disabled = count === 0 || count > 1000 || actionPending;
        });
    };
    const setRefreshBusy = busy => {
        refresh.disabled = busy;
        refresh.setAttribute('aria-busy', String(busy));
        refresh.setAttribute('aria-label', busy ? 'Refreshing inbox' : 'Refresh inbox');
        refresh.querySelector('[data-refresh-label]').textContent = busy ? 'Refreshing…' : 'Refresh';
    };
    const loadCounts = async (force = false) => {
        try {
            const url = new URL(app.dataset.countsUrl, location.origin);
            url.searchParams.set('account', app.dataset.account);
            if (force) url.searchParams.set('refresh', '1');
            const counts = await readJson(await fetch(url));
            document.querySelectorAll('[data-folder-count]').forEach(element => {
                const count = counts[element.dataset.folderCount];
                element.textContent = count ?? '';
                element.hidden = !count;
            });
        } catch { /* Existing counts remain when Gmail is unavailable. */ }
    };
    document.addEventListener('centromail-mail-read', event => {
        if (app.dataset.account === 'all' || event.detail.account === app.dataset.account) { changeGeneration++; statusController?.abort(); loadCounts(true); }
    });
    const syncGmailStatus = async () => {
        if (!app.dataset.statusUrl || document.hidden || search.disabled || loading || actionPending || statusController) return;
        const loaded = rows();
        if (!loaded.length) return;
        const visible = loaded.filter(row => { const box = row.getBoundingClientRect(); return box.bottom > 0 && box.top < innerHeight; });
        const batch = [...new Set([...visible, ...loaded.slice(statusOffset, statusOffset + 25)])].slice(0,50);
        statusOffset = (statusOffset + 25) % loaded.length;
        const pending = new AbortController(); statusController = pending;
        const version = changeGeneration, page = generation;
        const timeout = setTimeout(() => pending.abort(), 30000);
        const body = new URLSearchParams({account:app.dataset.account, csrf_token:app.dataset.csrf});
        batch.forEach(row => body.append('message_ids',row.dataset.messageId));
        try {
            const data = await readJson(await fetch(app.dataset.statusUrl,{method:'POST',body,signal:pending.signal}));
            if (version !== changeGeneration || page !== generation || document.hidden || search.disabled) return;
            for (const message of data.messages) {
                const row = loaded.find(item => item.dataset.messageId === message.id);
                if (!row?.isConnected) continue;
                row.classList.toggle('unread', message.unread);
                row.querySelector('.message-read-state').textContent = message.unread ? 'Unread: ' : '';
            }
            applyFilters();
            document.querySelectorAll('[data-folder-count]').forEach(element => {
                const count = data.counts[element.dataset.folderCount];
                if (count !== undefined) { element.textContent = count; element.hidden = !count; }
            });
        } catch { /* Keep the last known status when Gmail is temporarily unavailable. */ }
        finally { clearTimeout(timeout); if (statusController === pending) statusController = null; }
    };
    const loadMessages = async ({reset = false, force = false} = {}) => {
        if (reset) {
            generation += 1;
            controller?.abort();
            statusController?.abort(); statusController = null; statusOffset = 0;
            cursor = null;
            hasMore = true;
            failed = false;
            loading = false;
            clearFocusedRow();
        }
        if (loading || !hasMore) return;
        const currentGeneration = generation;
        controller = new AbortController();
        const pending = controller;
        const timeout = setTimeout(() => pending.abort(), 45000);
        loading = true;
        loadingIndicator.hidden = false;
        list.setAttribute('aria-busy', 'true');
        status.textContent = reset ? 'Loading messages…' : 'Loading more messages…';
        more.setAttribute('aria-disabled', 'true');
        more.hidden = document.activeElement !== more;
        if (force) setRefreshBusy(true);
        const url = new URL(app.dataset.messagesUrl, location.origin);
        url.searchParams.set('folder', folder);
        url.searchParams.set('account', app.dataset.account);
        if (cursor) url.searchParams.set('cursor', cursor);
        if (search.value.trim()) url.searchParams.set('search', search.value.trim());
        const activeTab = document.querySelector('.inbox-tab.active');
        if (activeTab) url.searchParams.set('category', activeTab.dataset.tab);
        if (force) url.searchParams.set('refresh', '1');
        try {
            const data = await readJson(await fetch(url, {signal: pending.signal}));
            if (currentGeneration !== generation) return;
            const fragment = document.createRange().createContextualFragment(data.html);
            const known = new Set(reset ? [] : rows().map(messageKey));
            fragment.querySelectorAll('.message').forEach(row => {
                const key = messageKey(row);
                if (known.has(key)) row.remove();
                else known.add(key);
            });
            if (reset) list.replaceChildren(fragment);
            else list.append(fragment);
            sortMessages();
            const previousCursor = cursor;
            cursor = data.next_cursor;
            hasMore = Boolean(cursor) && cursor !== previousCursor;
            failed = false;
            showFeedback(data.warning || '');
            const count = rows().length;
            loadedTotal = data.total;
            applyFilters();
            status.textContent = hasMore ? 'Scroll to load more messages.' : (count ? 'All messages loaded.' : '');
            if (force) loadCounts(true);
            if (force && !data.warning) {
                const message = hasMore ? 'Recent emails synced. Scroll to load older messages.' : 'Emails synced.';
                status.textContent = message;
                document.querySelector('#mail-sync-snackbar')?.showSnackbar?.({message, withDismissAction: true, duration: 'short'});
            }
        } catch (error) {
            if (currentGeneration !== generation) return;
            failed = true;
            status.textContent = error.name === 'AbortError' ? 'Loading took too long. Try again.' : error.message;
            showFeedback(status.textContent, error.reconnect);
        } finally {
            clearTimeout(timeout);
            if (currentGeneration === generation) {
                loading = false;
                loadingIndicator.hidden = true;
                list.setAttribute('aria-busy', 'false');
                const restoreMoreFocus = document.activeElement === more && !hasMore && !failed;
                more.hidden = !hasMore && !failed;
                more.removeAttribute('aria-disabled');
                more.textContent = failed ? 'Try again' : 'Load more';
                if (restoreMoreFocus) list.focus();
                setRefreshBusy(false);
                if (!failed) syncGmailStatus();
            }
        }
    };
    // Resizable reading pane ---------------------------------------------
    const resizer = document.querySelector('#reader-resizer');
    const inbox = document.querySelector('#inbox');
    const syncResizerHeight = () => { resizer.style.height = reader.getBoundingClientRect().height + 'px'; };
    new ResizeObserver(syncResizerHeight).observe(reader);
    const widthKey = 'centromail-reader-width-custom';
    let customWidth = null;
    try {
        const stored = Number(localStorage.getItem(widthKey));
        if (Number.isFinite(stored) && stored >= 320) customWidth = stored;
    } catch { /* Storage can be unavailable in private mode. */ }
    const maxReaderWidth = () => Math.max(320, Math.min(Math.round(innerWidth * 0.75),
        Math.floor(inbox.getBoundingClientRect().width + reader.getBoundingClientRect().width - 280)));
    const clampReaderWidth = px => Math.max(320, Math.min(maxReaderWidth(), Math.round(px)));
    const applyReaderWidth = (px, persist = false) => {
        const width = clampReaderWidth(px);
        customWidth = width;
        // Scope the drag width to this page so appearance changes to the
        // shared root variable (theme, accent, reset) cannot overwrite it.
        app.style.setProperty('--cm-reader-width', width + 'px');
        resizer.setAttribute('aria-valuenow', String(width));
        if (persist) { try { localStorage.setItem(widthKey, String(width)); } catch { /* Ignore storage errors. */ } }
        return width;
    };
    const syncResizer = () => {
        resizer.hidden = reader.hidden || !desktop.matches;
        if (resizer.hidden) return;
        if (customWidth) applyReaderWidth(customWidth);
        syncResizerHeight();
        resizer.setAttribute('aria-valuemin', '320');
        resizer.setAttribute('aria-valuemax', String(maxReaderWidth()));
        resizer.setAttribute('aria-valuenow', String(Math.round(reader.getBoundingClientRect().width || customWidth || 640)));
    };
    if (customWidth) applyReaderWidth(customWidth);
    let resizing = false;
    let dragX, dragWidth, dragPointer;
    resizer.addEventListener('pointerdown', event => {
        if (event.button !== 0 || !desktop.matches || reader.hidden) return;
        dragX = event.clientX;
        dragWidth = reader.getBoundingClientRect().width;
        dragPointer = event.pointerId;
        resizing = true;
        resizer.setPointerCapture(event.pointerId);
        resizer.classList.add('is-dragging');
        document.body.classList.add('is-resizing-reader');
        event.preventDefault();
    });
    resizer.addEventListener('pointermove', event => {
        if (!resizing) return;
        applyReaderWidth(dragWidth + dragX - event.clientX);
    });
    const stopResize = () => {
        if (!resizing) return;
        resizing = false;
        resizer.classList.remove('is-dragging');
        document.body.classList.remove('is-resizing-reader');
        if (resizer.hasPointerCapture(dragPointer)) resizer.releasePointerCapture(dragPointer);
        applyReaderWidth(Number(resizer.getAttribute('aria-valuenow')), true);
    };
    resizer.addEventListener('pointerup', stopResize);
    resizer.addEventListener('pointercancel', stopResize);
    resizer.addEventListener('lostpointercapture', stopResize);
    resizer.addEventListener('keydown', event => {
        const step = event.shiftKey ? 100 : 25;
        let width = Number(resizer.getAttribute('aria-valuenow')) || customWidth || 640;
        if (event.key === 'ArrowLeft') width += step;
        else if (event.key === 'ArrowRight') width -= step;
        else if (event.key === 'Home') width = 320;
        else if (event.key === 'End') width = maxReaderWidth();
        else return;
        event.preventDefault();
        applyReaderWidth(width, true);
    });
    window.addEventListener('resize', () => { stopResize(); syncResizer(); });
    const setReaderOpen = open => {
        if (reader.hidden === !open) return;
        const update = () => {
            if (!open) stopResize();
            reader.hidden = !open;
            app.classList.toggle('has-reader', open);
            syncResizer();
        };
        if (window.CentroMailMotion?.readerLayout) window.CentroMailMotion.readerLayout(update);
        else update();
    };
    const closeReader = () => {
        readerController?.abort();
        readerController = null;
        setReaderOpen(false);
        readerContent.removeAttribute('aria-busy');
        rows().forEach(row => row.classList.remove('is-open'));
        const link = visibleRows().find(row => messageKey(row) === readerMessageKey)?.querySelector('.message-details');
        (link || list).focus();
        readerMessageKey = null;
    };
    const openMessage = async row => {
        if (!desktop.matches || window.CentroMailAppearance.get('reading-pane') === 'page') {
            window.location.assign(row.dataset.messageUrl);
            return;
        }
        rows().forEach(item => item.classList.toggle('is-open', item === row));
        setReaderOpen(true);
        readerMessageKey = messageKey(row);
        readerContent.setAttribute('aria-busy', 'true');
        readerStatus.textContent = 'Opening email…';
        reader.focus();
        document.querySelector('#reader-open-page').href = row.dataset.messageUrl;
        readerController?.abort();
        const pending = new AbortController();
        readerController = pending;
        const url = new URL(row.dataset.messageUrl, location.origin);
        url.searchParams.set('pane', '1');
        try {
            const response = await fetch(url, {signal: pending.signal});
            if (readerController !== pending || pending.signal.aborted) return;
            if (response.redirected) { window.location.assign(response.url); return; }
            const html = await response.text();
            if (readerController !== pending || pending.signal.aborted || reader.hidden) return;
            readerContent.replaceChildren(document.createRange().createContextualFragment(html));
            readerContent.scrollTop = 0;
            window.CentroMailMotion?.readerContent?.(readerContent);
            readerStatus.textContent = response.ok ? 'Email opened.' : 'Could not open this email.';
            if (!response.ok) return;
        } catch (error) {
            if (readerController === pending && error.name !== 'AbortError') {
                readerStatus.textContent = 'Could not open this email. Try again.';
                const notice = document.createElement('p');
                notice.className = 'reader-empty';
                notice.textContent = readerStatus.textContent;
                readerContent.replaceChildren(notice);
            }
        } finally {
            if (readerController === pending) readerContent.removeAttribute('aria-busy');
        }
    };
    const performAction = async (action, targets) => {
        if (action === 'trash' && window.CentroMailAppearance.get('confirm-actions') === 'true' && !confirm('Move the selected messages to Trash?')) return;
        if (actionPending || !targets.length) return;
        changeGeneration++; statusController?.abort();
        const actionButton = document.activeElement.closest('[data-mail-action]');
        const groups = new Map();
        for (const row of targets) {
            const account = row.dataset.mailAccount || app.dataset.account;
            const sourceFolder = row.dataset.mailFolder || folder;
            if (!account || account === 'all') { showFeedback('Refresh the inbox before changing these messages.'); return; }
            const key = JSON.stringify([account, sourceFolder]);
            if (!groups.has(key)) groups.set(key, {account, folder: sourceFolder, rows: []});
            groups.get(key).rows.push(row);
        }
        actionPending = true;
        targets.forEach(row => row.querySelector('.star-button').disabled = true);
        updateSelection();
        showFeedback('Updating messages…');
        let updated = 0, failed = 0, firstError, reconnect = false;
        try {
            for (const group of groups.values()) {
                const data = new URLSearchParams({action, csrf_token: app.dataset.csrf, account: group.account, folder: group.folder});
                group.rows.forEach(row => data.append('message_ids', row.dataset.messageId));
                try {
                    await readJson(await fetch(app.dataset.actionsUrl, {method: 'POST', body: data}));
                } catch (error) {
                    failed += group.rows.length;
                    firstError ||= error;
                    reconnect ||= error.reconnect;
                    continue;
                }
                updated += group.rows.length;
                const affected = new Set(group.rows.map(messageKey));
                rows().filter(row => affected.has(messageKey(row))).forEach(row => {
                    if (action === 'read' || action === 'unread') {
                        row.classList.toggle('unread', action === 'unread');
                        row.querySelector('.message-read-state').textContent = action === 'unread' ? 'Unread: ' : '';
                    }
                    if (action === 'star' || action === 'unstar') {
                        const star = row.querySelector('.star-button');
                        star.classList.toggle('starred', action === 'star');
                        star.setAttribute('aria-pressed', String(action === 'star'));
                        star.setAttribute('aria-label', `${action === 'star' ? 'Unstar' : 'Star'} message: ${row.querySelector('.message-subject').textContent}`);
                    }
                    if ((action === 'trash' && group.folder !== 'trash') || (action === 'archive' && group.folder === 'inbox') ||
                        (action === 'restore' && group.folder === 'trash') || (action === 'unstar' && group.folder === 'starred')) {
                        if (row.classList.contains('is-open')) closeReader();
                        const restoreFocus = row.contains(document.activeElement);
                        row.remove();
                        if (restoreFocus) list.focus();
                    }
                    row.querySelector('.message-check').checked = false;
                });
            }
            const success = updated ? `${updated} message${updated === 1 ? '' : 's'} updated.` : '';
            const failure = failed ? `${failed} message${failed === 1 ? '' : 's'} could not be updated. ${firstError.message}` : '';
            showFeedback([success, failure].filter(Boolean).join(' '), reconnect);
            applyFilters();
            if (updated) loadCounts(true);
        } finally {
            actionPending = false;
            targets.forEach(row => row.querySelector('.star-button').disabled = false);
            updateSelection();
            if (actionButton && (document.activeElement === document.body || document.activeElement === actionButton)) {
                (selected().length ? actionButton : selectAll.disabled ? list : selectAll).focus({preventScroll:true});
            }
        }
    };
    list.addEventListener('click', event => {
        const row = event.target.closest('.message');
        if (!row) return;
        const star = event.target.closest('.star-button');
        if (star) { performAction(star.classList.contains('starred') ? 'unstar' : 'star', [row]); return; }
        if (event.target.closest('input, label, button') || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        openMessage(row);
    });
    list.addEventListener('change', updateSelection);
    selectAll.addEventListener('change', () => {
        visibleRows().forEach(row => row.querySelector('.message-check').checked = selectAll.checked);
        updateSelection();
    });
    document.querySelectorAll('[data-mail-action]').forEach(button => {
        button.addEventListener('click', () => performAction(button.dataset.mailAction, selected()));
    });
    document.querySelector('#refresh-mail-form').addEventListener('submit', event => {
        event.preventDefault();
        loadMessages({reset: true, force: true});
    });
    more.addEventListener('click', () => loadMessages({reset: failed && cursor === null}));
    search.addEventListener('input', () => {
        clearTimeout(searchTimer);
        if (!search.disabled) searchTimer = setTimeout(() => { if (!search.disabled) loadMessages({reset: true}); }, 350);
    });
    const tabs = [...document.querySelectorAll('.inbox-tab')];
    tabs.forEach((tab, index) => {
        tab.addEventListener('click', () => {
            tabs.forEach(item => {
                item.classList.toggle('active', item === tab);
                item.setAttribute('aria-selected', String(item === tab));
                item.tabIndex = item === tab ? 0 : -1;
            });
            list.setAttribute('aria-labelledby', tab.id);
            loadMessages({reset: true});
        });
        tab.addEventListener('keydown', event => {
            let next;
            if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
            if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
            if (event.key === 'Home') next = 0;
            if (event.key === 'End') next = tabs.length - 1;
            if (next !== undefined) { event.preventDefault(); tabs[next].focus(); tabs[next].click(); }
        });
    });
    if ('IntersectionObserver' in window) {
        const observer = new IntersectionObserver(entries => {
            if (entries.some(entry => entry.isIntersecting) && !failed) loadMessages();
        }, {rootMargin: '300px'});
        observer.observe(document.querySelector('#mail-load-sentinel'));
    }
    document.querySelector('#close-reader').addEventListener('click', closeReader);
    reader.addEventListener('keydown', event => { if (event.key === 'Escape') { event.preventDefault(); closeReader(); } });
    desktop.addEventListener('change', () => {
        syncResizer();
        if (!desktop.matches && !reader.hidden) window.location.assign(document.querySelector('#reader-open-page').href);
    });
    const help = document.querySelector('#mail-help-dialog');
    document.querySelector('#mail-help-button').addEventListener('click', () => help.showModal());
    document.querySelector('#close-mail-help').addEventListener('click', () => help.close());
    help.addEventListener('click', event => { if (event.target === help) help.close(); });
    document.querySelector('#show-shortcuts').addEventListener('click', () => { help.close(); window.CentroMailShortcuts?.show(); });
    document.querySelector('.profile-button img')?.addEventListener('error', event => {
        event.target.hidden = true;
        const initials = document.createElement('span');
        initials.textContent = document.querySelector('.profile-button').dataset.initial;
        event.target.replaceWith(initials);
    });

    let refreshTimer;
    const scheduleRefresh = () => {
    clearInterval(refreshTimer);
    refreshTimer = setInterval(() => {
        if (localStorage.getItem('centromail-auto-refresh') !== 'false' && document.visibilityState === 'visible' &&
            !search.disabled && !loading && !actionPending && !list.contains(document.activeElement) && !reader.contains(document.activeElement) && selected().length === 0 && rows().length <= 25 && !search.value.trim()) {
            loadMessages({reset: true, force: true});
        } else if (window.CentroMailAppearance.get('auto-refresh') !== 'false') syncGmailStatus();
    }, Number(window.CentroMailAppearance.get('refresh-interval')) * 1000);
    };
    document.addEventListener('centromail-appearance-change', scheduleRefresh);
    window.addEventListener('focus', syncGmailStatus);
    document.addEventListener('visibilitychange', () => { if (document.hidden) statusController?.abort(); else syncGmailStatus(); });
    document.querySelector('#workspace-tab-email').addEventListener('click', syncGmailStatus);
    scheduleRefresh();
    syncSort();
    applyFilters();
    loadMessages({reset: true, force: new URLSearchParams(location.search).get('refresh') === '1'});
    loadCounts();

    // Keyboard shortcuts -------------------------------------------------
    const shortcuts = window.CentroMailShortcuts;
    if (shortcuts) {
        const composeButton = document.querySelector('#open-compose');
        const focusedRow = () => list.querySelector('.message.is-focused');
        const focusRow = delta => {
            const all = visibleRows();
            if (!all.length) return;
            const next = focusedIndex < 0 ? (delta > 0 ? 0 : all.length - 1) :
                Math.min(all.length - 1, Math.max(0, focusedIndex + delta));
            clearFocusedRow();
            focusedIndex = next;
            const row = all[focusedIndex];
            row.classList.add('is-focused');
            row.scrollIntoView({block: 'nearest'});
            row.querySelector('.message-details').focus({preventScroll: true});
        };
        const selectFocused = () => {
            const row = focusedRow();
            if (!row) return null;
            const checkbox = row.querySelector('.message-check');
            if (!checkbox.checked) { checkbox.checked = true; updateSelection(); }
            return row;
        };
        list.addEventListener('focusin', event => {
            const row = event.target.closest('.message');
            if (!row) return;
            list.querySelectorAll('.message.is-focused').forEach(item => item.classList.remove('is-focused'));
            row.classList.add('is-focused');
            focusedIndex = visibleRows().indexOf(row);
        });
        list.addEventListener('keydown', event => {
            if (event.key === 'ArrowDown') { event.preventDefault(); focusRow(1); }
            else if (event.key === 'ArrowUp') { event.preventDefault(); focusRow(-1); }
        });
        shortcuts.register('c', () => composeButton.click(), 'Compose a new email', 'Inbox');
        shortcuts.register('j', () => focusRow(1), 'Move to next message', 'Inbox');
        shortcuts.register('k', () => focusRow(-1), 'Move to previous message', 'Inbox');
        shortcuts.register('enter', () => { const row = focusedRow(); if (row) openMessage(row); }, 'Open the focused message', 'Inbox');
        shortcuts.register('s', () => focusedRow()?.querySelector('.star-button').click(), 'Star or unstar the focused message', 'Inbox');
        shortcuts.register('x', () => focusedRow()?.querySelector('.message-check').click(), 'Select the focused message', 'Inbox');
        shortcuts.register('e', () => {
            if (!selectFocused()) return;
            const action = folder === 'trash' ? 'restore' : 'archive';
            document.querySelector(`[data-mail-action="${action}"]`)?.click();
        }, 'Archive the focused message', 'Inbox');
        shortcuts.register('#', () => {
            if (selectFocused()) document.querySelector('[data-mail-action="trash"]')?.click();
        }, 'Move the focused message to Trash', 'Inbox');
        shortcuts.register('u', () => {
            const row = selectFocused();
            if (!row) return;
            const action = row.classList.contains('unread') ? 'read' : 'unread';
            document.querySelector(`[data-mail-action="${action}"]`)?.click();
        }, 'Mark the focused message read or unread', 'Inbox');
        shortcuts.register('r', () => {
            const row = focusedRow() || rows().find(item => item.classList.contains('is-open'));
            if (!row) return;
            if (reader.hidden) { openMessage(row); return; }
            const reply = reader.querySelector('[data-email-reply]');
            if (reply && !reply.disabled) reply.click();
        }, 'Reply to the focused message', 'Inbox');
    }
})();
