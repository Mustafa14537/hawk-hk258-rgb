"""
HK258 RGB - exe derleme
=======================
  python derle.py   ->  Dagitim\\HK258 RGB Kurulum.exe

1) hk258_panel.py  -> "HK258 RGB.exe" (PyInstaller, klasor halinde; Python gerektirmez)
2) bu klasor       -> app.zip
3) kurulum sihirbazi + app.zip -> tek dosya "HK258 RGB Kurulum.exe"

Gereken: python -m pip install pyinstaller hidapi pywebview pystray pillow
Not: Exe'ler imzasizdir. Akilli Uygulama Denetimi (Smart App Control) acik olan bilgisayarlarda
calismaz; internetten indirilen kopyada SmartScreen "Ek bilgi > Yine de calistir" isteyebilir.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kur  # noqa: E402

BUILD = os.path.join(tempfile.gettempdir(), "hk258_build")
OUT = os.path.join(HERE, "Dagitim")
ICO = os.path.join(HERE, "app.ico")
SETUP_NAME = "HK258 RGB Kurulum"


def version_file(name, description, filename):
    v = tuple(int(x) for x in kur.VERSION.split(".")) + (0,)
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={v}, prodvers={v}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('041f04b0', [
      StringStruct('CompanyName', '{kur.PUBLISHER}'),
      StringStruct('FileDescription', '{description}'),
      StringStruct('FileVersion', '{kur.VERSION}'),
      StringStruct('InternalName', '{name}'),
      StringStruct('OriginalFilename', '{filename}'),
      StringStruct('ProductName', '{kur.APP}'),
      StringStruct('ProductVersion', '{kur.VERSION}')])]),
    VarFileInfo([VarStruct('Translation', [0x041f, 1200])])
  ]
)
"""
    path = os.path.join(BUILD, f"version_{name.replace(' ', '_')}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def pyinstaller(*args):
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--log-level", "WARN",
                    "--specpath", BUILD, "--paths", HERE, *args], check=True)


def data(path):
    return f"{path};."


def main():
    shutil.rmtree(BUILD, ignore_errors=True)
    os.makedirs(BUILD)

    print("1/3 Uygulama derleniyor (HK258 RGB.exe)...", flush=True)
    app_dist = os.path.join(BUILD, "app_dist")
    pyinstaller("--windowed", "--name", kur.APP, "--icon", ICO,
                "--add-data", data(os.path.join(HERE, "panel.html")),
                "--add-data", data(ICO), "--add-data", data(os.path.join(HERE, "app.png")),
                "--hidden-import", "pystray._win32",
                "--version-file", version_file(kur.APP, "HK258 RGB Panel", kur.APP_EXE),
                "--distpath", app_dist, "--workpath", os.path.join(BUILD, "work_app"),
                os.path.join(HERE, "hk258_panel.py"))

    print("2/3 Paketleniyor (app.zip)...", flush=True)
    app_dir = os.path.join(app_dist, kur.APP)
    payload = os.path.join(BUILD, "app.zip")
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for root, _, files in os.walk(app_dir):
            for f in files:
                full = os.path.join(root, f)
                z.write(full, os.path.relpath(full, app_dir))

    print("3/3 Kurulum dosyasi derleniyor (tek exe)...", flush=True)
    os.makedirs(OUT, exist_ok=True)
    pyinstaller("--onefile", "--windowed", "--name", SETUP_NAME, "--icon", ICO,
                "--add-data", data(payload), "--add-data", data(ICO),
                "--add-data", data(os.path.join(HERE, "app.png")),
                "--version-file", version_file(SETUP_NAME, "HK258 RGB Kurulum Sihirbazi", SETUP_NAME + ".exe"),
                "--exclude-module", "webview", "--exclude-module", "hid", "--exclude-module", "pystray",
                "--exclude-module", "PIL", "--exclude-module", "numpy",
                "--distpath", OUT, "--workpath", os.path.join(BUILD, "work_setup"),
                os.path.join(HERE, SETUP_NAME + ".pyw"))

    exe = os.path.join(OUT, SETUP_NAME + ".exe")
    print(f"Tamam: {exe}  ({os.path.getsize(exe) / 1024 / 1024:.1f} MB)")
    return exe


if __name__ == "__main__":
    main()
