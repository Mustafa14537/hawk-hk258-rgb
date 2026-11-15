"""
Hawk HK258 RGB kontrol programi (resmi olmayan, tersine muhendislikle cikarildi)
================================================================================
Klavye: Hawk Gaming HK258 (Shinetek Technology)
  - USB kablosu : VID 1A2C / PID B007 ("Gaming keyboard")
  - 2.4G alici  : VID 1A2C / PID 8FFF ("2.4 Wireless Device") - komutlari klavyeye iletir
Kanal : her ikisinde de USB arayuzu MI_00, HID Usage Page 0xFF02, 64 baytlik raporlar (report ID yok)

Cozulen protokol
----------------
Her paket 64 bayt:  aa 55 cc 33 | KOMUT | veri (59 bayt)
  0x0E               -> pil sorgusu. Cevap: aa 55 cc 33 0e <pil %> <baglanti> ...
                        (<baglanti>: kabloda 03, 2.4G'de 01). Klavye bu paketi ~7 sn'de
                        bir kendiliginden de gonderir; 2.4G alicisi sorguya cevap vermez,
                        orada pil bilgisi bu periyodik paketten okunur.
  0x00, 0xB5, 0xF0, 0xF1, 0xF4 (bu sirayla, ayni veriyle)
                     -> klavyeyi SABIT RENK moduna alir. Renk verinin basindan
                        itibaren R G B R G B ... diye tekrarlanir.
Bu mod GECICIDIR: bilgisayar ~3 sn boyunca yeniden gondermezse klavye kendi efektine
(gokkusagi) doner. Bu yuzden program rengi her saniye yeniden gonderir (keepalive).
Renk klavyenin kalici bellegine yazilmaz, surekli gondermek klavyeye zarar vermez.

Kullanim
--------
  python hk258_rgb.py                 -> basit pencereli program (asil panel: hk258_panel.py)
  python hk258_rgb.py kirmizi         -> hazir renk (kirmizi, yesil, mavi, beyaz, mor,
                                         turuncu, sari, pembe, turkuaz, kapali)
  python hk258_rgb.py ff8800          -> onaltilik RGB rengi (#ff8800 de olur)
  python hk258_rgb.py 255 136 0       -> R G B (0-255)
  python hk258_rgb.py pil             -> pil yuzdesini ve baglanti turunu yazdirir
  python hk258_rgb.py arkaplan        -> son secilen rengi surekli uygular
Renk, program acik kaldigi surece korunur; program kapaninca ~3 sn icinde gokkusagina doner.
Son secilen renk %APPDATA%\\hk258_rgb.json dosyasinda saklanir.
Gereken paket:  python -m pip install hidapi
"""
import json
import os
import sys
import threading
import time

try:
    import hid
except ImportError:  # pragma: no cover
    hid = None

VID = 0x1A2C
PID_WIRED, PID_DONGLE = 0xB007, 0x8FFF
PIDS = (PID_WIRED, PID_DONGLE)
VENDOR_PAGE = 0xFF02
HEADER = bytes.fromhex("aa55cc33")
COLOR_SEQUENCE = (0x00, 0xB5, 0xF0, 0xF1, 0xF4)
CMD_BATTERY = 0x0E
SEND_GAP = 0.03    # komutlar arasi bekleme (sn); 2.4G'de de calistigi dogrulandi
KEEPALIVE = 1.0    # rengi yeniden gonderme araligi (klavye ~3 sn sonra geri donuyor)
HEARTBEAT_FRESH = 16.0  # bu kadar sn icinde pil paketi geldiyse klavye "bagli" sayilir
CONFIG = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "hk258_rgb.json")

PRESETS = {
    "kirmizi": (255, 0, 0),
    "yesil": (0, 255, 0),
    "mavi": (0, 0, 255),
    "beyaz": (255, 255, 255),
    "mor": (255, 0, 255),
    "turuncu": (255, 100, 0),
    "sari": (255, 220, 0),
    "pembe": (255, 60, 150),
    "turkuaz": (0, 255, 200),
    "kapali": (0, 0, 0),
}
ALIASES = {"kırmızı": "kirmizi", "yeşil": "yesil", "sarı": "sari", "kapalı": "kapali"}
NOT_FOUND = "Hawk HK258 bulunamadi. USB kablosunu ya da 2.4G alicisini takin."


class KeyboardNotFound(RuntimeError):
    pass


# ----------------------------------------------------------------- cihaz erisimi
def vendor_paths():
    """[(path, pid), ...] - once kablolu baglanti, sonra 2.4G alicisi."""
    if hid is None:
        return []
    out = []
    for pid in PIDS:
        for d in hid.enumerate(VID, pid):
            if d["usage_page"] == VENDOR_PAGE:
                out.append((d["path"], pid))
    return out


class _Devices:
    """Takili olan tum HK258 kanallarini (kablo ve/veya 2.4G alici) tek cihaz gibi kullanir."""

    def __init__(self, paths):
        self.devs, self.pids = [], []
        try:
            for path, pid in paths:
                d = hid.device()
                d.open_path(path)
                d.set_nonblocking(True)
                self.devs.append(d)
                self.pids.append(pid)
        except Exception:
            self.close()
            raise
        if not self.devs:
            raise KeyboardNotFound(NOT_FOUND)
        self.key = tuple(sorted(p for p, _ in paths))

    @property
    def kind(self):
        return "USB" if PID_WIRED in self.pids else "2.4G"

    def write(self, data):
        for d in self.devs:
            n = d.write(data)
            if n is None or n < 0:
                raise OSError("yazma basarisiz (cihaz cikarilmis olabilir)")
        return len(data)

    def read(self, size=65):
        for d in self.devs:
            r = d.read(size)
            if r:
                return r
        return []

    def close(self):
        for d in self.devs:
            try:
                d.close()
            except Exception:
                pass
        self.devs = []


def _open():
    if hid is None:
        raise RuntimeError("hidapi kurulu degil. Kurmak icin: python -m pip install hidapi")
    paths = vendor_paths()
    if not paths:
        raise KeyboardNotFound(NOT_FOUND)
    return _Devices(paths)


def _frame(cmd, data=b""):
    return (HEADER + bytes([cmd]) + data + bytes(64))[:64]


def _drain(dev):
    frames = []
    while True:
        r = dev.read(65)
        if not r:
            return frames
        frames.append(bytes(r))


def _check_rgb(rgb):
    r, g, b = (int(v) for v in rgb)
    for v in (r, g, b):
        if not 0 <= v <= 255:
            raise ValueError("R, G, B degerleri 0-255 arasinda olmali")
    return r, g, b


def _send_color(dev, rgb):
    """Renk dizisini gonderir; bu sirada gelen paketleri dondurur."""
    data = bytes(_check_rgb(rgb)) * 20
    frames = []
    for cmd in COLOR_SEQUENCE:
        dev.write(b"\x00" + _frame(cmd, data))  # basa 0x00 = report ID (yok)
        time.sleep(SEND_GAP)
        frames += _drain(dev)
    return frames


def _battery_frame(f):
    return len(f) >= 7 and f[:5] == HEADER + bytes([CMD_BATTERY])


def _query_battery(dev, timeout=1.0):
    """(pil %, baglanti baiti) ya da None. 2.4G'de periyodik paketi bekler (timeout'a kadar)."""
    _drain(dev)
    dev.write(b"\x00" + _frame(CMD_BATTERY))
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = dev.read(65)
        if r and _battery_frame(bytes(r)):
            return r[5], r[6]
        time.sleep(0.005)
    return None


def set_color_once(r, g, b):
    """Rengi BIR KEZ gonderir (klavye ~3 sn sonra geri doner). Test icin."""
    dev = _open()
    try:
        _send_color(dev, (r, g, b))
    finally:
        dev.close()


def battery(timeout=9.0):
    """(pil %, 'USB'/'2.4G') ya da (None, tur)."""
    dev = _open()
    try:
        res = _query_battery(dev, timeout)
        return (res[0] if res else None), dev.kind
    finally:
        dev.close()


# ----------------------------------------------------------------- son renk
def save_last(rgb):
    try:
        with open(CONFIG, "w", encoding="utf-8") as f:
            json.dump({"rgb": list(rgb) if rgb is not None else None}, f)
    except OSError:
        pass


def load_last():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            rgb = json.load(f)["rgb"]
        return None if rgb is None else tuple(int(v) for v in rgb[:3])
    except (OSError, ValueError, KeyError, TypeError):
        return None


# ----------------------------------------------------------------- keepalive
class ColorKeeper:
    """Secilen rengi her KEEPALIVE saniyede bir yeniden gonderir (efektlerde surekli).
    set(None) -> gondermeyi birakir, klavye ~3 sn icinde kendi efektine doner.
    Kablo / alici takilip cikarilinca kendiliginden yeniden baglanir.
    Klavyenin periyodik pil paketlerini de izler (battery_level, heartbeat_age)."""

    def __init__(self, interval=KEEPALIVE):
        self.interval = interval
        self.connected = False     # en az bir kanal (kablo/alici) acik
        self.kind = None           # "USB" / "2.4G"
        self.last_sent = None      # klavyeye en son gonderilen renk
        self.battery_level = None
        self.started = time.time()
        self._last_heartbeat = 0.0
        self._rgb = None
        self._source = None
        self._dev = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    # ---- disaridan
    def set(self, rgb):
        """Sabit renk (None = klavyenin kendi efekti)."""
        self._source = None
        self._rgb = None if rgb is None else _check_rgb(rgb)
        self._wake.set()

    def set_source(self, fn):
        """Efekt: fn(zaman) -> (r, g, b); klavyenin kaldirabildigi kadar sik cagrilir."""
        self._rgb = None
        self._source = fn
        self._wake.set()

    @property
    def color(self):
        return self._rgb

    @property
    def heartbeat_age(self):
        return time.time() - self._last_heartbeat if self._last_heartbeat else None

    def battery(self):
        """Kablolu baglantida sorgular; 2.4G'de periyodik paketten gelen son degeri verir."""
        with self._lock:
            try:
                self._ensure_open()
                res = _query_battery(self._dev, timeout=0.6)
                if res:
                    self._note_battery(res[0])
            except Exception:
                self._drop()
        return self.battery_level

    def close(self):
        self._stop.set()
        self._wake.set()
        self._thread.join(2)
        with self._lock:
            self._drop()

    # ---- ic isler
    def _note_battery(self, level):
        self.battery_level = int(level)
        self._last_heartbeat = time.time()

    def _scan(self, frames):
        for f in frames:
            if _battery_frame(f):
                self._note_battery(f[5])

    def _ensure_open(self):
        paths = vendor_paths()
        key = tuple(sorted(p for p, _ in paths))
        if self._dev is not None and self._dev.key != key:   # kablo/alici takildi ya da cikti
            self._drop()
        if self._dev is None:
            self._dev = _open()
        self.kind = self._dev.kind

    def _drop(self):
        if self._dev is not None:
            self._dev.close()
        self._dev = None
        self.connected = False

    def _run(self):
        last_check = 0.0
        while not self._stop.is_set():
            fn = self._source
            try:
                rgb = fn(time.time()) if fn is not None else self._rgb
            except Exception:
                rgb = None
            with self._lock:
                try:
                    now = time.time()
                    if self._dev is None or now - last_check > 2.0:
                        last_check = now
                        self._ensure_open()
                    if rgb is not None:
                        self._scan(_send_color(self._dev, rgb))
                        self.last_sent = tuple(int(v) for v in rgb)
                    else:
                        self._scan(_drain(self._dev))
                        self.last_sent = None
                    self.connected = True
                except Exception:
                    self._drop()
                    self.last_sent = None if rgb is None else self.last_sent
            if fn is not None and self.connected:
                time.sleep(0.005)               # efekt: hemen bir sonraki kareyi gonder
            else:
                self._wake.wait(self.interval)
                self._wake.clear()


def parse_color(args):
    """Komut satiri argumanlarini (r, g, b) demetine cevirir."""
    if len(args) == 3:
        return _check_rgb(args)
    if len(args) == 1:
        a = args[0].strip().lower()
        a = ALIASES.get(a, a)
        if a in PRESETS:
            return PRESETS[a]
        h = a.lstrip("#")
        if len(h) == 6:
            return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    raise ValueError("Renk anlasilamadi. Ornek: kirmizi | ff8800 | 255 136 0")


# ----------------------------------------------------------------- basit pencere
def run_gui():
    import tkinter as tk
    from tkinter import colorchooser

    keeper = ColorKeeper()
    root = tk.Tk()
    root.title("Hawk HK258 RGB")
    root.resizable(False, False)
    status = tk.StringVar()
    bat = tk.StringVar(value="Pil: ...")

    def show():
        rgb = keeper.color
        txt = "Gokkusagi (klavyenin kendi efekti)" if rgb is None else "Renk: #%02x%02x%02x" % rgb
        if not keeper.connected:
            txt += "  - klavye bekleniyor..."
        elif keeper.kind:
            txt += f"  ({keeper.kind})"
        status.set(txt)
        b = keeper.battery_level
        bat.set(f"Pil: %{b}" if b is not None else "Pil: ?")

    def apply(rgb):
        keeper.set(rgb)
        save_last(rgb)
        show()

    def pick():
        res = colorchooser.askcolor(title="Klavye rengini secin")
        if res and res[0]:
            apply(tuple(int(v) for v in res[0]))

    def tick():
        show()
        root.after(1000, tick)

    def refresh_battery():
        threading.Thread(target=keeper.battery, daemon=True).start()
        root.after(20000, refresh_battery)

    def on_close():
        keeper.close()
        root.destroy()

    tk.Label(root, text="Hawk HK258 RGB", font=("Segoe UI", 14, "bold")).grid(
        row=0, column=0, columnspan=5, pady=(10, 4))
    for i, n in enumerate(PRESETS):
        rgb = PRESETS[n]
        fg = "white" if sum(rgb) < 400 else "black"
        tk.Button(root, text=n.capitalize(), width=9, bg="#%02x%02x%02x" % rgb, fg=fg,
                  command=lambda rgb=rgb: apply(rgb)).grid(
            row=1 + i // 5, column=i % 5, padx=4, pady=4)
    tk.Button(root, text="Ozel renk sec...", command=pick).grid(
        row=3, column=0, columnspan=3, sticky="ew", padx=4, pady=(8, 4))
    tk.Button(root, text="Gokkusagi (varsayilan)", command=lambda: apply(None)).grid(
        row=3, column=3, columnspan=2, sticky="ew", padx=4, pady=(8, 4))
    tk.Label(root, textvariable=status).grid(row=4, column=0, columnspan=4, sticky="w", padx=6)
    tk.Label(root, textvariable=bat).grid(row=4, column=4, sticky="e", padx=6)
    tk.Label(root, text="Renk, bu pencere acik kaldikca korunur (simge durumuna kucultebilirsiniz).\n"
                        "Pencereyi kapatinca klavye ~3 sn icinde gokkusagina doner.",
             fg="gray", justify="center").grid(row=5, column=0, columnspan=5, pady=(4, 10))

    root.protocol("WM_DELETE_WINDOW", on_close)
    keeper.set(load_last())
    tick()
    refresh_battery()
    root.mainloop()


def _hold(keeper, msg):
    print(msg)
    print("Renk bu pencere acik kaldikca korunur. Cikmak icin Ctrl+C (klavye ~3 sn icinde gokkusagina doner).")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        keeper.close()


def main(argv):
    if not argv:
        run_gui()
        return 0
    try:
        cmd = argv[0].lower()
        if cmd == "pil":
            level, kind = battery()
            print(f"Baglanti: {kind}")
            print(f"Pil: %{level}" if level is not None else "Pil bilgisi alinamadi (klavye kapali olabilir)")
            return 0
        if cmd == "arkaplan":
            rgb = load_last()
            if rgb is None:
                print("Kayitli renk yok. Once bir renk secin (ornek: python hk258_rgb.py kirmizi).")
                return 1
            keeper = ColorKeeper()
            keeper.set(rgb)
            _hold(keeper, "Arka plan modu: #%02x%02x%02x surekli uygulaniyor." % rgb)
            return 0
        rgb = parse_color(argv)
        _open().close()  # klavye bagli mi? (degilse anlasilir bir hata verir)
        save_last(rgb)
        keeper = ColorKeeper()
        keeper.set(rgb)
        _hold(keeper, "Renk ayarlandi: #%02x%02x%02x" % rgb)
        return 0
    except Exception as e:
        print("Hata:", e)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
