// AK820 geometry adapted from kabelklaus/ajazz-ak820-pro, MIT (c) 2026 kabelklaus.
// Full license: LICENSE.ajazz-ak820-pro. Legends are a preview, not detected keycaps.
export type Key = { label: string; code: string; x: number; y: number; w: number; h: number };
type Cell = [string, string, number?];
const rows: Cell[][] = [
  [['Esc', 'Escape'], ['', '', .25], ...Array.from({ length: 12 }, (_, i): Cell => [`F${i + 1}`, `F${i + 1}`]), ['', '', .5], ['Del', 'Delete']],
  [['`', 'Backquote'], ...'1234567890'.split('').map((n): Cell => [n, `Digit${n}`]), ['−', 'Minus'], ['=', 'Equal'], ['⌫', 'Backspace', 2]],
  [['Tab', 'Tab', 1.5], ...'QWERTYUIOP'.split('').map((n): Cell => [n, `Key${n}`]), ['[', 'BracketLeft'], [']', 'BracketRight'], ['\\', 'Backslash', 1.5]],
  [['Caps', 'CapsLock', 1.75], ...'ASDFGHJKL'.split('').map((n): Cell => [n, `Key${n}`]), [';', 'Semicolon'], ["'", 'Quote'], ['Enter', 'Enter', 2.25]],
  [['Shift', 'ShiftLeft', 2.25], ...'ZXCVBNM'.split('').map((n): Cell => [n, `Key${n}`]), [',', 'Comma'], ['.', 'Period'], ['/', 'Slash'], ['Shift', 'ShiftRight', 1.75], ['', '', .5], ['↑', 'ArrowUp']],
  [['Ctrl', 'ControlLeft', 1.25], ['Super', 'MetaLeft', 1.25], ['Alt', 'AltLeft', 1.25], ['', 'Space', 6.25], ['Alt', 'AltRight'], ['Fn', 'Fn'], ['Ctrl', 'ControlRight'], ['', '', .5], ['←', 'ArrowLeft'], ['↓', 'ArrowDown'], ['→', 'ArrowRight']],
];
export function keyboardKeys(iso = false): Key[] {
  const keys: Key[] = [];
  rows.forEach((cells, y) => {
    let x = 0;
    cells.forEach(([label, code, w = 1]) => { if (code) keys.push({ label, code, x, y, w, h: 1 }); x += w; });
  });
  keys.push(...[['Home', 'Home'], ['PgUp', 'PageUp'], ['PgDn', 'PageDown']].map(([label, code], i) => ({ label, code, x: 15.5, y: i + 1, w: 1, h: 1 })));
  if (iso) {
    const shift = keys.find(k => k.code === 'ShiftLeft')!;
    shift.w = 1.25;
    keys.push({ label: '<', code: 'IntlBackslash', x: 1.25, y: 4, w: 1, h: 1 });
    const enter = keys.find(k => k.code === 'Enter')!;
    Object.assign(enter, { x: 13.75, y: 2, w: 1.25, h: 2 });
    const slash = keys.find(k => k.code === 'Backslash')!;
    Object.assign(slash, { label: '#', x: 12.75, y: 3, w: 1 });
  }
  return keys;
}
