import struct, json
from dataclasses import dataclass, field
from .constants import MAGIC, BOOT_SIZE

@dataclass
class Boot:
    magic: bytes = MAGIC
    version: int = 1
    volume_size: int = 0
    bytes_per_sector: int = 512
    sectors_per_cluster: int = 8
    cluster_count: int = 0
    fat_offset: int = 0
    fat_length: int = 0
    bitmap_offset: int = 0
    bitmap_length: int = 0
    dir_offset: int = 0
    dir_length: int = 0
    heap_offset: int = 0
    heap_length: int = 0
    root_dir_entries: int = 1024
    partition_offset: int = 0
    snapshot: dict = field(default_factory=dict)


    def pack(self) -> bytes:
        hdr = bytearray(BOOT_SIZE)
        def put64(off, v): hdr[off:off+8] = struct.pack('<Q', v)
        def put32(off, v): hdr[off:off+4] = struct.pack('<I', v)
        hdr[0:8] = self.magic
        put32(8, self.version)
        put64(12, self.volume_size)
        put32(20, self.bytes_per_sector)
        put32(24, self.sectors_per_cluster)
        put32(28, self.cluster_count)
        put64(32, self.fat_offset)
        put64(40, self.fat_length)
        put64(48, self.bitmap_offset)
        put64(56, self.bitmap_length)
        put64(64, self.dir_offset)
        put64(72, self.dir_length)
        put64(80, self.heap_offset)
        put64(88, self.heap_length)
        put64(96, self.root_dir_entries)
        put64(104, self.partition_offset)
        snap = json.dumps(self.snapshot, separators=(',', ':')).encode('utf-8')[:392]
        hdr[120:120+len(snap)] = snap
        return bytes(hdr)


    @staticmethod
    def unpack(buf: bytes) -> 'Boot':
        def get64(off): return struct.unpack('<Q', buf[off:off+8])[0]
        def get32(off): return struct.unpack('<I', buf[off:off+4])[0]
        b = Boot(
            magic=buf[0:8],
            version=get32(8),
            volume_size=get64(12),
            bytes_per_sector=get32(20),
            sectors_per_cluster=get32(24),
            cluster_count=get32(28),
            fat_offset=get64(32),
            fat_length=get64(40),
            bitmap_offset=get64(48),
            bitmap_length=get64(56),
            dir_offset=get64(64),
            dir_length=get64(72),
            heap_offset=get64(80),
            heap_length=get64(88),
            root_dir_entries=get64(96),
            partition_offset=get64(104),
            )
        snap_raw = buf[120:512]
        try:
            snap_txt = snap_raw.split(b'\x00', 1)[0].decode('utf-8', 'ignore')
            b.snapshot = json.loads(snap_txt) if snap_txt else {}
        except Exception:
            b.snapshot = {}
        return b