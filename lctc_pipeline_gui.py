#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import json
from typing import Optional, List, Dict, Any, Callable

# ---- Chặn biến môi trường có thể gây PermissionError (sslkeys) khi tải mạng
os.environ.pop("SSLKEYLOGFILE", None)

# ---- Đảm bảo SSL certificates khi đóng gói (yt-dlp tải mạng)
try:
    import certifi

    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except Exception:
    pass

# Import external dependencies if they exist, otherwise mark as missing
DOCX_AVAILABLE = False
try:
    from docx import Document

    DOCX_AVAILABLE = True
except ImportError:
    # print("Warning: python-docx not found. DOCX generation will be basic.", file=sys.stderr)
    pass  # Will log to GUI if applicable

YTDLP_AVAILABLE = False
try:
    import yt_dlp

    YTDLP_AVAILABLE = True
except ImportError:
    # print("Warning: yt-dlp not found. YouTube subtitle extraction will not work.", file=sys.stderr)
    pass  # Will log to GUI if applicable

# ====== Cấu trúc thư mục & template (kế thừa make_lctc.py) =====
INVALID = r'[<>:"/\\|?*]'
SUBFOLDERS = ["TAI NGUYEN", "THUMB"]
TEMPLATE = "template.docx"
DEFAULT_PREFIX = "LCTC"


def sanitize(name: str) -> str:
    return re.sub(INVALID, "-", name).strip().rstrip(".")


def _try_create_template_with_word(path: str) -> bool:
    if not DOCX_AVAILABLE:
        try:  # fallback to simple file creation
            open(path, 'a', encoding='utf-8').close()
            return True
        except Exception:
            return False

    try:
        doc = Document();
        doc.add_paragraph(" ");
        doc.save(path + ".tmp")
        try:
            import pythoncom, win32com.client as win32
            pythoncom.CoInitialize()
            word = win32.gencache.EnsureDispatch("Word.Application")
            word.Visible = False
            docx = word.Documents.Open(os.path.abspath(path + ".tmp"))
            docx.SaveAs(os.path.abspath(path), FileFormat=16)  # wdFormatXMLDocument
            docx.Close(False);
            word.Quit()
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


def ensure_template_gui(log_func: Callable[[str, Optional[str]], None]):
    if not os.path.exists(TEMPLATE):
        log_func(f"⚠ Không thấy {TEMPLATE}, đang tạo file mẫu.", "yellow")
        ok = _try_create_template_with_word(TEMPLATE)
        if ok:
            log_func(f"✓ Đã tạo {TEMPLATE}.", "green")
        else:
            log_func(f"✗ Không thể tạo {TEMPLATE}. Sẽ bỏ qua bước tạo .docx mẫu.", "red")


def new_blank_docx_gui(dst: str):
    if os.path.exists(TEMPLATE):
        shutil.copyfile(TEMPLATE, dst)
    else:
        open(dst, 'a', encoding='utf-8').close()


def make_name(prefix: str, n: int, pad_width: int = 0) -> str:
    if pad_width and pad_width > 0:
        return f"{prefix}-{n:0{pad_width}d}"
    return f"{prefix}-{n}"


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
                    if isinstance(data, list):  # Handles formats like 'transcript_list' in some cases
                        lines = [it.get("text", "") for it in data if it.get("text", "")]
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


def get_subtitles_fallback(info: Dict[str, Any], primary_lang='vi', fallback_lang='en'):
    try:
        subs = info.get('subtitles', {}) or {}
        auto = info.get('automatic_captions', {}) or {}

        def get_sub_url(lang):
            if lang in subs:
                return subs[lang][0]['url']
            if lang in auto:
                return auto[lang][0]['url']
            return None

        # Thử phụ đề tiếng Việt trước
        url = get_sub_url(primary_lang) or get_sub_url(primary_lang + '-VN')
        if url:
            text = download_subtitle_content(url)
            if text:
                return clean_subtitles(text)

        # Nếu không có, thử fallback sang tiếng Anh
        url = get_sub_url(fallback_lang)
        if url:
            text = download_subtitle_content(url)
            if text:
                return clean_subtitles(text + "\n\n(Nguồn phụ đề: Tiếng Anh - fallback)")

        # Nếu vẫn không có gì
        return "Không tìm thấy phụ đề tiếng Việt (video không có phụ đề hoặc chưa được hỗ trợ)."

    except Exception as e:
        return f"Lỗi khi tải phụ đề: {e}"


def get_video_info_gui(url: str, log_func: Callable[[str, Optional[str]], None]):
    if not YTDLP_AVAILABLE:
        return {'url': url, 'status': 'error', 'error': 'yt-dlp is not available.'}
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extractaudio': False,
            'extract_flat': False,
            'sleep_interval': 20,  # Added for polite scraping
            'max_sleep_interval': 25,
            'retries': 5,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                'title': info.get('title', 'Không có tiêu đề'),
                'video_id': info.get('id', 'unknown'),
                'duration': info.get('duration', 0),
                'url': url,
                'subtitles': get_subtitles_fallback(info),
                'status': 'success'
            }
    except Exception as e:
        log_func(f"Lỗi khi lấy thông tin cho {url}: {e}", "red")
        return {'url': url, 'status': 'error', 'error': f'Lỗi khi lấy thông tin: {e}'}


def load_existing_index(results_path='youtube_results.json'):
    if not os.path.exists(results_path): return {}, []
    try:
        with open(results_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        idx, ordered = {}, []
        for item in data:
            vid = item.get('video_id') or extract_video_id(item.get('url', '')) or ''
            if vid and vid not in idx:
                idx[vid] = item;
                ordered.append(item)
        return idx, ordered
    except Exception:
        return {}, []


def save_results_merge_gui(new_results: List[Dict[str, Any]], log_func: Callable[[str, Optional[str]], None],
                           output_file='youtube_results.json'):
    existing_index, ordered = load_existing_index(output_file)
    appended = 0
    for item in new_results:
        vid = item.get('video_id') or extract_video_id(item.get('url', '')) or item.get('url')
        if not vid:  # If no video_id or URL, just append if unique (less ideal)
            if item not in ordered:  # Simple check for uniqueness
                ordered.append(item);
                appended += 1
            continue
        if vid in existing_index:
            continue
        existing_index[vid] = item;
        ordered.append(item);
        appended += 1
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(ordered, f, ensure_ascii=False, indent=2)
    log_func(f"✓ Gộp kết quả (thêm {appended}) vào youtube_results.json", "green")


def safe_title(result_title: str) -> str:
    t = re.sub(INVALID, "_", result_title or "Video").strip()
    return t[:80] if t else "Video"


def read_urls_from_file(file_path: str, log_func: Callable[[str, Optional[str]], None]) -> Optional[List[str]]:
    urls = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for ln, line in enumerate(f, 1):
                s = line.strip()
                if s and not s.startswith('#'):
                    if extract_video_id(s):
                        urls.append(s)
                    else:
                        log_func(f"Dòng {ln}: URL không hợp lệ - {s}", "yellow")
    except Exception as e:
        log_func(f"Lỗi đọc file: {e}", "red")
        return None
    return urls


# ====== GUI Class ======
class LCTCPipelineGUI:
    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue") # Keep 'blue' for default components not explicitly styled

        self.root = ctk.CTk()
        self.root.title("LCTC Pipeline")
        self.root.geometry("900x750")
        self.root.minsize(850, 650)

        # Updated colors for YouTube Red theme
        self.colors = {
            'bg': '#0a0e14',        # Dark background
            'card': '#151b24',      # Slightly lighter card/panel background
            'accent': '#FF0000',    # YouTube Red
            'accent_hover': '#CC0000', # Darker YouTube Red for hover
            'text': '#ffffff',      # White text
            'text_dim': '#7a8896',  # Dimmed text
            'success': '#00ff9f',   # Green for success
            'warning': '#ffa500',   # Orange for warning
            'error': '#ff4757',     # Existing error red (can be changed to #FF0000 if desired)
        }
        self.root.configure(fg_color=self.colors['bg'])

        # State variables
        self.urls_to_process: List[str] = []
        self.pipeline_running = False
        self.stop_pipeline_flag = False

        # Main container
        self.main_container = ctk.CTkFrame(self.root, fg_color=self.colors['bg'])
        self.main_container.pack(fill="both", expand=True, padx=20, pady=20)

        self._setup_ui()

    def _setup_ui(self):
        self.clear_screen()

        # Header
        header_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            header_frame,
            text="LCTC Pipeline (Folder Builder + YouTube Sub)",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=self.colors['accent']
        ).pack(pady=5)
        ctk.CTkLabel(
            header_frame,
            text="Build folders, extract YouTube subtitles, and organize.",
            font=ctk.CTkFont(size=12),
            text_color=self.colors['text_dim']
        ).pack(pady=(0, 15))

        # Main content area with two columns (left for inputs, right for log)
        content_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        content_frame.pack(fill="both", expand=True)
        content_frame.grid_columnconfigure(0, weight=1)  # Input panel
        content_frame.grid_columnconfigure(1, weight=1)  # Log panel
        content_frame.grid_rowconfigure(0, weight=1)

        # Left Panel: Inputs
        input_panel = ctk.CTkScrollableFrame(content_frame, fg_color=self.colors['card'], corner_radius=10)
        input_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=0)

        # URL Input Section
        self._add_input_section(input_panel, "Cấu hình URL")

        ctk.CTkLabel(input_panel, text="URL YouTube đơn:", text_color=self.colors['text']).pack(anchor="w", padx=15,
                                                                                                pady=(10, 0))
        url_input_frame = ctk.CTkFrame(input_panel, fg_color="transparent")
        url_input_frame.pack(fill="x", padx=15, pady=5)
        self.single_url_entry = ctk.CTkEntry(
            url_input_frame,
            placeholder_text="Nhập URL YouTube",
            fg_color=self.colors['bg'],
            border_color=self.colors['accent']
        )
        self.single_url_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.add_url_button = ctk.CTkButton(
            url_input_frame,
            text="Thêm URL",
            command=self._add_single_url,
            fg_color=self.colors['accent'],
            hover_color=self.colors['accent_hover'],
            width=80
        )
        self.add_url_button.pack(side="left")

        ctk.CTkLabel(input_panel, text="Hoặc tải lên file .txt với nhiều URL (mỗi dòng một URL):",
                     text_color=self.colors['text']).pack(anchor="w", padx=15, pady=(10, 0))
        self.browse_url_file_button = ctk.CTkButton(
            input_panel,
            text="Duyệt file .txt URL",
            command=self._browse_urls_file,
            fg_color=self.colors['card'],
            border_width=1,
            border_color=self.colors['accent'],
            hover_color=self.colors['accent_hover'],
            width=200
        )
        self.browse_url_file_button.pack(anchor="w", padx=15, pady=5)

        ctk.CTkLabel(input_panel, text="Các URL sẽ xử lý:", text_color=self.colors['text']).pack(anchor="w", padx=15,
                                                                                                 pady=(10, 0))
        self.url_list_textbox = ctk.CTkTextbox(
            input_panel,
            height=100,
            fg_color=self.colors['bg'],
            text_color=self.colors['text_dim'],
            wrap="word",
            state="disabled"
        )
        self.url_list_textbox.pack(fill="x", padx=15, pady=(0, 10))

        url_list_buttons_frame = ctk.CTkFrame(input_panel, fg_color="transparent")
        url_list_buttons_frame.pack(fill="x", padx=15, pady=(0, 10))
        self.clear_urls_button = ctk.CTkButton(
            url_list_buttons_frame,
            text="Xóa URL",
            command=self._clear_urls,
            fg_color=self.colors['error'],
            hover_color="#cc3a47",
            width=80
        )
        self.clear_urls_button.pack(side="left", padx=(0, 5))

        self.url_count_label = ctk.CTkLabel(
            url_list_buttons_frame,
            text="Tổng số URL: 0",
            text_color=self.colors['text_dim']
        )
        self.url_count_label.pack(side="right")

        # Naming & Numbering Section
        self._add_input_section(input_panel, "Đặt tên & Đánh số")

        ctk.CTkLabel(input_panel, text="Tiền tố (Prefix):", text_color=self.colors['text']).pack(anchor="w", padx=15,
                                                                                                 pady=(10, 0))
        self.prefix_entry = ctk.CTkEntry(
            input_panel,
            placeholder_text=DEFAULT_PREFIX,
            fg_color=self.colors['bg'],
            border_color=self.colors['accent']
        )
        self.prefix_entry.insert(0, DEFAULT_PREFIX)
        self.prefix_entry.pack(fill="x", padx=15, pady=(0, 10))
        self.prefix_entry.bind("<KeyRelease>", self._update_end_num_label)

        ctk.CTkLabel(input_panel, text="Số bắt đầu:", text_color=self.colors['text']).pack(anchor="w", padx=15,
                                                                                           pady=(10, 0))
        self.start_num_entry = ctk.CTkEntry(
            input_panel,
            placeholder_text="1",
            fg_color=self.colors['bg'],
            border_color=self.colors['accent']
        )
        self.start_num_entry.insert(0, "1")
        self.start_num_entry.pack(fill="x", padx=15, pady=(0, 10))
        self.start_num_entry.bind("<KeyRelease>", self._update_end_num_label)

        ctk.CTkLabel(input_panel, text="Chiều rộng đệm số (ví dụ 3 cho 001):", text_color=self.colors['text']).pack(
            anchor="w", padx=15, pady=(10, 0))
        self.pad_width_entry = ctk.CTkEntry(
            input_panel,
            placeholder_text="Tự động tính toán",
            fg_color=self.colors['bg'],
            border_color=self.colors['accent']
        )
        self.pad_width_entry.pack(fill="x", padx=15, pady=(0, 10))
        self.pad_width_entry.bind("<KeyRelease>", self._update_end_num_label)

        self.end_num_label = ctk.CTkLabel(
            input_panel,
            text="Số kết thúc: (tự động tính)",
            text_color=self.colors['text_dim'],
            font=ctk.CTkFont(size=11)
        )
        self.end_num_label.pack(anchor="w", padx=15, pady=(0, 10))

        # Destination Directory
        self._add_input_section(input_panel, "Thư mục đầu ra")

        ctk.CTkLabel(input_panel, text="Thư mục đích:", text_color=self.colors['text']).pack(anchor="w", padx=15,
                                                                                             pady=(10, 0))
        dir_input_frame = ctk.CTkFrame(input_panel, fg_color="transparent")
        dir_input_frame.pack(fill="x", padx=15, pady=5)
        self.dest_dir_entry = ctk.CTkEntry(
            dir_input_frame,
            placeholder_text="Chọn một thư mục",
            fg_color=self.colors['bg'],
            border_color=self.colors['accent']
        )
        self.dest_dir_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.browse_dest_dir_button = ctk.CTkButton(
            dir_input_frame,
            text="Duyệt",
            command=self._browse_destination_directory,
            fg_color=self.colors['card'],
            border_width=1,
            border_color=self.colors['accent'],
            hover_color=self.colors['accent_hover'],
            width=80
        )
        self.browse_dest_dir_button.pack(side="left")

        # Start Button
        self.start_button = ctk.CTkButton(
            input_panel,
            text="Bắt đầu Pipeline",
            command=self._start_pipeline_thread,
            height=40,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color=self.colors['accent'],
            hover_color=self.colors['accent_hover']
        )
        self.start_button.pack(fill="x", padx=15, pady=20)

        # Right Panel: Log and Progress
        log_panel = ctk.CTkFrame(content_frame, fg_color=self.colors['card'], corner_radius=10)
        log_panel.grid(row=0, column=1, sticky="nsew", padx=(10, 0), pady=0)
        log_panel.grid_rowconfigure(2, weight=1)  # Log textbox expands

        ctk.CTkLabel(log_panel, text="Tiến độ Pipeline", font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=self.colors['text']).pack(pady=(15, 10))

        self.current_task_label = ctk.CTkLabel(
            log_panel,
            text="Sẵn sàng.",
            text_color=self.colors['text_dim'],
            font=ctk.CTkFont(size=12)
        )
        self.current_task_label.pack(anchor="w", padx=15, pady=(0, 5))

        self.pipeline_progress_bar = ctk.CTkProgressBar(log_panel, height=20, progress_color=self.colors['accent'])
        self.pipeline_progress_bar.pack(fill="x", padx=15, pady=(0, 10))
        self.pipeline_progress_bar.set(0)

        ctk.CTkLabel(log_panel, text="Nhật ký chi tiết:", font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=self.colors['text']).pack(anchor="w", padx=15, pady=(10, 0))

        self.log_textbox = ctk.CTkTextbox(
            log_panel,
            fg_color=self.colors['bg'],
            text_color=self.colors['text_dim'],
            wrap="word",
            state="disabled",
            height=300  # Initial height
        )
        self.log_textbox.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        # Cancel button
        self.cancel_button = ctk.CTkButton(
            log_panel,
            text="Hủy Pipeline",
            command=self._cancel_pipeline,
            fg_color=self.colors['error'],
            hover_color="#cc3a47",
            state="disabled"
        )
        self.cancel_button.pack(fill="x", padx=15, pady=(0, 15))

        # --- MOVE THESE INITIAL UPDATE CALLS TO THE END ---
        self._update_url_list_display()  # This now safely calls _update_end_num_label
        # The call below is somewhat redundant if _update_url_list_display already calls it,
        # but ensures consistency for initial state.
        self._update_end_num_label()

    def _add_input_section(self, parent: ctk.CTkFrame, title: str):
        """Helper to create a visually separated input section"""
        section_frame = ctk.CTkFrame(parent, fg_color="transparent")
        section_frame.pack(fill="x", pady=(10, 5))
        ctk.CTkLabel(
            section_frame,
            text=title.upper(),
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=self.colors['text']
        ).pack(anchor="w", padx=10, pady=(0, 5))
        ctk.CTkFrame(section_frame, height=2, fg_color=self.colors['accent']).pack(fill="x", padx=10)  # Separator

    def clear_screen(self):
        """Clears all widgets in the main container for screen transitions."""
        for widget in self.main_container.winfo_children():
            widget.destroy()

    def gui_log_output(self, message: str, color_tag: Optional[str] = None):
        """Thread-safe logging to the GUI textbox."""
        self.root.after(0, lambda: self._append_log(message, color_tag))

    def _append_log(self, message: str, color: Optional[str] = None):
        """Appends a message to the log textbox."""
        self.log_textbox.configure(state="normal")
        if color == "red":
            self.log_textbox.insert("end", f"{message}\n", "red_tag")
            self.log_textbox.tag_config("red_tag", foreground=self.colors['error'])
        elif color == "yellow":
            self.log_textbox.insert("end", f"{message}\n", "yellow_tag")
            self.log_textbox.tag_config("yellow_tag", foreground=self.colors['warning'])
        elif color == "green":
            self.log_textbox.insert("end", f"{message}\n", "green_tag")
            self.log_textbox.tag_config("green_tag", foreground=self.colors['success'])
        elif color == "blue":  # Custom blue for general info/process start, now uses accent color
            self.log_textbox.insert("end", f"{message}\n", "blue_tag")
            self.log_textbox.tag_config("blue_tag", foreground=self.colors['accent'])
        else:
            self.log_textbox.insert("end", f"{message}\n")
        self.log_textbox.see("end")  # Scroll to bottom
        self.log_textbox.configure(state="disabled")

    def _update_url_list_display(self):
        """Updates the URL list textbox and count label."""
        self.url_list_textbox.configure(state="normal")
        self.url_list_textbox.delete("1.0", "end")
        for url in self.urls_to_process:
            self.url_list_textbox.insert("end", f"{url}\n")
        self.url_list_textbox.configure(state="disabled")
        self.url_count_label.configure(text=f"Tổng số URL: {len(self.urls_to_process)}")
        self._update_end_num_label()  # Recalculate end number based on URL count

    def _add_single_url(self):
        url = self.single_url_entry.get().strip()
        if url:
            if extract_video_id(url):
                if url not in self.urls_to_process:
                    self.urls_to_process.append(url)
                    self.single_url_entry.delete(0, "end")
                    self.gui_log_output(f"Đã thêm URL: {url}", "blue")
                    self._update_url_list_display()
                else:
                    messagebox.showinfo("URL trùng lặp", "URL này đã có trong danh sách.")
            else:
                messagebox.showerror("URL không hợp lệ", "Vui lòng nhập một URL YouTube hợp lệ.")
        else:
            messagebox.showwarning("URL trống", "Vui lòng nhập URL trước khi nhấp 'Thêm URL'.")

    def _browse_urls_file(self):
        file_path = filedialog.askopenfilename(
            parent=self.root,
            title="Chọn file .txt chứa danh sách URL YouTube",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialdir=os.path.expanduser("~")
        )
        if file_path:
            urls = read_urls_from_file(file_path, self.gui_log_output)
            if urls:
                new_urls_added = 0
                for url in urls:
                    if url not in self.urls_to_process:
                        self.urls_to_process.append(url)
                        new_urls_added += 1
                self.gui_log_output(
                    f"Đã tải {len(urls)} URL từ '{os.path.basename(file_path)}'. Đã thêm {new_urls_added} URL mới.",
                    "green")
                self.root.after(0, self._update_url_list_display)
            else:
                messagebox.showwarning("Không có URL hợp lệ",
                                       f"Không tìm thấy URL YouTube hợp lệ nào trong '{os.path.basename(file_path)}'.")

    def _clear_urls(self):
        if messagebox.askyesno("Xóa URL", "Bạn có chắc muốn xóa tất cả URL khỏi danh sách không?"):
            self.urls_to_process = []
            self.gui_log_output("Tất cả URL đã được xóa.", "yellow")
            self._update_url_list_display()

    def _browse_destination_directory(self):
        directory = filedialog.askdirectory(parent=self.root, title="Chọn thư mục đích",
                                            mustexist=True, initialdir=os.path.expanduser("~"))
        if directory:
            self.dest_dir_entry.delete(0, "end")
            self.dest_dir_entry.insert(0, directory)

    def _update_end_num_label(self, event=None):
        try:
            start_num = int(self.start_num_entry.get() or "1")
            num_urls = len(self.urls_to_process)
            end_num = start_num + num_urls - 1
            if num_urls == 0:
                self.end_num_label.configure(text="Số kết thúc: (0 URL được chọn)")
            else:
                prefix = self.prefix_entry.get().strip() or DEFAULT_PREFIX
                raw_pad_width = self.pad_width_entry.get().strip()

                # Calculate default padding if not provided or invalid
                try:
                    pad_width_input = int(raw_pad_width) if raw_pad_width else 0
                except ValueError:
                    pad_width_input = 0  # Fallback for invalid input

                calculated_pad_width = pad_width_input
                if pad_width_input <= 0:  # If padding is 0 or negative, calculate based on max number
                    calculated_pad_width = max(1, len(str(end_num)))

                self.end_num_label.configure(text=f"Số kết thúc: {make_name(prefix, end_num, calculated_pad_width)}")
        except ValueError:
            self.end_num_label.configure(text="Số kết thúc: Số bắt đầu không hợp lệ")
        except Exception as e:
            self.end_num_label.configure(text=f"Số kết thúc: Lỗi - {e}")

    def _start_pipeline_thread(self):
        if self.pipeline_running:
            messagebox.showwarning("Pipeline đang chạy", "Một pipeline khác đang được tiến hành.")
            return

        prefix = self.prefix_entry.get().strip() or DEFAULT_PREFIX
        try:
            start_num = int(self.start_num_entry.get())
        except ValueError:
            messagebox.showerror("Dữ liệu không hợp lệ", "Số bắt đầu phải là một số nguyên.")
            return

        raw_pad_width = self.pad_width_entry.get().strip()
        try:
            pad_width = int(raw_pad_width) if raw_pad_width else 0
            if pad_width <= 0:  # If padding is 0 or negative, calculate based on max number
                pad_width = max(1, len(str(start_num + len(self.urls_to_process) - 1)))
        except ValueError:
            pad_width = max(1, len(str(start_num + len(self.urls_to_process) - 1)))  # Default if invalid

        dest_dir = self.dest_dir_entry.get().strip()
        if not os.path.isdir(dest_dir):
            messagebox.showerror("Thư mục không hợp lệ", "Vui lòng chọn một thư mục đích hợp lệ.")
            return

        if not self.urls_to_process:
            messagebox.showwarning("Không có URL", "Vui lòng thêm ít nhất một URL YouTube để xử lý.")
            return

        if not YTDLP_AVAILABLE:
            if not messagebox.askyesno("yt-dlp bị thiếu",
                                       "yt-dlp chưa được cài đặt/không có sẵn. Quá trình trích xuất phụ đề YouTube sẽ bị bỏ qua. Bạn có muốn tiếp tục không?"):
                return
            self.gui_log_output("yt-dlp không có sẵn. Quá trình trích xuất phụ đề YouTube sẽ bị bỏ qua.", "yellow")

        # Disable inputs and enable cancel button
        self._toggle_ui_state(False)
        self.stop_pipeline_flag = False
        self.pipeline_running = True
        self.gui_log_output("Pipeline đã bắt đầu!", "blue")

        threading.Thread(target=self._run_pipeline, args=(prefix, start_num, pad_width, dest_dir), daemon=True).start()

    def _toggle_ui_state(self, enable: bool):
        """Enable/disable input widgets and buttons."""
        state = "normal" if enable else "disabled"
        self.single_url_entry.configure(state=state)
        self.prefix_entry.configure(state=state)
        self.start_num_entry.configure(state=state)
        self.pad_width_entry.configure(state=state)
        self.dest_dir_entry.configure(state=state)
        self.start_button.configure(state=state)
        self.add_url_button.configure(state=state)
        self.browse_url_file_button.configure(state=state)
        self.clear_urls_button.configure(state=state)
        self.browse_dest_dir_button.configure(state=state)

        # Special case for url_list_textbox, it's always disabled for direct input, but needs to be updated.
        # Its state is controlled by _update_url_list_display.

        # Cancel button is special: enabled when running, disabled otherwise
        self.cancel_button.configure(state="normal" if not enable else "disabled")
        if not enable:
            self.cancel_button.configure(text="Đang dừng...")  # Change text while stopping

    def _cancel_pipeline(self):
        if messagebox.askyesno("Hủy Pipeline", "Bạn có chắc muốn dừng pipeline hiện tại không?"):
            self.stop_pipeline_flag = True
            self.gui_log_output("Yêu cầu hủy Pipeline. Đang chờ bước hiện tại hoàn thành...", "yellow")
            self.cancel_button.configure(state="disabled", text="Đang dừng...")  # Prevent multiple clicks

    def _update_progress_gui(self, current: int, total: int, description: str):
        """Updates GUI progress bar and label from background thread."""
        self.root.after(0, lambda: self.current_task_label.configure(text=description))
        if total > 0:
            self.root.after(0, lambda: self.pipeline_progress_bar.set(current / total))
        else:
            self.root.after(0, lambda: self.pipeline_progress_bar.set(0))  # Or a neutral state
        self.root.update_idletasks()  # Ensure UI updates immediately, might be heavy for many small updates

    def _run_pipeline(self, prefix: str, start_num: int, pad_width: int, dest_dir: str):
        try:
            # Step 1: Create folders
            self.gui_log_output(
                f"\n--- Bước 1: Tạo cấu trúc thư mục ({prefix}-{make_name(prefix, start_num, pad_width)} đến {prefix}-{make_name(prefix, start_num + len(self.urls_to_process) - 1, pad_width)}) ---",
                "blue")
            self._update_progress_gui(0, len(self.urls_to_process),
                                      f"Đang tạo thư mục {prefix}-{make_name(prefix, start_num, pad_width)}...")

            if not DOCX_AVAILABLE:
                self.gui_log_output("python-docx không có sẵn. Việc tạo file .docx sẽ chỉ tạo file trống.", "yellow")
            ensure_template_gui(self.gui_log_output)

            total_folders = len(self.urls_to_process)
            created_folders = 0
            skipped_folders = 0

            for i, _ in enumerate(self.urls_to_process):
                if self.stop_pipeline_flag:
                    self.gui_log_output("Pipeline bị hủy trong quá trình tạo thư mục.", "red")
                    return

                n = start_num + i
                name = make_name(prefix, n, pad_width)
                safe_name = sanitize(name)
                base_path = os.path.join(dest_dir, safe_name)

                if not os.path.exists(base_path):
                    os.makedirs(base_path, exist_ok=True)
                    created_folders += 1
                    self.gui_log_output(f"Đã tạo thư mục: {base_path}", "green")
                else:
                    skipped_folders += 1
                    self.gui_log_output(f"Thư mục đã tồn tại: {base_path}", "yellow")

                for sf in SUBFOLDERS:
                    os.makedirs(os.path.join(base_path, sf), exist_ok=True)

                main_doc = os.path.join(base_path, f"{safe_name}.docx")
                desc_doc = os.path.join(base_path, "MO TA.docx")
                if not os.path.exists(main_doc): new_blank_docx_gui(main_doc)
                if not os.path.exists(desc_doc): new_blank_docx_gui(desc_doc)

                self.root.after(0, self._update_progress_gui, i + 1, total_folders,
                                f"Đang tạo thư mục {i + 1}/{total_folders}: {base_path}")

            self.gui_log_output(
                f"✓ Hoàn tất tạo folder (tổng {total_folders}, mới {created_folders}, tồn tại {skipped_folders}).",
                "green")

            # Step 2: Extract YouTube subtitles & info
            self.gui_log_output("\n--- Bước 2: Trích xuất thông tin và phụ đề YouTube ---", "blue")
            results: List[Dict[str, Any]] = []
            total_urls = len(self.urls_to_process)
            for i, url in enumerate(self.urls_to_process):
                if self.stop_pipeline_flag:
                    self.gui_log_output("Pipeline bị hủy trong quá trình trích xuất YouTube.", "red")
                    return

                self.root.after(0, self._update_progress_gui, i, total_urls,
                                f"Đang xử lý video {i + 1}/{total_urls}: {url}")
                self.gui_log_output(f"Đang xử lý URL: {url}")

                vid = extract_video_id(url)
                existing_index, _ = load_existing_index('youtube_results.json')

                if vid and vid in existing_index:
                    r = existing_index[vid]
                    r.setdefault('url', url)
                    r.setdefault('status', 'success')
                    results.append(r)
                    self.gui_log_output(f"↷ Dùng lại kết quả đã có cho: {url}", "blue")
                else:
                    r = get_video_info_gui(url, self.gui_log_output)
                    results.append(r)
                    self.gui_log_output(f"{'✓ OK' if r.get('status') == 'success' else '✗ Lỗi'} - {url}",
                                        "green" if r.get('status') == 'success' else "red")

                if i < total_urls - 1 and not self.stop_pipeline_flag:
                    wait_time = random.randint(20, 25)
                    self.gui_log_output(f"⏳ Đợi {wait_time} giây trước khi xử lý video tiếp theo.", "yellow")
                    time.sleep(wait_time)

            self.root.after(0, self._update_progress_gui, total_urls, total_urls, "Hoàn tất xử lý YouTube.")
            save_results_merge_gui(results, self.gui_log_output)
            self.gui_log_output("✓ Hoàn tất trích xuất thông tin và phụ đề.", "green")

            # Step 3: Assign results to LCTC folders
            self.gui_log_output("\n--- Bước 3: Gán kết quả vào thư mục LCTC ---", "blue")
            assigned_count = 0
            for idx, r in enumerate(results):
                if self.stop_pipeline_flag:
                    self.gui_log_output("Pipeline bị hủy trong quá trình gán kết quả.", "red")
                    return

                n = start_num + idx
                lctc_dir = os.path.join(dest_dir, make_name(prefix, n, pad_width))

                if not os.path.isdir(lctc_dir):
                    self.gui_log_output(f"⚠ Thiếu folder {lctc_dir} (bỏ qua gán cho video này).", "yellow")
                    continue

                target_base = lctc_dir

                if r.get('status') != 'success':
                    # Ensure folder name for errors is safe and unique
                    error_id = r.get('video_id', 'unknown_id') if r.get('video_id') else extract_video_id(
                        r.get('url', '')) or 'unknown_url'
                    folder_name_error = f"ERR_{idx + 1:02d}_{error_id}"
                    folder = os.path.join(target_base, sanitize(folder_name_error))
                    os.makedirs(folder, exist_ok=True)
                    with open(os.path.join(folder, 'info.txt'), 'w', encoding='utf-8') as f:
                        f.write(f"URL: {r.get('url')}\n")
                        f.write(f"Status: {r.get('status')}\n")
                        f.write(f"Error: {r.get('error', '')}\n")
                    self.gui_log_output(f"↷ Ghi chú lỗi vào {folder}", "yellow")
                    continue

                title = r.get('title', 'Video')
                vid = r.get('video_id', 'unknown')
                sub = r.get('subtitles') or "Không có phụ đề"
                safe = safe_title(title)

                folder = os.path.join(target_base, f"{safe}_{vid}")
                os.makedirs(folder, exist_ok=True)

                sub_path = os.path.join(folder, 'sub.txt')
                info_path = os.path.join(folder, 'info.txt')

                if os.path.exists(sub_path) and os.path.exists(info_path):
                    self.gui_log_output(f"↷ Bỏ qua (đã tồn tại): {folder}", "blue")
                else:
                    with open(sub_path, 'w', encoding='utf-8') as f:
                        f.write(sub)
                    with open(info_path, 'w', encoding='utf-8') as f:
                        f.write(f"Title: {title}\nVideo ID: {vid}\nURL: {r.get('url')}\n")
                        f.write(f"Duration: {r.get('duration', 'N/A')} seconds\n")
                        f.write(f"MappedTo: {make_name(prefix, n, pad_width)}\n")
                    assigned_count += 1
                    self.gui_log_output(f"✓ Lưu vào: {folder}", "green")

                self.root.after(0, self._update_progress_gui, idx + 1, len(results),
                                f"Đang gán kết quả {idx + 1}/{len(results)}")

            self.gui_log_output(f"→ Đã gán {assigned_count}/{len(results)} video vào {prefix}-*.", "green")

            messagebox.showinfo("Pipeline Hoàn thành", "LCTC Pipeline đã hoàn thành thành công!")

        except Exception as e:
            error_msg = f"Đã xảy ra lỗi nghiêm trọng: {e}"
            self.gui_log_output(error_msg, "red")
            messagebox.showerror("Lỗi Pipeline", error_msg)
        finally:
            self.root.after(0, lambda: self.current_task_label.configure(text="Sẵn sàng."))
            self.root.after(0, lambda: self.pipeline_progress_bar.set(0))
            self.pipeline_running = False
            self.stop_pipeline_flag = False
            self.root.after(0, lambda: self._toggle_ui_state(True))
            self.root.after(0, lambda: self.cancel_button.configure(text="Hủy Pipeline"))

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = LCTCPipelineGUI()
    app.run()