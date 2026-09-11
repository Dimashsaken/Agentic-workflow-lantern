import hashlib, importlib.metadata, json, pathlib, ssl, subprocess, zipfile
import OpenSSL
from OpenSSL import SSL
files={p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() for p in
       ['/opt/gateway/requirements.lock','/opt/gateway/policy.py','/opt/gateway/entrypoint.py',
        '/opt/gateway/vendor_wheel.py','/opt/gateway/qa_transport.py']}
with zipfile.ZipFile('/opt/gateway/upstream/mitmproxy-12.2.3-py3-none-any.whl') as original, zipfile.ZipFile('/opt/gateway/vendor/mitmproxy-12.2.3+lantern1-py3-none-any.whl') as patched:
    names=[n for n in original.namelist() if not n.startswith('mitmproxy-12.2.3.dist-info/')]
    same=all(original.read(n)==patched.read(n) for n in names)
result={'scope':'actual gateway image offline installed inventory, source hashes and vendor byte comparison; not advisory result',
        'source_hashes':files,'os_release':pathlib.Path('/etc/os-release').read_text(),
        'gateway_packages':sorted([{'name':d.metadata['Name'],'version':d.version} for d in importlib.metadata.distributions()],key=lambda x:x['name'].lower()),
        'os_packages':subprocess.check_output(['dpkg-query','-W','-f=${Package}\t${Version}\n'],text=True).splitlines(),
        'stdlib_tls':ssl.OPENSSL_VERSION,'gateway_tls':SSL.SSLeay_version(SSL.SSLEAY_VERSION).decode(),
        'vendor_runtime_members_identical':same,'vendor_runtime_member_count':len(names),
        'vendor_provenance':json.loads(pathlib.Path('/opt/gateway/vendor-provenance.json').read_text()),
        'installed_pth_files':[str(p) for p in pathlib.Path('/opt/gateway').rglob('*.pth')]}
print(json.dumps(result,indent=2))
