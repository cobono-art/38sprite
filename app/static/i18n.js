"use strict";
/* 영어 화면: 화면 코드(app.js)는 한국어로만 쓰고, 화면에 그려지는 글자를 이 사전으로 바꿔 끼운다.
   정확히 같은 문구(EN) → 숫자·이름이 섞인 문구(EN_RULES) → " · "로 이은 문구는 조각마다 차례로 찾는다.
   새 문구를 화면에 넣으면 여기에 영어를 더해 주세요 (없으면 한국어 그대로 보인다). */
const LANG = (() => {
  try { const v = localStorage.getItem("lang"); if (v === "ko" || v === "en") return v; } catch { /* 무시 */ }
  return (navigator.language || "ko").toLowerCase().startsWith("ko") ? "ko" : "en";
})();

const EN = {
  // 머리말 · 연결
  "캐릭터": "Character", "영상 AI (ComfyUI)": "Video AI (ComfyUI)", "영상 AI 확인 중…": "Checking video AI…",
  "Codex 이미지 생성": "Codex image generation", "Codex 확인 중…": "Checking Codex…", "연결 설정": "Connection settings",
  "영상 AI 연결됨": "Video AI connected", "영상 따라 하기 없음": "no video following", "영상 AI 연결 안 됨": "Video AI not connected",
  "Codex 로그인됨": "Codex logged in", "Codex 확인 필요": "Check Codex", "서버 오류": "Server error",
  "ComfyUI 주소 (영상 AI 모델이 있는 ComfyUI)": "ComfyUI address (the ComfyUI with the video AI model)",
  "저장": "Save", "닫기": "Close", "레퍼런스 영상 모델 있음": "reference-video model found", "레퍼런스 영상 모델 없음": "no reference-video model",
  // 처음 화면 · 새 캐릭터
  "캐릭터 삼면도를 올려서 시작하세요": "Upload a character turnaround to start",
  "삼면도 올리기:": "Upload a turnaround:", "앞·옆·뒤가 한 장에 있는 그림": "front, side and back views in one image",
  "보기 설정:": "View settings:", "보는 각도, 8·4·2방향, HD 또는 픽셀아트": "camera angle, 8/4/2 directions, HD or pixel art",
  "방향 그림:": "Direction drawing:",
  "Codex가 그 각도로 방향별 그림을 그려요. 마음에 안 들면 다시 그리기": "Codex draws every direction at that angle. Redraw if you don't like it",
  "동작 만들기:": "Make motions:",
  "텍스트 설명이나 레퍼런스 영상 → 영상 AI가 방향마다 영상을 만들고 스프라이트 시트로 정리해요":
    "from text or a reference video, the video AI makes a clip per direction and turns them into sprite sheets",
  "필요한 것: Codex 로그인, 영상 AI(기본: MiniMax H3)가 깔린 ComfyUI(켜 둔 상태)":
    "You need: a Codex login and a running ComfyUI with a video AI model (default: MiniMax H3)",
  "+ 새 캐릭터": "+ New character", "새 캐릭터": "New character", "이름": "Name", "예: 빨간머리 모험가": "e.g. Red-haired adventurer",
  "삼면도 이미지를 끌어다 놓거나 눌러서 고르세요 (PNG·JPG)": "Drop a turnaround image here or click to choose (PNG/JPG)",
  "만들기": "Create", "취소": "Cancel", "삼면도 이미지를 골라 주세요": "Choose a turnaround image",
  // 1 · 보기 설정
  "옵션": "Options", "삼면도 크게 보기": "View turnaround", "삼면도": "Turnaround", "보기 설정": "View settings",
  "보는 각도": "Camera angle", "보는 각도(도)": "Camera angle (degrees)", "방향": "Directions", "왼쪽은 반전": "Mirror left",
  "생성 시간을 아끼는 대신, 무기 든 손이 반대로 바뀌어요": "Saves generation time, but the weapon hand flips",
  "왼쪽 방향은 오른쪽을 좌우 반전해서 채우기": "Fill left directions by mirroring the right ones",
  "스타일": "Style", "픽셀아트": "Pixel art", "키": "Height", "픽셀": "Pixel",
  "정면 눈높이": "Eye level", "쿼터뷰 30°": "Quarter view 30°", "높은 쿼터뷰 45°": "High quarter 45°", "탑다운 60°": "Top-down 60°",
  // 2 · 방향 그림
  "방향 그림": "Direction drawing", "방향 그림 크게 보기": "View direction drawing", "아직 없어요": "Not yet",
  "Codex로 그리기": "Draw with Codex", "Codex로 다시 그리기": "Redraw with Codex", "직접 올리기": "Upload my own",
  "한 방향만": "One direction", "다시 그릴 방향": "Direction to redraw", "다시 그리기": "Redraw", "직접 올림": "uploaded",
  "3×3 나침반 배치(가운데 비움, 위가 뒷모습)로 그려요.": "Drawn as a 3×3 compass grid (center empty, back views on top).",
  "이전 방향 그림": "Previous direction drawing",
  "바꾸기": "Change", "접기": "Collapse", "한 방향만 다시 그리기": "Redraw one direction", "예전 그림": "Earlier drawings",
  // 3 · 동작 만들기
  "동작 만들기": "Make a motion", "텍스트 설명": "Text", "레퍼런스 영상": "Reference video", "동작 설명": "Motion description",
  "예: 걷기 / 오른손 검을 머리 위로 치켜들었다가 대각선으로 내려베기": "e.g. walk / raise the sword in the right hand overhead and slash down diagonally",
  "(선택) 동작에 대한 보충 설명": "(optional) extra notes about the motion",
  "레퍼런스 영상 (사람이 동작하는 영상, 앞 5초만 써요)": "Reference video (a person doing the motion; only the first 5 s is used)",
  "반복 동작 (걷기·대기)": "Loop (walk, idle)", "한 번 하는 동작 (공격·피격)": "One-shot (attack, hit)",
  "프레임": "Frames", "비우면 설명에서": "From the description if empty", "방향 맞추는 방식": "How directions are matched",
  "3D 마네킹": "3D mannequin", "마스터 먼저": "Master first", "방향별 바로": "Per direction",
  "Codex가 짠 3D 동작을 방향마다 그 각도에서 따라 해요. 손·궤적·박자가 가장 잘 맞아요.":
    "Each direction follows a 3D motion written by Codex, seen from its own angle. Hands, paths and timing match best.",
  "영상에서 3D 뼈대를 뽑아(MediaPipe) 마네킹을 그대로 움직이고, 방향마다 그 각도에서 따라 해요. 옆모습도 같은 동작이 돼요.":
    "Extracts the 3D skeleton from the video (MediaPipe), drives the mannequin with it, and each direction follows it from its own angle. Side views do the same move.",
  "Codex가 영상을 보고 3D 마네킹 동작으로 옮겨요. setup_pose.bat을 한 번 실행하면 영상에서 뼈대를 직접 뽑아 더 정확해져요.":
    "Codex reads the video and turns it into a 3D mannequin motion. Run setup_pose.bat once to extract the skeleton from the video directly, which is more accurate.",
  "영상에서 3D 뼈대를 뽑는 중이에요 (MediaPipe)": "Extracting the 3D skeleton from the video (MediaPipe)",
  "레퍼런스 영상에서 사람 자세를 거의 찾지 못했어요 (온몸이 잘 보이는 영상을 써 주세요)":
    "Couldn't find a person's pose in most of the reference video (use a video where the whole body is visible)",
  "분홍 효과가 남음": "pink effect left", "바닥 그림자": "floor shadow",
  "영상 AI가 발밑에 회색 그림자를 그렸어요. 게임에서 그림자를 따로 그린다면 이 방향만 다시 만들어 보세요.":
    "The video AI drew a gray shadow under the feet. If your game draws its own shadows, remake just this direction.",
  "영상 AI가 분홍빛 효과를 그렸어요. 그 장을 다른 장면으로 바꾸거나, 이 방향만 다시 만들어 보세요.":
    "The video AI drew a pink effect. Replace the frame or remake just this direction.",
  "한 방향을 먼저 보여 드리고, 고른 영상을 나머지 방향이 따라 해요. 느려요.":
    "Shows one direction first; the others copy the clip you approve. Slow.",
  "방향마다 따로 만들어요. 걷기·대기처럼 단순한 동작에 빠르고 충분해요.":
    "Makes each direction separately. Fast and good enough for simple motions like walk or idle.",
  "빛 효과": "Light FX", "없음": "None", "살리기": "Vivid", "지우기": "Strip",
  "효과 없이 그려요. 걷기·대기·공격처럼 빛 효과가 없는 동작에 맞아요.": "Draws without effects. Right for motions with no light effects, like walk, idle or attack.",
  "마법·검기 같은 빛 효과를 화려하게 살려서 그려요.": "Draws light effects like magic or sword trails vividly.",
  "영상 AI가 그린 빛 궤적을 지워요. 흰 옷·금발처럼 밝은 캐릭터는 구멍이 날 수 있어요.":
    "Removes light trails drawn by the video AI. Bright characters (white clothes, blond hair) may get holes.",
  "레퍼런스 영상을 골라 주세요": "Choose a reference video", "동작 설명을 적어 주세요": "Describe the motion",
  "먼저 2번에서 방향 그림을 만들어 주세요": "Make the direction drawing in step 2 first",
  "고급 옵션 ▸": "Advanced ▸", "고급 옵션 ▾": "Advanced ▾", "세트 만들기": "Make set", "동작 고르기": "Choose motions",
  "기본 모션 세트": "Basic motion set", "게임에 넣을 동작 묶음을 한 번에 만들어요": "Makes a set of game motions in one go",
  "대기": "Idle", "걷기": "Walk", "달리기": "Run", "공격": "Attack", "피격": "Hit", "쓰러짐": "Death",
  // 결과 · 내보내기
  "결과": "Results", "동작": "Motions", "ZIP 받기 (엔진용 포함)": "ZIP (with engine files)", "시트 PNG": "Sheet PNG",
  "시트 PNG·JSON·GIF + Aseprite/Phaser JSON, Godot SpriteFrames, 프레임 PNG(Unity 등)":
    "Sheet PNG/JSON/GIF + Aseprite/Phaser JSON, Godot SpriteFrames, frame PNGs (Unity etc.)",
  "받기 ▾": "Download ▾", "ZIP (엔진용 포함)": "ZIP (with engine files)", "Godot · Phaser · Unity 파일 모두": "Godot · Phaser · Unity files",
  "이 캐릭터 동작 전부": "Every motion of this character", "Godot 하나로 합친 것 포함": "Includes one merged Godot file",
  "정보 · 보기 설정": "Info · display",
  "전체 받기": "Download all", "다 만든 동작 전부 + Godot 하나로 합친 SpriteFrames": "All finished motions + one merged Godot SpriteFrames",
  "+ 새 동작": "+ New motion", "반복": "Loop", "한 번": "One-shot", "반복 동작": "Loop", "한 번 하는 동작": "One-shot",
  "만드는 중": "Making", "완료": "Done", "실패": "Failed", "중지됨": "Stopped", "중단됨": "Interrupted",
  "마스터 확인": "Review master", "마네킹 확인": "Review mannequin",
  "아직 만든 동작이 없어요. 왼쪽 3번에서 동작을 만들면 여기서 방향별로 재생돼요.":
    "No motions yet. Make one in step 3 on the left and it plays here by direction.",
  "왼쪽 2번에서 방향 그림부터 만들어 주세요. 그다음 3번에서 동작을 만들면 여기서 재생돼요.":
    "Make the direction drawing in step 2 first. Then make a motion in step 3 and it plays here.",
  // 재생기
  "방향 고르기": "Pick a direction", "전체": "All", "한 방향": "One", "어둡게": "Dark", "밝게": "Light", "체크": "Checker",
  "재생 속도": "Playback speed", "재생 속도 (원래 속도의 몇 배)": "Playback speed (× original)", "원래대로": "Reset",
  "그림 수": "Frames", "생성": "Generated", "방식": "Mode", "보기": "View", "영상": "video",
  "효과 없음": "No FX", "효과 살림": "Vivid FX", "효과 지움": "FX stripped",
  "장면 바꾸기": "Swap frames", "이상한 장을 누르면 영상의 앞뒤 장면 중에서 골라 바꿀 수 있어요": "Click a bad frame to replace it with a nearby moment of the video",
  "원래 장면으로": "Original frame", "원본 영상": "Source videos", "바꿈": "swapped", "확인": "check",
  "영상 장면을 불러오는 중…": "Loading video frames…", "지금 장면": "Current frame", "지금": "Now",
  "바꾸는 중… 시트를 다시 만들어서 30초쯤 걸려요": "Replacing… rebuilding the sheet takes about 30 s",
  "저장 중…": "Saving…", "저장했어요. 받는 GIF·시트·ZIP도 이 속도예요.": "Saved. Downloaded GIFs, sheets and ZIPs use this speed too.",
  "자동 점검: 문제 없음": "Auto check: no problems",
  "누르면 그 방향으로 가요. 표시된 장을 눌러 다른 장면으로 바꿀 수 있어요.": "Click to jump to that direction. Click a marked frame to replace it.",
  "구멍": "hole", "테두리 색 번짐": "color fringe", "빈 칸": "empty frame", "반복 이음새가 튐": "loop seam jumps",
  "화면 밖으로 잘렸을 수 있음": "may be cut off at the edge", "이 방향만 크기가 다름": "size differs in this direction",
  "옷이나 무기 한가운데가 뚫렸어요. 그 장을 눌러 다른 장면으로 바꾸거나, 이 방향만 다시 만들어 보세요.":
    "A hole in the middle of clothing or a weapon. Click the frame to replace it, or remake just this direction.",
  "가장자리에 배경색(분홍·초록)이 번졌어요. 그 장을 눌러 다른 장면으로 바꿔 보세요.": "Background color (magenta/green) bled into the edge. Click the frame to replace it.",
  "캐릭터가 거의 안 보이는 장이에요. 다른 장면으로 바꿔 보세요.": "The character is barely visible in this frame. Replace it with another moment.",
  "마지막 장에서 첫 장으로 넘어갈 때 튀어 보여요. 프레임 수를 바꾸거나 다시 만들어 보세요.": "The jump from the last frame back to the first is visible. Try another frame count or remake it.",
  "영상에서 캐릭터가 화면 끝에 닿았어요. 칼끝이나 발이 잘렸으면 이 방향만 다시 만들어 보세요.": "The character touched the edge of the video. If a sword tip or feet got cut off, remake just this direction.",
  "이 방향 영상만 새로 만들고 시트를 다시 조립해요 (2~4분)": "Remakes only this direction's video and rebuilds the sheet (2–4 min)",
  "다시 만드는 중…": "Remaking…", "다 만든 동작만 한 방향을 다시 만들 수 있어요": "Only finished motions can remake a direction",
  "두 결과를 맞바꿔요. 마음에 드는 쪽으로 언제든 다시 바꿀 수 있어요": "Swaps the two results. You can switch back any time.",
  "바꾸는 중…": "Swapping…", "보관한 결과가 없어요": "No saved result", "다 만든 동작만 되돌릴 수 있어요": "Only finished motions can be undone",
  "취소했어요": "Cancelled", "배경색이 바뀜": "background color changed",
  "영상 AI가 영상 중간에 배경을 마젠타가 아닌 색으로 바꿨어요. 효과 둘레가 덜 깨끗할 수 있어요 — 이 방향만 다시 만들어 보세요.":
    "The video AI changed the background away from magenta mid-clip. Edges around effects may be less clean — try remaking just this direction.",
  "이 방향만 캐릭터 키가 달라요. 방향 그림을 확인해 보세요.": "The character height differs only in this direction. Check the direction drawing.",
  "더 좋게 (선택, 앱 폴더에서 한 번 실행): setup_matting.bat — AI 배경 지우기":
    "Better results (optional, run once in the app folder): setup_matting.bat — AI matting",
  "더 좋게 (선택, 앱 폴더에서 한 번 실행): setup_pose.bat — 영상 → 3D 뼈대":
    "Better results (optional, run once in the app folder): setup_pose.bat — video → 3D skeleton",
  "setup_pose.bat — 영상 → 3D 뼈대": "setup_pose.bat — video → 3D skeleton",
  "setup_matting.bat — AI 배경 지우기": "setup_matting.bat — AI matting",
  "빛 궤적 빼기 켜기": "Turn on trail removal",
  "이 PC의 ComfyUI가 아니라서 다시 켤 수 없어요": "That ComfyUI is not on this PC, so it can't be restarted",
  "켜져 있는 ComfyUI를 찾지 못했어요": "Couldn't find the running ComfyUI", "다시 켜는 중… (1분쯤)": "Restarting… (about 1 min)",
  "빛 궤적 빼기 노드가 깔려 있지만 ComfyUI가 추가 노드를 끈 채로 켜져 있어요. 같은 설정에 이 노드만 허용해서 다시 켜요.":
    "The trail-removal node is installed, but ComfyUI is running with custom nodes disabled. Restart it with the same settings, allowing only this node.",
  "영상 AI ComfyUI를 지금 설정 그대로, 빛 궤적 빼기 노드만 허용해서 다시 켤게요. 만들고 있는 작업이 있으면 끊겨요. 계속할까요?":
    "Restart the video-AI ComfyUI with its current settings, allowing only the trail-removal node? Any job in progress will be interrupted.",
  "setup_negative.bat — 빛 궤적 빼기 (ComfyUI 다시 켜기)": "setup_negative.bat — remove light trails (restart ComfyUI)",
  // 진행 · 확인 · 실패
  "중지": "Stop", "준비 중": "Preparing", "키프레임 짜는 중": "Writing keyframes", "3D 마네킹 미리보기": "3D mannequin preview",
  "마네킹 확인을 기다려요": "Waiting for mannequin review", "마스터 확인을 기다려요": "Waiting for master review",
  "3D 마네킹 키프레임 미리보기": "3D mannequin keyframe preview", "마스터 방향 원본 영상": "Master direction source video",
  "Codex가 짠 3D 마네킹 동작이에요. 밝은 팔이 오른팔이고, 얼굴 점이 보는 방향이에요. 모든 방향이 이 동작을 그 방향 각도에서 그대로 따라 해요.":
    "This is the 3D mannequin motion Codex wrote. The lighter arm is the right arm and the dot on the face shows where it looks. Every direction follows this motion from its own angle.",
  "레퍼런스 영상에서 뽑은 3D 동작이에요. 모든 방향이 이 동작을 그 방향 각도에서 그대로 따라 해요.":
    "This is the 3D motion extracted from the reference video. Every direction follows it from its own angle.",
  "Codex가 짠 3D 동작이에요. 모든 방향이 이 동작을 그 방향 각도에서 그대로 따라 해요. 마음에 안 들면 다시 짜게 하세요.":
    "This is the 3D motion Codex wrote. Every direction follows it from its own angle. Rewrite it if you don't like it.",
  "이 동작으로 만들기": "Make it with this motion", "이 동작으로 나머지 방향 만들기": "Make the other directions with this motion",
  "키프레임 다시 짜기": "Rewrite keyframes", "마스터 다시 만들기": "Remake master",
  "중지했어요.": "Stopped.", "서버가 꺼지면서 중단됐어요. 다시 만들 수 있어요.": "Interrupted when the server stopped. You can make it again.",
  "만들다가 실패했어요.": "Failed while making it.", "다시 만들기": "Make again",
  "방향 그림을 그리지 못했어요": "Couldn't make the direction drawing", "이미지를 불러오지 못했어요": "Couldn't load the image",
  // 서버 · 작업 메시지
  "대기 중": "Queued", "Codex가 방향 그림을 그리는 중이에요 (보통 1~3분)": "Codex is drawing the directions (usually 1–3 min)",
  "방향마다 캐릭터를 찾는 중": "Finding the character in each direction", "방향별 첫 프레임 만드는 중": "Making the first frame of each direction",
  "레퍼런스 영상 준비 중": "Preparing the reference video", "마스터 영상 정리 중": "Processing the master clip",
  "마스터 확인 대기": "Waiting for master review", "방향별 마네킹 영상 렌더링 중": "Rendering mannequin clips per direction",
  "스프라이트 시트로 정리하는 중": "Assembling sprite sheets", "레퍼런스 영상에서 자세를 뽑는 중": "Extracting poses from the reference video",
  "Codex가 마네킹 키프레임을 짜는 중이에요 (보통 1~2분)": "Codex is writing mannequin keyframes (usually 1–2 min)",
  "마네킹 미리보기 만드는 중": "Making the mannequin preview", "키프레임 확인 대기": "Waiting for keyframe review",
  "새 그림을 방향 그림에 끼우는 중": "Fitting the new view into the drawing",
  "ComfyUI 주소는 http://로 시작해야 해요": "The ComfyUI address must start with http://", "삼면도 이미지를 올려 주세요": "Upload a turnaround image",
  "PNG, JPG, WEBP 이미지만 올릴 수 있어요": "Only PNG, JPG and WEBP images can be uploaded", "프로젝트를 찾지 못했어요": "Project not found",
  "설정 값이 올바르지 않아요": "Invalid settings", "Codex를 쓸 수 없어요": "Codex is not available",
  "방향 그림 파일을 올려 주세요": "Upload a direction drawing file", "먼저 방향 그림을 만들어 주세요": "Make the direction drawing first",
  "없는 방향이에요": "No such direction", "동작 종류가 올바르지 않아요": "Invalid motion type", "레퍼런스 영상을 올려 주세요": "Upload a reference video",
  "영상 AI(ComfyUI)를 쓸 수 없어요": "The video AI (ComfyUI) is not available",
  "지금 영상 AI에는 레퍼런스 영상 따라 하기 기능이 없어요 (H3면 ref2va 모델, 사용자 워크플로면 r2v.json)":
    "The current video AI can't follow reference videos (H3 needs the ref2va model; custom setups need r2v.json)",
  "만들 동작을 하나 이상 골라 주세요": "Pick at least one motion", "재생 속도가 올바르지 않아요": "Invalid playback speed",
  "다 만든 동작만 속도를 바꿀 수 있어요": "Only finished motions can change speed", "다 만든 동작만 장면을 바꿀 수 있어요": "Only finished motions can swap frames",
  "바꿀 칸이 올바르지 않아요": "Invalid frame", "작업을 찾지 못했어요": "Job not found",
  "작업을 찾지 못했어요 (서버를 다시 켜면 진행 중이던 작업 정보는 사라져요)": "Job not found (job info is lost when the server restarts)",
  "아직 결과가 없어요": "No result yet", "아직 다 만든 동작이 없어요": "No finished motions yet", "파일을 찾지 못했어요": "File not found",
  "이 앱 화면에서 온 요청만 받아요": "Only requests from this app's page are accepted",
  "Codex CLI를 찾지 못했어요. 터미널에서 npm i -g @openai/codex 로 설치해 주세요": "Codex CLI not found. Install it in a terminal with npm i -g @openai/codex",
  "Codex에 로그인되어 있지 않아요. 터미널에서 codex login 을 한 번 실행해 주세요": "Codex is not logged in. Run codex login once in a terminal",
  "마네킹 키프레임이 없어요. 키프레임부터 다시 짜 주세요": "No mannequin keyframes. Rewrite the keyframes first",
  "마스터 영상이 없어요. 마스터부터 다시 만들어 주세요": "No master clip. Remake the master first",
  "레퍼런스 영상을 읽지 못했거나 너무 짧아요 (0.5초 이상 필요)": "Couldn't read the reference video or it's too short (needs at least 0.5 s)",
  "Codex가 키프레임 JSON을 돌려주지 않았어요": "Codex didn't return keyframe JSON", "키프레임이 비어 있어요": "The keyframes are empty",
  "이 ComfyUI에는 MiniMax H3 노드가 없어요 (0.37 이상 필요)": "This ComfyUI has no MiniMax H3 nodes (0.37 or later needed)",
  "ComfyUI 큐에서 작업이 사라졌어요 (취소됐거나 ComfyUI가 다시 켜졌어요)": "The job left the ComfyUI queue (cancelled or ComfyUI restarted)",
  "잘못된 프로젝트 id": "Invalid project id",
};

const QA_KO = "구멍|테두리 색 번짐|분홍 효과가 남음|바닥 그림자|빈 칸|반복 이음새가 튐|화면 밖으로 잘렸을 수 있음|이 방향만 크기가 다름";
const PART_STATE = { "대기": "queued", "생성 중": "generating", "완료": "done", "확인 중": "checking", "실패": "failed" };
const EN_RULES = [
  [/^(.*) \(설명을 보고 골랐어요\)$/, (_, a) => `${trKey(a) ?? a} (picked from the description)`],
  [/^(.+) 방향이 (앞모습|뒷모습)처럼 보여요\. 아래 '한 방향만 다시 그리기'로 그 방향만 고칠 수 있어요\.$/,
    (_, d, l) => `${d} looks like a ${l === "앞모습" ? "front" : "back"} view. Fix just that direction with "Redraw one direction" below.`],
  [/^이 그림은 (\d+)° · (\d+)방향 · (HD|픽셀)로 그렸어요\. 지금 설정으로 쓰려면 다시 그려 주세요\.$/,
    (_, a, c, s) => `This drawing was made at ${a}° · ${c} directions · ${s === "픽셀" ? "pixel" : "HD"}. Redraw it to use the current settings.`],
  [/^마스터\((.*)\) 영상이에요\. 나머지 방향이 이 동작을 그대로 따라 해요\. 마음에 들면 이어서 만들고, 아니면 마스터를 다시 만드세요\.$/,
    "This is the master ($1) clip. The other directions will copy this motion. Continue if you like it, or remake the master."],
  [new RegExp(`^(\\S*) ?([NSEW]{1,2}) · (${QA_KO})(?: \\(([\\d·]+)번째 장\\))?$`),
    (_, a, d, q, f) => `${a} ${d} · ${EN[q]}${f ? ` (frame ${f.split("·").join(", ")})` : ""}`],
  [/^(\S+) ([NSEW]{1,2}) (대기|생성 중|완료|확인 중|실패)( \d\d:\d\d)?$/, (_, a, d, s, t) => `${a} ${d} ${PART_STATE[s]}${t || ""}`],
  [/^요청이 실패했어요 \((\d+)\)$/, "Request failed ($1)"],
  [/^더 좋게 \(선택, 앱 폴더에서 한 번 실행\): (.*)$/, (_, t) =>
    `Better results (optional, run once in the app folder): ${t.split(" · ").map(x => trKey(x) ?? x).join(" · ")}`],
  [/^방향 그림 (\d+)장$/, "$1 drawing(s)"], [/^동작 (\d+)개$/, "$1 motion(s)"],
  [/^영상 AI로 만들 방향 (\d+)개 \((.*)\)$/, "Video AI makes $1 directions ($2)"], [/^반전으로 채울 방향 (\d+)개$/, "$1 mirrored"],
  [/^(\d+)방향\(왼쪽은 반전\)$/, "$1 directions (left mirrored)"], [/^픽셀아트 (\d+)px$/, "Pixel art $1px"],
  [/^예전 그림 \((\d+)\)$/, "Earlier drawings ($1)"], [/^프레임 (\d+)$/, "$1 frames"],
  [/^(\d+)방향(?: \+ 반전 (\d+))?$/, (_, a, b) => (b ? `${a} + ${b} mirrored` : `${a} directions`)],
  [/^(\d+)방향 생성(?: \+ 반전 (\d+)방향)?$/, (_, a, b) => `${a} generated${b ? ` + ${b} mirrored` : ""}`],
  [/^([NSEW]{1,2}) 다시 그림$/, "$1 redrawn"], [/^([NSEW]{1,2}) 다시 그리기$/, "Redraw $1"],
  [/^기본 동작 한 번에 만들기 \((\d+)개\)$/, "Make the basic motions at once ($1)"], [/^예상 (\d+)분$/, "about $1 min"],
  [/^생성 중 (\d+)\/(\d+)$/, "Generating $1/$2"], [/^영상 AI 생성 중: (\w+) \((\d+)\/(\d+)\)$/, "Video AI generating: $1 ($2/$3)"],
  [/^Codex가 ([NSEW]{1,2}) 방향만 다시 그리는 중이에요 \(보통 1~3분\)$/, "Codex is redrawing only $1 (usually 1–3 min)"],
  [/^(\w+) 방향 원본$/, "$1 source"], [/^([NSEW]{1,2}) 방향만 보기$/, "Show $1 only"], [/^픽셀 (\d+)px$/, "Pixel $1px"],
  [/^(\d+)장$/, "$1"], [/^자동 점검: 확인할 곳 (\d+)개$/, "Auto check: $1 to review"],
  [/^(\S+) ([NSEW]{1,2}) 방향 (\d+)장$/, "$1 $2 · $3 frames"], [/^(\d+)번째 장 바꾸기$/, "Replace frame $1"],
  [/^(\S+) ([NSEW]{1,2}) (\d+)번째 장을 바꿀 장면을 고르세요$/, "Pick a moment to replace $1 $2 frame $3"],
  [/^영상 원본이라 빛 궤적이 보여도, 고르면 시트에서는 지워져요\.(?: (\w+)는 (\w+)를 좌우로 뒤집은 거라 \w+도 같이 바뀌어요\.)?$/,
    (_, d, s) => "These are raw video frames: light trails you see here are removed in the sheet." +
      (d ? ` ${d} is ${s} mirrored, so ${s} changes too.` : "")],
  [/^(-?[\d.]+)초 장면으로 바꾸기$/, "Use the frame at $1 s"], [/^([+-]?[\d.]+)초$/, "$1 s"],
  [/^([\d.]+)초에 (한 바퀴|한 번)$/, (_, s, o) => `${s} s ${o === "한 바퀴" ? "per loop" : "once"}`],
  [/^원래 속도 \(([\d.]+)초\)$/, "Original speed ($1 s)"], [/^원래 ([\d.]+)초$/, "Original $1 s"],
  [/^([\d.]+)배 (빠르게|느리게)$/, (_, k, f) => `${k}× ${f === "빠르게" ? "faster" : "slower"}`],
  [/^만들다가 실패했어요: (.*)$/, (_, e) => `Failed while making it: ${trKey(e) ?? e}`],
  [/^영상 AI\((H3|사용자 워크플로)\): (.*)$/, (_, b, s) => `Video AI (${b === "H3" ? "H3" : "custom workflow"}): ${s === "사용 가능" ? "available" : (trKey(s) ?? s)}`],
  [/^(.*) \((만드는 중|완료|실패|중지됨|중단됨|마스터 확인|마네킹 확인)\)$/, (_, n, s) => `${trKey(n) ?? n} (${EN[s]})`],
  [/^방향 시트에서 이 방향의 캐릭터를 못 찾았어요: (.*?)( — 다시 그려 주세요)?$/,
    (_, d, r) => `Couldn't find the character for these directions in the drawing: ${d}${r ? " — please redraw" : ""}`],
  [/^Codex CLI를 실행하지 못했어요 \((.*)\)$/, "Couldn't run the Codex CLI ($1)"],
  [/^(\S+) ([NSEW]{1,2}) 방향만 다시 만들기$/, "Remake $1 $2 only"],
  [/^↶ (\S+) 다시 만들기 전으로 되돌리기$/, "↶ Undo the $1 remake"],
  [/^↷ 다시 만든 (\S+)로 돌아가기$/, "↷ Back to the remade $1"],
  [/^([NSEW]{1,2})는 ([NSEW]{1,2})를 뒤집은 거라 ([NSEW]{1,2})를 다시 만들어요$/, "$1 is $2 mirrored, so $2 is remade"],
  [/^지난번 다시 만들기가 실패했어요: (.*)$/, (_, e) => `The last remake failed: ${trKey(e) ?? e}`],
  [/^영상에서 뼈대를 뽑지 못했어요: (.*)$/, "Couldn't extract the skeleton from the video: $1"],
  [/^Codex가 이미지를 만들지 못했어요\. (.*)$/, "Codex couldn't make the image. $1"],
  [/^ComfyUI에 연결하지 못했어요 \((.*)\)$/, "Couldn't connect to ComfyUI ($1)"],
  [/^ComfyUI가 워크플로를 거절했어요: (.*)$/, "ComfyUI rejected the workflow: $1"],
  [/^(?:사용자 )?영상 AI 워크플로(?: 파일)?가 없어요: (.*)$/, "Video AI workflow file not found: $1"],
  [/^H3 이미지→영상 모델\((.*)\)이 이 ComfyUI의 models 폴더에 없어요$/, "The H3 image-to-video model ($1) is not in this ComfyUI's models folder"],
];

const HANGUL = /[가-힣]/;

function trKey(k) {
  if (EN[k] != null) return EN[k];
  for (const [re, rep] of EN_RULES) if (re.test(k)) return k.replace(re, rep);
  return null;
}

function tr(s) {
  const k = s.trim();
  if (!k || !HANGUL.test(k)) return s;
  let out = trKey(k);
  if (out == null && k.includes(" · ")) {                    // "8방향 · 45° · HD"처럼 이어 붙인 문구는 조각마다
    const parts = k.split(" · ");
    const done = parts.map(p => trKey(p.trim()) ?? p);
    if (done.some((p, i) => p !== parts[i])) out = done.join(" · ");
  }
  return out == null ? s : s.replace(k, out);
}

const ATTRS = ["placeholder", "title", "aria-label", "alt"];

function translateNode(n) {
  if (n.nodeType === Node.TEXT_NODE) {
    const v = tr(n.nodeValue);
    if (v !== n.nodeValue) n.nodeValue = v;
    return;
  }
  if (n.nodeType === Node.ELEMENT_NODE) {
    if (n.tagName === "SCRIPT" || n.tagName === "STYLE") return;
    for (const a of ATTRS) {
      const v = n.getAttribute(a);
      if (v) { const t = tr(v); if (t !== v) n.setAttribute(a, t); }
    }
    if (n.tagName === "TEMPLATE") translateNode(n.content);
  }
  if (n.childNodes) for (const c of [...n.childNodes]) translateNode(c);
}

function setupLanguage() {
  const btn = document.getElementById("btn-lang");
  if (btn) {
    btn.textContent = LANG === "en" ? "한국어" : "EN";
    btn.title = LANG === "en" ? "한국어로 보기" : "View in English";
    btn.addEventListener("click", () => {
      try { localStorage.setItem("lang", LANG === "en" ? "ko" : "en"); } catch { /* 무시 */ }
      location.reload();
    });
  }
  if (LANG !== "en") return;
  document.documentElement.lang = "en";
  translateNode(document.body);
  new MutationObserver(muts => {
    for (const m of muts) {
      if (m.type === "characterData") translateNode(m.target);
      else if (m.type === "attributes") {
        const v = m.target.getAttribute(m.attributeName);
        if (v) { const t = tr(v); if (t !== v) m.target.setAttribute(m.attributeName, t); }
      } else m.addedNodes.forEach(translateNode);
    }
  }).observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRS });
}

setupLanguage();
