"""악보 영상 -> PDF 핵심 로직."""
import os
import re
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image


# ---------------------------------------------------------------- 다운로드
def download_video(url: str, out_dir: str, max_height: int = 1080, progress_cb=None):
    """유튜브 영상(영상 스트림만, 소리 제외)을 내려받아 (경로, 제목)을 돌려준다.

    영상 스트림만 받기 때문에 ffmpeg 없이도 동작한다.
    """
    import yt_dlp

    os.makedirs(out_dir, exist_ok=True)

    def hook(d):
        if progress_cb and d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            if total:
                progress_cb(min(d.get("downloaded_bytes", 0) / total, 1.0))

    opts = {
        "format": (
            f"bv*[vcodec^=avc1][height<={max_height}]"
            f"/bv*[height<={max_height}]/b[height<={max_height}]/best"
        ),
        "outtmpl": os.path.join(out_dir, "video.%(ext)s"),
        "noplaylist": True,  # 링크에 list=... 가 붙어 있어도 영상 1개만
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = ydl.prepare_filename(info)
    download_video.last_info = info
    return path, info.get("title", "sheet")


# ---------------------------------------------------------------- 프레임 유틸
@dataclass
class Crop:
    top: float = 0.55      # 0~1, 영상 높이 기준 위쪽 경계
    bottom: float = 1.0
    left: float = 0.0
    right: float = 1.0

    def apply(self, frame):
        h, w = frame.shape[:2]
        y0, y1 = int(h * self.top), int(h * self.bottom)
        x0, x1 = int(w * self.left), int(w * self.right)
        return frame[y0:y1, x0:x1]


def video_info(path):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return dict(fps=fps, frames=int(n), duration=n / fps if fps else 0, width=w, height=h)


def read_frame_at(path, sec):
    cap = cv2.VideoCapture(path)
    cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000)
    ok, frame = cap.read()
    cap.release()
    return frame if ok else None


def _small_gray(img, width=320):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h = max(1, int(g.shape[0] * width / g.shape[1]))
    return cv2.resize(g, (width, h), interpolation=cv2.INTER_AREA)


def _diff(a, b):
    """두 작은 회색조 이미지에서 '많이 달라진 픽셀'의 비율(0~1)."""
    if a.shape != b.shape:
        b = cv2.resize(b, (a.shape[1], a.shape[0]))
    return float(np.mean(cv2.absdiff(a, b) > 40))


def _is_blank(gray):
    """검은/흰 화면 등 내용이 거의 없는 프레임."""
    return float(gray.std()) < 12


# ---------------------------------------------------------------- 악보 추출
def extract_pages(
    video_path,
    crop: Crop,
    interval=0.5,
    change_thr=0.05,
    stable_thr=0.02,
    dup_thr=0.02,
    max_wait=8,
    progress_cb=None,
):
    """악보 영역이 바뀔 때마다(페이지 넘김/스크롤) 한 장씩 캡처한다.

    - 마지막으로 저장한 장과 change_thr 이상 달라지면 '새 페이지 후보'
    - 화면이 안정(전환 효과 끝)되면 저장. 계속 움직이면 max_wait 샘플 뒤 저장
    - 이미 저장한 어떤 장과 dup_thr 미만이면 중복으로 보고 버림
    - 연주 위치 표시(커서)처럼 작은 변화는 change_thr 아래라 무시됨

    반환: [(시간(초), BGR 이미지), ...] 영상 순서대로
    """
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    step = max(1, int(round(fps * interval)))

    pages = []          # (t, img)
    page_smalls = []    # 비교용
    last_saved = None
    prev = None
    pending = None      # (t, img, small)
    waited = 0
    idx = 0

    def commit(t, img, small):
        nonlocal last_saved
        last_saved = small
        for s in page_smalls:
            if _diff(s, small) < dup_thr:
                return
        pages.append((t, img))
        page_smalls.append(small)

    while True:
        if not cap.grab():
            break
        if idx % step == 0:
            ok, frame = cap.retrieve()
            if ok:
                t = idx / fps
                img = crop.apply(frame)
                small = _small_gray(img)
                if not _is_blank(small):
                    if last_saved is None:
                        # 첫 유효 프레임: 안정될 때까지 기다렸다가 저장
                        if prev is not None and _diff(prev, small) < stable_thr:
                            commit(t, img, small)
                    else:
                        changed = _diff(last_saved, small) >= change_thr
                        if changed:
                            stable = prev is not None and _diff(prev, small) < stable_thr
                            waited = waited + 1 if pending else 1
                            pending = (t, img, small)
                            if stable or waited >= max_wait:
                                commit(*pending)
                                pending, waited = None, 0
                        else:
                            pending, waited = None, 0
                prev = small
                if progress_cb and total:
                    progress_cb(min(idx / total, 1.0))
        idx += 1
    cap.release()
    return pages


# ---------------------------------------------------------------- PDF
A4_W, A4_H = 1240, 1754  # 150dpi
DEBUG = False


def build_pdf(images, out_path, layout="stack", margin=70, gap=40, song="", artist=""):
    """images: PIL RGB 이미지 리스트.

    layout="stack": A4 세로에 악보를 위에서부터 이어 붙임(인쇄용)
    layout="single": 한 장당 한 페이지(원본 크기)
    """
    if not images:
        raise ValueError("이미지가 없습니다")
    images = [im.convert("RGB") for im in images]

    if layout == "single":
        hd = header_image(song, artist, images[0].width, images[0].width / A4_W * 1.4)
        if hd is not None:
            first = Image.new("RGB", (images[0].width, hd.height + images[0].height), "white")
            first.paste(hd, (0, 0))
            first.paste(images[0], (0, hd.height))
            images[0] = first
        images[0].save(out_path, "PDF", resolution=150.0, save_all=True, append_images=images[1:])
        return out_path

    pages = []
    page = Image.new("RGB", (A4_W, A4_H), "white")
    y = margin
    cw = A4_W - 2 * margin
    scale = cw / max(im.width for im in images)  # 모든 줄을 같은 배율로
    hd = header_image(song, artist, cw)
    if hd is not None:
        page.paste(hd, (margin, y))
        y += hd.height + gap // 2
    for im in images:
        cw_i, h = int(im.width * scale), int(im.height * scale)
        if h > A4_H - 2 * margin:  # 너무 큰 경우 페이지 높이에 맞춤
            h = A4_H - 2 * margin
            cw_i = int(im.width * h / im.height)
        if y + h > A4_H - margin and y > margin:
            pages.append(page)
            page = Image.new("RGB", (A4_W, A4_H), "white")
            y = margin
        resized = im.resize((cw_i, h), Image.LANCZOS)
        page.paste(resized, (margin if cw_i < cw else (A4_W - cw_i) // 2, y))
        y += h + gap
    pages.append(page)
    pages[0].save(out_path, "PDF", resolution=150.0, save_all=True, append_images=pages[1:])
    return out_path


def bgr_to_pil(img):
    return Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))


# ---------------------------------------------------------------- 겹침 제거
def _ink(img):
    """악보 잉크(검은 선·음표)만 1, 나머지(흰 배경, 노란 하이라이트 등) 0."""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return (g < 140).astype(np.float32)


def find_overlap(a, b, min_frac=0.06, strip_frac=0.15, thr=0.65, shift_frac=0.1):
    """b의 앞부분이 a의 끝부분과 겹치면 (방향, 픽셀)을 돌려준다.

    방향 'x': 가로 스크롤(b의 왼쪽 px만큼이 a 오른쪽 끝과 같음)
    방향 'y': 세로 스크롤(b의 위쪽 px만큼이 a 아래쪽 끝과 같음)
    수직/수평으로 약간 어긋나 있어도(shift_frac) 찾는다. 겹침이 없으면 None.
    """
    if a.shape != b.shape:
        return None
    h, w = a.shape[:2]
    A = cv2.GaussianBlur(_ink(a), (5, 5), 0)
    B = cv2.GaussianBlur(_ink(b), (5, 5), 0)
    best = None
    for axis in ("x", "y"):
        n, m = (w, h) if axis == "x" else (h, w)
        sw = max(8, int(n * strip_frac))
        mg = max(2, int(m * shift_frac))
        if axis == "x":
            tmpl, off = B[mg:h - mg, :sw], mg
        else:
            tmpl, off = B[:sw, mg:w - mg], mg
        if tmpl.sum() < 20 or tmpl.std() < 1e-3:
            continue
        res = cv2.matchTemplate(A, tmpl, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(res)
        pos, shift = (loc[0], loc[1] - off) if axis == "x" else (loc[1], loc[0] - off)
        ov = n - pos
        if pos <= 0 or score < thr or ov < n * min_frac or ov >= n * 0.97:
            continue
        # 겹친다고 본 구간 전체가 정말 같은지 확인 (어긋남 보정)
        M = np.float32([[1, 0, shift], [0, 1, 0]]) if axis == "y" else np.float32([[1, 0, 0], [0, 1, shift]])
        Bs = cv2.warpAffine(B, M, (w, h))
        ra = A[:, pos:] if axis == "x" else A[pos:, :]
        rb = Bs[:, :ov] if axis == "x" else Bs[:ov, :]
        inner = slice(mg, (h if axis == "x" else w) - mg)
        ra, rb = (ra[inner, :], rb[inner, :]) if axis == "x" else (ra[:, inner], rb[:, inner])
        ink = (ra > 0.3) | (rb > 0.3)
        if ink.sum() == 0:
            continue
        mismatch = float(np.mean(np.abs(ra - rb)[ink] > 0.5))
        if mismatch < 0.12 and (best is None or score > best[2]):
            best = (axis, ov, score, mismatch)
    if best and DEBUG: print("overlap", best)
    return best[:2] if best else None


def barlines(img):
    """세로 마디선 x 좌표 목록."""
    ink = _ink(img)
    col = ink.sum(0)
    if col.max() <= 0:
        return []
    med = float(np.median(col))
    th = med + 0.6 * (col.max() - med)
    xs = [x for x in range(len(col)) if col[x] >= th and col[x] >= ink.shape[0] * 0.25]
    out = []
    for x in xs:  # 붙어 있는 열은 하나로
        if not out or x - out[-1] > 3:
            out.append(x)
    return out


def remove_overlaps(pages):
    """[(t, img)] 에서 바로 앞 장과 겹치는 부분을 잘라낸다.

    가로 겹침은 마디선에 맞춰 자르고(앞 장 끝도 같은 마디선까지로 정리),
    반환: (새 pages, joins) — joins[i]=True 이면 i번은 앞 장에 가로로 이어지는 조각.
    """
    out, joins = [], []
    prev_full = None
    for t, img in pages:
        ov = find_overlap(prev_full, img) if prev_full is not None else None
        prev_full = img
        if not ov:
            out.append((t, img))
            joins.append(False)
            continue
        axis, px = ov
        if axis == "y":
            out.append((t, img[px:, :]))
            joins.append(False)
            continue
        w = img.shape[1]
        pos = w - px  # b의 x=0 이 a의 x=pos
        cut = px
        near = [x for x in barlines(img) if px - w * 0.25 <= x <= px + 2]
        if near:
            cut = near[-1]
            pt, pimg = out[-1]
            keep_a = min(pimg.shape[1], cut + pos - (img.shape[1] - pimg.shape[1]))
            # 앞 조각이 이미 잘린 경우를 고려해 오른쪽 끝에서부터 계산
            trim = img.shape[1] - (cut + pos)
            if 0 < trim < pimg.shape[1]:
                out[-1] = (pt, pimg[:, : pimg.shape[1] - trim])
        out.append((t, img[:, cut:]))
        joins.append(True)
    return out, joins


def wrap_strip(strip, row_w):
    """긴 가로 악보 줄을 row_w 폭 안에서 마디선 기준으로 잘라 여러 줄로."""
    rows, x0, W = [], 0, strip.shape[1]
    bl = barlines(strip)
    while W - x0 > row_w:
        cands = [x for x in bl if x0 + row_w * 0.5 < x <= x0 + row_w]
        x1 = cands[-1] if cands else x0 + row_w
        rows.append(strip[:, x0:x1 + 1])
        x0 = x1
    rows.append(strip[:, x0:])
    return rows


def merge_rows(bgr_images, joins, row_w=None):
    """가로로 이어지는 조각을 한 줄로 합친 뒤 원래 폭 기준으로 다시 줄바꿈."""
    if not bgr_images:
        return []
    row_w = row_w or max(i.shape[1] for i in bgr_images)
    strips = []
    for img, j in zip(bgr_images, joins):
        if j and strips and strips[-1].shape[0] == img.shape[0]:
            strips[-1] = np.hstack([strips[-1], img])
        else:
            strips.append(img)
    rows = []
    for s in strips:
        rows += wrap_strip(s, row_w) if s.shape[1] > row_w else [s]
    return rows


# ---------------------------------------------------------------- 곡 제목 / 원곡자
_NOISE = re.compile(
    r"\[[^\]]*\]|\([^)]*\)|【[^】]*】|「[^」]*」"
    r"|\b(bass|guitar|piano|drum|violin|ukulele|flute|sax)\s*(tab|tabs|cover|sheet\s*music|sheet|score|tutorial|lesson)?\b"
    r"|\b(tab|tabs|sheet\s*music|sheet|score|cover|tutorial|lesson|playthrough|lyrics?|mv|m/v|official|audio|with)\b"
    r"|악보|타브|커버|연주|베이스|기타|피아노|드럼|레슨|강좌",
    re.I,
)


def _clean(s):
    s = _NOISE.sub(" ", s or "")
    s = re.sub(r"[|#/]+.*$", " ", s)
    return re.sub(r"\s+", " ", s).strip(" -–—:·,'\"")


def guess_song(info):
    """yt-dlp 정보에서 (곡 제목, 원곡자) 추정. 모르면 빈 문자열."""
    info = info or {}
    track, artist = info.get("track"), info.get("artist") or info.get("creator")
    if track:
        return track.strip(), (artist or "").split(",")[0].strip()
    title = info.get("title") or ""
    for sep in (" - ", " – ", " — ", " _ "):
        if sep in title:
            left, right = title.split(sep, 1)
            a, t = _clean(left), _clean(right)
            if a and t:
                return t, a
    return _clean(title) or title, ""


def _font(size):
    from PIL import ImageFont
    cands = [
        "C:/Windows/Fonts/malgunbd.ttf", "C:/Windows/Fonts/malgun.ttf",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc", "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
        "/Library/Fonts/AppleGothic.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for c in cands:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except Exception:  # noqa: BLE001
                pass
    return ImageFont.load_default(size)


def header_image(song, artist, width, scale=1.0):
    """제목(가운데, 크게) + 원곡자(오른쪽) 머리글 이미지."""
    from PIL import ImageDraw
    song, artist = (song or "").strip(), (artist or "").strip()
    if not song and not artist:
        return None
    ft, fa = _font(int(56 * scale)), _font(int(30 * scale))
    pad = int(20 * scale)
    h = pad + (int(70 * scale) if song else 0) + (int(44 * scale) if artist else 0) + pad
    img = Image.new("RGB", (width, h), "white")
    d = ImageDraw.Draw(img)
    y = pad
    if song:
        # 너무 길면 글자 크기 줄이기
        size = int(56 * scale)
        while size > 20 and d.textlength(song, font=ft) > width * 0.9:
            size -= 4
            ft = _font(size)
        d.text((width / 2, y), song, font=ft, fill="black", anchor="mt")
        y += int(70 * scale)
    if artist:
        d.text((width - pad, y), artist, font=fa, fill=(60, 60, 60), anchor="rt")
    return img
