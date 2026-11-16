(() => {
    const buttons = [...document.querySelectorAll('[data-app-provider]')];
    if (!buttons.length) return;
    const feed = document.querySelector('#apps-feed-messages');
    const status = document.querySelector('#apps-feed-status');
    const refresh = document.querySelector('#refresh-app-feed');
    const loading = document.querySelector('#apps-feed-loading');
    let selected, controller;
    const load = async button => {
        selected = button;
        window.CentroMailTelegram.close();
        controller?.abort();
        controller = null;
        buttons.forEach(item => item.setAttribute('aria-pressed', String(item === button)));
        document.querySelector('#apps-feed-title').textContent = button.dataset.appName;
        feed.replaceChildren();
        loading.hidden = true;
        if (!button.dataset.appFeed) {
            refresh.disabled = true;
            feed.removeAttribute('aria-busy');
            status.textContent = 'Connected. Manage this integration to see its available actions.';
            return;
        }
        const pending = new AbortController();
        controller = pending;
        const timeout = setTimeout(() => pending.abort(), 30000);
        refresh.disabled = true;
        status.textContent = 'Loading recent messages…';
        feed.setAttribute('aria-busy','true');
        loading.hidden = false;
        try {
            const response = await fetch(button.dataset.appFeed,{signal:pending.signal});
            if (response.redirected) { location.assign(response.url); return; }
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Messages could not be loaded.');
            if (selected !== button || controller !== pending) return;
            if (button.dataset.appProvider === 'telegram') {
                window.CentroMailTelegram.open(data.messages || []);
                status.textContent = 'Your recent Telegram conversations.';
                return;
            }
            for (const message of data.messages || []) {
                const row = document.createElement('article');
                row.className = 'apps-feed-message';
                for (const [tag, value] of [['strong',message.sender],['time',message.time],['p',message.text]]) {
                    const element = document.createElement(tag);
                    element.textContent = value || '';
                    row.append(element);
                }
                feed.append(row);
            }
            status.textContent = feed.children.length ? `${feed.children.length} recent ${feed.children.length === 1 ? 'message' : 'messages'}.` : 'No recent messages yet.';
        } catch (error) {
            if (controller === pending) status.textContent = error.name === 'AbortError' ? 'Loading took too long. Try Refresh.' : error.message;
        } finally {
            clearTimeout(timeout);
            if (controller === pending) { refresh.disabled = false; feed.removeAttribute('aria-busy'); loading.hidden = true; }
        }
    };
    buttons.forEach(button => button.addEventListener('click', () => load(button)));
    refresh.addEventListener('click', () => { if (selected) load(selected); });
    document.querySelector('#workspace-tab-apps').addEventListener('click', () => { if (!selected) load(buttons[0]); });
})();
