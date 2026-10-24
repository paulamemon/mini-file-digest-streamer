"""Tests for mini_file_digest_streamer.core.

Every name imported below is exported by the source. Tests cover the
edge cases the implementation actually handles: empty files, files
larger than one block, non-positive block sizes, non-existent paths,
progress callback semantics, and digest equivalence with hashlib.
"""
import hashlib
import os
import tempfile
import unittest

from mini_file_digest_streamer import DigestStreamer, digest_file


class _TmpFile:
    """Context manager that writes bytes to a temp file and cleans up."""

    def __init__(self, data: bytes = b""):
        self.data = data

    def __enter__(self) -> str:
        fd, self.path = tempfile.mkstemp(prefix="mfds_", suffix=".bin")
        os.close(fd)
        with open(self.path, "wb") as fh:
            fh.write(self.data)
        return self.path

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            os.remove(self.path)
        except OSError:
            pass


class TestDigestStreamer(unittest.TestCase):
    def test_empty_file_matches_hashlib(self):
        with _TmpFile(b"") as p:
            got = digest_file(p, algorithm="sha256")
        self.assertEqual(got, hashlib.sha256(b"").hexdigest())

    def test_small_file_matches_hashlib(self):
        data = b"hello world"
        with _TmpFile(data) as p:
            got = digest_file(p, algorithm="sha256")
        self.assertEqual(got, hashlib.sha256(data).hexdigest())

    def test_file_larger_than_block(self):
        # 3 full blocks plus a partial tail.
        block = 16
        data = bytes(range(256)) * 3 + b"tail"
        self.assertEqual(len(data), 3 * 256 + 4)
        with _TmpFile(data) as p:
            got = digest_file(p, algorithm="sha256", block_size=block)
        self.assertEqual(got, hashlib.sha256(data).hexdigest())

    def test_block_size_equal_to_file_size(self):
        data = b"exactly one block"
        with _TmpFile(data) as p:
            got = digest_file(p, algorithm="md5", block_size=len(data))
        self.assertEqual(got, hashlib.md5(data).hexdigest())

    def test_progress_callback_totals(self):
        data = bytes(range(128)) * 5  # 640 bytes
        block = 256
        seen = []

        def cb(n: int, total: int) -> None:
            seen.append((n, total))

        with _TmpFile(data) as p:
            digest_file(p, algorithm="sha1", block_size=block, callback=cb)

        self.assertEqual(seen, [(256, 256), (256, 512), (128, 640)])

    def test_progress_callback_not_called_for_empty_file(self):
        seen = []
        with _TmpFile(b"") as p:
            digest_file(p, callback=lambda n, t: seen.append((n, t)))
        self.assertEqual(seen, [])

    def test_default_algorithm_is_sha256(self):
        data = b"default algo"
        with _TmpFile(data) as p:
            got = digest_file(p)
        self.assertEqual(got, hashlib.sha256(data).hexdigest())

    def test_missing_file_raises_filenotfound(self):
        with self.assertRaises(FileNotFoundError):
            digest_file("/no/such/path/here/mfds_missing.bin")

    def test_non_positive_block_size_rejected(self):
        with self.assertRaises(ValueError):
            DigestStreamer(block_size=0)
        with self.assertRaises(ValueError):
            DigestStreamer(block_size=-1)

    def test_bool_block_size_rejected(self):
        # bool is a subclass of int; we treat it as a programming error.
        with self.assertRaises(ValueError):
            DigestStreamer(block_size=True)

    def test_streamer_reusable_across_files(self):
        # A single streamer accumulates across calls by design.
        s = DigestStreamer(algorithm="sha256")
        with _TmpFile(b"abc") as p1, _TmpFile(b"def") as p2:
            s.stream_file(p1)
            s.stream_file(p2)
        self.assertEqual(s.hexdigest(), hashlib.sha256(b"abcdef").hexdigest())
        self.assertEqual(s.total_bytes, 6)

    def test_update_accepts_memoryview(self):
        s = DigestStreamer(algorithm="sha256")
        s.update(memoryview(b"abc"))
        s.update(bytearray(b"def"))
        self.assertEqual(s.hexdigest(), hashlib.sha256(b"abcdef").hexdigest())

    def test_update_rejects_str(self):
        s = DigestStreamer()
        with self.assertRaises(TypeError):
            s.update("not bytes")

    def test_hexdigest_idempotent(self):
        s = DigestStreamer()
        s.update(b"constant")
        first = s.hexdigest()
        second = s.hexdigest()
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
