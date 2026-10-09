# 바뀐 내역 / Changelog

버전은 [깃허브 릴리스](https://github.com/cobono-art/38sprite/releases) 태그와 같습니다. 앱 화면 왼쪽 위에서 지금 버전을 볼 수 있어요.
Versions match the [GitHub release](https://github.com/cobono-art/38sprite/releases) tags. The app shows its version at the top left.

## v0.6.0 — 2026-10-09

**처음 설치 / First install**
- ComfyUI 기본 설치에는 OpenCV가 없어서, 깃허브에서 새로 받은 사람은 앱이 켜지지 않을 수 있었습니다. `run_app.bat`이
  빠진 패키지를 알려 주고 설치할지 묻습니다(이미 있는 numpy 등은 건드리지 않음).
- ComfyUI 데스크톱 앱·가상환경 설치도 찾습니다.
- ComfyUI가 여러 개 켜진 PC에서 앱이 다른 ComfyUI의 파이썬을 골라, 빛 궤적 빼기 노드 확인·설치와 자동 켜기가 엉뚱한
  ComfyUI를 향했습니다. 켜져 있는 영상 AI ComfyUI의 파이썬을 기억해서 씁니다(설정 `comfy_python`).
- A stock ComfyUI has no OpenCV, so a fresh download could fail to start: `run_app.bat` now lists missing packages and
  offers to install them. ComfyUI desktop-app/venv installs are found, and on PCs with several ComfyUIs the video-AI one is
  remembered for node checks, node install and auto-start.

**걷기·달리기 / Walks and runs**
- 방향마다 따로 반복 구간을 고르면 어떤 방향은 두 바퀴를 골라, 게임에서 방향을 틀면 걸음이 두 배로 빨라졌습니다.
  이제 모든 방향이 한 바퀴(두 걸음)씩입니다.
- Every direction now loops exactly one cycle (two steps), so the cadence doesn't double when the character turns.

**도트 / Pixel art**
- 원본 그림의 머리를 장면마다 맞는 자리에 옮겨 붙여, 얼굴이 원본 그대로이고 흔들리지 않습니다(고개를 숙이거나 효과가
  가린 장면은 그대로, 설정 `pixel_keep_head`).
- 원본에 외곽선이 있으면 바깥에 한 줄을 더 두르지 않고 안쪽 한 줄을 외곽선으로 씁니다. 외곽선이 두 겹이 되거나 실루엣이
  한 칸 커지던 것이 없어졌습니다(설정 `pixel_outline`).
- 도트 스타일은 영상을 480으로 만듭니다. 방향당 80~85초 → 55~60초, 도트 결과는 같습니다(설정 `pixel_video_size`).
- The original drawing's head is pasted into every frame where it fits, the outline stays a single row like the art, and
  pixel-style videos render at 480 px (about 30% faster, same result).

**방향 그림 / Direction drawings**
- 앞뒤가 바뀐 대각선을 정면에만 있는 얼굴 색으로 찾습니다(예전 검사는 후드가 머리를 덮은 캐릭터를 놓쳤음). 찾으면 그
  칸만 Codex로 자동으로 다시 그립니다(기본 2번까지, 설정 `auto_redraw`).
- 방향마다 몸 키를 맞춥니다(±8%까지). Codex가 방향마다 조금씩 다른 크기로 그려서 방향을 틀면 캐릭터가 커졌다
  작아졌습니다. 늑대인간처럼 원래 생김새가 다른 키 차이는 그대로 둡니다(설정 `even_height`).
- Wrong-facing diagonals are found by face colors and redrawn automatically; body heights are evened out across directions.

**남은 효과 지우기 / Fix leftover effects**
- ComfyUI 공식 Qwen-Image-Edit(2509·2511, Lightning 4단계 LoRA가 있으면 4단계)도 씁니다. 영상 AI ComfyUI 하나로도
  됩니다(처음 모델 읽기 몇 분, 다음부터 한 장 20초 안팎).
- Works with ComfyUI's official Qwen-Image-Edit too, even inside the video-AI ComfyUI.

## v0.5.0 — 2026-10-09

**도트 / Pixel art**
- Codex는 키 64칸으로 지시해도 실제로는 약 74칸으로 그립니다. 그래서 64칸으로 줄이면 눈·허리띠·지팡이 구슬이
  뭉개졌습니다. 방향 그림에서 도트 한 칸 크기를 재서 결과를 그 키로 만듭니다(방향 그림 아래 '도트 키 N칸',
  설정 `pixel_auto_height`). 못 재거나 도트 그림이 아니면 설정한 키를 씁니다.
- 도트 마감에서 작은 잡티를 둘레 색으로 합치고, 장마다 색이 바뀌는 지글거림을 줄였습니다.
- 시험: Codex 그림을 진짜 도트로 먼저 정리해서 영상을 만드는 방식(정수배 격자)은 이득이 없었습니다. 영상 AI가
  움직이는 동안 격자를 지키지 않아서, 그대로 만들고 마지막에 정리합니다.
- Codex draws about 74 pixels tall when asked for 64; the pixel height is now measured from the drawn pixel grid so one
  sprite pixel matches one pixel of the art (`pixel_auto_height`). Small specks are merged and color flicker reduced.

**마젠타 / Magenta**
- Codex 방향 그림과 한 방향 다시 그리기도 마젠타 배경으로 그립니다. 회색 배경은 지팡이 테두리에 회색 잔테두리,
  몸과의 틈에 회색이 남았습니다.
- 3D 마네킹 모드 생성 단계를 4 → 6으로 늘렸습니다. 4단계는 시드 40%쯤이 배경을 얼룩·동심원으로 망가뜨려 다시
  만들어야 했습니다(설정 `turbo_r2v_steps`).
- 영상 프롬프트의 "배경은 마젠타" 문장은 그대로 둡니다(빼 보니 배경이 바뀐 장면이 걷기 3 → 46장, 마법 18 → 64장).
- Direction drawings are made on magenta too, and the 3D mannequin mode uses 6 steps instead of 4 (4 broke about 40%
  of backgrounds).

**걷기·달리기 / Walks and runs**
- 디딘 발을 따라가 발이 미끄러지지 않는 이동 속도를 재고(`move_speed`), '게임처럼 걸어 보기'로 땅이 움직이는
  화면을 보며 속도를 맞출 수 있습니다(0.3~3배, 시트 JSON에 반영).
- The movement speed is measured from the planted foot, and "Walk like in a game" previews the motion over a scrolling
  ground to tune it.

**남은 효과 지우기 (선택) / Fix leftover effects (optional)**
- 칸을 골라 '이 장 효과 지우기'를 누르면 이미지 편집 AI(Qwen-Image 2.1 edit)가 그 장의 빛 효과만 지우고 시트를
  다시 만듭니다. '원래 장면으로'로 되돌립니다. 편집 모델이 있는 ComfyUI가 따로 필요합니다(설정 `edit_url`).
- "Remove effects in this frame" erases leftover light effects in one frame with an image-editing AI; "Original frame"
  undoes it.

**3D 마네킹 / 3D mannequin**
- 같은 사람 모델을 2~3등신으로 만든 마네킹을 고를 수 있습니다(`mannequin_body: chibi`). 시험에서는 어른 모델과
  결과가 거의 같아 기본은 그대로입니다.
- A chibi-proportioned mannequin is available (`mannequin_body: chibi`); it tested about the same, so it is not the default.

**홍보 영상 / Promo video**
- 여러 캐릭터가 같이 추는 춤 장면도 스프라이트 프레임(초당 10장)으로 바꿨습니다.

## v0.4.0 — 2026-10-09

**빛 궤적 빼기 / Light-trail removal**
- 영상 AI(H3)는 '효과 없음'이어도 휘두르는 동작에 큰 궤적·별빛·빛무리를 그렸습니다. 원인 두 가지를 고쳤습니다.
  - 프롬프트의 금지문("no slash trails, no glow …")이 오히려 그 낱말을 그리게 했습니다(H3 공식 안내와 같음). 영상
    프롬프트는 원하는 상태만 긍정형으로 적습니다.
  - H3는 네거티브 프롬프트가 없습니다. NegPiP 원리를 직접 구현한 ComfyUI 노드(`comfyui_nodes/sprite_neg_h3`)로
    효과 없이 만드는 동작에서 궤적·반짝임·빛무리를 생성 단계에서 뺍니다. 생성 시간은 그대로입니다.
    `setup_negative.bat`으로 ComfyUI에 설치하면 앱이 알아서 씁니다 (설정 `negative_words`·`negative_weight`).
  - 시험(같은 시드): 정면·옆 공격, 공격 5방향, 춤 5방향에서 궤적이 사라지고 동작은 그대로, 걷기는 변화 없음.
- Prompts no longer name unwanted things (that made H3 draw them), and a ComfyUI node written for 38Sprite removes light
  trails, sparkles and glows during generation at the same speed. Install it with `setup_negative.bat`.

**3D 마네킹 / 3D mannequin**
- 기본 레퍼런스를 원통 마네킹에서 사람 3D 모델(머리카락 없는 점토 모습)로 바꿨습니다. 원통 마네킹은 앞팔·뒤팔이
  똑같아 보여서 영상 AI가 뒤쪽 빈손을 휘두르곤 했습니다. 새 프롬프트로는 사람 모델의 생김새를 베끼지 않았습니다.
  뼈대 도구 가상환경(`setup_pose.bat`)이 없으면 원통 마네킹을 씁니다 (설정 `mannequin_body`).
- 마네킹이 무기를 들지 않게 된 뒤로 "빈손은 비워 둬" 문장이 캐릭터 무기를 치우게 해서, "든 물건은 같은 손에, 그
  손과 함께 움직인다"로 바꿨습니다.
- The mannequin reference is now a shaded human model (bald clay) instead of capsules, so the video AI can tell which
  arm is in front; the prompt keeps the character's held item in its hand.

**영상 AI 켜기 / Starting the video AI**
- 앱을 켤 때 이 PC의 ComfyUI가 꺼져 있으면 마지막으로 본 실행 옵션 그대로 켭니다 (`comfy_autostart`).
- 빛 궤적 빼기 노드가 깔렸는데 ComfyUI가 추가 노드를 끈 채로(`--disable-all-custom-nodes`) 켜져 있으면, 위쪽의
  '빛 궤적 빼기 켜기' 버튼이 같은 옵션에 이 노드만 허용해서 다시 켭니다.
- The app starts the local ComfyUI if it is off, and a button restarts it with the trail-removal node allowed.

**더 빠르고 더 깨끗하게 / Faster and cleaner**
- '방향별 바로' 모드의 생성 단계를 8 → 6으로 줄였습니다(약 25% 빠름, 같은 품질; 설정 `turbo_steps`).
- 영상 AI가 마젠타 배경 위에 동심원·소용돌이 무늬를 그리면 배경이 바뀐 것으로 보고 새 시드로 다시 만듭니다.
- Per-direction mode uses 6 steps instead of 8 (about 25% faster); patterned backgrounds (rings, swirls) trigger a
  regeneration with a new seed.

## v0.3.0 — 2026-10-08

**화면 간소화 / Simpler screen**
- 지금 배치는 그대로 두고 자주 안 쓰는 것만 접었습니다.
  - 보기 설정: 방향 그림이 생기면 한 줄 요약으로 접힙니다('바꾸기'로 펼침).
  - 방향 그림: 직접 올리기·한 방향만 다시 그리기·예전 그림을 작은 링크로. 앞뒤가 바뀐 칸이 있으면 다시 그리기 줄이 바로 보입니다.
  - 동작 만들기: 프레임·이름·방향 맞추는 방식·빛 효과를 '고급 옵션'으로 접고, 지금 값을 한 줄로 보여 줍니다.
  - 세트: '기본 동작 한 번에 만들기' 버튼 하나와 '동작 고르기' 링크.
  - 받기: 버튼 5개를 '받기 ▾' 메뉴 하나로.
  - 재생기: 해상도·배경·정보를 '정보 · 보기 설정' 안으로.
- Same layout, but rarely used controls are folded away: view settings collapse to a one-line summary once a drawing
  exists; upload / redraw one direction / earlier drawings become small links; frames, mode and light effects move under
  "Advanced" with a one-line summary; the five download buttons become one "Download ▾" menu; player display options
  and stats move into "Info · display".

**3D 마네킹 / 3D mannequin**
- 마네킹 영상에 든 막대(무기)를 그리지 않습니다. 그리면 지팡이를 든 캐릭터도 칼을 든 모습으로 바뀌었습니다(실험: 막대 있음 4개 중 2개, 없음 0개). 칼끝까지 화면에 들어오게 하는 크기 계산에는 그대로 씁니다.
- The mannequin video no longer shows the held prop (it made staff-wielding characters draw a sword); the prop is still
  used to size the frame.

## v0.2.1 — 2026-10-08

**처음 쓰는 사람 설치 / First-time setup**
- 처음 켤 때 켜져 있는 ComfyUI(8188·8189·8000)를 찾아, H3 모델 파일이 있는 쪽 주소를 `config.json`에 적어 둡니다. 기본 주소는 ComfyUI 표준인 8188로 바꿨습니다.
- `run_app.bat`이 켜져 있는 ComfyUI의 파이썬을 쓰고, 없으면 C~F 드라이브의 흔한 설치 위치를 찾아 `python_path.txt`에 기억합니다 (전에는 E 드라이브 등은 못 찾았음).
- 첫 화면에 아직 설치하지 않은 선택 도구(AI 배경 지우기, 영상 → 3D 뼈대)를 알려 줍니다.
- The app finds a running ComfyUI with the H3 model on first launch; `run_app.bat` finds ComfyUI's Python on more drives; the start screen lists missing optional tools.

**안정성 / Reliability**
- 영상을 기다리는 동안 잠깐 연결이 끊겨도(포트 부족 등) 2분까지 다시 물어서, 작업 전체가 실패하지 않습니다.
- 배경이 마젠타에서 바뀌면 새 시드로 다시 만드는 횟수 기본값을 2번으로 올렸습니다. 실험(같은 동작 · 시드 3개 × 프롬프트 3가지)에서 배경이 바뀌는 건 프롬프트 문구가 아니라 시드가 정했습니다.
- 빛 효과 알파에서 배경색 그대로 어두워진 곳(그림자)을 남기지 않습니다.
- Polling survives short disconnects; background-drift retries default to 2 (drift depends on the seed, not the prompt); shadows are dropped from light alpha.

**개발 / Development**
- 자동 테스트 29개(`python -m unittest discover -s tests`, 추가 설치·영상 AI 없이 가짜 프레임으로)와 깃허브 자동 검사(윈도우·리눅스)를 넣었습니다.
- `requirements.txt`의 OpenCV를 화면 없는 판(opencv-python-headless)으로 바꿨습니다.
- Automated tests and GitHub Actions CI; headless OpenCV in requirements.

## v0.2.0 — 2026-10-08

**처음부터 끝까지 마젠타 배경 / Magenta from start to end**
- 영상 AI에 배경을 매 프레임 마젠타로 유지하라고 더 강하게 지시합니다.
- 방향마다 영상을 받으면 바로 배경을 검사해서, 마젠타가 아닌 프레임이 10%를 넘으면 새 시드로 한 번 더 만들고 덜 바뀐 쪽을 씁니다(`bg_retry`). 자동 점검에 '배경색이 바뀜'이 추가됐습니다.
- 3D 마네킹 모드도 마젠타 배경으로 만듭니다(`mannequin_bg`). 마네킹이 든 소품은 회색으로 그려서, 지팡이를 든 캐릭터가 칼을 베끼지 않게 했습니다.
- Stronger prompt, a background check with one automatic regeneration, a new "background color changed" check, and a magenta 3D mannequin with a gray prop.

**AI 배경 지우기와 층 분리 / AI matting and layers** (선택 / optional, `setup_matting.bat`)
- BEN v2(MIT)로 크로마키가 틀리는 곳만 고칩니다: 배경과 비슷한 색에 난 구멍, 바닥 그림자, 색 테두리. '지우기' 모드도 AI로 지워 밝은 캐릭터에 구멍이 나지 않습니다.
- 빛 효과를 살린 동작은 캐릭터 층(`sheet_hd_body.png`)과 빛 층(`sheet_hd_fx.png`)을 같은 배치로 함께 만듭니다.
- BEN v2 fixes holes, floor shadows and fringes; "strip" uses AI instead of punching holes; vivid motions get body/effects layer sheets.

**게임용 정보 / Game info**
- 시트 JSON·Aseprite·Godot에 `hit_frame`(공격이 맞는 칸), `hold_last`, `frame_ms`, 걷기·달리기의 `move_speed`와 방향별 `velocity`를 넣습니다.

**되돌리기 / Undo a remake**
- '이 방향만 다시 만들기' 전 결과를 보관하고, 재생 화면에서 전 결과로 되돌리거나 다시 앞으로 바꿀 수 있습니다.

**더 빠른 생성 / Faster generation**
- 글로 만드는 반복 동작과 3D 마네킹 한 번 동작은 3초 영상으로 만듭니다(5초와 같은 품질, 30~40% 빠름). 마네킹 키프레임의 앞뒤 기다림만 줄입니다.

**그 밖에 / Also**
- 게임 엔진용 내보내기(Aseprite JSON, Godot 4, 프레임 PNG)와 '전체 받기'의 Godot SpriteFrames 합치기
- 자동 점검(구멍·테두리·이음새·잘림·크기·빈 칸), 기본 모션 세트, 한 방향 다시 그리기·다시 만들기
- 레퍼런스 영상 → 3D 뼈대(MediaPipe, `setup_pose.bat`), 영어 화면, README 영어판
- 홍보 영상과 하이라이트를 AI 배경 지우기로 다시 오린 버전으로 교체

## v0.1.0 — 2026-10-08

- 첫 공개 버전 / First public release
- 삼면도 → Codex 8방향 그림 → 방향별 MiniMax H3 영상 → 8방향 스프라이트 시트(PNG·JSON·GIF)
- 글·레퍼런스 영상·3D 마네킹 동작, 반복·한 번 동작, HD·도트, 빛 효과, 재생 속도·장면 바꾸기
- GIF 색 깜빡임 수정(모든 프레임이 팔레트 하나를 같이 씀)
