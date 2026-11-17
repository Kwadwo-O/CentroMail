(() => {
    const storageKey = 'centromail-reply-position';
    let position, current, drag, suppressClick;
    try {
        const saved = JSON.parse(localStorage.getItem(storageKey));
        if (saved && Number.isFinite(saved.x) && Number.isFinite(saved.y)) position = saved;
    } catch { /* Reply remains movable when storage is unavailable. */ }
    const hint = document.createElement('p');
    hint.id = 'reply-move-hint'; hint.className = 'sr-only';
    hint.textContent = 'Drag Reply to move it. Alt and arrow keys also move it. Alt and Home restore its original position.';
    document.body.append(hint);
    const save = () => {
        try {
            if (position) localStorage.setItem(storageKey, JSON.stringify(position));
            else localStorage.removeItem(storageKey);
        } catch { /* Keep the current position for this page. */ }
    };
    const restore = wrapper => {
        wrapper.classList.remove('is-positioned');
        wrapper.style.removeProperty('left'); wrapper.style.removeProperty('top');
        wrapper.querySelector('[data-reply-reset]').hidden = true;
    };
    const place = (wrapper, x, y) => {
        wrapper.classList.add('is-positioned');
        wrapper.querySelector('[data-reply-reset]').hidden = false;
        const box = wrapper.getBoundingClientRect();
        position = {x: Math.max(8, Math.min(x, innerWidth - box.width - 8)),
            y: Math.max(8, Math.min(y, innerHeight - box.height - 8))};
        wrapper.style.left = position.x + 'px'; wrapper.style.top = position.y + 'px';
    };
    const reset = () => { position = null; if (current) restore(current); save(); };
    const sync = () => {
        const button = [...document.querySelectorAll('[data-email-reply]')].find(item =>
            !item.disabled && !item.closest('[hidden], details:not([open])') &&
            (!item.closest('[data-conversation-message]') || item.closest('[data-current-message]')));
        const wrapper = button?.closest('.reply-button-wrap');
        if (wrapper === current) return;
        if (current) { restore(current); current.querySelector('[data-email-reply]').removeAttribute('data-reply-movable'); }
        current = wrapper;
        if (!current) return;
        button.dataset.replyMovable = '';
        button.setAttribute('aria-describedby', hint.id);
        button.title = 'Drag to move Reply · Alt + arrow keys to move · Alt + Home to reset';
        if (!current.querySelector('[data-reply-reset]')) {
            const control = document.createElement('button');
            control.type = 'button'; control.className = 'm3e-icon-button m3e-icon-button--standard';
            control.dataset.replyReset = ''; control.hidden = true;
            control.setAttribute('aria-label', 'Reset Reply button position');
            control.title = 'Reset Reply position';
            const icon = document.createElement('span'); icon.className = 'm3e-icon';
            icon.setAttribute('aria-hidden', 'true'); icon.textContent = 'undo';
            control.append(icon); current.append(control);
        }
        if (position) place(current, position.x, position.y);
    };
    document.addEventListener('pointerdown', event => {
        const button = event.target.closest('[data-reply-movable]');
        if (!button || button.disabled || event.button !== 0 || !event.isPrimary) return;
        const wrapper = button.closest('.reply-button-wrap'), box = wrapper.getBoundingClientRect();
        drag = {button, wrapper, id:event.pointerId, x:event.clientX, y:event.clientY, left:box.left, top:box.top, moved:false};
        button.setPointerCapture(event.pointerId);
    });
    document.addEventListener('pointermove', event => {
        if (!drag || event.pointerId !== drag.id) return;
        const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
        if (!drag.moved && Math.hypot(dx, dy) < 6) return;
        drag.moved = true; drag.button.classList.add('is-dragging');
        place(drag.wrapper, drag.left + dx, drag.top + dy);
    });
    const finish = event => {
        if (!drag || event.pointerId !== drag.id) return;
        const pending = drag; drag = null;
        pending.button.classList.remove('is-dragging');
        if (pending.button.hasPointerCapture(pending.id)) pending.button.releasePointerCapture(pending.id);
        if (pending.moved) {
            suppressClick = pending.button;
            setTimeout(() => { if (suppressClick === pending.button) suppressClick = null; }, 0);
            save();
        }
    };
    document.addEventListener('pointerup', finish);
    document.addEventListener('pointercancel', finish);
    document.addEventListener('lostpointercapture', finish);
    document.addEventListener('click', event => {
        const button = event.target.closest('[data-email-reply]');
        if (button && button === suppressClick) {
            suppressClick = null; event.preventDefault(); event.stopImmediatePropagation();
        }
        if (event.target.closest('[data-reply-reset]')) { reset(); current.querySelector('[data-email-reply]').focus(); }
    }, true);
    document.addEventListener('keydown', event => {
        const button = event.target.closest('[data-reply-movable]');
        if (!button || !event.altKey || !['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home'].includes(event.key)) return;
        event.preventDefault(); event.stopPropagation();
        if (event.key === 'Home') { reset(); return; }
        const box = current.getBoundingClientRect(), step = event.shiftKey ? 40 : 16;
        place(current, box.left + (event.key === 'ArrowRight' ? step : event.key === 'ArrowLeft' ? -step : 0),
            box.top + (event.key === 'ArrowDown' ? step : event.key === 'ArrowUp' ? -step : 0));
        save();
    });
    window.addEventListener('resize', () => { if (current && position) { place(current, position.x, position.y); save(); } });
    new MutationObserver(sync).observe(document.body, {childList:true, subtree:true, attributes:true, attributeFilter:['hidden', 'open']});
    sync();
})();
