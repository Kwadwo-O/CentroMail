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
                copy.append(sender);
                if (message.text) {
                    const text = document.createElement('p'); text.textContent = message.text;
                    copy.append(text);
                }
                if (message.media?.available === false) {
                    const note = document.createElement('p'); note.textContent = 'Open Telegram for media larger than 64 MB.';
                    copy.append(note);
                } else if (message.media && ['photo', 'video'].includes(message.media.kind)) {
                    const media = message.media, photo = media.kind === 'photo';
                    const wrapper = document.createElement('div'); wrapper.className = 'telegram-preview-media';
                    const content = document.createElement(photo ? 'img' : 'video');
                    let mediaSource;
                    if (photo) {
                        content.src = media.url; content.alt = 'Photo from ' + message.sender;
                        content.loading = 'lazy'; content.decoding = 'async';
                        const link = document.createElement('a'); link.href = media.url;
                        link.target = '_blank'; link.rel = 'noopener'; link.setAttribute('aria-label', 'Open photo from ' + message.sender);
                        link.append(content); wrapper.append(link);
                    } else {
                        content.controls = true; content.preload = 'none'; content.playsInline = true;
                        content.setAttribute('aria-label', 'Video from ' + message.sender);
                        const source = document.createElement('source'); source.src = media.url; source.type = media.mime_type;
                        mediaSource = source;
                        content.append(source); wrapper.append(content);
                    }
                    const failure = document.createElement('p'); failure.className = 'telegram-media-feedback';
                    failure.hidden = true; failure.setAttribute('role', 'status');
                    const detail = document.createElement('span'); detail.textContent = 'This ' + (photo ? 'photo' : 'video') + ' could not be loaded. ';
                    const retry = document.createElement('button'); retry.type = 'button'; retry.className = 'm3e-button m3e-button--text';
                    retry.textContent = 'Retry ' + (photo ? 'photo' : 'video');
                    retry.addEventListener('click', () => {
                        failure.hidden = true; content.hidden = false;
                        if (photo) content.src = media.url;
                        else content.load();
                    });
                    const failed = () => { content.hidden = true; failure.hidden = false; };
                    content.addEventListener('error', failed);
                    mediaSource?.addEventListener('error', failed);
                    content.addEventListener(photo ? 'load' : 'loadedmetadata', () => { failure.hidden = true; content.hidden = false; });
                    failure.append(detail, retry); wrapper.append(failure); copy.append(wrapper);
                }
                const date = document.createElement('time'); date.textContent = message.time;
                row.append(avatar, copy, date); list.append(row);
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
