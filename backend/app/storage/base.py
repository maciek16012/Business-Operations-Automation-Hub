from abc import ABC, abstractmethod
from pathlib import Path, PurePosixPath
from uuid import uuid4


class ObjectStorage(ABC):
    @abstractmethod
    def put(self, content: bytes) -> str: ...

    @abstractmethod
    def get(self, key: str) -> bytes: ...


class LocalFilesystemStorage(ObjectStorage):
    def __init__(self, base_directory: str):
        self.base = Path(base_directory).resolve()
        self.base.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if not key or "\\" in key or ":" in key:
            raise ValueError("Invalid storage key")
        relative = PurePosixPath(key)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Invalid storage key")
        target = (self.base / key).resolve()
        if not target.is_relative_to(self.base) or target == self.base:
            raise ValueError("Invalid storage key")
        return target

    def put(self, content: bytes) -> str:
        key = uuid4().hex
        with self._path(key).open("xb") as target:
            target.write(content)
        return key

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()
