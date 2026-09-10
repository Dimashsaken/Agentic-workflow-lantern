"""Decode actual recordings; emit frame offsets for independent visual review."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
sys.path.insert(0, str(ROOT/'tools/azure-runner'))
from evidence_manifest import probe_video

results = []
for path in sorted((OUT/'media').glob('*bcd*.webm')):
    decoded = probe_video(path)
    offset = min(1.0, decoded['duration_seconds']/2)
    frame = path.with_name(path.stem+'-frame.png')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(offset), '-i', str(path), '-frames:v', '1', str(frame)], check=True)
    results.append({'video': 'media/'+path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                    **decoded, 'frame': 'media/'+frame.name, 'frame_offset_seconds': offset})
(OUT/'bcd-video-decode.json').write_text(json.dumps(results, indent=2)+'\n')
print(json.dumps([{'video': r['video'], 'duration': r['duration_seconds'], 'decoded': r['decoded']} for r in results]))
