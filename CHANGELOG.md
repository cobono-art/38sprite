# 바뀐 내역 / Changelog

버전은 [깃허브 릴리스](https://github.com/cobono-art/38sprite/releases) 태그와 같습니다. 앱 화면 왼쪽 위에서 지금 버전을 볼 수 있어요.
Versions match the [GitHub release](https://github.com/cobono-art/38sprite/releases) tags. The app shows its version at the top left.

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
