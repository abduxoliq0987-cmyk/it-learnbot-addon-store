import sys
import os
import json
import hashlib
import zipfile
import io
import urllib.request
import shutil
import re
from pathlib import Path
from urllib.parse import quote_plus

from PySide6.QtCore import QUrl, Qt, QSize
from PySide6.QtGui import QAction, QKeySequence, QIcon, QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QToolButton, QMenu, QMessageBox, QDialog,
    QFormLayout, QCheckBox, QComboBox, QLabel, QDialogButtonBox, QStyle,
    QListWidget, QListWidgetItem, QAbstractItemView, QTextBrowser, QFileDialog,
    QScrollArea
)
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineDownloadRequest
from PySide6.QtWebEngineWidgets import QWebEngineView


APP_NAME = "IT Learn Browser"
INTERNAL_HOME_URL = "itl://home"
HOME_URL = INTERNAL_HOME_URL
APP_DIR = Path.home() / "AppData" / "Local" / "ITLearnBrowser"
APP_DIR.mkdir(parents=True, exist_ok=True)
BOOKMARKS_FILE = APP_DIR / "bookmarks.json"
STORE_URL = "https://it-learnbot-addon-store.onrender.com/api/addons"
ADDONS_DIR = APP_DIR / "addons"
ADDONS_DIR.mkdir(parents=True, exist_ok=True)
PACKAGE_CACHE_DIR = APP_DIR / "package_cache"
PACKAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
CATALOG_CACHE_FILE = APP_DIR / "addons_catalog_cache.json"
ENABLED_FILE = APP_DIR / "enabled_addons.json"
MOD_API_VERSION = 1

OFFLINE_HOME_HTML = r"""<!doctype html><html lang="uz"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>IT Learn Browser</title><style>
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at top,#253b59,#111827 65%);color:#eef4ff;font:16px Segoe UI,Arial;min-height:100vh;display:grid;place-items:center}.card{width:min(760px,92vw);padding:42px;border:1px solid #49617f;border-radius:24px;background:#172338eF;box-shadow:0 20px 70px #0006}h1{font-size:36px;margin:0 0 10px}.muted{color:#b7c7dc;line-height:1.6}.pill{display:inline-block;border:1px solid #55759b;border-radius:99px;padding:6px 12px;margin-bottom:18px;color:#b9e2ff}.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:24px}.actions a{background:#3278d4;color:#fff;text-decoration:none;padding:11px 17px;border-radius:10px}.actions a.secondary{background:#293a52;border:1px solid #526986}.note{margin-top:25px;padding:14px;border-radius:12px;background:#0e1929;color:#c6d8eb;font-size:14px}
</style></head><body><main class="card"><span class="pill">● OFFLINE MODE READY</span><h1>IT Learn Browser</h1><p class="muted">O‘rnatilgan o‘yinlar va brauzer modlari internet bo‘lmasa ham ishlashi mumkin. Internet faqat yangi qo‘shimchalarni do‘kondan yuklab olish va internet saytlarini ochish uchun kerak.</p><form onsubmit="event.preventDefault();let q=document.getElementById('q').value.trim();if(q)location.href='https://www.google.com/search?q='+encodeURIComponent(q)"><input id="q" placeholder="Internet bor bo‘lsa Google orqali qidiring" style="width:100%;padding:14px;border-radius:10px;border:1px solid #526986;background:#0e1929;color:white;font-size:16px"></form><div class="actions"><a href="https://it-learnbot-addon-store.onrender.com/api/addons">Add-on Store</a><a class="secondary" href="https://www.google.com">Internetga kirish</a></div><div class="note">Maslahat: oldin o‘rnatilgan offline o‘yin va modlarni menyu → O‘rnatilgan qo‘shimchalar bo‘limidan oching. Modlar menyusi orqali brauzerga yangi vositalar qo‘shiladi.</div></main></body></html>"""

ASI_MAGIC = b"ITLASI01"
ASI_FORMAT = "ITL-ASI"
ASI_FORMAT_VERSION = 1


def app_icon(app, standard_icon):
    return app.style().standardIcon(standard_icon)


class BrowserTab(QWidget):
    def __init__(self, browser, url=HOME_URL):
        super().__init__()
        self.browser = browser
        self.view = QWebEngineView(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        self.view.urlChanged.connect(self.on_url_changed)
        self.view.titleChanged.connect(self.on_title_changed)
        self.view.loadFinished.connect(self.on_load_finished)
        if url == INTERNAL_HOME_URL:
            self.view.setHtml(OFFLINE_HOME_HTML, QUrl("about:blank"))
        else:
            self.view.setUrl(QUrl(url))

    def on_url_changed(self, url):
        if self.browser.current_tab() is self:
            shown = "IT Learn Home (offline)" if url.toString() == "about:blank" else url.toString()
            self.browser.url_bar.setText(shown)

    def on_title_changed(self, title):
        index = self.browser.tabs.indexOf(self)
        if index >= 0:
            self.browser.tabs.setTabText(index, (title or "Yangi sahifa")[:22])

    def on_load_finished(self, ok):
        if ok:
            url = self.view.url().toString()
            if url and url not in ("about:blank",):
                self.browser.add_history(url, self.view.title())
            self.browser.apply_page_mods(self)


class SettingsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Sozlamalar")
        self.setMinimumWidth(380)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.search = QComboBox()
        self.search.addItem("Google", "https://www.google.com/search?q={}")
        self.search.addItem("Bing", "https://www.bing.com/search?q={}")
        self.search.addItem("DuckDuckGo", "https://duckduckgo.com/?q={}")
        current = parent.search_template
        idx = self.search.findData(current)
        if idx >= 0:
            self.search.setCurrentIndex(idx)
        self.home = QLineEdit(parent.home_url)
        self.dark = QCheckBox("Qorong‘i mavzu")
        self.dark.setChecked(parent.dark_mode)
        form.addRow("Qidiruv tizimi:", self.search)
        form.addRow("Bosh sahifa:", self.home)
        form.addRow("", self.dark)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class AddonStoreDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.browser = parent
        self.setWindowTitle("IT LearnBot Add-on Store")
        self.resize(680, 470)
        layout = QVBoxLayout(self)
        self.info = QLabel("Do‘kon yuklanmoqda…")
        layout.addWidget(self.info)
        self.items = QListWidget()
        self.items.setSelectionMode(QAbstractItemView.SingleSelection)
        layout.addWidget(self.items, 1)
        buttons = QHBoxLayout()
        refresh = QPushButton("Yangilash")
        refresh.clicked.connect(self.load_addons)
        local = QPushButton("Fayldan o‘rnatish")
        local.clicked.connect(self.install_local)
        install = QPushButton("Tanlanganini o‘rnatish")
        install.clicked.connect(self.install_selected)
        close = QPushButton("Yopish")
        close.clicked.connect(self.accept)
        buttons.addWidget(refresh)
        buttons.addWidget(local)
        buttons.addStretch(1)
        buttons.addWidget(install)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.addons = []
        self.load_addons()

    def load_addons(self):
        self.items.clear()
        self.info.setText("Do‘kon bilan bog‘lanmoqda…")
        QApplication.processEvents()
        try:
            req = urllib.request.Request(STORE_URL, headers={"User-Agent": "IT-Learn-Browser/1.4"})
            with urllib.request.urlopen(req, timeout=12) as response:
                data = json.loads(response.read().decode("utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("addons"), list):
                raise ValueError("Do‘kon katalogi JSON formatida noto‘g‘ri.")
            self.addons = data["addons"]
            CATALOG_CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            state = "Internet orqali yangilandi"
        except Exception as exc:
            try:
                data = json.loads(CATALOG_CACHE_FILE.read_text(encoding="utf-8"))
                self.addons = data.get("addons", [])
                state = f"Internet yo‘q — saqlangan katalog ishlatildi ({exc})"
            except Exception:
                self.addons = []
                self.info.setText(f"Do‘konni yuklab bo‘lmadi va offline katalog ham yo‘q.\n{exc}\nOldin yuklab olingan paketni ‘Fayldan o‘rnatish’ orqali o‘rnating.")
                return
        for addon in self.addons:
            addon_id = str(addon.get("id", ""))
            installed = (ADDONS_DIR / addon_id / "manifest.json").is_file()
            cached = (PACKAGE_CACHE_DIR / f"{addon_id}.pkg").is_file()
            marker = "✓ O‘rnatilgan" if installed else ("◉ Offline kesh" if cached else "↓ Yuklash kerak")
            name = addon.get("name", "Nomsiz qo‘shimcha")
            version = addon.get("version", "")
            desc = addon.get("description", "")
            self.items.addItem(f"{name}  •  v{version}  •  {marker}\n{desc}")
        self.info.setText(f"{data.get('store_name', 'Add-on Store')} — {len(self.addons)} ta qo‘shimcha\n{state}. O‘rnatilgan paketlar internet bo‘lmasa ham ishlaydi.")
        if not self.addons:
            self.info.setText("Katalogda hozircha qo‘shimcha yo‘q.")

    def install_selected(self):
        index = self.items.currentRow()
        if index < 0 or index >= len(self.addons):
            QMessageBox.information(self, "Tanlanmagan", "Avval ro‘yxatdan qo‘shimcha tanlang.")
            return
        addon = self.addons[index]
        addon_id = str(addon.get("id", ""))
        expected_hash = str(addon.get("sha256", "")).lower().strip()
        cached_file = PACKAGE_CACHE_DIR / f"{addon_id}.pkg"
        try:
            package = cached_file.read_bytes() if cached_file.is_file() else None
            source = "offline kesh"
            actual_hash = hashlib.sha256(package).hexdigest() if package is not None else ""
            if package is None or not expected_hash or actual_hash != expected_hash:
                url = addon.get("download_url", "")
                if not isinstance(url, str) or not url.startswith("https://"):
                    raise ValueError("Qo‘shimchaning HTTPS manzili noto‘g‘ri yoki offline kesh eskirgan.")
                req = urllib.request.Request(url, headers={"User-Agent": "IT-Learn-Browser/1.4"})
                with urllib.request.urlopen(req, timeout=45) as response:
                    package = response.read()
                source = "Add-on Store"
                actual_hash = hashlib.sha256(package).hexdigest()
            if not expected_hash or actual_hash != expected_hash:
                raise ValueError(f"SHA-256 mos kelmadi.\nKatalog: {expected_hash or '(yo‘q)'}\nFayl: {actual_hash}\nGitHub katalogidagi hashni ZIP/ASI faylning aynan shu nusxasidan hisoblang.")
            self.browser.install_package_bytes(package, expected_id=addon_id, expected_hash=expected_hash, trusted=True)
            cached_file.write_bytes(package)
            QMessageBox.information(self, "Muvaffaqiyatli", f"{addon.get('name', addon_id)} o‘rnatildi ({source}).\nEndi internet bo‘lmasa ham ishga tushirish mumkin.")
            self.load_addons()
        except Exception as exc:
            QMessageBox.critical(self, "O‘rnatishda xatolik", str(exc))

    def install_local(self):
        path, _ = QFileDialog.getOpenFileName(self, "ITL-ASI yoki ZIP paketini tanlang", str(Path.home()), "Qo‘shimcha paketlari (*.asi *.zip *.pkg);;Barcha fayllar (*.*)")
        if not path:
            return
        try:
            package = Path(path).read_bytes()
            digest = hashlib.sha256(package).hexdigest()
            answer = QMessageBox.question(self, "Mahalliy paket", f"Paket SHA-256:\n{digest}\n\nBu paket do‘kon orqali tekshirilmagan. Faqat ishonchli manbadan olingan paketni o‘rnating. Davom etilsin?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
            manifest, _ = self.browser.install_package_bytes(package, trusted=False)
            QMessageBox.information(self, "Muvaffaqiyatli", f"{manifest.get('name', manifest.get('id'))} o‘rnatildi.\nInternet talab qilinmaydi, agar paketning barcha resurslari ichida bo‘lsa.")
            self.load_addons()
        except Exception as exc:
            QMessageBox.critical(self, "O‘rnatishda xatolik", str(exc))


class AddonRunnerDialog(QDialog):
    def __init__(self, manifest, content, parent=None):
        super().__init__(parent)
        self.setWindowTitle(manifest.get("name", "Qo‘shimcha"))
        self.resize(900, 650)
        layout = QVBoxLayout(self)
        kind = manifest.get("type", content.get("type", "learning-content"))
        if kind == "game" and isinstance(content.get("html"), str):
            view = QWebEngineView(self)
            layout.addWidget(view)
            # Game HTML is supplied by the installed, SHA-256-verified add-on.
            view.setHtml(content["html"], QUrl("about:blank"))
        else:
            title = QLabel(content.get("title", manifest.get("name", "Darslar")))
            title.setStyleSheet("font-size:20px;font-weight:600;padding:10px")
            layout.addWidget(title)
            body = QTextBrowser(self)
            layout.addWidget(body, 1)
            lines = []
            for lesson in content.get("lessons", []):
                lines.append(f"<h2>{lesson.get('title','Dars')}</h2><p>{lesson.get('content','')}</p>")
            body.setHtml("".join(lines) or "<p>Bu qo‘shimchada ko‘rsatish uchun kontent topilmadi.</p>")
        close = QPushButton("Yopish")
        close.clicked.connect(self.accept)
        layout.addWidget(close)


class BrowserWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 820)
        self.setMinimumSize(850, 560)
        self.home_url = HOME_URL
        self.search_template = "https://www.google.com/search?q={}"
        self.dark_mode = True
        self.history = []
        self.bookmarks = self.load_bookmarks()
        self.enabled_addons = self.load_enabled_addons()
        self._build_ui()
        self._build_menus()
        self.apply_theme()
        self.refresh_mod_controls()
        self.add_tab()

    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(8)

        # macOS-inspired traffic-light controls and tab strip
        top = QHBoxLayout()
        top.setSpacing(6)
        for color in ("#ff5f57", "#febc2e", "#28c840"):
            dot = QLabel()
            dot.setFixedSize(12, 12)
            dot.setStyleSheet(f"background:{color};border-radius:6px;")
            top.addWidget(dot)
        top.addSpacing(8)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.tabs.setElideMode(Qt.ElideRight)
        top.addWidget(self.tabs, 1)

        self.new_tab_button = QToolButton()
        self.new_tab_button.setText("+")
        self.new_tab_button.setToolTip("Yangi tab (Ctrl+T)")
        self.new_tab_button.clicked.connect(self.add_tab)
        top.addWidget(self.new_tab_button)
        root.addLayout(top)

        nav = QHBoxLayout()
        nav.setSpacing(6)
        self.back_btn = self.make_tool_button("‹", "Orqaga", lambda: self.current_view() and self.current_view().back())
        self.forward_btn = self.make_tool_button("›", "Oldinga", lambda: self.current_view() and self.current_view().forward())
        self.reload_btn = self.make_tool_button("↻", "Yangilash", lambda: self.current_view() and self.current_view().reload())
        self.home_btn = self.make_tool_button("⌂", "Bosh sahifa", lambda: self.navigate(self.home_url))
        nav.addWidget(self.back_btn)
        nav.addWidget(self.forward_btn)
        nav.addWidget(self.reload_btn)
        nav.addWidget(self.home_btn)

        self.url_bar = QLineEdit()
        self.url_bar.setPlaceholderText("Google orqali qidiring yoki sayt manzilini kiriting")
        self.url_bar.setClearButtonEnabled(True)
        self.url_bar.returnPressed.connect(self.navigate_from_bar)
        nav.addWidget(self.url_bar, 1)

        self.bookmark_btn = self.make_tool_button("☆", "Xatcho‘pga qo‘shish", self.add_bookmark)
        nav.addWidget(self.bookmark_btn)
        self.menu_btn = self.make_tool_button("⋯", "Menyu", self.show_app_menu)
        nav.addWidget(self.menu_btn)
        root.addLayout(nav)

        self.mods_bar_widget = QWidget()
        self.mods_bar = QHBoxLayout(self.mods_bar_widget)
        self.mods_bar.setContentsMargins(0, 0, 0, 0)
        self.mods_bar.setSpacing(6)
        root.addWidget(self.mods_bar_widget)

        self.status = QLabel("Tayyor — offline bosh sahifa")
        self.status.setObjectName("status")
        root.addWidget(self.status)
        self.setCentralWidget(central)

        self.tabs.currentChanged.connect(lambda _: self.update_navigation())
        self._create_shortcuts()

    def make_tool_button(self, text, tooltip, callback):
        b = QToolButton()
        b.setText(text)
        b.setToolTip(tooltip)
        b.setFixedSize(34, 32)
        b.clicked.connect(callback)
        return b

    def _build_menus(self):
        self.app_menu = QMenu(self)
        self.app_menu.addAction("Yangi tab", self.add_tab, QKeySequence.New)
        self.app_menu.addAction("Yangi oyna", self.new_window)
        self.app_menu.addSeparator()
        self.app_menu.addAction("Xatcho‘plar", self.show_bookmarks)
        self.app_menu.addAction("Tarix", self.show_history)
        self.app_menu.addAction("Yuklamalar papkasi", self.open_downloads)
        self.app_menu.addAction("Add-on Store", self.open_addon_store)
        self.app_menu.addAction("O‘rnatilgan qo‘shimchalar / Modlar", self.show_installed_addons)
        self.mods_menu = self.app_menu.addMenu("Mod funksiyalari")
        self.app_menu.addSeparator()
        self.app_menu.addAction("Sozlamalar", self.open_settings)
        self.app_menu.addAction("IT Learn Browser haqida", self.about)

    def _create_shortcuts(self):
        shortcuts = [
            ("Ctrl+T", self.add_tab), ("Ctrl+W", lambda: self.close_tab(self.tabs.currentIndex())),
            ("Ctrl+L", self.focus_url), ("Alt+Left", lambda: self.current_view() and self.current_view().back()),
            ("Alt+Right", lambda: self.current_view() and self.current_view().forward()),
            ("Ctrl+R", lambda: self.current_view() and self.current_view().reload()),
            ("Ctrl+D", self.add_bookmark), ("Ctrl+H", self.show_history),
        ]
        for key, fn in shortcuts:
            action = QAction(self)
            action.setShortcut(QKeySequence(key))
            action.triggered.connect(fn)
            self.addAction(action)

    def add_tab(self, url=HOME_URL):
        tab = BrowserTab(self, url)
        index = self.tabs.addTab(tab, "Yangi tab")
        self.tabs.setCurrentIndex(index)
        tab.view.loadProgress.connect(lambda p: self.status.setText(f"Yuklanmoqda… {p}%"))
        tab.view.loadFinished.connect(lambda ok: self.status.setText("Tayyor" if ok else "Sahifa yuklanmadi"))
        self.update_navigation()
        return tab

    def current_tab(self):
        w = self.tabs.currentWidget()
        return w if isinstance(w, BrowserTab) else None

    def current_view(self):
        tab = self.current_tab()
        return tab.view if tab else None

    def close_tab(self, index):
        if self.tabs.count() <= 1:
            self.current_view().setUrl(QUrl(self.home_url))
            return
        widget = self.tabs.widget(index)
        self.tabs.removeTab(index)
        widget.deleteLater()

    def on_tab_changed(self, _):
        self.update_navigation()

    def update_navigation(self):
        view = self.current_view()
        if not view:
            return
        self.url_bar.setText(view.url().toString())
        self.back_btn.setEnabled(view.history().canGoBack())
        self.forward_btn.setEnabled(view.history().canGoForward())

    def navigate_from_bar(self):
        raw = self.url_bar.text().strip()
        if not raw:
            return
        if "://" in raw or raw.startswith("file:"):
            target = raw
        elif " " not in raw and ("." in raw or raw.startswith("localhost")):
            target = "https://" + raw
        else:
            target = self.search_template.format(quote_plus(raw))
        self.navigate(target)

    def navigate(self, url):
        view = self.current_view()
        if view:
            if url == INTERNAL_HOME_URL:
                view.setHtml(OFFLINE_HOME_HTML, QUrl("about:blank"))
                self.url_bar.setText("IT Learn Home (offline)")
            else:
                view.setUrl(QUrl(url))
                self.url_bar.setText(url)

    def focus_url(self):
        self.url_bar.setFocus()
        self.url_bar.selectAll()

    def add_history(self, url, title):
        item = {"url": url, "title": title or url}
        if not self.history or self.history[-1]["url"] != url:
            self.history.append(item)
            self.history = self.history[-500:]

    def add_bookmark(self):
        view = self.current_view()
        if not view:
            return
        item = {"title": view.title() or view.url().host(), "url": view.url().toString()}
        if item["url"] and not any(x["url"] == item["url"] for x in self.bookmarks):
            self.bookmarks.append(item)
            self.save_bookmarks()
            self.bookmark_btn.setText("★")
            self.status.setText("Xatcho‘p saqlandi")

    def load_bookmarks(self):
        try:
            return json.loads(BOOKMARKS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []

    def save_bookmarks(self):
        BOOKMARKS_FILE.write_text(json.dumps(self.bookmarks, ensure_ascii=False, indent=2), encoding="utf-8")

    def show_bookmarks(self):
        menu = QMenu(self)
        if not self.bookmarks:
            menu.addAction("Hozircha xatcho‘p yo‘q").setEnabled(False)
        for item in self.bookmarks:
            menu.addAction(item["title"][:45], lambda checked=False, u=item["url"]: self.navigate(u))
        menu.addSeparator()
        menu.addAction("Joriy sahifani saqlash", self.add_bookmark)
        menu.exec(self.menu_btn.mapToGlobal(self.menu_btn.rect().bottomLeft()))

    def show_history(self):
        menu = QMenu(self)
        if not self.history:
            menu.addAction("Tarix hozircha bo‘sh").setEnabled(False)
        for item in reversed(self.history[-40:]):
            menu.addAction(item["title"][:45], lambda checked=False, u=item["url"]: self.navigate(u))
        menu.exec(self.menu_btn.mapToGlobal(self.menu_btn.rect().bottomLeft()))

    def show_app_menu(self):
        self.app_menu.exec(self.menu_btn.mapToGlobal(self.menu_btn.rect().bottomLeft()))

    def load_enabled_addons(self):
        try:
            data = json.loads(ENABLED_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def save_enabled_addons(self):
        ENABLED_FILE.write_text(json.dumps(self.enabled_addons, ensure_ascii=False, indent=2), encoding="utf-8")

    def installed_records(self):
        records = []
        for folder in ADDONS_DIR.iterdir():
            if not folder.is_dir():
                continue
            mf, cf = folder / "manifest.json", folder / "content.json"
            if not (mf.is_file() and cf.is_file()):
                continue
            try:
                manifest = json.loads(mf.read_text(encoding="utf-8"))
                content = json.loads(cf.read_text(encoding="utf-8"))
                if isinstance(manifest, dict) and isinstance(content, dict):
                    records.append((folder, manifest, content))
                    self.enabled_addons.setdefault(str(manifest.get("id", folder.name)), True)
            except Exception:
                continue
        return records

    def install_package_bytes(self, package, expected_id=None, expected_hash=None, trusted=False):
        digest = hashlib.sha256(package).hexdigest()
        if expected_hash and digest.lower() != str(expected_hash).lower().strip():
            raise ValueError(f"SHA-256 mos kelmadi. Katalog: {expected_hash}; fayl: {digest}")
        is_asi = package.startswith(ASI_MAGIC)
        archive_bytes = package[len(ASI_MAGIC):] if is_asi else package
        try:
            with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
                files = [n for n in archive.namelist() if not n.endswith("/")]
                if len(files) != 2 or set(files) != {"manifest.json", "content.json"}:
                    raise ValueError("Paket ichida aynan manifest.json va content.json bo‘lishi kerak.")
                if any(n.startswith(("/", "\\")) or ".." in Path(n).parts for n in files):
                    raise ValueError("Paketda xavfli fayl yo‘li bor.")
                manifest = json.loads(archive.read("manifest.json").decode("utf-8-sig"))
                content = json.loads(archive.read("content.json").decode("utf-8-sig"))
        except zipfile.BadZipFile as exc:
            raise ValueError("Paket ITL-ASI yoki mos ZIP konteyneri emas.") from exc
        if not isinstance(manifest, dict) or not isinstance(content, dict):
            raise ValueError("manifest.json va content.json JSON obyekt bo‘lishi kerak.")
        addon_id = str(manifest.get("id", ""))
        if not addon_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in addon_id):
            raise ValueError("manifest.json ichida xavfsiz id ko‘rsatilmagan.")
        if expected_id and addon_id != expected_id:
            raise ValueError("Paket ID si katalogdagi qo‘shimcha ID siga mos emas.")
        if is_asi and (manifest.get("package_format") != ASI_FORMAT or manifest.get("package_format_version") != ASI_FORMAT_VERSION):
            raise ValueError("ASI imzosi va manifest format versiyasi mos emas.")
        if manifest.get("package_format") not in (None, ASI_FORMAT):
            raise ValueError("Qo‘shimcha paket formati ITL-ASI emas.")
        kind = manifest.get("type", content.get("type", "learning-content"))
        if kind == "game" and not isinstance(content.get("html"), str):
            raise ValueError("O‘yin paketida content.json ichida html matni bo‘lishi kerak.")
        if kind in ("browser-mod", "browser_mod", "mod"):
            mod = content.get("mod")
            if not isinstance(mod, dict) or content.get("api_version", MOD_API_VERSION) != MOD_API_VERSION:
                raise ValueError("Brauzer modi uchun content.json ichida mod obyekt va api_version: 1 bo‘lishi kerak.")
            scripts = mod.get("scripts", [])
            if not isinstance(scripts, list) or any(not isinstance(x, dict) or not isinstance(x.get("code"), str) for x in scripts):
                raise ValueError("Mod scripts ro‘yxati noto‘g‘ri.")
        elif kind not in ("game", "learning-content", "learning", "content"):
            raise ValueError(f"Noma’lum qo‘shimcha turi: {kind}")
        elif kind != "game" and not isinstance(content.get("lessons"), list) and not isinstance(content.get("html"), str):
            raise ValueError("Dars paketi ichida lessons ro‘yxati yoki html bo‘lishi kerak.")
        target = ADDONS_DIR / addon_id
        target.mkdir(parents=True, exist_ok=True)
        (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        (target / "content.json").write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
        (PACKAGE_CACHE_DIR / f"{addon_id}.pkg").write_bytes(package)
        self.enabled_addons[addon_id] = True
        self.save_enabled_addons()
        self.refresh_mod_controls()
        return manifest, content

    def refresh_mod_controls(self):
        if not hasattr(self, "mods_bar"):
            return
        while self.mods_bar.count():
            item = self.mods_bar.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        if hasattr(self, "mods_menu"):
            self.mods_menu.clear()
        records = self.installed_records()
        count = 0
        if records:
            label = QLabel("MODLAR:")
            label.setStyleSheet("font-weight:600;color:#8aa8cf;padding:0 4px")
            self.mods_bar.addWidget(label)
        for folder, manifest, content in records:
            addon_id = str(manifest.get("id", folder.name))
            kind = manifest.get("type", content.get("type", "learning-content"))
            if kind not in ("browser-mod", "browser_mod", "mod") or not self.enabled_addons.get(addon_id, True):
                continue
            mod = content.get("mod", {})
            for item in mod.get("toolbar", []) if isinstance(mod.get("toolbar", []), list) else []:
                if not isinstance(item, dict) or not isinstance(item.get("action"), dict):
                    continue
                label_text = str(item.get("label", item.get("id", "Mod")))[:24]
                button = QToolButton()
                button.setText(str(item.get("icon", "🧩")) + " " + label_text)
                button.setToolTip(str(item.get("tooltip", manifest.get("name", "Mod"))))
                button.setAutoRaise(True)
                button.clicked.connect(lambda checked=False, a=item["action"], m=manifest: self.execute_mod_action(a, m))
                self.mods_bar.addWidget(button)
                count += 1
            for item in mod.get("menu", []) if isinstance(mod.get("menu", []), list) else []:
                if not isinstance(item, dict) or not isinstance(item.get("action"), dict):
                    continue
                label_text = str(item.get("label", item.get("id", "Mod")))
                action = self.mods_menu.addAction(label_text)
                action.triggered.connect(lambda checked=False, a=item["action"], m=manifest: self.execute_mod_action(a, m))
                count += 1
        self.mods_bar_widget.setVisible(count > 0)
        if hasattr(self, "mods_menu") and self.mods_menu.isEmpty():
            self.mods_menu.addAction("Faol mod funksiyalari yo‘q").setEnabled(False)
        if records and count == 0:
            self.status.setText("Modlar o‘rnatilgan, lekin hozircha yoqilgan brauzer funksiyasi yo‘q")

    def execute_mod_action(self, action, manifest=None):
        kind = action.get("type", "")
        view = self.current_view()
        if kind == "open_url":
            url = str(action.get("url", ""))
            if url.startswith(("https://", "http://")):
                self.add_tab(url)
            else:
                QMessageBox.warning(self, "Mod", "Mod faqat http/https manzilini ochishi mumkin.")
        elif kind == "new_tab":
            self.add_tab(str(action.get("url", INTERNAL_HOME_URL)))
        elif kind == "show_message":
            QMessageBox.information(self, str(action.get("title", manifest.get("name", "Mod") if manifest else "Mod")), str(action.get("message", ""))[:2000])
        elif kind == "toggle_theme":
            self.dark_mode = not self.dark_mode
            self.apply_theme()
        elif kind == "set_theme":
            theme = action.get("theme")
            if theme not in ("dark", "light"):
                return
            self.dark_mode = theme == "dark"
            self.apply_theme()
        elif kind == "copy_url":
            if view:
                QApplication.clipboard().setText(view.url().toString())
                self.status.setText("Sahifa manzili nusxalandi")
        elif kind == "reload":
            if view:
                view.reload()
        elif kind == "search_selection":
            if view:
                view.page().runJavaScript("window.getSelection().toString()", lambda value: self.search_selected_text(value))
        elif kind == "javascript":
            code = action.get("code", "")
            if view and isinstance(code, str) and len(code) <= 50000:
                view.page().runJavaScript(code)
            elif len(str(code)) > 50000:
                QMessageBox.warning(self, "Mod", "JavaScript kodi 50 KB dan oshmasligi kerak.")
        else:
            QMessageBox.warning(self, "Mod", f"Qo‘llab-quvvatlanmaydigan amal: {kind}")

    def search_selected_text(self, value):
        query = str(value or "").strip()
        if query:
            self.add_tab(self.search_template.format(quote_plus(query)))
        else:
            self.status.setText("Avval sahifada matn belgilang")

    def _url_matches(self, pattern, url):
        if pattern == "*":
            return url.startswith(("http://", "https://"))
        if pattern.endswith("*"):
            return url.startswith(pattern[:-1])
        return url == pattern

    def apply_page_mods(self, tab):
        if not hasattr(self, "tabs") or self.tabs.indexOf(tab) < 0:
            return
        url = tab.view.url().toString()
        api_js = r"""(() => {
          if (window.ITLearnBrowser && window.ITLearnBrowser.apiVersion === 1) return;
          const toast = (message) => {
            let box = document.getElementById('__itl_mod_toast');
            if (!box) { box = document.createElement('div'); box.id='__itl_mod_toast'; box.style.cssText='position:fixed;z-index:2147483647;right:18px;bottom:18px;max-width:360px;padding:12px 16px;border-radius:12px;background:#172338;color:#fff;box-shadow:0 8px 30px #0006;font:14px Segoe UI,Arial'; document.documentElement.appendChild(box); }
            box.textContent = String(message).slice(0,500); box.style.display='block'; clearTimeout(box.__timer); box.__timer=setTimeout(()=>box.style.display='none',3500);
          };
          window.ITLearnBrowser = {
            apiVersion: 1,
            notify: toast,
            addStyle(css) { const s=document.createElement('style'); s.textContent=String(css); (document.head||document.documentElement).appendChild(s); return s; },
            highlight(selector, color) { let n=0; try { document.querySelectorAll(selector).forEach(e=>{e.style.outline='2px solid '+(color||'#ffb020');e.style.outlineOffset='2px';n++;}); } catch(e) {} return n; },
            getPageInfo() { return {title:document.title,url:location.href,host:location.host}; },
            addPanel(options) { const o=options||{}; const id=String(o.id||'itl-mod-panel').replace(/[^a-z0-9_-]/gi,''); let p=document.getElementById(id); if(p)p.remove(); p=document.createElement('section');p.id=id;p.style.cssText='position:fixed;z-index:2147483646;right:16px;top:90px;width:min(340px,85vw);max-height:65vh;overflow:auto;background:#172338;color:#fff;border:1px solid #57708f;border-radius:14px;padding:14px;box-shadow:0 12px 36px #0008;font:14px Segoe UI,Arial'; const h=document.createElement('div');h.textContent=String(o.title||'IT Learn Browser mod');h.style.cssText='font-weight:700;margin-bottom:10px';const b=document.createElement('button');b.textContent='×';b.style.cssText='float:right;cursor:pointer';b.onclick=()=>p.remove();p.append(b,h);const c=document.createElement('div');c.innerHTML=String(o.html||'');p.append(c);document.documentElement.appendChild(p);return p; }
          };
        })();"""
        tab.view.page().runJavaScript(api_js)
        if not url.startswith(("http://", "https://")):
            return
        for folder, manifest, content in self.installed_records():
            addon_id = str(manifest.get("id", folder.name))
            kind = manifest.get("type", content.get("type", ""))
            if kind not in ("browser-mod", "browser_mod", "mod") or not self.enabled_addons.get(addon_id, True):
                continue
            scripts = content.get("mod", {}).get("scripts", [])
            for script in scripts:
                matches = script.get("matches", ["*"])
                if isinstance(matches, str):
                    matches = [matches]
                if any(self._url_matches(str(p), url) for p in matches):
                    code = script.get("code", "")
                    if isinstance(code, str) and len(code) <= 100000:
                        tab.view.page().runJavaScript(code)

    def open_addon_store(self):
        dialog = AddonStoreDialog(self)
        dialog.exec()

    def show_installed_addons(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("O‘rnatilgan qo‘shimchalar va modlar")
        dialog.resize(650, 460)
        layout = QVBoxLayout(dialog)
        info = QLabel("Modlarni belgilang va saqlang. O‘chirilgan modlarning funksiyalari brauzerda ishlamaydi.")
        layout.addWidget(info)
        items = QListWidget()
        records = self.installed_records()
        for folder, manifest, content in records:
            addon_id = str(manifest.get("id", folder.name))
            kind = manifest.get("type", content.get("type", "learning-content"))
            label = f"{manifest.get('name', addon_id)} — v{manifest.get('version', '?')} [{kind}]"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, addon_id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if self.enabled_addons.get(addon_id, True) else Qt.Unchecked)
            items.addItem(item)
        layout.addWidget(items, 1)
        buttons = QHBoxLayout()
        launch = QPushButton("Ishga tushirish")
        import_btn = QPushButton("Paket import qilish")
        uninstall = QPushButton("Tanlanganini o‘chirish")
        save = QPushButton("Holatni saqlash")
        close = QPushButton("Yopish")
        buttons.addWidget(launch)
        buttons.addWidget(import_btn)
        buttons.addWidget(uninstall)
        buttons.addWidget(save)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        def save_states():
            for i in range(items.count()):
                item = items.item(i)
                self.enabled_addons[item.data(Qt.UserRole)] = item.checkState() == Qt.Checked
            self.save_enabled_addons()
            self.refresh_mod_controls()
            self.status.setText("Modlar holati saqlandi")

        def run_selected():
            save_states()
            idx = items.currentRow()
            if idx < 0 or idx >= len(records):
                QMessageBox.information(dialog, "Tanlanmagan", "Avval qo‘shimchani tanlang.")
                return
            folder, manifest, content = records[idx]
            addon_id = str(manifest.get("id", folder.name))
            if not self.enabled_addons.get(addon_id, True):
                QMessageBox.information(dialog, "Mod o‘chiq", "Avval modni belgilang va holatini saqlang.")
                return
            kind = manifest.get("type", content.get("type", "learning-content"))
            if kind in ("browser-mod", "browser_mod", "mod"):
                mod = content.get("mod", {})
                info_text = f"{manifest.get('name')} mod yoqildi. Uning toolbar yoki menyu funksiyalaridan foydalaning."
                QMessageBox.information(dialog, "Mod faol", info_text)
                dialog.accept()
                return
            if isinstance(content.get("html"), str):
                tab = self.add_tab("about:blank")
                tab.view.setHtml(content["html"], QUrl("about:blank"))
                tab_index = self.tabs.indexOf(tab)
                if tab_index >= 0:
                    self.tabs.setTabText(tab_index, manifest.get("name", "O‘yin")[:22])
                self.status.setText("O‘yin ochildi — paket ichidagi offline HTML")
                dialog.accept()
                return
            runner = AddonRunnerDialog(manifest, content, self)
            runner.exec()

        def import_local():
            path, _ = QFileDialog.getOpenFileName(dialog, "Paketni tanlang", str(Path.home()), "ITL paketlari (*.asi *.zip *.pkg);;Barcha fayllar (*.*)")
            if not path:
                return
            try:
                package = Path(path).read_bytes()
                digest = hashlib.sha256(package).hexdigest()
                ok = QMessageBox.question(dialog, "Ishonch tekshiruvi", f"SHA-256: {digest}\n\nFaqat ishonchli paketni import qiling. Davom etilsin?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if ok != QMessageBox.Yes:
                    return
                manifest, _ = self.install_package_bytes(package, trusted=False)
                QMessageBox.information(dialog, "Import qilindi", f"{manifest.get('name')} o‘rnatildi.")
                dialog.accept()
                self.show_installed_addons()
            except Exception as exc:
                QMessageBox.critical(dialog, "Import xatosi", str(exc))

        def remove_selected():
            idx = items.currentRow()
            if idx < 0 or idx >= len(records):
                return
            folder, manifest, content = records[idx]
            addon_id = str(manifest.get("id", folder.name))
            answer = QMessageBox.question(dialog, "O‘chirish", f"{manifest.get('name', addon_id)} qo‘shimchasi o‘chirilsinmi?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
            shutil.rmtree(folder, ignore_errors=True)
            self.enabled_addons.pop(addon_id, None)
            self.save_enabled_addons()
            self.refresh_mod_controls()
            dialog.accept()
            self.show_installed_addons()

        launch.clicked.connect(run_selected)
        import_btn.clicked.connect(import_local)
        uninstall.clicked.connect(remove_selected)
        save.clicked.connect(save_states)
        close.clicked.connect(dialog.accept)
        if items.count():
            items.setCurrentRow(0)
        dialog.exec()

    def open_settings(self):
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.Accepted:
            self.search_template = dialog.search.currentData()
            self.home_url = dialog.home.text().strip() or HOME_URL
            self.dark_mode = dialog.dark.isChecked()
            self.apply_theme()

    def apply_theme(self):
        if self.dark_mode:
            self.setStyleSheet("""
                QMainWindow, QWidget { background:#202124; color:#e8eaed; font-family:'Segoe UI'; font-size:10pt; }
                QTabWidget::pane { border:1px solid #3c4043; border-radius:10px; background:#fff; }
                QTabBar::tab { background:#303134; color:#bdc1c6; padding:8px 14px; margin-right:4px; border-radius:9px; }
                QTabBar::tab:selected { background:#45474a; color:white; }
                QLineEdit { background:#303134; color:#f1f3f4; border:1px solid #4a4d50; border-radius:16px; padding:8px 14px; selection-background-color:#8ab4f8; }
                QToolButton, QPushButton { background:#303134; color:#e8eaed; border:0; border-radius:9px; padding:5px; }
                QToolButton:hover, QPushButton:hover { background:#45474a; }
                QToolButton:disabled { color:#666; }
                QLabel#status { color:#9aa0a6; font-size:9pt; padding-left:5px; }
                QMenu { background:#303134; color:#eee; border:1px solid #555; }
                QMenu::item:selected { background:#4b4e52; }
                QComboBox { background:#303134; padding:6px; border-radius:6px; }
            """)
        else:
            self.setStyleSheet("""
                QMainWindow, QWidget { background:#f5f6f8; color:#202124; font-family:'Segoe UI'; font-size:10pt; }
                QTabWidget::pane { border:1px solid #d8dce2; border-radius:10px; background:white; }
                QTabBar::tab { background:#e8eaed; color:#444; padding:8px 14px; margin-right:4px; border-radius:9px; }
                QTabBar::tab:selected { background:white; color:#111; }
                QLineEdit { background:white; color:#202124; border:1px solid #d4d8de; border-radius:16px; padding:8px 14px; }
                QToolButton, QPushButton { background:#e8eaed; color:#202124; border:0; border-radius:9px; padding:5px; }
                QToolButton:hover, QPushButton:hover { background:#d9dde3; }
                QLabel#status { color:#666; font-size:9pt; padding-left:5px; }
            """)

    def open_downloads(self):
        path = Path.home() / "Downloads"
        os.startfile(str(path))

    def new_window(self):
        self.other_window = BrowserWindow()
        self.other_window.show()

    def about(self):
        QMessageBox.about(self, APP_NAME, "IT Learn Browser\n\nPython 3.13 + PySide6 + Chromium WebEngine\nGoogle qidiruvi va haqiqiy veb-sahifalar uchun mustaqil brauzer.")

    def closeEvent(self, event):
        event.accept()


def configure_downloads(profile):
    def on_download(download: QWebEngineDownloadRequest):
        downloads = Path.home() / "Downloads"
        downloads.mkdir(exist_ok=True)
        name = download.downloadFileName() or "download"
        download.setDownloadDirectory(str(downloads))
        download.setDownloadFileName(name)
        download.accept()
    profile.downloadRequested.connect(on_download)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("IT Learn")
    app.setStyle("Fusion")
    profile = QWebEngineProfile.defaultProfile()
    configure_downloads(profile)
    window = BrowserWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
