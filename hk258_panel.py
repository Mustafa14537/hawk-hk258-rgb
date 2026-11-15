"""
Hawk HK258 RGB Paneli
=====================
hk258_rgb.py surucusunun ustune modern bir kontrol paneli (pywebview + panel.html).
Calistirmak:  pythonw hk258_panel.py            (ya da derlenmis "HK258 RGB.exe")
              pythonw hk258_panel.py --gizli    (pencere acmadan, sistem tepsisinde baslar)
Gereken paketler:  python -m pip install hidapi pywebview pystray pillow

Modlar: sabit renk, nefes, renk dongusu, klavyenin kendi efekti (gokkusagi).
USB kablosuyla da 2.4G alicisiyla da calisir (hangisi takiliysa).
Klavye tek renk destekledigi icin nefes ve dongu efektleri bu programda hesaplanip
klavyeye surekli gonderilir. Pencere kapatilinca program sistem tepsisinde calismaya
devam eder (renk korunur); tamamen cikmak icin tepsi menusunden "Cikis".
"""
import colorsys
import ctypes
import json
import math
import os
import sys
import threading
import time
from ctypes import wintypes

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hk258_rgb as kb  # noqa: E402

APP_NAME = "HK258 RGB"
HERE = os.path.dirname(os.path.abspath(__file__))
RES = getattr(sys, "_MEIPASS", HERE)          # PyInstaller ile derlenince dosyalar burada
EFFECTS = ("static", "breathe", "cycle", "native")
DEFAULTS = {"color": "#00a2ff", "brightness": 100, "effect": "static", "speed": 5}
PRESETS = [(n, "#%02x%02x%02x" % rgb) for n, rgb in kb.PRESETS.items() if n != "kapali"]
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def resource(name):
    return os.path.join(RES, name)


def hex_to_rgb(h):
    h = str(h).strip().lstrip("#")
    if len(h) != 6:
        raise ValueError("gecersiz renk")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#%02x%02x%02x" % tuple(rgb)


# ----------------------------------------------------------------- Windows acilisi
def autostart_command():
    """Acilista calistirilacak komut (gizli, tepside baslar)."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --gizli'
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.isfile(pyw):
        pyw = sys.executable
    return f'"{pyw}" "{os.path.abspath(__file__)}" --gizli'


def get_autostart(key_path=RUN_KEY):
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


def set_autostart(enabled, key_path=RUN_KEY):
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as k:
        if enabled:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass


# ----------------------------------------------------------------- tek kopya
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.CreateMutexW.restype = wintypes.HANDLE
_k32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
_k32.CreateEventW.restype = wintypes.HANDLE
_k32.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
_k32.OpenEventW.restype = wintypes.HANDLE
_k32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
_k32.OpenMutexW.restype = wintypes.HANDLE
_k32.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
_k32.SetEvent.argtypes = [wintypes.HANDLE]
_k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_k32.WaitForSingleObject.restype = wintypes.DWORD
_k32.CloseHandle.argtypes = [wintypes.HANDLE]


def _signal(event_name):
    ev = _k32.OpenEventW(0x0002, False, event_name)       # EVENT_MODIFY_STATE
    if ev:
        _k32.SetEvent(ev)
        _k32.CloseHandle(ev)
        return True
    return False


def is_running(name="HK258RGB"):
    """Uygulama calisiyor mu? (kendi kopyasini baslatmadan, sadece bakar)"""
    h = _k32.OpenMutexW(0x00100000, False, f"Local\\{name}_Instance")   # SYNCHRONIZE
    if h:
        _k32.CloseHandle(h)
        return True
    return False


def request_quit(name="HK258RGB"):
    """Calisan uygulamaya 'kapan' der (kurulum/kaldirma oncesi)."""
    return _signal(f"Local\\{name}_Quit")


class SingleInstance:
    """Ikinci kopya acilirsa birinciye 'pencereni goster' der ve kapanir.
    Kurulum sihirbazi da 'kapan' sinyali gonderebilir."""

    def __init__(self, name="HK258RGB"):
        self.mutex_name = f"Local\\{name}_Instance"
        self.event_name = f"Local\\{name}_Show"
        self.quit_name = f"Local\\{name}_Quit"
        self.mutex = _k32.CreateMutexW(None, False, self.mutex_name)
        self.first = ctypes.get_last_error() != 183          # ERROR_ALREADY_EXISTS
        self.event = _k32.CreateEventW(None, False, False, self.event_name) if self.first else None
        self.quit_event = _k32.CreateEventW(None, False, False, self.quit_name) if self.first else None

    def signal_first(self):
        return _signal(self.event_name)

    def listen(self, on_show, stop, on_quit=None):
        def watch(handle, callback):
            while not stop.is_set():
                if _k32.WaitForSingleObject(handle, 500) == 0:   # WAIT_OBJECT_0
                    callback()
        threading.Thread(target=watch, args=(self.event, on_show), daemon=True).start()
        if on_quit is not None:
            threading.Thread(target=watch, args=(self.quit_event, on_quit), daemon=True).start()


# ----------------------------------------------------------------- panel durumu
class Controller:
    """Panelin durumu + klavyeye ne gonderilecegi."""

    def __init__(self, state_file=kb.CONFIG, keeper=None, autostart_key=RUN_KEY):
        self.state_file = state_file
        self.autostart_key = autostart_key
        self.state = dict(DEFAULTS)
        self._load()
        self.keeper = keeper or kb.ColorKeeper()
        self._stop = threading.Event()
        self.apply()
        threading.Thread(target=self._battery_loop, daemon=True).start()

    # ---- kalici durum
    def _load(self):
        try:
            with open(self.state_file, encoding="utf-8") as f:
                data = json.load(f)
            panel = data.get("panel") or {}
            for k in DEFAULTS:
                if k in panel:
                    self.state[k] = panel[k]
            if "panel" not in data and data.get("rgb"):  # eski surumden kalan renk
                self.state["color"] = rgb_to_hex(data["rgb"])
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        self._sanitize()

    def _sanitize(self):
        s = self.state
        try:
            hex_to_rgb(s["color"])
        except (ValueError, TypeError):
            s["color"] = DEFAULTS["color"]
        s["brightness"] = max(0, min(100, int(s.get("brightness", 100))))
        s["speed"] = max(1, min(10, int(s.get("speed", 5))))
        if s.get("effect") not in EFFECTS:
            s["effect"] = "static"

    def _save(self):
        static = self.static_rgb() if self.state["effect"] == "static" else None
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                # "rgb" alani komut satiri "arkaplan" modu icin
                json.dump({"rgb": list(static) if static else None, "panel": self.state}, f)
        except OSError:
            pass

    # ---- renk hesaplari
    def _scaled(self, rgb, factor):
        f = max(0.0, min(1.0, factor))
        return tuple(int(round(v * f)) for v in rgb)

    def static_rgb(self):
        return self._scaled(hex_to_rgb(self.state["color"]), self.state["brightness"] / 100)

    def color_at(self, t):
        s = self.state
        speed = s["speed"]
        bright = s["brightness"] / 100
        if s["effect"] == "breathe":
            period = 7.0 - 0.6 * speed                       # 6.4 sn (yavas) .. 1 sn (hizli)
            level = 0.06 + 0.94 * (0.5 - 0.5 * math.cos(2 * math.pi * t / period))
            return self._scaled(hex_to_rgb(s["color"]), bright * level)
        if s["effect"] == "cycle":
            period = 32.0 / speed                            # 32 sn .. 3.2 sn
            r, g, b = colorsys.hsv_to_rgb((t / period) % 1.0, 1.0, bright)
            return (int(r * 255), int(g * 255), int(b * 255))
        return self.static_rgb()

    def apply(self):
        e = self.state["effect"]
        if e == "native":
            self.keeper.set(None)
        elif e == "static":
            self.keeper.set(self.static_rgb())
        else:
            self.keeper.set_source(self.color_at)
        self._save()

    def update(self, **changes):
        self.state.update(changes)
        self._sanitize()
        self.apply()

    def status(self):
        """'ok' (klavye bagli), 'wait' (alici takili ama klavyeden sinyal yok), 'off' (hicbir sey takili degil),
        'connecting' (program yeni acildi)."""
        k = self.keeper
        if not k.connected:
            return "connecting" if time.time() - k.started < 2.5 else "off"
        age = k.heartbeat_age
        if age is not None and age < kb.HEARTBEAT_FRESH:
            return "ok"
        if time.time() - k.started < 10:        # ilk pil paketi henuz gelmemis olabilir
            return "ok"
        return "wait"

    def snapshot(self):
        live = self.keeper.last_sent
        st = self.status()
        return {
            **self.state,
            "live": rgb_to_hex(live) if live else None,
            "status": st,
            "connected": st == "ok",
            "kind": self.keeper.kind,
            "battery": self.keeper.battery_level,
            "presets": PRESETS,
            "autostart": get_autostart(self.autostart_key),
        }

    def _battery_loop(self):
        while not self._stop.is_set():
            self.keeper.battery()     # kabloda sorgular; 2.4G'de periyodik paketler zaten izleniyor
            self._stop.wait(20)

    def close(self):
        self._stop.set()
        self.keeper.close()


class Api:
    """JavaScript'ten cagrilan metotlar (window.pywebview.api.*)."""

    def __init__(self, ctrl):
        self._ctrl = ctrl
        self._app = None

    def get_state(self):
        return self._ctrl.snapshot()

    def set_color(self, hex_color):
        hex_to_rgb(hex_color)
        effect = self._ctrl.state["effect"]
        self._ctrl.update(color=hex_color, effect="static" if effect == "native" else effect)
        return self._ctrl.snapshot()

    def set_brightness(self, value):
        self._ctrl.update(brightness=int(value))
        return self._ctrl.snapshot()

    def set_speed(self, value):
        self._ctrl.update(speed=int(value))
        return self._ctrl.snapshot()

    def set_effect(self, name):
        if name not in EFFECTS:
            raise ValueError("bilinmeyen efekt")
        self._ctrl.update(effect=name)
        return self._ctrl.snapshot()

    def set_autostart(self, enabled):
        set_autostart(bool(enabled), self._ctrl.autostart_key)
        return self._ctrl.snapshot()

    def minimize(self):
        self._app.window.minimize()

    def close(self):
        self._app.hide_to_tray()


# ----------------------------------------------------------------- uygulama
class App:
    def __init__(self, start_hidden):
        import pystray
        import webview
        from PIL import Image

        self.webview = webview
        self.ctrl = Controller()
        self.api = Api(self.ctrl)
        self.api._app = self
        self.quitting = False
        self.notified = False
        self.stop = threading.Event()
        with open(resource("panel.html"), encoding="utf-8") as f:
            html = f.read()
        self.window = webview.create_window(
            "Hawk HK258 RGB", html=html, js_api=self.api, width=1040, height=660,
            resizable=False, frameless=True, easy_drag=False, background_color="#0a0c10",
            hidden=start_hidden)
        self.window.events.closing += self._on_closing
        menu = pystray.Menu(
            pystray.MenuItem("Paneli aç", lambda icon, item: self.show(), default=True),
            pystray.MenuItem("Klavyenin kendi efekti", lambda icon, item: self.ctrl.update(effect="native")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Çıkış", lambda icon, item: self.quit()))
        self.tray = pystray.Icon("HK258RGB", Image.open(resource("app.png")), "Hawk HK258 RGB", menu)

    def show(self):
        self.window.show()
        self.window.restore()

    def hide_to_tray(self):
        self.window.hide()
        if not self.notified:
            self.notified = True
            try:
                self.tray.notify("Panel sistem tepsisinde çalışmaya devam ediyor; renk korunuyor.",
                                 "Hawk HK258 RGB")
            except Exception:
                pass

    def quit(self):
        self.quitting = True
        self.stop.set()
        try:
            self.tray.stop()
        except Exception:
            pass
        self.window.destroy()

    def _on_closing(self):
        if self.quitting:
            return True
        self.hide_to_tray()         # Alt+F4 vb. -> kapatma, tepsiye gizle
        return False

    def run(self, instance):
        threading.Thread(target=self.tray.run, daemon=True).start()
        instance.listen(self.show, self.stop, on_quit=self.quit)
        try:
            self.webview.start(icon=resource("app.ico"))
        finally:
            self.stop.set()
            try:
                self.tray.stop()
            except Exception:
                pass
            self.ctrl.close()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    instance = SingleInstance()
    if not instance.first:              # zaten calisiyor: onun penceresini one getir
        instance.signal_first()
        return 0
    try:                                # gorev cubugunda Python yerine kendi logomuz gorunsun
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Hawk.HK258RGB")
    except Exception:
        pass
    App(start_hidden="--gizli" in argv).run(instance)
    return 0


if __name__ == "__main__":
    sys.exit(main())
