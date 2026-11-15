"""
Hawk HK258 RGB - Kurulum Sihirbazi
Cift tiklayin. Kurulum, guncelleme ve kaldirma islemlerini adim adim yapar.
(Sadece Python'un kendi tkinter'ini kullanir; eksik paketleri kendisi kurar.)
derle.py bu dosyayi "HK258 RGB Kurulum.exe" olarak da derler (Python gerektirmeyen surum).
  --kaldir  -> dogrudan kaldirma sihirbazi (Ayarlar > Uygulamalar > Kaldir bunu acar)
"""
import ctypes
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

HERE = os.path.dirname(os.path.abspath(__file__))
RES = getattr(sys, "_MEIPASS", HERE)          # exe icinden calisirken logo/simge burada
sys.path.insert(0, HERE)
import kur  # noqa: E402

BG, SIDE, PANEL, BORDER = "#0f1218", "#0a0d12", "#171c25", "#252c38"
TEXT, MUTED, FAINT = "#e9edf5", "#8b93a7", "#5b6375"
ACCENT, ACCENT_HOVER, OK, BAD = "#1e9bff", "#4db1ff", "#3ddc84", "#ff5d6c"
STEPS = ["Hoş geldiniz", "Seçenekler", "Kurulum", "Tamamlandı"]
STEPS_UNINSTALL = ["Onay", "Kaldırma", "Tamamlandı"]          # sayfa 0, 2, 3

try:                                    # net (bulanik olmayan) yazi icin
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass
try:                                    # gorev cubugunda kendi logomuz
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Hawk.HK258RGB.Setup")
except Exception:
    pass


class Button(tk.Label):
    """Duz, renkli dugme (tk.Button Windows'ta renkleri iyi gostermiyor)."""

    def __init__(self, master, text, command, primary=True, **kw):
        self.bg = ACCENT if primary else PANEL
        self.hover = ACCENT_HOVER if primary else BORDER
        super().__init__(master, text=text, bg=self.bg, fg="#ffffff" if primary else TEXT,
                         font=("Segoe UI Semibold", 10), padx=22, pady=7, cursor="hand2", **kw)
        self.command, self.enabled = command, True
        self.bind("<Button-1>", lambda e: self.enabled and self.command())
        self.bind("<Enter>", lambda e: self.enabled and self.config(bg=self.hover))
        self.bind("<Leave>", lambda e: self.config(bg=self.bg if self.enabled else PANEL))

    def set_enabled(self, on):
        self.enabled = on
        self.config(bg=self.bg if on else PANEL, fg=("#ffffff" if self.bg == ACCENT else TEXT) if on else FAINT,
                    cursor="hand2" if on else "arrow")


class Wizard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.S = self.winfo_fpixels("1i") / 96.0          # ekran olcegi (100% = 1.0)
        px = lambda v: int(v * self.S)
        self.px = px
        self.title("HK258 RGB Kurulum Sihirbazı")
        self.configure(bg=BG)
        self.resizable(False, False)
        w, h = px(760), px(480)
        self.geometry(f"{w}x{h}+{(self.winfo_screenwidth() - w) // 2}+{(self.winfo_screenheight() - h) // 3}")
        try:
            self.iconbitmap(default=os.path.join(RES, "app.ico"))
        except tk.TclError:
            pass
        self.protocol("WM_DELETE_WINDOW", self.cancel)

        self.installed = kur.is_installed()
        self.uninstall_only = "--kaldir" in sys.argv[1:]
        self.mode = tk.StringVar(value="uninstall" if self.uninstall_only else "install")
        self.opt = {k: tk.BooleanVar(value=True) for k in ("desktop", "start_menu", "autostart", "launch")}
        self.busy = False
        self.q = queue.Queue()

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("HK.Horizontal.TProgressbar", troughcolor=PANEL, background=ACCENT, bordercolor=PANEL,
                        lightcolor=ACCENT, darkcolor=ACCENT, thickness=px(8))

        self._sidebar()
        right = tk.Frame(self, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        self.body = tk.Frame(right, bg=BG, padx=px(34), pady=px(30))
        self.body.pack(fill="both", expand=True)
        bar = tk.Frame(right, bg=BG, padx=px(34), pady=px(22))
        bar.pack(fill="x", side="bottom")
        self.btn_cancel = Button(bar, "İptal", self.cancel, primary=False)
        self.btn_cancel.pack(side="left")
        self.btn_next = Button(bar, "İleri", self.next)
        self.btn_next.pack(side="right")
        self.btn_back = Button(bar, "Geri", self.back, primary=False)
        self.btn_back.pack(side="right", padx=(0, px(10)))
        self.page = 0
        self.show(0)
        self.mode.trace_add("write", lambda *a: self._mark_steps(self.page))   # Kaldir secilince adimlar

    # ------------------------------------------------------------ yan cubuk
    def _sidebar(self):
        px = self.px
        side = tk.Frame(self, bg=SIDE, width=px(230))
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        img = tk.PhotoImage(file=os.path.join(RES, "app.png"))       # 256 px
        self.logo = img.subsample(2) if self.S < 1.2 else img.zoom(3).subsample(4)
        tk.Label(side, image=self.logo, bg=SIDE).pack(pady=(px(34), px(10)))
        tk.Label(side, text="H A W K", bg=SIDE, fg=TEXT, font=("Segoe UI Semibold", 15)).pack()
        tk.Label(side, text="HK258 RGB Panel", bg=SIDE, fg=MUTED, font=("Segoe UI", 10)).pack(pady=(0, px(30)))
        self.step_labels = []
        for _ in STEPS:
            lab = tk.Label(side, text="", bg=SIDE, anchor="w", font=("Segoe UI", 10), padx=px(30))
            lab.pack(fill="x", pady=px(4))
            self.step_labels.append(lab)

    def _mark_steps(self, page):
        if self.mode.get() == "uninstall":
            names, current = STEPS_UNINSTALL, {0: 0, 2: 1, 3: 2}.get(page, 0)
        else:
            names, current = STEPS, page
        for i, lab in enumerate(self.step_labels):
            name = names[i] if i < len(names) else ""
            if not name:
                lab.config(text="")
            elif i < current:
                lab.config(text=f"✓   {name}", fg=OK, font=("Segoe UI", 10))
            elif i == current:
                lab.config(text=f"●   {name}", fg=TEXT, font=("Segoe UI Semibold", 10))
            else:
                lab.config(text=f"○   {name}", fg=FAINT, font=("Segoe UI", 10))

    # ------------------------------------------------------------ sayfa yardimcilari
    def _clear(self):
        for w in self.body.winfo_children():
            w.destroy()

    def _title(self, text, sub=None):
        tk.Label(self.body, text=text, bg=BG, fg=TEXT, font=("Segoe UI Semibold", 17), anchor="w",
                 justify="left").pack(fill="x")
        if sub:
            tk.Label(self.body, text=sub, bg=BG, fg=MUTED, font=("Segoe UI", 10), anchor="w", justify="left",
                     wraplength=self.px(440)).pack(fill="x", pady=(self.px(8), self.px(18)))

    def _check(self, parent, text, var, hint=None):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", pady=(0, 1))
        tk.Checkbutton(row, text=text, variable=var, bg=PANEL, fg=TEXT, selectcolor=BG, activebackground=PANEL,
                       activeforeground=TEXT, font=("Segoe UI", 10), anchor="w", highlightthickness=0, bd=0,
                       padx=self.px(12), pady=self.px(7), cursor="hand2").pack(side="left")
        if hint:
            tk.Label(row, text=hint, bg=PANEL, fg=FAINT, font=("Segoe UI", 9)).pack(side="right", padx=self.px(12))

    def _box(self, text, color=MUTED):
        f = tk.Frame(self.body, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        f.pack(fill="x", pady=(self.px(6), 0))
        tk.Label(f, text=text, bg=PANEL, fg=color, font=("Segoe UI", 10), justify="left", anchor="w",
                 wraplength=self.px(430), padx=self.px(14), pady=self.px(10)).pack(fill="x")
        return f

    # ------------------------------------------------------------ sayfalar
    def show(self, i):
        self.page = i
        self._clear()
        self._mark_steps(i)
        [self.page_welcome, self.page_options, self.page_progress, self.page_done][i]()

    def page_welcome(self):
        if self.uninstall_only:
            self._title("HK258 RGB kaldırılacak",
                        "Uygulama, kısayolları ve Windows açılışı kaydı bilgisayarınızdan silinecek. "
                        "Klavye kendi gökkuşağı efektine döner. Renk ayarlarınız ileride yeniden kurarsanız "
                        "kullanılmak üzere saklanır.")
            self.btn_back.pack_forget()
            self.btn_next.config(text="Kaldır")
            self.btn_next.set_enabled(self.installed)
            if not self.installed:
                self._box("HK258 RGB bu bilgisayarda kurulu görünmüyor.", MUTED)
            return
        self._title("Kurulum sihirbazına hoş geldiniz",
                    "Bu sihirbaz Hawk HK258 klavyeniz için RGB kontrol panelini bilgisayarınıza kurar. "
                    "Panel sabit renk, nefes ve renk döngüsü efektleri sunar; USB kablosu ve 2.4G "
                    "alıcısıyla çalışır, Windows açılışında sistem tepsisinde sessizce başlayabilir.")
        if self.installed:
            box = self._box("Bilgisayarınızda HK258 RGB zaten kurulu. Ne yapmak istersiniz?", TEXT)
            for val, text in (("install", "Güncelle / onar"), ("uninstall", "Kaldır")):
                tk.Radiobutton(box, text=text, value=val, variable=self.mode, bg=PANEL, fg=TEXT,
                               selectcolor=BG, activebackground=PANEL, activeforeground=TEXT,
                               font=("Segoe UI", 10), highlightthickness=0, bd=0, cursor="hand2",
                               padx=self.px(14), pady=self.px(3)).pack(anchor="w")
            tk.Frame(box, bg=PANEL, height=self.px(8)).pack()
        self.btn_back.pack_forget()
        self.btn_next.config(text="İleri")
        self.btn_next.set_enabled(True)

    def page_options(self):
        self._title("Kurulum seçenekleri")
        tk.Label(self.body, text="Kurulacağı yer", bg=BG, fg=FAINT, font=("Segoe UI", 9), anchor="w").pack(fill="x")
        tk.Label(self.body, text=kur.DEST, bg=PANEL, fg=MUTED, font=("Consolas", 9), anchor="w",
                 padx=self.px(12), pady=self.px(7)).pack(fill="x", pady=(self.px(4), self.px(16)))
        opts = tk.Frame(self.body, bg=BG)
        opts.pack(fill="x")
        self._check(opts, "Masaüstüne kısayol oluştur", self.opt["desktop"])
        self._check(opts, "Başlat menüsüne ekle", self.opt["start_menu"])
        self._check(opts, "Windows açılışında başlat", self.opt["autostart"], "sistem tepsisinde, sessizce")
        self._check(opts, "Kurulum bitince paneli aç", self.opt["launch"])
        missing = kur.missing_packages()
        if kur.FROZEN:
            note = "Ek bir şey gerekmez: uygulama bu kurulum dosyasının içinde, Python gerektirmez."
        elif missing:
            note = "Eksik Python paketleri internetten otomatik kurulacak: " + ", ".join(missing)
        else:
            note = "Gerekli Python paketlerinin hepsi kurulu."
        tk.Label(self.body, text=note, bg=BG, fg=FAINT, font=("Segoe UI", 9), anchor="w", justify="left",
                 wraplength=self.px(440)).pack(fill="x", pady=(self.px(14), 0))
        self.btn_back.pack(side="right", padx=(0, self.px(10)))
        self.btn_next.config(text="Kur")

    def page_progress(self):
        uninstall = self.mode.get() == "uninstall"
        self._title("Kaldırılıyor…" if uninstall else "Kuruluyor…")
        self.plan = kur.uninstall_plan() if uninstall else kur.install_plan(
            self.opt["desktop"].get(), self.opt["start_menu"].get(), self.opt["autostart"].get())
        self.bar = ttk.Progressbar(self.body, style="HK.Horizontal.TProgressbar", maximum=len(self.plan))
        self.bar.pack(fill="x", pady=(self.px(10), self.px(18)))
        self.rows = []
        for label, _ in self.plan:
            row = tk.Frame(self.body, bg=BG)
            row.pack(fill="x", pady=self.px(3))
            icon = tk.Label(row, text="○", bg=BG, fg=FAINT, font=("Segoe UI", 10), width=2)
            icon.pack(side="left")
            text = tk.Label(row, text=label, bg=BG, fg=FAINT, font=("Segoe UI", 10), anchor="w")
            text.pack(side="left")
            detail = tk.Label(row, text="", bg=BG, fg=FAINT, font=("Segoe UI", 9), anchor="e")
            detail.pack(side="right")
            self.rows.append((icon, text, detail))
        self.btn_back.pack_forget()
        self.btn_next.set_enabled(False)
        self.btn_cancel.set_enabled(False)
        self.busy = True
        threading.Thread(target=self._worker, daemon=True).start()
        self.after(80, self._poll)

    def page_done(self):
        uninstall = self.mode.get() == "uninstall"
        if uninstall:
            self._title("Kaldırma tamamlandı",
                        "HK258 RGB bilgisayarınızdan kaldırıldı. Kısayollar ve Windows açılışı kaydı silindi. "
                        "Klavye birkaç saniye içinde kendi gökkuşağı efektine döner.")
        else:
            self._title("Kurulum tamamlandı",
                        "HK258 RGB kuruldu. Paneli masaüstündeki veya Başlat menüsündeki “HK258 RGB” "
                        "simgesiyle açabilirsiniz. Paneli kapatınca uygulama sistem tepsisinde çalışmaya "
                        "devam eder ve rengi korur; tamamen çıkmak için tepsi simgesine sağ tıklayın.")
            opts = tk.Frame(self.body, bg=BG)
            opts.pack(fill="x", pady=(self.px(6), 0))
            self._check(opts, "Paneli şimdi aç", self.opt["launch"])
        self.btn_back.pack_forget()
        self.btn_cancel.pack_forget()
        self.btn_next.config(text="Bitir")
        self.btn_next.set_enabled(True)

    # ------------------------------------------------------------ islem
    def _worker(self):
        for i, (label, step) in enumerate(self.plan):
            self.q.put(("start", i, None))
            try:
                self.q.put(("ok", i, str(step() or "")))
            except Exception as e:
                self.q.put(("fail", i, str(e) or e.__class__.__name__))
                return
        self.q.put(("done", None, None))

    def _poll(self):
        try:
            while True:
                kind, i, info = self.q.get_nowait()
                if kind == "start":
                    icon, text, _ = self.rows[i]
                    icon.config(text="◌", fg=ACCENT)
                    text.config(fg=TEXT)
                elif kind == "ok":
                    icon, text, detail = self.rows[i]
                    icon.config(text="✓", fg=OK)
                    text.config(fg=MUTED)
                    detail.config(text=info[:38])
                    self.bar["value"] = i + 1
                elif kind == "fail":
                    icon, text, _ = self.rows[i]
                    icon.config(text="✗", fg=BAD)
                    text.config(fg=BAD)
                    self.busy = False
                    self._box("Bir hata oluştu:\n" + info[:400], BAD)
                    self.btn_cancel.config(text="Kapat")
                    self.btn_cancel.set_enabled(True)
                    return
                elif kind == "done":
                    self.busy = False
                    self.after(500, lambda: self.show(3))
                    return
        except queue.Empty:
            pass
        self.after(80, self._poll)

    # ------------------------------------------------------------ dugmeler
    def next(self):
        if self.page == 0 and self.uninstall_only:
            self.show(2)
        elif self.page == 0:
            if self.mode.get() == "uninstall":
                if messagebox.askyesno("HK258 RGB", "HK258 RGB kaldırılsın mı?", parent=self):
                    self.show(2)
            else:
                self.show(1)
        elif self.page == 1:
            self.show(2)
        elif self.page == 3:
            if self.mode.get() == "install" and self.opt["launch"].get():
                kur.launch_app()
            self.destroy()

    def back(self):
        if self.page == 1:
            self.show(0)

    def cancel(self):
        if self.busy:
            return
        if self.page in (2, 3) or messagebox.askyesno("HK258 RGB", "Kurulumdan çıkılsın mı?", parent=self):
            self.destroy()


if __name__ == "__main__":
    Wizard().mainloop()
    kur.finish_pending()          # kaldirici kendi klasorunu kapandiktan sonra siler
