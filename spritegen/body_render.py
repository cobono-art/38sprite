"""사람 3D 모델(Quaternius Universal Base Characters, CC0)을 마네킹 동작(프레임마다 관절 위치)으로 움직여
방향별 레퍼런스 영상으로 그린다. 원통 마네킹보다 사람 몸으로 잘 보여서 영상 AI(H3)가 동작을 더 정확히 따라 한다.

앱 전용 가상환경(.venv-pose: moderngl, pygltflib, opencv)에서 실행한다:
  .venv-pose\\Scripts\\python.exe spritegen/body_render.py <요청.json>
요청: {"poses": "poses.json", "model": "몸.gltf", "hair": "머리카락.gltf" 또는 null, "out": "폴더",
       "dirs": {"S": 0, "E": 90, ...}, "elevation": 45, "size": 640, "scale": 화면px/미터(키 1.62m 기준),
       "center": [0.5, 0.88], "bg": [128, 128, 128], "fps": 24, "name": "mannequin_{d}.mp4"}
poses.json: {"joints": [이름...], "frames": [[[x, y, z] × 관절] × 프레임]}  (+X 캐릭터 왼쪽, +Y 위, +Z 앞, 미터)
색은 무채색 점토로만 칠한다: 알록달록한 마네킹은 H3가 빛나는 효과로 읽어 캐릭터에 분홍 테두리를 그렸다.
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

import cv2
import moderngl
import numpy as np
import pygltflib

COMPONENT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
CLAY = (0.80, 0.79, 0.76)        # 몸: 밝은 무채색 점토
DARK = (0.17, 0.15, 0.14)        # 머리카락·눈썹: 앞뒤를 가르는 어두운 색
MANNEQUIN_HEIGHT = 1.62          # 원통 마네킹 키 (scale이 이 키 기준이라 사람 모델 키로 바꿔 맞춘다)

# 팔다리 뼈: (마네킹 관절 a → b 방향으로 겨눈다, 그 뼈의 자식 뼈)
AIM = {"upperarm_l": ("l_shoulder", "l_elbow", "lowerarm_l"), "lowerarm_l": ("l_elbow", "l_hand", "hand_l"),
       "upperarm_r": ("r_shoulder", "r_elbow", "lowerarm_r"), "lowerarm_r": ("r_elbow", "r_hand", "hand_r"),
       "thigh_l": ("l_hip", "l_knee", "calf_l"), "calf_l": ("l_knee", "l_ankle", "foot_l"), "foot_l": ("l_ankle", "l_toe", "ball_l"),
       "thigh_r": ("r_hip", "r_knee", "calf_r"), "calf_r": ("r_knee", "r_ankle", "foot_r"), "foot_r": ("r_ankle", "r_toe", "ball_r"),
       "neck_01": ("neck", "head", "Head")}
# 몸통 뼈: 골반 방향과 가슴 방향 사이를 나눠 갖는 비율
SPINE = {"pelvis": 0.0, "spine_01": 0.34, "spine_02": 0.67, "spine_03": 1.0}
# 2~3등신 체형(chibi): 뼈마다 길이(자식 관절까지)와 굵기를 바꾼다. 머리는 통째로 키운다.
SEGMENT = {"thigh_l": "leg", "thigh_r": "leg", "calf_l": "leg", "calf_r": "leg",
           "upperarm_l": "arm", "upperarm_r": "arm", "lowerarm_l": "arm", "lowerarm_r": "arm",
           "spine_01": "spine", "spine_02": "spine", "spine_03": "spine", "neck_01": "neck"}
CHIBI = {"head": 2.0, "leg": 0.55, "arm": 0.7, "spine": 0.8, "neck": 0.6, "thick": 1.2}


def _unit(v):
    return v / (np.linalg.norm(v) + 1e-9)


def _frame(across, up):
    y = _unit(up)
    x = _unit(across - y * (across @ y))
    return np.stack([x, y, np.cross(x, y)], axis=1)


def _rot_between(a, b):
    a, b = _unit(a), _unit(b)
    v, c = np.cross(a, b), float(a @ b)
    if c < -0.9999:                                   # 정반대: 아무 수직축으로 180도
        axis = _unit(np.cross(a, [1, 0, 0] if abs(a[0]) < 0.9 else [0, 1, 0]))
        return 2 * np.outer(axis, axis) - np.eye(3)
    k = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + k + k @ k / (1 + c)


def _quat(R):
    w = np.sqrt(max(0.0, 1 + R[0, 0] + R[1, 1] + R[2, 2])) / 2
    x = np.sqrt(max(0.0, 1 + R[0, 0] - R[1, 1] - R[2, 2])) / 2
    y = np.sqrt(max(0.0, 1 - R[0, 0] + R[1, 1] - R[2, 2])) / 2
    z = np.sqrt(max(0.0, 1 - R[0, 0] - R[1, 1] + R[2, 2])) / 2
    x, y, z = np.copysign(x, R[2, 1] - R[1, 2]), np.copysign(y, R[0, 2] - R[2, 0]), np.copysign(z, R[1, 0] - R[0, 1])
    return np.array([w, x, y, z])


def _mat(q):
    w, x, y, z = q / np.linalg.norm(q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _slerp(R0, R1, t):
    q0, q1 = _quat(R0), _quat(R1)
    if q0 @ q1 < 0:
        q1 = -q1
    d = float(np.clip(q0 @ q1, -1, 1))
    if d > 0.9995:
        return _mat(q0 + t * (q1 - q0))
    th = np.arccos(d)
    return _mat((np.sin((1 - t) * th) * q0 + np.sin(t * th) * q1) / np.sin(th))


class Gltf:
    def __init__(self, path):
        self.path = Path(path)
        self.g = pygltflib.GLTF2().load(str(path))
        self.buffers = [(self.path.parent / b.uri).read_bytes() for b in self.g.buffers]
        self.parent = {c: i for i, n in enumerate(self.g.nodes) for c in (n.children or [])}
        self.local = [self._local(n) for n in self.g.nodes]
        self.names = {n.name: i for i, n in enumerate(self.g.nodes)}

    def accessor(self, i):
        a = self.g.accessors[i]
        v = self.g.bufferViews[a.bufferView]
        dt, n = np.dtype(COMPONENT[a.componentType]), NCOMP[a.type]
        start, buf = (v.byteOffset or 0) + (a.byteOffset or 0), self.buffers[v.buffer]
        stride = v.byteStride or dt.itemsize * n
        if stride == dt.itemsize * n:
            arr = np.frombuffer(buf, dt, count=a.count * n, offset=start).reshape(a.count, n)
        else:
            arr = np.stack([np.frombuffer(buf, dt, count=n, offset=start + k * stride) for k in range(a.count)])
        if a.normalized:
            arr = arr.astype(np.float32) / np.iinfo(dt).max
        return arr

    @staticmethod
    def _local(n):
        if n.matrix:
            return np.array(n.matrix, float).reshape(4, 4).T
        M = np.eye(4)
        M[:3, :3] = _mat(np.array([(n.rotation or [0, 0, 0, 1])[3], *(n.rotation or [0, 0, 0, 1])[:3]])) \
            * np.array(n.scale or [1, 1, 1])
        M[:3, 3] = n.translation or [0, 0, 0]
        return M

    def rest_global(self, i):
        M = self.local[i]
        while i in self.parent:
            i = self.parent[i]
            M = self.local[i] @ M
        return M

    def order(self):
        """부모가 자식보다 먼저 오는 노드 순서."""
        seen, out = set(), []

        def visit(i):
            if i in seen:
                return
            if i in self.parent:
                visit(self.parent[i])
            seen.add(i)
            out.append(i)
        for i in range(len(self.g.nodes)):
            visit(i)
        return out

    def parts(self):
        """스킨이 있는 메시 조각: (위치, 법선, uv, 관절 번호(스킨 안), 가중치, 삼각형, 재질 이름, 텍스처 파일)."""
        out = []
        for n in self.g.nodes:
            if n.mesh is None or n.skin is None:
                continue
            for p in self.g.meshes[n.mesh].primitives:
                at = p.attributes
                mat = self.g.materials[p.material] if p.material is not None else None
                tex = None
                if mat and mat.pbrMetallicRoughness.baseColorTexture is not None:
                    img = self.g.images[self.g.textures[mat.pbrMetallicRoughness.baseColorTexture.index].source]
                    tex = self.path.parent / img.uri
                out.append({"pos": self.accessor(at.POSITION).astype(np.float32),
                            "nrm": self.accessor(at.NORMAL).astype(np.float32),
                            "uv": self.accessor(at.TEXCOORD_0).astype(np.float32) if at.TEXCOORD_0 is not None
                            else np.zeros((self.g.accessors[at.POSITION].count, 2), np.float32),
                            "jnt": self.accessor(at.JOINTS_0).astype(np.int64), "wt": self.accessor(at.WEIGHTS_0).astype(np.float32),
                            "idx": self.accessor(p.indices).reshape(-1).astype(np.uint32),
                            "mat": mat.name if mat else "", "tex": tex, "skin": n.skin})
        return out


class Body:
    """사람 모델 하나(+머리카락)를 관절 위치로 움직인다."""

    def __init__(self, model, hair=None, chibi=None):
        self.chibi = chibi
        self.m = Gltf(model)
        skin = self.m.g.skins[0]
        self.joints = skin.joints
        self.ibm = self.m.accessor(skin.inverseBindMatrices).reshape(-1, 4, 4).transpose(0, 2, 1)
        self.rest = {i: self.m.rest_global(i) for i in range(len(self.m.g.nodes))}
        self.order = self.m.order()
        self.parts = self.m.parts()
        for p in self.parts:
            p["jmap"] = np.arange(len(self.joints))
        if hair:                                          # 머리카락: 자기 뼈 이름을 몸의 같은 이름 뼈에 붙인다
            h = Gltf(hair)
            hskin = h.g.skins[0]
            hibm = h.accessor(hskin.inverseBindMatrices).reshape(-1, 4, 4).transpose(0, 2, 1)
            body_joint = {self.m.g.nodes[j].name: k for k, j in enumerate(self.joints)}
            for p in h.parts():
                p["jmap"] = np.array([body_joint.get(h.g.nodes[j].name, 0) for j in hskin.joints])
                p["ibm"] = hibm
                self.parts.append(p)
        for p in self.parts:
            if p["tex"] is not None and not Path(p["tex"]).exists():
                p["tex"] = None
        if chibi:                                         # 체형을 바꾸면 쉬는 자세의 관절 위치도 바뀐다
            self.rest = self._globals(None)
        pts = np.concatenate([self._skin(p, self._rest_mats())[0] for p in self.parts])
        self.height = float(pts[:, 1].max() - pts[:, 1].min())
        g = lambda n: self.rest[self.m.names[n]][:3, 3]   # noqa: E731
        self.rest_pelvis_frame = _frame(g("thigh_l") - g("thigh_r"), g("spine_03") - g("pelvis"))
        self.rest_chest_frame = _frame(g("upperarm_l") - g("upperarm_r"), g("neck_01") - g("pelvis"))

    def _rest_mats(self):
        return np.stack([self.rest[j] @ self._shape(j) @ self.ibm[k] for k, j in enumerate(self.joints)])

    def _shape(self, i):
        """2~3등신: 이 뼈의 메시를 뼈 방향(로컬 Y)으로 늘리거나 줄이고 굵게, 머리는 통째로 키운다."""
        if not self.chibi:
            return np.eye(4)
        name = self.m.g.nodes[i].name
        S = np.eye(4)
        if name == "Head":
            S[:3, :3] *= self.chibi["head"]
        elif name in SEGMENT:
            t = self.chibi.get("thick", 1.0)
            S[:3, :3] = np.diag([t, self.chibi[SEGMENT[name]], t])
        return S

    def _local(self, i):
        """부모 뼈 길이를 바꾼 만큼 이 관절의 자리(부모에서 본 위치)도 옮긴다."""
        L = self.m.local[i]
        parent = self.m.parent.get(i)
        if self.chibi and parent is not None and self.m.g.nodes[parent].name in SEGMENT:
            L = L.copy()
            L[:3, 3] *= self.chibi[SEGMENT[self.m.g.nodes[parent].name]]
        return L

    def _globals(self, P):
        """관절마다 전역 변환. P(마네킹 관절 위치)를 주면 몸통·팔다리를 그 방향으로 돌린다."""
        names = self.m.g.nodes
        if P is not None:
            dp = _frame(P["l_hip"] - P["r_hip"], P["chest"] - P["pelvis"]) @ self.rest_pelvis_frame.T
            dc = _frame(P["l_shoulder"] - P["r_shoulder"], P["neck"] - P["pelvis"]) @ self.rest_chest_frame.T
        G = {}
        for i in self.order:
            parent = self.m.parent.get(i)
            M = (G[parent] if parent is not None else np.eye(4)) @ self._local(i)
            name = names[i].name
            if P is not None and name in SPINE:
                M = M.copy()
                M[:3, :3] = _slerp(dp, dc, SPINE[name]) @ self.rest[i][:3, :3]
            elif P is not None and name in AIM:
                a, b, child = AIM[name]
                cur = M[:3, :3] @ self._local(self.m.names[child])[:3, 3]
                M = M.copy()
                M[:3, :3] = _rot_between(cur, P[b] - P[a]) @ M[:3, :3]
            G[i] = M
        return G

    def pose(self, P):
        """마네킹 관절 위치 → 몸 뼈마다 전역 변환 → 스키닝 행렬."""
        G = self._globals(P)
        return np.stack([G[j] @ self._shape(j) @ self.ibm[k] for k, j in enumerate(self.joints)]), G

    def _skin(self, p, mats, own=None):
        M = mats[p["jmap"]] if own is None else own
        if "ibm" in p and own is None:                    # 머리카락은 자기 역바인드 행렬을 쓴다
            M = M @ np.linalg.inv(self.ibm[p["jmap"]]) @ p["ibm"]
        W = p["wt"] / (p["wt"].sum(axis=1, keepdims=True) + 1e-9)
        Mv = np.einsum("vk,vkij->vij", W, M[p["jnt"]])
        pos = np.einsum("vij,vj->vi", Mv[:, :3, :3], p["pos"]) + Mv[:, :3, 3]
        nrm = np.einsum("vij,vj->vi", Mv[:, :3, :3], p["nrm"])
        return pos, nrm / (np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-9)

    def skinned(self, P):
        mats, _ = self.pose(P)
        out = [self._skin(p, mats) for p in self.parts]
        low = min(float(pos[:, 1].min()) for pos, _ in out)      # 발이 땅(y=0)에 닿게
        return [(pos - [0, low, 0], nrm) for pos, nrm in out]


VERT = """
#version 330
in vec3 in_pos; in vec3 in_nrm; in vec2 in_uv;
out vec3 v_nrm; out vec2 v_uv;
void main() { gl_Position = vec4(in_pos, 1.0); v_nrm = in_nrm; v_uv = in_uv; }
"""
FRAG = """
#version 330
in vec3 v_nrm; in vec2 v_uv;
uniform vec3 albedo; uniform bool use_tex; uniform sampler2D tex;
out vec4 f;
void main() {
    vec3 n = normalize(v_nrm);
    float d = max(dot(n, normalize(vec3(-0.45, 0.65, 0.62))), 0.0);
    float fill = max(dot(n, normalize(vec3(0.6, 0.2, 0.75))), 0.0);
    float rim = pow(1.0 - clamp(n.z, 0.0, 1.0), 3.0);
    vec3 base = use_tex ? texture(tex, v_uv).rgb : albedo;
    f = vec4(base * (0.30 + 0.62 * d + 0.18 * fill) + rim * 0.10, 1.0);
}
"""


class Renderer:
    def __init__(self, size, ss=2):
        self.size, self.ss = size, ss
        self.ctx = moderngl.create_standalone_context()
        self.prog = self.ctx.program(vertex_shader=VERT, fragment_shader=FRAG)
        S = size * ss
        self.fbo = self.ctx.framebuffer(self.ctx.renderbuffer((S, S)), self.ctx.depth_renderbuffer((S, S)))
        self.tex = {}

    def texture(self, path):
        if path not in self.tex:
            # cv2.imread는 한글 경로를 못 읽어서 바이트로 읽어 푼다
            im = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)[:, :, ::-1].copy()
            t = self.ctx.texture((im.shape[1], im.shape[0]), 3, im.tobytes())
            t.build_mipmaps()
            self.tex[path] = t
        return self.tex[path]

    def draw(self, parts, skinned, yaw, elevation, scale, center, bg):
        a, e = np.radians(yaw), np.radians(elevation)
        Ry = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
        V = np.array([[1, 0, 0], [0, np.cos(e), -np.sin(e)], [0, np.sin(e), np.cos(e)]]) @ Ry
        S = self.size * self.ss
        self.fbo.use()
        self.ctx.enable(moderngl.DEPTH_TEST)
        self.fbo.clear(bg[0] / 255, bg[1] / 255, bg[2] / 255, 1.0, depth=1.0)
        cx, cy = center[0] * S, center[1] * S
        for p, (pos, nrm) in zip(parts, skinned):
            q, n = pos @ V.T, nrm @ V.T
            ndc = np.stack([(cx + q[:, 0] * scale * self.ss) / S * 2 - 1, 1 - (cy - q[:, 1] * scale * self.ss) / S * 2,
                            -q[:, 2] / 6.0], axis=1)
            data = np.hstack([ndc, n, p["uv"]]).astype("f4")
            vbo = self.ctx.buffer(data.tobytes())
            ibo = self.ctx.buffer(p["idx"].tobytes())
            vao = self.ctx.vertex_array(self.prog, [(vbo, "3f 3f 2f", "in_pos", "in_nrm", "in_uv")], ibo)
            dark = "hair" in p["mat"].lower() or "brow" in p["mat"].lower()
            eyes = "eye" in p["mat"].lower() and p["tex"] is not None
            self.prog["use_tex"].value = bool(eyes)
            self.prog["albedo"].value = DARK if dark else CLAY
            if eyes:
                self.texture(p["tex"]).use(0)
                self.prog["tex"].value = 0
            vao.render(moderngl.TRIANGLES)
            vao.release(), vbo.release(), ibo.release()
        img = np.frombuffer(self.fbo.read(components=3), np.uint8).reshape(S, S, 3)[::-1]
        return cv2.resize(img, (self.size, self.size), interpolation=cv2.INTER_AREA)


def main():
    req = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    data = json.loads(Path(req["poses"]).read_text(encoding="utf-8"))
    names = data["joints"]
    poses = [{n: np.asarray(v, float) for n, v in zip(names, f)} for f in data["frames"]]
    body = Body(req["model"], req.get("hair"), req.get("chibi"))
    scale = req["scale"] * MANNEQUIN_HEIGHT / body.height
    skinned = [body.skinned(P) for P in poses]
    ren = Renderer(req["size"])
    out = Path(req["out"])
    out.mkdir(parents=True, exist_ok=True)
    files = {}
    tmp = Path(tempfile.mkdtemp(prefix="38sprite_body_"))      # 한글 경로에 바로 쓰지 못하는 경우가 있어 임시로 쓴 뒤 옮긴다
    for d, yaw in req["dirs"].items():
        path = out / req.get("name", "mannequin_{d}.mp4").format(d=d)
        writer = cv2.VideoWriter(str(tmp / f"{d}.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), req.get("fps", 24),
                                 (req["size"], req["size"]))
        for sk in skinned:
            writer.write(ren.draw(body.parts, sk, yaw, req["elevation"], scale, req["center"], req["bg"])[:, :, ::-1])
        writer.release()
        shutil.move(str(tmp / f"{d}.mp4"), str(path))
        files[d] = str(path)
    shutil.rmtree(tmp, ignore_errors=True)
    print(json.dumps({"files": files, "height": body.height}), flush=True)


if __name__ == "__main__":
    main()
