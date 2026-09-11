"""Full configured check recorder; local engineering evidence, no fleet claim."""
import hashlib
import json
import os
import re
import sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
PREFIX=os.environ.get("C3_CHECK_PREFIX","c3-foundation")
sys.path.insert(0,str(ROOT/'tools/azure-runner'))
import factory

def source():
    paths=[]
    for folder in ('tools/azure-runner','tools/mission-control','tools/evals','infra/qa-gateway'):
        paths.extend((ROOT/folder).glob('*.py'))
    paths.extend([ROOT/'lantern.toml',ROOT/'infra/qa-gateway/Dockerfile',ROOT/'infra/qa-gateway/requirements.lock',ROOT/'infra/qa-gateway/upstream.lock',ROOT/'infra/qa-gateway/build-tools.lock'])
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}

before=source()
config=factory.quality_config(ROOT)
factory.QUALITY_TAIL=10000000
rows=[]
for name,command in config['commands']:
    result=factory.run_command(command,ROOT,config['timeout_s'])
    output=result.pop('output_tail')
    log=OUT/f'{PREFIX}-{name}.log';log.write_text(output,encoding='utf-8')
    result.update(name=name,command=command,log=log.name,
      unittest_count=sum(int(n) for n in re.findall(r'^Ran (\d+) tests? in',output,re.M)))
    rows.append(result)
    print(json.dumps(result),flush=True)
after=source()
record={'kind':'complete_configured_local_checks','fleet_execution':False,'at':datetime.now(timezone.utc).isoformat(),
 'python':sys.version,'policy_sha256':config.get('sha256'),'source_before':before,'source_after':after,
 'source_unchanged':before==after,'results':rows,'passed':before==after and all(r['passed'] for r in rows)}
(OUT/f'{PREFIX}-quality.json').write_text(json.dumps(record,indent=2)+'\n')
raise SystemExit(0 if record['passed'] else 1)
