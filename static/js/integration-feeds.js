document.querySelectorAll('[data-integration-feed]').forEach(async panel => {
    const load = async () => {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 30000);
        panel.setAttribute('aria-busy', 'true');
        try {
            const response = await fetch(panel.dataset.integrationFeed, {signal: controller.signal});
            if (response.redirected) { location.assign(response.url); return; }
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Messages could not be loaded.');
            const list = document.createElement('ul');
            list.className = 'telegram-list';
            for (const message of data.messages) {
                const row = document.createElement('li');
                const avatar = document.createElement('div'); avatar.className = 'telegram-avatar'; avatar.textContent = message.sender.slice(0, 2).toUpperCase();
                const copy = document.createElement('div');
                const sender = document.createElement('strong'); sender.textContent = message.sender;
                const text = document.createElement('p'); text.textContent = message.text;
                const date = document.createElement('time'); date.textContent = message.time;
                copy.append(sender, text); row.append(avatar, copy, date); list.append(row);
            }
            panel.replaceChildren(list);
            if (!data.messages.length) panel.textContent = 'No recent messages yet.';
        } catch (error) {
            const message = document.createElement('p'); message.className = 'integration-alert';
            message.textContent = error.name === 'AbortError' ? 'Messages took too long to load.' : error.message;
            const retry = document.createElement('button'); retry.type = 'button'; retry.className = 'm3e-button m3e-button--text'; retry.textContent = 'Try again'; retry.addEventListener('click', load);
            panel.replaceChildren(message, retry);
        } finally { clearTimeout(timeout); panel.setAttribute('aria-busy', 'false'); }
    };
    await load();
});
