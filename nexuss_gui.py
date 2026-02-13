#!/usr/bin/env python3
"""Nexuss Chat - Dark-themed GUI interface for Nexuss Service."""

import tkinter as tk
import threading
import json
import urllib.request
import urllib.error
import time
import subprocess
import shutil
import sys
from datetime import datetime
from pathlib import Path

# ══════════════════════════════════════════════════════════════════════════════
#  THEME
# ══════════════════════════════════════════════════════════════════════════════

BG      = "#0d1117"
BG2     = "#161b22"
BG3     = "#21262d"
BORDER  = "#30363d"
TEXT    = "#c9d1d9"
DIM     = "#8b949e"
ACCENT  = "#58a6ff"
ORANGE  = "#f78166"
GREEN   = "#3fb950"
RED     = "#f85149"
YELLOW  = "#d29922"

SERVICE_URL = "http://127.0.0.1:7860"


# ══════════════════════════════════════════════════════════════════════════════
#  GUI APPLICATION
# ══════════════════════════════════════════════════════════════════════════════

class NexussChat:

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Nexuss AI")
        self.root.geometry("1100x750")
        self.root.minsize(850, 550)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.connected = False
        self.waiting = False
        self.info_labels = {}

        self._build()
        self._dark_titlebar()

        # Start polling for service status
        self._alive = True
        threading.Thread(target=self._poll_loop, daemon=True).start()

    # ── Windows dark title bar ────────────────────────────────────────────

    def _dark_titlebar(self):
        try:
            import ctypes
            self.root.update()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 20, ctypes.byref(ctypes.c_int(1)), 4
            )
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════════
    #  BUILD UI
    # ══════════════════════════════════════════════════════════════════════

    def _build(self):
        # ── Header ────────────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=BG2, height=52)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)

        tk.Label(
            hdr, text="\u26A1 NEXUSS AI", font=("Consolas", 15, "bold"),
            bg=BG2, fg=TEXT
        ).pack(side=tk.LEFT, padx=16)

        self.st_text = tk.Label(
            hdr, text="Disconnected", font=("Segoe UI", 9), bg=BG2, fg=DIM
        )
        self.st_text.pack(side=tk.RIGHT, padx=(0, 14))
        self.st_dot = tk.Label(
            hdr, text="\u25CF", font=("Segoe UI", 11), bg=BG2, fg=RED
        )
        self.st_dot.pack(side=tk.RIGHT)

        tk.Frame(self.root, bg=BORDER, height=1).pack(fill=tk.X)

        # ── Body ──────────────────────────────────────────────────────────
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill=tk.BOTH, expand=True)

        # Chat area
        chat_frame = tk.Frame(body, bg=BG)
        chat_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0), pady=8)

        self.chat = tk.Text(
            chat_frame, bg=BG2, fg=TEXT, font=("Segoe UI", 11),
            wrap=tk.WORD, state=tk.DISABLED, bd=0,
            padx=14, pady=10, spacing3=2, cursor="arrow",
            selectbackground=ACCENT, selectforeground="#fff",
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=ACCENT,
        )
        vsb = tk.Scrollbar(chat_frame, command=self.chat.yview)
        self.chat.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.chat.pack(fill=tk.BOTH, expand=True)

        # Text tags
        for tag, opts in [
            ("uname",  {"foreground": ACCENT, "font": ("Segoe UI", 11, "bold")}),
            ("bname",  {"foreground": ORANGE, "font": ("Segoe UI", 11, "bold")}),
            ("umsg",   {"foreground": "#e6edf3"}),
            ("bmsg",   {"foreground": TEXT}),
            ("ts",     {"foreground": DIM, "font": ("Segoe UI", 8)}),
            ("sys",    {"foreground": DIM, "font": ("Segoe UI", 9, "italic"),
                        "justify": tk.CENTER}),
            ("err",    {"foreground": RED}),
            ("think",  {"foreground": YELLOW, "font": ("Segoe UI", 10, "italic")}),
        ]:
            self.chat.tag_configure(tag, **opts)

        # Vertical separator
        tk.Frame(body, bg=BORDER, width=1).pack(side=tk.LEFT, fill=tk.Y, pady=8)

        # Sidebar
        sidebar = tk.Frame(body, bg=BG, width=250)
        sidebar.pack(side=tk.RIGHT, fill=tk.Y, padx=8, pady=8)
        sidebar.pack_propagate(False)
        self._build_sidebar(sidebar)

        # ── Input bar ─────────────────────────────────────────────────────
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill=tk.X)
        inp = tk.Frame(self.root, bg=BG)
        inp.pack(fill=tk.X, padx=8, pady=8)

        self.entry = tk.Entry(
            inp, bg=BG3, fg=DIM, font=("Segoe UI", 12),
            insertbackground=ACCENT, bd=0,
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=ACCENT,
        )
        self.entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, ipady=10, padx=(0, 8))
        self.entry.insert(0, "Type a message...")
        self.entry.bind("<Return>", lambda _: self._send())
        self.entry.bind("<FocusIn>", self._focus_in)
        self.entry.bind("<FocusOut>", self._focus_out)

        self.send_btn = tk.Button(
            inp, text="Send", bg=ACCENT, fg="#000",
            font=("Segoe UI", 11, "bold"), bd=0,
            padx=20, cursor="hand2", command=self._send,
            activebackground="#79c0ff", activeforeground="#000",
        )
        self.send_btn.pack(side=tk.RIGHT, ipady=6)

    # ── Sidebar ───────────────────────────────────────────────────────────

    def _build_sidebar(self, parent):
        sections = [
            ("\u2699  MODEL", [
                "Name", "Device", "GPU", "VRAM", "Quantization", "Parameters",
            ]),
            ("\u2764  HEARTBEAT", [
                "State", "Count", "Interval", "Last Beat",
            ]),
            ("\U0001F9E0  MEMORY", [
                "Core", "Recall", "Archival",
            ]),
            ("\U0001F331  MINDROOT", [
                "Active", "Thoughts", "Last Topic", "Last Thought",
            ]),
        ]
        for i, (title, keys) in enumerate(sections):
            if i > 0:
                tk.Frame(parent, bg=BORDER, height=1).pack(fill=tk.X, pady=6)
            tk.Label(
                parent, text=title, font=("Consolas", 9, "bold"),
                bg=BG, fg=ACCENT, anchor=tk.W,
            ).pack(fill=tk.X, padx=4, pady=(8, 3))
            for key in keys:
                row = tk.Frame(parent, bg=BG)
                row.pack(fill=tk.X, padx=4, pady=1)
                tk.Label(
                    row, text=f"{key}:", font=("Segoe UI", 9),
                    bg=BG, fg=DIM, width=11, anchor=tk.W,
                ).pack(side=tk.LEFT)
                lbl = tk.Label(
                    row, text="\u2014", font=("Segoe UI", 9),
                    bg=BG, fg=TEXT, anchor=tk.W,
                )
                lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
                self.info_labels[key] = lbl

        # Service control
        tk.Frame(parent, bg=BORDER, height=1).pack(fill=tk.X, pady=8)
        self.svc_btn = tk.Button(
            parent, text="Start Service", bg=GREEN, fg="#000",
            font=("Segoe UI", 10, "bold"), bd=0,
            padx=12, pady=6, cursor="hand2",
            command=self._start_service,
        )
        self.svc_btn.pack(fill=tk.X, padx=4, pady=4)

        # Manual triggers
        btn_row = tk.Frame(parent, bg=BG)
        btn_row.pack(fill=tk.X, padx=4, pady=2)

        self.beat_btn = tk.Button(
            btn_row, text="\u2764 Beat", bg=BG3, fg=TEXT,
            font=("Segoe UI", 9, "bold"), bd=0,
            padx=6, pady=4, cursor="hand2",
            activebackground=BORDER, activeforeground=TEXT,
            command=self._manual_beat,
        )
        self.beat_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))

        self.thought_btn = tk.Button(
            btn_row, text="\U0001F331 Think", bg=BG3, fg=TEXT,
            font=("Segoe UI", 9, "bold"), bd=0,
            padx=6, pady=4, cursor="hand2",
            activebackground=BORDER, activeforeground=TEXT,
            command=self._manual_thought,
        )
        self.thought_btn.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(2, 0))

    # ══════════════════════════════════════════════════════════════════════
    #  CHAT METHODS
    # ══════════════════════════════════════════════════════════════════════

    def _sys(self, text):
        self.chat.configure(state=tk.NORMAL)
        self.chat.insert(tk.END, f"{text}\n\n", "sys")
        self.chat.configure(state=tk.DISABLED)
        self.chat.see(tk.END)

    def _msg(self, name, text, is_user=False):
        now = datetime.now().strftime("%I:%M %p")
        self.chat.configure(state=tk.NORMAL)
        self.chat.insert(tk.END, name, "uname" if is_user else "bname")
        self.chat.insert(tk.END, f"  {now}\n", "ts")
        self.chat.insert(tk.END, f"{text}\n\n", "umsg" if is_user else "bmsg")
        self.chat.configure(state=tk.DISABLED)
        self.chat.see(tk.END)

    def _focus_in(self, _):
        if self.entry.get() == "Type a message...":
            self.entry.delete(0, tk.END)
            self.entry.configure(fg=TEXT)

    def _focus_out(self, _):
        if not self.entry.get().strip():
            self.entry.delete(0, tk.END)
            self.entry.insert(0, "Type a message...")
            self.entry.configure(fg=DIM)

    # ══════════════════════════════════════════════════════════════════════
    #  SEND / RECEIVE
    # ══════════════════════════════════════════════════════════════════════

    def _send(self):
        text = self.entry.get().strip()
        if not text or text == "Type a message..." or self.waiting:
            return
        if not self.connected:
            self._sys("Not connected to Nexuss Service")
            return

        self.entry.delete(0, tk.END)
        self._msg("You", text, is_user=True)

        self.waiting = True
        self.send_btn.configure(state=tk.DISABLED, bg=BG3)

        # Show thinking indicator
        self.chat.configure(state=tk.NORMAL)
        self.chat.insert(tk.END, "Nexuss is thinking...\n\n", "think")
        self.chat.configure(state=tk.DISABLED)
        self.chat.see(tk.END)

        threading.Thread(target=self._do_send, args=(text,), daemon=True).start()

    def _do_send(self, text):
        try:
            data = json.dumps({"message": text}).encode()
            req = urllib.request.Request(
                f"{SERVICE_URL}/chat", data=data, method="POST",
                headers={"Content-Type": "application/json"},
            )
            r = urllib.request.urlopen(req, timeout=600)
            resp = json.loads(r.read()).get("response", "[No response]")
        except urllib.error.URLError:
            resp = "[Error: Service not responding]"
        except Exception as e:
            resp = f"[Error: {e}]"
        self.root.after(0, self._on_reply, resp)

    def _on_reply(self, text):
        # Remove thinking indicator (all text with "think" tag)
        self.chat.configure(state=tk.NORMAL)
        ranges = self.chat.tag_ranges("think")
        if ranges:
            self.chat.delete(ranges[0], ranges[-1])
        self.chat.configure(state=tk.DISABLED)

        self._msg("Nexuss", text)
        self.waiting = False
        self.send_btn.configure(state=tk.NORMAL, bg=ACCENT)
        self._refresh_status()

    # ══════════════════════════════════════════════════════════════════════
    #  SERVICE POLLING
    # ══════════════════════════════════════════════════════════════════════

    def _poll_loop(self):
        while self._alive:
            ok = self._health_ok()
            if ok and not self.connected:
                self.root.after(0, self._on_connect)
            elif not ok and self.connected:
                self.root.after(0, self._on_disconnect)
            if ok:
                self.root.after(0, self._refresh_status)
            time.sleep(5)

    def _health_ok(self):
        try:
            r = urllib.request.urlopen(f"{SERVICE_URL}/health", timeout=3)
            return json.loads(r.read()).get("status") == "ok"
        except Exception:
            return False

    def _on_connect(self):
        self.connected = True
        self.st_dot.configure(fg=GREEN)
        self.st_text.configure(text="Connected")
        self.svc_btn.pack_forget()
        self._sys("Connected to Nexuss Service")
        self._fetch_model_info()

    def _on_disconnect(self):
        self.connected = False
        self.st_dot.configure(fg=RED)
        self.st_text.configure(text="Disconnected")
        self.svc_btn.pack(fill=tk.X, padx=4, pady=4)
        self._sys("Disconnected from service")

    # ══════════════════════════════════════════════════════════════════════
    #  STATUS UPDATES
    # ══════════════════════════════════════════════════════════════════════

    def _fetch_model_info(self):
        def _f():
            try:
                r = urllib.request.urlopen(f"{SERVICE_URL}/model-info", timeout=5)
                info = json.loads(r.read())
                self.root.after(0, self._set_model_info, info)
            except Exception:
                pass
        threading.Thread(target=_f, daemon=True).start()

    def _set_model_info(self, info):
        L = self.info_labels
        L["Name"].configure(text=info.get("model_name", "\u2014"))
        L["Device"].configure(text=info.get("device", "\u2014"))
        L["GPU"].configure(text=info.get("gpu_name", "\u2014"))

        vt = info.get("vram_total_gb")
        vu = info.get("vram_used_gb")
        L["VRAM"].configure(text=f"{vu}/{vt} GB" if vt else "\u2014")
        L["Quantization"].configure(text=info.get("quantization", "\u2014"))

        p = info.get("parameters")
        if p:
            if p > 1e9:
                L["Parameters"].configure(text=f"{p/1e9:.1f}B")
            elif p > 1e6:
                L["Parameters"].configure(text=f"{p/1e6:.0f}M")
            else:
                L["Parameters"].configure(text=f"{p:,}")

    def _refresh_status(self):
        def _f():
            try:
                r = urllib.request.urlopen(f"{SERVICE_URL}/status", timeout=5)
                data = json.loads(r.read())
                self.root.after(0, self._set_status, data)
            except Exception:
                pass
        threading.Thread(target=_f, daemon=True).start()

    def _set_status(self, data):
        hb = data.get("heartbeat", {})
        L = self.info_labels

        state = hb.get("state", "\u2014")
        L["State"].configure(
            text=state,
            fg=GREEN if state == "IDLE" else YELLOW,
        )
        L["Count"].configure(text=str(hb.get("beat_count", "\u2014")))
        L["Interval"].configure(text=f"{hb.get('interval_seconds', '\u2014')}s")
        lb = hb.get("last_heartbeat")
        L["Last Beat"].configure(text=lb[:19] if lb else "\u2014")

        mem = hb.get("memory_stats", {})
        L["Core"].configure(
            text=f"{mem.get('core_characters', 0)}/{mem.get('core_limit', 0)}"
        )
        L["Recall"].configure(
            text=f"{mem.get('recall_messages', 0)}/{mem.get('recall_limit', 0)}"
        )
        L["Archival"].configure(text=str(mem.get("archival_blocks", 0)))

        # Mindroot
        mr_active = data.get("mindroot", False)
        L["Active"].configure(
            text="Yes" if mr_active else "No",
            fg=GREEN if mr_active else DIM,
        )
        L["Thoughts"].configure(text=str(data.get("mindroot_thoughts", 0)))
        last_thought = data.get("mindroot_last_thought", "")
        last_topic = data.get("mindroot_last_topic", "")
        L["Last Topic"].configure(text=last_topic or "\u2014")
        # Truncate thought to fit sidebar
        if last_thought and len(last_thought) > 40:
            last_thought = last_thought[:37] + "..."
        L["Last Thought"].configure(text=last_thought or "\u2014")

    # ══════════════════════════════════════════════════════════════════════
    #  SERVICE CONTROL
    # ══════════════════════════════════════════════════════════════════════

    def _start_service(self):
        self.svc_btn.configure(state=tk.DISABLED, text="Starting...", bg=YELLOW)
        self._sys("Starting Nexuss Service...")
        threading.Thread(target=self._do_start_svc, daemon=True).start()

    def _manual_beat(self):
        if not self.connected:
            return
        self.beat_btn.configure(state=tk.DISABLED, bg=YELLOW, fg="#000")
        def _do():
            try:
                req = urllib.request.Request(
                    f"{SERVICE_URL}/beat", data=b"{}", method="POST",
                    headers={"Content-Type": "application/json"},
                )
                urllib.request.urlopen(req, timeout=5)
            except Exception:
                pass
            time.sleep(1)
            self.root.after(0, lambda: (
                self.beat_btn.configure(state=tk.NORMAL, bg=BG3, fg=TEXT),
                self._refresh_status(),
            ))
        threading.Thread(target=_do, daemon=True).start()

    def _manual_thought(self):
        if not self.connected:
            return
        self.thought_btn.configure(state=tk.DISABLED, bg=YELLOW, fg="#000")
        self._sys("Generating thought...")
        def _do():
            try:
                req = urllib.request.Request(
                    f"{SERVICE_URL}/thought", data=b"{}", method="POST",
                    headers={"Content-Type": "application/json"},
                )
                urllib.request.urlopen(req, timeout=5)
            except Exception:
                pass
            # Wait for thought to generate then refresh
            time.sleep(8)
            self.root.after(0, self._after_thought)
        threading.Thread(target=_do, daemon=True).start()

    def _after_thought(self):
        self.thought_btn.configure(state=tk.NORMAL, bg=BG3, fg=TEXT)
        self._refresh_status()

    def _do_start_svc(self):
        try:
            exe = shutil.which("nexuss-service")
            if exe:
                cmd = [exe, "start", "--background"]
            else:
                cmd = [
                    sys.executable,
                    str(Path(__file__).parent / "nexuss_service.py"),
                    "start", "--background",
                ]
            subprocess.run(cmd, capture_output=True, timeout=15)
        except Exception:
            pass

        # Wait for service health
        for _ in range(60):
            time.sleep(2)
            if self._health_ok():
                self.root.after(0, lambda: self.svc_btn.configure(
                    state=tk.NORMAL, text="Start Service", bg=GREEN))
                return

        self.root.after(0, self._svc_fail)

    def _svc_fail(self):
        self.svc_btn.configure(state=tk.NORMAL, text="Start Service", bg=GREEN)
        self._sys("Failed to start. Run 'nexuss-service start' manually.")

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def _on_close(self):
        self._alive = False
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    app = NexussChat()
    app.run()


if __name__ == "__main__":
    main()
