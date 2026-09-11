"""Benign gzip API checks, including fail-closed writes to /dev/full.

No corruption is triggered: the unpatched control only inspects gzclearerr's
error reset and exits without further gzip writes or close on that failed handle.
"""
import ctypes as c
import gzip
import json
from pathlib import Path
import sys
import tempfile


def check(library, *, baseline=False):
    z = c.CDLL(library)
    for name, args, result in (
        ('gzopen', [c.c_char_p, c.c_char_p], c.c_void_p),
        ('gzwrite', [c.c_void_p, c.c_void_p, c.c_uint], c.c_int),
        ('gzflush', [c.c_void_p, c.c_int], c.c_int),
        ('gzerror', [c.c_void_p, c.POINTER(c.c_int)], c.c_char_p),
        ('gzclearerr', [c.c_void_p], None),
        ('gzclose', [c.c_void_p], c.c_int),
    ):
        function = getattr(z, name)
        function.argtypes, function.restype = args, result
    content = b'Lantern ordinary gzip roundtrip\n' * 64
    data = c.create_string_buffer(content)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'ordinary.gz'
        handle = z.gzopen(str(path).encode(), b'wb')
        assert handle
        assert z.gzwrite(handle, data, len(content)) == len(content)
        assert z.gzclose(handle) == 0
        assert gzip.decompress(path.read_bytes()) == content
    handle = z.gzopen(b'/dev/full', b'wb')
    assert handle
    z.gzwrite(handle, data, len(content))
    assert z.gzflush(handle, 2) == -1
    error = c.c_int()
    z.gzerror(handle, c.byref(error))
    assert error.value == -1
    z.gzclearerr(handle)
    z.gzerror(handle, c.byref(error))
    if baseline:
        assert error.value == 0, 'baseline no longer exhibits reset; reassess patch'
    else:
        assert error.value == -1, 'failed writer was revived'
        assert z.gzwrite(handle, data, len(content)) == 0
        assert z.gzclose(handle) == -1
    print(json.dumps({'ordinary_gzip_roundtrip': True, 'terminal_write_error': not baseline,
                      'baseline_reset_observed': baseline, 'passed': True}))


if __name__ == '__main__':
    check(sys.argv[1], baseline='--baseline' in sys.argv[2:])
