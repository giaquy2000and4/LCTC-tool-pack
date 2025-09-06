import os, re, sys, shutil, tkinter as tk
from tkinter import filedialog
from docx import Document   # chỉ để tạo file tạm lần đầu
import pythoncom
import win32com.client as win32   # cần pywin32

INVALID = r'[<>:"/\\|?*]'
SUBFOLDERS = ["TAI NGUYEN", "THUMB"]
TEMPLATE = "template.docx"

def sanitize(name: str) -> str:
    return re.sub(INVALID, "-", name).strip().rstrip(".")

def create_template_with_word(path: str):
    """Tạo template.docx chuẩn bằng MS Word (không Compatibility Mode)."""
    # Tạo file tạm bằng python-docx
    temp_path = path + ".tmp"
    doc = Document()
    doc.add_paragraph(" ")   # thêm đoạn trống
    doc.save(temp_path)

    # Dùng Word COM để SaveAs sang chuẩn mới
    pythoncom.CoInitialize()
    word = win32.gencache.EnsureDispatch("Word.Application")
    word.Visible = False
    docx = word.Documents.Open(os.path.abspath(temp_path))
    docx.SaveAs(os.path.abspath(path), FileFormat=16)  # 16 = wdFormatXMLDocument (docx chuẩn)
    docx.Close(False)
    word.Quit()
    os.remove(temp_path)

def ensure_template():
    """Đảm bảo có file template.docx chuẩn."""
    if not os.path.exists(TEMPLATE):
        print(f"⚠ Không tìm thấy {TEMPLATE}, đang tạo file mẫu chuẩn bằng Word...")
        create_template_with_word(TEMPLATE)
        print(f"✔ Đã tạo {TEMPLATE} hoàn toàn chuẩn (không Compatibility Mode).")

def new_blank_docx(path: str):
    """Copy file template để tạo docx chuẩn"""
    shutil.copyfile(TEMPLATE, path)

def choose_directory_topmost(title: str) -> str:
    """Mở hộp thoại chọn thư mục ở chế độ luôn-trên-cùng"""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    dest = filedialog.askdirectory(parent=root, title=title,
                                   mustexist=True,
                                   initialdir=os.path.expanduser("~"))
    root.destroy()
    return dest

def main():
    print("=== TẠO CẤU TRÚC LCTC TỪ KHOẢNG SỐ ===")
    try:
        start = int(input("Nhập số bắt đầu: ").strip())
        end   = int(input("Nhập số kết thúc: ").strip())
    except ValueError:
        print("❗ Vui lòng nhập số nguyên hợp lệ.")
        sys.exit(1)

    if start > end:
        print("❗ Số bắt đầu phải ≤ số kết thúc.")
        sys.exit(1)

    # Đảm bảo có template.docx chuẩn
    ensure_template()

    # Popup chọn nơi lưu
    dest_dir = choose_directory_topmost("Chọn nơi lưu các folder LCTC-*")
    if not dest_dir:
        print("❗ Bạn đã hủy chọn nơi lưu. Thoát.")
        sys.exit(1)

    total = end - start + 1
    created = skipped = 0

    for n in range(start, end + 1):
        folder_name = f"LCTC-{n}"
        safe = sanitize(folder_name)
        base = os.path.join(dest_dir, safe)
        if not os.path.exists(base):
            os.makedirs(base, exist_ok=True)
            created += 1
        else:
            skipped += 1

        # subfolders
        for sf in SUBFOLDERS:
            os.makedirs(os.path.join(base, sf), exist_ok=True)

        # files
        main_doc = os.path.join(base, f"{safe}.docx")
        desc_doc = os.path.join(base, "MO TA.docx")

        if not os.path.exists(main_doc):
            new_blank_docx(main_doc)
        if not os.path.exists(desc_doc):
            new_blank_docx(desc_doc)

    # Thông tin kết quả
    msg = (
        f"Hoàn tất!\n"
        f"Tổng: {total}\n"
        f"Tạo mới: {created}\n"
        f"Đã tồn tại: {skipped}\n"
        f"Thư mục đích:\n{dest_dir}"
    )
    print("\n=== KẾT QUẢ ===")
    print(msg)

    input("\nNhấn Enter để thoát...")

if __name__ == "__main__":
    main()
