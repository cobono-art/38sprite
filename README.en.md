# 38Sprite

[한국어](README.md) · **English**

A local web app that turns **one character turnaround** (front · side · back on one image) and a **motion description**
into game-ready **8-direction sprite sheets** (PNG + JSON + GIF).

The name means **3-view → 8 directions**.

![38Sprite promo highlight](docs/promo_highlight.webp)

https://github.com/user-attachments/assets/38e45399-a1d9-4126-8a3f-20a381fb4540

Every character animation in the video was made with 38Sprite.

A real result (8-direction walk sheets):

![8-direction walk example](docs/demo_walk8.gif)

## Features

| Feature | What it does |
|---|---|
| 8-direction drawings | Upload a turnaround and Codex draws all 8 directions in a 3×3 grid. You can also upload your own grid. |
| Direction check · redraw one direction | Finds cells drawn facing the wrong way (e.g. a back diagonal NE/NW drawn as a front view) by face colors (skin and eye colors only the front view has) and redraws just that cell with Codex automatically (up to twice by default). You can also redraw one direction by hand. |
| Three motion inputs | Text ("walk in place"), a reference video (e.g. a dance), or a 3D mannequin (Codex writes keyframes; each direction follows a mannequin video rendered from its own angle). |
| Video → 3D mannequin | Extracts a 3D skeleton from every frame of a reference video (MediaPipe), drives the 3D mannequin with it, and has each direction follow it from its own angle, so side and back views do the same move. Without the skeleton tool, Codex reads the video and writes the motion instead. |
| Basic motion set | Idle, walk, run, attack, hit and death in one click. |
| Loops · one-shots | Walks and dances are cut into seamless loops; attacks are trimmed to the action. Every direction of a walk or run loops exactly one cycle (two steps), so the cadence stays the same when the character turns. Motions that end in a different pose (like death) are supported. |
| Directions · camera | 8, 4 or 2 directions, from eye level to top-down (default: 45° high quarter view). |
| HD · pixel art | Every motion is exported as an HD sheet and a pixel-art sheet. In pixel style the pixel height is measured from the pixel grid Codex actually drew, so one sprite pixel matches one pixel of the art (asked for 64, Codex draws about 74). Small specks are merged into the surrounding color and frame-to-frame color flicker is reduced. The head of the original drawing is pasted where it fits in every frame, so the face stays exactly like the art and doesn't wobble. Pixel style renders its videos at 480 px, about 30% faster. |
| Light effects | None · vivid · strip (under "Advanced"). Picks "vivid" automatically when the description mentions magic, sword trails and so on. "Vivid" also writes a character-only and an effects-only layer sheet. |
| Magenta from start to end | Everything from the Codex direction drawings to the 3D mannequin mode is made on a magenta background so chroma keying stays clean. If the video AI changes the background color mid-clip, the direction is regenerated with a new seed (up to twice by default) and the cleanest result is kept. |
| Light-trail removal (optional) | The video AI (H3) has no negative prompt, and writing "no trails" makes it draw them. A ComfyUI node made for 38Sprite (install with `setup_negative.bat`) removes light trails, sparkles and glows during generation for motions without effects, at the same speed. |
| Fix leftover effects (optional) | For a trail that still slips through, pick the frame and press "Remove effects in this frame": an image-editing AI (ComfyUI's official Qwen-Image-Edit, or Qwen-Image 2.1 edit) erases only the effects and only the strongly changed areas are pasted into the original frame (about a minute per frame including model loading). "Original frame" undoes it. |
| AI matting (optional) | BEN v2 (MIT) fixes only what chroma keying gets wrong: holes in colors close to the background, floor shadows and colored fringes. Used automatically after `setup_matting.bat` downloads the model (about 380 MB). |
| Automatic checks | Flags holes, magenta/green fringes, loop seams, cut-offs at the frame edge, per-direction size differences, empty frames and mid-clip background color changes, and marks the frames. |
| Post-processing | Change playback speed, swap a bad frame for another moment of the video, or remake one direction (and undo it if you liked the old one better), without regenerating everything. Walks and runs can be previewed over a scrolling ground, like in a game, to tune the movement speed ("Walk like in a game"). |
| Game engine export | One ZIP with the sheet PNG/JSON/GIF plus **Aseprite JSON** (Phaser, PixiJS), **Godot 4** SpriteFrames + scene, and per-direction **frame PNGs** (Unity etc.). "Download ▾ → Every motion of this character" also merges every motion into a single Godot SpriteFrames. |
| Game info | The sheet JSON includes the attack impact frame (`hit_frame`), whether to stop on the last frame (`hold_last`) and, for walks and runs, the movement speed that keeps the feet from sliding (`move_speed`, per-direction `velocity`). |

## How it works

```
turnaround ─▶ Codex: 8-direction grid (3×3) ─▶ first frame per direction (magenta background)
                                                  │
               text / reference video / 3D mannequin ─┤
                                                  ▼
                         video AI (ComfyUI, MiniMax H3 by default)
                                                  │
          background removal · loop search · size and foot alignment
                                                  ▼
                              sheet PNG + JSON + GIF
```

- Only 5 directions (S, SE, E, NE, N) are generated; the 3 left directions are mirrored.
- Videos are 640×640 at 24 fps; the first and last frames are pinned to the same image to encourage loops. Text loops
  and 3D-mannequin one-shots are 3 s (same quality as 5 s, 30–40% faster); reference-video motions and motions that end
  in a different pose (like death) are 5 s.
- The character height is the same in every motion (200 px in HD), so switching motions in a game does not change the size.

## Requirements

- **Windows + NVIDIA GPU** (16 GB VRAM recommended; tested on an RTX 5080 16 GB)
- **ComfyUI** (running) + a **video AI model**
  - MiniMax H3 by default. See [docs/H3_SETUP.md](docs/H3_SETUP.md) (Korean).
  - To use another video model, see [docs/CUSTOM_WORKFLOW.md](docs/CUSTOM_WORKFLOW.md) (Korean).
- **Codex CLI login** (ChatGPT account): used for the 8-direction drawings and mannequin keyframes. Without it you can
  upload your own direction grid (mannequin mode is not available).
- **Python**: the Python bundled with ComfyUI works as is. For another Python: `pip install -r requirements.txt`
- **(Optional) video → 3D skeleton tool**: run `setup_pose.bat` once. It installs MediaPipe into an app-only virtual
  environment (`.venv-pose`) and downloads the pose model (Google's official model, about 30 MB) into `models/`, without
  touching ComfyUI's Python. Needs Python 3.10–3.12; about 130 MB in total.
- **(Optional) light-trail removal node**: run `setup_negative.bat` once to copy `comfyui_nodes/sprite_neg_h3` into the
  `custom_nodes` folder of your video-AI ComfyUI (nothing is downloaded). Restart ComfyUI and the app uses it automatically. If your ComfyUI runs with `--disable-all-custom-nodes`, the
  "Turn on trail removal" button at the top restarts it with the same options, allowing only this node.
- **(Optional) image-editing AI**: "Remove effects in this frame" needs a ComfyUI with ComfyUI's official Qwen-Image-Edit
  models (`qwen_image_edit_2509`/`2511` etc. + the `qwen_2.5_vl_7b` text encoder + `qwen_image_vae`, faster with the Lightning
  4-step LoRA) or the Qwen-Image 2.1 edit nodes (`TextEncodeQwenImage21`, `QwenImage21Cache`). The official models can live in
  your video-AI ComfyUI (a few minutes to load the first time, then about 20 s per frame). The app looks on ports 8188, 8189
  and 8000 (setting `edit_url`).
  It shares the GPU with the video AI, so the video model is unloaded first and frames can't be fixed while a video is being made.
- **(Optional) AI matting model**: run `setup_matting.bat` once to download BEN v2 (PramaLLC, MIT) into `models/ben2`
  (about 380 MB). The Python bundled with ComfyUI already has torch, so nothing else needs installing.

## Install and run

1. Start ComfyUI. On the first run the app looks for a running ComfyUI (ports 8188, 8189, 8000) and writes the one
   with the H3 model into `config.json`. If yours is elsewhere, change it in the app's connection settings.
2. Get this repository and run `run_app.bat`. It uses the Python of the running ComfyUI, or looks in common install
   locations on drives C–F, and remembers it in `python_path.txt`. If it can't find one, create `python_path.txt` in
   this folder with the full path to `python.exe` on one line.
3. `http://127.0.0.1:7870` opens in your browser. Use the KO/EN button at the top to switch the interface language.
   The start screen lists optional tools you haven't installed yet.

To run it directly: `python app/server.py --port 7870 --open`

Developers can run the tests with `python -m unittest discover -s tests` (no extra installs, no video AI — they use
fake frames). They also run automatically on Windows and Linux for every push.

## Workflow

1. Upload a turnaround.
2. Make the 8-direction drawing (Codex or upload). If a direction faces the wrong way you get a warning; fix just that
   direction with "redraw one direction".
3. Make motions from text or a reference video and pick loop or one-shot. Frame count, how directions are matched
   (3D mannequin etc.) and light effects are under "Advanced" (defaults suit the motion). Press "Make the basic
   motions at once" to make all six basic motions.
4. Check the automatic-check marks, adjust the speed or swap bad frames.
5. Download the ZIP from "Download ▾" at the top right. Engine instructions are in `엔진에서_쓰는_법.txt` (Korean and English) inside the ZIP.

## Using the sprites in a game engine

| Engine | Files in the ZIP | How |
|---|---|---|
| Phaser 3 | `<name>_aseprite.json` + `sheet_hd.png` | `load.aseprite()` → `anims.createFromAseprite()` (animation names = directions: S, SE, E …) |
| PixiJS | `<name>_aseprite.json` | `Assets.load()` → `new AnimatedSprite(sheet.animations['S'])` |
| Godot 4 | `godot/` folder | Copy the folder and instance the `.tscn` (AnimatedSprite2D with the feet at the node origin) |
| Unity · others | `frames/hd/<direction>/` | Import the PNGs per direction and make animations (pivot values are in the txt) |

"Every motion of this character" contains every motion, and `godot_all/` holds a single SpriteFrames with all motions (animation names
like `walk_S`). Frames are padded so the feet stay at the same point in every motion, so switching animations does not
make the character jump.

## Sheet JSON

```json
{
  "image": "sheet_hd.png",
  "frame_w": 154, "frame_h": 249,
  "fps": 7.52,
  "pivot": [76.8, 219.6],
  "loop": true,
  "order": ["S", "SW", "W", "NW", "N", "NE", "E", "SE"],
  "directions": { "S": [{ "x": 0, "y": 0, "w": 154, "h": 249 }] }
}
```

- `pivot`: the foot point shared by every frame (px from the frame's top-left)
- `directions`: frame rectangles per direction, in playback order
- `frame_ms`: how long each frame is shown (milliseconds)
- One-shots: `hit_frame` (the frame with the biggest movement, from 0 — the impact for attacks), per-direction
  `hit_frames`, `hold_last` (true: stop on the last frame)
- Walks and runs: `move_speed` (sheet px per second; move the character at this speed so the feet don't slide) and
  per-direction `velocity` [x, y] (y is + down the screen, scaled by `ground_y` for the tilted ground)
- Vivid-effect motions: `layers` — `sheet_hd_body.png` (character only) and `sheet_hd_fx.png` (effects only) with the
  same layout

## Settings (config.json)

Defaults work out of the box. Copy `config.example.json` to `config.json` only if you need to change something.

| Key | Default | Meaning |
|---|---|---|
| `comfy_url` | (found automatically on the first run, else `http://127.0.0.1:8188`) | ComfyUI address |
| `port` | `7870` | Port of this app |
| `video_backend` | `h3` | `h3`, or `custom` (swap the video AI with your own workflow) |
| `workflow_dir` | `workflows` | Folder with your workflow files when `custom` |
| `models` | (default H3 file names) | Only if your H3 model files are named differently |
| `matting` | `auto` | AI matting: `auto` (use the model if present) or `off` |
| `matting_dir` | `models/ben2` | Folder with the BEN v2 files (`BEN2.py`, `model.safetensors`) |
| `turbo_r2v_steps` | `6` | Generation steps for 3D mannequin mode (4 is faster, but about 40% of seeds turn the background into blotches or rings and need a redo) |
| `pixel_auto_height` | `true` | Use the pixel height measured from the direction sheet's pixel grid (`false` scales down to the height you chose) |
| `pixel_video_size` | `480` | Video size for pixel style (640 matches HD and is about 30% slower; the pixel result is the same) |
| `pixel_keep_head` | `true` | Paste the original drawing's head into every pixel frame where it fits (frames where it doesn't fit are left alone) |
| `auto_redraw` | `2` | How many times to redraw cells drawn facing the wrong way (0 = only warn) |
| `turbo_steps` | `6` | Video generation steps for per-direction mode (8 = the old setting, about 25% slower; 4 leaves specks in the background) |
| `negative_weight` | `1.5` | Strength of the light-trail removal node (0 = off). Used only when the node is installed and the motion's light effects are "none" or "strip" |
| `negative_words` | (trails, sparkles, glows …) | What the node removes (English, comma-separated) |
| `comfy_autostart` | `true` | When the app starts and the local ComfyUI is off, start it (with the last seen options `comfy_args`, allowing the trail-removal node if installed) |
| `bg_retry` | `2` | How many times to regenerate with a new seed when the video AI changes the background color or draws patterns (rings etc.) on it (0 = never) |
| `mannequin_body` | `clay` | 3D mannequin reference: `clay` (bald human model) · `chibi` (the same model with chibi proportions) · `male` · `female` · `off` (capsule mannequin) |
| `mannequin_bg` | `magenta` | 3D mannequin background: `magenta`, or the old `gray` |
| `edit_url` | (found automatically) | ComfyUI with the image-editing AI for "Remove effects in this frame" |
| `edit_models` | (picked from the files you have) | Only to choose the edit model files yourself: `{"unet": …, "clip": …, "vae": …, "lora": …}` |

## Please read: licenses and notes

- **The code in this repository** is under the [MIT License](LICENSE).
- **The human 3D models** (`spritegen/assets/body/`) are [Quaternius](https://quaternius.com)' Universal Base Characters
  (free standard pack), CC0 (public domain). The 3D mannequin mode animates this model (bald clay look) by default:
  its shading shows the video AI which arm is in front far better than the capsule mannequin. Without the skeleton-tool
  environment (`setup_pose.bat`) the capsule mannequin is used.
- **The AI matting model BEN v2** (PramaLLC) is MIT-licensed and not included in the repository; `setup_matting.bat`
  downloads it from Hugging Face.
- **No video AI model is included.** To use MiniMax H3 you must check and follow MiniMax's model license yourself.
  It may restrict regions or commercial use; regions excluded from the public license may need separate permission
  from MiniMax.
- **Codex** runs on your own ChatGPT account login and uses your own quota. Do not share accounts or run it as a
  service that generates for other people.
- **What you make** is subject to the terms of the models and services you use.

## Known limitations

- Following a reference video with "per direction" can give side views a different move or turn them toward the camera.
  Use the 3D mannequin mode when all 8 directions must do the same move. The mannequin has no fingers or facial
  expressions, so fine details get simpler, and without the skeleton tool (`setup_pose.bat`) Codex's reading of the
  video is less accurate.
- Codex sometimes draws a back diagonal as a front view. The app detects it automatically, but the check compares colors
  only, so take a quick look yourself.
- Without the AI matting model, the "strip" light-effect mode can punch holes in bright characters (white clothes,
  blond hair). The default is "none".
- Even when told "no effects", the video AI sometimes draws sword trails on attacks. AI matting may treat a trail
  attached to the character as part of it, so it can't always remove it.
- Automatic checks are hints for common defects. For "vivid" effect motions some checks (holes, cut-offs, size, empty
  frames) are skipped because of the light trails.
- The basic motion set makes 6 motions in a row and takes over an hour on an RTX 5080.
- Depending on the seed, the video AI may flip the magenta background to yellow, cyan, red and so on every few frames
  (especially in light-effect scenes; prompt wording does not prevent it). Each
  direction is checked as soon as it arrives and regenerated with a new seed (up to twice); if every attempt drifts, the cleanest
  one is kept and the automatic checks mark "background color changed".
- Videos are processed at 24 fps.

## Folders

```
app/          web server (aiohttp) and UI (HTML/JS)
spritegen/    pipeline, background removal (incl. AI matting), loop search, sheet assembly, 3D mannequin, engine export, checks (qa)
workflows/    example workflows for swapping the video AI
comfyui_nodes/ ComfyUI node: light-trail removal (sprite_neg_h3, installed by setup_negative.bat)
docs/         setup guides
projects/     your results (created on first run, not committed)
```
