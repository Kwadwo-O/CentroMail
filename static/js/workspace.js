(() => {
    const buttons = [...document.querySelectorAll('[data-app-provider]')];
    const appsTab = document.querySelector('#workspace-tab-apps');
    if (!buttons.length) {
        if (location.hash === '#apps') appsTab.click();
        return;
    }
    const feed = document.querySelector('#apps-feed-messages');
    const status = document.querySelector('#apps-feed-status');
    const refresh = document.querySelector('#refresh-app-feed');
    const loading = document.querySelector('#apps-feed-loading');
    const connectionPrompt = document.querySelector('#apps-connection-prompt');
    const stylesheet = document.querySelector('#chat-styles');
    let chatStyles;
    const loadChatStyles = () => chatStyles ??= new Promise((resolve, reject) => {
        const link = stylesheet.content.firstElementChild.cloneNode();
        link.addEventListener('load', resolve, {once: true});
        link.addEventListener('error', () => {
            link.remove();
            chatStyles = null;
            reject(new Error('Chat styles could not be loaded. Try Refresh.'));
        }, {once: true});
        stylesheet.after(link);
    });
    const clients = {
        telegram: () => import('./telegram-chat.js').then(() => window.CentroMailTelegram),
        teams: () => Promise.all([import('./teams-chat.js'), loadChatStyles()]).then(() => window.CentroMailTeams),
        'google-chat': () => Promise.all([import('./google-chat.js'), loadChatStyles()]).then(() => window.CentroMailGoogleChat),
    };
    let selected, controller, activeClient;
    const load = async button => {
        selected = button;
        activeClient?.close();
        activeClient = null;
        controller?.abort();
        controller = null;
        buttons.forEach(item => item.setAttribute('aria-pressed', String(item === button)));
        document.querySelector('#apps-feed-title').textContent = button.dataset.appName;
        feed.replaceChildren();
        loading.hidden = true;
        connectionPrompt.hidden = true;
        if (button.dataset.appConnected === 'false') {
            connectionPrompt.hidden = false;
            refresh.disabled = true;
            feed.removeAttribute('aria-busy');
            status.textContent = 'Connect Google Chat to open your conversations and spaces.';
            return;
        }
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
            const provider = button.dataset.appProvider;
            const cancelled = new Promise((_, reject) => {
                pending.signal.addEventListener('abort', () => reject(pending.signal.reason), {once: true});
            });
            const [response, client] = await Promise.race([cancelled, Promise.all([
                fetch(button.dataset.appFeed, {signal: pending.signal}),
                clients[provider]?.(),
            ])]);
            if (controller !== pending) return;
            if (response.redirected) { location.assign(response.url); return; }
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Messages could not be loaded.');
            if (controller !== pending) return;
            activeClient = client;
            if (provider === 'telegram') {
                client.open(data.messages || []);
                status.textContent = 'Your recent Telegram conversations.';
                return;
            }
            if (provider === 'teams') {
                client.open(data);
                status.textContent = 'Your Teams chats and team channels.';
                return;
            }
            if (provider === 'google-chat') {
                client.open(data);
                status.textContent = 'Your Google Chat conversations and spaces.';
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
            pending.abort();
            if (controller === pending) { refresh.disabled = false; feed.removeAttribute('aria-busy'); loading.hidden = true; }
        }
    };
    buttons.forEach(button => button.addEventListener('click', () => load(button)));
    refresh.addEventListener('click', () => { if (selected?.dataset.appProvider === 'teams' && activeClient) activeClient.refresh(); else if (selected) load(selected); });
    appsTab.addEventListener('click', () => { if (!selected) load(buttons.find(button => button.dataset.appConnected !== 'false') || buttons[0]); });
    if (location.hash === '#apps') appsTab.click();
})();
