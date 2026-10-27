@echo off
rem Gera dist\Claude-Containers-<versao>-Setup-x64.exe (Windows x64). Requer Python 3.10+ x64 e Inno Setup 6.
setlocal
cd /d "%~dp0"
set /p VER=<VERSION
if not exist .venv-build ( py -3 -m venv .venv-build || exit /b 1 )
call .venv-build\Scripts\activate.bat
pip install -q -r requirements.txt -r requirements-build.txt || exit /b 1
pyinstaller --noconfirm --clean claude-containers.spec || exit /b 1

set ISCC=ISCC.exe
where ISCC.exe >nul 2>nul || set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
"%ISCC%" /DAppVersion=%VER% packaging\installer.iss || exit /b 1
echo OK: dist\Claude-Containers-%VER%-Setup-x64.exe
