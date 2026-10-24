"""Bounded application TFT transfer with receipt checks, not display readback."""
import json
import subprocess
import sys
from pathlib import Path

from pcc.screen_models import ScreenIntent, artwork_payload, artwork_digest


class AjazzScreenAdapter:
    validation_reference = 'Owner 2026-10-24: FF13/FF68 exact descriptors, nine chunks/receipts, checkerboard visually confirmed'

    def apply(self, intent: ScreenIntent) -> None:
        try:
            result = subprocess.run(
                [sys.executable,'-m','pcc.diagnostics.ajazz_screen_apply','--apply','--vendor-tools-closed','--allow-device-memory-writes'],
                input=intent.model_dump_json(), cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=305, check=False,
            )
            if result.returncode != 0 or len(result.stdout) > 8192: raise RuntimeError('Screen transfer was not confirmed.')
            data = json.loads(result.stdout)
            chunks = len(artwork_payload(intent)) // 4096
            expected = {'status':'screen_transfer_completed_visual_check_required','operation':'screen','usb_id':'0c45:8009',
                        'requested':{'frame_count':len(intent.frames),'payload_sha256':artwork_digest(intent)},
                        'actual_settings':None,'persistence_verified':False,'data_receipt_semantics_verified':False,
                        'diagnostics':{'phase':'save','feature_sets_attempted':3,'feature_sets_completed':3,'feature_gets_attempted':4,
                                       'data_outputs_attempted':chunks,'data_outputs_completed':chunks,'data_receipts':chunks,
                                       'data_receipt_semantics_verified':False,'data_reply_length':64}}
            if json.dumps(data, sort_keys=True) != json.dumps(expected, sort_keys=True):
                raise RuntimeError('Screen result did not match the requested artwork and transfer budget.')
        except (OSError, ValueError, subprocess.TimeoutExpired):
            raise RuntimeError('Screen transfer was not confirmed; artwork may have changed.') from None
