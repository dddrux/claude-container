#!/usr/bin/env python3
"""Claude Containers — navegador (Chromium/QtWebEngine) com um perfil isolado por conta,
no estilo do ZapZap. Cada perfil tem cookies, cache e storage próprios."""

import base64
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from PyQt6.QtCore import (QEasingCurve, QEvent, QPoint, QProcess, QProcessEnvironment, Qt, QPointF, QRectF, QSize, QTimer,
                          QUrl, QVariantAnimation)
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtGui import (QAction, QColor, QDesktopServices, QFont, QIcon,
                         QKeySequence, QPainter, QPainterPath, QPalette, QPen, QPixmap,
                         QShortcut)
from PyQt6.QtWebEngineCore import (QWebEngineDownloadRequest, QWebEnginePage,
                                   QWebEngineProfile, QWebEngineScript,
                                   QWebEngineSettings)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (QApplication, QButtonGroup, QColorDialog,
                             QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel,
                             QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea,
                             QSizePolicy, QSplitter, QStackedWidget, QSystemTrayIcon, QToolButton,
                             QVBoxLayout, QWidget)

APP = "claude-containers"
HOME_URL = "https://claude.ai/"
CONFIG_DIR = Path.home() / ".config" / APP
DATA_DIR = Path.home() / ".local" / "share" / APP
CONFIG_FILE = CONFIG_DIR / "profiles.json"
ICON_FILE = CONFIG_DIR / "deepseek_icon.png"  # favicon do próprio site, guardado em cache
DEEPSEEK_URL = "https://chat.deepseek.com/"  # painel lateral global (todos os perfis)
DEEPSEEK_ALLOWED = (
    "deepseek.com", "google.com", "gstatic.com", "googleusercontent.com", "recaptcha.net",
    "cloudflare.com", "hcaptcha.com", "apple.com", "aliyun.com", "alicdn.com", "aliyuncs.com",
)
FROZEN = bool(getattr(sys, "frozen", False))  # PyInstaller (AppImage / setup.exe)
# instalado (install.sh/AppImage/setup.exe) -> dado do usuário; rodando do código-fonte (run.sh) -> raiz do projeto
INSTALLED = FROZEN or bool(os.environ.get("CC_INSTALLED"))
PAUSE_FILE = (DATA_DIR / "pausas.json") if INSTALLED else Path(__file__).resolve().parent / "pausas.json"


def clean_env() -> dict:
    """Ambiente para programas externos (notify-send...): sem as libs embutidas do PyInstaller/AppImage."""
    e = dict(os.environ)
    orig = e.pop("LD_LIBRARY_PATH_ORIG", None)
    if orig is not None:
        e["LD_LIBRARY_PATH"] = orig
    elif FROZEN:
        e.pop("LD_LIBRARY_PATH", None)
    return e
PAUSE_HOURS = 5
SNIP_JS = (
    "(function(){var t=document.title||'';"
    "var els=document.querySelectorAll('[data-is-streaming],.font-claude-response,.font-claude-message');"
    "var e=els.length?els[els.length-1]:null;var x=e?(e.innerText||''):'';"
    "return JSON.stringify({t:t,b:x.replace(/\\s+/g,' ').trim().slice(0,160)});})()"
)  # título do chat + início da última resposta
BUSY_JS = (
    "!!(document.querySelector('[data-is-streaming=\"true\"]')||"
    "document.querySelector('button[aria-label*=\"Stop\" i],button[aria-label*=\"Parar\" i],"
    "button[aria-label*=\"Interromper\" i],button[aria-label*=\"Detener\" i],"
    "button[data-testid*=\"stop\" i]'))"
)  # true enquanto o Claude está gerando resposta

# Domínios que abrem dentro do app (login/OAuth/pagamento). O resto vai pro navegador do sistema.
ALLOWED = (
    "claude.ai", "claude.com", "anthropic.com", "google.com", "gstatic.com",
    "googleusercontent.com", "apple.com", "microsoft.com", "live.com",
    "microsoftonline.com", "stripe.com", "cloudflare.com", "hcaptcha.com",
    "recaptcha.net", "okta.com",
)
COLORS = ["#D97757", "#6A9BCC", "#788C5D", "#C46686", "#D4A27F", "#8E7CC3", "#4FA3A5"]
OLD_COLORS = ["#d97757", "#4f8cff", "#3ecf8e", "#b57bee", "#f2b84b", "#ef5b7b", "#2cb5c5"]


THEMES = {
    "light": dict(bg="#FAF9F5", side="#F0EEE6", border="#DDD9CC", text="#141413",
                  hover="#E6E2D6", field="#FFFFFF", field_border="#D8D3C5", sel="#EFEBE0",
                  accent="#C15F3C", accent_hover="#AE5334", dashed="#BDB7A6", plus="#7A776C",
                  tip_bg="#141413", tip_fg="#FAF9F5", checked="#FAF9F5", sep="#E5E1D5"),
    "dark": dict(bg="#262624", side="#1F1E1D", border="#3A3935", text="#FAF9F5",
                 hover="#30302E", field="#1F1E1D", field_border="#4A4944", sel="#3A3935",
                 accent="#D97757", accent_hover="#E58A6D", dashed="#5A5851", plus="#A6A39A",
                 tip_bg="#FAF9F5", tip_fg="#141413", checked="#30302E", sep="#3A3935"),
}
THEME = "dark"
T = THEMES[THEME]


def set_theme(name: str):
    global THEME, T
    THEME = name if name in THEMES else "dark"
    T = THEMES[THEME]


def css(template: str) -> str:
    """Troca tokens @chave pelas cores do tema atual."""
    for k in sorted(T, key=len, reverse=True):
        template = template.replace("@" + k, T[k])
    return template


def is_allowed(url: QUrl, domains=ALLOWED) -> bool:
    if url.scheme() in ("about", "blob", "data", "qrc", ""):
        return True
    host = url.host().lower()
    return any(host == d or host.endswith("." + d) for d in domains)


# ---------------------------------------------------------------- config

def load_config() -> dict:
    cfg = {"profiles": [], "last": None, "pending_delete": [], "theme": "dark",
           "notes_open": False, "notes_width": 440}
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text()))
        except Exception:
            pass
    # limpa perfis removidos na sessão anterior (arquivos já não estão em uso)
    for pid in cfg.get("pending_delete", []):
        shutil.rmtree(DATA_DIR / "profiles" / pid, ignore_errors=True)
    cfg["pending_delete"] = []
    remap = dict(zip(OLD_COLORS, COLORS))
    for pr in cfg["profiles"]:  # migra as cores vibrantes antigas para a paleta nova
        pr["color"] = remap.get(pr["color"].lower(), pr["color"])
    if not cfg["profiles"]:
        cfg["profiles"] = [new_profile("Pessoal", COLORS[0])]
    return cfg


def save_config(cfg: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))


def _now() -> datetime:
    return datetime.now().astimezone()


def save_pauses(d: dict):
    try:
        PAUSE_FILE.parent.mkdir(parents=True, exist_ok=True)
        PAUSE_FILE.write_text(json.dumps(d, indent=2, ensure_ascii=False))
    except OSError:
        pass


def load_pauses() -> dict:
    """Lê pausas.json e descarta as que já passaram das 5h."""
    data = {}
    if PAUSE_FILE.exists():
        try:
            data = json.loads(PAUSE_FILE.read_text())
        except Exception:
            data = {}
    now, clean = _now(), {}
    for pid, info in data.items():
        try:
            if datetime.fromisoformat(info["volta_em"]) > now:
                clean[pid] = info
        except Exception:
            pass
    if clean != data:
        save_pauses(clean)
    return clean


def new_profile(name: str, color: str) -> dict:
    return {"id": uuid.uuid4().hex[:10], "name": name, "color": color}


def draw_spark(p, cx, cy, r, color):
    """Faísca no estilo do logo do Claude: 12 raios grossos, pontas redondas, centro cheio."""
    lengths = [1.0, 0.74, 0.92, 0.68, 1.0, 0.78, 0.90, 0.70, 1.0, 0.72, 0.94, 0.76]
    w = r * 0.20
    pen = QPen(QColor(color))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setWidthF(w)
    p.save()
    p.translate(cx, cy)
    p.setPen(pen)
    for i, ln in enumerate(lengths):
        p.save()
        p.rotate(i * 30 + 8)
        p.drawLine(QPointF(0, 0), QPointF(0, -(r * ln - w / 2)))
        p.restore()
    p.restore()


def make_icon(name: str, color: str, size: int = 32, badge: bool = True, paused: bool = False) -> QIcon:
    dpr = 3
    pm = QPixmap(size * dpr, size * dpr)
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    if paused:  # em pausa: ícone preto
        p.setPen(QPen(QColor("#5A5851"), 1.2))
        p.setBrush(QColor("#000000"))
        p.drawRoundedRect(QRectF(0.6, 0.6, size - 1.2, size - 1.2), size * 0.26, size * 0.26)
        draw_spark(p, size / 2, size / 2, size * 0.38, "#6B6A63")
        p.end()
        return QIcon(pm)
    p.setBrush(QColor(color))
    p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.26, size * 0.26)
    draw_spark(p, size / 2, size / 2, size * 0.38, "#FFFFFF")
    if badge and name and size >= 36:
        d = size * 0.34
        rect = QRectF(size - d, size - d, d, d)
        p.setBrush(QColor(T["bg"]))
        p.setPen(QPen(QColor(color), 1.4))
        p.drawEllipse(rect)
        f = QFont()
        f.setBold(True)
        f.setPixelSize(int(d * 0.62))
        p.setFont(f)
        p.setPen(QColor(T["text"]))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, name[:1].upper())
    p.end()
    return QIcon(pm)


def apply_theme(app: QApplication):
    app.setStyle("Fusion")
    try:  # faz o claude.ai (modo "auto") seguir o tema do app
        app.styleHints().setColorScheme(
            Qt.ColorScheme.Dark if THEME == "dark" else Qt.ColorScheme.Light)
    except Exception:
        pass
    pal = QPalette()
    R = QPalette.ColorRole
    pal.setColor(R.Window, QColor(T["bg"]))
    pal.setColor(R.WindowText, QColor(T["text"]))
    pal.setColor(R.Base, QColor(T["field"]))
    pal.setColor(R.AlternateBase, QColor(T["bg"]))
    pal.setColor(R.Text, QColor(T["text"]))
    pal.setColor(R.PlaceholderText, QColor(T["plus"]))
    pal.setColor(R.Button, QColor(T["bg"]))
    pal.setColor(R.ButtonText, QColor(T["text"]))
    pal.setColor(R.Highlight, QColor(T["accent"]))
    pal.setColor(R.HighlightedText, QColor("#FFFFFF"))
    pal.setColor(R.ToolTipBase, QColor(T["tip_bg"]))
    pal.setColor(R.ToolTipText, QColor(T["tip_fg"]))
    app.setPalette(pal)
    app.setStyleSheet(css("""
        QMenu{background:@bg;color:@text;border:1px solid @border;border-radius:10px;padding:6px;}
        QMenu::item{padding:7px 20px;border-radius:6px;}
        QMenu::item:selected{background:@sel;color:@text;}
        QMenu::separator{height:1px;background:@sep;margin:5px 8px;}
        QDialog,QMessageBox,QInputDialog{background:@bg;}
        QLabel{color:@text;}
        QLineEdit{background:@field;color:@text;border:1px solid @field_border;border-radius:8px;
                  padding:6px 8px;selection-background-color:@accent;}
        QLineEdit:focus{border:1px solid @accent;}
        QPushButton{background:@bg;border:1px solid @field_border;border-radius:8px;
                    padding:6px 18px;color:@text;}
        QPushButton:hover{background:@sel;}
        QPushButton:default{background:@accent;border-color:@accent;color:#FFFFFF;}
        QPushButton:default:hover{background:@accent_hover;}
        QToolTip{background:@field;color:@text;border:1px solid @border;padding:5px 8px;}
    """))


# ---------------------------------------------------------------- web

class PopupWindow(QWidget):
    """Janela para window.open (OAuth etc.), compartilhando o perfil."""
    alive: set = set()

    def __init__(self, profile: QWebEngineProfile, allowed=ALLOWED):
        super().__init__()
        self.allowed = allowed
        PopupWindow.alive.add(self)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(520, 700)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.view = QWebEngineView(self)
        self.web = QWebEnginePage(profile, self.view)
        self.view.setPage(self.web)
        lay.addWidget(self.view)
        self.web.urlChanged.connect(self._url_changed)
        self.web.loadFinished.connect(lambda _ok: self.show())
        self.web.windowCloseRequested.connect(self.close)

    def _url_changed(self, url: QUrl):
        if url.isEmpty() or url.toString() == "about:blank":
            return
        if not is_allowed(url, self.allowed):
            QDesktopServices.openUrl(url)
            self.close()
        else:
            self.show()

    def closeEvent(self, e):
        PopupWindow.alive.discard(self)
        super().closeEvent(e)


class ClaudePage(QWebEnginePage):
    allowed = ALLOWED

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if (is_main_frame and not is_allowed(url, self.allowed)
                and nav_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked):
            QDesktopServices.openUrl(url)
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)

    def createWindow(self, _type):
        return PopupWindow(self.profile(), self.allowed).web


class DeepSeekPage(ClaudePage):
    allowed = DEEPSEEK_ALLOWED


# Faz o site enxergar o app como modo escuro/claro (matchMedia prefers-color-scheme).
SCHEME_JS = r"""(function(){var dark=__DARK__;var o=window.matchMedia.bind(window);
window.matchMedia=function(q){var m=/prefers-color-scheme\s*:\s*(dark|light)/.exec(q||'');
var r=o(q);if(!m)return r;var v=((m[1]==='dark')===dark);
return {matches:v,media:q,onchange:null,addEventListener:function(){},removeEventListener:function(){},
addListener:function(){},removeListener:function(){},dispatchEvent:function(){return false;}};};})();"""


# Selos/etiquetas do claude.ai que somem da interface (texto exato, sem diferenciar maiúsculas). Edite à vontade.
HIDE_LABELS = ["Fazer upgrade", "Experimental"]
CLEAN_JS = r"""(function(){
var L=__LABELS__.map(function(s){return s.toLowerCase();});
var SKIP='.font-claude-response,.font-claude-message,[data-testid="user-message"],textarea,[contenteditable="true"],pre,code';
function hide(e){e.style.setProperty('display','none','important');e.dataset.ccHid='1';}
function scan(){
  if(!document.body)return;
  var els=document.body.querySelectorAll('span,div,p,small,em');
  for(var i=0;i<els.length;i++){var e=els[i];
    if(e.dataset&&e.dataset.ccHid)continue;
    if(e.children.length)continue;
    var t=(e.textContent||'').trim().toLowerCase();
    if(L.indexOf(t)<0||e.closest(SKIP)||e.offsetHeight>32)continue;
    hide(e);
    var p=e.parentElement;  // a "pílula" pode ser um wrapper só com o texto
    for(var k=0;k<2&&p;k++,p=p.parentElement){
      if((p.textContent||'').trim().toLowerCase()===t&&p.offsetHeight<=40)hide(p);else break;}
  }
}
var tm=null;function sched(){if(tm)return;tm=setTimeout(function(){tm=null;scan();},250);}
new MutationObserver(sched).observe(document.documentElement,{childList:true,subtree:true,characterData:true});
sched();})();"""


class Tip(QLabel):
    """Tooltip próprio: cantos arredondados, borda fina e cores do tema (o do Qt é um retângulo cru)."""

    def __init__(self):
        super().__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setContentsMargins(11, 6, 11, 6)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(T["border"]), 1))
        p.setBrush(QColor(T["field"]))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
        p.end()
        super().paintEvent(e)

    def show_for(self, w: QWidget, text: str):
        self.setStyleSheet(css("color:@text;font-size:12px;background:transparent;"))
        self.setText(text)
        self.adjustSize()
        g = w.mapToGlobal(QPoint(w.width() + 8, (w.height() - self.height()) // 2))
        self.move(g)
        self.show()


class LoadingOverlay(QWidget):
    """Tela de carregamento: faísca pulsando + barra de progresso; vira tela de erro se falhar."""

    def __init__(self, parent, on_retry, label="Claude"):
        super().__init__(parent)
        self.label = label
        self.angle, self.progress, self.error, self.tick = 0.0, 0, False, 0
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self._tick)
        self.retry = QPushButton("Tentar novamente", self)
        self.retry.setCursor(Qt.CursorShape.PointingHandCursor)
        self.retry.setDefault(True)
        self.retry.clicked.connect(on_retry)
        self.retry.hide()
        self.hide()

    def _tick(self):
        self.angle = (self.angle + 2.5) % 360
        self.tick += 1
        self.update()

    def start(self):
        self.error, self.progress = False, 0
        self.retry.hide()
        self.setGeometry(self.parentWidget().rect())
        self.raise_()
        self.show()
        self.timer.start()

    def set_progress(self, v: int):
        self.progress = v
        self.update()

    def fail(self):
        self.error = True
        self.timer.stop()
        self.retry.show()
        self.raise_()
        self.show()
        self.update()

    def done(self):
        self.timer.stop()
        self.hide()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.retry.adjustSize()
        self.retry.move((self.width() - self.retry.width()) // 2, self.height() // 2 + 60)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(T["bg"]))
        cx, cy = self.width() / 2, self.height() / 2 - 30
        if self.error:
            draw_spark(p, cx, cy, 34, T["dashed"])
            p.setPen(QColor(T["text"]))
            f = QFont(); f.setPixelSize(16); f.setBold(True); p.setFont(f)
            p.drawText(QRectF(0, cy + 50, self.width(), 24), Qt.AlignmentFlag.AlignCenter,
                       f"Não foi possível carregar o {self.label}")
            f.setBold(False); f.setPixelSize(13); p.setFont(f)
            p.setPen(QColor(T["plus"]))
            p.drawText(QRectF(0, cy + 76, self.width(), 20), Qt.AlignmentFlag.AlignCenter,
                       "Verifique sua conexão e tente de novo.")
            p.end()
            return
        r = 34 * (1 + 0.07 * math.sin(self.tick / 8))
        p.save()
        p.translate(cx, cy)
        p.rotate(self.angle)
        draw_spark(p, 0, 0, r, T["accent"])
        p.restore()
        p.setPen(QColor(T["plus"]))
        f = QFont(); f.setPixelSize(13); p.setFont(f)
        p.drawText(QRectF(0, cy + 50, self.width(), 20), Qt.AlignmentFlag.AlignCenter, "Carregando…")
        bw, bh = 160, 4
        x, y = cx - bw / 2, cy + 82
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(T["border"]))
        p.drawRoundedRect(QRectF(x, y, bw, bh), 2, 2)
        p.setBrush(QColor(T["accent"]))
        p.drawRoundedRect(QRectF(x, y, bw * max(self.progress, 4) / 100, bh), 2, 2)
        p.end()


class ProfileView(QWebEngineView):
    """Uma conta = um QWebEngineProfile com disco próprio."""

    def __init__(self, pdata: dict, parent=None, home=HOME_URL, page_cls=None, label="Claude"):
        super().__init__(parent)
        self.pdata = pdata
        self.home = home
        self._loading = False
        base = DATA_DIR / "profiles" / pdata["id"]
        (base / "storage").mkdir(parents=True, exist_ok=True)
        (base / "cache").mkdir(parents=True, exist_ok=True)

        self.qprofile = QWebEngineProfile(f"{APP}-{pdata['id']}", self)
        self.qprofile.setPersistentStoragePath(str(base / "storage"))
        self.qprofile.setCachePath(str(base / "cache"))
        self.qprofile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        self.qprofile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
        self.qprofile.downloadRequested.connect(self._download)

        s = self.qprofile.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)

        self.web = (page_cls or ClaudePage)(self.qprofile, self)
        self.setPage(self.web)
        self.web.setBackgroundColor(QColor(T["bg"]))
        self.web.fullScreenRequested.connect(lambda r: r.accept())
        self.set_scheme(THEME == "dark", reload=False)
        if page_cls is None and HIDE_LABELS:  # só nas contas do Claude (não no painel DeepSeek)
            sc = QWebEngineScript()
            sc.setName("cleanup")
            sc.setSourceCode(CLEAN_JS.replace("__LABELS__", json.dumps(HIDE_LABELS, ensure_ascii=False)))
            sc.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
            sc.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
            sc.setRunsOnSubFrames(False)
            self.web.scripts().insert(sc)
        self.setZoomFactor(float(pdata.get("zoom", 1.0)))

        self.overlay = LoadingOverlay(self, self.reload_home, label)
        self.web.loadStarted.connect(self._load_started)
        self.web.loadProgress.connect(self.overlay.set_progress)
        self.web.loadFinished.connect(self._load_finished)
        self.overlay.start()
        self.load(QUrl(self.home))

    def _load_started(self):
        self._loading = True
        self.overlay.start()

    def _load_finished(self, ok: bool):
        if ok:
            self._loading = False
            self.overlay.done()
        elif self._loading:
            self._loading = False
            self.overlay.fail()

    def reload_home(self):
        url = self.url()
        self.load(url if url.isValid() and not url.isEmpty() and is_allowed(url, self.web.allowed) else QUrl(self.home))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, "overlay"):
            self.overlay.setGeometry(self.rect())

    def set_scheme(self, dark: bool, reload: bool = True):
        coll = self.web.scripts()
        for old in coll.find("scheme"):
            coll.remove(old)
        sc = QWebEngineScript()
        sc.setName("scheme")
        sc.setSourceCode(SCHEME_JS.replace("__DARK__", "true" if dark else "false"))
        sc.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        sc.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        sc.setRunsOnSubFrames(True)
        coll.insert(sc)
        if reload:
            self.reload()

    def _download(self, d: QWebEngineDownloadRequest):
        default = str(Path.home() / "Downloads" / d.downloadFileName())
        path, _ = QFileDialog.getSaveFileName(self, "Salvar arquivo", default)
        if not path:
            d.cancel()
            return
        p = Path(path)
        d.setDownloadDirectory(str(p.parent))
        d.setDownloadFileName(p.name)
        d.accept()

    def clear_data(self):
        self.qprofile.cookieStore().deleteAllCookies()
        self.qprofile.clearHttpCache()
        self.qprofile.clearAllVisitedLinks()
        self.load(QUrl(self.home))


# ---------------------------------------------------------------- UI

class ProfileButton(QToolButton):
    """Botão de perfil; o selecionado ganha uma barrinha de destaque à esquerda."""

    done = False  # Claude respondeu e a conta ainda não foi aberta

    def paintEvent(self, e):
        super().paintEvent(e)
        if self.isChecked() or self.done:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(T["accent"]))
            if self.isChecked():
                p.drawRoundedRect(QRectF(0, self.height() * 0.22, 3, self.height() * 0.56), 1.5, 1.5)
            if self.done:
                p.setBrush(QColor(T["side"]))
                p.drawEllipse(QPointF(self.width() - 8, 8), 7, 7)
                p.setBrush(QColor(ORANGE))
                p.drawEllipse(QPointF(self.width() - 8, 8), 5, 5)
            p.end()


class IconButton(QToolButton):
    """Botão com ícone vetorial desenhado à mão (nítido em qualquer DPI e segue o tema)."""

    def __init__(self, kind: str):
        super().__init__()
        self.kind = kind
        self.pix = None

    def set_pix(self, pm: QPixmap):
        """Usa a imagem (ex.: ícone do site) no lugar do desenho vetorial."""
        self.pix = pm
        self.kind = "app"
        self.update()

    def set_kind(self, kind: str):
        self.kind = kind
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        hot = self.underMouse() or self.isChecked()
        col = QColor(T["accent"] if hot else T["plus"])
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(col, 1.7)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        if self.kind == "plus":  # borda tracejada própria (a do stylesheet sai cortada)
            dp = QPen(QColor(T["accent"] if hot else T["dashed"]), 2)
            dp.setStyle(Qt.PenStyle.DashLine)
            dp.setCapStyle(Qt.PenCapStyle.FlatCap)
            p.setPen(dp)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5), 10, 10)
            p.setPen(pen)
        p.translate(self.width() / 2, self.height() / 2)
        k = self.kind
        if k == "plus":
            p.drawLine(QPointF(-7, 0), QPointF(7, 0))
            p.drawLine(QPointF(0, -7), QPointF(0, 7))
        elif k == "app" and self.pix is not None:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.setOpacity(1.0 if hot else 0.85)
            p.drawPixmap(QRectF(-11, -11, 22, 22), self.pix, QRectF(self.pix.rect()))
        elif k == "notes":  # balão de conversa (até o ícone do site ser baixado)
            p.drawRoundedRect(QRectF(-8, -8, 16, 12.5), 4, 4)
            p.drawPolyline([QPointF(-4, 4.5), QPointF(-4, 8.5), QPointF(0.5, 4.5)])
            p.drawLine(QPointF(-3.5, -3.5), QPointF(3.5, -3.5))
            p.drawLine(QPointF(-3.5, 0), QPointF(1.5, 0))
        elif k == "sun":
            p.drawEllipse(QPointF(0, 0), 3.6, 3.6)
            for i in range(8):
                p.save()
                p.rotate(i * 45)
                p.drawLine(QPointF(0, -6.4), QPointF(0, -8.2))
                p.restore()
        elif k == "moon":
            from PyQt6.QtGui import QPainterPath
            path = QPainterPath()
            path.addEllipse(QPointF(0, 0), 7, 7)
            cut = QPainterPath()
            cut.addEllipse(QPointF(4, -3), 6, 6)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col)
            p.drawPath(path.subtracted(cut))
        p.end()


ORANGE = "#D97757"
ORANGE_DK = "#C15F3C"
INK = "#141413"
BTN_IDLE = "#C9694A"   # botões da barra: um tom abaixo do laranja
BTN_HOVER = "#B0532F"
BAR_H = 36
FRAME = 4  # espessura da moldura laranja (também é a zona de redimensionamento)
GRIP = 14  # zona de canto para redimensionar


class WinBtn(QToolButton):
    """Botão da barra de título (min/max/fechar), desenhado à mão."""

    def __init__(self, kind: str):
        super().__init__()
        self.kind = kind
        self.setFixedSize(40, BAR_H)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._hov = False

    def enterEvent(self, e):
        self._hov = True
        self.update()

    def leaveEvent(self, e):
        self._hov = False
        self.update()

    def hideEvent(self, e):
        self._hov = False
        super().hideEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        hov = self._hov
        p.fillRect(self.rect(), QColor(BTN_IDLE))
        if hov:
            p.fillRect(self.rect(), QColor(INK if self.kind == "close" else BTN_HOVER))
        col = QColor("#FAF9F5" if hov and self.kind == "close" else INK)
        pen = QPen(col)
        pen.setWidthF(1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        cx, cy = self.width() / 2, self.height() / 2
        if self.kind == "min":
            p.drawLine(QPointF(cx - 5, cy + 3), QPointF(cx + 5, cy + 3))
        elif self.kind == "max":
            if self.window().isMaximized():
                p.drawRect(QRectF(cx - 5, cy - 2, 7, 7))
                p.drawLine(QPointF(cx - 2, cy - 5), QPointF(cx + 5, cy - 5))
                p.drawLine(QPointF(cx + 5, cy - 5), QPointF(cx + 5, cy + 2))
            else:
                p.drawRect(QRectF(cx - 5, cy - 5, 10, 10))
        else:
            p.drawLine(QPointF(cx - 5, cy - 5), QPointF(cx + 5, cy + 5))
            p.drawLine(QPointF(cx + 5, cy - 5), QPointF(cx - 5, cy + 5))


class TitleBar(QWidget):
    """Barra de título própria: só o texto "Claude", arrastável, duplo clique maximiza."""

    def __init__(self, win: QMainWindow):
        super().__init__()
        self.win = win
        self.setFixedHeight(BAR_H)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addStretch(1)
        self.b_min, self.b_max, self.b_close = WinBtn("min"), WinBtn("max"), WinBtn("close")
        self.b_min.clicked.connect(win.showMinimized)
        self.b_max.clicked.connect(self.toggle_max)
        self.b_close.clicked.connect(win.close)
        for b in (self.b_min, self.b_max, self.b_close):
            lay.addWidget(b)

    def refresh_btns(self):
        for b in (self.b_min, self.b_max, self.b_close):
            b._hov = False  # só volta a ser true num enterEvent real
            b.update()

    def leaveEvent(self, e):
        self.refresh_btns()
        super().leaveEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.refresh_btns()

    def toggle_max(self):
        w = self.win
        w.showNormal() if w.isMaximized() else w.showMaximized()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(ORANGE))
        draw_spark(p, 22, BAR_H / 2, 9, INK)
        f = QFont(self.font())
        f.setPixelSize(15)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(INK))
        p.drawText(QRectF(40, 0, self.width() - 200, BAR_H),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "Claude")

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.refresh_btns()
            h = self.win.windowHandle()
            if h:
                h.startSystemMove()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.toggle_max()


class Framed(QWidget):
    """Moldura laranja ao redor de tudo; as bordas/cantos redimensionam a janela."""

    def __init__(self, win: QMainWindow):
        super().__init__()
        self.win = win
        self.setMouseTracking(True)
        self.lay = QVBoxLayout(self)
        self.lay.setSpacing(0)
        self.set_maximized(False)

    def set_maximized(self, mx: bool):
        m = 0 if mx else FRAME
        if self.lay.contentsMargins().left() == m and self.lay.contentsMargins().top() == m:
            return
        self.lay.setContentsMargins(m, m, m, m)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(ORANGE))

    def _edges(self, pos):
        if self.win.isMaximized() or self.win.isFullScreen():
            return Qt.Edge(0)
        x, y, w, h = pos.x(), pos.y(), self.width(), self.height()
        ed = Qt.Edge(0)
        if x < GRIP and (x < FRAME or y < FRAME or y > h - GRIP):
            ed |= Qt.Edge.LeftEdge
        if x >= w - GRIP and (x >= w - FRAME or y < FRAME or y > h - GRIP):
            ed |= Qt.Edge.RightEdge
        if y < GRIP and (y < FRAME or x < FRAME or x > w - GRIP):
            ed |= Qt.Edge.TopEdge
        if y >= h - GRIP and (y >= h - FRAME or x < FRAME or x > w - GRIP):
            ed |= Qt.Edge.BottomEdge
        return ed

    def mouseMoveEvent(self, e):
        ed = self._edges(e.position().toPoint())
        L, R, T, B = (Qt.Edge.LeftEdge, Qt.Edge.RightEdge, Qt.Edge.TopEdge, Qt.Edge.BottomEdge)
        if (ed & L and ed & T) or (ed & R and ed & B):
            c = Qt.CursorShape.SizeFDiagCursor
        elif (ed & R and ed & T) or (ed & L and ed & B):
            c = Qt.CursorShape.SizeBDiagCursor
        elif ed & (L | R):
            c = Qt.CursorShape.SizeHorCursor
        elif ed & (T | B):
            c = Qt.CursorShape.SizeVerCursor
        else:
            c = Qt.CursorShape.ArrowCursor
        self.setCursor(c)

    def mousePressEvent(self, e):
        ed = self._edges(e.position().toPoint())
        h = self.win.windowHandle()
        if e.button() == Qt.MouseButton.LeftButton and ed and h:
            h.startSystemResize(ed)


class Toast(QWidget):
    """Balão laranja com seta apontando para o botão do perfil que respondeu."""
    ARROW = 8

    def __init__(self, parent: QWidget, on_click):
        super().__init__(parent)
        self.on_click = on_click
        self.text = ""
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)
        self.hide()

    def show_at(self, text: str, anchor: QPoint):
        """anchor = ponto (coords do pai) na borda direita do botão, centro vertical."""
        self.text = text
        f = QFont(self.font())
        f.setPixelSize(13)
        f.setBold(True)
        self.setFont(f)
        w = self.fontMetrics().horizontalAdvance(text) + 28 + self.ARROW
        h = 34
        par = self.parentWidget()
        y = min(max(4, anchor.y() - h // 2), max(4, par.height() - h - 4))
        self.setGeometry(anchor.x() + 2, y, w, h)
        self._ay = anchor.y() - y
        self.raise_()
        self.show()
        self.update()
        self.timer.start(7000)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        a = self.ARROW
        body = QRectF(a, 0, self.width() - a, self.height())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(ORANGE))
        p.drawRoundedRect(body, 9, 9)
        ay = min(max(self._ay, 12), self.height() - 12)
        tri = QPainterPath()
        tri.moveTo(0, ay)
        tri.lineTo(a + 1, ay - 7)
        tri.lineTo(a + 1, ay + 7)
        tri.closeSubpath()
        p.drawPath(tri)
        p.setPen(QColor(INK))
        p.setFont(self.font())
        p.drawText(body, Qt.AlignmentFlag.AlignCenter, self.text)

    def mousePressEvent(self, e):
        self.hide()
        self.on_click()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowTitle("Claude")
        self.resize(1280, 820)
        self.cfg = load_config()
        try:
            if self.cfg.get("geometry"):
                self.restoreGeometry(base64.b64decode(self.cfg["geometry"]))
        except Exception:
            pass
        set_theme(self.cfg.get("theme", "dark"))
        self.pauses = load_pauses()
        apply_theme(QApplication.instance())
        self.views: dict[str, ProfileView] = {}
        self.buttons: dict[str, QToolButton] = {}

        self.frame = Framed(self)
        self.titlebar = TitleBar(self)
        self.frame.lay.addWidget(self.titlebar)
        root = QWidget()
        root.setObjectName("content")
        self.frame.lay.addWidget(root, 1)
        self.content = root
        self._toast_pid = None
        self.toast = Toast(root, lambda: self._select(self._toast_pid)
                           if self._toast_pid in self.buttons else None)
        self.setCentralWidget(self.frame)
        row = QHBoxLayout(root)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(52)
        self.side_lay = QVBoxLayout(self.sidebar)
        self.side_lay.setContentsMargins(6, 8, 6, 8)
        self.side_lay.setSpacing(6)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)

        # lista de perfis rolável (roda do mouse); "+" e tema ficam fixos embaixo
        self.profile_holder = QWidget()
        self.profile_box = QVBoxLayout(self.profile_holder)
        self.profile_box.setContentsMargins(0, 0, 0, 0)
        self.profile_box.setSpacing(6)
        self.profile_box.addStretch(1)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(
            "QScrollArea{background:transparent;border:none;}"
            "QScrollArea > QWidget > QWidget{background:transparent;}")
        self.scroll.setWidget(self.profile_holder)
        self.side_lay.addWidget(self.scroll, 1)

        self.count_lbl = QLabel("0")
        self.count_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.side_lay.addWidget(self.count_lbl)

        add = IconButton("plus")
        add.setToolTip("Novo perfil (Ctrl+T)")
        add.setFixedSize(40, 40)
        add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn = add
        add.clicked.connect(self.add_profile)
        self.side_lay.addWidget(add)

        self.notes_btn = IconButton("notes")
        self.notes_btn.setCheckable(True)
        self.notes_btn.setToolTip("DeepSeek (Ctrl+J)")
        self.notes_btn.setFixedSize(40, 40)
        self.notes_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.notes_btn.clicked.connect(lambda: self.toggle_notes())
        self.side_lay.addWidget(self.notes_btn)
        try:
            if ICON_FILE.exists():
                pm = QPixmap(str(ICON_FILE))
                if not pm.isNull():
                    self.notes_btn.set_pix(pm)
        except Exception:
            pass

        self.theme_btn = IconButton("sun")
        self.theme_btn.setFixedSize(40, 40)
        self.theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_btn.clicked.connect(self.toggle_theme)
        self.side_lay.addWidget(self.theme_btn)

        self.stack = QStackedWidget()

        # painel DeepSeek global: fica fora do stack, então aparece em todos os perfis
        self.notes_panel = QFrame()
        self.notes_panel.setObjectName("notes")
        self.ds_lay = QVBoxLayout(self.notes_panel)
        self.ds_lay.setContentsMargins(0, 0, 0, 0)
        self.ds_view = None  # criado na primeira abertura (economiza RAM)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setOpaqueResize(False)  # arrastar só move uma linha; aplica ao soltar (sem engasgar o site)
        self._notes_anim = None
        self.splitter.addWidget(self.stack)
        self.splitter.addWidget(self.notes_panel)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.splitterMoved.connect(self._notes_moved)
        row.addWidget(self.sidebar)
        row.addWidget(self.splitter, 1)

        for p in self.cfg["profiles"]:
            self._make_button(p)
        self._select(self.cfg.get("last") or self.cfg["profiles"][0]["id"])
        self.tip = Tip()
        QApplication.instance().installEventFilter(self)
        self.apply_look()
        self._notes_w = max(320, int(self.cfg.get("notes_width", 440)))
        self.toggle_notes(bool(self.cfg.get("notes_open")), persist=False)
        self.pause_timer = QTimer(self)
        self.pause_timer.setInterval(30_000)
        self.pause_timer.timeout.connect(self._check_pauses)
        self.pause_timer.start()
        self._busy: dict[str, bool] = {}
        self._idle: dict[str, int] = {}
        self._notif_pid = None
        self.busy_timer = QTimer(self)
        self.busy_timer.setInterval(2000)
        self.busy_timer.timeout.connect(self._poll_busy)
        self.busy_timer.start()

        # atalhos
        for i in range(9):
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self,
                      activated=lambda i=i: self._select_index(i))
        QShortcut(QKeySequence("Ctrl+Tab"), self, activated=lambda: self._cycle(1))
        QShortcut(QKeySequence("Ctrl+Shift+Tab"), self, activated=lambda: self._cycle(-1))
        QShortcut(QKeySequence("Ctrl+T"), self, activated=self.add_profile)
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self._reload)
        QShortcut(QKeySequence("F5"), self, activated=self._reload)
        QShortcut(QKeySequence("Ctrl+Q"), self, activated=self.quit_app)
        QShortcut(QKeySequence("Ctrl+Shift+D"), self, activated=self.toggle_theme)
        QShortcut(QKeySequence("Ctrl+J"), self, activated=self.toggle_notes)
        for k in ("Ctrl+=", "Ctrl++"):
            QShortcut(QKeySequence(k), self, activated=lambda: self._zoom(+0.1))
        QShortcut(QKeySequence("Ctrl+-"), self, activated=lambda: self._zoom(-0.1))
        QShortcut(QKeySequence("Ctrl+0"), self, activated=lambda: self._zoom(0))

        # bandeja
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(make_icon("C", COLORS[0], 64, badge=False), self)
            menu = QMenu()
            menu.addAction("Mostrar", self.show_normal)
            menu.addAction("Alternar tema", self.toggle_theme)
            menu.addAction("Testar notificação",
                           lambda: self._notify("Claude", "Notificação de teste", self.cfg.get("last")))
            act = menu.addAction("Notificações")
            act.setCheckable(True)
            act.setChecked(bool(self.cfg.get("notify", True)))
            act.toggled.connect(self._set_notify)
            menu.addAction("Sair", self.quit_app)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(
                lambda r: self.show_normal()
                if r == QSystemTrayIcon.ActivationReason.Trigger else None)
            self.tray.messageClicked.connect(self._notif_click)
            self.tray.show()
        self._quitting = False

    def eventFilter(self, obj, ev):
        if isinstance(obj, QToolButton) and obj.window() is self:
            t = ev.type()
            if t == QEvent.Type.ToolTip:
                if obj.toolTip():
                    self.tip.show_for(obj, obj.toolTip())
                return True
            if t in (QEvent.Type.Leave, QEvent.Type.MouseButtonPress, QEvent.Type.Hide):
                self.tip.hide()
        return super().eventFilter(obj, ev)

    # -- zoom (por perfil, lembrado)
    def _zoom(self, delta):
        v = self.stack.currentWidget()
        if not v:
            return
        z = 1.0 if delta == 0 else min(3.0, max(0.5, round(v.zoomFactor() + delta, 2)))
        v.setZoomFactor(z)
        v.pdata["zoom"] = z
        save_config(self.cfg)

    # -- painel DeepSeek
    def _ds_icon(self, icon: QIcon):
        """Usa o favicon do próprio DeepSeek no botão e guarda em cache para as próximas aberturas."""
        pm = icon.pixmap(QSize(64, 64))
        if pm.isNull():
            return
        self.notes_btn.set_pix(pm)
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            pm.save(str(ICON_FILE), "PNG")
        except Exception:
            pass

    def toggle_notes(self, show=None, persist=True):
        if not isinstance(show, bool):
            show = not self.notes_panel.isVisible()
        if show and self.ds_view is None:
            self.ds_view = ProfileView({"id": "_deepseek", "name": "DeepSeek", "color": COLORS[0]},
                                       home=DEEPSEEK_URL, page_cls=DeepSeekPage, label="DeepSeek")
            self.ds_lay.addWidget(self.ds_view)
            self.ds_view.web.iconChanged.connect(self._ds_icon)
        self.notes_btn.setChecked(show)
        total = max(self.splitter.width(), self._notes_w + 400)
        if persist and self.isVisible():  # abre/fecha deslizando
            start = self.notes_panel.width() if self.notes_panel.isVisible() else 0
            end = self._notes_w if show else 0
            if self._notes_anim is not None:
                self._notes_anim.stop()
            if show:
                self.notes_panel.setVisible(True)
            anim = QVariantAnimation(self)
            anim.setStartValue(start)
            anim.setEndValue(end)
            anim.setDuration(180)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.valueChanged.connect(
                lambda v: self.splitter.setSizes([total - int(v), int(v)]))
            if not show:
                anim.finished.connect(lambda: self.notes_panel.setVisible(False))
            self._notes_anim = anim
            anim.start()
        else:
            self.notes_panel.setVisible(show)
            if show:
                self.splitter.setSizes([total - self._notes_w, self._notes_w])
        if show:
            self.ds_view.setFocus()
        if persist:
            self.cfg["notes_open"] = show
            save_config(self.cfg)

    def _notes_moved(self, *_):
        if self.notes_panel.isVisible():
            self._notes_w = max(320, self.notes_panel.width())
            self.cfg["notes_width"] = self._notes_w

    # -- perfis
    def _make_button(self, p: dict):
        b = ProfileButton()
        b.setCheckable(True)
        b.setIconSize(QSize(32, 32))
        b.setFixedSize(40, 40)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        b.customContextMenuRequested.connect(lambda pos, pid=p["id"], btn=b: self._menu(pid, btn, pos))
        b.clicked.connect(lambda _c, pid=p["id"]: self._select(pid))
        self.group.addButton(b)
        self.profile_box.insertWidget(self.profile_box.count() - 1, b)
        self.buttons[p["id"]] = b
        self._update_btn(p["id"])

    def _pdata(self, pid):
        return next(p for p in self.cfg["profiles"] if p["id"] == pid)

    def _select(self, pid: str):
        if pid not in self.views:  # carrega só quando abrir (economiza RAM)
            v = ProfileView(self._pdata(pid))
            self.views[pid] = v
            self.stack.addWidget(v)
        self.stack.setCurrentWidget(self.views[pid])
        self.buttons[pid].setChecked(True)
        self.buttons[pid].done = False
        self.buttons[pid].update()
        if getattr(self, "_toast_pid", None) == pid:
            self.toast.hide()
        self.scroll.ensureWidgetVisible(self.buttons[pid])
        self.cfg["last"] = pid
        save_config(self.cfg)
        ids = self._ids()
        self._update_count()

    def _ids(self):
        return [p["id"] for p in self.cfg["profiles"]]

    def _select_index(self, i):
        ids = self._ids()
        if i < len(ids):
            self._select(ids[i])

    def _cycle(self, step):
        ids = self._ids()
        cur = ids.index(self.cfg["last"])
        self._select(ids[(cur + step) % len(ids)])

    def _reload(self):
        w = self.stack.currentWidget()
        if w:
            w.reload()

    def apply_look(self):
        self.sidebar.setStyleSheet(css(
            "#sidebar{background:@side;border-right:1px solid @border;}"
            "#sidebar QToolButton{border:none;border-radius:10px;background:transparent;}"
            "#sidebar QToolButton:hover{background:@hover;}"
            "#sidebar QToolButton:checked{background:@checked;}"))
        self.add_btn.setStyleSheet(css(
            "QToolButton{border:none;border-radius:10px;background:transparent;}"
            "QToolButton:hover{background:@hover;}"))
        self.splitter.setStyleSheet(css("QSplitter::handle{background:@side;}"))
        self.notes_btn.setStyleSheet(css(
            "QToolButton{color:@plus;font-size:16px;border:none;border-radius:10px;"
            "background:transparent;}"
            "QToolButton:hover{background:@hover;color:@accent;}"
            "QToolButton:checked{background:@checked;color:@accent;}"))
        self.notes_panel.setStyleSheet(css(
            "#notes{background:@side;border-left:1px solid @border;}"))
        if self.ds_view:
            self.ds_view.web.setBackgroundColor(QColor(T["bg"]))
        self.theme_btn.set_kind("sun" if THEME == "dark" else "moon")
        self.theme_btn.setToolTip("Tema claro (Ctrl+Shift+D)" if THEME == "dark"
                                  else "Tema escuro (Ctrl+Shift+D)")
        self.theme_btn.setStyleSheet(css(
            "QToolButton{color:@plus;font-size:14px;border:none;border-radius:10px;"
            "background:transparent;}"
            "QToolButton:hover{background:@hover;color:@accent;}"))
        self.count_lbl.setStyleSheet(css("color:@plus;font-size:11px;font-weight:600;"))
        for pid in self.buttons:
            self._update_btn(pid)
        for v in self.views.values():
            v.web.setBackgroundColor(QColor(T["bg"]))

    def toggle_theme(self):
        new = "light" if THEME == "dark" else "dark"
        set_theme(new)
        self.cfg["theme"] = new
        save_config(self.cfg)
        apply_theme(QApplication.instance())
        self.apply_look()
        for v in list(self.views.values()) + ([self.ds_view] if self.ds_view else []):
            v.set_scheme(new == "dark")

    def add_profile(self):
        name, ok = QInputDialog.getText(self, "Novo perfil", "Nome do perfil:")
        if not ok or not name.strip():
            return
        color = COLORS[len(self.cfg["profiles"]) % len(COLORS)]
        p = new_profile(name.strip(), color)
        self.cfg["profiles"].append(p)
        self._make_button(p)
        self._select(p["id"])

    def _menu(self, pid, btn, pos):
        m = QMenu(self)
        m.addAction("Recarregar", lambda: self.views.get(pid) and self.views[pid].reload())
        if pid in self.pauses:
            m.addAction("Retomar agora", lambda: self._resume(pid))
        else:
            m.addAction(f"Pausar ({PAUSE_HOURS}h)", lambda: self._pause(pid))
        m.addAction("Renomear", lambda: self._rename(pid))
        m.addAction("Mudar cor", lambda: self._recolor(pid))
        m.addAction("Limpar cookies e cache", lambda: self._clear(pid))
        m.addSeparator()
        m.addAction("Remover perfil", lambda: self._remove(pid))
        m.exec(btn.mapToGlobal(pos))

    def _update_btn(self, pid):
        p = self._pdata(pid)
        info = self.pauses.get(pid)
        b = self.buttons[pid]
        b.setIcon(make_icon(p["name"], p["color"], paused=bool(info)))
        tip = p["name"]
        if info:
            volta = datetime.fromisoformat(info["volta_em"])
            tip += f" — em pausa, volta {volta.strftime('%d/%m %H:%M')}"
        b.setToolTip(tip)
        self._update_count()

    def _update_count(self):
        total = len(self.cfg["profiles"])
        paused = len(self.pauses)
        self.count_lbl.setText(str(total))
        self.count_lbl.setToolTip(f"{total} perfis · {paused} em pausa · {total - paused} ativos")

    def _pause(self, pid):
        now = _now()
        self.pauses[pid] = {
            "perfil": self._pdata(pid)["name"],
            "pausado_em": now.isoformat(timespec="seconds"),
            "volta_em": (now + timedelta(hours=PAUSE_HOURS)).isoformat(timespec="seconds"),
        }
        save_pauses(self.pauses)
        self._update_btn(pid)

    def _resume(self, pid):
        if self.pauses.pop(pid, None) is not None:
            save_pauses(self.pauses)
        self._update_btn(pid)

    def _check_pauses(self):
        now = _now()
        for pid, info in list(self.pauses.items()):
            try:
                expired = datetime.fromisoformat(info["volta_em"]) <= now
            except Exception:
                expired = True
            if expired:
                self.pauses.pop(pid, None)
                save_pauses(self.pauses)
                if pid in self.buttons:
                    self._update_btn(pid)
                    self._notify("Claude", f"{self._pdata(pid)['name']} voltou a ficar ativa", pid)

    # -- notificações
    def _set_notify(self, on: bool):
        self.cfg["notify"] = bool(on)
        save_config(self.cfg)

    def _notify(self, title: str, body: str, pid=None):
        """Notificação do GNOME (central de notificações) via notify-send/gdbus; bandeja só como último recurso."""
        if not self.cfg.get("notify", True):
            return
        self._notif_pid = pid
        if shutil.which("notify-send"):
            self._notify_send(title, body, actions=True)
        elif shutil.which("gdbus"):
            subprocess.Popen(
                ["gdbus", "call", "--session", "--dest", "org.freedesktop.Notifications",
                 "--object-path", "/org/freedesktop/Notifications",
                 "--method", "org.freedesktop.Notifications.Notify",
                 "Claude", "0", self._icon_path(), title, body, "[]", "{}", "8000"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=clean_env())
        elif self.tray:
            self.tray.showMessage(title, body, self.tray.icon(), 8000)

    def _icon_path(self) -> str:
        """PNG do ícone do app (faísca laranja) para as notificações."""
        f = CONFIG_DIR / "notify_icon.png"
        if not f.exists():
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            make_icon("C", COLORS[0], 128, badge=False).pixmap(128, 128).save(str(f))
        return str(f)

    def _notify_send(self, title, body, actions):
        args = ["-a", "Claude", "-t", "8000", "-i", self._icon_path()]
        if actions:  # clicar na notificação abre a conta (libnotify >= 0.7.10)
            args += ["-A", "default=Abrir", "-w"]
        proc = QProcess(self)
        env = QProcessEnvironment()
        for k, v in clean_env().items():
            env.insert(k, v)
        proc.setProcessEnvironment(env)
        proc.start("notify-send", args + [title, body])
        self._procs = [p for p in getattr(self, "_procs", []) if p.state() != QProcess.ProcessState.NotRunning]
        self._procs.append(proc)

        def fin(code, _st, proc=proc):
            out = bytes(proc.readAllStandardOutput()).decode(errors="ignore")
            if code == 0 and "default" in out:
                self._notif_click()
            elif code != 0 and actions:  # notify-send antigo sem -A: reenvia simples
                self._notify_send(title, body, actions=False)
        proc.finished.connect(fin)

    def _notif_click(self):
        self.show_normal()
        if self._notif_pid in self.buttons:
            self._select(self._notif_pid)

    def _poll_busy(self):
        for pid, v in list(self.views.items()):
            if v._loading:
                continue
            v.web.runJavaScript(BUSY_JS, lambda r, pid=pid: self._on_busy(pid, bool(r)))

    def _on_busy(self, pid: str, busy: bool):
        if busy:
            self._busy[pid] = True
            self._idle[pid] = 0
            return
        if not self._busy.get(pid):
            return
        self._idle[pid] = self._idle.get(pid, 0) + 1
        if self._idle[pid] < 2:  # ~4s parado: evita falso positivo entre ferramentas/etapas
            return
        self._busy[pid] = False
        name = self._pdata(pid)["name"]
        active = self.isVisible() and self.isActiveWindow()
        if active and self.stack.currentWidget() is self.views.get(pid):
            return  # já está olhando
        self.buttons[pid].done = True
        self.buttons[pid].update()
        if active:  # dentro do app: balão com seta no perfil
            self._toast_pid = pid
            b = self.buttons[pid]
            self.scroll.ensureWidgetVisible(b)
            self.toast.show_at(f"{name} respondeu", b.mapTo(self.content, QPoint(b.width(), b.height() // 2)))
        else:  # fora do app: notificação do sistema, com assunto e início da resposta
            def got(r, pid=pid, name=name):
                t = b = ""
                try:
                    d = json.loads(r or "{}")
                    t = (d.get("t") or "").strip()
                    b = (d.get("b") or "").strip()
                except Exception:
                    pass
                for suf in (" - Claude", " | Claude", " — Claude"):
                    if t.endswith(suf):
                        t = t[: -len(suf)]
                if t.lower() in ("claude", ""):
                    t = ""
                title = f"{name} · {t}" if t else f"{name} respondeu"
                if len(b) >= 160:
                    b = b[:157].rstrip() + "…"
                self._notify(title, b or "Claude respondeu", pid)
            self.views[pid].web.runJavaScript(SNIP_JS, got)

    def _refresh_btn(self, pid):
        p = self._pdata(pid)
        self._update_btn(pid)
        save_config(self.cfg)

    def _rename(self, pid):
        p = self._pdata(pid)
        name, ok = QInputDialog.getText(self, "Renomear", "Novo nome:", text=p["name"])
        if ok and name.strip():
            p["name"] = name.strip()
            self._refresh_btn(pid)

    def _recolor(self, pid):
        p = self._pdata(pid)
        c = QColorDialog.getColor(QColor(p["color"]), self, "Cor do perfil")
        if c.isValid():
            p["color"] = c.name()
            self._refresh_btn(pid)

    def _clear(self, pid):
        if QMessageBox.question(self, "Limpar dados",
                                "Isso desloga a conta deste perfil. Continuar?") \
                == QMessageBox.StandardButton.Yes:
            if pid not in self.views:
                self._select(pid)
            self.views[pid].clear_data()

    def _remove(self, pid):
        if len(self.cfg["profiles"]) == 1:
            QMessageBox.information(self, "Remover", "Mantenha pelo menos um perfil.")
            return
        if QMessageBox.question(self, "Remover perfil",
                                "Apagar este perfil e todos os dados dele?") \
                != QMessageBox.StandardButton.Yes:
            return
        idx = self._ids().index(pid)
        v = self.views.pop(pid, None)
        if v:
            self.stack.removeWidget(v)
            v.setPage(None)
            v.web.deleteLater()
            v.deleteLater()
        b = self.buttons.pop(pid)
        if self.pauses.pop(pid, None) is not None:
            save_pauses(self.pauses)
        self.group.removeButton(b)
        b.deleteLater()
        self.cfg["profiles"] = [p for p in self.cfg["profiles"] if p["id"] != pid]
        self.cfg["pending_delete"].append(pid)  # arquivos apagados no próximo início
        save_config(self.cfg)
        ids = self._ids()
        self._select(ids[max(0, idx - 1)])

    # -- janela
    def _sync_frame(self):
        """Moldura laranja só fora do estado maximizado/tela cheia (o estado pode vir restaurado antes da moldura existir)."""
        if not hasattr(self, "frame"):
            return
        self.frame.set_maximized(self.isMaximized() or self.isFullScreen())
        self.titlebar.refresh_btns()

    def changeEvent(self, e):
        if e.type() == QEvent.Type.WindowStateChange:
            self._sync_frame()
            QTimer.singleShot(150, self._sync_frame)
        super().changeEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._sync_frame()

    def _save_geometry(self):
        self.cfg["geometry"] = base64.b64encode(bytes(self.saveGeometry())).decode()
        self.cfg["maximized"] = bool(self.isMaximized() or self.isFullScreen())

    def show_window(self, force=False):
        """Janela expandida (maximizada), nunca tela cheia. Na partida (force) sempre maximiza; ao reabrir da bandeja respeita o último estado."""
        if self.isFullScreen():
            self.showNormal()
        if force or self.cfg.get("maximized", True):
            self.showMaximized()
        else:
            self.showNormal()
        self._sync_frame()
        QTimer.singleShot(200, self._sync_frame)
        self.raise_()
        self.activateWindow()

    def show_normal(self):
        self.show_window()

    def quit_app(self):
        self._quitting = True
        self._save_geometry()
        save_config(self.cfg)
        QApplication.quit()

    def closeEvent(self, e):
        if self.tray and not self._quitting:
            e.ignore()
            self._save_geometry()
            save_config(self.cfg)
            self.hide()
        else:
            self._save_geometry()
            save_config(self.cfg)
            super().closeEvent(e)


def main():
    # evita o tema gtk3 do Qt, que aborta em GNOME novo (schema xsettings sem a chave antialiasing)
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORMTHEME", "generic")
        if os.environ.get("APPIMAGE") or os.environ.get("APPDIR"):  # AppImage: chrome-sandbox sem setuid
            os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox")
    elif sys.platform == "win32":  # ícone/agrupamento corretos na barra de tarefas
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("claude.containers.app")
        except Exception:
            pass
    # flags do Chromium (opcional): descomente se tiver problema de GPU
    # import os; os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")
    app = QApplication(sys.argv)
    signal.signal(signal.SIGINT, signal.SIG_DFL)  # Ctrl+C no terminal fecha o app de vez
    app.setApplicationName(APP)
    app.setDesktopFileName(APP)  # casa a janela com o .desktop/ícone no GNOME
    app.setQuitOnLastWindowClosed(False)

    # instância única: duas instâncias disputam o LOCK do IndexedDB dos perfis (o app fica na bandeja ao fechar)
    sname = f"{APP}-{os.getuid() if hasattr(os, 'getuid') else os.environ.get('USERNAME', 'u')}"
    sock = QLocalSocket()
    sock.connectToServer(sname)
    if sock.waitForConnected(500):  # já existe uma rodando: só pede para ela aparecer
        sock.write(b"show")
        sock.waitForBytesWritten(500)
        sock.disconnectFromServer()
        print("Claude Containers já está aberto — trazendo a janela para frente.")
        sys.exit(0)
    QLocalServer.removeServer(sname)  # limpa socket órfão de uma execução que travou
    server = QLocalServer()
    server.listen(sname)

    apply_theme(app)
    app.setWindowIcon(make_icon("C", COLORS[0], 128, badge=False))
    w = MainWindow()

    def _wake():
        c = server.nextPendingConnection()
        if c:
            c.close()
        w.show_window()
    server.newConnection.connect(_wake)
    w.show_window(force=True)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
