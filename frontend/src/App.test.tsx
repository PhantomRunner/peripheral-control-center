import { StrictMode } from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { deviceResponse, mouse, offlineMouse, pendingRequest } from './test/fixtures';

describe('discovery views', () => {
  it('shows loading without inventing device counts or readings', () => {
    vi.stubGlobal('fetch', vi.fn(pendingRequest));
    render(<App />);
    expect(screen.getByRole('status')).toHaveTextContent('Checking USB devices');
    expect(screen.getByRole('button', { name: 'Checking…' })).toBeDisabled();
    expect(screen.queryByRole('article')).not.toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Device overview' })).toHaveTextContent('Known devices—');
  });

  it('renders device cards and navigates to details and back', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => deviceResponse()));
    render(<App />);
    const card = await screen.findByRole('article', { name: mouse.name });
    expect(within(card).getByText('USB receiver detected')).toBeVisible();
    expect(within(card).getAllByRole('definition').map((el) => el.textContent)).toEqual(['—', '—', '—']);
    fireEvent.click(within(card).getByRole('link', { name: `View ${mouse.name} details` }));
    expect(await screen.findByRole('heading', { name: `${mouse.name}.`, level: 1 })).toBeVisible();
    expect(screen.getByRole('region', { name: 'Adapter support' })).toBeVisible();
    fireEvent.click(screen.getByRole('link', { name: '← All devices' }));
    expect(await screen.findByRole('heading', { name: 'Your peripherals.', level: 1 })).toBeVisible();
    expect(screen.getAllByRole('article')).toHaveLength(2);
  });

  it('opens a direct device URL', async () => {
    window.history.replaceState({}, '', '/#/devices/ajazz_ak820_pro');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(deviceResponse()));
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'AJAZZ AK820 Pro.', level: 1 })).toBeVisible();
    expect(screen.getByRole('region', { name: 'Connection' })).toHaveTextContent('Wired USB detected');
  });

  it.each(['#/devices/missing', '#/devices/%E0%A4%A', '#/unrecognised'])('handles an unknown URL: %s', async (hash) => {
    window.history.replaceState({}, '', `/${hash}`);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(deviceResponse()));
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Device not found', level: 3 })).toBeVisible();
    expect(screen.getByRole('link', { name: 'Go to dashboard' })).toHaveAttribute('href', '#/');
  });

  it('stops the loading state on an initial failure and supports retry', async () => {
    const fetchMock = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(deviceResponse());
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Backend unavailable.');
    expect(screen.queryByText('Checking USB devices')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry connection' }));
    expect(await screen.findByRole('article', { name: mouse.name })).toBeVisible();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('marks cached data stale on error, then distinguishes a USB disconnect on recovery', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(deviceResponse([mouse]));
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);
    await screen.findByRole('article', { name: mouse.name });
    fetchMock.mockRejectedValueOnce(new Error('offline'));
    fireEvent.click(screen.getByRole('button', { name: '↻ Refresh' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('current USB presence is unknown');
    expect(screen.getByText('Last known: USB receiver detected')).toBeVisible();
    expect(screen.getByRole('region', { name: 'Device overview' })).toHaveTextContent('USB hardware detected—');
    fetchMock.mockResolvedValueOnce(deviceResponse([offlineMouse]));
    fireEvent.click(screen.getByRole('button', { name: 'Retry connection' }));
    expect(await screen.findByText('USB not detected')).toBeVisible();
    expect(screen.getByRole('status')).toHaveTextContent('USB disconnected since last scan: Pulsar Susanto-X');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByText('Last known: USB receiver detected')).not.toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Device overview' })).toHaveTextContent('USB hardware detected0');
  });

  it('keeps valid cards if a later payload is malformed', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(deviceResponse());
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);
    await screen.findByRole('article', { name: mouse.name });
    fetchMock.mockResolvedValueOnce(Response.json({ devices: [{}] }));
    fireEvent.click(screen.getByRole('button', { name: '↻ Refresh' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Unexpected API response.');
    expect(screen.getAllByRole('article')).toHaveLength(2);
  });

  it('shows an empty state for an empty adapter list', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(deviceResponse([])));
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'No registered devices' })).toBeVisible();
    expect(screen.queryByRole('article')).not.toBeInTheDocument();
  });

  it('ignores a late response from an aborted StrictMode mount', async () => {
    let resolveOld!: (value: Response) => void;
    const oldRequest = new Promise<Response>((resolve) => { resolveOld = resolve; });
    const fetchMock = vi.fn().mockReturnValueOnce(oldRequest).mockResolvedValueOnce(deviceResponse([mouse]));
    vi.stubGlobal('fetch', fetchMock);
    render(<StrictMode><App /></StrictMode>);
    await screen.findByText('USB receiver detected');
    await act(async () => { resolveOld(deviceResponse([offlineMouse])); });
    expect(screen.getByText('USB receiver detected')).toBeVisible();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });
});
