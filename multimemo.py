"""멀티 메모 - 한 화면에 여러 개의 스티커 메모를 동시에 띄우는 프로그램.

- 메모 개수에 맞춰 화면을 자동으로 나눠 배치 (1개=전체, 2개=반반, 4개=2x2 ...)
- 각 메모는 개별 .txt 파일로 자동 저장 (맥: 문서/멀티메모, 윈도우: notes 폴더)
- 단축키: Cmd(Ctrl)+N 새 메모, Cmd(Ctrl)+마우스휠 글자 크기 (5~20pt)
- 맥/윈도우 공용
"""
import json
import math
import os
import shutil
import subprocess
import sys
import time
import ctypes
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox

IS_MAC = sys.platform == "darwin"
if IS_MAC:
    # 앱(.app)으로 묶어도 메모가 남도록 '문서' 폴더에 저장
    NOTES_DIR = os.path.join(os.path.expanduser("~"), "Documents", "멀티메모")
else:
    NOTES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notes")
TRASH_DIR = os.path.join(NOTES_DIR, "_삭제됨")
META_FILE = os.path.join(NOTES_DIR, "_meta.json")

# (배경색, 포인트색) - 아주 연한 파스텔 톤
COLORS = [
    ("#FFFCE3", "#F2E6A0"),  # 노랑
    ("#EEF9E8", "#C9E6B8"),  # 초록
    ("#FFF0F5", "#F2C9D8"),  # 분홍
    ("#F4F0FF", "#D6CCF2"),  # 보라
    ("#EDF6FF", "#C3DCF2"),  # 파랑
    ("#FAFAFA", "#DADADA"),  # 회색
]
BOARD_BG = "#EDEEF0"
RADIUS = 16   # 모서리 둥근 정도
INSET = 7     # 둥근 모서리 안쪽으로 내용 들여쓰기
UI_SCALE = 0.9           # 전체 글자 배율 (작게 하려면 낮추기)
MAC_SCALE = 1.4          # 맥 글자 배율 (맥 Tk는 1pt=1px이라 그대로 두면 너무 작음)
FONT_MIN, FONT_MAX = 5, 20
if IS_MAC:
    FONT_FAMILY = "Apple SD Gothic Neo"
    # 굵기: 이름 -> (후보 글꼴들, weight). 설치된 첫 번째 글꼴을 사용
    WEIGHT_SPECS = {
        "얇게": (["Apple SD Gothic Neo Light", "AppleSDGothicNeo-Light", "Apple SD Gothic Neo"], "normal"),
        "보통": (["Apple SD Gothic Neo"], "normal"),
        "굵게": (["Apple SD Gothic Neo"], "bold"),
    }
    MOD = "Command"
else:
    FONT_FAMILY = "맑은 고딕"
    WEIGHT_SPECS = {
        "얇게": (["맑은 고딕 Semilight"], "normal"),
        "보통": (["맑은 고딕"], "normal"),
        "굵게": (["맑은 고딕"], "bold"),
    }
    MOD = "Control"
WEIGHTS = {}  # Tk 시작 후 resolve_fonts()가 채움


def resolve_fonts():
    installed = set(tkfont.families())
    for name, (cands, wt) in WEIGHT_SPECS.items():
        fam = next((c for c in cands if c in installed), FONT_FAMILY)
        WEIGHTS[name] = (fam, wt)
SAVE_DELAY_MS = 500


def load_meta():
    try:
        with open(META_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"order": [], "notes": {}, "font_size": 11, "font_weight": "보통", "geometry": "1200x800"}


def rounded_rect(canvas, x1, y1, x2, y2, r, **kw):
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(pts, smooth=True, **kw)


class Note:
    def __init__(self, app, note_id, title="", color=0):
        self.app = app
        self.id = note_id
        self.color = color
        self._save_job = None

        bg, accent = COLORS[color]
        # 둥근 배경은 Canvas에 그리고, 실제 내용은 그 안쪽에 배치
        self.frame = tk.Canvas(app.board, bg=BOARD_BG, highlightthickness=0, bd=0,
                               width=50, height=50)
        self.frame.bind("<Configure>", self._redraw)

        self.inner = tk.Frame(self.frame, bg=bg)
        self.inner.place(x=INSET, y=INSET, relwidth=1, relheight=1,
                         width=-2 * INSET, height=-2 * INSET - 2)

        self.header = tk.Frame(self.inner, bg=bg)
        self.header.pack(fill="x")

        self.title_var = tk.StringVar(value=title)
        self.title_entry = tk.Entry(self.header, textvariable=self.title_var, bd=0,
                                    bg=bg, fg="#444", font=(FONT_FAMILY, 10, "bold"),
                                    relief="flat", highlightthickness=0)
        self.title_entry.pack(side="left", fill="x", expand=True, padx=(6, 4), pady=4)
        self.title_var.trace_add("write", lambda *_: self.schedule_save())

        self.btn_del = self._header_button("✕", self.delete, "메모 삭제")
        self.btn_color = self._header_button("●", self.next_color, "색 바꾸기")
        self.btn_color.config(fg=accent)
        self.btn_new = self._header_button("＋", app.add_note, "새 메모")

        self.sep = tk.Frame(self.inner, bg=accent, height=1)
        self.sep.pack(fill="x", padx=4)

        self.text = tk.Text(self.inner, wrap="word", bd=0, bg=bg, padx=8, pady=8,
                            font=app.body_font, undo=True,
                            relief="flat", insertbackground="#333", fg="#333",
                            highlightthickness=0)
        self.text.pack(fill="both", expand=True)
        self.text.bind("<<Modified>>", self._on_modified)
        self.text.bind(f"<{MOD}-MouseWheel>", app.on_zoom)

        self.status = tk.Label(self.inner, text="", bg=bg, fg="#AAA",
                               font=(FONT_FAMILY, 8), anchor="e")
        self.status.pack(fill="x")

    def _redraw(self, _event=None):
        c = self.frame
        c.delete("bg")
        w, h = c.winfo_width(), c.winfo_height()
        bg, accent = COLORS[self.color]
        # 살짝 그림자 + 둥근 메모 본체
        rounded_rect(c, 2, 3, w - 1, h - 1, RADIUS, fill="#DCDDE0", outline="", tags="bg")
        rounded_rect(c, 0, 0, w - 3, h - 4, RADIUS, fill=bg, outline=accent, tags="bg")
        c.tag_lower("bg")

    def _header_button(self, label, cmd, tip):
        bg, _ = COLORS[self.color]
        b = tk.Label(self.header, text=label, bg=bg, fg="#999", cursor="hand2",
                     font=(FONT_FAMILY, 10), padx=5)
        b.pack(side="right")
        normal = lambda: COLORS[self.color][1] if b is getattr(self, "btn_color", None) else "#999"
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: (b.config(fg="#333"), self.app.show_tip(tip)))
        b.bind("<Leave>", lambda e: (b.config(fg=normal()), self.app.show_tip("")))
        return b

    @property
    def path(self):
        return os.path.join(NOTES_DIR, f"{self.id}.txt")

    def load_text(self):
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                self.text.insert("1.0", f.read())
        self.text.edit_modified(False)
        self.text.edit_reset()

    def _on_modified(self, _event):
        if self.text.edit_modified():
            self.text.edit_modified(False)
            self.schedule_save()

    def schedule_save(self):
        if self._save_job:
            self.app.root.after_cancel(self._save_job)
        self.status.config(text="입력 중…")
        self._save_job = self.app.root.after(SAVE_DELAY_MS, self.save)

    def save(self):
        self._save_job = None
        content = self.text.get("1.0", "end-1c")
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(content)
        self.app.save_meta()
        self.status.config(text=f"저장됨 {time.strftime('%H:%M:%S')}")

    def flush(self):
        if self._save_job:
            self.app.root.after_cancel(self._save_job)
            self.save()

    def next_color(self):
        self.color = (self.color + 1) % len(COLORS)
        bg, accent = COLORS[self.color]
        for w in (self.inner, self.header, self.title_entry, self.btn_del,
                  self.btn_color, self.btn_new, self.text, self.status):
            w.config(bg=bg)
        self.btn_color.config(fg=accent)
        self.sep.config(bg=accent)
        self._redraw()
        self.app.save_meta()

    def delete(self):
        content = self.text.get("1.0", "end-1c").strip()
        name = self.title_var.get() or "이 메모"
        if content and not messagebox.askyesno("메모 삭제", f"'{name}'를 삭제할까요?\n(_삭제됨 폴더로 옮겨집니다)"):
            return
        self.flush()
        if os.path.exists(self.path):
            os.makedirs(TRASH_DIR, exist_ok=True)
            stamp = time.strftime("%Y%m%d_%H%M%S")
            shutil.move(self.path, os.path.join(TRASH_DIR, f"{self.id}_{stamp}.txt"))
        self.app.remove_note(self)


class App:
    def __init__(self):
        os.makedirs(NOTES_DIR, exist_ok=True)
        meta = load_meta()
        self.font_size = max(FONT_MIN, min(FONT_MAX, meta.get("font_size", 11)))
        self.font_weight = meta.get("font_weight", "보통")
        if self.font_weight not in WEIGHT_SPECS:
            self.font_weight = "보통"

        # 고해상도(DPI) 인식: 윈도우가 흐리게 확대하지 않고 선명하게 그리도록
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            pass
        self.root = tk.Tk()
        if IS_MAC:
            self.root.tk.call("tk", "scaling", MAC_SCALE)
        else:
            dpi = self.root.winfo_fpixels("1i")
            self.root.tk.call("tk", "scaling", dpi / 72 * UI_SCALE)
        resolve_fonts()
        family, weight = WEIGHTS[self.font_weight]
        self.body_font = tkfont.Font(family=family, size=self.font_size, weight=weight)
        self.root.title("멀티 메모")
        self.root.geometry(meta.get("geometry", "1200x800"))
        self.root.configure(bg=BOARD_BG)
        self.root.minsize(400, 300)

        bar = tk.Frame(self.root, bg=BOARD_BG)
        bar.pack(fill="x", padx=8, pady=(6, 0))
        # 맥은 tk.Button 배경색이 적용되지 않아 Label로 버튼을 만듦
        self._small_button(bar, "＋ 새 메모 (⌘N)" if IS_MAC else "＋ 새 메모 (Ctrl+N)",
                           self.add_note, side="left", padx=10, pady=4)
        self._small_button(bar, "저장 폴더 열기", self.open_folder, side="left",
                           padx=10, pady=4).pack_configure(padx=6)
        # 글자 크기 / 굵기 조절
        self.weight_btns = {}
        for name in reversed(list(WEIGHTS)):
            fam, wt = WEIGHTS[name]
            b = tk.Label(bar, text=name, font=(fam, 9, wt), padx=8, pady=2, cursor="hand2")
            b.pack(side="right", padx=(0, 1))
            b.bind("<Button-1>", lambda e, n=name: self.set_font_weight(n))
            self.weight_btns[name] = b
        tk.Label(bar, text="굵기", bg=BOARD_BG, fg="#666",
                 font=(FONT_FAMILY, 9)).pack(side="right", padx=(14, 4))
        self._small_button(bar, "＋", lambda: self.set_font_size(self.font_size + 1))
        self.size_label = tk.Label(bar, text="", bg="#FFFFFF", fg="#333", width=5,
                                   font=(FONT_FAMILY, 9), pady=2)
        self.size_label.pack(side="right")
        self._small_button(bar, "－", lambda: self.set_font_size(self.font_size - 1))
        tk.Label(bar, text="글자 크기", bg=BOARD_BG, fg="#666",
                 font=(FONT_FAMILY, 9)).pack(side="right", padx=(14, 4))
        self._refresh_font_controls()

        self.tip = tk.Label(bar, text="", bg=BOARD_BG, fg="#777", font=(FONT_FAMILY, 9))
        self.tip.pack(side="left", padx=8)
        self.count_label = tk.Label(bar, text="", bg=BOARD_BG, fg="#555",
                                    font=(FONT_FAMILY, 9))
        self.count_label.pack(side="right", padx=(0, 6))

        self.board = tk.Frame(self.root, bg=BOARD_BG)
        self.board.pack(fill="both", expand=True, padx=6, pady=6)

        self.notes = []
        notes_meta = meta.get("notes", {})
        order = [i for i in meta.get("order", []) if i in notes_meta or
                 os.path.exists(os.path.join(NOTES_DIR, f"{i}.txt"))]
        # meta에 없지만 폴더에 있는 txt 파일도 불러오기
        for fn in sorted(os.listdir(NOTES_DIR)):
            nid, ext = os.path.splitext(fn)
            if ext == ".txt" and nid not in order:
                order.append(nid)
        for nid in order:
            m = notes_meta.get(nid, {})
            note = Note(self, nid, m.get("title", ""), m.get("color", 0) % len(COLORS))
            note.load_text()
            self.notes.append(note)
        if not self.notes:
            self.add_note()
        else:
            self.relayout()

        self.root.bind_all(f"<{MOD}-n>", lambda e: self.add_note())
        self.root.bind_all(f"<{MOD}-N>", lambda e: self.add_note())
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def open_folder(self):
        if IS_MAC:
            subprocess.Popen(["open", NOTES_DIR])
        else:
            os.startfile(NOTES_DIR)

    def _small_button(self, parent, text, cmd, side="right", padx=7, pady=2):
        b = tk.Label(parent, text=text, bg="#FFFFFF", fg="#555", font=(FONT_FAMILY, 9),
                     padx=padx, pady=pady, cursor="hand2")
        b.pack(side=side, padx=1)
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: b.config(bg="#E6E9EE"))
        b.bind("<Leave>", lambda e: b.config(bg="#FFFFFF"))
        return b

    def _refresh_font_controls(self):
        self.size_label.config(text=f"{self.font_size}pt")
        for name, b in self.weight_btns.items():
            on = name == self.font_weight
            b.config(bg="#FFFFFF" if on else "#E2E4E8", fg="#222" if on else "#888")

    def set_font_size(self, size):
        self.font_size = max(FONT_MIN, min(FONT_MAX, size))
        self.body_font.config(size=self.font_size)
        self._refresh_font_controls()
        self.save_meta()

    def set_font_weight(self, name):
        self.font_weight = name
        family, weight = WEIGHTS[name]
        self.body_font.config(family=family, weight=weight)
        self._refresh_font_controls()
        self.save_meta()

    def show_tip(self, text):
        self.tip.config(text=text)

    def add_note(self):
        nid = time.strftime("memo_%Y%m%d_%H%M%S")
        existing = {n.id for n in self.notes}
        base, k = nid, 1
        while nid in existing or os.path.exists(os.path.join(NOTES_DIR, f"{nid}.txt")):
            nid, k = f"{base}_{k}", k + 1
        color = len(self.notes) % len(COLORS)
        note = Note(self, nid, f"메모 {len(self.notes) + 1}", color)
        self.notes.append(note)
        note.save()
        self.relayout()
        note.text.focus_set()
        return "break"

    def remove_note(self, note):
        self.notes.remove(note)
        note.frame.destroy()
        self.save_meta()
        if not self.notes:
            self.add_note()
        else:
            self.relayout()

    def relayout(self):
        """메모 개수에 맞춰 격자를 다시 계산해서 화면을 균등 분할."""
        n = len(self.notes)
        w, h = max(self.board.winfo_width(), 1), max(self.board.winfo_height(), 1)
        # 화면이 가로로 넓으면 열을 더 많이 (메모 한 칸이 살짝 가로로 긴 비율이 되도록)
        ratio = w / h if w > 1 and h > 1 else 1.5
        cols = min(n, max(1, round(math.sqrt(n * ratio / 1.2))))
        rows = math.ceil(n / cols)

        for c in range(12):
            self.board.columnconfigure(c, weight=0, uniform="")
        for r in range(12):
            self.board.rowconfigure(r, weight=0, uniform="")
        for c in range(cols):
            self.board.columnconfigure(c, weight=1, uniform="col")
        for r in range(rows):
            self.board.rowconfigure(r, weight=1, uniform="row")

        for i, note in enumerate(self.notes):
            r, c = divmod(i, cols)
            # 마지막 줄이 비면 남은 메모가 가로로 늘어나도록
            span = 1
            if r == rows - 1 and i == n - 1:
                span = cols - c
            note.frame.grid(row=r, column=c, columnspan=span, sticky="nsew", padx=5, pady=5)
        self.count_label.config(text=f"메모 {n}개")

    def on_zoom(self, event):
        self.set_font_size(self.font_size + (1 if event.delta > 0 else -1))
        return "break"

    def save_meta(self):
        meta = {
            "order": [n.id for n in self.notes],
            "notes": {n.id: {"title": n.title_var.get(), "color": n.color} for n in self.notes},
            "font_size": self.font_size,
            "font_weight": self.font_weight,
            "geometry": self.root.geometry(),
        }
        tmp = META_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        os.replace(tmp, META_FILE)

    def on_close(self):
        for n in self.notes:
            n.flush()
        self.save_meta()
        self.root.destroy()

    def run(self):
        self.root.after(100, self.relayout)
        self._last_size = None
        self.board.bind("<Configure>", self._on_resize)
        self.root.mainloop()

    def _on_resize(self, event):
        size = (event.width, event.height)
        if size != self._last_size:
            self._last_size = size
            self.relayout()


if __name__ == "__main__":
    App().run()
