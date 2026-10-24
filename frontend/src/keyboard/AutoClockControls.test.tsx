import { useState } from 'react';
import { act,fireEvent,render,screen } from '@testing-library/react';
import { beforeEach,expect,it,vi } from 'vitest';
import { AutoClockControls } from './AutoClockControls';
import { keyboard } from '../test/fixtures';

const device={...keyboard,studio_capabilities:{lighting_effects:true,clock_write:true,standby_write:true,screen_write:true,max_screen_frames:120}};
function Controls({stale=false,intervalMinutes=1}:{stale?:boolean;intervalMinutes?:number}) {
  const [busy,setBusy]=useState(false);
  return <AutoClockControls device={device} stale={stale} intervalMinutes={intervalMinutes} busy={busy} onBusy={setBusy} onUpdated={vi.fn()} />;
}
beforeEach(()=>{vi.useFakeTimers();});
function enable(){
  fireEvent.click(screen.getByRole('checkbox',{name:'Other device-control tools stay closed for automatic clock sync'}));
  fireEvent.click(screen.getByRole('checkbox',{name:'Allow repeated device-memory writes while automatic clock sync is enabled'}));
  fireEvent.click(screen.getByRole('checkbox',{name:'Keep keyboard clock in sync'}));
}
function network(fail=false){
  const fetchMock=vi.fn().mockImplementation(async(input,init)=>{
    if(input==='/api/session')return Response.json({token:'x'.repeat(43),expires_in_seconds:1800});
    if(fail)return new Response('private device data',{status:502});
    return Response.json({device_id:keyboard.id,status:'acknowledged',requested:JSON.parse(init.body).intent,actual_settings:null,persistence_verified:false});
  });vi.stubGlobal('fetch',fetchMock);return fetchMock;
}
it('waits the configured interval and requires separate repeated-memory consent',async()=>{
  const fetchMock=network();render(<Controls />);
  expect(screen.getByRole('checkbox',{name:'Keep keyboard clock in sync'})).toBeDisabled();
  expect(fetchMock).not.toHaveBeenCalled();enable();
  await act(async()=>{await vi.advanceTimersByTimeAsync(59_999);});expect(fetchMock).not.toHaveBeenCalled();
  await act(async()=>{await vi.advanceTimersByTimeAsync(1);});expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(screen.getByRole('status')).toHaveTextContent('Clock command acknowledged');
  fireEvent.click(screen.getByRole('checkbox',{name:'Keep keyboard clock in sync'}));
  await act(async()=>{await vi.advanceTimersByTimeAsync(180_000);});expect(fetchMock).toHaveBeenCalledTimes(2);
});
it('stops on write failure without retrying or exposing private errors',async()=>{
  const fetchMock=network(true);render(<Controls />);enable();
  await act(async()=>{await vi.advanceTimersByTimeAsync(60_000);});
  expect(screen.getByRole('alert')).toHaveTextContent('Automatic sync stopped');expect(screen.getByRole('alert')).not.toHaveTextContent('private');
  await act(async()=>{await vi.advanceTimersByTimeAsync(180_000);});expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(screen.getByRole('checkbox',{name:'Keep keyboard clock in sync'})).not.toBeChecked();
});
it('does not resume after backend recovery or an imported interval change',async()=>{
  const fetchMock=network();const{rerender,unmount}=render(<Controls />);enable();
  rerender(<Controls stale />);rerender(<Controls intervalMinutes={30} />);
  await act(async()=>{await vi.advanceTimersByTimeAsync(60_000);});expect(fetchMock).not.toHaveBeenCalled();
  expect(screen.getByRole('checkbox',{name:'Keep keyboard clock in sync'})).not.toBeChecked();
  enable();unmount();await vi.advanceTimersByTimeAsync(1_800_000);expect(fetchMock).not.toHaveBeenCalled();
});

it('revokes repeated-write consent when the page is hidden',async()=>{
  const fetchMock=network();render(<Controls />);enable();
  vi.spyOn(document,'visibilityState','get').mockReturnValue('hidden');
  fireEvent(document,new Event('visibilitychange'));
  await act(async()=>{await vi.advanceTimersByTimeAsync(120_000);});
  expect(fetchMock).not.toHaveBeenCalled();
  expect(screen.getByRole('checkbox',{name:'Keep keyboard clock in sync'})).not.toBeChecked();
  expect(screen.getByRole('checkbox',{name:'Allow repeated device-memory writes while automatic clock sync is enabled'})).not.toBeChecked();
});
