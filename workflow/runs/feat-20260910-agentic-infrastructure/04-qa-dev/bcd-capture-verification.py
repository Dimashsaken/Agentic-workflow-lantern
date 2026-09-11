"""Independent actual-media receipt checks; inputs provided by local controller env."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
sys.path.insert(0, str(ROOT/'tools/azure-runner'))
from qa_provenance import Capture, CaptureHeld, Identity, verify


def main():
    authority = Path(os.environ['QA_CAPTURE_AUTHORITY'])
    media = Path(os.environ['QA_CAPTURE_MEDIA'])
    recording_id = os.environ['QA_CAPTURE_RECORDING_ID']
    expected = json.loads(Path(os.environ['QA_CAPTURE_EXPECTED']).read_text())
    identity = Identity(**expected['identity'])
    deployment = expected['deployment']
    source = authority/(recording_id+'.json')
    receipt = verify(authority, media, recording_id, identity, deployment)
    assert receipt['test_only'] is True, 'Only local test capture authorized'
    assert receipt['transport_mode'] == 'direct_fixture' and receipt['images']['gateway'] is None
    results = [{'scenario': 'positive_actual_media_full_decode', 'passed': True}]
    def held(name, fn):
        try:
            fn()
        except (CaptureHeld, FileNotFoundError):
            results.append({'scenario': name, 'passed': True})
        else:
            results.append({'scenario': name, 'passed': False})
    for field in ('run_id', 'execution_key', 'execution_id', 'attempt', 'fence'):
        wrong = identity.document()
        wrong[field] = wrong[field]+1 if type(wrong[field]) is int else wrong[field]+'-wrong'
        held('wrong_'+field, lambda wrong=wrong: verify(authority, media, recording_id, Identity(**wrong), deployment))
    wrong_revision = '0'*40 if deployment['revision'] != '0'*40 else '1'*40
    held('wrong_revision', lambda: verify(authority, media, recording_id, identity, {**deployment, 'revision': wrong_revision}))
    held('wrong_recording', lambda: verify(authority, media, 'f'*32 if recording_id != 'f'*32 else 'e'*32, identity, deployment))
    with tempfile.TemporaryDirectory(prefix='lantern-bcd-capture-negatives-') as temporary:
        temp = Path(temporary)
        temp_authority, temp_media = temp/'authority', temp/'media'
        temp_authority.mkdir()
        temp_media.mkdir()
        for item in receipt['media'].values():
            shutil.copy2(media/item['name'], temp_media/item['name'])
        copy_receipt = temp_authority/source.name
        shutil.copy2(source, copy_receipt)
        for kind in ('video', 'trace'):
            path = temp_media/receipt['media'][kind]['name']
            original = path.read_bytes()
            altered = bytearray(original)
            altered[len(altered)//2] ^= 1
            path.write_bytes(altered)
            held('same_size_'+kind+'_tamper', lambda: verify(temp_authority, temp_media, recording_id, identity, deployment))
            path.write_bytes(original)
        changed = deepcopy(receipt)
        changed['outcomes'][0]['passed'] = False
        copy_receipt.write_text(json.dumps(changed))
        held('failed_requirement', lambda: verify(temp_authority, temp_media, recording_id, identity, deployment))
        changed['outcomes'] = []
        copy_receipt.write_text(json.dumps(changed))
        held('missing_requirements', lambda: verify(temp_authority, temp_media, recording_id, identity, deployment))
        copy_receipt.unlink()
        (temp_media/source.name).write_text(json.dumps(receipt))
        held('forged_writable_mirror', lambda: verify(temp_authority, temp_media, recording_id, identity, deployment))
    result = {'kind': 'independent_local_capture_receipt_verification', 'fleet_execution': False,
              'external_transport_verified': False, 'gateway_accepted': False,
              'transport_mode': receipt['transport_mode'], 'test_only': receipt['test_only'],
              'images': receipt['images'],
              'source_sha256': hashlib.sha256((ROOT/'tools/azure-runner/qa_provenance.py').read_bytes()).hexdigest(),
              'recording_id': recording_id, 'identity': identity.document(),
              'deployment_sha256': receipt['deployment_sha256'], 'receipt_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'media': receipt['media'], 'results': results}
    (OUT/'bcd-capture-verification.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(results))
    assert all(r['passed'] for r in results)


if __name__ == '__main__':
    main()
