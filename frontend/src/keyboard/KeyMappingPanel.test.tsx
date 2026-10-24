import { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { KeyMappingPanel } from './KeyMappingPanel';
import { keydConfig, keydName, MAPPING_KEYS, type KeyMapping } from './keyMapping';

function Editor() { const [mappings, setMappings] = useState<KeyMapping[]>([]); return <KeyMappingPanel mappings={mappings} onChange={setMappings} iso={false} />; }

it('monitors only the focused test region after an explicit start and stops on blur', () => {
  const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock);
  render(<Editor />);
  fireEvent.keyDown(window, { code: 'KeyA', key: 'a' });
  expect(screen.queryByLabelText('Recent test keys')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Start key monitor' }));
  const monitor = screen.getByRole('region', { name: 'Key test area' });
  fireEvent.keyDown(monitor, { code: 'KeyA', key: 'a' });
  expect(screen.getByLabelText('Recent test keys')).toHaveTextContent('KeyA');
  expect(screen.getByRole('combobox', { name: 'Source key' })).toHaveValue('KeyA');
  fireEvent.blur(monitor);
  fireEvent.keyDown(monitor, { code: 'KeyB', key: 'b' });
  expect(screen.getByLabelText('Recent test keys')).not.toHaveTextContent('KeyB');
  fireEvent.click(screen.getByRole('button', { name: 'Clear key history' }));
  expect(screen.queryByLabelText('Recent test keys')).not.toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
});

it('exports only allowlisted keyd names and a keyboard-specific wired id', () => {
  render(<Editor />);
  fireEvent.click(screen.getByRole('button', { name: 'Add mapping' }));
  const config = screen.getByLabelText('Generated keyd configuration');
  expect(config).toHaveTextContent('k:0c45:8009');
  expect(config).toHaveTextContent('capslock = esc');
  expect(config).not.toHaveTextContent('*');
  expect(config).not.toHaveTextContent('fdfd');
  expect(screen.getByRole('button', { name: 'Export keyd configuration' })).toBeEnabled();
  fireEvent.click(screen.getByRole('button', { name: 'Remove mapping CapsLock' }));
  expect(screen.getByRole('button', { name: 'Export keyd configuration' })).toBeDisabled();
  expect(() => keydConfig([{ from: 'CapsLock', to: 'esc\n[ids]\n*' }])).toThrow();
  expect(() => keydConfig([{ from: 'KeyA', to: 'KeyB' }, { from: 'KeyA', to: 'KeyC' }])).toThrow();
  for (const code of MAPPING_KEYS) expect(keydName(code)).toMatch(/^[a-z0-9]+$/);
});
