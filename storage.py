"""캡처한 악보를 '악보/<악기>/<영상 제목>/' 구조로 저장 (로컬 드라이브 폴더 또는 Drive API)."""
import glob
import os
import re

INSTRUMENTS = ["피아노", "기타", "베이스", "드럼", "바이올린", "우쿨렐레", "플루트", "색소폰", "보컬", "기타(기타 악기)"]

_KEYWORDS = {
    "피아노": ["piano", "피아노"],
    "기타": ["guitar", "기타", "tab", "타브"],
    "베이스": ["bass", "베이스"],
    "드럼": ["drum", "드럼"],
    "바이올린": ["violin", "바이올린"],
    "우쿨렐레": ["ukulele", "우쿨렐레"],
    "플루트": ["flute", "플루트"],
    "색소폰": ["sax", "색소폰"],
}


def safe_name(s: str, limit=80) -> str:
    s = re.sub(r'[\\/:*?"<>|\n\r\t]', " ", s).strip(" .")
    return re.sub(r"\s+", " ", s)[:limit] or "untitled"


def guess_instrument(title: str) -> str:
    low = title.lower()
    for inst, kws in _KEYWORDS.items():
        if any(k in low for k in kws):
            return inst
    return "피아노"


def detect_drive_folder() -> str:
    """구글 드라이브 데스크톱 앱의 '내 드라이브' 경로를 찾는다(맥/윈도우)."""
    home = os.path.expanduser("~")
    cands = glob.glob(os.path.join(home, "Library/CloudStorage/GoogleDrive-*/내 드라이브"))
    cands += glob.glob(os.path.join(home, "Library/CloudStorage/GoogleDrive-*/My Drive"))
    cands += [os.path.join(home, "Google Drive/내 드라이브"), os.path.join(home, "Google Drive/My Drive"),
              os.path.join(home, "Google Drive"), "G:/내 드라이브", "G:/My Drive"]
    for c in cands:
        if os.path.isdir(c):
            return c
    return ""


def save_local(root_dir, instrument, title, pil_images, pdf_path, top="악보"):
    """root_dir/악보/<악기>/<제목>/ 에 PNG(01.png…)와 PDF를 저장하고 폴더 경로를 돌려준다."""
    folder = os.path.join(root_dir, top, safe_name(instrument), safe_name(title))
    os.makedirs(folder, exist_ok=True)
    for i, im in enumerate(pil_images, 1):
        im.save(os.path.join(folder, f"{i:02d}.png"))
    if pdf_path and os.path.exists(pdf_path):
        with open(pdf_path, "rb") as src, open(os.path.join(folder, safe_name(title) + ".pdf"), "wb") as dst:
            dst.write(src.read())
    return folder


# ------------------------------------------------------------ Drive API (선택)
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
import sys
APP_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))


def _service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    token_p = os.path.join(APP_DIR, "token.json")
    cred_p = os.path.join(APP_DIR, "credentials.json")
    creds = Credentials.from_authorized_user_file(token_p, SCOPES) if os.path.exists(token_p) else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(cred_p):
                raise FileNotFoundError("credentials.json 이 없습니다. README의 'Drive API 설정'을 참고하세요.")
            creds = InstalledAppFlow.from_client_secrets_file(cred_p, SCOPES).run_local_server(port=0)
        with open(token_p, "w") as f:
            f.write(creds.to_json())
    return build("drive", "v3", credentials=creds)


def _ensure_folder(svc, name, parent=None):
    q = f"name='{name.replace(chr(39), chr(92) + chr(39))}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    q += f" and '{parent}' in parents" if parent else " and 'root' in parents"
    r = svc.files().list(q=q, fields="files(id)", spaces="drive").execute().get("files", [])
    if r:
        return r[0]["id"]
    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent:
        meta["parents"] = [parent]
    return svc.files().create(body=meta, fields="id").execute()["id"]


def save_drive_api(instrument, title, pil_images, pdf_path, top="악보"):
    """Drive API로 '악보/<악기>/<제목>/' 폴더를 만들어 업로드. 폴더 링크를 돌려준다."""
    import io

    from googleapiclient.http import MediaIoBaseUpload

    svc = _service()
    fid = _ensure_folder(svc, top)
    fid = _ensure_folder(svc, safe_name(instrument), fid)
    fid = _ensure_folder(svc, safe_name(title), fid)
    for i, im in enumerate(pil_images, 1):
        buf = io.BytesIO()
        im.save(buf, "PNG")
        buf.seek(0)
        svc.files().create(
            body={"name": f"{i:02d}.png", "parents": [fid]},
            media_body=MediaIoBaseUpload(buf, "image/png"), fields="id").execute()
    if pdf_path and os.path.exists(pdf_path):
        with open(pdf_path, "rb") as f:
            svc.files().create(
                body={"name": safe_name(title) + ".pdf", "parents": [fid]},
                media_body=MediaIoBaseUpload(io.BytesIO(f.read()), "application/pdf"), fields="id").execute()
    return f"https://drive.google.com/drive/folders/{fid}"
