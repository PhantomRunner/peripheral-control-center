"""Explicit RGB565 artwork transfer using the owner's validated FF13/FF68 framing.

Only semantic pixel frames on bounded stdin. Header/config/chunks are constructed
inside the adapter; no raw command/report-ID or alternate protocol arguments.
"""
import argparse
import json
import os
import signal
import sys
from contextlib import contextmanager

from pcc.diagnostics import ajazz_rgb_probe as rgb
from pcc.diagnostics.ajazz_screen_probe import open_screen, observe_screen
from pcc.screen_models import MAX_REQUEST_BYTES, ScreenIntent, artwork_payload, artwork_digest


@contextmanager
def deadline():
    if signal.getitimer(signal.ITIMER_REAL) != (0.0,0.0): raise rgb.ProbeBlocked('Use a standalone child.')
    def expired(*_): raise rgb.ProbeBlocked('Screen deadline reached.')
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 300)
    try: yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, previous)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--vendor-tools-closed', action='store_true')
    parser.add_argument('--allow-device-memory-writes', action='store_true')
    args = parser.parse_args(argv)
    if not args.apply:
        print(json.dumps({'mode':'plan','device_io':False,'max_frames':120,'max_data_outputs':961,'process_deadline_seconds':300,'retries':0})); return 0
    transport = None
    try:
        if os.geteuid() == 0 or not args.vendor_tools_closed or not args.allow_device_memory_writes:
            raise rgb.ProbeBlocked('Normal user and both explicit consents are required.')
        content = sys.stdin.read(MAX_REQUEST_BYTES + 1)
        if len(content) > MAX_REQUEST_BYTES: raise rgb.ProbeBlocked('Artwork request exceeds its bound.')
        intent = ScreenIntent.model_validate_json(content)
        payload = artwork_payload(intent)
        with deadline(), open_screen(payload) as transport:
            result = observe_screen(transport, len(payload) // 4096)
            result['requested'] = {'frame_count':len(intent.frames),'payload_sha256':artwork_digest(intent)}
            result['diagnostics'] = transport.diagnostics()
        print(json.dumps(result)); return 0
    except (rgb.ProbeBlocked, OSError, ValueError, rgb.DeviceBusyError, rgb.OwnershipUnavailableError):
        print(json.dumps({'status':'blocked','detail':'Screen transfer was not confirmed. The screen may have changed; no retry, restore or fallback.',
                          'diagnostics':transport.diagnostics() if transport is not None else None})); return 2


if __name__ == '__main__': raise SystemExit(main())
