import json
from .constants import MAGIC, BOOT_SIZE
from .boot import Boot

# 1) Sai phân vùng -------------------------------------------------------------


def induce_wrong_partition(vol, offset_bytes: int = 4096):
    vol.boot.partition_offset = offset_bytes
    vol.flush_boot()




def recover_wrong_partition(vol) -> bool:
    for off in (0, BOOT_SIZE, 4096, 1024*1024):
        hdr = vol.read(off, BOOT_SIZE)
        b = Boot.unpack(hdr)
        if b.magic == MAGIC and b.snapshot.get('cluster_count'):
            vol.boot.partition_offset = off
            vol.flush_boot()
            return True
    b = Boot.unpack(vol.read(BOOT_SIZE, BOOT_SIZE))
    if b.magic == MAGIC:
        vol.boot.partition_offset = BOOT_SIZE
        vol.flush_boot(); return True
    return False
# 2) Tham số volume sai --------------------------------------------------------


def induce_bad_params(vol):
    vol.boot.bytes_per_sector = 256
    vol.boot.sectors_per_cluster = 1
    vol.flush_boot()




def recover_params(vol) -> bool:
    snap = vol.boot.snapshot
    ok = False
    if snap:
        vol.boot.bytes_per_sector = int(snap.get('bytes_per_sector', 512))
        vol.boot.sectors_per_cluster = int(snap.get('sectors_per_cluster', 8))
        vol.boot.cluster_count = int(snap.get('cluster_count', vol.boot.cluster_count))
        ok = True
    else:
        cc = vol.boot.fat_length // 4
        if vol.boot.bitmap_length * 8 >= cc:
            vol.boot.cluster_count = cc
            heap_len = vol.boot.heap_length
            per = heap_len // cc if cc else 0
        if per >= 512 and per % 512 == 0:
            vol.boot.bytes_per_sector = 512
            vol.boot.sectors_per_cluster = per // 512
            ok = True
    if ok: vol.flush_boot()
    return ok

# 3) Bảng thư mục & cluster sai ------------------------------------------------


def induce_bad_dir_fat(vol):
    vol.write(vol.boot.fat_offset + vol.boot.partition_offset, b'\x00'*vol.boot.fat_length)
    vol.write(vol.boot.bitmap_offset + vol.boot.partition_offset, b'\x00'*vol.boot.bitmap_length)
    # xoá 5 entry đầu
    for i in range(min(5, len(vol.dir))):
        if vol.dir[i]:
            vol.write(vol.boot.dir_offset + i*256 + vol.boot.partition_offset, b'\x00'*256)
            vol.dir[i] = None




def recover_dir_fat(vol) -> int:
    rebuilt = 0
    per = vol.cluster_size()
    new_fat = [0]*(vol.boot.cluster_count+1)
    new_bitmap = bytearray(vol.boot.bitmap_length)
    new_dir = [None]*vol.boot.root_dir_entries


    def bset(i):
        b=i-1; new_bitmap[b//8] |= (1 << (b%8))


        free_dir = 0
        for c in range(1, vol.boot.cluster_count+1):
            off = vol.cluster_off(c) + vol.boot.partition_offset
            hdr = vol.read(off, 256)
            if b'XFATSIM_FILE' in hdr:
                try:
                    d = json.loads(hdr.split(b'\n',1)[0].decode('utf-8'))
                    name = d.get('XFATSIM_FILE'); size = int(d.get('size',0))
                except Exception:
                    continue
                need = (size + per -1)//per if size else 1
                chain = [c]; bset(c)
                for k in range(1, need):
                    if c+k > vol.boot.cluster_count: break
                    chain.append(c+k); bset(c+k)
                for i,ch in enumerate(chain):
                    new_fat[ch] = 0xFFFFFFFF if i==len(chain)-1 else chain[i+1]
                entry = { 'name': name, 'size': size, 'start': chain[0], 'chain': chain,
                        'deleted': False, 'attrs': {'readonly': False} }
                if free_dir < len(new_dir):
                    new_dir[free_dir] = entry; free_dir += 1
                rebuilt += 1
        vol.fat = new_fat; vol.bitmap = new_bitmap; vol.dir = new_dir
        # commit
        vol.flush_boot(); vol.flush_fat(); vol.flush_bitmap(); vol.flush_dir()
        return rebuilt

# 4) File/thư mục đã xoá -------------------------------------------------------


def recover_deleted_from_shadow(vol, name: str) -> bool:
    shadow = vol.boot.snapshot.get('dir_shadow') or []
    for e in shadow:
        if e and e.get('name') == name:
            if all(vol.bitmap_get(c) for c in e.get('chain', [])):
                for i in range(len(vol.dir)):
                    if vol.dir[i] is None:
                        vol.dir[i] = e
                        vol.flush_dir(); return True
    return False