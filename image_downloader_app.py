# -*- coding: utf-8 -*-
"""
Tải ảnh siêu tốc — v1.0.2
- Tự kiểm tra cập nhật khi khởi động (hiện thông báo, người dùng bấm "Tải về" để cài)
- Hỗ trợ thay icon ứng dụng (ưu tiên file app.ico bên cạnh exe; nếu không có dùng icon nhúng)
- Các tính năng cũ: đa luồng, chọn ảnh lớn nhất, lọc định dạng/thumbnail, dark mode, tải qua .txt

Build gợi ý (Windows):
    pyinstaller --onefile --windowed --collect-all PySide6 --name "TaiAnhSieuToc" --icon app.ico image_downloader_app.py
    (nếu không có app.ico có thể bỏ --icon)

Lưu ý: MANIFEST_URL cần trỏ tới JSON public trong repo GitHub của bạn.
"""

import sys, subprocess

__version__ = "1.0.3"
# Đặt mặc định theo repo đã dùng trước đó; đổi nếu khác.
MANIFEST_URL = "https://raw.githubusercontent.com/bacsyda/tai-anh-sieu-toc/main/public/tai_anh_sieu_toc.json"


def _install_if_missing(pkg: str):
    try:
        __import__(pkg)
    except Exception:
        print(f"[Setup] Chưa có '{pkg}', đang cài...", flush=True)
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

for _pkg in ("requests", "bs4", "PySide6"):
    try:
        _install_if_missing(_pkg)
    except Exception as e:
        print(f"[Setup] Lỗi cài {_pkg}: {e}")

import os, re, hashlib, base64, threading, concurrent.futures, tempfile, json
from threading import Lock
from urllib.parse import urljoin, urlparse, unquote, parse_qs
import requests
from requests.adapters import HTTPAdapter, Retry
from bs4 import BeautifulSoup
from PySide6 import QtCore, QtWidgets
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QGridLayout, QLineEdit, QPushButton,
    QFileDialog, QLabel, QCheckBox, QSpinBox, QTextEdit, QProgressBar, QHBoxLayout,
    QVBoxLayout, QMessageBox, QMenuBar, QMenu
)
from PySide6.QtGui import QIcon, QPixmap, QPalette, QColor, QAction

# ====== Constants & Regex ======
INVALID_RE = re.compile(r'[<>:"/\\|?*]')
MIME_TO_EXT = {
    "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png",
    "image/gif": ".gif", "image/webp": ".webp", "image/avif": ".avif",
    "image/svg+xml": ".svg", "image/bmp": ".bmp", "image/tiff": ".tif",
}
SIZE_SUFFIX_RE = re.compile(r"-(\d{2,5})x(\d{2,5})(?=\.(jpe?g|png|webp|gif|avif|bmp|tiff?)$)", re.I)
PIN_DIR_RE = re.compile(r"/(\d{2,5})x/")
DATA_URL_RE = re.compile(r"^data:([^;,]+)?((?:;[^,]+)*)?,(.*)$", re.I)
HINT_SIZES = {}

# ====== App Icon (fallback nhúng) ======
_APP_ICON_B64 = (
    b"iVBORw0KGgoAAAANSUhEUgAAAIAAAACACAYAAADDPmHLAAAACXBIWXMAAAsSAAALEgHS3X78AAABr0lEQVR4nO3aMW7CQBBF0a2vB1w2tHkqg3Cw6j3mB4qAM5J5Hk3c0xqgqF0KXj2ZyQ5i+3xwW0QmH0z7o0I1a6d2i8k1H7wM9o+qO5p3tJf7S6Y8n3FQkAAAAAAAAAAAAAAAAAAACw3m1m1zVQW1X0mJQeJjQp8fJg8m+e3g3Q4wq7m1v1m7o0f4b9m3m4X3l1g0E0bB3IY5q3X3+Y1mAgm2tH7n1c5mU1u7Gx5yr2VxJ9eXG1bS7lCj0v5i5cb7b7j7m7qkq3k8qfUz0l0bqvX4HcNQ2d8H1z3k2o8tG3d7tV2Y2Wv3mU8qj9n8h2Jm2d8x4xk3rq9U6i1hU8bq8gqS3d4aX2pQ0oM2kX0b7W3p8fS7o9m0C3n8m3g8mGv0b9V6q7cQ9m7kWLq3rXx3g2h+Q6N0l2p1o0W1m4m8k4o9l8m8ZKp2a8c7m4ZpE2r8g6n5V4r8f5u4GxV7r9G6t9X+f7m8AAAAAAAAAAAAAAAAAAAAAPw5v8s5m6m2jDqAAAAAElFTkSuQmCC"
)

def load_app_icon() -> QIcon:
    # Ưu tiên icon runtime (app.ico / app.png) bên cạnh exe/py
    for name in ("app.ico", "app.png"):
        p = os.path.join(os.path.dirname(getattr(sys, 'executable', sys.argv[0])), name)
        if os.path.isfile(p):
            try:
                return QIcon(p)
            except Exception:
                pass
    try:
        ba = base64.b64decode(_APP_ICON_B64)
        pix = QPixmap(); pix.loadFromData(ba, "PNG"); return QIcon(pix)
    except Exception:
        return QIcon()

# ====== Theming ======
_def_palette = None

def apply_dark_mode(app: QApplication, enabled: bool):
    global _def_palette
    if _def_palette is None:
        _def_palette = app.palette()
    if not enabled:
        app.setPalette(_def_palette); app.setStyle("Fusion"); return
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.WindowText, QColor(220, 220, 220))
    palette.setColor(QPalette.Base, QColor(35, 35, 35))
    palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.Text, QColor(220, 220, 220))
    palette.setColor(QPalette.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ButtonText, QColor(220, 220, 220))
    palette.setColor(QPalette.Highlight, QColor(64, 128, 255))
    palette.setColor(QPalette.HighlightedText, QColor(0, 0, 0))
    app.setStyle("Fusion"); app.setPalette(palette)

# ====== Networking ======

def build_session():
    s = requests.Session()
    retries = Retry(total=3, backoff_factor=0.5,
                    status_forcelist=[429, 500, 502, 503, 504],
                    allowed_methods=["HEAD", "GET", "OPTIONS"])
    s.mount("http://", HTTPAdapter(max_retries=retries))
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119 Safari/537.36"
    })
    return s

# ====== Utils ======

def sanitize_filename(name: str) -> str:
    name = name.split("?")[0].split("#")[0]
    name = INVALID_RE.sub("_", name).strip(". ")
    return name or "image"

def ensure_unique(path: str) -> str:
    if not os.path.exists(path): return path
    root, ext = os.path.splitext(path)
    i = 1
    while True:
        p = f"{root}_{i}{ext}"
        if not os.path.exists(p): return p
        i += 1

def is_image_content_type(ct: str) -> bool:
    return ct and ct.split(";")[0].strip().startswith("image/")

def choose_extension(filename: str, content_type: str) -> str:
    _, ext = os.path.splitext(filename); ext = ext.lower()
    guessed = MIME_TO_EXT.get((content_type or "").split(";")[0].strip(), "")
    if not ext: return guessed or ".bin"
    if guessed and ext != guessed: return guessed
    return ext

# ====== data: URL ======

def decode_data_url(data_url: str):
    m = DATA_URL_RE.match(data_url)
    if not m: return None, None
    mime = (m.group(1) or "").lower().strip(); params = (m.group(2) or "").lower(); data_part = m.group(3) or ""
    is_base64 = ";base64" in params
    if is_base64: raw = base64.b64decode(data_part, validate=True)
    else: raw = unquote(data_part).encode("utf-8")
    ext = MIME_TO_EXT.get(mime, ".bin")
    return raw, ext

# ====== Size helpers ======

def extract_named_size(url_path: str):
    fname = os.path.basename(url_path); m = SIZE_SUFFIX_RE.search(fname)
    if m: return int(m.group(1)), int(m.group(2))
    m2 = PIN_DIR_RE.search(url_path)
    if m2: n = int(m2.group(1)); return n, n
    return None

def extract_query_size(full_url: str):
    try: q = parse_qs(urlparse(full_url).query)
    except Exception: return None
    def first_int(key):
        if key in q and q[key]:
            try: return int(str(q[key][0]).split(",")[0].split("x")[0])
            except: return None
        return None
    def pair_from(key):
        if key in q and q[key]:
            raw = str(q[key][0]).replace("%2C", ",").lower()
            m = re.search(r"(\d{2,5})[x,](\d{2,5})", raw)
            if m: return int(m.group(1)), int(m.group(2))
        return None
    for k in ("fit","resize","size","dim","dimensions"):
        p = pair_from(k)
        if p: return p
    w = None
    for k in ("w","width","maxwidth","maxw"):
        w = first_int(k)
        if w: break
    h = None
    for k in ("h","height","maxheight","maxh"):
        h = first_int(k)
    if w and h: return w, h
    if w: return w, w
    if h: return h, h
    return None

def canonical_basename(url_path: str):
    path = PIN_DIR_RE.sub("/originals/", url_path)
    fname = os.path.basename(path)
    base = SIZE_SUFFIX_RE.sub("", fname)
    return base.lower()

def prefer_original_path(url_path: str):
    return PIN_DIR_RE.sub("/originals/", url_path)

def head_content_length(session, url):
    try:
        r = session.head(url, timeout=10, allow_redirects=True)
        cl = r.headers.get("Content-Length"); return int(cl) if cl and cl.isdigit() else -1
    except Exception: return -1

def pick_largest_variants(session, urls: list[str]) -> list[str]:
    buckets = {}
    for u in urls:
        if u.startswith("data:"):
            key = f"DATA::{hash(u)}"; buckets.setdefault(key, []).append((u, None, None)); continue
        parsed = urlparse(u)
        rew_path = prefer_original_path(parsed.path)
        rew_url = parsed._replace(path=rew_path).geturl() if rew_path != parsed.path else u
        size = (extract_named_size(rew_path) or extract_query_size(rew_url) or HINT_SIZES.get(rew_url))
        key = canonical_basename(rew_path)
        buckets.setdefault(key, []).append((rew_url, rew_path, size))
    picked = []
    for key, cands in buckets.items():
        origs = [c for c in cands if "/originals/" in (c[1] or "")]
        pool = origs if origs else cands
        with_sizes = [c for c in pool if c[2]]
        if with_sizes:
            best = max(with_sizes, key=lambda c: (c[2][0] * c[2][1])); picked.append(best[0]); continue
        best_url, best_len = None, -1
        for c in pool:
            ln = head_content_length(session, c[0])
            if ln > best_len: best_len, best_url = ln, c[0]
        picked.append(best_url if best_url else pool[0][0])
    return picked

# ====== HTML extraction ======

def extract_image_urls(html, base_url):
    soup = BeautifulSoup(html, "html.parser"); urls = set()
    for img in soup.find_all("img"):
        for key in ("src","data-src","data-original","data-lazy"):
            v = img.get(key)
            if v:
                full = v if v.startswith("data:") else urljoin(base_url, v)
                urls.add(full)
        srcset = img.get("srcset")
        if srcset:
            for part in srcset.split(","):
                part = part.strip();
                if not part: continue
                tokens = part.split(); u = tokens[0]; full = urljoin(base_url, u); urls.add(full)
                if len(tokens) >= 2:
                    d = tokens[1].lower()
                    if d.endswith("w"):
                        try: w = int(d[:-1]); HINT_SIZES[full] = (w, w)
                        except: pass
                    elif d.endswith("x"):
                        try: mul = float(d[:-1]); w = int(mul * 1000); HINT_SIZES[full] = (w, w)
                        except: pass
    for tag in soup.find_all(style=True):
        for m in re.finditer(r"url\((['\"]?)(.+?)\1\)", tag["style"]):
            u = m.group(2);
            if u:
                full = u if u.startswith("data:") else urljoin(base_url, u); urls.add(full)
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("data:"): urls.add(href)
        elif re.search(r"\.(png|jpe?g|gif|webp|avif|svg|bmp|tiff?)(\?|#|$)", href, re.I):
            urls.add(urljoin(base_url, href))
    return list(urls)

# ====== Save/Download ======

def save_bytes(raw: bytes, out_dir: str, filename: str, min_bytes: int, allow_exts: set, seen_hashes: set, lock: Lock | None = None):
    if min_bytes and len(raw) < min_bytes: return False, f"Bỏ qua (nhỏ hơn {min_bytes}B): {filename}"
    ext = os.path.splitext(filename)[1].lower()
    if allow_exts and ext and ext[1:] not in allow_exts: return False, f"Bỏ qua (không nằm trong allow): {filename}"
    h = hashlib.sha1(raw).hexdigest()
    if lock:
        with lock:
            if h in seen_hashes: return False, f"Bỏ qua (trùng nội dung): {filename}"
            seen_hashes.add(h)
    else:
        if h in seen_hashes: return False, f"Bỏ qua (trùng nội dung): {filename}"
        seen_hashes.add(h)
    out_path = ensure_unique(os.path.join(out_dir, filename))
    with open(out_path, "wb") as f: f.write(raw)
    return True, f"Đã lưu: {out_path}"

def download_http_image(session, img_url, out_dir, referer, min_bytes, allow_exts, seen_hashes, lock: Lock | None = None):
    parsed = urlparse(img_url); filename = sanitize_filename(os.path.basename(parsed.path) or "image")
    headers = {"Referer": referer} if referer else {}
    try: r = session.get(img_url, stream=True, timeout=20, headers=headers, allow_redirects=True)
    except requests.RequestException as e: return False, f"Lỗi tải {img_url} -> {e}"
    ct = r.headers.get("Content-Type", "").lower()
    if not is_image_content_type(ct) and not re.search(r"\.(png|jpe?g|gif|webp|avif|svg|bmp|tiff?)$", filename, re.I):
        r.close(); return False, f"Bỏ qua (không phải ảnh): {img_url} ({ct or 'no content-type'})"
    ext = choose_extension(filename, ct)
    filename = os.path.splitext(filename)[0] + ext
    raw = bytearray()
    for chunk in r.iter_content(8192):
        if chunk: raw.extend(chunk)
    r.close()
    return save_bytes(bytes(raw), out_dir, filename, min_bytes, allow_exts, seen_hashes, lock)

# ====== Update helpers ======

def parse_version_tuple(s: str):
    nums = re.findall(r"\d+", s)
    while len(nums) < 3: nums.append('0')
    return tuple(int(x) for x in nums[:3])

def get_current_exe_path() -> str | None:
    if getattr(sys, 'frozen', False): return sys.executable
    return None

def download_with_progress(url: str, dest: str, log_cb):
    session = build_session()
    try:
        with session.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            total = int(r.headers.get('Content-Length', '0'))
            done = 0
            with open(dest, 'wb') as f:
                for chunk in r.iter_content(1024 * 64):
                    if chunk:
                        f.write(chunk); done += len(chunk)
                        if total: log_cb(f"Tải gói cập nhật: {int(done * 100 / total)}%")
        return True, None
    except Exception as e:
        return False, str(e)

def sha256sum(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()

def write_windows_updater(old_exe: str, new_exe: str) -> str:
    bat = f"""@echo off
setlocal enabledelayedexpansion
:waitloop
  >nul 2>&1 (copy /y "{new_exe}" "{old_exe}")
  if errorlevel 1 (
    timeout /t 1 >nul
    goto waitloop
  )
start "" "{old_exe}"
del "{new_exe}" >nul 2>&1
(del "%~f0")
"""
    up_path = os.path.join(tempfile.gettempdir(), "tas_updater.bat")
    with open(up_path, 'w', encoding='utf-8', errors='ignore') as f: f.write(bat)
    return up_path

# ====== Workers ======
class DownloaderWorker(QtCore.QThread):
    log_msg = QtCore.Signal(str); progress = QtCore.Signal(int); finished = QtCore.Signal(int, int)
    def __init__(self, pages: list[str], out_dir: str, allow_exts: set, min_bytes: int,
                 accept_data: bool, auto_referer: bool, explicit_referer: str, max_workers: int):
        super().__init__()
        self.pages = pages; self.out_dir = out_dir; self.allow_exts = allow_exts; self.min_bytes = min_bytes
        self.accept_data = accept_data; self.auto_referer = auto_referer; self.explicit_referer = explicit_referer
        self.max_workers = max(1, int(max_workers)); self._stop = threading.Event(); self.hash_lock = Lock(); self.seen_hashes = set()
    def stop(self): self._stop.set()
    def _derive_referer(self, page_url: str) -> str:
        if self.explicit_referer: return self.explicit_referer
        if not self.auto_referer: return ""
        try:
            p = urlparse(page_url)
            if p.scheme and p.netloc: return f"{p.scheme}://{p.netloc}/"
        except Exception: return ""
        return ""
    def _download_one(self, img_url: str, referer: str) -> bool:
        if self._stop.is_set(): return False
        if img_url.startswith("data:"):
            if not self.accept_data: return False
            try:
                raw, ext = decode_data_url(img_url)
                if raw is None: return False
                fname = f"inline_{hashlib.sha1(raw).hexdigest()[:12]}{ext}"
                success, msg = save_bytes(raw, self.out_dir, fname, self.min_bytes, self.allow_exts, self.seen_hashes, self.hash_lock)
                self.log_msg.emit(msg); return success
            except Exception as e:
                self.log_msg.emit(f"Lỗi data URL -> {e}"); return False
        session = build_session()
        success, msg = download_http_image(session, img_url, self.out_dir, referer or img_url, self.min_bytes, self.allow_exts, self.seen_hashes, self.hash_lock)
        self.log_msg.emit(msg); return success
    def run(self):
        os.makedirs(self.out_dir, exist_ok=True); session = build_session(); collected = []
        for page_url in self.pages:
            if self._stop.is_set(): break
            try:
                page = session.get(page_url, timeout=25); page.raise_for_status()
            except requests.RequestException as e:
                self.log_msg.emit(f"Lỗi tải trang {page_url}: {e}"); continue
            urls = extract_image_urls(page.text, page_url);
            if not urls: self.log_msg.emit(f"Không tìm thấy ảnh ở: {page_url}"); continue
            collected.extend(urls)
        if not collected: self.finished.emit(0, 0); return
        final_urls = pick_largest_variants(session, list(dict.fromkeys(collected)))
        total = len(final_urls); self.log_msg.emit(f"Sau khi gom biến thể, còn {total} URL cần tải.")
        if total == 0: self.finished.emit(0, 0); return
        ok = 0; done = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            futures = [ex.submit(self._download_one, u, self._derive_referer(self.pages[0])) for u in final_urls]
            for fut in concurrent.futures.as_completed(futures):
                try:
                    if fut.result(): ok += 1
                except Exception as e:
                    self.log_msg.emit(f"Lỗi worker: {e}")
                done += 1; self.progress.emit(int(done * 100 / total))
                if self._stop.is_set(): break
        self.finished.emit(ok, total)

class UpdateCheckWorker(QtCore.QThread):
    result = QtCore.Signal(object, object)  # (manifest or None, error or None)
    def run(self):
        try:
            s = build_session()
            r = s.get(MANIFEST_URL, timeout=10)
            r.raise_for_status()
            # strip BOM nếu có:
            txt = r.content.decode("utf-8-sig", errors="replace")
            manifest = json.loads(txt)
            self.result.emit(manifest, None)
        except Exception as e:
            self.result.emit(None, e)


# ====== Main Window ======
class MainWindow(QMainWindow):
    def __init__(self, app: QApplication):
        super().__init__(); self.app = app
        self.setWindowTitle("Tải ảnh siêu tốc"); self.setWindowIcon(load_app_icon()); self.setMinimumSize(940, 640)
        cw = QWidget(); self.setCentralWidget(cw)

        # Menu (giữ lại mục trợ giúp)
        menubar = QMenuBar(self); self.setMenuBar(menubar)
        help_menu = QMenu("Trợ giúp", self); menubar.addMenu(help_menu)
        act_about = QAction("Giới thiệu", self); act_about.triggered.connect(self.show_about); help_menu.addAction(act_about)

        # Inputs
        self.url_edit = QLineEdit(); self.url_edit.setPlaceholderText("Dán URL trang web...")
        self.txt_edit = QLineEdit(); self.txt_edit.setPlaceholderText("(Tùy chọn) File .txt chứa danh sách URL — mỗi dòng 1 URL")
        self.btn_txt = QPushButton("Chọn file .txt…")
        self.out_edit = QLineEdit(os.path.join(os.getcwd(), "images")); self.btn_out = QPushButton("Chọn thư mục…")
        self.allow_edit = QLineEdit("jpg,png,webp,gif,avif")
        self.min_spin = QSpinBox(); self.min_spin.setRange(0, 10_000_000); self.min_spin.setValue(30000)
        self.cb_no_data = QCheckBox("Bỏ qua data: URL"); self.cb_no_data.setChecked(True)
        self.cb_auto_ref = QCheckBox("Tự suy ra Referer từ domain"); self.cb_auto_ref.setChecked(True)
        self.ref_edit = QLineEdit(); self.ref_edit.setPlaceholderText("Tùy chọn: Referer cụ thể (nếu site chặn hotlink)")
        self.dark_cb = QCheckBox("Dark mode")
        self.workers_spin = QSpinBox(); self.workers_spin.setRange(1, 32); self.workers_spin.setValue(8)

        # Buttons
        self.btn_start = QPushButton("Bắt đầu tải"); self.btn_stop = QPushButton("Hủy"); self.btn_open = QPushButton("Mở thư mục lưu")
        self.progress = QProgressBar(); self.progress.setRange(0, 100); self.progress.setValue(0)
        self.log = QTextEdit(); self.log.setReadOnly(True)

        grid = QGridLayout()
        grid.addWidget(QLabel("URL:"), 0, 0); grid.addWidget(self.url_edit, 0, 1, 1, 3)
        grid.addWidget(QLabel("Danh sách URL (.txt):"), 1, 0); grid.addWidget(self.txt_edit, 1, 1, 1, 2); grid.addWidget(self.btn_txt, 1, 3)
        grid.addWidget(QLabel("Thư mục lưu:"), 2, 0); grid.addWidget(self.out_edit, 2, 1, 1, 2); grid.addWidget(self.btn_out, 2, 3)
        grid.addWidget(QLabel("Định dạng cho phép:"), 3, 0); grid.addWidget(self.allow_edit, 3, 1)
        grid.addWidget(QLabel("Min bytes (lọc nhỏ):"), 3, 2); grid.addWidget(self.min_spin, 3, 3)
        grid.addWidget(self.cb_no_data, 4, 1); grid.addWidget(self.cb_auto_ref, 4, 2)
        grid.addWidget(QLabel("Referer (tùy chọn):"), 5, 0); grid.addWidget(self.ref_edit, 5, 1, 1, 3)
        grid.addWidget(QLabel("Số luồng tải:"), 6, 0); grid.addWidget(self.workers_spin, 6, 1); grid.addWidget(self.dark_cb, 6, 2)
        btn_row = QHBoxLayout(); btn_row.addWidget(self.btn_start); btn_row.addWidget(self.btn_stop); btn_row.addStretch(1); btn_row.addWidget(self.btn_open)
        vbox = QVBoxLayout(cw); vbox.addLayout(grid); vbox.addWidget(self.progress); vbox.addLayout(btn_row); vbox.addWidget(self.log, 1)

        # Signals
        self.btn_out.clicked.connect(self.pick_dir); self.btn_txt.clicked.connect(self.pick_txt)
        self.btn_start.clicked.connect(self.start_download); self.btn_stop.clicked.connect(self.stop_download)
        self.btn_open.clicked.connect(self.open_dir); self.dark_cb.toggled.connect(self.toggle_dark)
        self.worker: DownloaderWorker | None = None

        # Auto-check update sau 1.2s
        QtCore.QTimer.singleShot(1200, self.auto_check_updates)

    # ===== Update flow =====
    def show_about(self):
        QMessageBox.information(self, "Giới thiệu", f"Tải ảnh siêu tốc\nPhiên bản: {__version__}")

    def auto_check_updates(self):
        self.log.append("Đang kiểm tra cập nhật...")
        self.up_worker = UpdateCheckWorker(); self.up_worker.result.connect(self.on_update_checked); self.up_worker.start()

    def on_update_checked(self, manifest, err):
        if err:
            self.log.append(f"Không kiểm tra được cập nhật: {err}")
            return
        latest = str(manifest.get("version", "0.0.0")); cur = parse_version_tuple(__version__); lat = parse_version_tuple(latest)
        if lat <= cur:
            self.log.append("Bạn đang dùng bản mới nhất.")
            return
        win = manifest.get("windows", {}); url = win.get("url"); sha = (win.get("sha256") or "").lower()
        if not url:
            self.log.append("Manifest thiếu URL tải cho Windows.")
            return
        # Hỏi tải ngay
        ret = QMessageBox.question(self, "Có bản cập nhật", f"Phát hiện phiên bản mới {latest}.\nBạn có muốn tải và cài đặt ngay không?",
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if ret == QMessageBox.Yes:
            self.download_and_install(url, sha, latest)

    def download_and_install(self, url: str, sha: str, latest: str):
        exe_path = get_current_exe_path()
        if not exe_path:
            QMessageBox.information(self, "Cập nhật", f"Bạn đang chạy từ source.\nVui lòng tải file .exe mới tại:\n{url}")
            return
        tmp_dir = tempfile.gettempdir(); new_path = os.path.join(tmp_dir, f"TaiAnhSieuToc_{latest}.exe")
        ok, err = download_with_progress(url, new_path, self.log.append)
        if not ok:
            QMessageBox.warning(self, "Cập nhật", f"Tải thất bại: {err}")
            try: os.remove(new_path)
            except: pass
            return
        if sha:
            calc = sha256sum(new_path).lower()
            if calc != sha:
                QMessageBox.warning(self, "Cập nhật", f"Sai checksum!\nManifest: {sha}\nTải được: {calc}")
                try: os.remove(new_path)
                except: pass
                return
        up_bat = write_windows_updater(exe_path, new_path)
        try:
            if sys.platform.startswith('win'):
                subprocess.Popen(["cmd", "/c", "start", "", up_bat], shell=True)
            else:
                QMessageBox.information(self, "Cập nhật", "Tự cập nhật hiện chỉ hỗ trợ Windows.")
                return
        except Exception as e:
            QMessageBox.warning(self, "Cập nhật", f"Không chạy được updater: {e}")
            return
        QApplication.instance().quit()

    # ===== UI actions =====
    def toggle_dark(self, checked: bool): apply_dark_mode(self.app, checked)
    def pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu", self.out_edit.text() or os.getcwd())
        if d: self.out_edit.setText(d)
    def pick_txt(self):
        path, _ = QFileDialog.getOpenFileName(self, "Chọn file .txt chứa danh sách URL", os.getcwd(), "Text files (*.txt)")
        if path: self.txt_edit.setText(path)
    def start_download(self):
        pages = []
        txt_path = self.txt_edit.text().strip()
        if txt_path and os.path.isfile(txt_path):
            try:
                with open(txt_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        u = line.strip();
                        if u: pages.append(u)
            except Exception as e:
                self.log.append(f"Không đọc được file .txt: {e}")
        if not pages:
            url = self.url_edit.text().strip();
            if url: pages = [url]
        if not pages:
            self.log.append("❗ Vui lòng nhập URL hoặc chọn file .txt danh sách URL."); return
        out_dir = self.out_edit.text().strip() or os.path.join(os.getcwd(), "images")
        allow_exts = set([e.strip().lower() for e in self.allow_edit.text().split(",") if e.strip()])
        min_bytes = int(self.min_spin.value()); accept_data = not self.cb_no_data.isChecked()
        auto_ref = self.cb_auto_ref.isChecked(); ref = self.ref_edit.text().strip(); max_workers = int(self.workers_spin.value())
        self.log.clear(); self.progress.setValue(0); self.btn_start.setEnabled(False)
        self.worker = DownloaderWorker(pages, out_dir, allow_exts, min_bytes, accept_data, auto_ref, ref, max_workers)
        self.worker.log_msg.connect(self.log.append); self.worker.progress.connect(self.progress.setValue); self.worker.finished.connect(self.on_finished)
        self.worker.start()
    def stop_download(self):
        if self.worker and self.worker.isRunning(): self.worker.stop()
    def on_finished(self, ok: int, total: int):
        self.log.append(f"\n✅ Hoàn tất: {ok}/{total} ảnh hợp lệ."); self.btn_start.setEnabled(True); self.progress.setValue(100)
    def open_dir(self):
        path = self.out_edit.text().strip() or os.path.join(os.getcwd(), "images")
        try:
            if os.path.isdir(path):
                if sys.platform.startswith('win'): os.startfile(path)
                elif sys.platform == 'darwin': subprocess.Popen(['open', path])
                else: subprocess.Popen(['xdg-open', path])
        except Exception as e:
            self.log.append(f"Không mở được thư mục: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv); w = MainWindow(app); w.show(); sys.exit(app.exec())

