"""Reproducibility/integrity of the narrow metadata-only vendor transformation."""
import base64
import contextlib
import csv
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

spec=importlib.util.spec_from_file_location('vendor_wheel',Path(__file__).with_name('vendor_wheel.py'))
vendor=importlib.util.module_from_spec(spec); spec.loader.exec_module(vendor)

class VendorTests(unittest.TestCase):
    def test_unreviewed_upstream_is_refused_before_output(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); source=root/'source.whl'; source.write_bytes(b'wrong release'); output=root/'candidate.whl'
            with self.assertRaisesRegex(ValueError,'unreviewed'): vendor.patch(source,output)
            self.assertFalse(output.exists())

    def test_only_metadata_changes_and_record_is_valid_reproducibly(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); source=root/'source.whl'
            original={'mitmproxy/runtime.py':b'print("unchanged runtime")\n',
                      vendor.OLD+'METADATA': ('\n'.join(vendor.CHANGES)+'\n').encode(),
                      vendor.OLD+'WHEEL':b'Wheel-Version: 1.0\n',vendor.OLD+'RECORD':b'old'}
            with zipfile.ZipFile(source,'w') as archive:
                for name,data in original.items(): archive.writestr(name,data)
            digest=hashlib.sha256(source.read_bytes()).hexdigest()
            with mock.patch.object(vendor,'UPSTREAM_SHA256',digest),contextlib.redirect_stdout(io.StringIO()):
                vendor.patch(source,root/'one.whl'); vendor.patch(source,root/'two.whl')
            self.assertEqual((root/'one.whl').read_bytes(),(root/'two.whl').read_bytes())
            with zipfile.ZipFile(root/'one.whl') as archive:
                self.assertEqual(archive.read('mitmproxy/runtime.py'),original['mitmproxy/runtime.py'])
                self.assertEqual(archive.read(vendor.NEW+'WHEEL'),original[vendor.OLD+'WHEEL'])
                metadata=archive.read(vendor.NEW+'METADATA').decode()
                self.assertEqual(metadata.splitlines(),list(vendor.CHANGES.values()))
                for name,hashtext,size in csv.reader(io.StringIO(archive.read(vendor.NEW+'RECORD').decode())):
                    if not hashtext: continue
                    data=archive.read(name)
                    actual=base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()
                    self.assertEqual(hashtext,'sha256='+actual); self.assertEqual(int(size),len(data))

    def test_changed_upstream_metadata_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); source=root/'source.whl'
            with zipfile.ZipFile(source,'w') as archive:
                archive.writestr(vendor.OLD+'METADATA','Version: 12.2.3\n')
            with mock.patch.object(vendor,'UPSTREAM_SHA256',hashlib.sha256(source.read_bytes()).hexdigest()):
                with self.assertRaisesRegex(ValueError,'metadata differs'): vendor.patch(source,root/'candidate.whl')

if __name__=='__main__': unittest.main()
