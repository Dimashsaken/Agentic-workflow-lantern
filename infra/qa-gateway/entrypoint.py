"""Generate a session-local CA in tmpfs and start the locked-down candidate."""
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def main():
    os.umask(0o077)
    directory = Path('/tmp/qa-ca')
    directory.mkdir(mode=0o700)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Lantern ephemeral QA CA')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(seconds=30))
            .not_valid_after(now+timedelta(hours=24)).add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False,
               data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
               encipher_only=False, decipher_only=False), critical=True).sign(key, hashes.SHA256()))
    public = cert.public_bytes(serialization.Encoding.PEM)
    (directory/'mitmproxy-ca.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()) + public)
    (directory/'mitmproxy-ca-cert.pem').write_bytes(public)
    args = ['/opt/gateway/bin/mitmdump', '--quiet', '--listen-host', '0.0.0.0', '--listen-port', '8080',
            '-s', '/opt/gateway/policy.py', '--set', 'confdir=/tmp/qa-ca']
    for option in ('connection_strategy=lazy', 'upstream_cert=false', 'ssl_insecure=false', 'http2=false',
                   'http3=false', 'websocket=false', 'rawtcp=false', 'onboarding=false',
                   'validate_inbound_headers=true', 'body_size_limit=8m',
                   'tcp_timeout=30', 'flow_detail=0'):
        args.extend(['--set', option])
    os.execv(args[0], args)


if __name__ == '__main__':
    main()
