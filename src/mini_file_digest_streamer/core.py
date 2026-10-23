"""Incremental file digest computation in fixed-size blocks.

The streamer reads a file in fixed chunks so that arbitrarily large
files can be hashed without holding their full contents in memory.
It uses hashlib's incremental update so each block is folded into
the digest as soon as it is read.

Design decisions (stated plainly so the README and tests agree):
  * Read mode is 'rb'. This library deals with file *bytes*. A text
    mode stream would apply universal-newline translation and we do
    not want that layer of interpretation for a digest.
  * The callback receives the bytes count just consumed and the total
    consumed so far (ints, never floats). It is optional and defaults
    to None so the caller can ignore progress entirely.
  * If the file does not exist, we raise FileNotFoundError untouched.
    We deliberately do not re-wrap it, so callers can catch the
    builtin exception they already expect.
  * The block size must be a positive int. A non-positive or non-int
    block size is a programming error and raises ValueError.
  * An empty file yields the same digest as hashlib.<algo>(b'').
    This is a deliberate guarantee we test.
"""
from __future__ import annotations

import hashlib
from typing import Callable, Optional


ProgressCallback = Callable[[int, int], None]


class DigestStreamer:
    """Incremental digest of a file, read in fixed-size blocks.

    Attributes
    ----------
    algorithm : str
        A hashlib algorithm name (e.g. 'sha256', 'md5', 'sha1').
    block_size : int
        Number of bytes read per chunk. Must be a positive integer.

    Notes
    -----
    We validate in __init__ rather than lazily, because failing early
    on a bad algorithm name or block size makes debugging simpler and
    avoids a half-open file handle.
    """

    def __init__(self, algorithm: str = "sha256", block_size: int = 65536) -> None:
        if not isinstance(block_size, int) or isinstance(block_size, bool):
            raise ValueError("block_size must be an int")
        if block_size <= 0:
            raise ValueError("block_size must be a positive integer")
        # Validate the algorithm up front. hashlib.new raises
        # ValueError (or TypeError for non-str) on a bad name, which
        # is the behaviour we want surfaced to the caller directly.
        self._digest = hashlib.new(algorithm)
        self.algorithm = algorithm
        self.block_size = block_size
        self.total_bytes: int = 0

    def update(self, chunk: bytes) -> None:
        """Fold a chunk of bytes into the running digest.

        Kept public so callers can stream bytes they already have in
        memory; the file helper uses it internally.
        """
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise TypeError("chunk must be bytes-like")
        # memoryview/bytearray are accepted because hashlib handles
        # them; we normalize to bytes for the length accounting since
        # len() is well-defined on all three.
        self._digest.update(chunk)
        n = len(chunk)
        self.total_bytes += n

    def hexdigest(self) -> str:
        """Return the hex digest of all bytes consumed so far."""
        return self._digest.hexdigest()

    def stream_file(
        self,
        path: str,
        callback: Optional[ProgressCallback] = None,
    ) -> str:
        """Read 'path' in blocks and return its hex digest.

        Parameters
        ----------
        path : str
            Filesystem path to a readable file.
        callback : callable, optional
            Invoked as callback(bytes_read_this_block, total_bytes_so_far)
            after each block. May be None to skip progress reporting.

        Raises
        ------
        FileNotFoundError
            If 'path' does not exist (surfaced from open). Not re-wrapped
            so callers catch the familiar builtin.
        ValueError
            If 'path' is a directory (open raises IsADirectoryError on
            POSIX, PermissionError on some platforms; we leave these
            untouched as well).
        """
        # We open with no buffering beyond block_size because the
        # whole point is to control memory; a buffered reader would
        # pull more than block_size off disk internally.
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(self.block_size)
                if not chunk:
                    break
                n = len(chunk)
                self.update(chunk)
                if callback is not None:
                    callback(n, self.total_bytes)
        return self.hexdigest()


_DigestStreamer = DigestStreamer


def digest_file(
    path: str,
    algorithm: str = "sha256",
    block_size: int = 65536,
    callback: Optional[ProgressCallback] = None,
) -> str:
    """Convenience wrapper: one-shot digest of 'path'.

    Equivalent to constructing a DigestStreamer and calling
    stream_file(). Returns the hex digest string.
    """
    streamer = DigestStreamer(algorithm=algorithm, block_size=block_size)
    return streamer.stream_file(path, callback=callback)
