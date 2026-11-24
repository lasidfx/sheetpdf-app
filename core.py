"""악보 영상 -> PDF 핵심 로직."""
import os
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


def build_pdf(images, out_path, layout="stack", margin=70, gap=40):
    """images: PIL RGB 이미지 리스트.

    layout="stack": A4 세로에 악보를 위에서부터 이어 붙임(인쇄용)
    layout="single": 한 장당 한 페이지(원본 크기)
    """
    if not images:
        raise ValueError("이미지가 없습니다")
    images = [im.convert("RGB") for im in images]

    if layout == "single":
        images[0].save(out_path, "PDF", resolution=150.0, save_all=True, append_images=images[1:])
        return out_path

    pages = []
    page = Image.new("RGB", (A4_W, A4_H), "white")
    y = margin
    cw = A4_W - 2 * margin
    for im in images:
        h = int(im.height * cw / im.width)
        if h > A4_H - 2 * margin:  # 너무 큰 경우 페이지 높이에 맞춤
            h = A4_H - 2 * margin
            cw_i = int(im.width * h / im.height)
        else:
            cw_i = cw
        if y + h > A4_H - margin and y > margin:
            pages.append(page)
            page = Image.new("RGB", (A4_W, A4_H), "white")
            y = margin
        resized = im.resize((cw_i, h), Image.LANCZOS)
        page.paste(resized, ((A4_W - cw_i) // 2, y))
        y += h + gap
    pages.append(page)
    pages[0].save(out_path, "PDF", resolution=150.0, save_all=True, append_images=pages[1:])
    return out_path


def bgr_to_pil(img):
    return Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
