"""38Sprite: MiniMax H3용 '빼는 낱말' 노드 (ComfyUI 사용자 정의 노드).

H3는 CFG 증류 모델이라 네거티브 프롬프트(CFG)가 없고, 프롬프트에 "궤적 없이"라고 적으면 오히려 그 낱말이 내용으로 읽힌다.
이 노드는 NegPiP 원리를 이 파일에서 처음부터 구현한다 (다른 저장소 코드는 쓰지 않음):
1) 빼고 싶은 낱말(예: 빛 궤적, 반짝이)을 따로 인코딩해 글자 토큰 끝에 붙이고
2) DiT 어텐션에서 영상·소리·조건 줄(query)이 그 토큰을 볼 때만 값(value) 부호를 뒤집어(-weight) 그 개념을 뺀다.
   글자 줄끼리는 원래 값 그대로라 글자 흐름이 망가지지 않는다.
3) 글자 다듬기(token refiner)는 원래 문장과 빼는 낱말을 따로 해서 서로 섞이지 않게 한다.
CFG를 쓰지 않으므로 터보(BasicGuider)에서도 돌고 계산 시간도 거의 같다.
2026-10-08 시험(마네킹 공격, 같은 시드): 지팡이 빛·반짝임·작은 궤적이 모두 사라지고 휘두르는 동작은 그대로.

설치: 이 폴더(sprite_neg_h3)를 ComfyUI/custom_nodes/ 에 복사하고 ComfyUI를 다시 켠다 (38Sprite의 setup_negative.bat).
H3 모델이 아니거나 ComfyUI 구조가 달라 맞지 않으면 아무것도 바꾸지 않고 그대로 통과시킨다."""
import logging

import torch

log = logging.getLogger(__name__)


class SpriteNegativeH3:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "model": ("MODEL",),
            "clip": ("CLIP",),
            "conditioning": ("CONDITIONING",),
            "negative": ("STRING", {"multiline": True, "default": ""}),
            "weight": ("FLOAT", {"default": 1.5, "min": 0.0, "max": 8.0, "step": 0.1}),
            "block_start": ("INT", {"default": 0, "min": 0, "max": 256}),
            "block_end": ("INT", {"default": 256, "min": 0, "max": 256}),
        }}

    RETURN_TYPES = ("MODEL", "CONDITIONING")
    FUNCTION = "apply"
    CATEGORY = "38sprite"

    def apply(self, model, clip, conditioning, negative, weight, block_start, block_end):
        text = (negative or "").strip()
        dm = getattr(getattr(model, "model", None), "diffusion_model", None)
        cls_fn = getattr(type(dm), "preprocess_text_embeds", None)
        if not text or weight == 0 or cls_fn is None or not hasattr(dm, "hidden_size"):
            return (model, conditioning)                   # H3가 아니면 그대로
        neg = clip.encode_from_tokens_scheduled(clip.tokenize(text))[0][0]   # [1, Ln, D] Qwen 은닉 상태
        n_neg = int(neg.shape[1])
        out = []
        for t, d in conditioning:
            d = d.copy()
            tags = d.get("minimax_token_tags")
            if tags is not None:                           # 붙인 토큰은 글자(태그 1)
                tags = tags.view(-1)
                d["minimax_token_tags"] = torch.cat([tags, torch.ones(n_neg, dtype=tags.dtype, device=tags.device)])
            out.append([torch.cat([t, neg.to(t.device, t.dtype)], dim=1), d])

        m = model.clone()

        def preprocess(text_states, *a, **kw):
            if text_states.shape[-1] == dm.hidden_size or text_states.shape[1] <= n_neg:
                return cls_fn(dm, text_states, *a, **kw)
            pos = cls_fn(dm, text_states[:, :-n_neg], *a, **kw)
            ng = cls_fn(dm, text_states[:, -n_neg:], *a, **kw)
            return torch.cat([pos, ng], dim=1)

        m.add_object_patch("diffusion_model.preprocess_text_embeds", preprocess)
        to = m.model_options.setdefault("transformer_options", {})
        prev = to.get("optimized_attention_override")
        warned = []

        def attention(func, q, k, v, heads, *args, **kwargs):
            call = (lambda *aa, **kk: prev(func, *aa, **kk)) if prev is not None else func
            opts = kwargs.get("transformer_options") or {}
            layout = opts.get("minimax_h3_layout")
            blk = opts.get("block_index", -1)
            if (layout is None or q.dim() != 4 or q.shape[2] != getattr(layout, "seq_len", -1)
                    or not (block_start <= blk < block_end)):
                return call(q, k, v, heads, *args, **kwargs)
            try:
                T = layout.segments[0][1]                  # 글자 구간 [0, T), 빼는 낱말은 끝 n_neg줄
                a = T - n_neg
                out_text = call(q[:, :, :T].contiguous(), k, v, heads, *args, **kwargs)
                v2 = v.clone()
                v2[:, :, a:T] *= -weight
                out_rest = call(q[:, :, T:].contiguous(), k, v2, heads, *args, **kwargs)
                return torch.cat([out_text, out_rest], dim=1)
            except Exception as e:  # noqa: BLE001 — 구조가 달라도 생성은 계속
                if not warned:
                    warned.append(1)
                    log.warning("SpriteNegativeH3: 이 ComfyUI 구조와 맞지 않아 빼는 낱말 없이 진행 (%s)", e)
                return call(q, k, v, heads, *args, **kwargs)

        to["optimized_attention_override"] = attention
        return (m, out)


NODE_CLASS_MAPPINGS = {"SpriteNegativeH3": SpriteNegativeH3}
NODE_DISPLAY_NAME_MAPPINGS = {"SpriteNegativeH3": "38Sprite Negative (H3)"}
