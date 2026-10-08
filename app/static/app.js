"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const ARROWS = { NW: "↖", N: "↑", NE: "↗", W: "←", E: "→", SW: "↙", S: "↓", SE: "↘" };
const COMPASS = [["NW", "N", "NE"], ["W", null, "E"], ["SW", "S", "SE"]];
const DEFAULT_PRESETS = [
  { label: "정면 눈높이", deg: 0 }, { label: "쿼터뷰 30°", deg: 30 },
  { label: "높은 쿼터뷰 45°", deg: 45 }, { label: "탑다운 60°", deg: 60 },
];
const SEC_PER_DIR = { text: 160, video: 720, mannequin: 200, follow: 720 };
const STATUS_LABEL = { running: "만드는 중", done: "완료", error: "실패", cancelled: "중지됨", interrupted: "중단됨",
  review: "마스터 확인", keys_review: "마네킹 확인" };
const MODE_LABEL = { mannequin: "3D 마네킹", master: "마스터 먼저", direct: "방향별 바로" };
const FX_LABEL = { none: "효과 없음", vivid: "효과 살림", strip: "효과 지움" };
const FX_HINT = {
  none: "효과 없이 그려요. 걷기·대기·공격처럼 빛 효과가 없는 동작에 맞아요.",
  vivid: "마법·검기 같은 빛 효과를 화려하게 살려서 그려요.",
  strip: "영상 AI가 그린 빛 궤적을 지워요. 흰 옷·금발처럼 밝은 캐릭터는 구멍이 날 수 있어요.",
};
const MQ_DESC = {
  text: "Codex가 짠 3D 동작을 방향마다 그 각도에서 따라 해요. 손·궤적·박자가 가장 잘 맞아요.",
  pose: "영상에서 3D 뼈대를 뽑아(MediaPipe) 마네킹을 그대로 움직이고, 방향마다 그 각도에서 따라 해요. 옆모습도 같은 동작이 돼요.",
  video: "Codex가 영상을 보고 3D 마네킹 동작으로 옮겨요. setup_pose.bat을 한 번 실행하면 영상에서 뼈대를 직접 뽑아 더 정확해져요.",
};
const fxOf = m => m.effects || (m.strip_effects ? "strip" : "vivid");
const QA_TEXT = { hole: "구멍", fringe: "테두리 색 번짐", pink: "분홍 효과가 남음", shadow: "바닥 그림자",
  empty: "빈 칸", seam: "반복 이음새가 튐", edge: "화면 밖으로 잘렸을 수 있음", size: "이 방향만 크기가 다름",
  bg: "배경색이 바뀜" };
const QA_TIP = {
  hole: "옷이나 무기 한가운데가 뚫렸어요. 그 장을 눌러 다른 장면으로 바꾸거나, 이 방향만 다시 만들어 보세요.",
  fringe: "가장자리에 배경색(분홍·초록)이 번졌어요. 그 장을 눌러 다른 장면으로 바꿔 보세요.",
  pink: "영상 AI가 분홍빛 효과를 그렸어요. 그 장을 다른 장면으로 바꾸거나, 이 방향만 다시 만들어 보세요.",
  shadow: "영상 AI가 발밑에 회색 그림자를 그렸어요. 게임에서 그림자를 따로 그린다면 이 방향만 다시 만들어 보세요.",
  empty: "캐릭터가 거의 안 보이는 장이에요. 다른 장면으로 바꿔 보세요.",
  seam: "마지막 장에서 첫 장으로 넘어갈 때 튀어 보여요. 프레임 수를 바꾸거나 다시 만들어 보세요.",
  edge: "영상에서 캐릭터가 화면 끝에 닿았어요. 칼끝이나 발이 잘렸으면 이 방향만 다시 만들어 보세요.",
  size: "이 방향만 캐릭터 키가 달라요. 방향 그림을 확인해 보세요.",
  bg: "영상 AI가 영상 중간에 배경을 마젠타가 아닌 색으로 바꿨어요. 효과 둘레가 덜 깨끗할 수 있어요 — 이 방향만 다시 만들어 보세요.",
};
const DROP_TEXT = "삼면도 이미지를 끌어다 놓거나 눌러서 고르세요 (PNG·JPG)";

const state = {
  status: null, projects: [], project: null, selected: null,
  polls: new Map(), jobs: new Map(), player: null, sheetError: "",
  prefs: new Map(),      // 동작마다 보던 방향·크기·배경 (재생 화면을 다시 그려도 그대로)
};

async function api(url, opts = {}) {
  const res = await fetch(url, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `요청이 실패했어요 (${res.status})`);
  return data;
}
const postJSON = (url, body) =>
  api(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
const fileUrl = (pid, path) => `/files/${pid}/${path}`;
const mmss = s => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
const styleName = st => (st === "pixel" ? "픽셀" : "HD");

function layoutFor(count) {
  if (count === 8) return COMPASS;
  if (count === 4) return [[null, "N", null], ["W", null, "E"], [null, "S", null]];
  return [["W", "E"]];
}
function dirsFor(count) {
  return { 8: ["S", "SW", "W", "NW", "N", "NE", "E", "SE"], 4: ["S", "W", "N", "E"], 2: ["W", "E"] }[count];
}
function generatedFor(count, mirror) {
  const left = new Set(["W", "SW", "NW"]);
  return dirsFor(count).filter(d => !mirror || !left.has(d));
}
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function showText(sel, text, root = document) {
  const e = $(sel, root);
  e.textContent = text || "";
  e.hidden = !text;
}

/* ---------- 연결 상태 ---------- */

function setChip(chip, ok, text, title) {
  chip.textContent = text;
  chip.className = "chip " + (ok ? "ok" : "bad");
  chip.title = title || "";
}

async function loadStatus() {
  try {
    const st = await api("/api/status");
    state.status = st;
    if (st.version) $("#app-version").textContent = `v${st.version}`;
    const c = st.comfy;
    setChip($("#st-comfy"), c.ok, c.ok ? (c.r2v ? "영상 AI 연결됨" : "영상 AI 연결됨 · 영상 따라 하기 없음") : "영상 AI 연결 안 됨",
      c.error || `${c.url} · ComfyUI ${c.version || ""}`);
    setChip($("#st-codex"), st.codex.ok, st.codex.ok ? "Codex 로그인됨" : "Codex 확인 필요",
      st.codex.error || st.codex.version || "");
    updateModeAvailability();
    if (state.project) renderSettings();
  } catch (e) {
    setChip($("#st-comfy"), false, "서버 오류", e.message);
  }
}

/* ---------- 캐릭터 ---------- */

async function loadProjects(selectId) {
  state.projects = await api("/api/projects");
  renderProjectPicker();
  if (selectId) await openProject(selectId);
  return state.projects;
}

function renderProjectPicker() {
  const sel = $("#project-select");
  sel.replaceChildren(...state.projects.map(p => new Option(p.name, p.id)), new Option("+ 새 캐릭터", "__new"));
  if (state.project) sel.value = state.project.id;
  $("#char-pick").hidden = !state.projects.length;
}

function showView(view) {
  $("#view-empty").hidden = view !== "empty";
  $("#view-project").hidden = view !== "project";
}

async function openProject(pid) {
  if (!state.project || state.project.id !== pid) {
    state.selected = null;
    state.sheetError = "";
    clearMotionView();
    $("#activity").replaceChildren();
    delete $("#activity").dataset.key;
  }
  state.project = await api(`/api/projects/${pid}`);
  try { localStorage.setItem("lastProject", pid); } catch { /* 저장 안 돼도 무시 */ }
  showView("project");
  $("#project-select").value = pid;
  renderProject();
}

async function refreshProject() {
  if (!state.project) return;
  state.project = await api(`/api/projects/${state.project.id}`);
  renderProject();
}

function renderCharacter() {
  const p = state.project;
  $("#p-turn").src = fileUrl(p.id, p.turnaround);
  $("#p-name").textContent = p.name;
  $("#p-meta").textContent = `방향 그림 ${p.sheets.length}장 · 동작 ${p.motions.length}개`;
}

function setupNewDialog() {
  const dlg = $("#dlg-new"), file = $("#new-file"), drop = $("#new-drop"), preview = $("#new-preview");
  const reset = () => {
    $("#form-new").reset();
    preview.hidden = true;
    $("#new-drop-text").textContent = DROP_TEXT;
    showText("#new-error", "");
  };
  const open = () => { reset(); dlg.showModal(); };
  const showPreview = () => {
    const f = file.files[0];
    if (!f) return;
    preview.src = URL.createObjectURL(f);
    preview.hidden = false;
    $("#new-drop-text").textContent = f.name;
    if (!$("#new-name").value) $("#new-name").value = f.name.replace(/\.[^.]+$/, "");
  };
  file.addEventListener("change", showPreview);
  drop.addEventListener("dragover", e => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", e => {
    e.preventDefault();
    drop.classList.remove("over");
    if (e.dataTransfer.files.length) { file.files = e.dataTransfer.files; showPreview(); }
  });
  $("#btn-new-empty").addEventListener("click", open);
  $("#project-select").addEventListener("change", e => {
    if (e.target.value === "__new") {
      if (state.project) e.target.value = state.project.id;
      open();
    } else openProject(e.target.value);
  });
  $("#new-cancel").addEventListener("click", () => dlg.close());
  $("#form-new").addEventListener("submit", async e => {
    e.preventDefault();
    if (!file.files[0]) { showText("#new-error", "삼면도 이미지를 골라 주세요"); return; }
    const fd = new FormData();
    fd.append("name", $("#new-name").value.trim());
    fd.append("file", file.files[0]);
    try {
      const p = await api("/api/projects", { method: "POST", body: fd });
      dlg.close();
      reset();
      await loadProjects(p.id);
    } catch (ex) { showText("#new-error", ex.message); }
  });
}

/* ---------- 1 · 보기 설정 ---------- */

function renderSettings() {
  const s = state.project.settings;
  const presets = (state.status && state.status.presets) || DEFAULT_PRESETS;
  $("#angle-presets").replaceChildren(...presets.map(p => {
    const b = el("button", "", p.label);
    b.type = "button";
    b.setAttribute("aria-pressed", String(p.deg === s.angle));
    b.addEventListener("click", () => saveSettings({ angle: p.deg }));
    return b;
  }));
  $("#angle").value = s.angle;
  $("#angle-value").textContent = `${s.angle}°`;
  $$("#count-seg button").forEach(b => b.setAttribute("aria-pressed", String(+b.dataset.count === s.count)));
  $$("#style-seg button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.style === s.style)));
  $("#mirror").checked = s.mirror;
  $("#pixel-size-wrap").hidden = s.style !== "pixel";
  $("#pixel-height").value = String(s.pixel_height);
  const gen = generatedFor(s.count, s.mirror);
  const mirrored = dirsFor(s.count).length - gen.length;
  $("#plan-text").textContent = `영상 AI로 만들 방향 ${gen.length}개 (${gen.map(d => ARROWS[d] + d).join(" ")})` +
    (mirrored ? ` · 반전으로 채울 방향 ${mirrored}개` : "");
}

async function saveSettings(patch) {
  const next = { ...state.project.settings, ...patch };
  try {
    state.project = await postJSON(`/api/projects/${state.project.id}/settings`, next);
    showText("#settings-error", "");
    renderProject();
  } catch (e) { showText("#settings-error", e.message); }
}

function setupSettings() {
  const angle = $("#angle");
  angle.addEventListener("input", () => { $("#angle-value").textContent = `${angle.value}°`; });
  angle.addEventListener("change", () => saveSettings({ angle: +angle.value }));
  $$("#count-seg button").forEach(b => b.addEventListener("click", () => saveSettings({ count: +b.dataset.count })));
  $$("#style-seg button").forEach(b => b.addEventListener("click", () => saveSettings({ style: b.dataset.style })));
  $("#mirror").addEventListener("change", e => saveSettings({ mirror: e.target.checked }));
  $("#pixel-height").addEventListener("change", e => saveSettings({ pixel_height: +e.target.value }));
}

/* ---------- 2 · 방향 그림 ---------- */

function renderSheet() {
  const p = state.project, sh = p.sheet, s = p.settings;
  const img = $("#sheet-img"), stateEl = $("#sheet-state");
  $("#btn-sheet").textContent = sh ? "Codex로 다시 그리기" : "Codex로 그리기";
  img.hidden = !sh;
  $("#sheet-empty").hidden = !!sh;
  $("#sheet-btn").disabled = !sh;
  let warn = state.sheetError;
  if (sh) {
    img.src = fileUrl(p.id, sh.file) + `?v=${encodeURIComponent(sh.created)}`;
    const t = sh.settings;
    const differs = t.angle !== s.angle || t.count !== s.count || t.style !== s.style;
    const facing = sh.facing || [];
    const facingText = facing.length
      ? `${facing.map(f => f.dir).join(", ")} 방향이 ${facing[0].looks === "front" ? "앞모습" : "뒷모습"}처럼 보여요. ` +
        "아래 '한 방향만 다시 그리기'로 그 방향만 고칠 수 있어요." : "";
    warn = warn || sh.problem || (differs
      ? `이 그림은 ${t.angle}° · ${t.count}방향 · ${styleName(t.style)}로 그렸어요. 지금 설정으로 쓰려면 다시 그려 주세요.` : "")
      || facingText;
    stateEl.textContent = `${t.count}방향 · ${t.angle}° · ${styleName(t.style)}${sh.uploaded ? " · 직접 올림" : ""}` +
      (sh.fixed ? ` · ${sh.fixed} 다시 그림` : "");
    stateEl.className = "small " + (sh.problem || differs || facing.length ? "warn-text" : "ok-text");
    const sel = $("#redraw-dir"), prev = sel.value;
    sel.replaceChildren(...generatedFor(t.count, t.mirror !== false).map(d => new Option(`${ARROWS[d]} ${d}`, d)));
    sel.value = facing.length ? facing[0].dir : (prev && [...sel.options].some(o => o.value === prev) ? prev : sel.options[0].value);
  } else {
    stateEl.textContent = "3×3 나침반 배치(가운데 비움, 위가 뒷모습)로 그려요.";
    stateEl.className = "small muted";
  }
  showText("#sheet-warn", warn);

  const hist = $("#sheet-history");
  hist.replaceChildren(...p.sheets.slice().reverse().map(rec => {
    const b = el("button");
    b.type = "button";
    b.title = `${rec.created} · ${rec.settings.angle}° · ${rec.settings.count}방향${rec.uploaded ? " · 직접 올림" : ""}`;
    b.setAttribute("aria-current", String(!!sh && rec.file === sh.file));
    const im = el("img");
    im.src = fileUrl(p.id, rec.file);
    im.alt = "이전 방향 그림";
    b.append(im);
    b.addEventListener("click", async () => {
      state.sheetError = "";
      state.project = await postJSON(`/api/projects/${p.id}/sheet/select`, { file: rec.file });
      renderProject();
    });
    return b;
  }));
  hist.hidden = p.sheets.length < 2;

  const box = $("#sheet-job");
  const job = p.active_jobs.find(j => j.kind === "sheet");
  $("#btn-sheet").disabled = !!job;
  $("#redraw-row").hidden = !sh || !!sh.problem;
  $("#btn-redraw").disabled = !!job;
  box.hidden = !job;
  if (job) {
    box.dataset.job = job.id;
    if (state.jobs.has(job.id)) paintJob(job.id, state.jobs.get(job.id));
    watchJob(job.id);
  } else delete box.dataset.job;
}

function setupSheet() {
  $("#btn-sheet").addEventListener("click", async () => {
    state.sheetError = "";
    try {
      await postJSON(`/api/projects/${state.project.id}/sheet`);
      await refreshProject();
    } catch (e) { showText("#sheet-warn", e.message); }
  });
  $("#sheet-file").addEventListener("change", async e => {
    const f = e.target.files[0];
    if (!f) return;
    const fd = new FormData();
    fd.append("file", f);
    state.sheetError = "";
    try {
      state.project = await api(`/api/projects/${state.project.id}/sheet/upload`, { method: "POST", body: fd });
      renderProject();
    } catch (ex) { showText("#sheet-warn", ex.message); }
    e.target.value = "";
  });
  $("#btn-redraw").addEventListener("click", async () => {
    state.sheetError = "";
    $("#btn-redraw").disabled = true;
    try {
      await postJSON(`/api/projects/${state.project.id}/sheet/redraw`, { dir: $("#redraw-dir").value });
      await refreshProject();
    } catch (e) { showText("#sheet-warn", e.message); $("#btn-redraw").disabled = false; }
  });
  $("#sheet-btn").addEventListener("click", () => openImage($("#sheet-img").src, "방향 그림"));
  $("#p-turn-btn").addEventListener("click", () => openImage($("#p-turn").src, "삼면도"));
}

function openImage(src, alt) {
  const im = $("#dlg-image-img");
  im.src = src;
  im.alt = alt;
  $("#dlg-image").showModal();
}

/* ---------- 3 · 동작 만들기 ---------- */

let motionSource = "text", motionKind = "loop", motionMode = "direct", modeTouched = false, submitting = false;
let fxMode = "none", fxTouched = false;

const defaultMode = () => (motionKind === "oneshot" ? "mannequin" : "direct");

/* 빛 효과: 설명에 마법·검기 같은 말이 있으면 '살리기', 아니면 '없음' (직접 고르면 그대로 둔다) */
function autoEffects(text) {
  const words = (state.status && state.status.effect_words) || ["마법", "검기", "번개", "불꽃", "빛", "magic"];
  const t = (text || "").toLowerCase();
  return words.some(w => t.includes(w)) ? "vivid" : "none";
}
function setFx(mode, auto) {
  fxMode = mode;
  $$("#fx-seg button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.fx === mode)));
  $("#fx-hint").textContent = FX_HINT[mode] + (auto && mode !== "none" ? " (설명을 보고 골랐어요)" : "");
}

function setMode(mode) {
  motionMode = mode;
  $$("#mode-cards .mode").forEach(card => {
    const on = card.dataset.mode === mode;
    card.classList.toggle("on", on);
    $("input", card).checked = on;
  });
  suggestFrames();
  updateEta();
}

function updateModeAvailability() {
  $("#mq-desc").textContent = motionSource === "text" ? MQ_DESC.text
    : (state.status && state.status.pose ? MQ_DESC.pose : MQ_DESC.video);
  suggestFrames();
}

/* 칸 수: 영상을 마네킹으로 따라 하는 반복 동작(춤)은 길어서 16장, 나머지는 8장 (직접 고르면 그대로) */
let framesTouched = false;
function suggestFrames() {
  if (framesTouched) return;
  $("#m-frames").value = motionSource === "video" && motionMode === "mannequin" && motionKind === "loop" ? "16" : "8";
}

function setupMotionForm() {
  const press = (sel, attr, val) => $$(sel).forEach(b => b.setAttribute("aria-pressed", String(b.dataset[attr] === val)));
  $$("#source-seg button").forEach(b => b.addEventListener("click", () => {
    motionSource = b.dataset.source;
    press("#source-seg button", "source", motionSource);
    $("#video-wrap").hidden = motionSource !== "video";
    $("#m-text").placeholder = motionSource === "video"
      ? "(선택) 동작에 대한 보충 설명" : "예: 걷기 / 오른손 검을 머리 위로 치켜들었다가 대각선으로 내려베기";
    updateModeAvailability();
    if (!modeTouched) setMode(defaultMode());
    updateEta();
  }));
  $$("#kind-seg button").forEach(b => b.addEventListener("click", () => {
    motionKind = b.dataset.kind;
    press("#kind-seg button", "kind", motionKind);
    if (!modeTouched) setMode(defaultMode());
    suggestFrames();
  }));
  $("#m-frames").addEventListener("change", () => { framesTouched = true; });
  $$("#mode-cards input").forEach(r => r.addEventListener("change", () => {
    if (!r.checked) return;
    modeTouched = true;
    setMode(r.value);
  }));
  setMode("direct");
  $$("#fx-seg button").forEach(b => b.addEventListener("click", () => { fxTouched = true; setFx(b.dataset.fx, false); }));
  $("#m-text").addEventListener("input", () => { if (!fxTouched) setFx(autoEffects($("#m-text").value), true); });
  setFx("none", true);
  $("#form-motion").addEventListener("submit", async e => {
    e.preventDefault();
    showText("#motion-error", "");
    const text = $("#m-text").value.trim();
    const fd = new FormData();
    fd.append("source", motionSource);
    fd.append("kind", motionKind);
    fd.append("text", text);
    fd.append("frames", $("#m-frames").value);
    fd.append("name", $("#m-name").value.trim());
    fd.append("effects", fxMode);
    fd.append("mode", motionMode);
    if (motionSource === "video") {
      const v = $("#m-video").files[0];
      if (!v) { showText("#motion-error", "레퍼런스 영상을 골라 주세요"); return; }
      fd.append("video", v);
    } else if (!text) {
      showText("#motion-error", "동작 설명을 적어 주세요");
      return;
    }
    submitting = true;
    updateEta();
    try {
      const res = await api(`/api/projects/${state.project.id}/motions`, { method: "POST", body: fd });
      $("#m-text").value = "";
      $("#m-name").value = "";
      $("#m-video").value = "";
      fxTouched = false;
      setFx("none", true);
      framesTouched = false;
      suggestFrames();
      state.selected = res.motion.id;
      await refreshProject();
    } catch (ex) { showText("#motion-error", ex.message); }
    submitting = false;
    updateEta();
  });
}

/* 기본 모션 세트: 대기·걷기·달리기·공격·피격·쓰러짐을 한 번에 건다 (공격·피격은 마네킹을 확인 없이 이어서) */
async function setupMotionSet() {
  try { state.setItems = await api("/api/motion_set"); }
  catch { $("#set-box").hidden = true; return; }
  $("#set-items").replaceChildren(...state.setItems.map(it => {
    const lab = el("label", "check");
    const cb = el("input");
    cb.type = "checkbox";
    cb.checked = true;
    cb.value = it.key;
    cb.addEventListener("change", updateSetEta);
    lab.title = it.text;
    lab.append(cb, document.createTextNode(" " + it.name));
    return lab;
  }));
  updateSetEta();
  $("#btn-set").addEventListener("click", async () => {
    const keys = $$("#set-items input:checked").map(c => c.value);
    showText("#set-error", "");
    $("#btn-set").disabled = true;
    try {
      const res = await postJSON(`/api/projects/${state.project.id}/motion_set`, { keys });
      state.selected = res.motions[0].id;
      await refreshProject();
    } catch (e) { showText("#set-error", e.message); }
    updateSetEta();
  });
}

/* 방향 하나 만드는 시간(초). 서버의 default_seconds와 같은 규칙: 텍스트 반복 동작과 마네킹 한 번 동작은 3초 영상이라 빠르다 */
const shortClip = (kind, mode, source, holdEnd) => source !== "video" && !holdEnd
  && ((kind === "loop" && mode === "direct") || (kind === "oneshot" && mode === "mannequin"));
const dirSec = (kind, mode, source, holdEnd) => {
  if (mode === "mannequin") return shortClip(kind, mode, source, holdEnd) ? 120 : SEC_PER_DIR.mannequin;
  return shortClip(kind, mode, source, holdEnd) ? 110 : SEC_PER_DIR[source] || SEC_PER_DIR.text;
};

function updateSetEta() {
  if (!state.project || !state.setItems) return;
  const s = state.project.settings, n = generatedFor(s.count, s.mirror).length;
  const keys = new Set($$("#set-items input:checked").map(c => c.value));
  const sec = state.setItems.filter(it => keys.has(it.key))
    .reduce((a, it) => a + (it.mode === "mannequin" ? 50 : 0) + n * dirSec(it.kind, it.mode, "text", it.hold_end), 0);
  const btn = $("#btn-set");
  btn.textContent = `세트 만들기 (${keys.size}개) · 예상 ${Math.max(1, Math.round(sec / 60))}분`;
  btn.disabled = !state.project.sheet || !keys.size;
}

function updateEta() {
  if (!state.project) return;
  const s = state.project.settings;
  const all = dirsFor(s.count).length;
  const n = generatedFor(s.count, s.mirror).length;
  let sec = n * dirSec(motionKind, motionMode, motionSource, false);
  if (motionMode === "mannequin") sec = 50 + n * dirSec(motionKind, motionMode, motionSource, false);   // 키프레임 짜기 + 터보
  else if (motionMode === "master") sec = SEC_PER_DIR[motionSource] + (n - 1) * SEC_PER_DIR.follow;
  const noSheet = !state.project.sheet;
  const btn = $("#btn-motion");
  btn.textContent = `동작 만들기 · 예상 ${Math.max(1, Math.round(sec / 60))}분`;
  btn.disabled = noSheet || submitting;
  $("#motion-eta").textContent = noSheet ? "먼저 2번에서 방향 그림을 만들어 주세요"
    : `${n}방향 생성${n < all ? ` + 반전 ${all - n}방향` : ""}`;
}

/* ---------- 결과: 동작 탭 ---------- */

function renderResults() {
  const p = state.project;
  const motions = p.motions.slice().reverse();         // 오래된 것부터 (새 동작이 오른쪽 끝)
  if (!motions.some(m => m.id === state.selected)) {
    const pick = p.motions.find(m => m.status === "done") || p.motions[0];
    state.selected = pick ? pick.id : null;
  }
  renderTabs(motions);
  renderMotionView(p, motions.find(m => m.id === state.selected));
  renderActivity(p, motions);
  for (const m of motions) if (m.status === "running" && m.job) watchJob(m.job);
}

function renderTabs(motions) {
  const tabs = motions.map(m => {
    const b = el("button", "tab");
    b.type = "button";
    b.setAttribute("role", "tab");
    b.setAttribute("aria-selected", String(m.id === state.selected));
    const meta = el("span", "tab-meta");
    if (m.status === "running" && m.job) {
      meta.dataset.job = m.job;
      meta.textContent = state.jobs.has(m.job) ? jobShort(state.jobs.get(m.job)) : "만드는 중";
    } else if (m.status === "done") {
      meta.textContent = `${m.kind === "loop" ? "반복" : "한 번"} · ${m.settings.count}방향`;
    } else meta.textContent = STATUS_LABEL[m.status] || m.status;
    b.append(el("span", `dot ${m.status}`), el("span", "tab-name", m.name), meta);
    b.setAttribute("aria-label", `${m.name} (${STATUS_LABEL[m.status] || m.status})`);
    b.addEventListener("click", () => { state.selected = m.id; renderResults(); });
    return b;
  });
  const add = el("button", "tab add", "+ 새 동작");
  add.type = "button";
  add.addEventListener("click", () => {
    $("#h-motion").scrollIntoView({ behavior: "smooth", block: "start" });
    $("#m-text").focus({ preventScroll: true });
  });
  $("#motion-tabs").replaceChildren(...tabs, add);
}

function clearMotionView() {
  if (state.player) { state.player.stop(); state.player = null; }
  const view = $("#motion-view");
  view.replaceChildren();
  delete view.dataset.key;
  $("#exports").hidden = true;
}

function renderMotionView(p, m) {
  const view = $("#motion-view");
  const key = m ? `${p.id}:${m.id}:${m.status}:${m.job || ""}:${m.result ? m.result.finished : ""}` : `${p.id}:none`;
  if (view.dataset.key === key) return;
  clearMotionView();
  view.dataset.key = key;
  if (!m) {
    const box = el("div", "notice");
    box.append(el("p", "", p.sheet
      ? "아직 만든 동작이 없어요. 왼쪽 3번에서 동작을 만들면 여기서 방향별로 재생돼요."
      : "왼쪽 2번에서 방향 그림부터 만들어 주세요. 그다음 3번에서 동작을 만들면 여기서 재생돼요."));
    view.append(box);
  } else if (m.status === "done" && m.result) buildPlayer(view, p, m);
  else if (m.status === "running") view.append(progressCard(p, m, true));
  else if (m.status === "keys_review" || m.status === "review") buildReview(view, p, m);
  else buildFailed(view, p, m);
}

function renderActivity(p, motions) {
  const box = $("#activity");
  const others = motions.filter(m => m.id !== state.selected && ["running", "review", "keys_review"].includes(m.status));
  const key = others.map(m => `${m.id}:${m.status}:${m.job || ""}`).join("|");
  if (box.dataset.key === key) return;
  box.dataset.key = key;
  box.replaceChildren(...others.map(m => progressCard(p, m, false)));
}

/* ---------- 결과: 진행·확인·실패 ---------- */

function progressCard(p, m, big) {
  const card = $("#tpl-progress").content.firstElementChild.cloneNode(true);
  const waiting = m.status !== "running";
  card.classList.toggle("big", big);
  card.classList.toggle("waiting", waiting);
  card.dataset.mid = m.id;
  $(".pc-title", card).textContent = `${m.name} · ${MODE_LABEL[m.mode || "direct"]}`;
  const thumb = $(".pc-thumb", card);
  if (m.mode === "mannequin") {
    thumb.addEventListener("load", () => { thumb.hidden = false; });
    thumb.src = fileUrl(p.id, `motions/${m.id}/keys_preview.gif`) + `?t=${Date.now()}`;
    thumb.alt = "3D 마네킹 미리보기";
  }
  const open = $(".pc-open", card), cancel = $(".pc-cancel", card);
  open.hidden = big;
  open.addEventListener("click", () => { state.selected = m.id; renderResults(); });
  if (waiting) {
    $(".job-msg", card).textContent = m.status === "keys_review" ? "마네킹 확인을 기다려요" : "마스터 확인을 기다려요";
    $(".bar", card).hidden = true;
    cancel.hidden = true;
    return card;
  }
  card.dataset.job = m.job || "";
  $(".job-msg", card).textContent = "준비 중";
  $(".raw-row", card).hidden = !big;
  cancel.addEventListener("click", async () => {
    cancel.disabled = true;
    await postJSON(`/api/jobs/${m.job}/cancel`).catch(() => {});
    refreshProject();
  });
  if (m.job && state.jobs.has(m.job)) paintInto(card, state.jobs.get(m.job));
  return card;
}

function buildReview(view, p, m) {
  const frag = $("#tpl-review").content.cloneNode(true);
  const img = $(".rv-img", frag), go = $(".rv-go", frag), again = $(".rv-again", frag);
  const keys = m.status === "keys_review";
  img.src = fileUrl(p.id, keys ? `motions/${m.id}/keys_preview.gif` : `motions/${m.id}/raw/${m.master}.webp`) + `?t=${Date.now()}`;
  img.alt = keys ? "3D 마네킹 키프레임 미리보기" : "마스터 방향 원본 영상";
  $(".rv-title", frag).textContent = `${m.name} · ${keys ? "마네킹 확인" : "마스터 확인"}`;
  $(".rv-text", frag).textContent = keys
    ? (m.source === "video"
      ? "레퍼런스 영상에서 뽑은 3D 동작이에요. 모든 방향이 이 동작을 그 방향 각도에서 그대로 따라 해요."
      : "Codex가 짠 3D 동작이에요. 모든 방향이 이 동작을 그 방향 각도에서 그대로 따라 해요. 마음에 안 들면 다시 짜게 하세요.")
    : `마스터(${ARROWS[m.master] || ""} ${m.master}) 영상이에요. 나머지 방향이 이 동작을 그대로 따라 해요. 마음에 들면 이어서 만들고, 아니면 마스터를 다시 만드세요.`;
  go.textContent = keys ? "이 동작으로 만들기" : "이 동작으로 나머지 방향 만들기";
  again.textContent = keys ? "키프레임 다시 짜기" : "마스터 다시 만들기";
  again.hidden = keys && m.source === "video";        // 영상에서 뽑은 동작은 다시 뽑아도 같다
  const errBox = $(".rv-error", frag);
  const post = async (url, btn) => {
    btn.disabled = true;
    try { await postJSON(url); await refreshProject(); }
    catch (ex) { errBox.textContent = ex.message; errBox.hidden = false; btn.disabled = false; }
  };
  go.addEventListener("click", () => post(`/api/projects/${p.id}/motions/${m.id}/continue`, go));
  again.addEventListener("click", () => post(`/api/projects/${p.id}/motions/${m.id}/${keys ? "rekeys" : "remaster"}`, again));
  view.append(frag);
}

function buildFailed(view, p, m) {
  const box = el("div", "notice");
  const msg = el("p", "", m.status === "cancelled" ? "중지했어요." :
    m.status === "interrupted" ? "서버가 꺼지면서 중단됐어요. 다시 만들 수 있어요." : "만들다가 실패했어요.");
  const retry = el("button", "primary", "다시 만들기");
  retry.type = "button";
  const err = el("p", "error small");
  err.hidden = true;
  retry.addEventListener("click", async () => {
    retry.disabled = true;
    try { await postJSON(`/api/projects/${p.id}/motions/${m.id}/retry`); await refreshProject(); }
    catch (ex) { err.textContent = ex.message; err.hidden = false; retry.disabled = false; }
  });
  box.append(el("b", "", m.name), msg, retry, err);
  view.append(box);
  if (m.status === "error" && m.job) {
    api(`/api/jobs/${m.job}`).then(j => { if (j.error) msg.textContent = `만들다가 실패했어요: ${j.error}`; }).catch(() => {});
  }
}

function renderParts(box, parts) {
  const names = { queued: "대기", running: "생성 중", done: "완료", unknown: "확인 중", error: "실패" };
  box.replaceChildren(...Object.entries(parts || {}).map(([d, v]) =>
    el("span", `part ${v.state}`, `${ARROWS[d] || ""} ${d} ${names[v.state] || v.state}${v.state === "running" ? " " + mmss(v.sec) : ""}`)));
}

function addRawPreviews(row, p, mid, dirs) {
  for (const d of dirs) {
    if ($(`[data-dir="${d}"]`, row)) continue;
    const fig = el("figure");
    fig.dataset.dir = d;
    const im = el("img");
    im.loading = "lazy";                              // 접힌 '원본 영상'은 펼칠 때 받는다
    im.src = fileUrl(p.id, `motions/${mid}/raw/${d}.webp`) + `?t=${Date.now()}`;
    im.alt = `${d} 방향 원본`;
    fig.append(im, el("figcaption", "", `${ARROWS[d]} ${d}`));
    row.append(fig);
  }
}

/* ---------- 작업 진행 확인 ---------- */

function jobShort(job) {
  const parts = Object.values(job.parts || {});
  if (!parts.length) return job.label === "keys" ? "키프레임 짜는 중" : "준비 중";
  return `생성 중 ${parts.filter(v => v.state === "done").length}/${parts.length}`;
}

function paintInto(box, job) {
  if (box.classList.contains("tab-meta")) { box.textContent = jobShort(job); return; }
  const bar = $(".bar i", box);
  if (bar) bar.style.width = `${Math.max(3, Math.round(job.progress * 100))}%`;
  const msg = $(".job-msg", box);
  if (msg) msg.textContent = `${job.message} · ${mmss(job.elapsed)}`;
  const parts = $(".parts", box);
  if (parts) renderParts(parts, job.parts);
  const raw = $(".raw-row", box);
  if (raw && !raw.hidden && box.dataset.mid && state.project) {
    addRawPreviews(raw, state.project, box.dataset.mid,
      Object.entries(job.parts || {}).filter(([, v]) => v.state === "done").map(([d]) => d));
  }
}

function paintJob(jid, job) {
  $$(`[data-job="${jid}"]`).forEach(box => paintInto(box, job));
}

function watchJob(jid) {
  if (state.polls.has(jid)) return;
  const tick = async () => {
    let job;
    try { job = await api(`/api/jobs/${jid}`); }
    catch { state.polls.delete(jid); return; }
    state.jobs.set(jid, job);
    paintJob(jid, job);
    if (["done", "error", "cancelled"].includes(job.status)) {
      state.polls.delete(jid);
      if (job.kind === "sheet" && job.status === "error") state.sheetError = job.error || "방향 그림을 그리지 못했어요";
      await refreshProject().catch(() => {});
      return;
    }
    state.polls.set(jid, setTimeout(tick, 2000));
  };
  state.polls.set(jid, setTimeout(tick, 0));
}

/* ---------- 결과: 재생기 ---------- */

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const im = new Image();
    im.onload = () => resolve(im);
    im.onerror = () => reject(new Error("이미지를 불러오지 못했어요"));
    im.src = src;
  });
}

class SpritePlayer {
  constructor(canvas, stage, count) {
    this.canvas = canvas;
    this.stage = stage;
    this.ctx = canvas.getContext("2d");
    this.layout = layoutFor(count);
    this.view = "all";
    this.dir = count === 2 ? "E" : "S";
    this.acc = 0;
    this.shown = -1;
    this.ro = new ResizeObserver(() => this.fit());
    this.ro.observe(stage);
  }

  stop() {
    this.ro.disconnect();
    this.meta = null;
  }

  async load(metaUrl, imgUrl, pixel) {
    const [meta, img] = await Promise.all([api(metaUrl), loadImage(imgUrl)]);
    this.meta = meta;
    this.img = img;
    this.pixel = pixel;
    this.n = meta.directions[meta.order[0]].length;
    this.resize();
  }

  resize() {
    const { frame_w: fw, frame_h: fh } = this.meta;
    this.gap = Math.round(fw * 0.06);
    if (this.view === "all") {
      const R = this.layout.length, C = this.layout[0].length;
      this.canvas.width = C * fw + (C - 1) * this.gap;
      this.canvas.height = R * fh + (R - 1) * this.gap;
    } else {
      this.canvas.width = fw;
      this.canvas.height = fh;
    }
    this.canvas.classList.toggle("px", this.pixel);
    this.ctx.imageSmoothingEnabled = !this.pixel;
    this.shown = -1;
    this.fit();
  }

  fit() {
    // 무대 크기에 맞춰 화면 크기만 바꾼다 (HD는 너무 키우면 흐려져서 1.6배까지, 픽셀은 더 키워도 선명)
    if (!this.meta) return;
    const cs = getComputedStyle(this.stage);
    const aw = this.stage.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
    const ah = this.stage.clientHeight - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom);
    if (aw <= 0 || ah <= 0) return;
    const k = Math.min(aw / this.canvas.width, ah / this.canvas.height, this.pixel ? 8 : 1.6);
    this.canvas.style.width = `${Math.floor(this.canvas.width * k)}px`;
    this.canvas.style.height = `${Math.floor(this.canvas.height * k)}px`;
  }

  draw(f) {
    const { ctx, meta, img } = this;
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    const blit = (d, x, y) => {
      const r = meta.directions[d] && meta.directions[d][f];
      if (r) ctx.drawImage(img, r.x, r.y, r.w, r.h, x, y, r.w, r.h);
    };
    if (this.view === "all") {
      this.layout.forEach((row, ri) => row.forEach((d, ci) => {
        if (d) blit(d, ci * (meta.frame_w + this.gap), ri * (meta.frame_h + this.gap));
      }));
    } else blit(this.dir, 0, 0);
  }

  tick(dt) {
    if (!this.meta) return;
    this.acc += dt * this.meta.fps;
    const f = Math.floor(this.acc) % this.n;
    if (f !== this.shown) { this.draw(f); this.shown = f; }
  }
}

function buildPlayer(view, p, m) {
  const frag = $("#tpl-player").content.cloneNode(true);
  const s = m.settings, base = m.result.dir, rep = m.result.report;
  const hasPx = s.style === "pixel";
  const stage = $(".stage", frag);
  const player = new SpritePlayer($("canvas", frag), stage, s.count);
  state.player = player;
  const pref = { view: "all", dir: player.dir, res: hasPx ? "px" : "hd", bg: "dark", ...(state.prefs.get(m.id) || {}) };
  state.prefs.set(m.id, pref);
  player.view = pref.view;
  player.dir = pref.dir;
  const errBox = $(".sv-error", frag);
  const origFps = rep.sprite_fps || 8;               // H3 영상 원래 속도
  let fps = m.play_fps || origFps;                    // 지금 재생 속도 (후처리로 바꾼 값)
  const frames = setupFrames(frag, p, m, player);
  const load = res => {
    pref.res = res;
    updateExports(p, m, res);
    const v = encodeURIComponent(m.result.finished || "");   // 장면을 바꾸면 시트가 새로 만들어진다
    player.load(fileUrl(p.id, `${base}/sheet_${res}.json?v=${v}`), fileUrl(p.id, `${base}/sheet_${res}.png?v=${v}`), res === "px")
      .then(() => { player.meta.fps = fps; frames.render(); })
      .catch(e => { errBox.textContent = e.message; errBox.hidden = false; });
  };

  $(".sv-title", frag).textContent = m.name;
  $(".sv-sub", frag).textContent = `${m.kind === "loop" ? "반복 동작" : "한 번 하는 동작"} · ${s.count}방향 · ` +
    (hasPx ? `픽셀 ${s.pixel_height}px` : "HD");

  const dpad = $(".dpad", frag), viewSeg = $(".sv-view", frag);
  const avail = new Set(dirsFor(s.count));
  const press = () => $$("button", dpad).forEach(b =>
    b.setAttribute("aria-pressed", String(player.view === "one" && b.dataset.dir === player.dir)));
  /* 이 방향만 다시 만들기: 지금 보는 방향(반전 방향이면 원래 방향)만 새로 만들고 시트를 다시 조립한다 */
  const redo = $(".sv-redo", frag), redoMsg = $(".sv-redo-msg", frag);
  const genDirs = generatedFor(s.count, s.mirror);
  const updateRedo = () => {
    const d = player.dir, src = genDirs.includes(d) ? d : MIRROR[d];
    redo.textContent = `${ARROWS[d]} ${d} 방향만 다시 만들기`;
    redo.title = src !== d ? `${d}는 ${src}를 뒤집은 거라 ${src}를 다시 만들어요`
      : "이 방향 영상만 새로 만들고 시트를 다시 조립해요 (2~4분)";
  };
  redo.addEventListener("click", async () => {
    redo.disabled = true;
    showText(".sv-redo-msg", "다시 만드는 중…", redoMsg.parentElement);
    try {
      await postJSON(`/api/projects/${p.id}/motions/${m.id}/redo`, { dir: player.dir });
      await refreshProject();
    } catch (e) { showText(".sv-redo-msg", e.message, redoMsg.parentElement); redo.disabled = false; }
  });
  if (m.redo_error) showText(".sv-redo-msg", `지난번 다시 만들기가 실패했어요: ${m.redo_error}`, redoMsg.parentElement);
  /* 되돌리기: 가장 최근 '이 방향만 다시 만들기' 전 결과와 지금 결과를 맞바꾼다 (한 번 더 누르면 다시 앞으로) */
  const undo = $(".sv-undo", frag), last = (m.versions || []).at(-1);
  if (last) {
    const dirs = last.dirs.join("·");
    undo.hidden = false;
    undo.textContent = last.holds === "previous" ? `↶ ${dirs} 다시 만들기 전으로 되돌리기` : `↷ 다시 만든 ${dirs}로 돌아가기`;
    undo.title = "두 결과를 맞바꿔요. 마음에 드는 쪽으로 언제든 다시 바꿀 수 있어요";
    undo.addEventListener("click", async () => {
      undo.disabled = redo.disabled = true;
      showText(".sv-redo-msg", "바꾸는 중…", redoMsg.parentElement);
      try {
        await postJSON(`/api/projects/${p.id}/motions/${m.id}/versions/${last.id}/swap`, {});
        await refreshProject();
      } catch (e) { showText(".sv-redo-msg", e.message, redoMsg.parentElement); undo.disabled = redo.disabled = false; }
    });
  }
  const goDir = d => {
    player.dir = pref.dir = d;
    player.view = pref.view = "one";
    setSeg(viewSeg, "view", "one");
    if (player.meta) player.resize();
    press();
    updateRedo();
    frames.render();
  };
  COMPASS.flat().forEach(d => {
    if (!d) { dpad.append(el("span")); return; }
    const b = el("button", "", ARROWS[d]);
    b.type = "button";
    b.dataset.dir = d;
    b.title = d;
    b.setAttribute("aria-label", `${d} 방향만 보기`);
    b.disabled = !avail.has(d);
    b.addEventListener("click", () => goDir(d));
    dpad.append(b);
  });
  renderQa($(".sv-qa", frag), rep, goDir);
  updateRedo();
  setSeg(viewSeg, "view", pref.view);
  press();
  segHandler(viewSeg, "view", v => { player.view = pref.view = v; if (player.meta) player.resize(); press(); });
  const resSeg = $(".sv-res", frag);
  resSeg.hidden = !hasPx;
  setSeg(resSeg, "res", pref.res);
  segHandler(resSeg, "res", r => load(r));
  const bgSeg = $(".sv-bg", frag);
  const applyBg = b => {
    pref.bg = b;
    stage.classList.toggle("light", b === "light");
    stage.classList.toggle("checker", b === "checker");
  };
  setSeg(bgSeg, "bg", pref.bg);
  applyBg(pref.bg);
  segHandler(bgSeg, "bg", applyBg);

  setupSpeed(frag, p, m, player, origFps, fps, v => { fps = v; });

  const gen = generatedFor(s.count, s.mirror);
  const all = dirsFor(s.count).length;
  const rows = [
    ["그림 수", `${rep.frames}장`],
    ["생성", `${gen.length}방향${gen.length < all ? ` + 반전 ${all - gen.length}` : ""}`],
    ["방식", `${MODE_LABEL[m.mode || "direct"]}${m.source === "video" ? " · 영상" : ""}`],
    ["보기", `${s.angle}° · ${FX_LABEL[fxOf(m)]}`],
  ];
  $(".stats", frag).replaceChildren(...rows.flatMap(([k, v]) => [el("dt", "", k), el("dd", "", v)]));
  $(".sv-text", frag).textContent = m.text || "";
  addRawPreviews($(".raw-row", frag), p, m.id, gen);
  view.append(frag);
  load(pref.res);
}

/* 자동 점검 결과: 누르면 그 방향으로 가고, 문제가 있는 장은 장면 바꾸기 줄에 노랗게 표시된다 */
function renderQa(box, rep, goDir) {
  if (!Array.isArray(rep.qa)) return;                // 점검 기능이 생기기 전에 만든 동작
  if (!rep.qa.length) { box.append(el("p", "small ok-text", "자동 점검: 문제 없음")); return; }
  box.append(el("p", "small warn-text", `자동 점검: 확인할 곳 ${rep.qa.length}개`));
  for (const q of rep.qa) {
    const which = q.frames && q.frames.length ? ` (${q.frames.map(f => f + 1).join("·")}번째 장)` : "";
    const b = el("button", "ghost small qa-item", `${ARROWS[q.dir] || ""} ${q.dir} · ${QA_TEXT[q.type] || q.type}${which}`);
    b.type = "button";
    b.title = QA_TIP[q.type] || "";
    b.addEventListener("click", () => goDir(q.dir));
    box.append(b);
  }
  box.append(el("p", "small muted", "누르면 그 방향으로 가요. 표시된 장을 눌러 다른 장면으로 바꿀 수 있어요."));
}

/* 장면 바꾸기(후처리): 이상한 장을 H3 영상의 앞뒤 장면 중 하나로 바꾼다. 서버가 시트·GIF를 다시 만든다(30초쯤). */
const MIRROR = { W: "E", SW: "SE", NW: "NE", E: "W", SE: "SW", NE: "NW" };

function setupFrames(frag, p, m, player) {
  const s = m.settings;
  const gen = generatedFor(s.count, s.mirror);
  const strip = $(".fr-strip", frag), title = $(".fr-title", frag), picker = $(".fr-picker", frag);
  const cands = $(".fr-cands", picker), msg = $(".fr-msg", picker);
  let slot = -1, openDir = null;
  const changed = (d, k) => String(k) in (((m.frame_overrides || {})[gen.includes(d) ? d : MIRROR[d]]) || {});
  const flagged = d => new Set((m.result.report.qa || []).filter(q => q.dir === (gen.includes(d) ? d : MIRROR[d]))
    .flatMap(q => q.frames || []));

  function render() {
    if (!player.meta || !player.img) return;
    const d = player.dir, rects = player.meta.directions[d] || [];
    if (!picker.hidden && openDir !== d) { picker.hidden = true; slot = -1; }
    title.textContent = `${ARROWS[d]} ${d} 방향 ${rects.length}장`;
    const qa = flagged(d);
    strip.replaceChildren(...rects.map((r, k) => {
      const b = el("button", "fr-thumb");
      b.type = "button";
      b.setAttribute("aria-label", `${k + 1}번째 장 바꾸기`);
      b.setAttribute("aria-pressed", String(k === slot && !picker.hidden));
      const c = el("canvas");
      c.height = 96;
      c.width = Math.max(1, Math.round(r.w * 96 / r.h));
      const ctx = c.getContext("2d");
      ctx.imageSmoothingEnabled = !player.pixel;
      ctx.drawImage(player.img, r.x, r.y, r.w, r.h, 0, 0, c.width, c.height);
      b.append(c, el("span", "fr-num", String(k + 1)));
      if (changed(d, k)) { b.classList.add("changed"); b.append(el("span", "fr-badge", "바꿈")); }
      else if (qa.has(k)) { b.classList.add("qa-flag"); b.append(el("span", "fr-badge", "확인")); }
      b.addEventListener("click", () => open(k));
      return b;
    }));
  }

  async function open(k) {
    const d = player.dir;
    slot = k;
    openDir = d;
    picker.hidden = false;
    picker.removeAttribute("aria-busy");
    msg.textContent = "";
    render();
    $(".fr-picker-title", picker).textContent = `${ARROWS[d]} ${d} ${k + 1}번째 장을 바꿀 장면을 고르세요`;
    $(".fr-picker-note", picker).textContent = "";
    cands.replaceChildren(el("span", "muted small", "영상 장면을 불러오는 중…"));
    let info;
    try { info = await api(`/api/projects/${p.id}/motions/${m.id}/frames/${d}`); }
    catch (e) { cands.replaceChildren(el("span", "error small", e.message)); return; }
    if (slot !== k || openDir !== d) return;
    $(".fr-picker-note", picker).textContent = "영상 원본이라 빛 궤적이 보여도, 고르면 시트에서는 지워져요." +
      (info.flip ? ` ${d}는 ${info.source}를 좌우로 뒤집은 거라 ${info.source}도 같이 바뀌어요.` : "");
    const cur = info.picked[k];
    const [x0, y0, x1, y1] = m.result.report.cell_crop || [0, 0, 640, 640];
    const items = [];
    for (let fi = Math.max(0, cur - 8); fi <= Math.min(info.files.length - 1, cur + 8); fi++) {
      const off = (fi - cur) / info.fps;
      const b = el("button", "fr-cand" + (fi === cur ? " current" : ""));
      b.type = "button";
      b.setAttribute("aria-label", fi === cur ? "지금 장면" : `${off.toFixed(2)}초 장면으로 바꾸기`);
      const c = el("canvas");
      c.height = 88;
      c.width = Math.max(1, Math.round((x1 - x0) * 88 / (y1 - y0)));
      b.append(c, el("span", "", fi === cur ? "지금" : `${off > 0 ? "+" : ""}${off.toFixed(2)}초`));
      loadImage(fileUrl(p.id, `motions/${m.id}/frames/${info.source}/${info.files[fi]}`)).then(im => {
        const ctx = c.getContext("2d");
        if (info.flip) { ctx.translate(c.width, 0); ctx.scale(-1, 1); }
        ctx.drawImage(im, x0, y0, x1 - x0, y1 - y0, 0, 0, c.width, c.height);
      }).catch(() => {});
      b.addEventListener("click", () => { if (fi !== cur) apply(d, k, fi); });
      items.push(b);
    }
    cands.replaceChildren(...items);
  }

  async function apply(d, k, frame) {
    picker.setAttribute("aria-busy", "true");
    msg.className = "small muted fr-msg";
    msg.textContent = "바꾸는 중… 시트를 다시 만들어서 30초쯤 걸려요";
    try {
      await postJSON(`/api/projects/${p.id}/motions/${m.id}/frames`, { dir: d, slot: k, frame });
      await refreshProject();        // 새 시트로 재생 화면을 다시 그린다 (보던 방향은 그대로)
    } catch (e) {
      picker.removeAttribute("aria-busy");
      msg.className = "small error fr-msg";
      msg.textContent = e.message;
    }
  }

  $(".fr-close", picker).addEventListener("click", () => { picker.hidden = true; slot = -1; render(); });
  $(".fr-reset", picker).addEventListener("click", () => { if (slot >= 0) apply(openDir, slot, null); });
  return { render };
}

/* 재생 속도(후처리): 그림은 그대로, 넘기는 속도만 바꾼다. 손을 떼면 시트 JSON·GIF·ZIP에 저장한다. */
function setupSpeed(frag, p, m, player, origFps, fps, onChange) {
  const slider = $(".sv-speed", frag), val = $(".sv-speed-val", frag);
  const orig = $(".sv-speed-orig", frag), msg = $(".sv-speed-msg", frag);
  const n = m.result.report.frames;
  const secs = f => (n / f).toFixed(1);
  const once = m.kind === "loop" ? "한 바퀴" : "한 번";
  const show = f => {
    const k = f / origFps;
    val.textContent = `${secs(f)}초에 ${once}`;
    orig.textContent = Math.abs(k - 1) < 0.05 ? `원래 속도 (${secs(origFps)}초)`
      : `원래 ${secs(origFps)}초 · ${k.toFixed(1)}배 ${k > 1 ? "빠르게" : "느리게"}`;
  };
  let saving = Promise.resolve();
  const save = f => {
    msg.className = "small muted sv-speed-msg";
    msg.textContent = "저장 중…";
    saving = saving
      .then(() => postJSON(`/api/projects/${p.id}/motions/${m.id}/speed`, { fps: f }))
      .then(() => { m.play_fps = f; msg.textContent = "저장했어요. 받는 GIF·시트·ZIP도 이 속도예요."; })
      .catch(e => { msg.className = "small error sv-speed-msg"; msg.textContent = e.message; });
  };
  const apply = () => {
    const f = Math.round(origFps * +slider.value * 100) / 100;
    onChange(f);
    if (player.meta) player.meta.fps = f;
    show(f);
    return f;
  };
  slider.value = String(Math.min(4, Math.max(0.5, Math.round((fps / origFps) * 10) / 10)));
  show(fps);
  slider.addEventListener("input", apply);
  slider.addEventListener("change", () => save(apply()));
  $(".sv-speed-reset", frag).addEventListener("click", () => { slider.value = "1"; save(apply()); });
}

function updateExports(p, m, res) {
  const base = m.result.dir;
  const safe = (m.name || "motion").replace(/[\\/:*?"<>|]+/g, "_");
  const link = (sel, href, name) => { const a = $(sel); a.href = href; a.download = name; };
  link("#ex-zip", `/api/projects/${p.id}/motions/${m.id}/download`, `${safe}.zip`);
  link("#ex-gif", fileUrl(p.id, `${base}/preview_${res}.gif`), `${safe}_${res}.gif`);
  link("#ex-png", fileUrl(p.id, `${base}/sheet_${res}.png`), `${safe}_${res}.png`);
  link("#ex-json", fileUrl(p.id, `${base}/sheet_${res}.json`), `${safe}_${res}.json`);
  link("#ex-all", `/api/projects/${p.id}/download`, `${(p.name || "character").replace(/[\\/:*?"<>|]+/g, "_")}_all.zip`);
  $("#exports").hidden = false;
}

function setSeg(seg, attr, val) {
  $$("button", seg).forEach(b => b.setAttribute("aria-pressed", String(b.dataset[attr] === val)));
}
function segHandler(seg, attr, fn) {
  $$("button", seg).forEach(b => b.addEventListener("click", () => { setSeg(seg, attr, b.dataset[attr]); fn(b.dataset[attr]); }));
}

let last = performance.now();
function frame(now) {
  const dt = Math.min(0.1, (now - last) / 1000);
  last = now;
  if (state.player && state.player.canvas.isConnected) state.player.tick(dt);
  requestAnimationFrame(frame);
}

/* ---------- 화면 그리기 ---------- */

function renderProject() {
  renderCharacter();
  renderSettings();
  renderSheet();
  renderResults();
  updateEta();
  updateSetEta();
}

function setupConfig() {
  const dlg = $("#dlg-config");
  $("#btn-config").addEventListener("click", () => {
    const st = state.status;
    $("#cfg-url").value = st ? st.config.comfy_url : "";
    $("#cfg-detail").textContent = st
      ? `영상 AI(${st.comfy.backend === "custom" ? "사용자 워크플로" : "H3"}): ${st.comfy.ok ? "사용 가능" : st.comfy.error} · 레퍼런스 영상 모델 ${st.comfy.r2v ? "있음" : "없음"} · ` +
        `Codex: ${st.codex.ok ? st.codex.version : st.codex.error}` : "";
    dlg.showModal();
  });
  $("#form-config").addEventListener("submit", async e => {
    if (e.submitter && e.submitter.value === "save") {
      try {
        await postJSON("/api/config", { comfy_url: $("#cfg-url").value.trim() });
        await loadStatus();
      } catch (ex) { $("#cfg-detail").textContent = ex.message; e.preventDefault(); }
    }
  });
}

async function init() {
  setupNewDialog();
  setupSettings();
  setupSheet();
  setupMotionForm();
  setupMotionSet();
  setupConfig();
  requestAnimationFrame(frame);
  loadStatus();
  setInterval(loadStatus, 30000);
  const list = await loadProjects();
  let lastId = null;
  try { lastId = localStorage.getItem("lastProject"); } catch { /* 무시 */ }
  if (lastId && list.some(p => p.id === lastId)) await openProject(lastId);
  else if (list.length) await openProject(list[0].id);
  else showView("empty");
}

init();
