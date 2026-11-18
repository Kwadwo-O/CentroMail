(() => {
    const button = document.querySelector('#scan-promotions');
    if (!button) return;

    const status = document.querySelector('#cleanup-status');
    const results = document.querySelector('#cleanup-results');
    const list = document.querySelector('#cleanup-message-list');
    const empty = document.querySelector('#cleanup-empty');
    const trashAll = document.querySelector('#cleanup-trash-all');
    const progress = document.querySelector('#cleanup-progress');
    const progressTrack = progress.querySelector('.cleanup-progress-track');
    const progressFill = document.querySelector('#cleanup-progress-fill');
    const progressCount = document.querySelector('#cleanup-progress-count');
    const elapsedLabel = document.querySelector('#cleanup-elapsed');
    const stateKey = `centromail-cleanup:${button.dataset.account}`;
    const setStatus = message => { status.textContent = message; };
    const showReconnect = message => {
        status.replaceChildren(document.createTextNode(`${message} `));
        const reconnect = document.createElement('a');
        reconnect.href = button.dataset.reconnectUrl;
        reconnect.textContent = 'Reconnect Gmail';
        status.append(reconnect);
    };
    const saveState = state => sessionStorage.setItem(stateKey, JSON.stringify(state));
    const loadState = () => {
        const saved = sessionStorage.getItem(stateKey);
        if (!saved) return null;
        try {
            return JSON.parse(saved);
        } catch {
            sessionStorage.removeItem(stateKey);
            return null;
        }
    };
    const readJson = async response => {
        if (response.redirected) throw new Error('Your session expired. Sign in again to continue.');
        if (!response.headers.get('content-type')?.includes('application/json')) {
            throw new Error(`The cleanup request failed (HTTP ${response.status}). Please try again.`);
        }
        return response.json();
    };
    const fetchCleanupJson = async (url, options = {}) => {
        let response, data;
        for (let attempt = 0; ; attempt += 1) {
            response = await fetch(url, {
                ...options,
                headers: {Accept: 'application/json', ...options.headers},
                credentials: 'same-origin'
            });
            data = await readJson(response);
            if (!data.retryable || attempt >= 3) break;
            const delay = 1000 * (2 ** attempt);
            setStatus(`Gmail is temporarily limiting requests. Retrying in ${delay / 1000} seconds…`);
            await new Promise(resolve => window.setTimeout(resolve, delay));
        }
        if (data.refresh_required) {
            setStatus('Gmail access expired. Reconnecting to Gmail…');
            const refreshResponse = await fetch(button.dataset.refreshUrl, {
                method: 'POST',
                headers: {
                    Accept: 'application/json',
                    'Content-Type': 'application/x-www-form-urlencoded'
                },
                body: new URLSearchParams({csrf_token: button.dataset.csrf}),
                credentials: 'same-origin'
            });
            const refreshData = await readJson(refreshResponse);
            if (!refreshResponse.ok) {
                if (refreshData.reconnect) {
                    showReconnect(refreshData.error);
                    const error = new Error(refreshData.error);
                    error.handled = true;
                    throw error;
                }
                throw new Error(refreshData.error || 'Could not reconnect to Gmail.');
            }
            setStatus('Gmail reconnected. Continuing the scan…');
            response = await fetch(url, {
                ...options,
                headers: {Accept: 'application/json', ...options.headers},
                credentials: 'same-origin'
            });
            data = await readJson(response);
            if (data.refresh_required) throw new Error('Gmail access expired again. Please try the scan once more.');
        }
        if (!response.ok) {
            if (data.retryable) throw new Error(data.error || 'Gmail is still limiting requests. Please retry the scan shortly.');
            if (data.reconnect) {
                showReconnect(data.error);
                const error = new Error(data.error);
                error.handled = true;
                throw error;
            }
            throw new Error(data.error || `The cleanup request failed (HTTP ${response.status}).`);
        }
        return data;
    };
    const updateProgress = (checked, total) => {
        const percent = total ? Math.round(checked * 100 / total) : 100;
        progressTrack.classList.remove('is-indeterminate');
        progressTrack.removeAttribute('aria-valuetext');
        progressTrack.setAttribute('aria-valuenow', String(percent));
        progressFill.style.width = `${percent}%`;
        progressCount.textContent = total
            ? `Checked ${checked} of ${total} emails (${percent}%)`
            : 'No promotional emails to check (100%)';
    };
    const addMessages = messages => {
        for (const message of messages) {
            const row = document.createElement('tr');
            const sender = document.createElement('td');
            const subject = document.createElement('td');
            const date = document.createElement('td');
            const subjectText = document.createElement('strong');
            const preview = document.createElement('span');

            row.dataset.messageId = message.id;
            sender.textContent = message.sender || 'Unknown sender';
            subjectText.textContent = message.subject || '(No subject)';
            preview.textContent = message.preview || '';
            preview.className = 'cleanup-preview-text';
            subject.append(subjectText, preview);
            date.textContent = message.date || 'Unknown date';
            row.append(sender, subject, date);
            list.append(row);
        }
    };
    const formatElapsed = milliseconds => {
        const seconds = Math.floor(milliseconds / 1000);
        return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
    };

    const scan = async resume => {
        let state = resume ? loadState() : null;
        if (!state) {
            sessionStorage.removeItem(stateKey);
            state = {messageIds: null, nextOffset: 0, checked: 0, messages: [], startedAt: Date.now()};
        }
        const startedAt = state.startedAt || Date.now();
        let completed = false;
        let reconnecting = false;
        const updateElapsed = () => { elapsedLabel.textContent = `Elapsed ${formatElapsed(Date.now() - startedAt)}`; };
        updateElapsed();
        const elapsedTimer = window.setInterval(updateElapsed, 1000);
        button.disabled = true;
        button.setAttribute('aria-busy', 'true');
        setStatus(resume ? 'Resuming promotional email scan…' : 'Scanning Gmail promotions…');
        progress.hidden = false;
        progressTrack.classList.add('is-indeterminate');
        progressTrack.setAttribute('aria-valuetext', state.messageIds ? 'Checking promotional emails' : 'Finding promotional emails');
        progressFill.style.width = '';
        progressCount.textContent = state.messageIds ? 'Resuming scan…' : 'Finding promotional emails…';
        list.replaceChildren();
        addMessages(state.messages || []);
        if (state.messageIds) {
            updateProgress(state.checked, state.messageIds.length);
            results.hidden = false;
            empty.hidden = true;
        } else {
            results.hidden = true;
        }

        try {
            if (!state.messageIds) {
                const data = await fetchCleanupJson(button.dataset.scanUrl);
                state.messageIds = data.message_ids || [];
                saveState(state);
            }
            const total = state.messageIds.length;
            updateProgress(state.checked, total);
            setStatus(total ? `Checking ${total} promotional ${total === 1 ? 'email' : 'emails'}…` : 'No promotional emails found.');

            for (let offset = state.nextOffset; offset < total; offset += 50) {
                const batch = state.messageIds.slice(offset, offset + 50);
                const detailsUrl = new URL(button.dataset.detailsUrl, window.location.href);
                batch.forEach(id => detailsUrl.searchParams.append('message_ids', id));
                let detailData;
                try {
                    detailData = await fetchCleanupJson(detailsUrl);
                } catch (error) {
                    if (error.handled) {
                        reconnecting = true;
                        saveState(state);
                    }
                    throw error;
                }

                const batchMessages = detailData.messages || [];
                addMessages(batchMessages);
                state.messages.push(...batchMessages);
                state.checked += detailData.checked;
                state.nextOffset = offset + batch.length;
                saveState(state);
                updateProgress(state.checked, total);
                results.hidden = false;
                empty.hidden = true;
                setStatus(`Checking promotional emails: ${state.checked} of ${total} (${Math.round(state.checked * 100 / total)}%).`);
            }

            empty.hidden = list.children.length !== 0;
            results.hidden = false;
            setStatus(`Scan finished in ${formatElapsed(Date.now() - startedAt)}. Checked ${total} emails; ${list.children.length} matched the promotion rules. Nothing has been changed.`);
            completed = true;
            trashAll.hidden = list.children.length === 0;
        } catch (error) {
            if (!error.handled) {
                setStatus(`Scan stopped after ${formatElapsed(Date.now() - startedAt)}. ${error.message || 'Could not scan promotional emails.'}`);
            }
        } finally {
            window.clearInterval(elapsedTimer);
            updateElapsed();
            progressTrack.classList.remove('is-indeterminate');
            if (!completed && !reconnecting) progressCount.textContent += ' · Scan stopped';
            button.disabled = false;
            button.removeAttribute('aria-busy');
        }
    };

    button.addEventListener('click', () => scan(false));
    if (button.dataset.resume === 'true' && loadState()) scan(true);

    trashAll.addEventListener('click', async () => {
        const messageIds = [...list.querySelectorAll('tr[data-message-id]')].map(row => row.dataset.messageId);
        if (!messageIds.length || !window.confirm(`Move ${messageIds.length} promotional emails to Gmail Trash? They will also disappear from your CentroMail inbox.`)) return;

        trashAll.disabled = true;
        button.disabled = true;
        progress.hidden = false;
        progressTrack.classList.add('is-indeterminate');
        progressTrack.setAttribute('aria-valuetext', 'Moving messages to Gmail Trash');
        progressFill.style.width = '';
        progressCount.textContent = `Moving ${messageIds.length} messages to Gmail Trash. Please wait…`;
        setStatus(`Moving ${messageIds.length} messages to Gmail Trash…`);
        const body = new URLSearchParams({
            account: button.dataset.account,
            action: 'trash',
            csrf_token: button.dataset.csrf
        });
        messageIds.forEach(id => body.append('message_ids', id));

        try {
            const data = await fetchCleanupJson(button.dataset.trashUrl, {
                method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body
            });
            const moved = new Set(data.ids || []);
            list.querySelectorAll('tr[data-message-id]').forEach(row => {
                if (moved.has(row.dataset.messageId)) row.remove();
            });
            empty.hidden = list.children.length !== 0;
            trashAll.hidden = list.children.length === 0;
            sessionStorage.removeItem(stateKey);
            progressTrack.classList.remove('is-indeterminate');
            progressTrack.removeAttribute('aria-valuetext');
            progressTrack.setAttribute('aria-valuenow', '100');
            progressFill.style.width = '100%';
            progressCount.textContent = `Moved ${data.trashed} of ${messageIds.length} messages to Gmail Trash.`;
            setStatus(`${data.trashed} message${data.trashed === 1 ? '' : 's'} moved to Gmail Trash. They are now in Gmail Trash and removed from your CentroMail inbox.${data.skipped ? ` ${data.skipped} message${data.skipped === 1 ? '' : 's'} were no longer eligible and were skipped.` : ''}`);
        } catch (error) {
            progressTrack.classList.remove('is-indeterminate');
            progressTrack.setAttribute('aria-valuetext', 'Trash status could not be confirmed');
            progressCount.textContent = 'Could not confirm the move. Check Gmail Trash before trying again.';
            if (!error.handled) setStatus(error.message || 'Could not move emails to Trash. Check Gmail Trash before trying again.');
        } finally {
            trashAll.disabled = false;
            button.disabled = false;
        }
    });
})();
