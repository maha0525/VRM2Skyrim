"""Read Skyrim BSA v104/105. Extract explicitly named files into local references."""
import logging
from pathlib import Path
import struct
import zlib


class BSA:
    def __init__(self, path):
        self.path = Path(path)
        self.entries = {}
        with self.path.open("rb") as stream:
            header = stream.read(36)
            magic, self.version, folder_offset, self.flags, folder_count, file_count, _, names_length, _ = struct.unpack("<4s8I", header)
            if magic != b"BSA\0" or self.version not in (104, 105):
                raise ValueError("Unsupported BSA version")
            if self.flags & 3 != 3:
                raise ValueError("BSA must contain folder and file names")
            stream.seek(folder_offset)
            folders = []
            for _ in range(folder_count):
                record = stream.read(24 if self.version == 105 else 16)
                count = struct.unpack_from("<I", record, 8)[0]
                folders.append(count)
            files = []
            for count in folders:
                length = stream.read(1)[0]
                folder = stream.read(length).rstrip(b"\0").decode("utf-8")
                for _ in range(count):
                    _, size, offset = struct.unpack("<QII", stream.read(16))
                    files.append((folder, size, offset))
            names = stream.read(names_length).split(b"\0")
            if len(files) != file_count or len(names) < file_count:
                raise ValueError("Bad BSA name table")
            for (folder, size, offset), name in zip(files, names):
                key = (folder + "\\" + name.decode("utf-8")).replace("\\", "/").lower()
                self.entries[key] = (size, offset)

    def read(self, name):
        size, offset = self.entries[name.replace("\\", "/").lower()]
        compressed = bool(self.flags & 4) ^ bool(size & 0x40000000)
        size &= 0x3FFFFFFF
        with self.path.open("rb") as stream:
            stream.seek(offset)
            blob = stream.read(size)
        if len(blob) != size:
            raise ValueError("Truncated BSA file")
        if self.flags & 0x100:
            blob = blob[1 + blob[0]:]
        if compressed:
            expected = struct.unpack_from("<I", blob)[0]
            if self.version == 105:
                import lz4.frame
                blob = lz4.frame.decompress(blob[4:])
            else:
                blob = zlib.decompress(blob[4:])
            if len(blob) != expected:
                raise ValueError("BSA decompressed size mismatch")
        return blob

    def extract(self, name, destination):
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.read(name))
        logging.info("Reference extracted: %s -> %s", name, target)
        return target
