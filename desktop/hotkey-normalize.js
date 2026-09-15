const MODIFIERS = { ctrl: 'Ctrl', control: 'Ctrl', '<ctrl>': 'Ctrl', '<control>': 'Ctrl', alt: 'Alt', '<alt>': 'Alt', shift: 'Shift', '<shift>': 'Shift', command: 'Command', cmd: 'Command', '<command>': 'Command', '<cmd>': 'Command', commandorcontrol: 'CommandOrControl', cmdorctrl: 'CommandOrControl' };
const KEYS = { space: 'Space', up: 'Up', arrowup: 'Up', down: 'Down', arrowdown: 'Down', left: 'Left', arrowleft: 'Left', right: 'Right', arrowright: 'Right', enter: 'Enter', tab: 'Tab', escape: 'Esc', esc: 'Esc', backspace: 'Backspace', delete: 'Delete', insert: 'Insert', home: 'Home', end: 'End', pageup: 'PageUp', pagedown: 'PageDown' };

function normalizeAccelerator(value) {
  const parts = String(value || '').trim().split('+').map(part => part.trim()).filter(Boolean);
  if (parts.length < 2) return null;
  const modifiers = []; let key = null;
  for (const part of parts) {
    const lower = part.toLowerCase();
    if (MODIFIERS[lower]) { if (modifiers.includes(MODIFIERS[lower])) return null; modifiers.push(MODIFIERS[lower]); continue; }
    if (key) return null;
    key = KEYS[lower] || (/^[a-z0-9]$/i.test(part) ? part.toUpperCase() : (/^f(?:[1-9]|1\d|2[0-4])$/i.test(part) ? part.toUpperCase() : null));
  }
  return key ? [...['Ctrl', 'Alt', 'Shift', 'Command', 'CommandOrControl'].filter(modifier => modifiers.includes(modifier)), key].join('+') : null;
}

module.exports = { normalizeAccelerator };
