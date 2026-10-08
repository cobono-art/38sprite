@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem 38Sprite 실행: ComfyUI에 딸린 파이썬(aiohttp, numpy, opencv, PIL 포함)을 찾아서 쓴다.
rem 찾는 순서: python_path.txt → 지금 켜져 있는 ComfyUI의 파이썬 → 흔한 설치 위치(C~F 드라이브, 이 폴더 옆).
rem 찾으면 python_path.txt 에 적어 두고 다음부터 바로 쓴다. 다른 파이썬을 쓰려면 그 파일에 python.exe 전체 경로를 적으세요.
set "PY="
if exist "python_path.txt" set /p PY=<python_path.txt
if defined PY if not exist "%PY%" set "PY="
if not defined PY for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*main.py*' -and $_.ExecutablePath -like '*python_embeded*' } | Select-Object -First 1 -ExpandProperty ExecutablePath" 2^>nul`) do set "PY=%%P"
if not defined PY for %%D in (C D E F) do for %%N in ("ComfyUI_windows_portable" "ComfyUI_windows_portable_nvidia\ComfyUI_windows_portable") do if not defined PY if exist "%%D:\%%~N\python_embeded\python.exe" set "PY=%%D:\%%~N\python_embeded\python.exe"
if not defined PY if exist "%~dp0..\ComfyUI_windows_portable\python_embeded\python.exe" set "PY=%~dp0..\ComfyUI_windows_portable\python_embeded\python.exe"
if not defined PY (
  echo ComfyUI 파이썬을 찾지 못했어요. ComfyUI를 켠 뒤 다시 실행하거나, python_path.txt 에 python.exe 경로를 적어 주세요.
  pause
  exit /b 1
)
if not exist "python_path.txt" (echo %PY%)> "python_path.txt"
echo 파이썬: %PY%
"%PY%" -s app\server.py --open
pause
