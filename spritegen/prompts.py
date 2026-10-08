"""Codex(방향 그림)와 H3(동작 영상)에 넣을 프롬프트."""
from .directions import CELL_TEXT, FACING, LAYOUT

ANGLE_PRESETS = [
    {"id": "eye", "label": "정면 눈높이", "deg": 0},
    {"id": "q30", "label": "쿼터뷰 30°", "deg": 30},
    {"id": "high", "label": "높은 쿼터뷰 45°", "deg": 45},
    {"id": "top", "label": "탑다운 60°", "deg": 60},
]
SHEET_BG = "#B8B8B8"


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
        f"Arrange the views in a 3x3 grid on a completely flat, uniform light gray ({SHEET_BG}) background:\n"
        + "\n".join(rows) + "\n\n"
        f"Pose: {pose_text}. It must be one identical 3D pose seen from different directions: items held in the right "
        "hand stay in the right hand in every view (left side of the image in front views, right side in back views).\n"
        "Each character is centered in its own cell with the full body visible and empty margin around it, no overlap "
        "between cells, feet on a common baseline within each row.\n"
        f"Style: {style_text(style, pixel_height)}.\n"
        "No text, no labels, no grid lines, no borders, no floor, no shadows, no effects. Square image, 1024x1024.\n"
        "Only generate the image with the image tool; do not try to save, copy, move or list any files."
    )


COMMON_TAIL = (
    "Locked-off static camera at the same angle: no zoom, no pan, no rotation, no camera shake. The flat, uniform "
    "solid magenta (#FF00FF) chroma-key background stays completely unchanged, with no floor and no shadows; the "
    "character is lit by neutral white light, with no pink or magenta light on the character. Keep the exact character design, "
    "colors and art style. No motion-blur trails, no visual effects, no text. Audio: quiet."
)
FX_TAIL = (
    "Locked-off static camera at the same angle: no zoom, no pan, no rotation, no camera shake. The flat, uniform "
    "solid magenta (#FF00FF) chroma-key background stays completely unchanged, with no floor and no shadows; the "
    "character is lit by neutral white light, with no pink or magenta light on the character. Keep the exact character design, "
    "colors and art style. Make the magical visual effects of the motion vivid and sparkling (stars, sparkles, glowing "
    "light trails, light bursts) in gold, white, cyan and blue only, never pink, magenta or purple. No text. "
    "Audio: magical chimes."
)
NO_FX = " No visual effects: no slash trails, no light arcs, no glow, no particles."


def tail(effects=False, gray=False):
    """효과를 살릴 동작(effects=True)은 반짝이·빛을 화려하게, 아니면 효과 없이.
    gray: 첫 프레임이 회색 배경일 때 (마네킹 모드) 배경 설명도 회색으로."""
    t = FX_TAIL if effects else COMMON_TAIL
    return t.replace("solid magenta (#FF00FF) chroma-key background", "plain flat gray studio background") if gray else t


def motion_prompt(kind, motion, deg, d, style="hd", effects=False):
    """텍스트 동작 설명 → H3 이미지→영상 프롬프트. motion은 한국어여도 된다 (H3 텍스트 인코더가 다국어)."""
    facing = FACING[d]
    pixel = " Keep the crisp pixel-art look with large square pixels and no blur." if style == "pixel" else ""
    if kind == "loop":
        body = (f"The character from <Picture 1> performs this motion in place, facing {facing}, as a steady, "
                f"seamless loop: {motion}. The character keeps facing {facing} for the whole clip, never turns, and "
                "stays on the same spot at the same size without moving across the frame.")
    else:
        body = (f"The character from <Picture 1> starts in exactly this pose, facing {facing}, and performs this "
                f"action ONCE: {motion}. Then the character returns to the same starting pose and stays still until "
                f"the end. The character keeps facing {facing} the whole time and does not move across the frame.")
    return f"2D game sprite animation, seen from {camera_text(deg)}. {body}{pixel} {tail(effects)}"


def reference_prompt(kind, deg, d, hint="", style="hd", effects=False):
    """레퍼런스 영상 → H3 레퍼런스 투 비디오 프롬프트."""
    facing = FACING[d]
    extra = f" Motion notes: {hint}." if hint else ""
    pixel = " Keep the crisp pixel-art look with large square pixels and no blur." if style == "pixel" else ""
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
    pixel = " Keep the crisp pixel-art look with large square pixels and no blur." if style == "pixel" else ""
    ending = ("as a steady, seamless loop" if kind == "loop"
              else "starting and ending in the pose from <Picture 1>")
    return (f"2D game sprite animation, seen from {camera_text(deg)}. The character from <Picture 1> performs exactly "
            f"the same motion as the character in <Video 1>: the same timing, the same body mechanics and the same "
            f"hand use (whatever is held stays in the same hand), {ending}. The only difference is the facing: here "
            f"the character faces {facing} the whole time, stays in place on the same spot at the same size, and does "
            f"not move across the frame.{extra}{'' if effects else NO_FX}{pixel} {tail(effects)}")


def mannequin_prompt(deg, d, hint="", style="hd", effects=False):
    """3D 마네킹 레퍼런스(그 방향에서 본 영상) → 캐릭터를 입힌 영상. 첫 프레임·마네킹 모두 회색 배경이다."""
    facing = FACING[d]
    extra = f" The motion is: {hint}." if hint else ""
    pixel = " Keep the crisp pixel-art look with large square pixels and no blur." if style == "pixel" else ""
    return (f"2D game sprite animation, seen from {camera_text(deg)}. The character from <Picture 1> performs exactly "
            f"the same motion as the gray mannequin in <Video 1>: the same body pose at every moment, the same timing, "
            f"the same facing and the same camera angle. The character faces {facing}. Anything the mannequin holds "
            f"stays in the same hand; an empty mannequin hand stays empty. The character stays on the same spot at the "
            f"same size. Only the motion comes from <Video 1>; the look, outfit, proportions and art style come from "
            f"<Picture 1>.{extra}{'' if effects else NO_FX}{pixel} {tail(effects, gray=True)}")
