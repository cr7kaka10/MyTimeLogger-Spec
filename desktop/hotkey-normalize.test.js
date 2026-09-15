const assert = require('node:assert/strict');
const { normalizeAccelerator } = require('./hotkey-normalize');

assert.equal(normalizeAccelerator('<alt>+z'), 'Alt+Z');
assert.equal(normalizeAccelerator('shift + control + f5'), 'Ctrl+Shift+F5');
assert.equal(normalizeAccelerator('Alt+ArrowDown'), 'Alt+Down');
assert.equal(normalizeAccelerator('Alt+Alt+Z'), null);
assert.equal(normalizeAccelerator('Alt'), null);
assert.equal(normalizeAccelerator('Alt+Unknown'), null);
console.log('hotkey normalization tests passed');
