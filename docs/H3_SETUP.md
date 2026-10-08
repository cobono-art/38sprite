# MiniMax H3 설치 안내

38Sprite는 기본 영상 AI로 MiniMax H3를 씁니다. 모델 파일은 저장소에 들어 있지 않습니다. 각자 받아서 ComfyUI에 넣어야 합니다.

> **라이선스 먼저 확인하세요.** H3는 MiniMax의 모델 라이선스를 따릅니다. 지역 제한이나 상업적 사용 조건이 있을 수 있습니다. 공개 라이선스 대상이 아닌 지역에서 쓰려면 MiniMax에 따로 허락을 받아야 할 수 있습니다.

## 필요한 것

- MiniMax H3 노드가 들어 있는 ComfyUI (0.37 이상)
- NVIDIA GPU (VRAM 16GB 권장)

## 모델 파일과 넣을 위치

ComfyUI의 공식 MiniMax H3 안내(템플릿)를 따라 받고, 아래 폴더에 넣습니다. 파일 이름이 다르면 `config.json`의 `models`에 실제 이름을 적으세요.

| 용도 | 기본 파일 이름 | ComfyUI 폴더 | config 키 |
|---|---|---|---|
| 이미지→영상 (필수) | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | `models/diffusion_models` | `i2v` |
| 레퍼런스 영상 따라 하기 (선택) | `minimax_h3_ref2va_pruned_int8_convrot.safetensors` | `models/diffusion_models` | `r2v` |
| 이미지→영상 8스텝 터보 (권장) | `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors` | `models/loras` | `turbo_i2v` |
| 레퍼런스 4스텝 터보 (선택) | `minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors` | `models/loras` | `turbo_r2v` |
| 텍스트 인코더 (필수) | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | `models/text_encoders` | `clip` |
| 영상 VAE (필수) | `minimax_h3_video_vae_int8_convrot.safetensors` | `models/vae` | `video_vae` |
| 오디오 VAE (레퍼런스 모드) | `minimax_h3_audio_vae_fp32.safetensors` | `models/vae` | `audio_vae` |

예시 (`config.json`):

```json
{
  "models": {
    "i2v": "내가_받은_파일이름.safetensors"
  }
}
```

## 확인

앱 오른쪽 위의 상태 표시가 "영상 AI 연결됨"이면 준비된 것입니다. "영상 따라 하기 없음"이라고 나오면 레퍼런스 영상 모드에 필요한 모델(`r2v`)이 없는 것입니다. 글·마네킹 모드는 쓸 수 있습니다.

## 속도 참고 (RTX 5080 16GB)

| 모드 | 방향 하나 |
|---|---|
| 글 (이미지→영상, 터보 8스텝) | 약 2분 30초 |
| 3D 마네킹 (레퍼런스, 터보 4스텝) | 약 3분 30초 |
| 레퍼런스 영상 (20스텝) | 약 12분 |

8방향은 5방향만 생성합니다(나머지는 좌우 반전). 처음 한 번은 모델을 불러오느라 더 걸립니다.
