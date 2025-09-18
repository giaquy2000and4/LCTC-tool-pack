#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
LCTC Pipeline CLI — one-file version
- GỘP: tạo cấu trúc thư mục (từ make_lctc.py) + xử lý YouTube/ghi phụ đề (từ transcript.py)
- MỚI: Cho phép đổi TIỀN TỐ (prefix) thay vì cố định 'LCTC' (mặc định vẫn là 'LCTC')

Tính năng chính:
1) Nhập 1 URL hoặc CHỌN FILE .TXT nhiều URL bằng pop-up (thứ tự link = thứ tự mapping)
2) Nhập số bắt đầu -> tool tự tính số kết thúc theo số link
3) Hỏi tiền tố (prefix) và độ dài zero-padding (vd 3 => <PREFIX>-001)
4) Tạo loạt <PREFIX>-[start..end] + subfolders + file docx từ template (nếu có)
5) Trích phụ đề YouTube (yt-dlp), merge youtube_results.json (không ghi đè)
6) Lưu sub.txt & info.txt vào <PREFIX>-<n>/<safe_title>_<videoid>/
"""

import os, sys, re, json, time, shutil, subprocess, random

# ---- Chặn biến môi trường có thể gây PermissionError (sslkeys) khi tải mạng
os.environ.pop("SSLKEYLOGFILE", None)

# ---- Đảm bảo SSL certificates khi đóng gói (yt-dlp tải mạng)
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except Exception:
    pass

# ====== UI ======
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_banner():
    banner = f"""
{Colors.HEADER}{Colors.BOLD}
╔══════════════════════════════════════════════════════════════╗
║                      LCTC Pipeline (CLI)                     ║
║                 (Folder Builder + YouTube Sub)               ║
╚══════════════════════════════════════════════════════════════╝
{Colors.ENDC}
"""
    print(banner)

def progress_bar(current, total, description="Processing", width=50):
    percent = (current / total) * 100 if total else 100.0
    filled = int(width * current // total) if total else width
    bar = '█' * filled + '░' * (width - filled)
    print(f"\r{Colors.OKBLUE}[{bar}] {percent:6.1f}% | {current}/{total} | {description}{Colors.ENDC}",
          end='', flush=True)

# ===== Helper chọn thư mục (lazy import tkinter + fallback)
def choose_directory_topmost(title: str) -> str:
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass
        dest = filedialog.askdirectory(parent=root, title=title,
                                       mustexist=True,
                                       initialdir=os.path.expanduser("~"))
        root.destroy()
        if dest:
            return dest
    except Exception:
        pass
    print(f"{Colors.WARNING}Không dùng được hộp thoại. Nhập đường dẫn thư mục đích:{Colors.ENDC}")
    p = input("> ").strip()
    return p if p else ""

# ====== Cấu trúc thư mục & template (kế thừa make_lctc.py) =====
INVALID = r'[<>:"/\\|?*]'
SUBFOLDERS = ["TAI NGUYEN", "THUMB"]
TEMPLATE = "template.docx"

def sanitize(name: str) -> str:
    return re.sub(INVALID, "-", name).strip().rstrip(".")

def _try_create_template_with_word(path: str) -> bool:
    # Ưu tiên tạo chuẩn bằng python-docx; nếu có Word COM sẽ "chuẩn hóa" thêm
    try:
        from docx import Document
        doc = Document(); doc.add_paragraph(" "); doc.save(path + ".tmp")
        try:
            import pythoncom, win32com.client as win32
            pythoncom.CoInitialize()
            word = win32.gencache.EnsureDispatch("Word.Application")
            word.Visible = False
            docx = word.Documents.Open(os.path.abspath(path + ".tmp"))
            docx.SaveAs(os.path.abspath(path), FileFormat=16)  # wdFormatXMLDocument
            docx.Close(False); word.Quit()
            os.remove(path + ".tmp")
        except Exception:
            # nếu không có Word COM, giữ file .tmp -> .docx từ python-docx
            shutil.move(path + ".tmp", path)
        return True
    except Exception:
        # fallback tối giản
        try:
            open(path, 'a', encoding='utf-8').close()
            return True
        except Exception:
            return False

def ensure_template():
    if not os.path.exists(TEMPLATE):
        print(f"{Colors.WARNING}⚠ Không thấy {TEMPLATE}, đang tạo file mẫu.{Colors.ENDC}")
        ok = _try_create_template_with_word(TEMPLATE)
        if ok:
            print(f"{Colors.OKGREEN}✓ Đã tạo {TEMPLATE}.{Colors.ENDC}")
        else:
            print(f"{Colors.FAIL}✗ Không thể tạo {TEMPLATE}. Sẽ bỏ qua bước tạo .docx mẫu.{Colors.ENDC}")

def new_blank_docx(dst: str):
    if os.path.exists(TEMPLATE):
        shutil.copyfile(TEMPLATE, dst)
    else:
        open(dst, 'a', encoding='utf-8').close()

# ====== PREFIX DYNAMIC ======
DEFAULT_PREFIX = "LCTC"

def make_name(prefix: str, n: int, pad_width: int = 0) -> str:
    if pad_width and pad_width > 0:
        return f"{prefix}-{n:0{pad_width}d}"
    return f"{prefix}-{n}"

def build_range(dest_dir: str, prefix: str, start: int, end: int, pad_width: int = 0):
    """Tạo <prefix>-start..end + subfolders + docx"""
    ensure_template()
    total = end - start + 1
    created = skipped = 0
    for n in range(start, end + 1):
        name = make_name(prefix, n, pad_width)
        safe = sanitize(name)
        base = os.path.join(dest_dir, safe)
        if not os.path.exists(base):
            os.makedirs(base, exist_ok=True); created += 1
        else:
            skipped += 1
        for sf in SUBFOLDERS:
            os.makedirs(os.path.join(base, sf), exist_ok=True)
        main_doc = os.path.join(base, f"{safe}.docx")
        desc_doc = os.path.join(base, "MO TA.docx")
        if not os.path.exists(main_doc): new_blank_docx(main_doc)
        if not os.path.exists(desc_doc): new_blank_docx(desc_doc)
    return total, created, skipped

# ====== Phần YouTube (kế thừa transcript.py) =====
def extract_video_id(url):
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com\/v\/([a-zA-Z0-9_-]{11})',
    ]
    for p in patterns:
        m = re.search(p, url)
        if m: return m.group(1)
    return None

def check_yt_dlp():
    print(f"{Colors.OKCYAN}Đang kiểm tra yt-dlp...{Colors.ENDC}")
    try:
        import yt_dlp  # noqa
        print(f"{Colors.OKGREEN}✓ yt-dlp đã sẵn sàng{Colors.ENDC}")
        return True
    except ImportError:
        if getattr(sys, "frozen", False):
            print(f"{Colors.FAIL}✗ yt-dlp không được đóng gói kèm theo. Hãy rebuild với tham số PyInstaller đúng.{Colors.ENDC}")
            return False
        print(f"{Colors.WARNING}yt-dlp chưa có. Đang cài.{Colors.ENDC}")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "yt-dlp"])
            print(f"{Colors.OKGREEN}✓ Cài xong yt-dlp{Colors.ENDC}")
            return True
        except Exception as e:
            print(f"{Colors.FAIL}✗ Không thể cài yt-dlp: {e}{Colors.ENDC}")
            return False

def download_subtitle_content(url):
    try:
        import urllib.request, json as _json
        with urllib.request.urlopen(url) as resp:
            raw = resp.read().decode('utf-8')
            s = raw.strip()
            if s.startswith('{') or s.startswith('['):
                try:
                    data = _json.loads(raw)
                    if isinstance(data, dict) and "events" in data:
                        lines = []
                        for ev in data["events"]:
                            if "segs" in ev:
                                line = ''.join(seg.get("utf8", "") for seg in ev["segs"]).strip()
                                if line: lines.append(line)
                        return "\n".join(lines)
                    if isinstance(data, list):
                        lines = [it.get("text","") for it in data if it.get("text","")]
                        return "\n".join(lines)
                    return raw
                except Exception:
                    return raw
            return raw
    except Exception:
        return ""

def clean_subtitles(subtitle_content):
    if not subtitle_content: return "Không có nội dung phụ đề"
    out = []
    for line in subtitle_content.splitlines():
        line = line.strip()
        if (not re.match(r'^\d+$', line)
            and not re.match(r'^\d{2}:\d{2}:\d{2}', line)
            and not re.match(r'^(WEBVTT|NOTE)', line)
            and line and line != '--'):
            line = re.sub(r'<[^>]+>', '', line)
            line = re.sub(r'&[a-zA-Z]+;', '', line)
            if line and (not out or out[-1] != line):
                out.append(line)
    return "\n".join(out) or "Không thể trích xuất nội dung phụ đề"

def get_vietnamese_subtitles_direct(info):
    try:
        subs = info.get('subtitles', {}) or {}
        auto = info.get('automatic_captions', {}) or {}
        urls = []
        if 'vi' in subs: urls.append(subs['vi'][0]['url'])
        if 'vi' in auto: urls.append(auto['vi'][0]['url'])
        if 'vi-VN' in auto: urls.append(auto['vi-VN'][0]['url'])
        for u in urls:
            text = download_subtitle_content(u)
            if text:
                return clean_subtitles(text)
        return "Không có phụ đề tiếng Việt"
    except Exception as e:
        return f"Lỗi khi tải phụ đề: {e}"

def get_video_info(url):
    try:
        import yt_dlp
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extractaudio': False,
            'extract_flat': False,
            'sleep_interval': 20,
            'max_sleep_interval': 25,
            'retries': 5,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                'title': info.get('title','Không có tiêu đề'),
                'video_id': info.get('id','unknown'),
                'duration': info.get('duration',0),
                'url': url,
                'subtitles': get_vietnamese_subtitles_direct(info),
                'status': 'success'
            }
    except Exception as e:
        return {'url': url, 'status': 'error', 'error': f'Lỗi khi lấy thông tin: {e}'}

def load_existing_index(results_path='youtube_results.json'):
    if not os.path.exists(results_path): return {}, []
    try:
        with open(results_path,'r',encoding='utf-8') as f:
            data = json.load(f)
        idx, ordered = {}, []
        for item in data:
            vid = item.get('video_id') or extract_video_id(item.get('url','')) or ''
            if vid and vid not in idx:
                idx[vid] = item; ordered.append(item)
        return idx, ordered
    except Exception:
        return {}, []

def save_results_merge(new_results, output_file='youtube_results.json'):
    existing_index, ordered = load_existing_index(output_file)
    appended = 0
    for item in new_results:
        vid = item.get('video_id') or extract_video_id(item.get('url','')) or item.get('url')
        if not vid:
            ordered.append(item); appended += 1; continue
        if vid in existing_index:
            continue
        existing_index[vid] = item; ordered.append(item); appended += 1
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(ordered, f, ensure_ascii=False, indent=2)
    print(f"{Colors.OKGREEN}✓ Gộp kết quả (thêm {appended}) vào youtube_results.json{Colors.ENDC}")

# ===== Đọc URL (pop-up hoặc nhập tay)
def read_urls_from_file(file_path):
    urls = []
    try:
        with open(file_path,'r',encoding='utf-8') as f:
            for ln, line in enumerate(f,1):
                s = line.strip()
                if s and not s.startswith('#'):
                    if extract_video_id(s): urls.append(s)
                    else: print(f"{Colors.WARNING}Dòng {ln}: URL không hợp lệ - {s}{Colors.ENDC}")
    except Exception as e:
        print(f"{Colors.FAIL}Lỗi đọc file: {e}{Colors.ENDC}")
        return None
    return urls

def select_file():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass
        path = filedialog.askopenfilename(
            parent=root,
            title="Chọn file .txt chứa danh sách URL YouTube",
            filetypes=[("Text files","*.txt"), ("All files","*.*")],
            initialdir=os.path.expanduser("~")
        )
        root.destroy()
        if path:
            return path
    except Exception:
        pass
    print(f"{Colors.WARNING}Không dùng được hộp thoại. Nhập đường dẫn file .txt:{Colors.ENDC}")
    p = input("> ").strip()
    return p if p else None

# ===== Pipeline-specific
def safe_title(result_title: str) -> str:
    t = re.sub(INVALID, "_", result_title or "Video").strip()
    return t[:80] if t else "Video"

def process_urls_keep_order(urls):
    """
    - Nếu URL đã có trong youtube_results.json => lấy lại entry cũ (giữ thứ tự/mapping).
    - Thêm sleep ngẫu nhiên giữa các video để tránh rate-limit.
    """
    existing_index, _ = load_existing_index('youtube_results.json')
    results = []
    total = len(urls)
    print(f"\n{Colors.BOLD}Bắt đầu xử lý {total} video(s).{Colors.ENDC}\n")

    min_sleep = 20
    max_sleep = 25

    for i, url in enumerate(urls, 1):
        progress_bar(i-1, total, f"Video {i}")
        vid = extract_video_id(url)
        if vid and vid in existing_index:
            r = existing_index[vid]
            r.setdefault('url', url)
            r.setdefault('status', 'success')
            results.append(r)
            print(f"\n{Colors.OKCYAN}↷ Dùng lại kết quả đã có: {url}{Colors.ENDC}")
            time.sleep(0.05)
        else:
            r = get_video_info(url)
            results.append(r)
            print(f"\n{Colors.OKBLUE}{'OK' if r.get('status')=='success' else 'Lỗi'} - {url}{Colors.ENDC}")
            time.sleep(0.05)

        if i < total:
            wait_time = random.randint(min_sleep, max_sleep)
            print(f"{Colors.WARNING}⏳ Đợi {wait_time} giây trước khi xử lý video tiếp theo.{Colors.ENDC}")
            time.sleep(wait_time)

    progress_bar(total, total, "Hoàn thành"); print()
    return results

def assign_results_to_lctc(results, dest_dir, prefix, start_num, pad_width: int = 0):
    """
    Map tuần tự:
      #1 -> <prefix>-start
      #2 -> <prefix>-(start+1)
      ...
    Lưu: <prefix>-<n>/<safe_title>_<videoid>/{sub.txt, info.txt}
    """
    assigned = 0
    for idx, r in enumerate(results):
        n = start_num + idx
        lctc_dir = os.path.join(dest_dir, make_name(prefix, n, pad_width))
        if not os.path.isdir(lctc_dir):
            print(f"{Colors.WARNING}⚠ Thiếu folder {lctc_dir} (bỏ qua).{Colors.ENDC}")
            continue

        target_base = lctc_dir

        if r.get('status') != 'success':
            folder = os.path.join(target_base, f"ERR_{idx+1:02d}")
            os.makedirs(folder, exist_ok=True)
            with open(os.path.join(folder,'info.txt'),'w',encoding='utf-8') as f:
                f.write(f"URL: {r.get('url')}\n")
                f.write(f"Status: {r.get('status')}\n")
                f.write(f"Error: {r.get('error','')}\n")
            print(f"{Colors.WARNING}↷ Ghi chú lỗi vào {folder}{Colors.ENDC}")
            continue

        title = r.get('title','Video')
        vid = r.get('video_id','unknown')
        sub = r.get('subtitles') or "Không có phụ đề"
        safe = safe_title(title)

        folder = os.path.join(target_base, f"{safe}_{vid}")
        os.makedirs(folder, exist_ok=True)

        sub_path = os.path.join(folder, 'sub.txt')
        info_path = os.path.join(folder, 'info.txt')

        if os.path.exists(sub_path) and os.path.exists(info_path):
            print(f"{Colors.OKCYAN}↷ Bỏ qua (đã tồn tại): {folder}{Colors.ENDC}")
            continue

        with open(sub_path,'w',encoding='utf-8') as f:
            f.write(sub)
        with open(info_path,'w',encoding='utf-8') as f:
            f.write(f"Title: {title}\nVideo ID: {vid}\nURL: {r.get('url')}\n")
            f.write(f"Duration: {r.get('duration','N/A')} seconds\n")
            f.write(f"MappedTo: {make_name(prefix, n, pad_width)}\n")

        assigned += 1
        print(f"{Colors.OKGREEN}✓ Lưu vào: {folder}{Colors.ENDC}")

    print(f"{Colors.OKGREEN if assigned else Colors.WARNING}→ Đã gán {assigned}/{len(results)} video vào {prefix}-*.{Colors.ENDC}")

# ===== Menu
def display_menu():
    print(f"""
{Colors.BOLD}Chọn một tùy chọn:{Colors.ENDC}
{Colors.OKGREEN}1.{Colors.ENDC} Chọn file .txt chứa danh sách URL (MỞ POP-UP)
{Colors.OKGREEN}2.{Colors.ENDC} Nhập 1 URL trực tiếp
{Colors.OKGREEN}3.{Colors.ENDC} Thoát

{Colors.OKCYAN}Nhập lựa chọn (1-3): {Colors.ENDC}""", end="")

def main():
    while True:
        clear_screen(); print_banner()

        if not check_yt_dlp():
            input(f"\n{Colors.FAIL}Thiếu yt-dlp. Nhấn Enter để thoát...{Colors.ENDC}")
            return

        display_menu()
        choice = input().strip()

        if choice == '1':
            clear_screen(); print_banner()
            fp = select_file()
            if not fp:
                input(f"\n{Colors.FAIL}Không thể chọn file. Enter để quay lại...{Colors.ENDC}")
                continue
            urls = read_urls_from_file(fp)
            if not urls:
                input(f"\n{Colors.FAIL}Không có URL hợp lệ. Enter để quay lại...{Colors.ENDC}")
                continue

        elif choice == '2':
            clear_screen(); print_banner()
            u = input(f"{Colors.OKCYAN}Nhập URL YouTube: {Colors.ENDC}").strip()
            if not extract_video_id(u):
                input(f"\n{Colors.FAIL}URL không hợp lệ. Enter để quay lại...{Colors.ENDC}")
                continue
            urls = [u]

        elif choice == '3':
            print(f"\n{Colors.OKGREEN}Tạm biệt!{Colors.ENDC}")
            break

        else:
            input(f"\n{Colors.FAIL}Lựa chọn không hợp lệ. Enter để thử lại...{Colors.ENDC}")
            continue

        # ===== Hỏi tiền tố & số bắt đầu
        print(f"\n{Colors.BOLD}Có {len(urls)} URL hợp lệ.{Colors.ENDC}")
        prefix = input(f"{Colors.OKCYAN}Nhập TIỀN TỐ (prefix) [Enter = {DEFAULT_PREFIX}]: {Colors.ENDC}").strip() or DEFAULT_PREFIX

        while True:
            try:
                start = int(input(f"{Colors.OKCYAN}Nhập số bắt đầu cho {prefix}-*: {Colors.ENDC}").strip())
                break
            except Exception:
                print(f"{Colors.FAIL}Vui lòng nhập số nguyên hợp lệ.{Colors.ENDC}")

        end = start + len(urls) - 1

        # ===== Hỏi padding (gợi ý theo số chữ số của 'end')
        default_width = max(1, len(str(end)))
        raw = input(f"{Colors.OKCYAN}Nhập số chữ số padding (vd 3) [Enter = {default_width}]: {Colors.ENDC}").strip()
        try:
            pad_width = default_width if not raw else max(0, int(raw))
        except Exception:
            pad_width = default_width

        dest = choose_directory_topmost(f"Chọn nơi lưu các {prefix}-*")
        if not dest:
            input(f"\n{Colors.FAIL}Bạn đã hủy chọn nơi lưu. Enter để quay lại...{Colors.ENDC}")
            continue

        # ===== 1) TẠO FOLDER TRƯỚC
        print(f"\n{Colors.OKBLUE}Đang tạo thư mục {make_name(prefix,start,pad_width)} .. {make_name(prefix,end,pad_width)} ...{Colors.ENDC}")
        total, created, skipped = build_range(dest, prefix, start, end, pad_width)
        print(f"{Colors.OKGREEN}✓ Hoàn tất tạo folder (tổng {total}, mới {created}, tồn tại {skipped}).{Colors.ENDC}")

        # ===== 2) TRÍCH PHỤ ĐỀ (giữ thứ tự & tái dụng kết quả cũ)
        results = process_urls_keep_order(urls)
        save_results_merge(results)

        # ===== 3) GÁN SUB VÀO TỪNG <prefix>-<n>
        print(f"\n{Colors.OKBLUE}Đang gán phụ đề vào từng {make_name(prefix,start,pad_width)} .. {make_name(prefix,end,pad_width)}{Colors.ENDC}")
        assign_results_to_lctc(results, dest, prefix, start, pad_width)

        input(f"\n{Colors.OKCYAN}Xong! Nhấn Enter để quay lại menu...{Colors.ENDC}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}Đã hủy bởi người dùng.{Colors.ENDC}")
