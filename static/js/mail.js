(() => {
    const app = document.querySelector('.gmail-app');
    if (!app) return;
    const navigation = document.querySelector('.site-header');
    const masthead = app.querySelector('.gmail-header');
    const syncHeaders = () => {
        for (const [element, property] of [[navigation, '--mail-nav-height'], [masthead, '--mail-search-height']]) {
            app.style.setProperty(property, getComputedStyle(element).position === 'sticky' ? element.getBoundingClientRect().height + 'px' : '0px');
        }
    };
    const headerObserver = new ResizeObserver(syncHeaders);
    headerObserver.observe(navigation);
    headerObserver.observe(masthead);
    document.addEventListener('centromail-appearance-change', syncHeaders);
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
    let cursor = null, hasMore = true, loading = false, failed = false;
    let generation = 0, controller, searchTimer, readerController;
    let actionPending = false, readerMessageId;
    let statusController, statusOffset = 0, changeGeneration = 0;
    const rows = () => [...list.querySelectorAll('.message')];
    const sort = document.querySelector('#mail-sort');
    const sortMessages = () => {
        const active = document.activeElement;
        const order = row => sort.value === 'replyable' ? Number(row.dataset.canReply !== 'true') :
            sort.value === 'noreply' ? Number(row.dataset.noReply !== 'true') : 0;
        const sorted = rows().sort((a, b) => order(a) - order(b) || Number(b.dataset.messageTime) - Number(a.dataset.messageTime));
        sorted.forEach((row, index) => {
            if (list.children[index] !== row) list.insertBefore(row, list.children[index] || null);
        });
        if (list.contains(active) && document.activeElement !== active) active.focus({preventScroll: true});
    };
    const syncSort = () => {
        sort.value = window.CentroMailAppearance.get('mail-sort');
        sortMessages();
    };
    sort.addEventListener('change', () => window.CentroMailAppearance.set('mail-sort', sort.value));
    document.addEventListener('centromail-appearance-change', syncSort);
    const selected = () => rows().filter(row => row.querySelector('.message-check').checked);
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
        selectAll.checked = rows().length > 0 && count === rows().length;
        selectAll.indeterminate = count > 0 && count < rows().length;
        selectAll.disabled = rows().length === 0 || actionPending;
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
        if (event.detail.account === app.dataset.account) { changeGeneration++; statusController?.abort(); loadCounts(true); }
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
            if (reset) list.replaceChildren(fragment);
            else {
                const known = new Set(rows().map(row => row.dataset.messageId));
                fragment.querySelectorAll('.message').forEach(row => {
                    if (known.has(row.dataset.messageId)) row.remove();
                });
                list.append(fragment);
            }
            sortMessages();
            const previousCursor = cursor;
            cursor = data.next_cursor;
            hasMore = Boolean(cursor) && cursor !== previousCursor;
            failed = false;
            showFeedback('');
            const count = rows().length;
            document.querySelector('#mail-page-count').textContent = hasMore ? `${count} loaded${data.total == null ? '' : ` · about ${data.total} total`}` : `${count} messages`;
            document.querySelector('#empty-state').hidden = count > 0;
            document.querySelector('#empty-state').textContent = search.value.trim() ? 'No messages match your search.' : 'No messages in this folder.';
            status.textContent = hasMore ? 'Scroll to load more messages.' : (count ? 'All messages loaded.' : '');
            updateSelection();
            if (force) loadCounts(true);
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
    const closeReader = () => {
        readerController?.abort();
        reader.hidden = true;
        app.classList.remove('has-reader');
        rows().forEach(row => row.classList.remove('is-open'));
        const link = rows().find(row => row.dataset.messageId === readerMessageId)?.querySelector('.message-details');
        (link || list).focus();
        readerMessageId = null;
    };
    const openMessage = async row => {
        if (!desktop.matches || window.CentroMailAppearance.get('reading-pane') === 'page') {
            window.location.assign(row.dataset.messageUrl);
            return;
        }
        rows().forEach(item => item.classList.toggle('is-open', item === row));
        reader.hidden = false;
        app.classList.add('has-reader');
        readerMessageId = row.dataset.messageId;
        readerContent.textContent = '';
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
            if (response.redirected) { window.location.assign(response.url); return; }
            const html = await response.text();
            if (readerController !== pending) return;
            readerContent.replaceChildren(document.createRange().createContextualFragment(html));
            readerStatus.textContent = response.ok ? 'Email opened.' : 'Could not open this email.';
            if (!response.ok) return;
        } catch (error) {
            if (readerController === pending && error.name !== 'AbortError') readerStatus.textContent = 'Could not open this email. Try again.';
        }
    };
    const performAction = async (action, targets) => {
        if (action === 'trash' && window.CentroMailAppearance.get('confirm-actions') === 'true' && !confirm('Move the selected messages to Trash?')) return;
        if (actionPending || !targets.length) return;
        changeGeneration++; statusController?.abort();
        const actionButton = document.activeElement.closest('[data-mail-action]');
        const data = new URLSearchParams({action, csrf_token: app.dataset.csrf, account: app.dataset.account, folder});
        targets.forEach(row => data.append('message_ids', row.dataset.messageId));
        actionPending = true;
        targets.forEach(row => row.querySelector('.star-button').disabled = true);
        updateSelection();
        showFeedback('Updating messages…');
        try {
            await readJson(await fetch(app.dataset.actionsUrl, {method: 'POST', body: data}));
            targets.forEach(row => {
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
                if ((action === 'trash' && folder !== 'trash') || (action === 'archive' && folder === 'inbox') ||
                    (action === 'restore' && folder === 'trash') || (action === 'unstar' && folder === 'starred')) {
                    if (row.classList.contains('is-open')) closeReader();
                    const restoreFocus = row.contains(document.activeElement);
                    row.remove();
                    if (restoreFocus) list.focus();
                }
                row.querySelector('.message-check').checked = false;
            });
            showFeedback(`${targets.length} message${targets.length === 1 ? '' : 's'} updated.`);
            document.querySelector('#empty-state').hidden = rows().length > 0;
            loadCounts(true);
        } catch (error) {
            showFeedback(error.message, error.reconnect);
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
        rows().forEach(row => row.querySelector('.message-check').checked = selectAll.checked);
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
        if (!desktop.matches && !reader.hidden) window.location.assign(document.querySelector('#reader-open-page').href);
    });
    const help = document.querySelector('#mail-help-dialog');
    document.querySelector('#mail-help-button').addEventListener('click', () => help.showModal());
    document.querySelector('#close-mail-help').addEventListener('click', () => help.close());
    help.addEventListener('click', event => { if (event.target === help) help.close(); });
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
    updateSelection();
    loadMessages({reset: true, force: new URLSearchParams(location.search).get('refresh') === '1'});
    loadCounts();
})();
