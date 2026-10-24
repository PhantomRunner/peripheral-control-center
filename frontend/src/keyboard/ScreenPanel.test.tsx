import { useState } from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { ScreenPanel } from './ScreenPanel';
import { DEFAULT_SCREEN, type ScreenSource } from './screenMedia';
import { keyboard } from '../test/fixtures';
import { useScreenTransfer } from './useScreenTransfer';

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal('ImageData', class { data: Uint8ClampedArray; constructor(data: Uint8ClampedArray) { this.data = data; } });
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
    clearRect: vi.fn(), putImageData: vi.fn(), drawImage: vi.fn(), fillRect: vi.fn(), fillText: vi.fn(),
    measureText: () => ({ width: 40 }), getImageData: () => ({ data: new Uint8ClampedArray(128 * 128 * 4) }),
  } as unknown as CanvasRenderingContext2D);
});

function Editor() {
  const [draft, setDraft] = useState(DEFAULT_SCREEN), [source, setSource] = useState<ScreenSource | null>(null);
  const transfer = useScreenTransfer();
  return <ScreenPanel draft={draft} onChange={setDraft} source={source} onSource={setSource} device={keyboard} stale={false} transfer={transfer} />;
}

it('renders text locally, exports converted data and never calls the hardware API', async () => {
  const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock);
  render(<Editor />);
  expect(screen.getByRole('button', { name: 'Export screen data' })).toBeDisabled();
  fireEvent.change(screen.getByRole('textbox', { name: 'Text artwork' }), { target: { value: 'Hello|Keyboard' } });
  fireEvent.click(screen.getByRole('button', { name: 'Create text artwork' }));
  await act(async () => { await vi.advanceTimersByTimeAsync(200); });
  expect(screen.getByText(/1 frame ·/)).toBeVisible();
  expect(screen.getByRole('button', { name: 'Export screen data' })).toBeEnabled();
  expect(screen.getByRole('button', { name: 'Send screen to keyboard' })).toBeDisabled();
  expect(fetchMock).not.toHaveBeenCalled();
});

it('rejects unsupported media and retains no stale export after failure', async () => {
  render(<Editor />);
  const file = new File(['not an image'], 'bad.svg', { type: 'image/svg+xml' });
  fireEvent.change(screen.getByLabelText('Choose an image or GIF'), { target: { files: [file] } });
  await act(async () => {});
  expect(screen.getByRole('alert')).toHaveTextContent('Choose PNG, JPEG, WebP or GIF');
  expect(screen.getByRole('button', { name: 'Export screen data' })).toBeDisabled();
});
