#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import json
import re
import subprocess


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
║                YouTube Video Info Extractor                  ║
║                           BOCCHI89                           ║
╚══════════════════════════════════════════════════════════════╝
{Colors.ENDC}
"""
    print(banner)


def progress_bar(current, total, description="Processing", width=50):
    percent = (current / total) * 100 if total else 100.0
    filled = int(width * current // total) if total else width
    bar = '█' * filled + '░' * (width - filled)
    print(f"\r{Colors.OKBLUE}[{bar}] {percent:6.1f}% | {current}/{total} | {description}{Colors.ENDC}", end='',
          flush=True)


def extract_video_id(url):
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com\/v\/([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def check_dependencies():
    print(f"{Colors.OKCYAN}Đang kiểm tra dependencies...{Colors.ENDC}")
    try:
        import yt_dlp  # noqa: F401
        print(f"{Colors.OKGREEN}✓ yt-dlp đã được cài đặt{Colors.ENDC}")
        return True
    except ImportError:
        print(f"{Colors.WARNING}yt-dlp chưa được cài đặt{Colors.ENDC}")
        print(f"{Colors.OKBLUE}Đang cài đặt yt-dlp...{Colors.ENDC}")
        try:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'yt-dlp'])
            print(f"{Colors.OKGREEN}✓ Đã cài đặt yt-dlp{Colors.ENDC}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"{Colors.FAIL}✗ Không thể cài đặt yt-dlp: {e}{Colors.ENDC}")
            return False


def read_urls_from_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            urls = []
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line and not line.startswith('#'):
                    if extract_video_id(line):
                        urls.append(line)
                    else:
                        print(f"{Colors.WARNING}Dòng {line_num}: URL không hợp lệ - {line}{Colors.ENDC}")
            return urls
    except FileNotFoundError:
        print(f"{Colors.FAIL}Không tìm thấy file: {file_path}{Colors.ENDC}")
        return None
    except Exception as e:
        print(f"{Colors.FAIL}Lỗi đọc file: {e}{Colors.ENDC}")
        return None


def download_subtitle_content(url):
    try:
        import urllib.request
        import json as _json

        with urllib.request.urlopen(url) as response:
            raw = response.read().decode('utf-8')

            # Nếu là JSON
            if raw.strip().startswith('{') or raw.strip().startswith('['):
                try:
                    data = _json.loads(raw)

                    if isinstance(data, dict) and "events" in data:
                        # Định dạng json3
                        lines = []
                        for ev in data["events"]:
                            if "segs" in ev:
                                line = ''.join(seg.get("utf8", "") for seg in ev["segs"]).strip()
                                if line:
                                    lines.append(line)
                        return "\n".join(lines)

                    elif isinstance(data, list):
                        # youtube_transcript_api format
                        lines = [item.get("text", "") for item in data if item.get("text", "")]
                        return "\n".join(lines)

                    else:
                        return raw  # fallback nếu định dạng không nhận diện được

                except Exception:
                    return raw  # fallback nếu lỗi parse JSON

            else:
                return raw  # fallback nếu không phải JSON

    except Exception:
        return ""


def clean_subtitles(subtitle_content):
    if not subtitle_content:
        return "Không có nội dung phụ đề"

    lines = subtitle_content.split('\n')
    cleaned_lines = []

    for line in lines:
        line = line.strip()
        if (not re.match(r'^\d+$', line) and
                not re.match(r'^\d{2}:\d{2}:\d{2}', line) and
                not re.match(r'^WEBVTT', line) and
                not re.match(r'^NOTE', line) and
                line and line != '--'):

            line = re.sub(r'<[^>]+>', '', line)
            line = re.sub(r'&[a-zA-Z]+;', '', line)

            if line.strip() and line.strip() not in cleaned_lines:
                cleaned_lines.append(line.strip())

    result = '\n'.join(cleaned_lines)
    return result if result else "Không thể trích xuất nội dung phụ đề"


def get_vietnamese_subtitles_direct(info, ydl):
    try:
        subtitles = info.get('subtitles', {})
        automatic_captions = info.get('automatic_captions', {})

        subtitle_text = ""

        if 'vi' in subtitles:
            subtitle_url = subtitles['vi'][0]['url']
            subtitle_text = download_subtitle_content(subtitle_url)
        elif 'vi' in automatic_captions:
            subtitle_url = automatic_captions['vi'][0]['url']
            subtitle_text = download_subtitle_content(subtitle_url)
        elif 'vi-VN' in automatic_captions:
            subtitle_url = automatic_captions['vi-VN'][0]['url']
            subtitle_text = download_subtitle_content(subtitle_url)

        if subtitle_text:
            return clean_subtitles(subtitle_text)
        else:
            return "Không có phụ đề tiếng Việt"

    except Exception as e:
        return f"Lỗi khi tải phụ đề: {str(e)}"


def get_video_info(url):
    try:
        import yt_dlp

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extractaudio': False,
            'extract_flat': False,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            title = info.get('title', 'Không có tiêu đề')
            video_id = info.get('id', 'unknown')
            duration = info.get('duration', 0)

            subtitles = get_vietnamese_subtitles_direct(info, ydl)

            return {
                'title': title,
                'video_id': video_id,
                'duration': duration,
                'url': url,
                'subtitles': subtitles,
                'status': 'success'
            }

    except Exception as e:
        return {
            'url': url,
            'status': 'error',
            'error': f'Lỗi khi lấy thông tin: {str(e)}'
        }


# ====== MỚI: Tải/Gộp kết quả cũ, tạo index theo video_id ======
def load_existing_index(results_path='youtube_results.json'):
    """
    Trả về (index, ordered_list). index: dict[video_id] -> item
    """
    if not os.path.exists(results_path):
        return {}, []
    try:
        with open(results_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        index = {}
        ordered = []
        for item in data:
            vid = item.get('video_id') or extract_video_id(item.get('url', '')) or ''
            if vid and vid not in index:
                index[vid] = item
                ordered.append(item)
        return index, ordered
    except Exception as e:
        print(f"{Colors.WARNING}Không đọc được {results_path}: {e}{Colors.ENDC}")
        return {}, []


def safe_title_from_result(result):
    title = result.get('title', 'Video')
    safe_title = re.sub(r'[<>:"/\\|?*]', '_', title).strip()
    return safe_title[:80] if safe_title else 'Video'


# ====== SỬA: Không ghi đè phụ đề/info nếu đã tồn tại ======
def save_subtitles_to_files(results, overwrite=False):
    base_dir = "subtitles"
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)

    saved_count = 0

    for i, result in enumerate(results, 1):
        if result.get('status') != 'success':
            continue

        subtitles_content = result.get('subtitles') or ""
        if subtitles_content in [
            "Không có phụ đề tiếng Việt",
            "Không thể tải phụ đề",
            "Không có nội dung phụ đề",
            "Không thể trích xuất nội dung phụ đề",
            ""
        ]:
            continue

        video_title = result.get('title', f'Video_{i}')
        video_id = result.get('video_id', f'unknown_{i}')
        safe_title = safe_title_from_result(result)

        folder_path = os.path.join(base_dir, safe_title)
        os.makedirs(folder_path, exist_ok=True)

        sub_path = os.path.join(folder_path, 'sub.txt')
        info_path = os.path.join(folder_path, 'info.txt')

        # Nếu không overwrite: bỏ qua khi file đã có
        if not overwrite and os.path.exists(sub_path) and os.path.exists(info_path):
            print(f"{Colors.OKCYAN}↷ Bỏ qua lưu (đã tồn tại): {safe_title}/sub.txt & info.txt{Colors.ENDC}")
            continue

        with open(sub_path, 'w', encoding='utf-8') as fsub:
            fsub.write(subtitles_content)

        with open(info_path, 'w', encoding='utf-8') as finfo:
            finfo.write(f"Title: {video_title}\n")
            finfo.write(f"Video ID: {video_id}\n")
            finfo.write(f"URL: {result.get('url')}\n")
            finfo.write(f"Duration: {result.get('duration', 'N/A')} seconds\n")

        saved_count += 1
        print(f"{Colors.OKGREEN}✓ Saved: {safe_title}/sub.txt & info.txt{Colors.ENDC}")

    if saved_count > 0:
        print(f"\n{Colors.OKGREEN}✓ Saved {saved_count} video(s) into folder 'subtitles'{Colors.ENDC}")
    else:
        print(f"\n{Colors.WARNING}⚠ No subtitle file was saved/updated{Colors.ENDC}")


# ====== SỬA: Gộp (merge) kết quả thay vì ghi đè ======
def save_results_merge(new_results, output_file='youtube_results.json'):
    """
    Hợp nhất kết quả mới vào file cũ theo video_id (ưu tiên dữ liệu cũ).
    """
    existing_index, ordered = load_existing_index(output_file)

    # thêm các item mới (nếu chưa có video_id)
    appended = 0
    for item in new_results:
        if item.get('status') != 'success':
            # vẫn có thể muốn lưu lỗi mới để tra cứu — thêm nếu url chưa có trong lỗi cũ
            vid = extract_video_id(item.get('url', '')) or item.get('video_id', '')
            key = vid or item.get('url', '')
            if key and key not in existing_index:
                existing_index[key] = item
                ordered.append(item)
                appended += 1
            continue

        vid = item.get('video_id') or extract_video_id(item.get('url', ''))
        if not vid:
            # nếu vì lý do gì đó không có id, thêm thẳng
            ordered.append(item)
            appended += 1
            continue

        if vid in existing_index:
            # ĐÃ CÓ -> giữ bản cũ (tránh ghi đè)
            continue
        else:
            existing_index[vid] = item
            ordered.append(item)
            appended += 1

    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(ordered, f, ensure_ascii=False, indent=2)
        print(f"{Colors.OKGREEN}✓ Đã gộp kết quả (thêm {appended} mục) vào {output_file}{Colors.ENDC}")

        # Lưu phụ đề cho các mục MỚI vừa thêm (không overwrite)
        save_subtitles_to_files([r for r in new_results if r.get('status') == 'success'], overwrite=False)
        return True
    except Exception as e:
        print(f"{Colors.FAIL}✗ Lỗi lưu file: {e}{Colors.ENDC}")
        return False


def display_menu():
    print(f"""
{Colors.BOLD}Chọn một tùy chọn:{Colors.ENDC}
{Colors.OKGREEN}1.{Colors.ENDC} Chọn file chứa danh sách URL
{Colors.OKGREEN}2.{Colors.ENDC} Nhập URL trực tiếp
{Colors.OKGREEN}3.{Colors.ENDC} Xem kết quả trước đó
{Colors.OKGREEN}4.{Colors.ENDC} Xuất tất cả phụ đề thành file txt
{Colors.OKGREEN}5.{Colors.ENDC} Thoát

{Colors.OKCYAN}Nhập lựa chọn (1-5): {Colors.ENDC}""", end="")


def select_file():
    print(f"\n{Colors.BOLD}Chọn file chứa danh sách URL YouTube:{Colors.ENDC}")

    txt_files = [f for f in os.listdir('.') if f.endswith('.txt')]

    if not txt_files:
        print(f"{Colors.WARNING}Không tìm thấy file .txt nào trong thư mục hiện tại{Colors.ENDC}")
        file_path = input(f"{Colors.OKCYAN}Nhập đường dẫn file: {Colors.ENDC}")
        return file_path if os.path.exists(file_path) else None

    print(f"\n{Colors.BOLD}Các file .txt có sẵn:{Colors.ENDC}")
    for i, file in enumerate(txt_files, 1):
        print(f"{Colors.OKGREEN}{i}.{Colors.ENDC} {file}")

    print(f"{Colors.OKGREEN}{len(txt_files) + 1}.{Colors.ENDC} Nhập đường dẫn khác")

    try:
        choice = int(input(f"\n{Colors.OKCYAN}Chọn file (1-{len(txt_files) + 1}): {Colors.ENDC}"))

        if 1 <= choice <= len(txt_files):
            return txt_files[choice - 1]
        elif choice == len(txt_files) + 1:
            file_path = input(f"{Colors.OKCYAN}Nhập đường dẫn file: {Colors.ENDC}")
            return file_path if os.path.exists(file_path) else None
        else:
            print(f"{Colors.FAIL}Lựa chọn không hợp lệ{Colors.ENDC}")
            return None

    except ValueError:
        print(f"{Colors.FAIL}Vui lòng nhập số{Colors.ENDC}")
        return None


# ====== SỬA: Bỏ qua URL đã xử lý dựa trên video_id ======
def process_urls(urls, existing_ids=None):
    results = []
    existing_ids = set(existing_ids or [])
    total = len(urls)

    print(f"\n{Colors.BOLD}Bắt đầu xử lý {total} video(s)...{Colors.ENDC}\n")

    skipped = 0
    processed = 0

    for i, url in enumerate(urls):
        progress_bar(i, total, f"Đang xử lý video {i + 1}")

        vid = extract_video_id(url)
        if vid and vid in existing_ids:
            print(f"\n{Colors.OKCYAN}↷ Bỏ qua (đã xử lý):{Colors.ENDC} {url}")
            skipped += 1
            time.sleep(0.1)
            continue

        result = get_video_info(url)
        results.append(result)

        if result.get('status') == 'success':
            existing_ids.add(result.get('video_id', ''))
            processed += 1

        print(f"\n{Colors.OKBLUE}Video {i + 1}/{total}:{Colors.ENDC}")
        if result['status'] == 'success':
            print(f"  {Colors.OKGREEN}✓{Colors.ENDC} {result['title']}")
        else:
            print(f"  {Colors.FAIL}✗{Colors.ENDC} {result.get('error', 'Unknown error')}")

        time.sleep(0.2)

    progress_bar(total, total, "Hoàn thành")
    print(f"\n\n{Colors.OKGREEN}✓ Đã xử lý xong!{Colors.ENDC} "
          f"(mới: {processed}, bỏ qua: {skipped}, tổng URL: {total})")

    return results


def display_results(results):
    print(f"\n{Colors.BOLD}KẾT QUẢ CHI TIẾT:{Colors.ENDC}")
    print("=" * 80)

    success_count = 0
    for i, result in enumerate(results, 1):
        print(f"\n{Colors.BOLD}Video {i}:{Colors.ENDC}")

        if result['status'] == 'success':
            success_count += 1
            print(f"  {Colors.OKGREEN}Tiêu đề:{Colors.ENDC} {result['title']}")
            print(f"  {Colors.OKGREEN}Video ID:{Colors.ENDC} {result['video_id']}")
            print(f"  {Colors.OKGREEN}Thời lượng:{Colors.ENDC} {result['duration']} giây")
            print(f"  {Colors.OKGREEN}URL:{Colors.ENDC} {result['url']}")
            print(f"  {Colors.OKGREEN}Phụ đề tiếng Việt:{Colors.ENDC}")

            subtitle_lines = result['subtitles'].split('\n')[:3]
            for line in subtitle_lines:
                if line.strip():
                    print(f"    {line}")
            if len(result['subtitles'].split('\n')) > 3:
                print(f"    {Colors.OKCYAN}[...và còn nữa]{Colors.ENDC}")
        else:
            print(f"  {Colors.FAIL}Lỗi:{Colors.ENDC} {result.get('error')}")
            print(f"  {Colors.FAIL}URL:{Colors.ENDC} {result.get('url')}")

        print("-" * 80)

    print(f"\n{Colors.BOLD}TỔNG KẾT:{Colors.ENDC}")
    print(f"  {Colors.OKGREEN}Thành công:{Colors.ENDC} {success_count}/{len(results)}")
    print(f"  {Colors.FAIL}Thất bại:{Colors.ENDC} {len(results) - success_count}/{len(results)}")


def main():
    while True:
        clear_screen()
        print_banner()

        if not check_dependencies():
            print(f"\n{Colors.FAIL}Không thể tiếp tục do thiếu dependencies{Colors.ENDC}")
            input(f"{Colors.OKCYAN}Nhấn Enter để thoát...{Colors.ENDC}")
            return

        display_menu()

        try:
            choice = input().strip()

            if choice == '1':
                clear_screen()
                print_banner()

                file_path = select_file()
                if not file_path:
                    input(f"\n{Colors.FAIL}Không thể chọn file. Nhấn Enter để quay lại...{Colors.ENDC}")
                    continue

                urls = read_urls_from_file(file_path)
                if not urls:
                    input(f"\n{Colors.FAIL}Không có URL hợp lệ nào. Nhấn Enter để quay lại...{Colors.ENDC}")
                    continue

                # Tải index hiện có để bỏ qua link cũ
                existing_index, _ordered = load_existing_index('youtube_results.json')
                existing_ids = set(k for k in existing_index.keys() if len(k) == 11)

                print(f"\n{Colors.OKGREEN}Đã tìm thấy {len(urls)} URL hợp lệ{Colors.ENDC}")
                print(f"{Colors.OKCYAN}Trong đó {len(existing_ids)} video có thể đã được xử lý trước đây.{Colors.ENDC}")
                confirm = input(f"{Colors.OKCYAN}Tiếp tục xử lý các video MỚI? (y/N): {Colors.ENDC}")

                if confirm.lower() in ['y', 'yes']:
                    results = process_urls(urls, existing_ids=existing_ids)
                    save_results_merge(results)
                    display_results(results)

                    input(f"\n{Colors.OKCYAN}Nhấn Enter để quay lại menu...{Colors.ENDC}")

            elif choice == '2':
                clear_screen()
                print_banner()

                url = input(f"{Colors.OKCYAN}Nhập URL YouTube: {Colors.ENDC}").strip()
                vid = extract_video_id(url)

                if not vid:
                    input(f"\n{Colors.FAIL}URL không hợp lệ. Nhấn Enter để quay lại...{Colors.ENDC}")
                    continue

                # Kiểm tra tồn tại trước khi xử lý
                existing_index, _ordered = load_existing_index('youtube_results.json')
                if vid in existing_index:
                    print(f"\n{Colors.OKCYAN}↷ Bỏ qua (đã xử lý):{Colors.ENDC} {url}")
                    # vẫn cho xem lại mục đã có
                    display_results([existing_index[vid]])
                    input(f"\n{Colors.OKCYAN}Nhấn Enter để quay lại menu...{Colors.ENDC}")
                    continue

                print(f"\n{Colors.OKBLUE}Đang xử lý video...{Colors.ENDC}")
                result = get_video_info(url)

                results = [result]
                save_results_merge(results)
                display_results(results)

                input(f"\n{Colors.OKCYAN}Nhấn Enter để quay lại menu...{Colors.ENDC}")

            elif choice == '3':
                clear_screen()
                print_banner()

                if os.path.exists('youtube_results.json'):
                    try:
                        with open('youtube_results.json', 'r', encoding='utf-8') as f:
                            results = json.load(f)
                        display_results(results)
                    except Exception as e:
                        print(f"{Colors.FAIL}Lỗi đọc file kết quả: {e}{Colors.ENDC}")
                else:
                    print(f"{Colors.WARNING}Chưa có kết quả nào được lưu{Colors.ENDC}")

                input(f"\n{Colors.OKCYAN}Nhấn Enter để quay lại menu...{Colors.ENDC}")

            elif choice == '4':
                clear_screen()
                print_banner()

                if os.path.exists('youtube_results.json'):
                    try:
                        with open('youtube_results.json', 'r', encoding='utf-8') as f:
                            results = json.load(f)

                        print(f"{Colors.OKBLUE}Đang xuất phụ đề thành file txt...{Colors.ENDC}")
                        # Vẫn tôn trọng overwrite=False để không ghi đè
                        save_subtitles_to_files(results, overwrite=False)

                    except Exception as e:
                        print(f"{Colors.FAIL}Lỗi đọc file kết quả: {e}{Colors.ENDC}")
                else:
                    print(f"{Colors.WARNING}Chưa có kết quả nào được lưu{Colors.ENDC}")

                input(f"\n{Colors.OKCYAN}Nhấn Enter để quay lại menu...{Colors.ENDC}")

            elif choice == '5':
                print(f"\n{Colors.OKGREEN}Cảm ơn bạn đã sử dụng!{Colors.ENDC}")
                break

            else:
                input(f"\n{Colors.FAIL}Lựa chọn không hợp lệ. Nhấn Enter để thử lại...{Colors.ENDC}")

        except KeyboardInterrupt:
            print(f"\n\n{Colors.WARNING}Đã hủy bởi người dùng{Colors.ENDC}")
            break
        except Exception as e:
            print(f"\n{Colors.FAIL}Lỗi: {e}{Colors.ENDC}")
            input(f"{Colors.OKCYAN}Nhấn Enter để tiếp tục...{Colors.ENDC}")


if __name__ == "__main__":
    main()
