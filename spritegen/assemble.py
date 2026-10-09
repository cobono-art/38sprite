"""방향별 H3 프레임 → 스프라이트 시트.

반복 동작: 방향마다 루프 한 바퀴를 찾고, 머리가 가장 낮은 순간(두 발 딛는 자세)을 시작으로 맞춘다.
한 번 하는 동작: 첫 자세에서 벗어났다 돌아오는 구간을 잘라, 가장 크게 움직인 순간(타격)이 꼭 들어가게 고른다.
모든 방향을 같은 칸 크기·같은 발 위치로 자르고, 만들지 않은 방향은 반대쪽을 좌우 반전해서 채운다.
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image

from . import qa
from .comfy import FPS
from .directions import SHEET_ORDER, preview_layout, source_of
from .effects import remove_effects
from .imaging import (bbox, bg_pattern, cutout_any, estimate_bg, frame_alpha, find_cycle, load_frames, pixelate, save_gif,
                      thumbnails)


def pick_loop(frames, alphas, n, prange=None):
    """prange: (최소, 최대) 한 바퀴 길이 — 모든 방향이 같은 걸음 수를 쓰게 정해 둔 범위(common_cycle). 없으면 이 방향만 보고 찾는다."""
    th = thumbnails(frames, alphas)
    doubled = False
    if prange:
        period, start, seam, scores = find_cycle(th, *prange)
    else:
        period, start, seam, scores = find_cycle(th, 14, 60)
        # 망토·치마로 다리가 가려지면 한 걸음이 한 바퀴처럼 보인다. 두 배 간격(두 걸음)이 확실히 더 잘 맞으면
        # 그쪽이 진짜 한 바퀴다 (그대로 두면 같은 발로만 걷는다).
        near = [k for k in range(2 * period - 2, 2 * period + 3) if k in scores]
        if near and min(scores[k] for k in near) < 0.95 * scores[period]:
            period, start, seam, _ = find_cycle(th, 2 * period - 2, 2 * period + 2)
            doubled = True
    head_y = [bbox(alphas[i])[1] for i in range(start, start + period)]
    phase = int(np.argmax(head_y))
    n = min(n, period)
    picks = [start + (phase + round(i * period / n)) % period for i in range(n)]
    return picks, n * FPS / period, {"period_frames": period, "period_sec": round(period / FPS, 2),
                                     "loop_start": start, "phase_offset": phase, "seam_error": round(seam, 4),
                                     "half_step_fixed": doubled}


def cycle_scores(frames_dir):
    """한 방향 영상의 반복 점수 곡선 {간격: 프레임 t와 t+간격의 차이} (작을수록 그 간격으로 되풀이된다)."""
    frames = load_frames(frames_dir)
    alphas = [frame_alpha(f, estimate_bg(f)) for f in frames]
    return find_cycle(thumbnails(frames, alphas), 8, 60)[3]


def common_cycle(all_scores, lo=10, hi=40, good=1.8):
    """모든 방향이 '한 바퀴(두 걸음)'를 반복하게 공통 한 바퀴 길이를 정한다 → (길이, {방향: 그 방향의 한 바퀴 길이 또는 None}).
    방향마다 따로 고르면 이음새가 조금 더 매끄러운 쪽을 따라 어떤 방향은 한 바퀴, 어떤 방향은 두 바퀴를 골랐다
    (2026-10-09 걷기: S 17·E 24·N 48프레임). 시트는 방향마다 같은 장수를 같은 속도로 틀어서, 게임에서 방향을 틀면
    걸음이 두 배로 빨라졌다.
    1) 방향마다 가장 잘 맞는 간격을 1·2·3으로 나눈 값 중, 그 근처에 잘 맞는 골(가장 좋은 것의 good배 이내)이 있는 것만
       후보로 해서 모든 방향이 가장 비슷해지는 한 바퀴 길이 C를 고른다(같으면 큰 쪽 — 한 바퀴를 반으로 쪼개지 않게).
    2) 방향마다 C에 가장 가까운 골(1.6배 안, 멀수록·덜 맞을수록 손해)을 쓴다. 없으면 그 방향은 예전처럼 따로 고른다.
       영상 AI가 방향마다 걷는 빠르기가 달라서(위 예: S가 E보다 30% 빠름) 방향별 길이는 다르다.
    3) 망토로 다리가 가려져 한 걸음이 한 바퀴처럼 보였으면, 대부분 방향에서 두 배 간격이 확실히(0.75배 미만) 더 잘 맞는다
       → 두 배를 한 바퀴로. 걸음이 조금 고르지 않으면 두 바퀴가 원래 조금 더 잘 맞아서 기준을 엄하게 했다.
    시험한 영상 5개(도트 걷기 640·480, 걷기 둘, 달리기)에서 모든 방향이 한 바퀴씩. 해 본 것: 잘 맞는 골만 고르면 '모두
    두 바퀴'도 서로 맞아서 그쪽으로 쏠렸고(8장에 두 바퀴면 한 걸음 2장), 흐릿한 골(반 바퀴 자리)까지 인정하면 반 바퀴가 골라졌다."""
    vs = {}
    for d, sc in all_scores.items():
        ps = sorted(sc)
        best = min(sc.values())
        vs[d] = [(p, sc[p] / best) for i, p in enumerate(ps[1:-1], 1)
                 if sc[p] <= sc[ps[i - 1]] and sc[p] <= sc[ps[i + 1]]]
    best = {d: min(sc, key=sc.get) for d, sc in all_scores.items()}

    def fund_cost(d, c):                                  # 나눈 값 중 c에 가까운 것까지의 거리 (그 근처에 잘 맞는 골이 없으면 손해)
        def cost(f):
            has = any(0.8 * f <= p <= 1.25 * f and rel <= good for p, rel in vs[d])
            return abs(np.log(f / c)) + (0 if has else 0.5)
        return min(cost(best[d] / k) for k in (1, 2, 3) if best[d] / k >= 0.7 * lo)

    def near(d, t):                                       # t 근처(1.6배 안) 골 중 가깝고 잘 맞는 것 (상대 점수, 간격)
        cand = [(abs(np.log(p / t)) + 0.3 * (rel - 1), rel, p) for p, rel in vs[d]
                if abs(np.log(p / t)) <= np.log(1.6) and rel <= 3]
        return min(cand)[1:] if cand else (None, None)
    costs = {c: sum(fund_cost(d, c) for d in best) for c in np.arange(lo, hi + 0.01, 0.5)}
    floor = min(costs.values())
    c = max(k for k, v in costs.items() if v <= floor + 0.01 * len(best))
    picked = {d: near(d, c) for d in best}
    doubled = {d: near(d, 2 * c) for d in best}
    twice = [d for d in best if picked[d][0] and doubled[d][0] and doubled[d][0] < 0.75 * picked[d][0]]
    if len(twice) > len(best) / 2:
        c, picked = 2 * c, doubled
    return float(c), {d: v[1] for d, v in picked.items()}


def motion_signal(alphas):
    """방향이 달라도 비슷하게 움직이는 신호: 실루엣 위쪽 30%에 든 양(팔을 머리 위로 드는 정도)과 실루엣 넓이.
    (실루엣 너비는 옆모습에서 팔을 벌려도 거의 안 변해서 쓰지 않는다)"""
    upper, area = [], []
    for a in alphas:
        x0, y0, x1, y1 = bbox(a)
        solid = a > 0.5
        upper.append(float(solid[int(y0):int(y0 + (y1 - y0) * 0.3)].sum()))
        area.append(float(solid.sum()))
    sig = np.stack([np.asarray(upper), np.asarray(area)], axis=1)
    return (sig - sig.mean(axis=0)) / (sig.std(axis=0) + 1e-6)


def best_lag(sig, ref, max_lag=10):
    """sig가 ref보다 몇 프레임 늦은지 (상관이 가장 큰 어긋남)."""
    n = min(len(sig), len(ref))
    best, lag_best = -1e9, 0
    for lag in range(-max_lag, max_lag + 1):
        a = ref[max(0, -lag):n - max(0, lag)]
        b = sig[max(0, lag):n - max(0, -lag)]
        if len(a) < 24:
            continue
        c = float((a * b).sum() / len(a))
        if c > best:
            best, lag_best = c, lag
    return lag_best


def oneshot_window(frames, alphas, hold_end=False):
    """첫 자세에서 벗어났다 돌아오는 구간과 가장 크게 달라진 순간 (시작, 끝, 타격) 프레임.
    hold_end(쓰러짐처럼 처음 자세로 돌아오지 않는 동작)면 움직임이 멎는 순간에서 끝낸다."""
    th = thumbnails(frames, alphas)
    diff = np.abs(th - th[0]).mean(axis=1)          # 첫 자세와 얼마나 다른지
    if hold_end:
        step = np.abs(np.diff(th, axis=0)).mean(axis=1)              # 앞 프레임과 얼마나 다른지
        moving = np.where(step > max(0.002, 0.15 * step.max()))[0]
        if len(moving):
            start, end = max(0, int(moving[0]) - 2), min(len(frames) - 1, int(moving[-1]) + 3)
            return start, end, int(np.argmax(diff[:end + 1]))
    active = np.where(diff > max(0.004, 0.2 * diff.max()))[0]
    start, end = (0, len(frames) - 1) if len(active) == 0 else (
        max(0, int(active[0]) - 2), min(len(frames) - 1, int(active[-1]) + 2))
    return start, end, int(np.argmax(diff))


def pick_oneshot(frames, alphas, n, window=None, hold_end=False):
    """window를 주면 모든 방향이 같은 구간·같은 타격 프레임을 쓴다 (마네킹·마스터처럼 같은 박자를 따를 때)."""
    start, end, peak = window or oneshot_window(frames, alphas, hold_end)
    end = min(end, len(frames) - 1)
    span = max(1, end - start)
    picks = [start + round(i * span / (n - 1)) for i in range(n)] if n > 1 else [start]
    if peak not in picks and start <= peak <= end:  # 타격 순간을 가장 가까운 칸에 넣는다
        j = int(np.argmin([abs(p - peak) for p in picks]))
        picks[j] = peak
        picks = sorted(set(picks))
    return picks, (len(picks) - 1) * FPS / span, {"action_start": start, "action_end": end,
                                                  "action_sec": round(span / FPS, 2), "peak_frame": peak,
                                                  "shared_window": window is not None}


def analyze_direction(frames_dir, kind, n_frames, strip_effects=False, window=None, override=None, loop=None,
                      hold_end=False, matte=None, prange=None):
    """override: {칸 번호: 영상 프레임 번호} — 사람이 '다른 장면으로 바꾸기'로 고른 프레임.
    loop: 기준 방향에서 고른 반복 구간 (picks, fps, rep) — 모든 방향이 같은 영상 박자를 따를 때 같은 프레임을 쓴다.
    matte: 빛 효과 방식(none·vivid·strip)을 주면 고른 프레임을 AI 배경 지우기(BEN v2)와 크로마키를 합쳐 딴다
    (matting.py). vivid면 캐릭터만 있는 층(body)과 빛만 있는 층(fx)도 만든다."""
    frames = load_frames(frames_dir)
    # 편집 AI로 빛 효과를 지운 프레임이 있으면 그 프레임 대신 쓴다 (<동작>/repaired/<방향>/<프레임 번호>.png, repair.py)
    fixed = Path(frames_dir).parent.parent / "repaired" / Path(frames_dir).name
    for f in (sorted(fixed.glob("*.png")) if fixed.exists() else []):
        if f.stem.isdigit() and int(f.stem) < len(frames):
            frames[int(f.stem)] = np.asarray(Image.open(f).convert("RGB"))
    # 배경색은 프레임마다 잰다 (H3가 가끔 영상 중간에 배경색을 바꾼다)
    bgs = [estimate_bg(f) for f in frames]
    bg = bgs[0]
    alphas = [frame_alpha(f, b) for f, b in zip(frames, bgs)]
    if kind == "loop" and loop:
        # 같은 영상을 따라도 방향마다 몇 프레임씩 밀린다 (마네킹처럼 박자가 정해진 구간이면 밀림을 재지 않는다)
        lag = best_lag(motion_signal(alphas), loop[3]) if loop[3] is not None else 0
        picks = [max(0, min(len(frames) - 1, p + lag)) for p in loop[0]]
        fps, rep = loop[1], dict(loop[2], shared_loop=True, lag_frames=lag)
    else:
        picks, fps, rep = (pick_loop(frames, alphas, n_frames, prange) if kind == "loop"
                           else pick_oneshot(frames, alphas, n_frames, window, hold_end))
    for k, fi in (override or {}).items():
        if 0 <= int(k) < len(picks):
            picks[int(k)] = max(0, min(len(frames) - 1, int(fi)))
    if kind == "loop" and rep.get("period_frames"):
        start = rep.get("loop_start", 0) + rep.get("lag_frames", 0)
        span = [alphas[i] for i in range(max(0, start), min(len(alphas), start + rep["period_frames"]))]
        rep["step_px"] = step_length(span)
        rep["stance_dx"] = stance_dx(span + span[:1])
    cx = [float(np.average(np.arange(a.shape[1]), weights=a.sum(axis=0) + 1e-6)) for a in alphas]
    rep["picked"] = picks
    # 첫 프레임과 배경색이 크게 다른 프레임 (영상 AI가 효과 장면에서 배경을 다른 색으로 바꾼 것)
    # 마젠타 위에 동심원·소용돌이 무늬를 그린 프레임도 (가장자리 중앙값은 그대로라 색 비교로는 안 잡힘)
    rep["bg_changed"] = int(sum(np.linalg.norm(np.asarray(b, np.float32) - np.asarray(bg, np.float32)) > 60
                                or bg_pattern(f) > 0.1 for b, f in zip(bgs, frames)))
    rep["video_frames"] = len(frames)
    rep["drift_x_px"] = round(max(cx) - min(cx), 1)
    rep["frames_touching_edge"] = sum(int(max(a[0].max(), a[-1].max(), a[:, 0].max(), a[:, -1].max()) > 0.5)
                                      for a in alphas)
    layers = None
    if matte:
        rgba, layers, rep["matting"] = matte_picks(frames_dir, frames, alphas, bgs, picks, matte)
    else:
        rgba = [cutout_any(frames[i], alphas[i], bgs[i]) for i in picks]
        if strip_effects:
            first = cutout_any(frames[0], alphas[0], bg)                     # 첫 프레임 = 캐릭터 원래 색
            rgba, removed = remove_effects(rgba, first, alphas, picks, bg)
            rep["effect_px_removed"] = removed
    boxes = [bbox(im[..., 3] / 255.0) if im[..., 3].any() else bbox(alphas[i]) for im, i in zip(rgba, picks)]
    return {"rgba": rgba, "boxes": boxes, "fps": fps, "report": rep, "layers": layers}


def step_length(alphas):
    """옆모습 반복 동작의 한 걸음 길이(영상 px): 발밑 띠(실루엣 아래 7%)의 너비가 가장 넓을 때(두 발을 벌림)와
    가장 좁을 때(두 발이 겹침)의 차이. 한 바퀴(두 걸음) 동안 몸은 이것의 두 배를 간다."""
    widths = []
    for a in alphas:
        solid = a > 0.5
        rows = np.where(solid.any(axis=1))[0]
        if len(rows) < 10:
            continue
        top, bottom = rows[0], rows[-1]
        band = solid[max(top, bottom - max(3, round(0.07 * (bottom - top)))):bottom + 1]
        cols = np.where(band.any(axis=0))[0]
        widths.append(cols[-1] - cols[0] + 1)
    return round(float(max(widths) - min(widths)), 1) if len(widths) >= 4 else None


def stance_dx(alphas, min_run=3):
    """제자리 반복 동작에서 디딘 발이 몸에 대해 옆으로 가는 속도 (영상 px/장, 양수) 또는 None.
    장마다 땅에 닿은 점(실루엣 맨 아래 4줄의 가운데 x)을 따라가면, 같은 발을 딛는 동안은 뒤로 가고 발을 바꿀 때 앞으로
    튄다. 더 많은 장이 가는 쪽을 디딘 구간으로 보고, min_run장 넘게 이어진 구간들의 기울기를 함께 맞춘다 — 게임에서 이
    속도로 움직이면 디딘 발이 바닥에서 가장 덜 미끄러진다. AI 영상은 디딘 발도 빨라졌다 느려졌다 해서 하나로 딱 맞지는
    않는다 (2026-10-09: 예전 '발 벌림 폭' 방식은 걷기 옆모습에서 약 25% 빠르게 잡았다)."""
    xs = []
    for a in alphas:
        solid = a > 0.5
        rows = np.where(solid.any(axis=1))[0]
        if len(rows) < 10:
            return None
        bot = rows[-1]
        xs.append(float(np.where(solid[max(0, bot - 3):bot + 1].any(axis=0))[0].mean()))
    xs = np.array(xs)
    d = np.diff(xs)
    sign = -1 if (d < -0.5).sum() >= (d > 0.5).sum() else 1
    moving = sign * d > 0.5
    if moving.sum() < 0.25 * len(d):
        return None
    slopes, weights, i = [], [], 0
    while i < len(d):
        if not moving[i]:
            i += 1
            continue
        j = i
        while j < len(d) and moving[j]:
            j += 1
        if j - i >= min_run:
            seg = xs[i:j + 1]
            slopes.append(abs(np.polyfit(np.arange(len(seg)), seg, 1)[0]))
            weights.append(j - i)
        i = j
    return round(float(np.average(slopes, weights=weights)), 2) if slopes else None


DIR_ANGLE = {"E": 0, "SE": 45, "S": 90, "SW": 135, "W": 180, "NW": 225, "N": 270, "NE": 315}


def move_velocity(v, order, ground_y):
    """이동 속도 v(시트 px/초) → 방향별 [x, y] px/초 (y는 화면 아래가 +, 땅을 내려다보는 만큼 ground_y배)."""
    return {d: [round(v * np.cos(np.radians(DIR_ANGLE[d])), 1) or 0.0,
                round(v * np.sin(np.radians(DIR_ANGLE[d])) * ground_y, 1) or 0.0] for d in order if d in DIR_ANGLE}


def game_info(done, order, kind, fps, scale, hold_end=False, locomotion=False, ground_y=0.5, move_scale=1.0):
    """게임에서 쓰는 정보 (시트 JSON에 같이 쓴다).
    - frame_ms: 한 칸 보여 줄 시간
    - 한 번 동작: hit_frame(가장 크게 움직인 칸, 공격이면 맞는 순간)과 방향별 hit_frames, hold_last(쓰러짐처럼 끝 칸에서 멈춤)
    - 걷기·달리기: move_speed(시트 px/초, 발이 미끄러지지 않는 이동 속도)와 방향별 velocity [x, y] px/초
      (y는 화면 아래가 +, 땅을 비스듬히 내려다보는 만큼 ground_y배로 줄인다)"""
    info = {"frame_ms": round(1000 / fps, 1)}
    if kind != "loop":
        hits = {}
        for d in order:
            src, _ = source_of(d, list(done))
            rep = done[src]["report"]
            picks, peak = rep.get("picked") or [], rep.get("peak_frame")
            if picks and peak is not None:
                hits[d] = int(np.argmin([abs(p - peak) for p in picks]))
        if hits:
            vals = list(hits.values())
            info["hit_frame"] = hits.get("S", max(set(vals), key=vals.count))
            info["hit_frames"] = hits
        info["hold_last"] = bool(hold_end)
    elif locomotion:
        side = next((d for d in ("E", "W", "SE", "NE", "SW", "NW") if d in done
                     and (done[d]["report"].get("stance_dx") or done[d]["report"].get("step_px"))), None)
        if side:
            rep = done[side]["report"]
            period_sec = rep["period_frames"] / FPS
            old = 2 * rep["step_px"] * scale / period_sec if rep.get("step_px") else None
            v = old
            if rep.get("stance_dx"):                 # 디딘 발 기울기 (대각선이면 옆 성분이라 cos로 나눈다)
                new = rep["stance_dx"] * FPS * scale / max(0.5, abs(np.cos(np.radians(DIR_ANGLE[side]))))
                v = new if old is None or 0.5 <= new / old <= 2 else old
            info["move_speed_auto"] = round(v, 1)
            v *= move_scale
            info["move_speed"] = round(v, 1)
            info["move_scale"] = round(move_scale, 3)
            info["velocity"] = move_velocity(v, order, ground_y)
            info["ground_y"] = round(ground_y, 3)
    return info


def set_move_scale(out_dir, scale):
    """후처리: 사용자가 '게임처럼 걸어 보기'에서 맞춘 이동 속도 배율을 시트 JSON에 쓴다 (그림은 그대로)."""
    out_dir = Path(out_dir)
    for res in GIF_STYLE:
        meta_path = out_dir / f"sheet_{res}.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if "move_speed_auto" not in meta:
            continue
        v = meta["move_speed_auto"] * scale
        meta.update(move_speed=round(v, 1), move_scale=round(scale, 3),
                    velocity=move_velocity(v, meta["order"], meta.get("ground_y", 0.5)))
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def matte_picks(frames_dir, frames, alphas, bgs, picks, effects):
    """고른 프레임을 AI 배경 지우기 + 크로마키로 딴다 → (rgba, 층 {"body", "fx"} 또는 None, 정보).
    AI 마스크는 <동작>/ai/<방향>/ 에 남겨 두고 다시 조립할 때 쓴다. 빛 지우기(strip)도 크로마키 시간축 마스크
    대신 AI로: 캐릭터가 아닌 것을 지우니 밝은 옷·금발에 네모 구멍이 나지 않는다."""
    from . import matting
    files = sorted(Path(frames_dir).glob("*.png"))
    frames_dir = Path(frames_dir)
    ai = matting.cached_masks([files[i] for i in picks], frames_dir.parent.parent / "ai" / frames_dir.name)
    rgba, body, fx = [], [], []
    info = {"filled": 0, "removed": 0}
    for i, m in zip(picks, ai):
        a, inf = matting.matte(frames[i], alphas[i], m, bgs[i], effects)
        for k in info:
            info[k] += inf[k]
        im = matting.finish(frames[i], a, bgs[i])
        rgba.append(im)
        if effects == "vivid":                          # 층 나누기: 몸은 AI가 캐릭터라고 본 곳만, 빛은 나머지
            b, _ = matting.combine(frames[i], alphas[i], m, bgs[i], "all", fill_conf=0.95)
            b = np.minimum(b, a)
            bi = matting.finish(frames[i], b, bgs[i])
            fi = im.copy()
            fi[..., 3] = (np.clip(a - b, 0, 1) * 255 + 0.5).astype(np.uint8)
            body.append(bi)
            fx.append(fi)
    layers = {"body": body, "fx": fx} if effects == "vivid" else None
    return rgba, layers, info


def write_sheet(rows, order, fps, pivot, out_dir, name, loop, extra=None):
    h, w = rows[order[0]][0].shape[:2]
    n = len(rows[order[0]])
    sheet = np.zeros((h * len(order), w * n, 4), np.uint8)
    dirs = {}
    for r, d in enumerate(order):
        dirs[d] = []
        for i, im in enumerate(rows[d]):
            sheet[r * h:(r + 1) * h, i * w:(i + 1) * w] = im
            dirs[d].append({"x": i * w, "y": r * h, "w": w, "h": h})
    Image.fromarray(sheet).save(Path(out_dir) / f"{name}.png")
    meta = {"image": f"{name}.png", "frame_w": w, "frame_h": h, "fps": round(fps, 2),
            "pivot": [round(pivot[0], 1), round(pivot[1], 1)], "loop": loop, **(extra or {}), "order": order,
            "directions": dirs}
    (Path(out_dir) / f"{name}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


GIF_STYLE = {"hd": {"gap": 8, "scale": 1}, "px": {"gap": 4, "scale": 3}}


def write_gifs(rows, order, count, fps, out_dir, res):
    """미리보기 GIF(나침반 배치)와 방향별 투명 GIF (다른 곳에 바로 얹어 쓰기 좋게)."""
    st = GIF_STYLE[res]
    save_gif(layout_frames(rows, count, gap=st["gap"]), fps, Path(out_dir) / f"preview_{res}.gif", scale=st["scale"])
    for d in order:
        save_gif(rows[d], fps, Path(out_dir) / f"{res}_{d}.gif", scale=st["scale"], transparent=True)


def retime(out_dir, count, fps):
    """후처리: 다 만든 시트의 재생 속도만 바꾼다. 시트 그림은 그대로 두고 JSON의 fps와 GIF만 다시 쓴다."""
    out_dir = Path(out_dir)
    for res in GIF_STYLE:
        meta_path = out_dir / f"sheet_{res}.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        k = fps / meta["fps"]
        if "frame_ms" in meta:
            meta["frame_ms"] = round(1000 / fps, 1)
        if "move_speed" in meta:                     # 걸음이 빨라지면 발이 미끄러지지 않게 이동도 빨리
            meta["move_speed"] = round(meta["move_speed"] * k, 1)
            if "move_speed_auto" in meta:
                meta["move_speed_auto"] = round(meta["move_speed_auto"] * k, 1)
            meta["velocity"] = {d: [round(x * k, 1), round(y * k, 1)] for d, (x, y) in meta["velocity"].items()}
        sheet = np.asarray(Image.open(out_dir / meta["image"]).convert("RGBA"))
        rows = {d: [np.ascontiguousarray(sheet[r["y"]:r["y"] + r["h"], r["x"]:r["x"] + r["w"]]) for r in rects]
                for d, rects in meta["directions"].items()}
        meta["fps"] = round(fps, 2)
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        write_gifs(rows, meta["order"], count, fps, out_dir, res)


def layout_frames(rows, count, gap=8):
    """방향별 프레임을 미리보기 배치로 합친다 (8방향은 나침반, 4방향은 십자, 2방향은 좌우)."""
    grid = preview_layout(count)
    h, w = next(iter(rows.values()))[0].shape[:2]
    n = len(next(iter(rows.values())))
    R, C = len(grid), len(grid[0])
    out = []
    for i in range(n):
        canvas = np.zeros((R * h + (R - 1) * gap, C * w + (C - 1) * gap, 4), np.uint8)
        for r, line in enumerate(grid):
            for c, d in enumerate(line):
                if d and d in rows:
                    canvas[r * (h + gap):r * (h + gap) + h, c * (w + gap):c * (w + gap) + w] = rows[d][i]
        out.append(canvas)
    return out


def assemble(dir_folders, count, size, feet_y, out_dir, kind="loop", n_frames=8, hd_height=256,
             pixel_height=0, colors=20, smooth=24, palette_refs=None, strip_effects=False,
             window=None, window_from=None, char_px=None, hd_char=200, overrides=None, loop_from=None, hold_end=False,
             effects="none", loop_span=None, matting=False, locomotion=False, ground_y=0.5, move_scale=1.0):
    """dir_folders: {만든 방향: 그 방향 PNG 프레임 폴더}. 시트·GIF·report.json을 out_dir에 쓴다.
    한 번 하는 동작에서 window(시작, 끝, 타격 프레임)나 window_from(기준 방향)을 주면 모든 방향을 같은 구간으로 자른다.
    반복 동작에서 loop_from(기준 방향)을 주면 그 방향에서 찾은 반복 구간을 모든 방향에 똑같이 쓴다
    (레퍼런스 영상·마네킹처럼 모든 방향이 같은 박자를 따를 때 — 방향마다 따로 찾으면 춤 박자가 어긋난다).
    char_px(영상 속 캐릭터 키)를 주면 캐릭터 키를 HD는 hd_char, 픽셀은 pixel_height로 맞춘다. 모든 동작에서 캐릭터
    크기가 같아서 게임에서 동작이 바뀌어도 그대로다 (칼을 크게 휘두르는 동작은 칸만 커진다).
    없으면 예전처럼 칸 높이를 hd_height·pixel_height로 맞춘다.
    matting이면 AI 배경 지우기(BEN v2)와 크로마키를 합쳐 따고, 빛 효과를 살리는 동작은 캐릭터 층(sheet_hd_body.png)과
    빛 층(sheet_hd_fx.png)도 같은 배치로 쓴다."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    order = SHEET_ORDER[count]
    if kind != "loop" and window is None and window_from in dir_folders:
        frames = load_frames(dir_folders[window_from])
        window = oneshot_window(frames, [frame_alpha(f, estimate_bg(f)) for f in frames], hold_end)
    shared = None
    if kind == "loop":
        window = None
        if loop_span:                                # 마네킹: 키프레임 길이가 곧 한 바퀴 (춤처럼 긴 동작도 통째로)
            start, period = loop_span
            n = max(1, min(n_frames, period))
            shared = ([start + round(i * period / n) for i in range(n)], n * FPS / period,
                      {"period_frames": period, "period_sec": round(period / FPS, 2), "loop_start": start,
                       "fixed_span": True}, None)
        elif loop_from in dir_folders:
            frames = load_frames(dir_folders[loop_from])
            al = [frame_alpha(f, estimate_bg(f)) for f in frames]
            shared = (*pick_loop(frames, al, n_frames), motion_signal(al))
    overrides = overrides or {}
    cycle, ranges = None, {}
    if kind == "loop" and shared is None and len(dir_folders) > 1:   # 방향마다 따로 만든 영상: 모두 한 바퀴씩
        cycle, lengths = common_cycle({d: cycle_scores(f) for d, f in dir_folders.items()})
        ranges = {d: (v - 1, v + 1) for d, v in lengths.items() if v}
    done = {d: analyze_direction(folder, kind, n_frames, strip_effects, window, overrides.get(d), shared, hold_end,
                                 effects if matting else None, ranges.get(d))
            for d, folder in dir_folders.items()}
    if matting:
        from . import matting as mt
        mt.release()                                 # 영상 AI가 같은 그래픽카드를 쓴다

    # 공통 칸: 가로는 화면 중앙 기준 좌우 대칭(반전해도 피벗이 그대로), 세로는 전체 합집합
    W, H = size
    boxes = [b for r in done.values() for b in r["boxes"]]
    pad = round(0.03 * H)
    half_w = max(max(W / 2 - b[0], b[2] - W / 2) for b in boxes) + pad
    x0, x1 = max(0, round(W / 2 - half_w)), min(W, round(W / 2 + half_w))
    y0 = max(0, int(min(b[1] for b in boxes)) - pad)
    y1 = min(H, int(max(max(b[3] for b in boxes), feet_y)) + pad)

    n = min(len(r["rgba"]) for r in done.values())
    has_layers = all(r.get("layers") for r in done.values())
    rows, sources = {}, {}
    layer_rows = {"body": {}, "fx": {}} if has_layers else None
    for d in order:
        src, flip = source_of(d, list(done))
        ims = [im[y0:y1, x0:x1] for im in done[src]["rgba"][:n]]
        rows[d] = [np.ascontiguousarray(im[:, ::-1] if flip else im) for im in ims]
        sources[d] = f"{src} 반전" if flip else "생성"
        for name in (layer_rows or {}):
            ims = [im[y0:y1, x0:x1] for im in done[src]["layers"][name][:n]]
            layer_rows[name][d] = [np.ascontiguousarray(im[:, ::-1] if flip else im) for im in ims]

    loop = kind == "loop"
    fps = float(np.mean([r["fps"] for r in done.values()]))
    pivot = (W / 2 - x0, feet_y - y0)
    s = hd_char / char_px if char_px else hd_height / (y1 - y0)
    def scaled(r):
        return {d: [np.asarray(Image.fromarray(im).resize((round(im.shape[1] * s), round(im.shape[0] * s)), Image.LANCZOS))
                    for im in r[d]] for d in order}
    hd = scaled(rows)
    meta = write_sheet(hd, order, fps, (pivot[0] * s, pivot[1] * s), out_dir, "sheet_hd", loop,
                       game_info(done, order, kind, fps, s, hold_end, locomotion, ground_y, move_scale))
    write_gifs(hd, order, count, fps, out_dir, "hd")
    for old in out_dir.glob("sheet_hd_*.png"):         # 예전 층 시트 (이번에 층이 없으면 지운다)
        old.unlink()
    if layer_rows:                                   # 캐릭터 층·빛 층: 시트와 같은 배치 (JSON 하나로 같이 쓴다)
        meta["layers"] = {}
        for name, r in layer_rows.items():
            hl = scaled(r)
            h, w = hl[order[0]][0].shape[:2]
            sheet = np.zeros((h * len(order), w * n, 4), np.uint8)
            for ri, d in enumerate(order):
                for i, im in enumerate(hl[d]):
                    sheet[ri * h:(ri + 1) * h, i * w:(i + 1) * w] = im
            Image.fromarray(sheet).save(out_dir / f"sheet_hd_{name}.png")
            meta["layers"][name] = f"sheet_hd_{name}.png"
        (out_dir / "sheet_hd.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    if pixel_height:
        flat = [im for d in order for im in rows[d]]
        ps = pixel_height / char_px if char_px else pixel_height / (y1 - y0)
        px, _ = pixelate(flat, max(1, round((y1 - y0) * ps)), colors, palette_ref=palette_refs, smooth=smooth, seq_len=n)
        prow = {d: px[k * n:(k + 1) * n] for k, d in enumerate(order)}
        write_sheet(prow, order, fps, (pivot[0] * ps, pivot[1] * ps), out_dir, "sheet_px", loop,
                    game_info(done, order, kind, fps, ps, hold_end, locomotion, ground_y, move_scale))
        write_gifs(prow, order, count, fps, out_dir, "px")

    report = {"kind": kind, "count": count, "order": order, "frames": n, "sprite_fps": round(fps, 2),
              "common_cycle_frames": cycle,
              "cell_crop": [x0, y0, x1, y1], "char_px": round(char_px, 1) if char_px else None, "sources": sources,
              "directions": {d: r["report"] for d, r in done.items()}}
    try:                                             # 점검이 실패해도 시트는 그대로 쓴다
        report["qa"] = qa.check(hd, list(done), kind, report["directions"], effects)
    except Exception as e:  # noqa: BLE001
        report["qa_error"] = str(e)
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report
