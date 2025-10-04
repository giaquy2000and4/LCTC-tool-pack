@echo off
REM Clear SSLKEYLOGFILE to prevent PermissionError during pip install
set "SSLKEYLOGFILE="

set NAME=LCTC-Pipeline-GUI
set ICON=icon.ico
set MAIN=lctc_pipeline_gui.py

REM Cài phụ thuộc build (chạy 1 lần là đủ)
echo Cài đặt/Kiểm tra các thư viện Python cần thiết...
python -m pip install --upgrade pip
pip install pyinstaller customtkinter yt-dlp python-docx certifi pywin32

REM Xóa build cũ (tùy chọn)
echo Xóa các thư mục build/dist cũ (nếu có)...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist %NAME%.spec del %NAME%.spec

echo Bắt đầu quá trình build với PyInstaller...
pyinstaller ^
  --name %NAME% ^
  --onefile ^
  --windowed ^
  --icon=%ICON% ^
  --add-data "template.docx;." ^
  --hidden-import tkinter ^
  --hidden-import pythoncom ^
  --hidden-import win32com.client ^
  --collect-all yt_dlp ^
  --collect-data certifi ^
  %MAIN%

echo.
echo ==== DONE ====
echo File: dist\%NAME%.exe
pause