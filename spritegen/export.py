"""다 만든 동작을 게임 엔진에서 바로 쓰는 형식으로 내보낸다 (ZIP에 넣을 {경로: bytes}를 만든다).

- Aseprite JSON: Phaser(load.aseprite + anims.createFromAseprite), PixiJS(animations), 엔진별 Aseprite·TexturePacker
  임포터가 읽는 형식. 방향마다 frameTags 하나, 프레임 이름은 Phaser가 찾는 "0", "1", … 순서 번호.
- Godot 4: SpriteFrames(.tres)와 AnimatedSprite2D 장면(.tscn). 발 위치(pivot)가 노드 원점에 오게 offset을 넣는다.
- 방향별 프레임 PNG: Unity·언리얼·GameMaker 등 어디든 끌어다 쓴다.
"""
import io
import json
import re
from pathlib import Path

from PIL import Image

RES_NAMES = {"hd": "HD", "px": "픽셀"}


GAME_KEYS = ("frame_ms", "hit_frame", "hit_frames", "hold_last", "move_speed", "velocity", "ground_y", "layers")


def game_fields(meta):
    """시트 JSON의 게임용 정보만 (타격 칸, 끝에서 멈춤, 이동 속도, 층 시트)."""
    return {k: meta[k] for k in GAME_KEYS if k in meta}


def load_meta(out_dir, res):
    p = Path(out_dir) / f"sheet_{res}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


KO_KEYS = {"대기": "idle", "걷기": "walk", "걷": "walk", "달리기": "run", "뛰": "run", "공격": "attack", "피격": "hit",
           "쓰러": "death", "죽": "death", "점프": "jump", "춤": "dance", "문워크": "dance", "베기": "slash", "마법": "magic",
           "방어": "guard", "구르기": "roll", "앉": "sit", "인사": "wave"}


def motion_key(m, used=None):
    """파일·애니메이션 이름: 모션 세트는 정해 둔 영어 이름(walk 등), 흔한 한국어 동작 이름은 영어로, 영문 이름은 그대로,
    나머지는 motion. 게임 코드에서 쓰기 좋게 영문 소문자로만 만든다."""
    name = m.get("name") or ""
    key = m.get("key") or next((en for ko, en in KO_KEYS.items() if ko in name), None) \
        or re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if not re.fullmatch(r"[a-z][a-z0-9_]*", key or ""):
        key = "motion"
    if used is not None:                               # 같은 이름이 또 나오면 walk2, walk3 …
        base, n = key, 2
        while key in used:
            key, n = f"{base}{n}", n + 1
        used.add(key)
    return key


def aseprite_json(meta, image_name):
    """시트 JSON → Aseprite 형식(frames 해시 + meta.frameTags). PixiJS용 animations도 같이 넣는다."""
    fw, fh = meta["frame_w"], meta["frame_h"]
    piv = {"x": round(meta["pivot"][0] / fw, 4), "y": round(meta["pivot"][1] / fh, 4)}
    dur = round(1000 / meta["fps"])
    frames, tags, anims, i = {}, [], {}, 0
    for d in meta["order"]:
        start = i
        anims[d] = []
        for r in meta["directions"][d]:
            frames[str(i)] = {"frame": {"x": r["x"], "y": r["y"], "w": r["w"], "h": r["h"]}, "rotated": False,
                              "trimmed": False, "spriteSourceSize": {"x": 0, "y": 0, "w": r["w"], "h": r["h"]},
                              "sourceSize": {"w": r["w"], "h": r["h"]}, "duration": dur, "pivot": piv, "anchor": piv}
            anims[d].append(str(i))
            i += 1
        tag = {"name": d, "from": start, "to": i - 1, "direction": "forward"}
        if not meta["loop"]:
            tag["repeat"] = "1"                        # 한 번 하는 동작 (Aseprite 1.3 형식)
        tags.append(tag)
    width = max(r["x"] + r["w"] for rs in meta["directions"].values() for r in rs)
    height = max(r["y"] + r["h"] for rs in meta["directions"].values() for r in rs)
    return {"frames": frames, "animations": anims,
            "meta": {"app": "38Sprite (https://github.com/cobono-art/38sprite)", "version": "1.0", "image": image_name,
                     "format": "RGBA8888", "size": {"w": width, "h": height}, "scale": "1", "frameTags": tags,
                     "loop": meta["loop"], "fps": meta["fps"], "pivot": meta["pivot"], **game_fields(meta)}}


def godot_value(v):
    """파이썬 값 → Godot 리소스 텍스트 값 (Dictionary·Array·숫자·문자열·bool)."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return f"{v:g}" if isinstance(v, float) else str(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, dict):
        return "{" + ", ".join(f"{json.dumps(str(k), ensure_ascii=False)}: {godot_value(x)}" for k, x in v.items()) + "}"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(godot_value(x) for x in v) + "]"
    return "null"


def godot_tres(entries, margins=None):
    """entries: [(애니메이션 이름 앞부분 또는 "", 시트 JSON, 이미지 경로(.tres 기준 상대 경로))] → SpriteFrames 텍스트.
    앞부분이 있으면 애니메이션 이름은 '앞부분_방향'(예: walk_S), 없으면 방향 이름(S, SE …).
    margins: 동작마다 (왼쪽, 위, 늘릴 너비, 늘릴 높이) — 여러 동작의 칸 크기·발 위치를 하나로 맞출 때."""
    ext, subs, anims = [], [], []
    for k, (prefix, meta, image) in enumerate(entries):
        tex = f"{k + 1}_tex"
        ext.append(f'[ext_resource type="Texture2D" path="{image}" id="{tex}"]')
        margin = f"\nmargin = Rect2({', '.join(f'{v:g}' for v in margins[k])})" if margins else ""
        for d in meta["order"]:
            frames = []
            for i, r in enumerate(meta["directions"][d]):
                sid = f"AtlasTexture_{k}_{d}_{i}"
                subs.append(f'[sub_resource type="AtlasTexture" id="{sid}"]\natlas = ExtResource("{tex}")\n'
                            f'region = Rect2({r["x"]}, {r["y"]}, {r["w"]}, {r["h"]}){margin}')
                frames.append(f'{{"duration": 1.0, "texture": SubResource("{sid}")}}')
            name = f"{prefix}_{d}" if prefix else d
            anims.append(f'{{"frames": [{", ".join(frames)}], "loop": {str(meta["loop"]).lower()}, '
                         f'"name": &"{name}", "speed": {float(meta["fps"])}}}')
    head = f'[gd_resource type="SpriteFrames" load_steps={len(ext) + len(subs) + 1} format=3]'
    res = "[resource]\nanimations = [" + ", ".join(anims) + "]"
    # 게임용 정보(타격 칸·이동 속도 등): 게임 코드에서 sprite_frames.get_meta("sprite_info")
    info = {prefix: {k: v for k, v in game_fields(meta).items() if k != "layers"} for prefix, meta, _ in entries}
    info = info.get("", info) if len(entries) == 1 else {k: v for k, v in info.items() if v}
    if info:
        res += f"\nmetadata/sprite_info = {godot_value(info)}"
    return "\n\n".join([head, *ext, *subs, res]) + "\n"


def godot_tscn(name, tres_file, meta, first_anim, pixel=False):
    """AnimatedSprite2D 장면: offset으로 발 위치를 노드 원점(0, 0)에 맞춘다 (centered 기본값 기준)."""
    dx = meta["frame_w"] / 2 - meta["pivot"][0]
    dy = meta["frame_h"] / 2 - meta["pivot"][1]
    lines = ['[gd_scene load_steps=2 format=3]', "",
             f'[ext_resource type="SpriteFrames" path="{tres_file}" id="1_frames"]', "",
             f'[node name="{name}" type="AnimatedSprite2D"]']
    if pixel:
        lines.append("texture_filter = 1")
    lines += ['sprite_frames = ExtResource("1_frames")', f'animation = &"{first_anim}"', f'autoplay = "{first_anim}"',
              f"offset = Vector2({dx:.1f}, {dy:.1f})"]
    return "\n".join(lines) + "\n"


def frame_pngs(out_dir, meta, res):
    """방향별 프레임 PNG: frames/<해상도>/<방향>/<방향>_00.png"""
    sheet = Image.open(Path(out_dir) / meta["image"]).convert("RGBA")
    files = {}
    for d in meta["order"]:
        for i, r in enumerate(meta["directions"][d]):
            buf = io.BytesIO()
            sheet.crop((r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"])).save(buf, "PNG")
            files[f"frames/{res}/{d}/{d}_{i:02d}.png"] = buf.getvalue()
    return files


def usage_text(key, metas):
    meta = metas.get("hd") or next(iter(metas.values()))
    fw, fh = meta["frame_w"], meta["frame_h"]
    px, py = meta["pivot"]
    return f"""38Sprite 엔진용 파일 ({key})  /  Engine files

발 기준점(pivot): 칸 왼쪽 위에서 ({px}, {py}) px · 칸 크기 {fw}x{fh} · 재생 {meta['fps']} fps · 반복 {meta['loop']}
비율로: x {px / fw:.4f}, y {py / fh:.4f} (위에서부터) / Unity는 y {1 - py / fh:.4f} (아래에서부터)

[Phaser 3]
  this.load.aseprite('{key}', 'sheet_hd.png', '{key}_aseprite.json');
  this.anims.createFromAseprite('{key}');           // 애니메이션 이름 = 방향: S, SE, E, NE, N, NW, W, SW
  this.add.sprite(x, y).setOrigin({px / fw:.4f}, {py / fh:.4f}).play('S');

[PixiJS 8]
  const sheet = await Assets.load('{key}_aseprite.json');
  const hero = new AnimatedSprite(sheet.animations['S']);   // anchor는 JSON의 pivot을 그대로 씀
  hero.animationSpeed = {meta['fps']} / 60; hero.play();

[Godot 4]
  godot 폴더를 프로젝트에 통째로 넣고 {key}.tscn 을 끌어다 쓰세요 (AnimatedSprite2D, 발이 노드 원점).
  $AnimatedSprite2D.play("SE") 처럼 방향 이름으로 재생합니다.
  Copy the godot folder into your project and instance {key}.tscn (feet at the node origin).

[Unity / 언리얼 / GameMaker 등]
  frames/hd/<방향>/ 의 PNG를 가져와 방향별 애니메이션으로 만드세요. Unity: Sprite Mode Single, Pivot Custom
  ({px / fw:.4f}, {1 - py / fh:.4f}), 여러 장을 한꺼번에 장면에 끌어다 놓으면 애니메이션이 만들어져요.

[원래 형식]
  sheet_hd.json: frame_w, frame_h, fps, pivot, loop, order, directions(방향마다 칸 위치 목록){game_text(meta)}
"""


def game_text(meta):
    """사용법 안내에 넣을 게임 정보 설명 (있는 것만)."""
    lines = []
    if "hit_frame" in meta:
        lines.append(f"  hit_frame: {meta['hit_frame']} — 가장 크게 움직인 칸(0부터, 공격이면 맞는 순간). 방향별은 hit_frames"
                     " / the frame with the biggest movement (attack impact), per direction in hit_frames")
    if meta.get("hold_last"):
        lines.append("  hold_last: true — 끝 칸에서 멈춰 두세요 (쓰러짐 등) / stop on the last frame")
    if "move_speed" in meta:
        lines.append(f"  move_speed: {meta['move_speed']} px/s — 이 속도로 캐릭터를 옮기면 발이 미끄러지지 않아요. 방향별 [x, y]는"
                     f" velocity (y는 화면 아래가 +, 비스듬히 내려다본 땅이라 {meta.get('ground_y', 0.5)}배)"
                     " / move the character at this speed so the feet don't slide; per-direction vectors in velocity")
    if meta.get("layers"):
        lines.append(f"  layers: {', '.join(meta['layers'].values())} — 캐릭터만 있는 층과 빛 효과만 있는 층 (같은 배치)."
                     " 빛 층을 더하기(Add) 블렌드로 겹치면 더 밝게 빛나요 / character-only and effects-only sheets")
    return ("\n\n[게임용 정보 / game info]\n" + "\n".join(lines)) if lines else ""


def engine_files(out_dir, key):
    """동작 하나의 엔진용 파일들 {ZIP 안 경로: bytes}."""
    files, metas = {}, {}
    for res in ("hd", "px"):
        meta = load_meta(out_dir, res)
        if not meta:
            continue
        metas[res] = meta
        tag = "" if res == "hd" else "_px"
        files[f"{key}{tag}_aseprite.json"] = json.dumps(aseprite_json(meta, meta["image"]), ensure_ascii=False,
                                                         indent=1).encode("utf-8")
        files[f"godot/{meta['image']}"] = (Path(out_dir) / meta["image"]).read_bytes()
        files[f"godot/{key}{tag}.tres"] = godot_tres([("", meta, meta["image"])]).encode("utf-8")
        files[f"godot/{key}{tag}.tscn"] = godot_tscn(f"{key}{tag}", f"{key}{tag}.tres", meta, meta["order"][0],
                                                     pixel=res == "px").encode("utf-8")
        files.update(frame_pngs(out_dir, meta, res))
    if metas:
        files["엔진에서_쓰는_법.txt"] = usage_text(key, metas).encode("utf-8")
    return files


def project_godot(motions):
    """여러 동작을 Godot SpriteFrames 하나로: motions = [(key, out_dir)] → {경로: bytes} (godot_all/ 아래).
    동작마다 칸 크기와 발 위치가 달라서, AtlasTexture margin으로 모든 칸을 같은 크기·같은 발 위치로 맞춘다
    (그래야 AnimatedSprite2D 하나에서 동작을 바꿔도 캐릭터가 튀지 않는다)."""
    files, entries = {}, []
    for key, out_dir in motions:
        meta = load_meta(out_dir, "hd")
        if not meta:
            continue
        image = f"{key}_hd.png"
        files[f"godot_all/{image}"] = (Path(out_dir) / meta["image"]).read_bytes()
        entries.append((key, meta, image))
    if not entries:
        return {}
    left = max(m["pivot"][0] for _, m, _ in entries)
    right = max(m["frame_w"] - m["pivot"][0] for _, m, _ in entries)
    top = max(m["pivot"][1] for _, m, _ in entries)
    bottom = max(m["frame_h"] - m["pivot"][1] for _, m, _ in entries)
    W, H = round(left + right), round(top + bottom)
    margins = [(round(left - m["pivot"][0]), round(top - m["pivot"][1]),
                W - m["frame_w"], H - m["frame_h"]) for _, m, _ in entries]
    files["godot_all/character.tres"] = godot_tres(entries, margins).encode("utf-8")
    common = {"frame_w": W, "frame_h": H, "pivot": [round(left), round(top)]}
    files["godot_all/character.tscn"] = godot_tscn("character", "character.tres", common,
                                                   f"{entries[0][0]}_{entries[0][1]['order'][0]}").encode("utf-8")
    return files
