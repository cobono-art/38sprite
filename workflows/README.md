# workflows

영상 AI를 바꿀 때 쓰는 ComfyUI 워크플로(API 형식 JSON)를 두는 폴더입니다. 자세한 방법은 [docs/CUSTOM_WORKFLOW.md](../docs/CUSTOM_WORKFLOW.md)를 보세요.

- `i2v.json`: 사용자 워크플로, 첫 프레임 → 영상 (필수, 직접 만드세요)
- `r2v.json`: 사용자 워크플로, 캐릭터 그림 + 동작 영상 → 영상 (선택)
- `example_h3_i2v.json`, `example_h3_r2v.json`: MiniMax H3로 만든 예시. 자리표시자 위치를 참고하세요. 이 파일을 `i2v.json`으로 복사하면 기본 H3 모드와 똑같이 동작합니다.
