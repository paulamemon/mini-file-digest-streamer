# mini-file-digest-streamer

Computes an incremental hash digest of a file in fixed-size blocks so large files can be hashed without loading them fully into memory.

```python
import hashlib
from mini_file_digest_streamer import DigestStreamer, digest_file

# Write a small temp file for demonstration.
with open("example.bin", "wb") as f:
    f.write(b"hello world" * 1000)

# One-shot convenience function.
print(digest_file("example.bin", algorithm="sha256", block_size=65536))

# Or drive a streamer yourself to keep state across multiple inputs.
s = DigestStreamer(algorithm="sha256", block_size=65536)
print(s.stream_file("example.bin", callback=lambda n, total: print(f"{total} bytes")))
print(s.hexdigest())

# Sanity check against hashlib.
print(hashlib.sha256(open("example.bin", "rb").read()).hexdigest())
```

## Why this exists

Hashing a multi-gigabyte file by reading it whole is wasteful and often
impossible under memory limits. This library wraps `hashlib`'s
incremental `update` with a simple fixed-block read loop, giving a
memory ceiling of roughly `block_size` bytes.

The trade-off is speed for predictability: a larger `block_size` means
fewer `read()` syscalls but a higher peak memory footprint. The default
of 65536 is a conservative choice that works well across SSDs and spinning
disks without tuning.

## Exported names

* `DigestStreamer(algorithm="sha256", block_size=65536)` — the class.
  * `.stream_file(path, callback=None) -> str` — read `path` in blocks,
    fold each into the running digest, return the hex digest.
  * `.update(chunk) -> None` — fold an in-memory bytes-like chunk in.
  * `.hexdigest() -> str` — return the current hex digest (idempotent).
  * `.total_bytes` — int, bytes consumed so far.
  * `.algorithm`, `.block_size` — the configured values.
* `digest_file(path, algorithm="sha256", block_size=65536, callback=None) -> str`
  — convenience wrapper that constructs a fresh `DigestStreamer` and
  returns its hex digest.

The `callback`, if given, is called as `callback(bytes_read_this_block,
total_bytes_so_far)` after every non-empty block. Both arguments are
ints.

## Edge cases worth knowing

* A `DigestStreamer` accumulates across `update` and `stream_file` calls.
  Calling `stream_file` twice on the same instance hashes the
  concatenation of both inputs, not each in isolation. This is intentional
  and is tested; if you want independent digests, construct a fresh
  streamer per file.
* The file is opened in `'rb'`. Universal-newline translation does not
  apply. The digest is of the file's raw bytes.
* A missing path surfaces as `FileNotFoundError` from `open()`; we do not
  re-wrap it.
* `block_size` must be a positive `int`. Booleans are rejected even though
  `bool` subclasses `int`, because passing `True` is almost certainly a bug.
* An empty file yields the digest of `b""`, and the progress callback is
  not invoked for it.
