(() => {
    const provider = document.querySelector('#email-provider');
    if (!provider) return;
    const update = () => {
        const preset = window.CentroMailEmailPresets.find(item => item.key === provider.value);
        for (const name of ['imap_host','imap_port','imap_security','smtp_host','smtp_port','smtp_security']) {
            document.querySelector('[name="'+name+'"]').value = preset[name];
        }
        document.querySelector('#email-server-details').open = ['custom','proton-bridge'].includes(preset.key);
        document.querySelector('#email-save-sent').value = preset.save_sent === false ? 'false' : 'true';
    };
    provider.addEventListener('change',update);
    document.querySelector('#email-connect-form').addEventListener('invalid', () => document.querySelector('#email-server-details').open = true, true);
    update();
})();
