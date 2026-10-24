import { act,fireEvent, render, screen,within } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { MouseWorkspace } from './MouseWorkspace';
import { mouse } from '../test/fixtures';
import { performanceCaps,performanceSnapshot } from './testFixtures';

it('keeps drafts across accessible tabs without sending requests', () => {
  const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
  render(<MouseWorkspace device={mouse} stale={false} onUpdated={vi.fn()} />);
  fireEvent.change(screen.getByLabelText('Current stage DPI (draft)'), { target: { value:'1200' } });
  fireEvent.click(screen.getByRole('tab', { name:'Sensor' }));
  expect(screen.getAllByRole('tabpanel')).toHaveLength(1);
  fireEvent.keyDown(screen.getByRole('tab', { name:'Sensor' }), { key:'Home' });
  expect(screen.getByLabelText('Current stage DPI (draft)')).toHaveValue(1200);
  expect(screen.getByRole('tab', { name:'DPI & polling' })).toHaveFocus();
  expect(fetch).not.toHaveBeenCalled();
});

function fakeApi(next:unknown=performanceSnapshot) {
  const fetch=vi.fn().mockResolvedValueOnce(Response.json({token:'a'.repeat(43),expires_in_seconds:1800})).mockResolvedValueOnce(Response.json(next));
  vi.stubGlobal('fetch',fetch);return fetch;
}
async function readPerformance() {
  fireEvent.click(screen.getByRole('checkbox',{name:'Other device-control tools are closed for performance reading'}));
  fireEvent.click(screen.getByRole('button',{name:'Read stages & sensor'}));
  await screen.findByText('Current stages and sensor settings read. Values describe this observation.');
}

it('shows observed stages, preserves drafts across tabs and requires separate write consent',async()=>{
  const fetch=fakeApi();
  const device={...mouse,performance_capabilities:performanceCaps};
  render(<MouseWorkspace device={device} stale={false} onUpdated={vi.fn()} />);
  await readPerformance();
  expect(within(screen.getByRole('region',{name:'Mouse overview'})).getByText('800')).toBeVisible();
  expect(screen.getByRole('button',{name:'Stage 1 · active 800 DPI'})).toBeVisible();
  fireEvent.change(screen.getByLabelText('Selected stage DPI (draft)'),{target:{value:'1200'}});
  expect(screen.getByRole('button',{name:'Apply selected change'})).toBeDisabled();
  fireEvent.click(screen.getByRole('tab',{name:'Sensor'}));
  fireEvent.change(screen.getByLabelText('Sensor parameter'),{target:{value:'rotation'}});
  fireEvent.change(screen.getByLabelText('Sensor Rotation (draft)'),{target:{value:'-10'}});
  expect(screen.getByRole('img')).toHaveAccessibleName('Mouse schematic; draft sensor rotation -10 degrees');
  fireEvent.click(screen.getByRole('tab',{name:'DPI & polling'}));
  expect(screen.getByLabelText('Selected stage DPI (draft)')).toHaveValue(1200);
  fireEvent.click(screen.getByRole('checkbox',{name:'Other device-control tools are closed for this change'}));
  fireEvent.click(screen.getByRole('checkbox',{name:'Allow this change to persist in device memory'}));
  expect(screen.getByRole('button',{name:'Apply selected change'})).toBeEnabled();
  fireEvent.change(screen.getByLabelText('Selected stage DPI (draft)'),{target:{value:'800'}});
  expect(screen.getByRole('checkbox',{name:'Allow this change to persist in device memory'})).not.toBeChecked();
  expect(fetch).toHaveBeenCalledTimes(2);
});

it('sends only the selected change and clears authorization after a failed write',async()=>{
  const fetch=fakeApi();
  render(<MouseWorkspace device={{...mouse,performance_capabilities:performanceCaps}} stale={false} onUpdated={vi.fn()} />);
  await readPerformance();
  fireEvent.click(screen.getByRole('tab',{name:'Sensor'}));
  fireEvent.change(screen.getByLabelText('Sensor parameter'),{target:{value:'motion_sync'}});
  fireEvent.change(screen.getByLabelText('Motion Sync (draft)'),{target:{value:'true'}});
  fireEvent.click(screen.getByRole('checkbox',{name:'Other device-control tools are closed for this change'}));
  fireEvent.click(screen.getByRole('checkbox',{name:'Allow this change to persist in device memory'}));
  fetch.mockResolvedValueOnce(new Response('private',{status:502}));
  fireEvent.click(screen.getByRole('button',{name:'Apply selected change'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('not confirmed');
  expect(fetch).toHaveBeenCalledTimes(3);
  expect(JSON.parse(fetch.mock.calls[2][1].body).action).toEqual({operation:'motion_sync',enabled:true});
  expect(screen.getByRole('checkbox',{name:'Allow this change to persist in device memory'})).not.toBeChecked();
  expect(screen.getByRole('button',{name:'Apply selected change'})).toBeDisabled();
});

it('rejects a late read across disconnect and reconnect without automatically restarting',async()=>{
  let finish!:(value:Response)=>void;
  const fetch=vi.fn().mockResolvedValueOnce(Response.json({token:'a'.repeat(43),expires_in_seconds:1800})).mockReturnValueOnce(new Promise<Response>(resolve=>{finish=resolve;}));
  vi.stubGlobal('fetch',fetch);
  const device={...mouse,performance_capabilities:performanceCaps};
  const {rerender}=render(<MouseWorkspace device={device} stale={false} onUpdated={vi.fn()} />);
  fireEvent.click(screen.getByRole('checkbox',{name:'Other device-control tools are closed for performance reading'}));
  fireEvent.click(screen.getByRole('button',{name:'Read stages & sensor'}));
  await act(async()=>{});
  rerender(<MouseWorkspace device={{...device,status:'offline',connection:{...device.connection,receiver_usb_present:false}}} stale={false} onUpdated={vi.fn()} />);
  rerender(<MouseWorkspace device={device} stale={false} onUpdated={vi.fn()} />);
  await act(async()=>{finish(Response.json(performanceSnapshot));});
  expect(screen.queryByRole('button',{name:'Stage 1 · active 800 DPI'})).not.toBeInTheDocument();
  expect(screen.getByRole('checkbox',{name:'Other device-control tools are closed for performance reading'})).not.toBeChecked();
  expect(fetch).toHaveBeenCalledTimes(2);
});
