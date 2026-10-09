"""Codex(방향 그림)와 H3(동작 영상)에 넣을 프롬프트."""
from .directions import CELL_TEXT, FACING, LAYOUT

ANGLE_PRESETS = [
    {"id": "eye", "label": "정면 눈높이", "deg": 0},
    {"id": "q30", "label": "쿼터뷰 30°", "deg": 30},
    {"id": "high", "label": "높은 쿼터뷰 45°", "deg": 45},
    {"id": "top", "label": "탑다운 60°", "deg": 60},
]
# 방향 그림 배경: 마젠타 크로마키 (영상과 같은 색). 2026-10-09 시험: 연회색(#B8B8B8)은 지팡이 테두리에 회색 잔테두리가
# 남고 팔·지팡이와 몸 사이 틈의 회색이 캐릭터로 남았는데(은색 갑옷처럼 회색 캐릭터는 더 헷갈림), 마젠타는 도트·HD 모두
# 테두리·틈이 깨끗했고 캐릭터 색에 분홍 기도 묻지 않았다.
SHEET_BG = "#FF00FF"
SHEET_BG_TEXT = f"pure magenta ({SHEET_BG}) chroma-key background (the magenta is only the background; the character keeps its own colors)"


def camera_text(deg):
    deg = int(round(deg))
    if deg <= 5:
        return "a fixed eye-level camera (straight horizontal view, not looking down)"
    if deg < 25:
        return f"a fixed camera slightly above the character, looking down at about {deg} degrees"
    if deg < 55:
        return (f"a fixed high-angle camera looking down at the character from about {deg} degrees above, "
                "like the classic high quarter-view camera of isometric-style MMORPGs")
    return (f"a fixed top-down camera looking down at the character from about {deg} degrees above, "
            "so the top of the head and the shoulders dominate the view")


def style_text(style, pixel_height):
    if style == "pixel":
        return (f"TRUE PIXEL ART game sprite: each character is about {pixel_height} pixel-art pixels tall; every "
                "pixel-art pixel is a crisp square block of exactly the same size across the whole image, aligned to "
                "one grid; no anti-aliasing, no gradients, no blur, no soft edges; a limited palette of about 24 colors; "
                "a clean 1-pixel dark outline around each character; simple cel shading with 2 to 3 shades per material")
    return "the same clean 2D game illustration style as the reference, with cel shading and clear dark outlines"


def sheet_prompt(dirs, deg, style="hd", pixel_height=64, pose=None):
    """방향 시트: 나침반 배치 3x3에 필요한 방향만 그리고 나머지 칸은 비운다."""
    rows = []
    for name, row in zip(("Top row", "Middle row", "Bottom row"), LAYOUT):
        cells = [CELL_TEXT[d] if d in dirs else "EMPTY cell, nothing in it" for d in row]
        rows.append(f"- {name}: " + " | ".join(cells))
    pose_text = pose or "the same relaxed standing pose in every view (arms slightly away from the body, feet slightly apart)"
    return (
        "$imagegen Using the attached character image as the exact reference (same face, hair, outfit, colors and "
        f"proportions), create ONE character direction sheet for a 2D game sprite, drawn from {camera_text(deg)}. "
        "Use exactly the same camera angle and the same scale in every view.\n\n"
        f"Arrange the views in a 3x3 grid on a completely flat, uniform {SHEET_BG_TEXT}:\n"
        + "\n".join(rows) + "\n\n"
        f"Pose: {pose_text}. It must be one identical 3D pose seen from different directions: items held in the right "
        "hand stay in the right hand in every view (left side of the image in front views, right side in back views).\n"
        "Each character is centered in its own cell with the full body visible and empty margin around it, no overlap "
        "between cells, feet on a common baseline within each row.\n"
        f"Style: {style_text(style, pixel_height)}.\n"
        "No text, no labels, no grid lines, no borders, no floor, no shadows, no effects. Square image, 1024x1024.\n"
        "Only generate the image with the image tool; do not try to save, copy, move or list any files."
    )


VIEW = {
    "S": "the front view: the character faces straight toward the camera",
    "SE": "the front three-quarter view: the character faces toward the lower-right of the image, toward the camera, so "
          "we see the face and the front of the body turned to the right",
    "E": "the side view: the character faces exactly toward the right edge of the image, in profile",
    "NE": "the back three-quarter view: the character faces toward the upper-right of the image, AWAY from the camera, so "
          "we see the back of the head, the back and a little of the right side; the face is NOT visible",
    "N": "the back view: the character faces straight away from the camera toward the top of the image; we see the back "
         "of the head and the back; the face is NOT visible",
    "NW": "the back three-quarter view: the character faces toward the upper-left of the image, AWAY from the camera, so "
          "we see the back of the head, the back and a little of the left side; the face is NOT visible",
    "W": "the side view: the character faces exactly toward the left edge of the image, in profile",
    "SW": "the front three-quarter view: the character faces toward the lower-left of the image, toward the camera, so "
          "we see the face and the front of the body turned to the left",
}


def redraw_prompt(d, deg, style="hd", pixel_height=64):
    """방향 그림에서 한 칸만 다시 그릴 때: 그 방향 하나만 같은 캐릭터·같은 카메라로."""
    return ("$imagegen The reference images show one character: an eight-direction sheet (3x3 grid; top row = back "
            "views, bottom row = front views) and a turnaround. Draw ONE single full-body view of this exact same "
            f"character in {VIEW[d]}. Use {camera_text(deg)}, exactly like the sheet, and the same pose as the other views "
            "in the sheet (items held in the right hand stay in the right hand). Same face, hair, outfit, colors and "
            f"proportions. Style: {style_text(style, pixel_height)}. Plain flat {SHEET_BG_TEXT}, no "
            "floor, no shadow, no text. Only generate the image with the image tool; do not try to save, copy, move or "
            "list any files.")


# 영상 프롬프트는 원하는 상태만 긍정형으로 적는다. H3 공식 프롬프트 안내: "원하지 않는 것을 이름으로 적으면 그 낱말이
# 내용으로 읽힌다" (H3는 CFG 증류라 네거티브도 없다). 2026-10-08 마네킹 공격 시험: "no slash trails, no glow ..."를 빼자
# 같은 시드에서 큰 칼 궤적이 사라지고(효과량 895k → 184~432k) 휘두르는 동작은 그대로였다.
CAMERA = "Locked-off static camera that stays perfectly still at the same angle and framing for the whole video. "
# 배경은 처음부터 끝까지 마젠타 한 색: 영상 AI가 효과 장면에서 배경을 다른 색으로 바꾸거나 무늬를 그리면 크로마키로
# 깨끗하게 오릴 수 없다. 바뀔지는 시드가 정해서(2026-10-08 실험) 받자마자 검사해 새 시드로 다시 만든다(bg_retry).
# 첫 장면이 마젠타여도 이 문장은 필요하다 — 2026-10-09 같은 시드 5개씩, 문장을 빼면 배경이 파랑·청록으로 바뀐 장면이
# 걷기 3 → 46장, 마법 18 → 64장(각 125장 중)으로 늘었다.
BG_MAGENTA = ("The background is one flat, uniform, solid magenta (#FF00FF) chroma-key color in every single frame, from "
              "the first frame to the last, the same pure magenta from edge to edge. ")
BG_GRAY = "The plain flat gray studio background stays exactly the same in every frame. "
LIGHT = ("The character is lit by soft neutral white light that keeps its original colors. Keep the exact character "
         "design, colors and art style. ")
COMMON_TAIL = CAMERA + BG_MAGENTA + LIGHT + "Audio: quiet."
FX_TAIL = (CAMERA + BG_MAGENTA + LIGHT + "Make the magical visual effects of the motion vivid and sparkling (stars, "
           "sparkles, glowing light trails, light bursts) in gold, white, cyan and blue. The effects float above the "
           "pure magenta background. Audio: magical chimes.")

# 이런 말이 들어간 동작은 빛 효과를 살려서 그리고, 나머지는 효과 없이 그린다.
# ('지우기'는 흰 옷·금발처럼 밝은 캐릭터에 구멍을 낼 수 있어서 기본으로 쓰지 않는다)
EFFECT_WORDS = ("마법", "주문", "시전", "마나", "불꽃", "화염", "불덩이", "번개", "전기", "얼음", "냉기", "광선", "레이저",
                "검기", "오라", "폭발", "충격파", "치유", "회복", "소환", "버프", "이펙트", "파티클", "반짝", "빛",
                "magic", "spell", "cast", "fire", "flame", "lightning", "thunder", "frost", "beam", "laser", "aura",
                "explosion", "heal", "summon", "glow", "sparkle", "effect")


def auto_effects(text):
    """동작 설명으로 빛 효과 방식을 고른다: vivid(화려하게 살림) | none(효과 없이)."""
    t = (text or "").lower()
    return "vivid" if any(w in t for w in EFFECT_WORDS) else "none"


def tail(effects=False, gray=False):
    """효과를 살릴 동작(effects=True)은 반짝이·빛을 화려하게, 아니면 효과 없이.
    gray: 첫 프레임이 회색 배경일 때 (예전 마네킹 모드) 배경 설명도 회색으로."""
    t = FX_TAIL if effects else COMMON_TAIL
    return t.replace(BG_MAGENTA, BG_GRAY) if gray else t


def motion_prompt(kind, motion, deg, d, style="hd", effects=False, hold_end=False):
    """텍스트 동작 설명 → H3 이미지→영상 프롬프트. motion은 한국어여도 된다 (H3 텍스트 인코더가 다국어).
    hold_end: 처음 자세로 돌아오지 않고 마지막 자세로 끝나는 동작 (쓰러짐 등)."""
    facing = FACING[d]
    pixel = " Keep the crisp, sharp pixel-art look with large square pixels." if style == "pixel" else ""
    if kind == "loop":
        body = (f"The character from <Picture 1> performs this motion in place, facing {facing}, as a steady, "
                f"seamless loop: {motion}. The character keeps facing {facing} for the whole clip, never turns, and "
                "stays on the same spot at the same size without moving across the frame.")
    elif hold_end:
        body = (f"The character from <Picture 1> starts in exactly this pose, facing {facing}, and performs this "
                f"action ONCE: {motion}. The character does NOT return to the starting pose: it stays completely still "
                f"in the final pose until the end of the clip. The character keeps facing {facing} and stays on the "
                "same spot.")
    else:
        body = (f"The character from <Picture 1> starts in exactly this pose, facing {facing}, and performs this "
                f"action ONCE: {motion}. Then the character returns to the same starting pose and stays still until "
                f"the end. The character keeps facing {facing} the whole time and does not move across the frame.")
    return f"2D game sprite animation, seen from {camera_text(deg)}. {body}{pixel} {tail(effects)}"


def reference_prompt(kind, deg, d, hint="", style="hd", effects=False):
    """레퍼런스 영상 → H3 레퍼런스 투 비디오 프롬프트."""
    facing = FACING[d]
    extra = f" Motion notes: {hint}." if hint else ""
    pixel = " Keep the crisp, sharp pixel-art look with large square pixels." if style == "pixel" else ""
    loop = ("as a steady, seamless loop" if kind == "loop"
            else "once, starting and ending in the character's pose from <Picture 1>")
    return (f"2D game sprite animation, seen from {camera_text(deg)}. The character from <Picture 1> performs exactly "
            f"the same motion as the person in <Video 1>, with the same timing and body mechanics, {loop}. The "
            f"character faces {facing} the whole time, stays in place on the same spot at the same size, and does not "
            f"move across the frame. Only the motion comes from <Video 1>; the look, outfit and proportions come from "
            f"<Picture 1>.{extra}{pixel} {tail(effects)}")


def follow_prompt(kind, deg, d, hint="", style="hd", effects=False):
    """마스터 방향 영상 → 다른 방향: 같은 캐릭터가 같은 동작을 같은 박자·같은 손으로, 방향만 바꿔서."""
    facing = FACING[d]
    extra = f" The motion is: {hint}." if hint else ""
    pixel = " Keep the crisp, sharp pixel-art look with large square pixels." if style == "pixel" else ""
    ending = ("as a steady, seamless loop" if kind == "loop"
              else "starting and ending in the pose from <Picture 1>")
    return (f"2D game sprite animation, seen from {camera_text(deg)}. The character from <Picture 1> performs exactly "
            f"the same motion as the character in <Video 1>: the same timing, the same body mechanics and the same "
            f"hand use (whatever is held stays in the same hand), {ending}. The only difference is the facing: here "
            f"the character faces {facing} the whole time, stays in place on the same spot at the same size, and does "
            f"not move across the frame.{extra}{pixel} {tail(effects)}")


def mannequin_prompt(deg, d, hint="", style="hd", effects=False, gray=False):
    """3D 마네킹 레퍼런스(그 방향에서 본 영상) → 캐릭터를 입힌 영상. 첫 프레임과 마네킹 영상은 같은 배경색이어야 한다
    (다르면 둘을 섞은 얼룩무늬 배경이 나온다). 기본은 둘 다 마젠타, gray면 예전처럼 둘 다 회색."""
    facing = FACING[d]
    extra = f" The motion is: {hint}." if hint else ""
    pixel = " Keep the crisp, sharp pixel-art look with large square pixels." if style == "pixel" else ""
    # 마네킹은 무기를 들지 않는다(그리면 지팡이가 칼로 바뀜). 그래서 '빈손은 비워 둬'라고 하면 캐릭터 무기까지 치우게 된다
    # → 든 물건은 첫 프레임 그대로 같은 손에, 그 손과 함께 움직인다고만 적는다.
    return (f"2D game sprite animation, seen from {camera_text(deg)}. The character from <Picture 1> performs exactly "
            f"the same motion as the mannequin in <Video 1>: the same body pose at every moment, the same timing, "
            f"the same facing and the same camera angle. The character faces {facing}. The character keeps holding "
            f"whatever it holds in <Picture 1> in the same hand, and the held item moves together with that hand. The "
            f"character stays on the same spot at the same size. Only the motion comes from <Video 1>; the look, "
            f"outfit, proportions and art style come from <Picture 1>.{extra}{pixel} {tail(effects, gray=gray)}")
