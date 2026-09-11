"""Run a local-only image audit on the already authorized native QA host."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[4]
CACHE = ROOT / '.venv/external-qa-scan'
OUT = Path(__file__).resolve().parents[1] / '06-security'
OUT.mkdir(parents=True, exist_ok=True)
CACHE.mkdir(parents=True, exist_ok=True)
archive = CACHE/'trivy.tar.gz'
url = 'https://github.com/aquasecurity/trivy/releases/download/v0.74.0/trivy_0.74.0_Linux-64bit.tar.gz'
if not archive.exists():
    with urllib.request.urlopen(url, timeout=180) as response, archive.open('wb') as output:
        while block := response.read(1024*1024):
            output.write(block)
if hashlib.sha256(archive.read_bytes()).hexdigest() != '2ae6fe3ee734b7fdf11335663e18c75ea12dccc76062f09f164a3b0f8be4371a':
    raise RuntimeError('public scanner checksum mismatch')
with tarfile.open(archive) as files:
    files.extractall(CACHE, filter='data')
subprocess.run([sys.executable, str(Path(__file__).with_name('external-qa-fetch-db.py'))], check=True)
for role, image in (
    ('gateway','sha256:05b1729428c8cdcfb099758f81d916afb94550eae48fad72e4c075e151d0b378'),
    ('recorder','sha256:bbf5ea982390470ce5d0331ac07fc004906ac1e896df5ebe2d84e7e6ff8d59fd'),
):
    resolved = subprocess.check_output(['docker','image','inspect',image,'--format','{{.Id}}'],text=True).strip()
    if resolved != image:
        raise RuntimeError('native image identity mismatch')
    target = CACHE/(role+'.tar')
    subprocess.run(['docker','image','save',image,'-o',str(target)],check=True)
    args = ['docker','run','--rm','--network','none','--user','0','--cap-drop','ALL',
        '--security-opt','no-new-privileges','--entrypoint','/trivy',
        '--mount',f'type=bind,src={CACHE / "trivy"},dst=/trivy,readonly',
        '--mount',f'type=bind,src={CACHE / "cache"},dst=/cache',
        '--mount',f'type=bind,src={target},dst=/input/image.tar,readonly',
        '--mount',f'type=bind,src={OUT},dst=/output',
        '-e','TRIVY_DISABLE_TELEMETRY=true',image,
        '--cache-dir','/cache','--timeout','10m','image','--input','/input/image.tar',
        '--offline-scan','--skip-db-update','--skip-java-db-update','--scanners','vuln',
        '--list-all-pkgs','--format','json','--output',f'/output/external-qa-native-{role}-audit.json']
    with (OUT/f'external-qa-native-{role}-audit.log').open('w') as log:
        subprocess.run(args,check=True,stdout=log,stderr=subprocess.STDOUT)
    report = json.loads((OUT/f'external-qa-native-{role}-audit.json').read_text())
    findings = [v for r in report.get('Results',[]) for v in r.get('Vulnerabilities',[])]
    summary = {'image':image, 'scanner':'Trivy 0.74.0','network':'none',
        'archive_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
        'finding_count':len(findings),
        'severity':{s:sum(v['Severity']==s for v in findings) for s in sorted({v['Severity'] for v in findings})},
        'findings':[{'package':v['PkgName'],'version':v['InstalledVersion'],'id':v['VulnerabilityID'],
                    'severity':v['Severity'],'fixed_version':v.get('FixedVersion')} for v in findings]}
    (OUT/f'external-qa-native-{role}-audit-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({'role':role, 'image':image,'finding_count':len(findings),'severity':summary['severity']}),flush=True)
