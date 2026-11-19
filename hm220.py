"""
Hawk HM220 mouse - pil durumu, DPI kademeleri ve raporlama hizi
===============================================================
Mouse bilgisayara iki yoldan baglanir ve ikisi ayri USB cihazi olarak gorunur:

    2.4G alicisi : VID 1D57 / PID FA60 ("HM220 2.4G")
    kablo        : VID 1D57 / PID 2027 ("HM220")

USB arayuzu 2'de iki HID koleksiyonu var:
  * usage page 0x000A (input)  : olaylar  -> 03 5c <tur> <p1> <p2>
        tur 40 = pil       (p1: 1 pilde, 2 dolu, 3 sarj oluyor; p2: seviye %)
        tur 10 = DPI tusu  (p1: yeni aktif kademe 1-5)
        tur 50 = komut onayi (p1: 0 kabul / 1 red; p2: report numarasi)
  * usage page 0x000B (feature): ayar komutlari
        okuma : A0 <report> <uzunluk> 00 01 00 00 00 gonder, ~250 ms sonra A0 oku (a0 01 = izin), sonra raporu oku
        0x04  : DPI kademeleri  (52 bayt kabloda / 56 bayt kablosuzda, 16 bit toplam checksum)
        0x06  : raporlama hizi  06 09 01 v (255-v) 00 00 00 00,  v = 1000 / Hz

Kablosuzda mouse 5 sn hareketsiz kalinca uyur ve komutlari kacirir: komutlar onay gelene kadar tekrarlanir,
okuma izni gelene kadar tekrar istenir. Alici, mouse uyurken saatlerce sessiz kalabilir; bu yuzden son bilinen
pil degeri diske yazilir ve sessizlik "mouse kapali" sayilmaz.

Protokol ve PAW3311 DPI tablosu su acik kaynak projelerden alinmistir (ikisi de MIT lisansli):
  https://github.com/WinTone01/hawk-hub-unofficial          (HM220 protokol belgesi)
  https://github.com/HarukaYamamoto0/attack-shark-x11-driver (ayni Beken firmware ailesi, DPI tablosu)
Bu dosyadaki okuma akisi, DPI cercevesi ve checksum bu bilgisayardaki HM220'de dogrulandi (2026-11-20).
"""
import ctypes
import json
import os
import threading
import time
from ctypes import wintypes

try:
    import hid
except ImportError:  # pragma: no cover
    hid = None

VID = 0x1D57
PIDS = {0x2027: "kablo", 0xFA60: "2.4G"}
EVENT_PAGE = 0x000A
CMD_PAGE = 0x000B
EVENT_REPORT = 0x03

REPORT_DPI = 0x04
REPORT_POLLING = 0x06
READ_LEN = {REPORT_DPI: 0x38, REPORT_POLLING: 0x09}
SEND_LEN = {REPORT_DPI: (52, 56), REPORT_POLLING: (9, 9)}    # (kablo, 2.4G), report numarasi dahil
DPI_FRAME = 52                    # DPI cercevesinin anlamli kismi (checksum dahil)
DPI_MIN, DPI_MAX = 100, 12000
POLLING_RATES = (125, 250, 500, 1000)

FRESH = 8.0            # son paket bu kadar saniye icindeyse bilgi "canli"
SPIKE = 20             # kisa surede bu kadar puandan buyuk sicrama -> once bekletilir
SPIKE_WINDOW = 120.0
PENDING_CONFIRM = 15.0  # bekletilen deger bu kadar sure itiraz gormezse kabul edilir
AWAKE = 20.0           # mouse bu kadar saniye icinde hareket ettirildiyse "bagli" sayilir
RESCAN = 3.0
SAVE_EVERY = 300.0
STATE = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "hm220_durum.json")

SLEEP_HINT = "Mouse cevap vermedi. Uyuyor olabilir: mouse'u biraz oynatıp tekrar dene."

# PAW3311 DPI tablosu (attack-shark-x11-driver, MIT). Ilk 200 deger kesin artan.
DPI_3311 = bytes([
    0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0e, 0x0f, 0x10, 0x11, 0x12, 0x13, 0x15, 0x16,
    0x17, 0x18, 0x19, 0x1b, 0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x29, 0x2a, 0x2b, 0x2c,
    0x2d, 0x2f, 0x30, 0x31, 0x32, 0x33, 0x34, 0x36, 0x37, 0x38, 0x39, 0x3a, 0x3b, 0x3d, 0x3e, 0x3f, 0x40, 0x41, 0x43,
    0x44, 0x45, 0x46, 0x47, 0x48, 0x4a, 0x4b, 0x4c, 0x4d, 0x4e, 0x4f, 0x51, 0x52, 0x53, 0x54, 0x55, 0x57, 0x58, 0x59,
    0x5a, 0x5b, 0x5c, 0x5e, 0x5f, 0x60, 0x61, 0x62, 0x63, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6b, 0x6c, 0x6d, 0x6e, 0x6f,
    0x70, 0x72, 0x73, 0x74, 0x75, 0x76, 0x77, 0x79, 0x7a, 0x7b, 0x7c, 0x7d, 0x7f, 0x80, 0x81, 0x82, 0x83, 0x84, 0x86,
    0x87, 0x88, 0x89, 0x8a, 0x8b, 0x8d, 0x8e, 0x8f, 0x90, 0x91, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x9a, 0x9b, 0x9c,
    0x9d, 0x9e, 0x9f, 0xa1, 0xa2, 0xa3, 0xa4, 0xa5, 0xa7, 0xa8, 0xa9, 0xaa, 0xab, 0xac, 0xae, 0xaf, 0xb0, 0xb1, 0xb2,
    0xb3, 0xb5, 0xb6, 0xb7, 0xb8, 0xb9, 0xbb, 0xbc, 0xbd, 0xbe, 0xbf, 0xc0, 0xc2, 0xc3, 0xc4, 0xc5, 0xc6, 0xc7, 0xc9,
    0xca, 0xcb, 0xcc, 0xcd, 0xcf, 0xd0, 0xd1, 0xd2, 0xd3, 0xd4, 0xd6, 0xd7, 0xd8, 0xd9, 0xda, 0xdb, 0xdd, 0xde, 0xdf,
    0xe0, 0xe1, 0xe3, 0xe4, 0xe5, 0xe6, 0xe7, 0xe8, 0xea, 0xeb, 0x76, 0x77, 0x79, 0x7a, 0x7b, 0x7c, 0x7d, 0x7f, 0x80,
    0x81, 0x82, 0x83, 0x84, 0x86, 0x87, 0x88, 0x89, 0x8a, 0x8b, 0x8d,
])


class MouseError(Exception):
    """Kullaniciya gosterilebilecek bir hata (mesaj Turkce)."""


# ----------------------------------------------------------------- olaylar
def parse_event(data):
    """Olay paketini cozer:
    ('battery', {'level', 'charging', 'full'}) | ('dpi_stage', n) | ('ack', report, ok) | None"""
    b = bytes(data)
    if len(b) < 5 or b[0] != EVENT_REPORT:
        return None
    kind, p1, p2 = b[2], b[3], b[4]
    if kind == 0x40 and p1 in (1, 2, 3) and p2 <= 100:
        level = 100 if p1 == 2 else (None if p1 == 3 else p2)     # sarj olurken seviye guvenilmez
        return ("battery", {"level": level, "charging": p1 == 3, "full": p1 == 2})
    if kind == 0x10 and 1 <= p1 <= 8:
        return ("dpi_stage", p1)
    if kind == 0x50:
        return ("ack", p2, p1 == 0)
    return None


# ----------------------------------------------------------------- DPI kodlamasi
def dpi_encode(dpi):
    """DPI -> (x baytı, y baytı, x2 bayrağı). 5000 üstü 100'lük, 10000 üstü 200'lük adımlar."""
    dpi = max(DPI_MIN, min(DPI_MAX, int(dpi)))
    double = dpi > 10000
    target = int(round(dpi / 2)) if double else dpi
    if target > 5000 and target % 100 == 0:
        return DPI_3311[min(target // 100 - 1, 219)], 1, double
    return DPI_3311[min(max(target - 50, 0) // 50, 219)], 0, double


def dpi_decode(x, y, double):
    try:
        i = DPI_3311[:200].index(x)
    except ValueError:
        i = 0
    base = (i + 1) * (100 if y == 1 else 50)
    return base * 2 if double else base


def dpi_snap(dpi):
    """Mouse'un gercekten saklayabilecegi en yakin degere yuvarlar."""
    return dpi_decode(*dpi_encode(dpi))


def _dpi_checksum(f):
    s = sum(f[3:50]) & 0xFFFF
    return s >> 8, s & 0xFF


def parse_dpi_frame(frame):
    """Report 0x04 cercevesi -> {'stages': [...], 'active': n}. Bozuksa MouseError."""
    f = bytes(frame)
    if len(f) < DPI_FRAME or f[0] != REPORT_DPI or tuple(f[50:52]) != _dpi_checksum(f):
        raise MouseError("Mouse'tan gelen DPI bilgisi okunamadı (bozuk çerçeve).")
    mask = f[5]
    count = 0
    while count < 8 and mask >> count & 1:
        count += 1
    count = count or 1
    stages = [dpi_decode(f[8 + i], f[16 + i], bool(f[6] >> i & 1)) for i in range(count)]
    active = f[24] if 1 <= f[24] <= count else 1
    return {"stages": stages, "active": active}


def build_dpi_frame(frame, stages=None, active=None):
    """Okunan DPI cercevesinde yalnizca kademe DPI'larini / aktif kademeyi degistirir, checksum'i yeniler."""
    cur = parse_dpi_frame(frame)                      # once dogrula
    f = bytearray(bytes(frame)[:DPI_FRAME])
    if stages is not None:
        if len(stages) != len(cur["stages"]):
            raise MouseError("Kademe sayısı mouse'takiyle aynı olmalı.")
        for i, dpi in enumerate(stages):
            x, y, double = dpi_encode(dpi)
            f[8 + i], f[16 + i] = x, y
            f[6] = (f[6] | 1 << i) if double else (f[6] & ~(1 << i) & 0xFF)
    if active is not None:
        active = int(active)
        if not 1 <= active <= len(cur["stages"]):
            raise MouseError("Geçersiz DPI kademesi.")
        f[24] = active
    f[50], f[51] = _dpi_checksum(f)
    return bytes(f)


def parse_polling_frame(frame):
    f = bytes(frame)
    if len(f) < 5 or f[0] != REPORT_POLLING or f[3] == 0 or (f[3] + f[4]) != 0xFF:
        raise MouseError("Mouse'tan gelen raporlama hızı okunamadı.")
    hz = round(1000 / f[3])
    return min(POLLING_RATES, key=lambda r: abs(r - hz))


def polling_frame(hz):
    if hz not in POLLING_RATES:
        raise MouseError("Raporlama hızı 125, 250, 500 ya da 1000 Hz olmalı.")
    v = round(1000 / hz)
    return bytes([REPORT_POLLING, 0x09, 0x01, v, 255 - v, 0, 0, 0, 0])


# ----------------------------------------------------------------- komut kanali
class _Link:
    """Bir ayar oturumu: komut koleksiyonu (0x000B) + onaylarin geldigi olay koleksiyonu (0x000A)."""

    def __init__(self, mode, cmd, evt):
        self.mode, self.cmd, self.evt = mode, cmd, evt
        self.wireless = mode == "2.4G"

    @classmethod
    def open(cls):
        if hid is None:
            raise MouseError("hidapi paketi kurulu değil.")
        paths = {}
        for pid, mode in PIDS.items():
            for d in hid.enumerate(VID, pid):
                if d["interface_number"] == 2 and d["usage_page"] in (EVENT_PAGE, CMD_PAGE):
                    paths.setdefault(mode, {})[d["usage_page"]] = d["path"]
        for mode in ("kablo", "2.4G"):                    # kablo takiliysa onu kullan
            p = paths.get(mode, {})
            if CMD_PAGE not in p:
                continue
            try:
                cmd = hid.device()
                cmd.open_path(p[CMD_PAGE])
            except Exception:
                raise MouseError("Mouse'un ayar kanalı açılamadı.") from None
            evt = None
            if EVENT_PAGE in p:
                try:
                    evt = hid.device()
                    evt.open_path(p[EVENT_PAGE])
                except Exception:
                    evt = None
            return cls(mode, cmd, evt)
        raise MouseError("Mouse bulunamadı: 2.4G alıcısı ya da kablo takılı değil.")

    def close(self):
        for h in (self.cmd, self.evt):
            if h is not None:
                try:
                    h.close()
                except Exception:
                    pass

    def read(self, report):
        """Ayar okur. Mouse uyuyorsa izin gelene kadar (kablosuzda ~8 sn) tekrar ister."""
        ln = READ_LEN[report]
        deadline = time.time() + (8.0 if self.wireless else 2.0)
        while time.time() < deadline:
            try:
                self.cmd.send_feature_report([0xA0, report, ln, 0x00, 0x01, 0x00, 0x00, 0x00])
                time.sleep(0.25)
                perm = self.cmd.get_feature_report(0xA0, 8)
                if len(perm) > 1 and perm[1] == 0x01:
                    return bytes(self.cmd.get_feature_report(report, ln))
            except (OSError, ValueError):
                time.sleep(0.1)
        raise MouseError(SLEEP_HINT)

    def _wait_ack(self, report, timeout):
        end = time.time() + timeout
        while True:
            left = end - time.time()
            if left <= 0:
                return None
            try:
                r = self.evt.read(64, max(1, int(left * 1000)))
            except (OSError, ValueError):
                return None
            if not r:
                return None
            ev = parse_event(r)
            if ev and ev[0] == "ack" and ev[1] == report:
                return ev[2]

    def send(self, report, frame):
        """Ayar yazar ve mouse'un onayini bekler (kablosuzda uyuyan mouse icin 10 deneme)."""
        n = SEND_LEN[report][1 if self.wireless else 0]
        data = list(bytes(frame)[:n].ljust(n, b"\0"))
        for _ in range(10 if self.wireless else 3):
            try:
                res = self.cmd.send_feature_report(data)
            except (OSError, ValueError):
                res = -1
            if res is None or res < 0:
                time.sleep(0.05)
                continue
            if self.evt is None:
                return                                      # onay kanali yok: onaysiz devam
            ok = self._wait_ack(report, 0.7)
            if ok is True:
                return
            if ok is False:
                raise MouseError("Mouse bu ayarı reddetti.")
        raise MouseError(SLEEP_HINT)


# ----------------------------------------------------------------- hareket zamani (Raw Input)
class _RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wintypes.USHORT), ("usUsage", wintypes.USHORT),
                ("dwFlags", wintypes.DWORD), ("hwndTarget", wintypes.HWND)]


class _RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", wintypes.DWORD), ("dwSize", wintypes.DWORD),
                ("hDevice", wintypes.HANDLE), ("wParam", wintypes.WPARAM)]


class ActivityWatch:
    """2.4G alicisi durum paketini yalnizca ara ara gonderdigi icin "mouse kullaniliyor mu?" sorusunu
    Windows Raw Input ile cevaplar: HM220'nin (VID 1D57) EN SON NE ZAMAN hareket ettirildigini tutar.
    Hareket verisi okunmaz ya da saklanmaz. Oyunlarda yuk olmasin diye dinleme kisa araliklarla acilir:
    mouse'tan tek bir olay gorulunce kapanir, 3 sn sonra yeniden acilir."""

    WM_INPUT, RID_HEADER, RIDI_DEVICENAME = 0x00FF, 0x10000005, 0x20000007
    RIDEV_INPUTSINK, RIDEV_REMOVE, PM_REMOVE, QS_ALLINPUT = 0x100, 0x1, 0x1, 0x04FF

    def __init__(self, stop, vid=VID):
        self.last = 0.0
        self._stop = stop
        self._tag = "VID_%04X" % vid
        self._names = {}
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            self._loop()
        except Exception:
            pass                                  # izlenemezse yalnizca durum paketlerine guvenilir

    def _user32(self):
        u = ctypes.WinDLL("user32", use_last_error=True)
        u.CreateWindowExW.restype = wintypes.HWND
        u.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                      ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                      wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
        u.RegisterRawInputDevices.argtypes = [ctypes.POINTER(_RAWINPUTDEVICE), wintypes.UINT, wintypes.UINT]
        u.GetRawInputData.restype = wintypes.UINT
        u.GetRawInputData.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPVOID,
                                      ctypes.POINTER(wintypes.UINT), wintypes.UINT]
        u.GetRawInputDeviceInfoW.restype = wintypes.UINT
        u.GetRawInputDeviceInfoW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPVOID,
                                             ctypes.POINTER(wintypes.UINT)]
        u.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT,
                                   wintypes.UINT]
        u.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        u.MsgWaitForMultipleObjects.restype = wintypes.DWORD
        u.MsgWaitForMultipleObjects.argtypes = [wintypes.DWORD, wintypes.LPVOID, wintypes.BOOL, wintypes.DWORD,
                                                wintypes.DWORD]
        u.DestroyWindow.argtypes = [wintypes.HWND]
        return u

    def _is_mouse(self, u, hraw):
        hdr = _RAWINPUTHEADER()
        size = wintypes.UINT(ctypes.sizeof(hdr))
        if u.GetRawInputData(hraw, self.RID_HEADER, ctypes.byref(hdr), ctypes.byref(size),
                             ctypes.sizeof(_RAWINPUTHEADER)) in (0, 0xFFFFFFFF):
            return False
        key = hdr.hDevice or 0
        if key not in self._names:
            n = wintypes.UINT(0)
            u.GetRawInputDeviceInfoW(hdr.hDevice, self.RIDI_DEVICENAME, None, ctypes.byref(n))
            buf = ctypes.create_unicode_buffer(n.value + 1)
            u.GetRawInputDeviceInfoW(hdr.hDevice, self.RIDI_DEVICENAME, buf, ctypes.byref(n))
            self._names[key] = buf.value.upper()
        return self._tag in self._names[key]

    def _loop(self):
        u = self._user32()
        hwnd = u.CreateWindowExW(0, "STATIC", "hm220-activity", 0, 0, 0, 0, 0,
                                 wintypes.HWND(-3), None, None, None)          # HWND_MESSAGE: gorunmez
        if not hwnd:
            return
        on = _RAWINPUTDEVICE(0x01, 0x02, self.RIDEV_INPUTSINK, hwnd)          # fare (Generic Desktop / Mouse)
        off = _RAWINPUTDEVICE(0x01, 0x02, self.RIDEV_REMOVE, None)
        msg = wintypes.MSG()
        try:
            while not self._stop.is_set():
                if not u.RegisterRawInputDevices(ctypes.byref(on), 1, ctypes.sizeof(on)):
                    return
                seen, end = False, time.time() + 2.0
                while not seen and not self._stop.is_set() and time.time() < end:
                    u.MsgWaitForMultipleObjects(0, None, False, max(1, int((end - time.time()) * 1000)),
                                                self.QS_ALLINPUT)
                    while u.PeekMessageW(ctypes.byref(msg), None, 0, 0, self.PM_REMOVE):
                        if msg.message == self.WM_INPUT and not seen and self._is_mouse(u, msg.lParam):
                            seen = True
                        u.DispatchMessageW(ctypes.byref(msg))
                u.RegisterRawInputDevices(ctypes.byref(off), 1, ctypes.sizeof(off))
                while u.PeekMessageW(ctypes.byref(msg), None, 0, 0, self.PM_REMOVE):
                    u.DispatchMessageW(ctypes.byref(msg))
                if seen:
                    self.last = time.time()
                    self._stop.wait(3.0)
        finally:
            u.DestroyWindow(hwnd)


# ----------------------------------------------------------------- izleyici
class MouseWatcher:
    """Pil / baglanti durumunu arka planda dinler; DPI ve raporlama hizini okur / yazar."""

    def __init__(self, state_file=STATE, start=True):
        self.state_file = state_file
        self.present = set()        # su an takili yollar: {"kablo", "2.4G"}
        self.mode = None            # son paketin geldigi yol
        self.last_seen = 0.0        # son olay paketinin zamani
        self.status = self._load()  # son kabul edilen pil bilgisi
        self.settings = None        # {"stages", "active", "polling", "mode", "rev", "time"}
        self._pending = None
        self._saved_at = 0.0
        self._rev = 0
        self._lock = threading.RLock()
        self._cmd_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.activity = None
        if start:
            self._thread.start()
            self.activity = ActivityWatch(self._stop)

    # ---- son bilinen pil degeri (uygulama kapanip acilinca da gorunsun)
    def _load(self):
        if not self.state_file:
            return None
        try:
            with open(self.state_file, encoding="utf-8") as f:
                s = json.load(f)
            if isinstance(s.get("battery"), int) and isinstance(s.get("time"), (int, float)):
                return {"battery": s["battery"], "charging": bool(s.get("charging")), "full": bool(s.get("full")),
                        "mode": s.get("mode"), "time": float(s["time"])}
        except (OSError, ValueError, AttributeError):
            pass
        return None

    def _save(self):
        if not self.state_file:
            return
        try:
            tmp = self.state_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.status, f)
            os.replace(tmp, self.state_file)
        except OSError:
            pass

    def _accept(self, new, now):
        prev = self.status
        changed = prev is None or any(prev.get(k) != new[k] for k in ("battery", "charging", "full", "mode"))
        self.status = new
        if changed or now - self._saved_at >= SAVE_EVERY:
            self._saved_at = now
            self._save()

    def _promote_pending(self, now):
        p = self._pending
        if p and self.last_seen == p["time"] and now - p["time"] >= PENDING_CONFIRM:
            self._pending = None
            self._accept(p, p["time"])

    # ---- olay isleme (donanimsiz test edilebilir)
    def feed(self, mode, data, now=None):
        """Bir olay paketini isler. Taninmayan paketse False doner."""
        now = time.time() if now is None else now
        ev = parse_event(data)
        if ev is None:
            return False
        with self._lock:
            self._promote_pending(now)
            self.last_seen, self.mode = now, mode
            if ev[0] == "dpi_stage":                          # mouse'un DPI tusuna basildi
                if self.settings and ev[1] <= len(self.settings["stages"]):
                    self._rev += 1
                    self.settings = {**self.settings, "active": ev[1], "rev": self._rev}
                return True
            if ev[0] != "battery":
                return True
            b, prev = ev[1], self.status
            level = b["level"]
            if level is None:                                 # sarj olurken: son bilinen seviyeyi koru
                level = prev["battery"] if prev else None
            elif (not b["full"] and prev and prev.get("battery") is not None
                  and now - prev["time"] < SPIKE_WINDOW and abs(level - prev["battery"]) > SPIKE):
                # kablo takilip cikarilirken gecici %100 gibi sicramalar: ikinci paket dogrulayana kadar beklet
                p = self._pending
                if not (p and abs(p["battery"] - level) <= 3):
                    self._pending = {"battery": level, "charging": False, "full": False, "mode": mode, "time": now}
                    return True
            self._pending = None
            if level is None:
                return True
            self._accept({"battery": level, "charging": b["charging"], "full": b["full"],
                          "mode": mode, "time": now}, now)
        return True

    # ---- cihaz takibi
    @staticmethod
    def _close(h):
        try:
            h.close()
        except Exception:
            pass

    def _scan(self, devs):
        found = {}
        for pid, mode in PIDS.items():
            for d in hid.enumerate(VID, pid):
                if d["interface_number"] == 2 and d["usage_page"] == EVENT_PAGE:
                    found[d["path"]] = mode
        for path in list(devs):
            if path not in found:
                self._close(devs.pop(path)[1])
        for path, mode in found.items():
            if path not in devs:
                try:
                    h = hid.device()
                    h.open_path(path)
                    h.set_nonblocking(True)
                    devs[path] = (mode, h)
                except Exception:
                    pass
        with self._lock:
            self.present = set(found.values())

    def _run(self):
        if hid is None:
            return
        devs, next_scan = {}, 0.0
        while not self._stop.is_set():
            if time.time() >= next_scan:
                try:
                    self._scan(devs)
                except Exception:
                    pass
                next_scan = time.time() + RESCAN
            got = False
            for path, (mode, h) in list(devs.items()):
                try:
                    r = h.read(64)
                except Exception:
                    self._close(h)
                    devs.pop(path, None)
                    continue
                if r:
                    got = True
                    self.feed(mode, r)
            if not got:
                self._stop.wait(0.1)
        for _, h in devs.values():
            self._close(h)

    # ---- ayarlar
    def _store_settings(self, dpi_frame, polling_frame_, mode):
        st = {**parse_dpi_frame(dpi_frame), "polling": parse_polling_frame(polling_frame_), "mode": mode}
        with self._lock:
            self._rev += 1
            self.settings = {**st, "rev": self._rev, "time": time.time()}
            return dict(self.settings)

    def read_settings(self):
        """Mouse'taki DPI kademelerini ve raporlama hizini okur."""
        with self._cmd_lock:
            link = _Link.open()
            try:
                dpi = link.read(REPORT_DPI)
                poll = link.read(REPORT_POLLING)
            finally:
                link.close()
        return self._store_settings(dpi, poll, link.mode)

    def apply_settings(self, stages=None, active=None, polling=None):
        """Degisen ayarlari mouse'a yazar (once guncel hali okunur, sadece istenen alanlar degisir),
        sonra tekrar okuyup dogrular. Ayarlar mouse'un kendi hafizasinda kalir."""
        if stages is not None:
            stages = [dpi_snap(v) for v in stages]
        with self._cmd_lock:
            link = _Link.open()
            try:
                cur = link.read(REPORT_DPI)
                new = build_dpi_frame(cur, stages, active)
                if new != bytes(cur[:DPI_FRAME]):
                    link.send(REPORT_DPI, new)
                if polling is not None and not link.wireless and int(polling) != 1000:
                    raise MouseError("Kabloluyken raporlama hızı hep 1000 Hz.")
                if polling is not None and link.wireless:
                    cur_poll = parse_polling_frame(link.read(REPORT_POLLING))
                    if int(polling) != cur_poll:
                        link.send(REPORT_POLLING, polling_frame(int(polling)))
                dpi = link.read(REPORT_DPI)
                poll = link.read(REPORT_POLLING)
            finally:
                link.close()
        st = self._store_settings(dpi, poll, link.mode)
        if stages is not None and st["stages"] != stages or active is not None and st["active"] != int(active):
            raise MouseError("Mouse ayarı onayladı ama okununca farklı çıktı; tekrar dene.")
        return st

    def snapshot(self, now=None):
        now = time.time() if now is None else now
        with self._lock:
            self._promote_pending(now)
            st, present, mode, settings = self.status, set(self.present), self.mode, self.settings
            live = self.last_seen > 0 and now - self.last_seen < FRESH
        wired = "kablo" in present
        if not live:
            mode = "kablo" if wired else ("2.4G" if present else None)
        moved = self.activity is not None and now - self.activity.last < AWAKE
        return {
            "receiver": bool(present),          # alici ya da kablo takili mi
            "mode": mode,                       # "kablo" / "2.4G"
            "live": live,                       # son birkac saniyede paket geldi mi
            "awake": bool(present) and (live or wired or moved),   # mouse su an kullaniliyor / uyanik mi
            "battery": st["battery"] if st else None,
            "charging": (st["charging"] if st else False) if live else (wired and not (st and st.get("full"))),
            "full": bool(st and st.get("full")) and (live or wired),
            "age": int(now - st["time"]) if st else None,
            "settings": dict(settings) if settings else None,
        }

    def close(self):
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(1)
