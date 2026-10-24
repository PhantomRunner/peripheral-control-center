import { LocalApiClient, LocalApiError } from '../localApi';
import { matchesAction, parseSnapshot, record, type PerformanceAction, type PerformanceSnapshot } from './performance';

const base='/api/devices/pulsar_susanto_x/performance';
export class PerformanceClient {
  private readonly api=new LocalApiClient(55_000);
  async read():Promise<PerformanceSnapshot> {
    try { return parseSnapshot(await this.api.request(`${base}/read`,'POST',{vendor_tools_closed:true})); }
    catch (cause) { throw performanceError(cause); }
  }
  async apply(action:PerformanceAction,snapshot:PerformanceSnapshot):Promise<PerformanceSnapshot> {
    try {
      const value=await this.api.request(`${base}/apply`,'POST',{action,expected_profile_index:snapshot.active_profile_index,
        expected_active_stage_index:snapshot.active_stage_index,vendor_tools_closed:true,allow_device_memory_writes:true});
      if (!record(value) || value.status!=='verified' || value.persistence_verified!==false || value.may_persist!==true || !record(value.requested)
        || Object.keys(action).some(key=>value.requested && record(value.requested) && value.requested[key]!==action[key as keyof PerformanceAction])) throw new Error('No matching verified result. Settings may have changed.');
      const actual=parseSnapshot(value.actual);
      if (actual.active_profile_index!==snapshot.active_profile_index || actual.stage_count!==snapshot.stage_count || !matchesAction(actual,action)) throw new Error('Device readback did not match. Settings may have changed.');
      return actual;
    } catch (cause) { throw performanceError(cause); }
  }
}
function performanceError(cause:unknown):Error {
  if (cause instanceof LocalApiError) {
    if (cause.status===409) return new Error('This operation is unavailable. Read the device again and check validated support.');
    if (cause.status===423) return new Error('The mouse is busy. Wait for the current operation.');
    if (cause.status===422) return new Error('These values are outside the supported performance settings.');
    if (cause.status===502 || cause.status===503) return new Error('The device operation was not confirmed. Read current settings before retrying; writes may have changed them.');
  }
  return cause instanceof Error?cause:new Error('The performance operation was not confirmed.');
}
