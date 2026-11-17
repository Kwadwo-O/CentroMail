/* Run with: node --test tests/test_password_validation.js */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');

function signup() {
    const nodes = {};
    function input(id, value = '') {
        const listeners = {};
        const attributes = {};
        const classes = new Map();
        const field = {id, value, attributes, classes, message: '',
            classList: {toggle: (name, value) => classes.set(name, value)},
            addEventListener(type, listener) { (listeners[type] ??= []).push(listener); },
            emit(type, event = {}) { for (const listener of listeners[type] ?? []) listener(event); },
            setCustomValidity(message) { this.message = message; },
            checkValidity() { if (this.message) this.emit('invalid'); return !this.message; },
            setAttribute(name, value) { attributes[name] = value; },
            closest() { return {classList: {toggle: (name, value) => classes.set(name, value)}}; },
            focus() { this.focused = true; },
        };
        nodes[id] = field;
        nodes[id + 'Error'] = {hidden: true, textContent: ''};
        return field;
    }
    const password = input('signupPassword');
    const confirmation = input('signupConfirmPassword');
    const name = input('signupName', 'Sample Person');
    const email = input('signupEmail', 'person@example.com');
    const form = input('signupForm');
    form.elements = {password, confirm_password: confirmation, name, email};
    const states = Object.fromEntries(['length', 'uppercase', 'digit', 'special', 'common', 'personal'].map(rule => {
        const state = {textContent: ''};
        const icon = {textContent: ''};
        const classes = new Map();
        return [rule, {state, icon, classes, hidden: false, classList: {toggle: (name, value) => classes.set(name, value)},
            querySelector: selector => selector === '[data-rule-icon]' ? icon : state}];
    }));
    nodes.passwordRules = {querySelector: selector => states[selector.match(/data-rule="(.+)"/)[1]]};
    nodes.passwordGuide = {hidden: true};
    nodes.passwordProgress = input('passwordProgress');
    nodes.passwordProgress.querySelector = selector => {
        const rule = selector.match(/data-rule-segment="(.+)"/)[1];
        return ['length', 'uppercase', 'digit', 'special'].includes(rule) ? states[rule] : null;
    };
    vm.runInNewContext(readFileSync('static/js/password-validation.js', 'utf8'), {
        document: {getElementById: id => nodes[id]}, window: {addEventListener() {}},
    });
    return {password, confirmation, name, email, form, nodes, states};
}

test('missing length, uppercase, number or special character blocks signup with an inline error', () => {
    for (const [value, message] of [
        ['Short1!', /12 and 1024/],
        ['lowercaseonly12!', /uppercase/],
        ['NoDigitsHere!!!!', /number/],
        ['NoSpecialChar123', /special character/],
    ]) {
        const {password, nodes} = signup();
        password.value = value;
        password.emit('input');
        assert.equal(nodes.signupPasswordError.hidden, true);
        assert.equal(password.checkValidity(), false);
        assert.match(nodes.signupPasswordError.textContent, message);
        assert.equal(password.attributes['aria-invalid'], 'true');
    }
});

test('the checklist shows readable status and corrected values clear the inline error', () => {
    const {password, states, nodes} = signup();
    assert.equal(states.common.state.textContent, 'Needed');
    assert.equal(states.common.icon.textContent, 'cancel');
    assert.equal(states.personal.icon.textContent, 'cancel');
    assert.equal(states.common.hidden, true);
    assert.equal(states.personal.hidden, true);
    assert.equal(nodes.passwordProgress.attributes['aria-valuenow'], '0');
    password.emit('blur');
    password.value = 'Brisk River Lantern!42';
    password.emit('input');
    assert.equal(password.checkValidity(), true);
    for (const item of Object.values(states)) {
        assert.equal(item.state.textContent, 'Met');
        assert.equal(item.icon.textContent, 'check_circle');
    }
    assert.equal(nodes.passwordProgress.attributes['aria-valuenow'], '4');
    assert.equal(nodes.passwordProgress.attributes['aria-valuetext'], '4 of 4 core password requirements met');
    assert.equal(nodes.signupPasswordError.hidden, true);
    assert.equal(password.attributes['aria-invalid'], 'false');
});

test('common passwords and updated name or email values remain rejected with visible rule feedback', () => {
    const {password, email, name, states} = signup();
    password.value = 'Password1234!';
    password.emit('input');
    assert.match(password.message, /too common/);
    assert.equal(states.common.hidden, false);
    password.value = 'Brisk River Lantern!42';
    name.value = 'River';
    name.emit('input');
    assert.match(password.message, /name or email/);
    assert.equal(states.common.hidden, true);
    assert.equal(states.personal.hidden, false);
    name.value = 'Sample Person';
    email.value = ' LANTERN@example.com ';
    email.emit('input');
    assert.match(password.message, /name or email/);
});

test('password guidance starts hidden and appears on keyboard focus or typing', () => {
    for (const type of ['focus', 'input']) {
        const {password, nodes} = signup();
        assert.equal(nodes.passwordGuide.hidden, true);
        if (type === 'input') password.value = 'A';
        password.emit(type);
        assert.equal(nodes.passwordGuide.hidden, false);
        password.emit('blur');
        assert.equal(nodes.passwordGuide.hidden, false);
    }
});

test('confirmation mismatch clears on correction and updates when the password changes', () => {
    const {password, confirmation, nodes} = signup();
    password.value = 'Brisk River Lantern!42';
    password.emit('input');
    confirmation.value = 'Different secret!42';
    confirmation.emit('input');
    confirmation.emit('blur');
    assert.match(nodes.signupConfirmPasswordError.textContent, /must match/);
    confirmation.value = password.value;
    confirmation.emit('input');
    assert.equal(confirmation.checkValidity(), true);
    assert.equal(nodes.signupConfirmPasswordError.hidden, true);
    password.value += 'x';
    password.emit('input');
    assert.equal(confirmation.checkValidity(), false);
    assert.match(nodes.signupConfirmPasswordError.textContent, /must match/);
});
