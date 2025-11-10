import os
from .volume import Volume
from exfat import recovery as rc
from tkinter import Tk, filedialog
def run():
    while True:
        print("\n===== MENU CHÍNH =====")
        print("1. tạo volume mới")
        print("2. mở volume có sẵn")
        print("0. Exit")
        ch = input("Chọn: ").strip()
        if ch == '1':
            Tk().withdraw()
            path = filedialog.asksaveasfilename(
                title="Tạo volume mới (.xvol)",
                defaultextension=".xvol",
                filetypes=[("exFAT volume", "*.xvol")]
            )
            if not path:
                print("Huỷ tạo volume.")
                return
            if not path.lower().endswith(".xvol"):
                path += ".xvol"
            size = int(input("Kích thước (MB, ví dụ 32): ") or '32')
            Volume.create(path, size_mb=size)
            print("Đã tạo volume:", path)
        elif ch == '2':
            Tk().withdraw()
            path = filedialog.askopenfilename(
                title="Chọn volume cần mở",
                filetypes=[("exFAT volume", "*.xvol")]
            )
            if not os.path.exists(path):
                print('Không tồn tại'); continue
            vol = Volume(path); vol.open(True)
            menu_volume(vol)
        elif ch == '0':
            return
        else:
            print('Lựa chọn không hợp lệ')

def menu_volume(vol: Volume):
    while True:
        print("\n===== MENU TÁC VỤ =====")
        print("1. import file")
        print("2. export file")
        print("3. show list file")
        print("4. remove file")
        print("5. restore file")
        print("6. Các tình huống")
        print("0. Back")
        ch = input("Chọn: ").strip()
        if ch == '1':
            Tk().withdraw()
            host = filedialog.askopenfilename(title="Chọn file cần import")
            name = input('Tên trên volume: ').strip()
            vol.import_file(host, name)
            print('Đã import.')
        elif ch == '2':
            name = input('Tên file trên volume: ').strip()
            out = input('Nơi lưu (PC): ').strip()
            vol.export_file(name, out); print('Đã export.')
        elif ch == '3':
            files = vol.list_files(); print('Danh sách:')
            for i, e in enumerate(files):
                flag = '[DELETED]' if e.get('deleted') else ''
                print(f"- {i+1}. {e['name']} ({e['size']} bytes) start={e['start']} chain={len(e['chain'])} {flag}")
        elif ch == '4':
            name = input('Tên file cần xoá (logical): ').strip()
            vol.remove_file(name); print("Đã đánh dấu xoá. Dùng 'purge' để xoá hẳn.")
            if input('Xoá hẳn (purge)? y/N: ').lower().startswith('y'):
                vol.purge_file(name); print('Đã purge.')
        elif ch == '5':
            name = input('Tên file cần restore: ').strip()
            try:
                ok = vol.restore_file(name)
                print('Phục hồi:', 'OK' if ok else 'Thất bại')
            except FileNotFoundError:
                ok = rc.recover_deleted_from_shadow(vol, name)
                print('Phục hồi từ shadow:', 'OK' if ok else 'Thất bại')
            except RuntimeError as e:
                print('Lỗi:', e)
        elif ch == '6':
            menu_scenarios(vol)
        elif ch == '0':
            return
        else:
            print('Lựa chọn không hợp lệ')

def menu_scenarios(vol: Volume):
    while True:
        print("\n===== CÁC TÌNH HUỐNG =====")
        print("1. sai phân vùng (gây lỗi / phục hồi)")
        print("2. tham số sai của volume (gây lỗi / phục hồi)")
        print("3. bảng thư mục và cluster sai (gây lỗi / phục hồi)")
        print("4. file/thư mục đã xoá (phục hồi)")
        print("0. back")
        ch = input('Chọn: ').strip()
        if ch == '1':
            sub = input('g) gây lỗi r) recover > ').strip().lower()
            if sub.startswith('g'):
                off = int(input('Offset bytes (mặc định 4096): ') or '4096')
                rc.induce_wrong_partition(vol, off); print('Đã gây lệch phân vùng:', off)
            else:
                ok = rc.recover_wrong_partition(vol); print('Recover partition:', 'OK' if ok else 'FAIL')
        elif ch == '2':
            sub = input('g) gây lỗi r) recover > ').strip().lower()
            if sub.startswith('g'):
                rc.induce_bad_params(vol); print('Đã làm sai tham số volume')
            else:
                ok = rc.recover_params(vol); print('Recover params:', 'OK' if ok else 'FAIL')
        elif ch == '3':
            sub = input('g) gây lỗi r) recover > ').strip().lower()
            if sub.startswith('g'):
                rc.induce_bad_dir_fat(vol); print('Đã phá bảng dir/FAT (mô phỏng)')
            else:
                n = rc.recover_dir_fat(vol); print(f'Đã dựng lại {n} file từ scan heap')
        elif ch == '4':
            name = input('Tên file đã xoá: ').strip()
            ok = rc.recover_deleted_from_shadow(vol, name)
            print('Recover deleted (shadow):', 'OK' if ok else 'FAIL')
        elif ch == '0':
            return
        else:
            print('Lựa chọn không hợp lệ')