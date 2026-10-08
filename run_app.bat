@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem 38Sprite 실행: ComfyUI에 딸린 파이썬(aiohttp, numpy, opencv, PIL 포함)을 찾아서 쓴다.
rem 다른 파이썬을 쓰려면 이 폴더에 python_path.txt 를 만들고 python.exe 전체 경로를 한 줄로 적으세요.
set "PY="
if exist "python_path.txt" set /p PY=<python_path.txt
if not defined PY for %%P in (
  "%~dp0..\ComfyUI_windows_portable\python_embeded\python.exe"
  "C:\ComfyUI_windows_portable_nvidia\ComfyUI_windows_portable\python_embeded\python.exe"
  "C:\ComfyUI_windows_portable\python_embeded\python.exe"
  "D:\ComfyUI_windows_portable\python_embeded\python.exe"
) do if not defined PY if exist %%P set "PY=%%~P"
if not defined PY (
  echo ComfyUI 파이썬을 찾지 못했어요. python_path.txt 에 python.exe 경로를 적어 주세요.
  pause
  exit /b 1
)
echo 파이썬: %PY%
"%PY%" -s app\server.py --open
pause
