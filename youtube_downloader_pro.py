"""
YouTube Downloader Pro
Interface tkinter moderne – couleurs YouTube (rouge/noir/blanc)
Taille fixe : 500 × 350 px
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
import re
import time

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

try:
    import imageio_ffmpeg
    _FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    _FFMPEG = None


# ── utilitaires ───────────────────────────────────────────────────────────────

def _fmt_bytes(n):
    if not n or n <= 0:
        return "?"
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


def _fmt_speed(bps):
    return "?" if not bps else _fmt_bytes(bps) + "/s"


def _fmt_eta(s):
    if not s or s <= 0:
        return "?"
    s = int(s)
    if s >= 3600:
        return f"{s // 3600}h{(s % 3600) // 60:02d}m"
    if s >= 60:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s}s"


class _Cancelled(Exception):
    """Signal interne d'annulation du téléchargement."""


# ── application ───────────────────────────────────────────────────────────────

class App:
    # Palette YouTube
    RED   = "#FF0000"
    DRED  = "#CC0000"
    BG    = "#0F0F0F"
    BG2   = "#1C1C1C"
    BG3   = "#2D2D2D"
    WHITE = "#FFFFFF"
    LG    = "#CCCCCC"
    MG    = "#888888"
    GREEN = "#00C853"

    def __init__(self, root):
        self.root = root
        self.root.title("YouTube Downloader Pro")
        self.root.geometry("500x350")
        self.root.resizable(False, False)
        self.root.configure(bg=self.BG)

        self.dl_path     = os.path.expanduser("~/Downloads")
        self.cookie_file = None
        self._cancel_ev  = threading.Event()
        self._pause_ev   = threading.Event()
        self._pause_ev.set()          # "set" = non pausé
        self._thread     = None

        self._styles()
        self._build()
        self._center()

    # ── centrage ──────────────────────────────────────────────────────────────

    def _center(self):
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"500x350+{(sw - 500) // 2}+{(sh - 350) // 2}")

    # ── styles ttk ────────────────────────────────────────────────────────────

    def _styles(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure(
            "Bar.Horizontal.TProgressbar",
            troughcolor=self.BG3, background=self.GREEN,
            bordercolor=self.BG, lightcolor=self.GREEN, darkcolor="#00A040",
        )
        s.configure(
            "TCombobox",
            fieldbackground=self.BG2, background=self.BG2,
            foreground=self.WHITE, arrowcolor=self.RED,
            selectbackground=self.RED, selectforeground=self.WHITE,
        )
        s.map("TCombobox",
              fieldbackground=[("readonly", self.BG2)],
              foreground=[("readonly", self.WHITE)])
        self.root.option_add("*TCombobox*Listbox.background",       self.BG2)
        self.root.option_add("*TCombobox*Listbox.foreground",       self.WHITE)
        self.root.option_add("*TCombobox*Listbox.selectBackground", self.RED)
        self.root.option_add("*TCombobox*Listbox.selectForeground", self.WHITE)

    # ── widgets ───────────────────────────────────────────────────────────────

    def _btn(self, parent, text, cmd, bg=None, fg=None, bold=False, **kw):
        return tk.Button(
            parent, text=text, command=cmd,
            bg=bg or self.BG3, fg=fg or self.WHITE,
            activebackground=bg or self.BG3, activeforeground=fg or self.WHITE,
            font=("Segoe UI", 9, "bold" if bold else "normal"),
            relief=tk.FLAT, bd=0, cursor="hand2", highlightthickness=0, **kw,
        )

    def _lbl(self, parent, text="", fg=None, sz=9, bold=False, **kw):
        return tk.Label(
            parent, text=text, bg=parent.cget("bg"),
            fg=fg or self.MG,
            font=("Segoe UI", sz, "bold" if bold else "normal"), **kw,
        )

    # ── construction de l'interface ───────────────────────────────────────────

    def _build(self):
        # ── EN-TÊTE ROUGE ─────────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=self.RED, height=38)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)
        tk.Label(
            hdr, text="▶  YouTube Downloader Pro",
            bg=self.RED, fg=self.WHITE,
            font=("Segoe UI", 12, "bold"),
        ).pack(side=tk.LEFT, padx=12)

        # ── CORPS ─────────────────────────────────────────────────────────────
        bd = tk.Frame(self.root, bg=self.BG, padx=12, pady=7)
        bd.pack(fill=tk.BOTH, expand=True)

        # ── Ligne 1 : Dossier + Cookie ────────────────────────────────────────
        r1 = tk.Frame(bd, bg=self.BG)
        r1.pack(fill=tk.X, pady=(0, 5))

        self._btn(
            r1, "📁 Dossier", self.pick_folder,
            bg=self.RED, bold=True, padx=10, pady=4,
        ).pack(side=tk.LEFT)

        self.lbl_path = tk.Label(
            r1, text=self._clip(self.dl_path),
            bg=self.BG2, fg=self.LG,
            font=("Segoe UI", 8), anchor="w", padx=6,
        )
        self.lbl_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5), ipady=3)

        self.btn_cookie = self._btn(
            r1, "🍪 Cookie", self.pick_cookie, fg=self.MG, padx=8, pady=4,
        )
        self.btn_cookie.pack(side=tk.RIGHT)

        # ── Ligne 2 : URL ─────────────────────────────────────────────────────
        r2 = tk.Frame(bd, bg=self.BG)
        r2.pack(fill=tk.X, pady=(0, 5))

        self._lbl(r2, "URL :").pack(side=tk.LEFT)
        self.url_var = tk.StringVar()
        tk.Entry(
            r2, textvariable=self.url_var,
            bg=self.BG2, fg=self.WHITE, insertbackground=self.RED,
            font=("Segoe UI", 9), relief=tk.FLAT, bd=0,
            highlightthickness=1,
            highlightbackground=self.BG3, highlightcolor=self.RED,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 4), ipady=5)

        self._btn(
            r2, "✕", lambda: self.url_var.set(""), fg=self.MG, padx=6, pady=4,
        ).pack(side=tk.RIGHT)

        # ── Ligne 3 : Format / Qualité / Télécharger ──────────────────────────
        r3 = tk.Frame(bd, bg=self.BG)
        r3.pack(fill=tk.X, pady=(0, 6))

        self._lbl(r3, "Format :").pack(side=tk.LEFT)
        self.fmt_var = tk.StringVar(value="MP4")
        ttk.Combobox(
            r3, textvariable=self.fmt_var,
            values=["MP4", "MP3", "WEBM"],
            state="readonly", width=7, font=("Segoe UI", 9),
        ).pack(side=tk.LEFT, padx=(4, 12))

        self._lbl(r3, "Qualité :").pack(side=tk.LEFT)
        self.qual_var = tk.StringVar(value="720p")
        ttk.Combobox(
            r3, textvariable=self.qual_var,
            values=["1080p", "720p", "480p", "360p", "144p", "Audio"],
            state="readonly", width=9, font=("Segoe UI", 9),
        ).pack(side=tk.LEFT, padx=(4, 0))

        self.btn_dl = self._btn(
            r3, "⬇  Télécharger", self.start_dl,
            bg=self.RED, bold=True, padx=12, pady=4,
        )
        self.btn_dl.pack(side=tk.RIGHT)

        # ── Ligne 4 : Barre de progression ────────────────────────────────────
        r4 = tk.Frame(bd, bg=self.BG)
        r4.pack(fill=tk.X, pady=(0, 4))

        self.pct_var = tk.DoubleVar()
        ttk.Progressbar(
            r4, variable=self.pct_var, maximum=100,
            style="Bar.Horizontal.TProgressbar",
        ).pack(fill=tk.X, ipady=3)

        # ── Ligne 5 : Informations ────────────────────────────────────────────
        r5 = tk.Frame(bd, bg=self.BG2, padx=8, pady=4)
        r5.pack(fill=tk.X, pady=(0, 5))

        top = tk.Frame(r5, bg=self.BG2)
        top.pack(fill=tk.X)

        self.info_var = tk.StringVar(value="Prêt à télécharger…")
        tk.Label(
            top, textvariable=self.info_var,
            bg=self.BG2, fg=self.LG, font=("Segoe UI", 8), anchor="w",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.pct_str = tk.StringVar(value="")
        tk.Label(
            top, textvariable=self.pct_str,
            bg=self.BG2, fg=self.RED,
            font=("Segoe UI", 9, "bold"),
        ).pack(side=tk.RIGHT)

        # ── Ligne 6 : Boutons de contrôle ─────────────────────────────────────
        r6 = tk.Frame(bd, bg=self.BG)
        r6.pack(fill=tk.X)

        self.btn_pause = self._btn(
            r6, "⏸  Pause", self.toggle_pause,
            pady=4, padx=10, state=tk.DISABLED,
        )
        self.btn_pause.pack(side=tk.LEFT, padx=(0, 5))

        self.btn_cancel = self._btn(
            r6, "✕  Annuler", self.cancel_dl,
            fg=self.LG, pady=4, padx=10, state=tk.DISABLED,
        )
        self.btn_cancel.pack(side=tk.LEFT, padx=(0, 5))

        self._btn(r6, "🗑  Effacer", self.clear, pady=4, padx=10).pack(side=tk.LEFT)

        self.lbl_cookie = tk.Label(
            r6, text="", bg=self.BG, fg=self.MG, font=("Segoe UI", 8),
        )
        self.lbl_cookie.pack(side=tk.RIGHT)

    # ── outils internes ───────────────────────────────────────────────────────

    @staticmethod
    def _clip(path, n=38):
        return path if len(path) <= n else "…" + path[-(n - 1):]

    @staticmethod
    def _valid_url(url):
        return bool(re.match(
            r"(https?://)?(www\.)?(youtube\.com|youtu\.be|m\.youtube\.com)/.+",
            url, re.IGNORECASE,
        ))

    def _reset_btns(self):
        self.btn_dl.config(state=tk.NORMAL)
        self.btn_pause.config(state=tk.DISABLED, text="⏸  Pause")
        self.btn_cancel.config(state=tk.DISABLED)

    # ── actions utilisateur ───────────────────────────────────────────────────

    def pick_folder(self):
        d = filedialog.askdirectory(initialdir=self.dl_path)
        if d:
            self.dl_path = d
            self.lbl_path.config(text=self._clip(d))

    def pick_cookie(self):
        f = filedialog.askopenfilename(
            title="Fichier cookie (.txt)",
            filetypes=[("Fichiers texte", "*.txt"), ("Tous les fichiers", "*.*")],
        )
        if f:
            self.cookie_file = f
            self.btn_cookie.config(fg=self.GREEN)
            self.lbl_cookie.config(text="🍪 ✓", fg=self.GREEN)

    def start_dl(self):
        if yt_dlp is None:
            messagebox.showerror(
                "yt-dlp manquant",
                "yt-dlp n'est pas installé.\n\nLancez :\n  pip install yt-dlp imageio-ffmpeg",
            )
            return

        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Attention", "Veuillez entrer une URL YouTube.")
            return
        if not self._valid_url(url):
            messagebox.showerror(
                "URL invalide",
                "L'URL ne semble pas être une URL YouTube valide.\n\nExemple :\nhttps://www.youtube.com/watch?v=...",
            )
            return
        if self._thread and self._thread.is_alive():
            return

        self._cancel_ev.clear()
        self._pause_ev.set()
        self.btn_dl.config(state=tk.DISABLED)
        self.btn_pause.config(state=tk.NORMAL, text="⏸  Pause")
        self.btn_cancel.config(state=tk.NORMAL)
        self.pct_var.set(0)
        self.pct_str.set("0%")
        self.info_var.set("Connexion en cours…")

        self._thread = threading.Thread(
            target=self._download, args=(url,), daemon=True,
        )
        self._thread.start()

    def toggle_pause(self):
        if self._pause_ev.is_set():
            self._pause_ev.clear()
            self.btn_pause.config(text="▶  Reprendre")
            self.info_var.set("⏸  Téléchargement en pause…")
        else:
            self._pause_ev.set()
            self.btn_pause.config(text="⏸  Pause")

    def cancel_dl(self):
        if messagebox.askyesno("Annuler", "Annuler le téléchargement en cours ?"):
            self._cancel_ev.set()
            self._pause_ev.set()       # débloque le hook si en pause
            self.pct_var.set(0)
            self.pct_str.set("")
            self.info_var.set("Téléchargement annulé.")
            self._reset_btns()

    def clear(self):
        if self._thread and self._thread.is_alive():
            return
        self.url_var.set("")
        self.pct_var.set(0)
        self.pct_str.set("")
        self.info_var.set("Prêt à télécharger…")
        self._reset_btns()

    # ── logique de téléchargement ─────────────────────────────────────────────

    def _build_opts(self):
        fmt  = self.fmt_var.get()
        qual = self.qual_var.get()
        H    = {"1080p": 1080, "720p": 720, "480p": 480, "360p": 360, "144p": 144}.get(qual)

        opts = {
            "outtmpl":        os.path.join(self.dl_path, "%(title)s.%(ext)s"),
            "progress_hooks": [self._hook],
            "noplaylist":     True,
            "quiet":          True,
            "no_warnings":    True,
        }

        if _FFMPEG:
            opts["ffmpeg_location"] = _FFMPEG
        if self.cookie_file and os.path.exists(self.cookie_file):
            opts["cookiefile"] = self.cookie_file

        # ── sélection du format ────────────────────────────────────────────────
        if fmt == "MP3" or qual == "Audio":
            opts["format"] = "bestaudio/best"
            if _FFMPEG:
                opts["postprocessors"] = [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }]

        elif fmt == "WEBM":
            opts["format"] = (
                f"bestvideo[height<={H}][ext=webm]+bestaudio[ext=webm]"
                f"/bestvideo[height<={H}]+bestaudio/best"
            ) if H else "bestvideo[ext=webm]+bestaudio[ext=webm]/best"

        else:  # MP4
            opts["format"] = (
                f"bestvideo[height<={H}][ext=mp4]+bestaudio[ext=m4a]"
                f"/bestvideo[height<={H}]+bestaudio/best[height<={H}]/best"
            ) if H else "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best"
            if _FFMPEG:
                opts["merge_output_format"] = "mp4"

        return opts

    def _download(self, url):
        try:
            with yt_dlp.YoutubeDL(self._build_opts()) as ydl:
                ydl.download([url])
            if not self._cancel_ev.is_set():
                self.root.after(0, self._done)
        except _Cancelled:
            pass
        except Exception as exc:
            if not self._cancel_ev.is_set():
                msg = str(exc)
                self.root.after(0, lambda: self._err(msg))

    def _hook(self, d):
        # Annulation
        if self._cancel_ev.is_set():
            raise _Cancelled

        # Pause : bloque jusqu'à reprise ou annulation
        self._pause_ev.wait()

        if self._cancel_ev.is_set():
            raise _Cancelled

        status = d.get("status")

        if status == "downloading":
            dl  = d.get("downloaded_bytes") or 0
            tot = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            spd = d.get("speed") or 0
            eta = d.get("eta") or 0
            pct = (dl / tot * 100) if tot else 0
            info = (
                f"Vitesse : {_fmt_speed(spd)}  │  "
                f"{_fmt_bytes(dl)} / {_fmt_bytes(tot)}  │  "
                f"ETA : {_fmt_eta(eta)}"
            )
            s = f"{pct:.1f}%"
            self.root.after(0, lambda p=pct, i=info, st=s: self._upd(p, i, st))

        elif status == "finished":
            self.root.after(0, lambda: self.info_var.set("Finalisation (fusion pistes)…"))

    def _upd(self, pct, info, s):
        self.pct_var.set(pct)
        self.info_var.set(info)
        self.pct_str.set(s)

    def _done(self):
        self.pct_var.set(100)
        self.pct_str.set("100%")
        self.info_var.set("✅  Téléchargement terminé avec succès !")
        self._reset_btns()
        messagebox.showinfo("Terminé", f"Fichier sauvegardé dans :\n{self.dl_path}")

    def _err(self, msg):
        short = msg[:90] + ("…" if len(msg) > 90 else "")
        self.info_var.set(f"❌  {short}")
        self._reset_btns()
        messagebox.showerror("Erreur de téléchargement", msg)


# ── point d'entrée ────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
