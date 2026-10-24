import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { KeyboardWorkspace } from './KeyboardWorkspace';
import { EFFECTS, DEFAULT_LIGHTING, keyColor } from './lighting';
import { keyboard } from '../test/fixtures';

const device = { ...keyboard, capabilities: { ...keyboard.capabilities, settings_write: true },
  rgb_write_options: { mode: 'static' as const, brightness_steps: [0,20,40,60,80,100], feedback: 'acknowledged' as const, may_persist: true as const } };

describe('AK820 lighting workspace', () => {
  it('previews every effect locally and never disguises a dynamic effect as static Apply', () => {
    const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock);
    render(<KeyboardWorkspace device={device} stale={false} onUpdated={vi.fn()} />);
    expect(screen.getByRole('img', { name: 'AK820 Pro ANSI keyboard preview' })).toBeVisible();
    const effect = screen.getByRole('combobox', { name: 'Effect' });
    expect(within(effect).getAllByRole('option')).toHaveLength(20);
    for (const [id] of EFFECTS) fireEvent.change(effect, { target: { value: id } });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Apply settings' })).toBeDisabled();
    expect(screen.getByText(/Hardware Apply needs validation/)).toBeVisible();
  });

  it('uses the existing protected static Apply and distinguishes acknowledgement from actual RGB', async () => {
    const intent = { kind: 'keyboard', rgb: { mode: 'static', color: '#4080ff', brightness_percent: 60 } };
    const fetchMock = vi.fn().mockResolvedValueOnce(Response.json({ token: 'x'.repeat(43), expires_in_seconds: 1800 }))
      .mockResolvedValueOnce(Response.json({ device_id: device.id, status: 'acknowledged', requested_settings: intent,
        actual_settings: null, readback_available: false, persistence_verified: false, may_persist: true, feedback: 'command_acknowledgements' }));
    vi.stubGlobal('fetch', fetchMock);
    render(<KeyboardWorkspace device={device} stale={false} onUpdated={vi.fn()} />);
    fireEvent.click(screen.getByRole('checkbox', { name: 'Other device-control tools are closed for Apply' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Allow settings writes that may persist in device memory' }));
    fireEvent.click(screen.getByRole('button', { name: 'Apply settings' }));
    expect(await screen.findByText('Lighting command acknowledged. Current RGB and reconnect persistence remain unverified.')).toBeVisible();
    expect(JSON.parse(fetchMock.mock.calls[1][1].body).settings).toEqual(intent);
    expect(screen.getByText(/Current lighting is not read/)).toBeVisible();
  });

  it('replaces tab panels, retains local preview and renews consent when returning', () => {
    const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock);
    render(<KeyboardWorkspace device={device} stale={false} onUpdated={vi.fn()} />);
    fireEvent.change(screen.getByRole('combobox', { name: 'Effect' }), { target: { value: 'breathe' } });
    fireEvent.click(screen.getByRole('tab', { name: 'Device & profiles' }));
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(screen.getAllByRole('region', { name: 'Connection' })).toHaveLength(1);
    fireEvent.keyDown(screen.getByRole('tab', { name: 'Device & profiles' }), { key: 'Home' });
    expect(screen.getByRole('combobox', { name: 'Effect' })).toHaveValue('breathe');
    expect(screen.getAllByRole('tabpanel')).toHaveLength(1);
    expect(screen.queryByRole('region', { name: 'Connection' })).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('simulates bounded colors at zero/full brightness for all modes', () => {
    for (const [effect] of EFFECTS) {
      for (const seconds of [0, 1, 60]) {
        expect(keyColor({ ...DEFAULT_LIGHTING, effect, brightness: 0 }, .2, .5, .3, seconds)).toBe('rgb(0,0,0)');
        const color = keyColor({ ...DEFAULT_LIGHTING, effect, brightness: 100, rainbow: true }, .2, .5, .3, seconds);
        expect(color).toMatch(/^rgb\(\d+,\d+,\d+\)$/);
        expect(color.match(/\d+/g)!.every(value => Number(value) <= 255)).toBe(true);
      }
    }
  });
});
