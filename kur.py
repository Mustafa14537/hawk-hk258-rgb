"""
Hawk HK258 RGB - kurulum / kaldirma islemleri
=============================================
Iki sekilde kullanilir:
  * "HK258 RGB Kurulum.pyw"  (Python ile)  -> uygulamayi Python betikleri olarak kurar.
    Bu bilgisayar gibi Akilli Uygulama Denetimi acik olan, imzasiz .exe calistirmayan PC'ler icin.
  * "HK258 RGB Kurulum.exe"  (derle.py ile uretilir) -> Python gerektirmez; icindeki hazir
    "HK258 RGB.exe" uygulamasini kurar, Ayarlar > Uygulamalar listesine ekler.
Komut satirindan (Python modu):
  python kur.py           -> kurar / gunceller (tum secenekler acik)
  python kur.py --kaldir  -> kaldirir

Kurulum yeri: %LOCALAPPDATA%\\Programs\\HK258 RGB. Baslat menusu + masaustu kisayolu (logolu),
Windows acilisinda sistem tepsisinde sessizce baslama.
"""
import ctypes
import os
import shutil
import subprocess
import sys
import time
import winreg
import zipfile
from ctypes import wintypes

APP = "HK258 RGB"
VERSION = "1.0.0"
PUBLISHER = "HK258 RGB (topluluk yapimi)"
FROZEN = bool(getattr(sys, "frozen", False))        # setup.exe icinden mi calisiyoruz?
SRC = os.path.dirname(os.path.abspath(__file__))
RES = getattr(sys, "_MEIPASS", SRC)                  # exe icine gomulu dosyalar burada acilir
PAYLOAD = os.path.join(RES, "app.zip")               # exe modu: derlenmis uygulama
FILES = ["hk258_panel.py", "hk258_rgb.py", "hm220.py", "panel.html", "app.ico", "app.png"]
PACKAGES = {"hid": "hidapi", "webview": "pywebview", "pystray": "pystray", "PIL": "pillow"}
DEST = os.path.join(os.environ["LOCALAPPDATA"], "Programs", APP)
START_MENU = os.path.join(os.environ["APPDATA"], r"Microsoft\Windows\Start Menu\Programs", APP + ".lnk")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"                  # hk258_panel.py ile ayni
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\HK258RGB"
APP_EXE = "HK258 RGB.exe"
UNINSTALLER = "Kaldir.exe"
NO_WINDOW = 0x08000000                                # alt islemler konsol penceresi acmasin
PENDING_SELF_DELETE = []                              # kaldirici kendi klasorunu kapaninca siler


# ----------------------------------------------------------------- yardimcilar
def python_exe(windowed=True):
    d = os.path.dirname(sys.executable)
    p = os.path.join(d, "pythonw.exe" if windowed else "python.exe")
    return p if os.path.isfile(p) else sys.executable


def desktop_dir():
    buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf)   # CSIDL_DESKTOPDIRECTORY
    return buf.value


def desktop_link():
    return os.path.join(desktop_dir(), APP + ".lnk")


def app_script():
    return os.path.join(DEST, "hk258_panel.py")


def app_exe():
    return os.path.join(DEST, APP_EXE)


def app_target():
    """(calistirilacak dosya, argumanlar)"""
    if FROZEN:
        return app_exe(), ""
    return python_exe(), f'"{app_script()}"'


def autostart_command():
    target, args = app_target()
    return " ".join(x for x in (f'"{target}"', args, "--gizli") if x)


def is_installed():
    return os.path.isfile(app_exe()) or os.path.isfile(app_script())


def _run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True, creationflags=NO_WINDOW)


def _ps_quote(s):
    return "'" + s.replace("'", "''") + "'"


def _dir_size_kb(path):
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total // 1024


# ----------------------------------------------------------------- calisan uygulama
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.OpenMutexW.restype = wintypes.HANDLE
_k32.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
_k32.OpenEventW.restype = wintypes.HANDLE
_k32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
_k32.SetEvent.argtypes = [wintypes.HANDLE]
_k32.CloseHandle.argtypes = [wintypes.HANDLE]


def app_running():
    h = _k32.OpenMutexW(0x00100000, False, "Local\\HK258RGB_Instance")      # SYNCHRONIZE
    if h:
        _k32.CloseHandle(h)
        return True
    return False


def request_app_quit():
    ev = _k32.OpenEventW(0x0002, False, "Local\\HK258RGB_Quit")             # EVENT_MODIFY_STATE
    if ev:
        _k32.SetEvent(ev)
        _k32.CloseHandle(ev)
        return True
    return False


# ----------------------------------------------------------------- adimlar
def stop_running_app(timeout=8.0):
    """Calisan HK258 RGB'yi kapatir: once nazikce, olmazsa zorla."""
    if not app_running():
        return "çalışmıyordu"
    request_app_quit()
    t0 = time.time()
    while time.time() - t0 < timeout and app_running():
        time.sleep(0.2)
    if app_running():          # eski surumler 'kapan' sinyalini tanimiyor -> islemi sonlandir
        _run(["powershell", "-NoProfile", "-Command",
              "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'HK258 RGB.exe' -or "
              "$_.CommandLine -like '*hk258_panel.py*' } | "
              "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"])
        time.sleep(1.0)
    return "kapatıldı"


def missing_packages():
    if FROZEN:
        return []
    out = []
    for mod, pkg in PACKAGES.items():
        try:
            __import__(mod)
        except ImportError:
            out.append(pkg)
    return out


def ensure_packages():
    missing = missing_packages()
    if missing:
        _run([python_exe(windowed=False), "-m", "pip", "install", "--disable-pip-version-check", *missing])
        return "kuruldu: " + ", ".join(missing)
    return "hepsi hazır"


def install_files():
    if FROZEN:
        # exe modu: eski kurulumu (Python surumu dahil) temizle, paketi ac, kaldiriciyi koy
        if os.path.isdir(DEST):
            shutil.rmtree(DEST, ignore_errors=True)
        os.makedirs(DEST, exist_ok=True)
        with zipfile.ZipFile(PAYLOAD) as z:
            z.extractall(DEST)
            n = len(z.namelist())
        if FROZEN:
            shutil.copy2(sys.executable, os.path.join(DEST, UNINSTALLER))
        return f"{n} dosya"
    os.makedirs(DEST, exist_ok=True)
    for f in FILES:
        shutil.copy2(os.path.join(SRC, f), os.path.join(DEST, f))
    shutil.rmtree(os.path.join(DEST, "__pycache__"), ignore_errors=True)   # eski derlenmis kopyalar
    return f"{len(FILES)} dosya"


def _make_shortcut(lnk):
    target, args = app_target()
    icon = app_exe() if FROZEN else os.path.join(DEST, "app.ico")
    cmd = (f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({_ps_quote(lnk)}); "
           f"$s.TargetPath = {_ps_quote(target)}; $s.Arguments = {_ps_quote(args)}; "
           f"$s.WorkingDirectory = {_ps_quote(DEST)}; $s.IconLocation = {_ps_quote(icon + ',0')}; "
           f"$s.Description = 'Hawk HK258 klavye RGB kontrol paneli'; $s.Save()")
    _run(["powershell", "-NoProfile", "-Command", cmd])


def set_shortcuts(desktop=True, start_menu=True):
    done = []
    for want, lnk, name in ((desktop, desktop_link(), "Masaüstü"), (start_menu, START_MENU, "Başlat")):
        if want:
            _make_shortcut(lnk)
            done.append(name)
        elif os.path.exists(lnk):
            os.remove(lnk)
    return ", ".join(done) or "yok"


def set_autostart(enabled):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
        if enabled:
            winreg.SetValueEx(k, APP, 0, winreg.REG_SZ, autostart_command())
            return "açık"
        try:
            winreg.DeleteValue(k, APP)
        except FileNotFoundError:
            pass
        return "kapalı"


def register_uninstall():
    """Ayarlar > Uygulamalar listesine ekler (sadece exe kurulumunda)."""
    uninstaller = os.path.join(DEST, UNINSTALLER)
    values = {
        "DisplayName": APP, "DisplayVersion": VERSION, "Publisher": PUBLISHER,
        "DisplayIcon": app_exe() + ",0", "InstallLocation": DEST,
        "UninstallString": f'"{uninstaller}" --kaldir',
        "Comments": "Hawk HK258 klavye RGB kontrol paneli",
    }
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as k:
        for name, val in values.items():
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, val)
        for name in ("NoModify", "NoRepair"):
            winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "EstimatedSize", 0, winreg.REG_DWORD, _dir_size_kb(DEST))
    return "eklendi"


def unregister_uninstall():
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
        return "silindi"
    except FileNotFoundError:
        return "yoktu"


def remove_files():
    me = os.path.abspath(sys.executable)
    if FROZEN and os.path.dirname(me).lower() == os.path.abspath(DEST).lower():
        # Kaldir.exe kendi klasorunden calisiyor: kendisi disindakileri simdi sil,
        # kalanini program kapaninca (finish_pending) sildir.
        for name in os.listdir(DEST):
            p = os.path.join(DEST, name)
            if os.path.abspath(p).lower() == me.lower():
                continue
            shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else _try_remove(p)
        PENDING_SELF_DELETE.append(DEST)
        return "silindi"
    shutil.rmtree(DEST, ignore_errors=True)
    return "silindi" if not os.path.exists(DEST) else "bazı dosyalar silinemedi"


def _try_remove(p):
    try:
        os.remove(p)
    except OSError:
        pass


def finish_pending():
    """Kaldirici kapandiktan 2 sn sonra kendi exe'sini ve klasorunu siler."""
    for d in PENDING_SELF_DELETE:
        subprocess.Popen(f'cmd /c ping 127.0.0.1 -n 3 > nul & rmdir /s /q "{d}"',
                         creationflags=NO_WINDOW | 0x00000200, close_fds=True)   # + NEW_PROCESS_GROUP


def launch_app():
    target, args = app_target()
    cmd = [target] + ([app_script()] if args else [])
    subprocess.Popen(cmd, cwd=DEST, close_fds=True)


# ----------------------------------------------------------------- planlar
def install_plan(desktop=True, start_menu=True, autostart=True):
    plan = [("Çalışan uygulama kapatılıyor", stop_running_app)]
    if not FROZEN:
        plan.append(("Gerekli Python paketleri kontrol ediliyor", ensure_packages))
    plan += [
        ("Dosyalar kopyalanıyor", install_files),
        ("Kısayollar oluşturuluyor", lambda: set_shortcuts(desktop, start_menu)),
        ("Windows açılışı ayarlanıyor", lambda: set_autostart(autostart)),
    ]
    if FROZEN:
        plan.append(("Uygulamalar listesine ekleniyor", register_uninstall))
    return plan


def uninstall_plan():
    return [
        ("Çalışan uygulama kapatılıyor", stop_running_app),
        ("Kısayollar kaldırılıyor", lambda: set_shortcuts(False, False)),
        ("Windows açılışı kaydı siliniyor", lambda: set_autostart(False)),
        ("Uygulamalar listesinden çıkarılıyor", unregister_uninstall),
        ("Program dosyaları siliniyor", remove_files),
    ]


def main(argv):
    plan = uninstall_plan() if "--kaldir" in argv else install_plan()
    for label, step in plan:
        print(f"- {label}... ", end="", flush=True)
        print(step())
    finish_pending()
    print("Tamam." + ("" if "--kaldir" in argv else f" Kurulum yeri: {DEST}"))


if __name__ == "__main__":
    main(sys.argv[1:])
