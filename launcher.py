# ═══════════════════════════════════════════════════════════
#  launcher.py  –  Smarthome Steuerungsfenster (Windows)
#  Kleines Fenster: Start / Stop / Status
#  Immer im Vordergrund, rechts unten
# ═══════════════════════════════════════════════════════════

import tkinter as tk
from tkinter import font as tkfont
import subprocess
import threading
import time
import sys
import os
import webbrowser

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
VENV_PY   = os.path.join(BASE_DIR, "venv", "Scripts", "pythonw.exe")
VENV_PYC  = os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")
MAIN_PY   = os.path.join(BASE_DIR, "main.py")
PID_FILE  = os.path.join(BASE_DIR, "data", "smarthome.pid")
LOG_FILE  = os.path.join(BASE_DIR, "data", "smarthome.log")

# Python-Pfad bestimmen
if os.path.exists(VENV_PYC):
    PY = VENV_PYC
elif os.path.exists(VENV_PY):
    PY = VENV_PY
else:
    PY = sys.executable

os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)


class Launcher:
    def __init__(self, root):
        self.root    = root
        self.process = None
        self._load_pid()
        self._build_ui()
        self._watchdog()

    # ── PID aus Datei laden ───────────────────────────────
    def _load_pid(self):
        try:
            if os.path.exists(PID_FILE):
                pid = int(open(PID_FILE).read().strip())
                import psutil
                if psutil.pid_exists(pid):
                    self.process = psutil.Process(pid)
                    return
        except Exception:
            pass
        self.process = None
        self._clear_pid()

    def _save_pid(self, pid):
        with open(PID_FILE, "w") as f:
            f.write(str(pid))

    def _clear_pid(self):
        if os.path.exists(PID_FILE):
            try:
                os.remove(PID_FILE)
            except Exception:
                pass

    # ── UI aufbauen ───────────────────────────────────────
    def _build_ui(self):
        r = self.root
        r.title("PI·HOME")
        r.geometry("290x215")
        r.resizable(False, False)
        r.attributes("-topmost", True)
        r.configure(bg="#0a0d12")
        r.protocol("WM_DELETE_WINDOW", lambda: r.destroy())

        # Position: rechts unten
        r.update_idletasks()
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        r.geometry(f"290x215+{sw-310}+{sh-255}")

        # Fonts
        f_title  = tkfont.Font(family="Segoe UI", size=14, weight="bold")
        f_sub    = tkfont.Font(family="Consolas",  size=10)
        f_btn    = tkfont.Font(family="Segoe UI",  size=10, weight="bold")
        f_foot   = tkfont.Font(family="Segoe UI",  size=8)

        # Titel
        tk.Label(r, text="PI·HOME", font=f_title,
                 bg="#0a0d12", fg="#4fc3f7").pack(pady=(14,2))

        # Status-Zeile
        sf = tk.Frame(r, bg="#0a0d12")
        sf.pack()
        self.dot   = tk.Label(sf, text="●", font=f_sub, bg="#0a0d12", fg="#3a4255")
        self.dot.pack(side="left")
        self.slbl  = tk.Label(sf, text="Gestoppt", font=f_sub, bg="#0a0d12", fg="#5a6480")
        self.slbl.pack(side="left", padx=4)

        # URL
        self.url = tk.Label(r, text="", font=tkfont.Font(family="Consolas", size=9),
                            bg="#0a0d12", fg="#3a4255", cursor="hand2")
        self.url.pack(pady=(1,0))
        self.url.bind("<Button-1>", lambda e: webbrowser.open("http://localhost:5000"))

        # Buttons
        bf = tk.Frame(r, bg="#0a0d12")
        bf.pack(pady=12)

        self.b_start = tk.Button(
            bf, text="▶  Starten", font=f_btn,
            bg="#1a3a5c", fg="#4fc3f7",
            activebackground="#1e4a70", activeforeground="#fff",
            relief="flat", bd=0, padx=16, pady=8,
            cursor="hand2", command=self._start
        )
        self.b_start.grid(row=0, column=0, padx=6)

        self.b_stop = tk.Button(
            bf, text="■  Stoppen", font=f_btn,
            bg="#1a1a1a", fg="#5a6480",
            activebackground="#2a1010", activeforeground="#fff",
            relief="flat", bd=0, padx=16, pady=8,
            cursor="hand2", command=self._stop, state="disabled"
        )
        self.b_stop.grid(row=0, column=1, padx=6)

        # Logfile-Link
        lf = tk.Frame(r, bg="#0a0d12")
        lf.pack()
        tk.Label(lf, text="📄", font=f_foot, bg="#0a0d12", fg="#3a4255").pack(side="left")
        ll = tk.Label(lf, text="Log öffnen", font=f_foot, bg="#0a0d12", fg="#3a4255", cursor="hand2")
        ll.pack(side="left", padx=2)
        ll.bind("<Button-1>", lambda e: os.startfile(LOG_FILE) if os.path.exists(LOG_FILE) else None)

        # Fußzeile
        tk.Label(r, text="PI·HOME Smarthome  –  Windows",
                 font=f_foot, bg="#0a0d12", fg="#1e2535").pack(side="bottom", pady=6)

        self._refresh_ui()

    # ── Server starten ────────────────────────────────────
    def _start(self):
        if self._running():
            return
        try:
            log = open(LOG_FILE, "a", encoding="utf-8")
            self.process = subprocess.Popen(
                [PY, MAIN_PY],
                cwd=BASE_DIR,
                stdout=log, stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self._save_pid(self.process.pid)
            self._set("Startet...", "#ffb347")
            threading.Thread(
                target=lambda: (time.sleep(2.5), self.root.after(0, self._refresh_ui)),
                daemon=True
            ).start()
        except Exception as e:
            self._set(f"Fehler: {e}", "#ff6b6b")

    # ── Server stoppen ────────────────────────────────────
    def _stop(self):
        if not self._running():
            return
        self._set("Stoppt...", "#ffb347")
        def do_stop():
            try:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except Exception:
                    self.process.kill()
            except Exception:
                pass
            self._clear_pid()
            self.process = None
            self.root.after(0, self._refresh_ui)
        threading.Thread(target=do_stop, daemon=True).start()

    # ── Läuft der Prozess? ────────────────────────────────
    def _running(self):
        if self.process is None:
            return False
        try:
            ret = self.process.poll()          # subprocess
            if ret is not None:
                self.process = None
                return False
            return True
        except AttributeError:
            try:
                return self.process.is_running()  # psutil
            except Exception:
                return False

    # ── UI-Update ─────────────────────────────────────────
    def _refresh_ui(self):
        running = self._running()
        if running:
            self._set("Läuft", "#69db7c")
            self.url.config(text="http://localhost:5000", fg="#4fc3f7")
            self.b_start.config(state="disabled", bg="#111a11", fg="#3a4255")
            self.b_stop.config(state="normal",   bg="#2a1010", fg="#ff6b6b")
        else:
            self._set("Gestoppt", "#5a6480")
            self.url.config(text="", fg="#3a4255")
            self.b_start.config(state="normal",   bg="#1a3a5c", fg="#4fc3f7")
            self.b_stop.config(state="disabled",  bg="#1a1a1a", fg="#5a6480")

    def _set(self, text, color):
        self.dot.config(fg=color)
        self.slbl.config(text=text, fg=color)

    # ── Watchdog ──────────────────────────────────────────
    def _watchdog(self):
        def loop():
            while True:
                time.sleep(3)
                self.root.after(0, self._refresh_ui)
        threading.Thread(target=loop, daemon=True).start()


if __name__ == "__main__":
    try:
        import psutil
    except ImportError:
        pass
    root = tk.Tk()
    app  = Launcher(root)
    root.mainloop()
