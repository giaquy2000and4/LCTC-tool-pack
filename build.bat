@echo off
set NAME=LCTC-Pipeline
set ICON=icon.ico
set MAIN=lctc_pipeline_cli.py

REM Cài phụ thuộc build (chạy 1 lần là đủ)
python -m pip install --upgrade pip
pip install pyinstaller yt-dlp python-docx certifi pywin32

REM Xóa build cũ (tùy chọn)
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist %NAME%.spec del %NAME%.spec

pyinstaller ^
  --name %NAME% ^
  --onefile ^
  --console ^
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
