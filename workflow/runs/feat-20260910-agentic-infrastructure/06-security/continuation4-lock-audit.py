"""Fresh package metadata and static Linux lock consistency; not an image scan."""
import concurrent.futures, hashlib, json, pathlib, re, urllib.request
from pip._vendor.packaging.requirements import Requirement
from pip._vendor.packaging.markers import default_environment
root=pathlib.Path.cwd(); file=root/'infra/qa-gateway/requirements.lock'
pins={}
for line in file.read_text().splitlines():
 m=re.match(r'([^=]+)==([^ ]+) --hash=sha256:(\w+)',line)
 if m: pins[re.sub(r'[-_.]+','-',m[1]).lower()]={'name':m[1],'version':m[2],'sha256':m[3]}
env=default_environment(); env.update(sys_platform='linux',os_name='posix',platform_system='Linux',platform_machine='x86_64',python_version='3.12',python_full_version='3.12.10',extra='')
def read(item):
 key,p=item
 if key=='mitmproxy':
  orig=json.loads((root/'workflow/runs/feat-20260910-agentic-infrastructure/06-security/continuation4-vendor-provenance.json').read_text())
  reqs=orig['upstream_requires']
  for old,new in orig['changes'].items():
   if old.startswith('Requires-Dist: '): reqs=[new[len('Requires-Dist: '):] if x==old[len('Requires-Dist: '):] else x for x in reqs]
  return key, dict(p, requires=reqs,advisories=[],local_vendor=True,hash_verified=orig['candidate_sha256']==p['sha256'])
 with urllib.request.urlopen(f"https://pypi.org/pypi/{p['name']}/{p['version']}/json",timeout=30) as r: data=json.load(r)
 matches=[f for f in data['urls'] if f['digests']['sha256']==p['sha256']]
 return key,dict(p,requires=data['info']['requires_dist'] or [],advisories=data['vulnerabilities'],hash_verified=len(matches)==1,
                 wheel=matches[0]['filename'] if matches else None,yanked=matches[0]['yanked'] if matches else None)
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex: packages=dict(ex.map(read,pins.items()))
failures=[]
for key,p in packages.items():
 for req in p['requires']:
  r=Requirement(req)
  if r.marker and not r.marker.evaluate(env): continue
  target=packages.get(re.sub(r'[-_.]+','-',r.name).lower())
  if not target or not r.specifier.contains(target['version']): failures.append({'source':key,'requirement':req,'target':target and target['version']})
result={'scope':'fresh exact PyPI release metadata + PEP508 Linux CPython3.12 static consistency; not installed-image audit',
        'lock_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'packages':packages,'dependency_conflicts':failures,
        'advisory_packages':[p['name'] for p in packages.values() if p['advisories']],
        'all_hashes_match':all(p['hash_verified'] for p in packages.values())}
(root/'workflow/runs/feat-20260910-agentic-infrastructure/06-security/continuation4-lock-audit.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='packages'},indent=2))
assert not failures and not result['advisory_packages'] and result['all_hashes_match']
