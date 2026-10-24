import { keyboardKeys } from './layout';

// keyd key names checked against rvaiya/keyd src/keys.c and docs/keyd.scdoc.
const special: Record<string, string> = {
  Escape: 'esc', Backspace: 'backspace', Tab: 'tab', CapsLock: 'capslock', Enter: 'enter',
  Space: 'space', Backquote: 'grave', Minus: 'minus', Equal: 'equal', BracketLeft: 'leftbrace',
  BracketRight: 'rightbrace', Backslash: 'backslash', Semicolon: 'semicolon', Quote: 'apostrophe',
  Comma: 'comma', Period: 'dot', Slash: 'slash', IntlBackslash: '102nd',
  ShiftLeft: 'leftshift', ShiftRight: 'rightshift', ControlLeft: 'leftcontrol', ControlRight: 'rightcontrol',
  MetaLeft: 'leftmeta', AltLeft: 'leftalt', AltRight: 'rightalt',
  ArrowLeft: 'left', ArrowRight: 'right', ArrowUp: 'up', ArrowDown: 'down',
  Delete: 'delete', Home: 'home', End: 'end', PageUp: 'pageup', PageDown: 'pagedown',
};
export type KeyMapping = { from: string; to: string };
export const MAPPING_KEYS = [...new Set([...keyboardKeys(true).map(key => key.code), 'End'])].filter(code => code !== 'Fn');
export function keydName(code: string): string {
  if (/^Key[A-Z]$/.test(code)) return code.slice(3).toLowerCase();
  if (/^Digit[0-9]$/.test(code)) return code.slice(5);
  if (/^F([1-9]|1[0-2])$/.test(code)) return code.toLowerCase();
  if (Object.hasOwn(special, code)) return special[code];
  throw new Error('Choose a supported physical key.');
}
export function keydConfig(mappings: KeyMapping[]): string {
  if (mappings.length > 82 || new Set(mappings.map(mapping => mapping.from)).size !== mappings.length) throw new Error('Each source key can have one mapping.');
  const lines = mappings.map(mapping => `${keydName(mapping.from)} = ${keydName(mapping.to)}`);
  return ['# PCC · AJAZZ AK820 Pro · wired USB only', '# Local export; review and install with keyd separately.', '[ids]', 'k:0c45:8009', '', '[main]', ...lines, ''].join('\n');
}
