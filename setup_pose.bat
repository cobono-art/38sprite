@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem 영상 → 3D 뼈대 도구 설치 (선택). 레퍼런스 영상을 3D 마네킹으로 따라 할 때 영상에서 관절을 직접 뽑는다.
rem ComfyUI 파이썬과 섞이지 않게 앱 전용 가상환경(.venv-pose)에 mediapipe(뼈대 뽑기)·moderngl·pygltflib(사람 모델 그리기)를 깔고, 자세 모델을 models 폴더에 받는다.
rem 파이썬 3.10~3.12가 필요해요 (py 런처 또는 PATH의 python). 받는 크기: 패키지 약 100MB + 모델 약 30MB.
set "PYEXE="
for %%V in (3.12 3.11 3.10) do if not defined PYEXE py -%%V -c "import sys" >nul 2>&1 && set "PYEXE=py -%%V"
if not defined PYEXE python -c "import sys" >nul 2>&1 && set "PYEXE=python"
if not defined PYEXE (
  echo 파이썬 3.10~3.12를 찾지 못했어요. python.org에서 설치한 뒤 다시 실행해 주세요.
  pause
  exit /b 1
)
echo 파이썬: %PYEXE%
if not exist ".venv-pose\Scripts\python.exe" %PYEXE% -m venv .venv-pose || goto fail
".venv-pose\Scripts\python.exe" -m pip install --disable-pip-version-check mediapipe moderngl pygltflib || goto fail
if not exist models mkdir models
if not exist "models\pose_landmarker_heavy.task" curl -L -o "models\pose_landmarker_heavy.task" "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task" || goto fail
echo.
echo 끝났어요. 앱을 다시 켜면 '레퍼런스 영상 + 3D 마네킹'에서 영상의 3D 뼈대를 그대로 씁니다.
pause
exit /b 0
:fail
echo.
echo 설치하다 실패했어요. 위의 메시지를 확인해 주세요.
pause
exit /b 1
