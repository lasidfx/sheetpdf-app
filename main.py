"""악보 영상 → PDF : 단일 실행 앱. 실행하면 브라우저가 열린다."""
import os
import socket
import tempfile
import threading
import uuid
import webbrowser

import cv2
from flask import Flask, Response, jsonify, request, send_file

import core
import storage
from ui import HTML

app = Flask(__name__)
S = {"workdir": tempfile.mkdtemp(prefix="sheetpdf_"), "video": None, "title": "", "pages": [], "joins": [], "pdf": None, "info": None}
JOBS = {}


def run_job(fn):
    jid = uuid.uuid4().hex[:8]
    JOBS[jid] = {"status": "running", "progress": 0.0, "result": None, "error": None}

    def work():
        try:
            JOBS[jid]["result"] = fn(lambda p: JOBS[jid].__setitem__("progress", p))
            JOBS[jid]["status"] = "done"
        except Exception as e:  # noqa: BLE001
            JOBS[jid]["status"], JOBS[jid]["error"] = "error", str(e)

    threading.Thread(target=work, daemon=True).start()
    return jid


@app.get("/")
def index():
    return Response(HTML, mimetype="text/html")


@app.get("/api/config")
def config():
    return jsonify(instruments=storage.INSTRUMENTS, drive_root=storage.detect_drive_folder())


@app.get("/api/job/<jid>")
def job(jid):
    return jsonify(JOBS.get(jid, {"status": "error", "progress": 0, "error": "unknown job"}))


@app.post("/api/load")
def load():
    d = request.json

    def fn(cb):
        path, title = core.download_video(d["url"], os.path.join(S["workdir"], "dl_" + uuid.uuid4().hex[:6]), d.get("quality", 720), cb)
        S.update(video=path, title=title, pages=[], pdf=None, info=core.video_info(path))
        song, artist = core.guess_song(getattr(core.download_video, "last_info", {"title": title}))
        return dict(title=title, guess=storage.guess_instrument(title), song=song, artist=artist, **S["info"])

    return jsonify(job=run_job(fn))


@app.get("/api/frame")
def frame():
    if not S["video"]:
        return "", 404
    a = request.args
    f = core.read_frame_at(S["video"], float(a.get("t", 0)))
    if f is None:
        return "", 404
    h, w = f.shape[:2]
    if a.get("box") != "0":
        c = core.Crop(int(a["top"]) / 100, int(a["bottom"]) / 100, int(a["left"]) / 100, int(a["right"]) / 100)
        cv2.rectangle(f, (int(w * c.left), int(h * c.top)), (int(w * c.right) - 1, int(h * c.bottom) - 1), (0, 0, 255), max(2, w // 300))
    nw = min(w, 1280)
    f = cv2.resize(f, (nw, int(h * nw / w)))
    return Response(cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes(), mimetype="image/jpeg")


@app.post("/api/extract")
def extract():
    d = request.json
    crop = core.Crop(d["top"], d["bottom"], d["left"], d["right"])

    def fn(cb):
        pages = core.extract_pages(S["video"], crop, interval=d["interval"], change_thr=d["change"], dup_thr=d["dup"], progress_cb=cb)
        if d.get("overlap", True):
            pages, joins = core.remove_overlaps(pages)
        else:
            joins = [False] * len(pages)
        S["pages"], S["joins"] = pages, joins
        return dict(count=len(pages), times=[t for t, _ in pages], joins=joins)

    return jsonify(job=run_job(fn))


@app.get("/api/page/<int:i>")
def page(i):
    img = S["pages"][i][1]
    return Response(cv2.imencode(".png", img)[1].tobytes(), mimetype="image/png")


@app.post("/api/finish")
def finish():
    d = request.json
    keep = d.get("keep") or []
    if not keep:
        return jsonify(error="선택된 악보가 없습니다")
    keep = sorted(keep)
    joins = [bool(S["joins"][i]) and k > 0 and keep[k - 1] == i - 1 for k, i in enumerate(keep)]
    rows = core.merge_rows([S["pages"][i][1] for i in keep], joins, max(p[1].shape[1] for p in S["pages"]))
    imgs = [core.bgr_to_pil(r) for r in rows]
    name = storage.safe_name(S["title"])
    out = os.path.join(S["workdir"], name + ".pdf")
    core.build_pdf(imgs, out, d.get("layout", "stack"), song=d.get("song", ""), artist=d.get("artist", ""))
    S["pdf"] = (out, name + ".pdf")
    inst = d.get("instrument") or "기타"
    try:
        if d["mode"] == "folder":
            root = d.get("root", "")
            if not root or not os.path.isdir(root):
                return jsonify(error="드라이브 폴더 경로를 확인하세요. (PDF는 다운로드할 수 있습니다)", pdf=True)
            saved = "저장됨: " + storage.save_local(root, inst, S["title"], imgs, out)
        elif d["mode"] == "api":
            saved = "업로드됨: " + storage.save_drive_api(inst, S["title"], imgs, out)
        else:
            saved = ""
    except Exception as e:  # noqa: BLE001
        return jsonify(error=f"드라이브 저장 실패: {e}", pdf=True)
    return jsonify(saved=saved)


@app.get("/api/pdf")
def pdf():
    if not S["pdf"]:
        return "", 404
    return send_file(S["pdf"][0], as_attachment=True, download_name=S["pdf"][1])


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


if __name__ == "__main__":
    port = int(os.environ.get("PORT") or free_port())
    url = f"http://127.0.0.1:{port}"
    print(f"악보 영상 → PDF 실행 중: {url}\n(이 창을 닫으면 앱이 종료됩니다)")
    if not os.environ.get("NO_BROWSER"):
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=port, threaded=True)
