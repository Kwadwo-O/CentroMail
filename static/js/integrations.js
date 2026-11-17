(() => {
    const page = document.querySelector('.integrations-page');
    if (!page) return;
    const cards = [...page.querySelectorAll('[data-integration-app]')];
    const search = page.querySelector('#integration-search');
    const connected = page.querySelector('#integration-connected-filter');
    const categories = [...page.querySelectorAll('[data-integration-category]')];
    let category = 'all';
    const filter = () => {
        const query = search.value.trim().toLowerCase();
        let count = 0;
        for (const card of cards) {
            card.hidden = !(card.dataset.search.includes(query) &&
                (category === 'all' || card.dataset.category === category) &&
                (connected.getAttribute('aria-pressed') !== 'true' || card.dataset.connected === 'true'));
            if (!card.hidden) count++;
        }
        page.querySelector('#integration-results').textContent = `${count} ${count === 1 ? 'app' : 'apps'}`;
        page.querySelector('#integration-empty').hidden = count !== 0;
    };
    search.addEventListener('input', filter);
    connected.addEventListener('click', () => {
        connected.setAttribute('aria-pressed', String(connected.getAttribute('aria-pressed') !== 'true'));
        filter();
    });
    const selectCategory = value => {
        category = value;
        for (const button of categories) {
            const selected = button.dataset.integrationCategory === category;
            button.setAttribute('aria-pressed', String(selected));
            button.classList.toggle('m3e-button--tonal', selected);
            button.classList.toggle('m3e-button--text', !selected);
        }
        filter();
    };
    for (const button of categories) button.addEventListener('click', () => selectCategory(button.dataset.integrationCategory));
    page.querySelector('#integration-reset').addEventListener('click', () => {
        search.value = '';
        connected.setAttribute('aria-pressed', 'false');
        selectCategory('all');
        search.focus();
    });
    let opener;
    const open = (key, trigger) => {
        const dialog = document.getElementById('integration-dialog-' + key);
        if (!dialog) return;
        opener = trigger || page.querySelector(`[data-integration-open="${key}"]`);
        if (dialog.open) dialog.close();
        dialog.showModal();
        dialog.scrollTop = 0;
        dialog.querySelector('h2').focus({preventScroll: true});
    };
    for (const link of page.querySelectorAll('[data-integration-open]')) {
        link.addEventListener('click', event => {
            if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
            event.preventDefault();
            open(link.dataset.integrationOpen, link);
        });
    }
    for (const dialog of page.querySelectorAll('dialog')) {
        dialog.querySelector('[data-integration-close]').addEventListener('click', () => dialog.close());
        dialog.addEventListener('close', () => {
            if (opener && !opener.closest('[hidden]')) opener.focus({preventScroll: true});
        });
        dialog.addEventListener('click', event => {
            const rect = dialog.getBoundingClientRect();
            if (event.target === dialog && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) dialog.close();
        });
    }
    if (page.dataset.openIntegration) open(page.dataset.openIntegration);
    for (const form of page.querySelectorAll('form[data-confirm]')) {
        form.addEventListener('submit', event => { if (!window.confirm(form.dataset.confirm)) event.preventDefault(); });
    }
    for (const button of page.querySelectorAll('[data-integration-check]')) {
        button.addEventListener('click', async () => {
            const status = button.closest('.integration-manage-actions').querySelector('.integration-check-status');
            const loading = button.parentElement.querySelector('m3e-loading-indicator');
            const controller = new AbortController();
            const timeout = setTimeout(() => controller.abort(), 60000);
            button.disabled = true;
            button.setAttribute('aria-busy', 'true');
            loading.hidden = false;
            status.dataset.error = 'false';
            status.textContent = 'Checking account access…';
            try {
                const response = await fetch(button.dataset.integrationCheck, {method: 'POST',
                    body: new URLSearchParams({csrf_token: button.dataset.csrf}), signal: controller.signal});
                if (response.redirected) { location.assign(response.url); return; }
                const data = await response.json();
                if (!response.ok) throw new Error(data.error || 'Access could not be confirmed. Reconnect this app.');
                status.textContent = data.message;
                window.CentroMailMotion?.feedback(button, 'selection');
            } catch (error) {
                status.dataset.error = 'true';
                status.textContent = error.name === 'AbortError' ? 'The check took too long. Try again.' : error.message;
            } finally {
                clearTimeout(timeout);
                button.disabled = false;
                button.removeAttribute('aria-busy');
                loading.hidden = true;
            }
        });
    }
})();
