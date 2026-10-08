@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem AI 배경 지우기 모델 받기 (선택). BEN v2 (PramaLLC, MIT 라이선스)를 models\ben2 에 받는다.
rem 크로마키가 틀리는 곳(배경과 비슷한 색의 구멍, 바닥 그림자, 색 테두리)을 고치고, 빛 효과 동작은 캐릭터 층·빛 층으로 나눈다.
rem 앱을 ComfyUI에 딸린 파이썬으로 돌리면 torch가 이미 있어서 따로 설치할 것이 없어요. 받는 크기: 약 380MB.
if not exist "models\ben2" mkdir "models\ben2"
if not exist "models\ben2\BEN2.py" curl -L -o "models\ben2\BEN2.py" "https://huggingface.co/PramaLLC/BEN2/resolve/main/BEN2.py" || goto fail
if not exist "models\ben2\model.safetensors" curl -L -o "models\ben2\model.safetensors" "https://huggingface.co/PramaLLC/BEN2/resolve/main/model.safetensors" || goto fail
echo.
echo 끝났어요. 앱을 다시 켜면 시트를 만들 때 AI 배경 지우기를 같이 써요 (끄려면 config.json에 "matting": "off").
pause
exit /b 0
:fail
echo.
echo 받다가 실패했어요. 위의 메시지를 확인해 주세요.
pause
exit /b 1
