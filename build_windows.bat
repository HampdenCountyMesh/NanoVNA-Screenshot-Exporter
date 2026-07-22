@echo off
setlocal
py -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
pyinstaller --noconfirm --clean --onefile --windowed --name NanoVNA-Screenshot-Exporter run.py
echo.
echo Built: dist\NanoVNA-Screenshot-Exporter.exe
pause
