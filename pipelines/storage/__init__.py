"""Durable immutable files on a private Linux/POSIX data volume."""

import hashlib
import os
import re
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from uuid import uuid4

from shared.contracts.analytics import FileDescriptor


class ImmutableConflict(RuntimeError):
    pass


class DurabilityUnavailable(RuntimeError):
    pass


def sync_directory(path):
    if os.name != "posix":
        raise DurabilityUnavailable("Directory fsync requires the Linux data volume")
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class FileStore:
    def __init__(self, root):
        root = Path(root)
        if root.is_symlink() or not root.is_dir():
            raise ValueError("FileStore root must be an existing private data directory")
        self.root = root.resolve(strict=True)
        sync_directory(self.root)

    def _path(self, path):
        if (
            not isinstance(path, str)
            or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_./-]{0,511}", path)
            or any(part in {"", ".", ".."} for part in path.split("/"))
            or PurePosixPath(path).is_absolute()
        ):
            raise ValueError("Expected a relative immutable path without traversal")
        current = self.root
        for part in path.split("/"):
            current /= part
            if current.is_symlink():
                raise ValueError("FileStore paths cannot contain symlinks")
        return current

    @contextmanager
    def _locked(self):
        import fcntl

        descriptor = os.open(
            self.root / ".filestore.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
        )
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            os.close(descriptor)

    def _sync_parents(self, directory):
        while True:
            sync_directory(directory)
            if directory == self.root:
                return
            directory = directory.parent

    def write_immutable(self, path, data, sha256):
        """Three-argument contract; opaque bytes have zero interpreted rows."""
        if not isinstance(data, bytes) or hashlib.sha256(data).hexdigest() != sha256:
            raise ValueError("Immutable content does not match its SHA-256")
        target = self._path(path)
        with self._locked():
            target = self._path(path)
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            self._sync_parents(target.parent)
            if target.exists():
                if not self.exists_with_hash(path, sha256):
                    raise ImmutableConflict("Immutable path already has different content")
                with target.open("rb") as stream:
                    os.fsync(stream.fileno())
                self._sync_parents(target.parent)
            else:
                temporary = target.with_name("_tmp-" + uuid4().hex)
                try:
                    with temporary.open("xb") as stream:
                        stream.write(data)
                        stream.flush()
                        os.fsync(stream.fileno())
                    # Cooperating writers share this volume lock; never overwrite a winner.
                    os.replace(temporary, target)
                    self._sync_parents(target.parent)
                finally:
                    if temporary.exists():
                        temporary.unlink()
            if not self.exists_with_hash(path, sha256):
                raise ImmutableConflict("Immutable file failed read-back verification")
        return FileDescriptor(
            path=path,
            sha256=sha256,
            byte_size=len(data),
            row_count=0,
            schema_name="opaque-bytes",
            schema_version=1,
            partition_values={},
            min_event_time=None,
            max_event_time=None,
        )

    def read(self, path):
        return self._path(path).read_bytes()

    def exists_with_hash(self, path, sha256):
        target = self._path(path)
        if not target.exists():
            return False
        digest = hashlib.sha256()
        with target.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest() == sha256

    def list_orphans(self, manifest_set):
        """Read-only inventory; callers supply ALL retained/replay/reader references."""
        referenced = set(manifest_set)
        for path in referenced:
            self._path(path)
        result = []
        with self._locked():
            for directory, subdirs, files in os.walk(self.root, followlinks=False):
                if any((Path(directory) / name).is_symlink() for name in subdirs + files):
                    raise ValueError("FileStore cannot inventory symlinks")
                for name in files:
                    path = (Path(directory) / name).relative_to(self.root).as_posix()
                    if path != ".filestore.lock" and path not in referenced:
                        result.append(path)
        return sorted(result)
