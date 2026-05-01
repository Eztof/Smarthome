# ═══════════════════════════════════════════════════════════
#  launcher.py  –  PI·HOME Steuerung (Windows)
#  Features: Start/Stop, Status, Log, Live-Stats, Config
# ═══════════════════════════════════════════════════════════

import tkinter as tk
from tkinter import font as tkfont, ttk, messagebox, filedialog
import subprocess, threading, time, sys, os, json, webbrowser

# BASE_DIR immer relativ zur launcher.py selbst — auch bei Desktop-Verknüpfung
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
# Falls launcher.py direkt auf dem Desktop liegt (Verknüpfung), Smarthome-Ordner suchen
if not os.path.exists(os.path.join(BASE_DIR, "config.py")):
    # Typischer Pfad
    candidate = os.path.join(os.path.expanduser("~"), "Desktop", "Smarthome")
    if os.path.exists(os.path.join(candidate, "config.py")):
        BASE_DIR = candidate

VENV_PYC = os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")
MAIN_PY  = os.path.join(BASE_DIR, "main.py")
PID_FILE = os.path.join(BASE_DIR, "data", "smarthome.pid")
LOG_FILE = os.path.join(BASE_DIR, "data", "smarthome.log")
CFG_FILE = os.path.join(BASE_DIR, "data", "launcher_config.json")
CONFIG_PY= os.path.join(BASE_DIR, "config.py")

PY = VENV_PYC if os.path.exists(VENV_PYC) else sys.executable
os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)

# ── Farben ────────────────────────────────────────────────
C = {
    "bg":      "#0a0d12",
    "panel":   "#111620",
    "card":    "#161c28",
    "border":  "#1e2535",
    "text":    "#e8edf5",
    "muted":   "#5a6480",
    "dim":     "#3a4255",
    "accent":  "#4fc3f7",
    "green":   "#69db7c",
    "red":     "#ff6b6b",
    "warm":    "#ffb347",
    "purple":  "#7c83ff",
}

def read_config_py(key, default=""):
    """Liest einen Wert aus config.py (Kommentare werden ignoriert)."""
    try:
        with open(CONFIG_PY, encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if stripped.startswith(key + " ") or stripped.startswith(key + "="):
                    val = stripped.split("=", 1)[1]
                    # Inline-Kommentar abschneiden
                    if "#" in val:
                        val = val[:val.index("#")]
                    val = val.strip().strip('"').strip("'")
                    return val
    except Exception:
        pass
    return default

def write_config_py(key, value):
    """Schreibt einen Wert sicher in config.py ohne Kommentare zu beschaedigen."""
    try:
        with open(CONFIG_PY, encoding="utf-8") as f:
            lines = f.readlines()
        new_lines = []
        found = False
        for line in lines:
            stripped = line.strip()
            # Nur echte Zuweisungen matchen, keine Kommentarzeilen
            is_assignment = (
                "=" in stripped
                and not stripped.startswith("#")
                and (stripped.startswith(key + " ") or stripped.startswith(key + "="))
            )
            if is_assignment:
                indent = line[:len(line) - len(line.lstrip())]
                # Kommentar NACH dem Wert erhalten
                after_eq = line.split("=", 1)[1]
                if "#" in after_eq:
                    comment = "  # " + after_eq.split("#", 1)[1].rstrip("\n").strip()
                else:
                    comment = ""
                # Neuen Wert formatieren (int / float / str)
                val_str = str(value).strip()
                try:
                    formatted = str(int(val_str))
                except ValueError:
                    try:
                        formatted = str(float(val_str))
                    except ValueError:
                        formatted = f'"{val_str}"'
                new_lines.append(f"{indent}{key} = {formatted}{comment}\n")
                found = True
            else:
                new_lines.append(line)
        if found:
            with open(CONFIG_PY, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            return True
    except Exception as e:
        print(f"Config-Fehler: {e}")
    return False


class Launcher:
    def __init__(self, root):
        self.root    = root
        self.process = None
        self.stats   = {"events_today": 0, "sensors": 0, "uptime": 0}
        self._start_time = None
        self._load_pid()
        self._build_ui()
        self._watchdog()

    def _load_pid(self):
        try:
            if os.path.exists(PID_FILE):
                pid = int(open(PID_FILE).read().strip())
                import psutil
                if psutil.pid_exists(pid):
                    self.process = psutil.Process(pid)
                    self._start_time = self.process.create_time()
                    return
        except Exception:
            pass
        self.process = None
        if os.path.exists(PID_FILE):
            try: os.remove(PID_FILE)
            except: pass

    def _save_pid(self, pid):
        with open(PID_FILE, "w") as f: f.write(str(pid))

    def _clear_pid(self):
        if os.path.exists(PID_FILE):
            try: os.remove(PID_FILE)
            except: pass

    # ── UI ────────────────────────────────────────────────
    def _build_ui(self):
        r = self.root
        r.title("PI·HOME Steuerung")
        r.configure(bg=C["bg"])
        r.resizable(True, True)
        r.minsize(480, 560)

        # Position: rechts unten
        r.update_idletasks()
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        r.geometry(f"520x620+{sw-540}+{sh-660}")

        # Fonts
        fh = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        fb = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        fm = tkfont.Font(family="Segoe UI", size=9)
        fc = tkfont.Font(family="Consolas",  size=9)
        ft = tkfont.Font(family="Segoe UI", size=14, weight="bold")

        # ── Header ────────────────────────────────────────
        hdr = tk.Frame(r, bg=C["panel"], pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⌂ PI·HOME", font=ft, bg=C["panel"], fg=C["accent"]).pack(side="left", padx=16)
        tk.Button(hdr, text="🌐 Browser", font=fm, bg=C["border"], fg=C["muted"],
                  relief="flat", bd=0, padx=10, pady=5, cursor="hand2",
                  command=lambda: webbrowser.open("http://localhost:5000")).pack(side="right", padx=12)

        # ── Tabs ──────────────────────────────────────────
        tab_frame = tk.Frame(r, bg=C["panel"])
        tab_frame.pack(fill="x")
        self.tabs = {}
        self.tab_contents = {}
        for name, label in [("main","⚡ Steuerung"),("log","📄 Log"),("config","⚙ Konfiguration")]:
            btn = tk.Button(tab_frame, text=label, font=fm,
                            bg=C["panel"], fg=C["muted"],
                            relief="flat", bd=0, padx=14, pady=8, cursor="hand2",
                            command=lambda n=name: self._show_tab(n))
            btn.pack(side="left")
            self.tabs[name] = btn

        sep = tk.Frame(r, bg=C["border"], height=1)
        sep.pack(fill="x")

        content = tk.Frame(r, bg=C["bg"])
        content.pack(fill="both", expand=True)

        # ── Tab: Steuerung ─────────────────────────────────
        main_tab = tk.Frame(content, bg=C["bg"], padx=16, pady=14)
        self.tab_contents["main"] = main_tab

        # Status-Karte
        sc = tk.Frame(main_tab, bg=C["card"], relief="flat", bd=0)
        sc.pack(fill="x", pady=(0,10))
        sc_inner = tk.Frame(sc, bg=C["card"], padx=16, pady=14)
        sc_inner.pack(fill="x")

        sf = tk.Frame(sc_inner, bg=C["card"])
        sf.pack(fill="x")
        self.dot  = tk.Label(sf, text="●", font=tkfont.Font(family="Consolas", size=16),
                             bg=C["card"], fg=C["dim"])
        self.dot.pack(side="left")
        sv = tk.Frame(sf, bg=C["card"])
        sv.pack(side="left", padx=10)
        self.status_lbl = tk.Label(sv, text="Gestoppt", font=fb, bg=C["card"], fg=C["muted"])
        self.status_lbl.pack(anchor="w")
        self.uptime_lbl = tk.Label(sv, text="", font=fc, bg=C["card"], fg=C["dim"])
        self.uptime_lbl.pack(anchor="w")
        self.url_lbl = tk.Label(sc_inner, text="", font=fc, bg=C["card"], fg=C["accent"], cursor="hand2")
        self.url_lbl.pack(anchor="w", pady=(6,0))
        self.url_lbl.bind("<Button-1>", lambda e: webbrowser.open("http://localhost:5000"))

        # Buttons
        bf = tk.Frame(main_tab, bg=C["bg"])
        bf.pack(fill="x", pady=(0,10))
        self.b_start = tk.Button(bf, text="▶  Server starten", font=fb,
            bg="#1a3a5c", fg=C["accent"], activebackground="#1e4a70", activeforeground="#fff",
            relief="flat", bd=0, padx=0, pady=10, cursor="hand2", command=self._start)
        self.b_start.pack(side="left", fill="x", expand=True, padx=(0,6))
        self.b_stop = tk.Button(bf, text="■  Stoppen", font=fb,
            bg="#1a1a1a", fg=C["muted"], activebackground="#2a1010", activeforeground="#fff",
            relief="flat", bd=0, padx=0, pady=10, cursor="hand2", command=self._stop, state="disabled")
        self.b_stop.pack(side="left", fill="x", expand=True)

        # Live-Statistiken
        stats_frame = tk.LabelFrame(main_tab, text=" Live-Statistik ", font=fm,
                                     bg=C["bg"], fg=C["muted"], bd=1, relief="flat",
                                     labelanchor="n")
        stats_frame.pack(fill="x", pady=(0,10))

        self.stat_vars = {}
        stats_items = [
            ("events", "🐕 Ereignisse heute", "—"),
            ("sensors", "📱 Verbundene Sensoren", "—"),
            ("uptime",  "⏱ Laufzeit", "—"),
            ("weather", "🌤 Letzter Wetter-Abruf", "—"),
        ]
        for key, label, default in stats_items:
            row = tk.Frame(stats_frame, bg=C["card"], padx=12, pady=8)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=label, font=fm, bg=C["card"], fg=C["muted"]).pack(side="left")
            var = tk.StringVar(value=default)
            self.stat_vars[key] = var
            tk.Label(row, textvariable=var, font=fc, bg=C["card"], fg=C["text"]).pack(side="right")

        # ── Tab: Log ──────────────────────────────────────
        log_tab = tk.Frame(content, bg=C["bg"], padx=16, pady=14)
        self.tab_contents["log"] = log_tab

        log_btn_f = tk.Frame(log_tab, bg=C["bg"])
        log_btn_f.pack(fill="x", pady=(0,8))
        for txt, cmd in [("↻ Aktualisieren", self._reload_log),
                         ("🗑 Log leeren", self._clear_log),
                         ("📂 Öffnen", lambda: os.startfile(LOG_FILE) if os.path.exists(LOG_FILE) else None)]:
            tk.Button(log_btn_f, text=txt, font=fm, bg=C["card"], fg=C["muted"],
                      relief="flat", bd=0, padx=10, pady=6, cursor="hand2", command=cmd
                      ).pack(side="left", padx=(0,6))

        log_frame = tk.Frame(log_tab, bg=C["border"])
        log_frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_frame, font=fc, bg=C["card"], fg=C["muted"],
                                 insertbackground=C["text"], relief="flat", bd=0,
                                 wrap="none", state="disabled", padx=8, pady=8)
        log_sb_y = tk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        log_sb_x = tk.Scrollbar(log_frame, orient="horizontal", command=self.log_text.xview)
        self.log_text.configure(yscrollcommand=log_sb_y.set, xscrollcommand=log_sb_x.set)
        log_sb_y.pack(side="right", fill="y")
        log_sb_x.pack(side="bottom", fill="x")
        self.log_text.pack(fill="both", expand=True)

        # ── Tab: Konfiguration ─────────────────────────────
        cfg_tab = tk.Frame(content, bg=C["bg"], padx=16, pady=14)
        self.tab_contents["config"] = cfg_tab

        # Scrollbare Config
        cfg_canvas = tk.Canvas(cfg_tab, bg=C["bg"], highlightthickness=0)
        cfg_scroll = tk.Scrollbar(cfg_tab, orient="vertical", command=cfg_canvas.yview)
        cfg_canvas.configure(yscrollcommand=cfg_scroll.set)
        cfg_scroll.pack(side="right", fill="y")
        cfg_canvas.pack(side="left", fill="both", expand=True)
        self.cfg_inner = tk.Frame(cfg_canvas, bg=C["bg"])
        cfg_canvas.create_window((0,0), window=self.cfg_inner, anchor="nw")
        self.cfg_inner.bind("<Configure>", lambda e: cfg_canvas.configure(scrollregion=cfg_canvas.bbox("all")))

        self._build_config()

        # Alle Tabs verstecken außer main
        for name, frame in self.tab_contents.items():
            frame.pack_forget()
        self._show_tab("main")
        self._refresh_ui()

    def _show_tab(self, name):
        for n, frame in self.tab_contents.items():
            frame.pack_forget()
            self.tabs[n].configure(bg=C["panel"], fg=C["muted"])
        self.tab_contents[name].pack(fill="both", expand=True)
        self.tabs[name].configure(bg=C["border"], fg=C["accent"])
        if name == "log":
            self._reload_log()

    # ── Konfiguration ─────────────────────────────────────
    def _build_config(self):
        p = self.cfg_inner
        self.cfg_vars = {}

        sections = [
            ("🌍 Standort & Server", [
                ("LOCATION_NAME", "Ortsname", "str", None),
                ("LATITUDE",      "Breitengrad", "float", None),
                ("LONGITUDE",     "Längengrad",  "float", None),
                ("PORT",          "Server-Port", "int", None),
                ("WEATHER_UPDATE_INTERVAL", "Wetter-Update (Min.)", "int", None),
            ]),
            ("🐕 Hunde-Modul", [
                ("DOG_THRESHOLD_DB",   "Schwellenwert (dB)", "float", None),
                ("DOG_COOLDOWN",       "Cooldown (Sek.)",    "float", None),
                ("DOG_CHUNK_DURATION", "Chunk-Dauer (Sek.)", "float", None),
            ]),
            ("🌧 Wetter-Chart Transparenz  (0.0 = unsichtbar, 1.0 = voll)", [
                ("WEATHER_RAIN_OPACITY_TOP", "Regen oben",         "float", None),
                ("WEATHER_RAIN_OPACITY_BTM", "Regen unten",        "float", None),
                ("WEATHER_RAIN_BORDER",      "Regen Randlinie",    "float", None),
                ("WEATHER_TEMP_OPACITY",     "Temperatur-Füllung", "float", None),
            ]),
            ("🎬 Jellyfin", [
                ("JELLYFIN_URL",     "Jellyfin URL",    "str", None),
                ("JELLYFIN_API_KEY", "API-Key",         "str", None),
            ]),
        ]

        for section_title, fields in sections:
            tk.Label(p, text=section_title, font=tkfont.Font(family="Segoe UI", size=10, weight="bold"),
                     bg=C["bg"], fg=C["accent"]).pack(anchor="w", pady=(12,4))

            card = tk.Frame(p, bg=C["card"], padx=12, pady=8)
            card.pack(fill="x", pady=(0,4))

            for key, label, typ, _ in fields:
                row = tk.Frame(card, bg=C["card"])
                row.pack(fill="x", pady=4)
                tk.Label(row, text=label, font=tkfont.Font(family="Segoe UI", size=9),
                         bg=C["card"], fg=C["muted"], width=24, anchor="w").pack(side="left")
                var = tk.StringVar(value=read_config_py(key))
                entry = tk.Entry(row, textvariable=var, font=tkfont.Font(family="Consolas", size=9),
                                  bg=C["bg"], fg=C["text"], insertbackground=C["text"],
                                  relief="flat", bd=1, highlightthickness=1,
                                  highlightcolor=C["accent"], highlightbackground=C["border"])
                entry.pack(side="left", fill="x", expand=True, ipady=4, padx=(6,0))
                self.cfg_vars[key] = var

        # Speichern-Button
        tk.Button(p, text="💾  Konfiguration speichern", font=tkfont.Font(family="Segoe UI", size=10, weight="bold"),
                  bg="#1a3a5c", fg=C["accent"], activebackground="#1e4a70", activeforeground="#fff",
                  relief="flat", bd=0, padx=0, pady=10, cursor="hand2",
                  command=self._save_config).pack(fill="x", pady=(16,4))

        tk.Label(p, text="⚠ Server muss neu gestartet werden damit Änderungen wirksam werden.",
                 font=tkfont.Font(family="Segoe UI", size=8),
                 bg=C["bg"], fg=C["muted"], wraplength=400, justify="center").pack(pady=(4,0))

    def _save_config(self):
        saved, failed = 0, []
        for key, var in self.cfg_vars.items():
            if write_config_py(key, var.get()):
                saved += 1
            else:
                failed.append(key)
        if failed:
            messagebox.showwarning("Fehler", f"Konnte nicht speichern: {', '.join(failed)}")
        else:
            messagebox.showinfo("Gespeichert", f"{saved} Einstellungen gespeichert.\nServer neu starten für Änderungen.")

    # ── Log ───────────────────────────────────────────────
    def _reload_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        try:
            if os.path.exists(LOG_FILE):
                with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                # Letzte 300 Zeilen
                text = "".join(lines[-300:])
                self.log_text.insert("end", text)
                self.log_text.see("end")
        except Exception as e:
            self.log_text.insert("end", f"Fehler: {e}")
        self.log_text.configure(state="disabled")

    def _clear_log(self):
        if messagebox.askyesno("Log leeren", "Log-Datei wirklich leeren?"):
            try:
                open(LOG_FILE, "w").close()
                self._reload_log()
            except Exception as e:
                messagebox.showerror("Fehler", str(e))

    # ── Server ────────────────────────────────────────────
    def _start(self):
        if self._running(): return
        try:
            log = open(LOG_FILE, "a", encoding="utf-8")
            self.process = subprocess.Popen(
                [PY, MAIN_PY], cwd=BASE_DIR,
                stdout=log, stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self._save_pid(self.process.pid)
            self._start_time = time.time()
            self._set("Startet...", C["warm"])
            threading.Thread(target=lambda: (time.sleep(2.5), self.root.after(0, self._refresh_ui)), daemon=True).start()
        except Exception as e:
            self._set(f"Fehler: {e}", C["red"])

    def _stop(self):
        if not self._running(): return
        self._set("Stoppt...", C["warm"])
        def do_stop():
            try:
                self.process.terminate()
                try: self.process.wait(timeout=5)
                except: self.process.kill()
            except: pass
            self._clear_pid()
            self.process = None
            self._start_time = None
            self.root.after(0, self._refresh_ui)
        threading.Thread(target=do_stop, daemon=True).start()

    def _running(self):
        if self.process is None: return False
        try:
            ret = self.process.poll()
            if ret is not None: self.process = None; return False
            return True
        except AttributeError:
            try: return self.process.is_running()
            except: return False

    def _refresh_ui(self):
        running = self._running()
        if running:
            self._set("Läuft", C["green"])
            self.url_lbl.config(text="→ http://localhost:5000", fg=C["accent"])
            self.b_start.config(state="disabled", bg="#111a11", fg=C["dim"])
            self.b_stop.config(state="normal",   bg="#2a1010", fg=C["red"])
            # Uptime
            if self._start_time:
                secs = int(time.time() - self._start_time)
                h,m,s = secs//3600, (secs%3600)//60, secs%60
                self.uptime_lbl.config(text=f"Laufzeit: {h:02d}:{m:02d}:{s:02d}")
            self.dot.config(fg=C["green"])
        else:
            self._set("Gestoppt", C["muted"])
            self.url_lbl.config(text="", fg=C["dim"])
            self.uptime_lbl.config(text="")
            self.b_start.config(state="normal",  bg="#1a3a5c", fg=C["accent"])
            self.b_stop.config(state="disabled", bg="#1a1a1a", fg=C["muted"])
            self.dot.config(fg=C["dim"])
            for key in self.stat_vars:
                self.stat_vars[key].set("—")

    def _set(self, text, color):
        self.status_lbl.config(text=text, fg=color)
        self.dot.config(fg=color)

    # ── Live-Statistiken ──────────────────────────────────


    def _fetch_stats(self):
        """Stats im Hintergrund-Thread holen — nie im UI-Thread aufrufen."""
        def _do():
            try:
                import urllib.request, json as _json
                base = "http://localhost:5000"
                try:
                    with urllib.request.urlopen(f"{base}/api/hunde/charts", timeout=1) as r:
                        d = _json.loads(r.read())
                        val = str(d.get("stats",{}).get("total",0))
                        self.root.after(0, lambda v=val: self.stat_vars["events"].set(v))
                except: pass
                try:
                    with urllib.request.urlopen(f"{base}/api/sensors", timeout=1) as r:
                        d = _json.loads(r.read())
                        val = str(len(d))
                        self.root.after(0, lambda v=val: self.stat_vars["sensors"].set(v))
                except: pass
                try:
                    with urllib.request.urlopen(f"{base}/api/weather/current", timeout=1) as r:
                        d = _json.loads(r.read())
                        ts = d.get("timestamp","")
                        val = ts[11:16] + " Uhr" if ts else "—"
                        self.root.after(0, lambda v=val: self.stat_vars["weather"].set(v))
                except: pass
            except: pass
        threading.Thread(target=_do, daemon=True).start()

    def _update_uptime(self):
        if self._running() and self._start_time:
            secs = int(time.time() - self._start_time)
            h,m,s = secs//3600, (secs%3600)//60, secs%60
            self.stat_vars["uptime"].set(f"{h:02d}:{m:02d}:{s:02d}")
            self.uptime_lbl.config(text=f"Laufzeit: {h:02d}:{m:02d}:{s:02d}")

    # ── Watchdog ──────────────────────────────────────────
    def _watchdog(self):
        def loop():
            tick = 0
            while True:
                time.sleep(1)
                tick += 1
                self.root.after(0, self._refresh_ui)
                self.root.after(0, self._update_uptime)
                if tick % 10 == 0 and self._running():  # alle 10s Stats
                    self._fetch_stats()
        threading.Thread(target=loop, daemon=True).start()


if __name__ == "__main__":
    try: import psutil
    except ImportError: pass
    root = tk.Tk()
    app = Launcher(root)
    root.mainloop()
