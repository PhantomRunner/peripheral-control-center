import { localClockTime, type StudioClient } from './studioApi';
import type { StudioProfile } from './studioProfile';
import type { ScreenFrame } from './screenMedia';

export async function runStudioBatch(profile: StudioProfile, frames: ScreenFrame[], client: Pick<StudioClient,'apply'>,
  upload: (frames: ScreenFrame[]) => Promise<boolean>, authorized: () => boolean): Promise<'screen_started'|'commands_acknowledged'> {
  let step = 'clock';
  try {
    if (!authorized()) throw new Error();
    await client.apply({operation:'clock',local_time:localClockTime()},true,true);
    step = 'lighting';
    if (!authorized()) throw new Error();
    await client.apply({operation:'lighting',settings:profile.lighting},true,true);
    if (frames.length) {
      step = 'screen';
      if (!authorized() || !await upload(frames)) throw new Error();
      return 'screen_started';
    }
    return 'commands_acknowledged';
  } catch {
    throw new Error(`Sequence stopped at ${step}. Earlier changes may remain; check the keyboard before retrying. No later step was sent.`);
  }
}
