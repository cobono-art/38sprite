@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem 빛 궤적 빼기 노드 설치 (선택). comfyui_nodes\sprite_neg_h3 를 영상 AI ComfyUI의 custom_nodes 폴더에 복사한다.
rem H3는 네거티브 프롬프트가 없어서, 효과 없이 만들 동작에서 이 노드로 빛 궤적·반짝임·빛무리를 뺀다. 생성 시간은 거의 같다.
rem 38Sprite가 직접 만든 노드라 따로 받는 것은 없다.
set "COMFY="
set "PY="
if exist "python_path.txt" for /f "usebackq delims=" %%P in ("python_path.txt") do set "PY=%%P"
if defined PY for %%D in ("%PY%") do set "PYDIR=%%~dpD"
if defined PYDIR if exist "%PYDIR%..\ComfyUI\custom_nodes" set "COMFY=%PYDIR%..\ComfyUI"
if not defined COMFY if defined PYDIR if exist "%PYDIR%..\..\custom_nodes" set "COMFY=%PYDIR%..\.."
if defined COMFY goto copy
echo ComfyUI 폴더를 찾지 못했어요. main.py가 있는 ComfyUI 폴더 경로를 붙여 넣고 Enter를 누르세요:
set /p "COMFY="
:copy
if not exist "%COMFY%\custom_nodes" goto fail
xcopy /e /i /y "comfyui_nodes\sprite_neg_h3" "%COMFY%\custom_nodes\sprite_neg_h3" >nul || goto fail
echo.
echo 설치했어요: %COMFY%\custom_nodes\sprite_neg_h3
echo ComfyUI를 다시 켜면, 앱이 효과 없이 만드는 동작에 자동으로 써요 (끄려면 config.json에 "negative_weight": 0).
pause
exit /b 0
:fail
echo.
echo 설치하지 못했어요. 고른 폴더 안에 custom_nodes 폴더가 있는지 확인해 주세요.
pause
exit /b 1
