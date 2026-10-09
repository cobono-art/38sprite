@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem 38Sprite 실행: ComfyUI에 딸린 파이썬(aiohttp, numpy, PIL 포함)을 찾아서 쓴다.
rem 찾는 순서: python_path.txt → 지금 켜져 있는 ComfyUI의 파이썬(포터블·데스크톱 앱·가상환경) → 흔한 설치 위치(C~F 드라이브,
rem 데스크톱 앱 기본 위치, 이 폴더 옆). 찾으면 python_path.txt 에 적어 두고 다음부터 바로 쓴다.
rem 다른 파이썬을 쓰려면 그 파일에 python.exe 전체 경로를 적으세요.
set "PY="
if exist "python_path.txt" set /p PY=<python_path.txt
if defined PY if not exist "%PY%" set "PY="
if not defined PY for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*main.py*' -and ($_.ExecutablePath -like '*python_embeded*' -or $_.CommandLine -like '*ComfyUI*') } | Select-Object -First 1 -ExpandProperty ExecutablePath" 2^>nul`) do set "PY=%%P"
if not defined PY for %%D in (C D E F) do for %%N in ("ComfyUI_windows_portable" "ComfyUI_windows_portable_nvidia\ComfyUI_windows_portable") do if not defined PY if exist "%%D:\%%~N\python_embeded\python.exe" set "PY=%%D:\%%~N\python_embeded\python.exe"
if not defined PY if exist "%USERPROFILE%\Documents\ComfyUI\.venv\Scripts\python.exe" set "PY=%USERPROFILE%\Documents\ComfyUI\.venv\Scripts\python.exe"
if not defined PY if exist "%~dp0..\ComfyUI_windows_portable\python_embeded\python.exe" set "PY=%~dp0..\ComfyUI_windows_portable\python_embeded\python.exe"
if not defined PY (
  echo ComfyUI 파이썬을 찾지 못했어요. ComfyUI를 켠 뒤 다시 실행하거나, python_path.txt 에 python.exe 경로를 적어 주세요.
  pause
  exit /b 1
)
echo 파이썬: %PY%

rem 필요한 패키지 확인 (app\check_deps.py). ComfyUI 기본 설치에는 OpenCV(cv2)가 없다.
set "MISSING="
for /f "usebackq delims=" %%M in (`"%PY%" -s app\check_deps.py`) do set "MISSING=%%M"
if defined MISSING call :install
if errorlevel 1 (
  pause
  exit /b 1
)
if not exist "python_path.txt" (echo %PY%)> "python_path.txt"
if "%SPRITE_NO_START%"=="1" exit /b 0
"%PY%" -s app\server.py --open
pause
exit /b 0

:install
echo.
echo 이 파이썬에 38Sprite가 쓰는 패키지가 없어요: %MISSING%
echo 처음 한 번 설치가 필요해요 (ComfyUI 기본 설치에는 OpenCV가 없어요). 이미 있는 numpy 등은 건드리지 않아요.
set "ANS="
set /p ANS=지금 이 파이썬에 설치할까요? [Y/N]
if /i not "%ANS%"=="Y" (
  echo 설치하지 않았어요. 직접 설치하려면: "%PY%" -m pip install -r requirements.txt
  exit /b 1
)
for %%K in (%MISSING%) do call :pip %%K
"%PY%" -s -c "import aiohttp, numpy, cv2, PIL" || (
  echo 설치했지만 아직 불러오지 못했어요. 위 메시지를 확인해 주세요.
  exit /b 1
)
echo 설치했어요.
exit /b 0

:pip
if "%~1"=="opencv-python-headless" (
  "%PY%" -s -m pip install --no-deps "opencv-python-headless>=4.9,<4.12"
) else (
  "%PY%" -s -m pip install %~1
)
exit /b 0
