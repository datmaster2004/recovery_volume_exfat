from __future__ import annotations
import os, struct, json
from typing import List, Optional, Dict, Tuple
from .constants import MAGIC, VERSION, BOOT_SIZE, ENTRY_SIZE
from .boot import Boot
from exfat import boot

class Volume:
    def __init__(self, path: str):
        self.path = path
        self.f = None
        self.boot: Optional[Boot] = None
        self.fat: List[int] = [] # 0=free, 0xFFFFFFFF=end, >0=next
        self.bitmap: bytearray = bytearray()
        self.dir: List[Optional[Dict]] = []
    # ---------- low-level I/O (public) ----------
    def open_file(self, mode='r+b'):
        self.f = open(self.path, mode)
    def write(self, off: int, data: bytes):
        self.f.seek(off); self.f.write(data)
    def read(self, off: int, size: int) -> bytes:
        self.f.seek(off); return self.f.read(size)
    # ---------- helpers ----------
    def cluster_size(self) -> int:
        return self.boot.bytes_per_sector * self.boot.sectors_per_cluster
    def cluster_off(self, cidx: int) -> int:
        if cidx < 1 or cidx > self.boot.cluster_count:
            raise ValueError('cluster out of range')
        return self.boot.heap_offset + (cidx - 1) * self.cluster_size()
    # ---------- create/open ----------
    @staticmethod
    def create(path: str, size_mb: int = 32, bytes_per_sector: int = 512,
    sectors_per_cluster: int = 8, root_dir_entries: int = 1024):
        total_bytes = size_mb * 1024 * 1024
        cluster_size = bytes_per_sector * sectors_per_cluster
        # tạm tính; sẽ tinh chỉnh sau khi bố trí metadata
        cluster_count = max(256, (total_bytes // cluster_size) - 8)
        def align(x, a=512): return (x + (a - 1)) // a * a
        fat_len = align(cluster_count * 4)
        bitmap_len = align((cluster_count + 7)//8)
        dir_len = align(root_dir_entries * ENTRY_SIZE)
        off = BOOT_SIZE * 2
        fat_off = off; off += fat_len
        bitmap_off = off; off += bitmap_len
        dir_off = off; off += dir_len
        heap_off = off
        heap_len = total_bytes - heap_off
        cluster_count = heap_len // cluster_size
        heap_len = cluster_count * cluster_size
        boot = Boot(
        magic=MAGIC, version=VERSION, volume_size=total_bytes,
        bytes_per_sector=bytes_per_sector, sectors_per_cluster=sectors_per_cluster,
        cluster_count=cluster_count, fat_offset=fat_off, fat_length=fat_len,
        bitmap_offset=bitmap_off, bitmap_length=bitmap_len,
        dir_offset=dir_off, dir_length=dir_len,
        heap_offset=heap_off, heap_length=heap_len,
        root_dir_entries=root_dir_entries, partition_offset=0,
        )
        boot.snapshot = {
        'cluster_count': cluster_count,
        'bytes_per_sector': bytes_per_sector,
        'sectors_per_cluster': sectors_per_cluster,
        'root_dir_entries': root_dir_entries,
        'dir_shadow': []
        }
        with open(path, 'wb') as f:
            f.truncate(total_bytes)
            prim = boot.pack()
            f.seek(0); f.write(prim)
            f.seek(BOOT_SIZE); f.write(prim)
            f.seek(fat_off); f.write(b'\x00'*fat_len)
            f.seek(bitmap_off); f.write(b'\x00'*bitmap_len)
            f.seek(dir_off); f.write(b'\x00'*dir_len)
        vol = Volume(path)
        vol.open(True)
        vol._init_in_memory(boot)
        vol._flush_all()
        vol.f.close()
    def open(self, write=True):
        self.open_file('r+b' if write else 'rb')
        base = self.read(0, BOOT_SIZE)
        boot = Boot.unpack(base)
        if boot.magic != MAGIC:
        # thử các offset phổ biến
            for off in (BOOT_SIZE, 4096, 1024*1024):
                hdr = self.read(off, BOOT_SIZE)
                b2 = Boot.unpack(hdr)
                if b2.magic == MAGIC:
                    boot = b2; break
        self.boot = boot
        # load regions
        fat_bytes = self.read(boot.fat_offset + boot.partition_offset, boot.fat_length)
        self.fat = [0]
        for i in range(0, len(fat_bytes), 4):
            if len(self.fat) > boot.cluster_count: break
            self.fat.append(struct.unpack('<I', fat_bytes[i:i+4])[0])
        self.bitmap = bytearray(self.read(boot.bitmap_offset + boot.partition_offset, boot.bitmap_length))
        self.dir = []
        for i in range(0, boot.dir_length, ENTRY_SIZE):
            raw = self.read(boot.dir_offset + i + boot.partition_offset, ENTRY_SIZE)
            if raw.strip(b"\x00") == b"":
                self.dir.append(None); continue
            try:
                entry = json.loads(raw.rstrip(b"\x00").decode('utf-8'))
            except Exception:
                entry = None
            self.dir.append(entry)
    # ---------- in-memory init ----------
    def _init_in_memory(self, boot: Boot):
        self.boot = boot
        self.fat = [0]*(boot.cluster_count+1)
        self.bitmap = bytearray(boot.bitmap_length)
        self.dir = [None]*boot.root_dir_entries
    # ---------- flush ----------
    def flush_boot(self):
        prim = self.boot.pack()
        self.write(0 + self.boot.partition_offset, prim)
        self.write(BOOT_SIZE + self.boot.partition_offset, prim)
    def flush_fat(self):
        b = bytearray()
        for i in range(1, self.boot.cluster_count+1):
            v = self.fat[i] if i < len(self.fat) else 0
            b += struct.pack('<I', v)
        self.write(self.boot.fat_offset + self.boot.partition_offset, bytes(b))
    def flush_bitmap(self):
        self.write(self.boot.bitmap_offset + self.boot.partition_offset, bytes(self.bitmap))
    def flush_dir(self):
        shadow = []
        for e in self.dir: shadow.append(e)
        self.boot.snapshot['dir_shadow'] = shadow
        self.flush_boot()
        for idx, e in enumerate(self.dir):
            off = self.boot.dir_offset + idx*ENTRY_SIZE + self.boot.partition_offset
            if e is None:
                self.write(off, b'\x00'*ENTRY_SIZE)
            else:
                buf = json.dumps(e, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
                buf = buf[:ENTRY_SIZE]
                buf += b'\x00'*(ENTRY_SIZE-len(buf))
                self.write(off, buf)
    def _flush_all(self):
        self.flush_boot(); self.flush_fat(); self.flush_bitmap(); self.flush_dir()
    # ---------- bitmap helpers ----------
    def bitmap_set(self, idx: int, val: bool):
        b = idx-1; byte = b//8; bit = b%8
        if val: self.bitmap[byte] |= (1<<bit)
        else: self.bitmap[byte] &= ~(1<<bit)
    def bitmap_get(self, idx: int) -> bool:
        b = idx-1; byte=b//8; bit=b%8
        return (self.bitmap[byte]>>bit)&1 == 1
    # ---------- allocation ----------
    def alloc_clusters(self, need: int) -> list[int]:
        free_list = [i for i in range(1, self.boot.cluster_count+1) if not self.bitmap_get(i)]
        if len(free_list) < need: raise RuntimeError('Không đủ dung lượng')
        # chọn dãy liên tục dài nhất trước
        best_run, run, prev = [], [], -999
        for i in free_list:
            if i == prev+1: run.append(i)
            else:
                if len(run) > len(best_run): best_run = run
                run = [i]
            prev = i
        if len(run) > len(best_run): best_run = run
        chosen = best_run[:need] if len(best_run) >= need else free_list[:need]
        for c in chosen: self.bitmap_set(c, True)
        for i, c in enumerate(chosen):
            self.fat[c] = 0xFFFFFFFF if i==len(chosen)-1 else chosen[i+1]
        return chosen
    def free_chain(self, start: int):
        c = start; visited=set()
        while c not in visited and 1<=c<=self.boot.cluster_count and c!=0:
            visited.add(c)
            self.bitmap_set(c, False)
            nxt = self.fat[c]; self.fat[c]=0
            if nxt in (0xFFFFFFFF, 0): break
            c = nxt
    # ---------- dir helpers ----------
    def find_entry(self, name: str) -> Optional[Dict]:
        for e in self.dir:
            if e and e['name']==name: return e
        return None
    def find_idx(self, name: str):
        for i, e in enumerate(self.dir):
            if e and e['name']==name: return i, e
        return -1, None
    # ---------- file ops ----------
    def import_file(self, host_path: str, name: str):
        data = open(host_path, 'rb').read()
        size = len(data); per = self.cluster_size()
        need = (size + per - 1)//per if size else 1
        chain = self.alloc_clusters(need)
        pos = 0
        for c in chain:
            off = self.cluster_off(c) + self.boot.partition_offset
            chunk = data[pos:pos+per]
            self.write(off, chunk + b'\x00'*(per-len(chunk)))
            pos += len(chunk)
        entry = { 'name': name, 'size': size, 'start': chain[0], 'chain': chain,
        'deleted': False, 'attrs': {'readonly': False} }
        for i in range(len(self.dir)):
            if self.dir[i] is None:
                self.dir[i] = entry
                self.flush_fat(); self.flush_bitmap(); self.flush_dir()
                # nhúng header hỗ trợ recover (kịch bản 3)
                self.embed_header_to_first_cluster(entry)
                return
        raise RuntimeError('Hết slot thư mục')
    def export_file(self, name: str, out_path: str):
        e = self.find_entry(name)
        if not e: raise FileNotFoundError
        data = bytearray(); per = self.cluster_size(); c = e['start']
        read_bytes = 0; visited=set()
        while c not in visited and 1<=c<=self.boot.cluster_count and read_bytes < e['size']:
            visited.add(c)
            off = self.cluster_off(c) + self.boot.partition_offset
            buf = self.read(off, per)
            need = min(per, e['size']-read_bytes)
            data += buf[:need]; read_bytes += need
            nxt = self.fat[c]
            if nxt in (0xFFFFFFFF, 0): break
            c = nxt
        with open(out_path, 'wb') as f: f.write(bytes(data))
    def list_files(self):
        return [e for e in self.dir if e]
    def remove_file(self, name: str):
        idx, e = self.find_idx(name)
        if e is None: raise FileNotFoundError
        e['deleted'] = True; self.dir[idx] = e; self.flush_dir()
    def purge_file(self, name: str):
        idx, e = self.find_idx(name)
        if e is None: raise FileNotFoundError
        self.free_chain(e['start'])
        self.dir[idx] = None
        self.flush_fat(); self.flush_bitmap(); self.flush_dir()
    def restore_file(self, name: str):
        idx, e = self.find_idx(name)
        if e and e.get('deleted'):
            intact = all(self.bitmap_get(c) for c in e['chain'])
            if not intact: raise RuntimeError('Đã bị ghi đè 1 phần — không thể phục hồi nguyên vẹn')
            e['deleted'] = False; self.dir[idx] = e; self.flush_dir(); return True
        raise FileNotFoundError
    def embed_header_to_first_cluster(self, e: Dict):
        c = e['start']; off = self.cluster_off(c) + self.boot.partition_offset
        info = json.dumps({'XFATSIM_FILE': e['name'], 'size': e['size']}).encode('utf-8') + b"\n"
        cur = self.read(off, len(info))
        if cur != info: self.write(off, info)