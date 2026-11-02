"""Простой редактор карт DEAD ROOMS. Запуск: python map_editor.py"""
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAP_DIR = ROOT / "data" / "maps"
MAP_CONFIG = ROOT / "data" / "maps.json"
BOSS_CONFIG = ROOT / "assets" / "boss" / "boss.json"
W, H, CELL = 50, 50, 16
MORGART_MARKER = "C"   # символ карты, который ставит Моргарта; другие боссы получат свои маркеры и панели
TILE = 32            # размер клетки в игре (пикселей) — нужен для перевода смещений рук
HEAD_DEFAULT = [0.50, 0.20]
# Запасные значения, если в assets/boss/boss.json нет блока "hands" (те же, что в boss_hands.py).
FALLBACK_SLOTS = {
    "upper_left": {"offset": [-11.0, -1.5], "hp": 260, "pattern": "grabber"},
    "lower_left": {"offset": [-11.0, 2.0], "hp": 220, "pattern": "sweeper"},
    "upper_right": {"offset": [11.0, -1.5], "hp": 260, "pattern": "slammer"},
    "lower_right": {"offset": [11.0, 2.0], "hp": 220, "pattern": "hunter"},
}
FALLBACK_PATTERNS = ["grabber", "sweeper", "slammer", "hunter"]
SLOT_TITLES = {"upper_left": "Верхняя левая", "lower_left": "Нижняя левая", "upper_right": "Верхняя правая", "lower_right": "Нижняя правая"}
SLOT_COLORS = {"upper_left": "#69e9ff", "lower_left": "#5aa8ff", "upper_right": "#ff75df", "lower_right": "#ff9a5a"}


def load_boss_hands():
    """(слоты рук, названия паттернов, размер руки в пикселях игры) из assets/boss/boss.json."""
    try:
        cfg = json.loads(BOSS_CONFIG.read_text(encoding="utf-8")).get("hands", {})
    except (OSError, ValueError):
        cfg = {}
    slots = cfg.get("slots") or FALLBACK_SLOTS
    patterns = list(cfg.get("patterns") or FALLBACK_PATTERNS)
    size = cfg.get("size") or [190, 132]
    return slots, patterns, size

# Символ -> название и запись легенды. Варианты используют отдельные символы,
# поэтому можно рисовать разные текстуры в пределах одной карты.
PALETTE = [
    (".", "Ластик / пусто", {"type": "empty"}),
    ("#", "Стена", {"type": "wall"}),
    ("=", "Платформа (авто)", {"type": "platform"}),
    ("1", "Платформа 1", {"type": "platform", "sprite": "environment/platform_1.png"}),
    ("2", "Платформа 2", {"type": "platform", "sprite": "environment/platform_2.png"}),
    ("3", "Платформа 3", {"type": "platform", "sprite": "environment/platform_3.png"}),
    ("4", "Платформа 4", {"type": "platform", "sprite": "environment/platform_4.png"}),
    ("5", "Платформа 5", {"type": "platform", "sprite": "environment/platform_5.png"}),
    ("a", "Стена 1", {"type": "wall", "sprite": "environment/wall_1.png"}),
    ("b", "Стена 2", {"type": "wall", "sprite": "environment/wall_2.png"}),
    ("c", "Стена 3", {"type": "wall", "sprite": "environment/wall_3.png"}),
    ("H", "Лестница (авто)", {"type": "ladder"}),
    ("i", "Лестница 1", {"type": "ladder", "sprite": "environment/ladder_1.png"}),
    ("j", "Лестница 2", {"type": "ladder", "sprite": "environment/ladder_2.png"}),
    ("k", "Лестница 3", {"type": "ladder", "sprite": "environment/ladder_3.png"}),
    ("x", "Шипы (авто)", {"type": "spikes", "damage": 10}),
    ("u", "Шипы 1", {"type": "spikes", "damage": 10, "sprite": "environment/spikes_1.png"}),
    ("v", "Шипы 2", {"type": "spikes", "damage": 10, "sprite": "environment/spikes_2.png"}),
    ("w", "Шипы 3", {"type": "spikes", "damage": 10, "sprite": "environment/spikes_3.png"}),
    ("P", "Старт игрока", {"type": "empty", "player": True}),
    ("S", "Случайный моб", {"type": "empty", "mob": "random"}),
    ("B", "Моргарт (точка появления)", {"type": "empty", "boss": True}),
    ("C", "Моргарт (точка появления)", {"type": "empty", "boss": True, "boss_type": "morgart"}),
    ("?", "Случайное оружие", {"type": "empty", "item": "random"}),
    ("<", "Выход назад", {"type": "empty", "exit": "prev"}),
    (">", "Выход дальше", {"type": "empty", "exit": "next"}),
    ("L", "Выход влево", {"type": "empty", "exit": "left"}),
    ("R", "Выход вправо", {"type": "empty", "exit": "right"}),
    ("U", "Выход вверх", {"type": "ladder", "exit": "up"}),
    ("D", "Выход вниз", {"type": "ladder", "exit": "down"}),
    ("*", "Свет: факел", {"type": "empty", "light": "torch"}),
    ("o", "Свет: фонарь", {"type": "empty", "light": "lantern"}),
    ("+", "Свет: кристалл", {"type": "empty", "light": "crystal"}),
    ("%", "Свет: магическая сфера", {"type": "empty", "light": "orb"}),
]
# Эти символы уже есть в общей легенде data/maps.json — в легенду карты их не копируем.
GLOBAL_SYMBOLS = (".", "#", "=", "H", "x", "<", ">", "L", "R", "U", "D", "P", "S", "B", "C", "?", "*", "o", "+", "%")
LEGEND = {ch: data for ch, _, data in PALETTE if ch not in GLOBAL_SYMBOLS}
LEGEND.update({".": "empty", "#": "wall", "=": "platform", "H": "ladder", "x": {"type": "spikes", "damage": 10},
               "<": {"exit": "prev"}, ">": {"exit": "next"}, "L": {"exit": "left"}, "R": {"exit": "right"},
               "U": {"exit": "up", "type": "ladder"}, "D": {"exit": "down", "type": "ladder"},
               "P": {"player": True}, "S": {"mob": "random"}, "B": {"boss": True}, "C": {"type": "empty", "boss": True, "boss_type": "morgart"}, "?": {"item": "random"},
               "*": {"light": "torch"}, "o": {"light": "lantern"}, "+": {"light": "crystal"}, "%": {"light": "orb"}})

COLORS = {".": "#20202a", "#": "#85858c", "=": "#b08a5a", "H": "#c6a66b", "x": "#d94a4a",
          "P": "#62d6ff", "S": "#d58bff", "B": "#ff5368", "C": "#bd58ff", "?": "#f5d75e", "<": "#8bd49b", ">": "#8bd49b",
          "L": "#8bd49b", "R": "#8bd49b", "U": "#8bd49b", "D": "#8bd49b",
          "*": "#ff9a3c", "o": "#ffd99a", "+": "#6fd2ff", "%": "#be6eff"}
for ch, _, data in PALETTE:
    if "sprite" in data:
        typ = data["type"]
        COLORS[ch] = {"platform": "#b08a5a", "wall": "#85858c", "ladder": "#c6a66b", "spikes": "#d94a4a"}[typ]

# ---- Свой свет: вид, цвет, сила. Каждому сочетанию редактор сам выдаёт символ и пишет его в легенду карты. ----
LIGHT_KINDS = [("Факел", "torch"), ("Фонарь", "lantern"), ("Кристалл", "crystal"), ("Сфера", "orb"), ("Невидимый свет", "glow")]
LIGHT_COLORS = [("тёплый", [255, 150, 60]), ("белый", [255, 244, 228]), ("красный", [255, 60, 45]), ("оранжевый", [255, 120, 30]),
                ("жёлтый", [255, 220, 80]), ("зелёный", [90, 255, 110]), ("голубой", [90, 225, 255]), ("синий", [70, 120, 255]),
                ("фиолетовый", [185, 95, 255]), ("розовый", [255, 110, 200])]
STRENGTH_NAMES = {1: "слабый", 2: "тусклый", 3: "обычный", 4: "яркий", 5: "очень яркий"}
LIGHT_BRUSH = "__light__"
# Символы для своих источников света (любые буквы, которые не заняты на карте).
SYMBOL_POOL = "АБВГДЕЖЗИЙКЛМНПРСТУФЦЧШЩЭЮЯабвгдежзийклмнпрстуфцчшщэюяΔΘΛΞΠΣΦΨΩαβγδεζηθλμξπσφψω"


def hex_color(c):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(v))) for v in c[:3])


def light_color(light):
    """Цвет записи света для показа в редакторе."""
    c = light.get("color") if isinstance(light, dict) else None
    if isinstance(c, list) and len(c) >= 3: return c
    if isinstance(c, str):
        names = dict(LIGHT_COLORS); names.update({"warm": [255, 150, 60], "white": [255, 244, 228], "red": [255, 60, 45],
                                                  "green": [90, 255, 110], "blue": [70, 120, 255], "purple": [185, 95, 255]})
        return names.get(c.lower(), [255, 220, 160])
    return [255, 220, 160]


def describe_light(definition):
    li = definition.get("light", {}) if isinstance(definition, dict) else {}
    if not isinstance(li, dict): return f"Свет: {li}"
    kind = dict((b, a) for a, b in LIGHT_KINDS).get(li.get("preset"), li.get("preset", "свет"))
    return f"Свет: {kind}, сила {li.get('strength', 3)} ({STRENGTH_NAMES.get(li.get('strength', 3), '')}), цвет {light_color(li)}"


class Editor:
    def __init__(self, root):
        self.root = root
        root.title("DEAD ROOMS — редактор карт")
        root.geometry("1100x820")
        self.map_w, self.map_h = W, H
        self.rows = [["." for _ in range(self.map_w)] for _ in range(self.map_h)]
        self.meta = {"name": "Новая карта", "pos": [0, 0], "fill": "."}
        self.current_path = None
        self.brush = tk.StringVar(value="#")
        self.map_id = tk.StringVar(value="my_map")
        self.name = tk.StringVar(value="Новая карта")
        self.status = tk.StringVar(value="Выбери элемент слева и рисуй мышью. Колесо мыши прокручивает карту.")
        self.rects = {}
        self.custom = {}   # символ -> запись легенды своего света
        self.light_kind = tk.StringVar(value=LIGHT_KINDS[0][0])
        self.light_rgb = list(LIGHT_COLORS[0][1])
        self.light_strength = tk.IntVar(value=3)
        self.sprite_images = {}
        self.background_images = {}
        self.background = tk.StringVar(value="Без фона")
        self.slots, self.patterns, self.hand_size = load_boss_hands()
        self.morg_mode = tk.BooleanVar(value=False)       # ЛКМ двигает метки Моргарта вместо рисования клеток
        self.morg_part = tk.StringVar(value="head")       # какая часть выбрана: head или id руки
        self.morg_on = {sid: tk.BooleanVar(value=True) for sid in self.slots}
        self.morg_hp = {sid: tk.StringVar(value=str(d.get("hp", ""))) for sid, d in self.slots.items()}
        self.morg_pat = {sid: tk.StringVar(value=str(d.get("pattern", ""))) for sid, d in self.slots.items()}
        self.morg_offset = {sid: list(d.get("offset", [0, 0])) for sid, d in self.slots.items()}   # клетки от головы
        self.morg_head = None      # [x, y] 0..1 или None (голова по маркеру C/B либо по умолчанию)
        self.morg_touched = False
        self._load_preview_images()
        self._ui(); self._draw_all()

    def _ui(self):
        outer = ttk.Frame(self.root, padding=8); outer.pack(fill="both", expand=True)
        left = ttk.Frame(outer); left.pack(side="left", fill="y")
        ttk.Label(left, text="Элементы окружения", font=("Arial", 12, "bold")).pack(anchor="w", pady=(0, 6))
        self._light_panel(left)
        palette_canvas = tk.Canvas(left, width=250, height=430, highlightthickness=0)
        palette_scroll = ttk.Scrollbar(left, orient="vertical", command=palette_canvas.yview)
        palette_canvas.configure(yscrollcommand=palette_scroll.set)
        palette_scroll.pack(side="right", fill="y"); palette_canvas.pack(side="left", fill="y")
        palette_frame = ttk.Frame(palette_canvas); palette_canvas.create_window((0, 0), window=palette_frame, anchor="nw")
        palette_frame.bind("<Configure>", lambda e: palette_canvas.configure(scrollregion=palette_canvas.bbox("all")))
        for ch, label, _ in PALETTE:
            b = ttk.Radiobutton(palette_frame, text=f" {ch}  {label}", value=ch, variable=self.brush)
            b.pack(anchor="w", fill="x", pady=1)
        right = ttk.Frame(outer); right.pack(side="left", fill="both", expand=True, padx=(12, 0))
        bar = ttk.Frame(right); bar.pack(fill="x", pady=(0, 8))
        ttk.Label(bar, text="ID карты:").pack(side="left")
        ttk.Entry(bar, textvariable=self.map_id, width=14).pack(side="left", padx=4)
        ttk.Label(bar, text="Название:").pack(side="left", padx=(8, 0))
        ttk.Entry(bar, textvariable=self.name, width=18).pack(side="left", padx=4)
        ttk.Button(bar, text="Открыть карту…", command=self.open_map).pack(side="left", padx=4)
        ttk.Button(bar, text="Сохранить в data/maps", command=self.save_map).pack(side="left", padx=4)
        ttk.Button(bar, text="Очистить", command=self.clear).pack(side="left", padx=4)
        ttk.Label(bar, text="Размер (клетки):").pack(side="left", padx=(8, 2))
        self.width_var = tk.StringVar(value=str(self.map_w))
        self.height_var = tk.StringVar(value=str(self.map_h))
        ttk.Spinbox(bar, from_=5, to=300, increment=1, textvariable=self.width_var, width=5).pack(side="left", padx=2)
        ttk.Label(bar, text="×").pack(side="left")
        ttk.Spinbox(bar, from_=5, to=300, increment=1, textvariable=self.height_var, width=5).pack(side="left", padx=2)
        ttk.Button(bar, text="Применить", command=self.resize_map).pack(side="left", padx=3)
        ttk.Label(bar, text="Фон:").pack(side="left", padx=(10, 2))
        self.bg_combo = ttk.Combobox(bar, textvariable=self.background, width=14, state="readonly",
                                     values=["Без фона", "Руины", "Пещера", "Склеп", "Кирпичная плитка"])
        self.bg_combo.pack(side="left", padx=2)
        self.bg_combo.bind("<<ComboboxSelected>>", self._background_changed)
        bar2 = ttk.Frame(right); bar2.pack(fill="x", pady=(0, 8))
        ttk.Label(bar2, text="Темнота карты, %:").pack(side="left")
        self.darkness_var = tk.StringVar(value="")
        ttk.Spinbox(bar2, from_=0, to=100, increment=5, textvariable=self.darkness_var, width=5).pack(side="left", padx=4)
        ttk.Label(bar2, text="пусто — авто: темно, только если на карте есть блоки света (* факел, o фонарь, + кристалл, % сфера); 0 — светло").pack(side="left", padx=6)
        board = ttk.Frame(right); board.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(board, width=800, height=520, bg="#15151b", scrollregion=(0, 0, self.map_w*CELL, self.map_h*CELL), highlightthickness=0)
        sx = ttk.Scrollbar(board, orient="horizontal", command=self.canvas.xview); sy = ttk.Scrollbar(board, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=sx.set, yscrollcommand=sy.set)
        self.canvas.grid(row=0, column=0, sticky="nsew"); sy.grid(row=0, column=1, sticky="ns"); sx.grid(row=1, column=0, sticky="ew")
        board.rowconfigure(0, weight=1); board.columnconfigure(0, weight=1)
        self.canvas.bind("<Button-1>", self.paint); self.canvas.bind("<B1-Motion>", self.paint)
        self.canvas.bind("<Button-3>", self.erase)
        ttk.Label(right, textvariable=self.status, wraplength=800).pack(fill="x", pady=(8, 0))
        ttk.Label(right, text="Размер сетки настраивается сверху (от 5×5 до 300×300 клеток). ЛКМ — рисовать, ПКМ — стереть. Разные варианты платформ/стен/лестниц/шипов выбираются в палитре.").pack(anchor="w", pady=(4, 0))
        self._morgart_panel(right)

    def _morgart_panel(self, parent):
        box = ttk.LabelFrame(parent, text="Моргарт: голова и руки (положение рук — относительно головы)", padding=5)
        self.morg_box = box; self.morg_shown = False     # панель видна, только пока на карте стоит маркер Моргарта (C)
        top = ttk.Frame(box); top.pack(fill="x")
        ttk.Checkbutton(top, text="Режим Моргарта: ЛКМ двигает выбранную метку (клетки не рисуются)", variable=self.morg_mode,
                        command=self._morg_mode_changed).pack(side="left")
        ttk.Button(top, text="Сбросить всё", command=self.reset_morgart_layout).pack(side="right")
        grid = ttk.Frame(box); grid.pack(fill="x", pady=(4, 0))
        for col, text in enumerate(("Метка", "Есть", "HP", "Паттерн", "Смещение от головы")):
            ttk.Label(grid, text=text, font=("Arial", 8, "bold")).grid(row=0, column=col, padx=4, sticky="w")
        ttk.Radiobutton(grid, text="ГОЛОВА", value="head", variable=self.morg_part).grid(row=1, column=0, sticky="w", padx=4)
        self.head_info = tk.StringVar(value="")
        ttk.Label(grid, textvariable=self.head_info).grid(row=1, column=4, sticky="w", padx=4)
        for i, sid in enumerate(self.slots):
            row = i + 2
            ttk.Radiobutton(grid, text=SLOT_TITLES.get(sid, sid), value=sid, variable=self.morg_part).grid(row=row, column=0, sticky="w", padx=4)
            ttk.Checkbutton(grid, variable=self.morg_on[sid], command=self._morg_changed).grid(row=row, column=1)
            hp = ttk.Entry(grid, textvariable=self.morg_hp[sid], width=6); hp.grid(row=row, column=2, padx=4)
            hp.bind("<FocusOut>", lambda e: self._morg_changed()); hp.bind("<Return>", lambda e: self._morg_changed())
            cb = ttk.Combobox(grid, textvariable=self.morg_pat[sid], width=10, state="readonly", values=self.patterns)
            cb.grid(row=row, column=3, padx=4); cb.bind("<<ComboboxSelected>>", lambda e: self._morg_changed())
        self.off_vars = {sid: tk.StringVar(value="") for sid in self.slots}
        for i, sid in enumerate(self.slots):
            ttk.Label(grid, textvariable=self.off_vars[sid]).grid(row=i + 2, column=4, sticky="w", padx=4)
        ttk.Label(box, text="Включи режим, выбери часть и щёлкни/перетащи по карте. Если сдвинуть голову, руки поедут с ней. "
                            "Пока жива хоть одна рука, голова неуязвима; уровень проходится убийством головы.",
                  wraplength=780).pack(anchor="w", pady=(4, 0))
        self._morg_refresh_info()


    def _load_preview_images(self):
        """Load tiny environment sprites as native Tk previews (no Pillow dependency)."""
        for ch, _, definition in PALETTE:
            rel = definition.get("sprite")
            if not rel:
                continue
            path = ROOT / "assets" / rel
            try:
                img = tk.PhotoImage(file=str(path))
                if img.width() != CELL or img.height() != CELL:
                    img = img.subsample(max(1, img.width() // CELL), max(1, img.height() // CELL))
                self.sprite_images[ch] = img
            except tk.TclError:
                pass
        bg_files = {"Руины": "ruins.png", "Пещера": "cave.png", "Склеп": "crypt.png", "Кирпичная плитка": "bricks_tile.png"}
        for label, filename in bg_files.items():
            try:
                self.background_images[label] = tk.PhotoImage(file=str(ROOT / "assets" / "backgrounds" / filename))
            except tk.TclError:
                pass

    def _background_changed(self, _event=None):
        self._draw_all()

    def _draw_all(self):
        self._morg_sync_panel()
        self.canvas.delete("all"); self.rects = {}
        bg = self.background.get()
        bg_img = self.background_images.get(bg)
        if bg_img:
            if bg == "Кирпичная плитка":
                for by in range(0, self.map_h * CELL, bg_img.height()):
                    for bx in range(0, self.map_w * CELL, bg_img.width()):
                        self.canvas.create_image(bx, by, image=bg_img, anchor="nw", tags=("background",))
            else:
                self.canvas.create_image((self.map_w * CELL - bg_img.width()) // 2,
                                         (self.map_h * CELL - bg_img.height()) // 2,
                                         image=bg_img, anchor="nw", tags=("background",))
        for y, row in enumerate(self.rows):
            for x, ch in enumerate(row):
                self._draw_cell(x, y, ch)
        self.canvas.tag_lower("background")
        self._draw_morgart_anchors()

    # ---------- Моргарт ----------
    def _boss_marker(self):
        """Центр первой клетки C — маркера Моргарта (первая по строкам, как в игре) в клетках карты или None."""
        for y, row in enumerate(self.rows):
            for x, ch in enumerate(row):
                if ch == MORGART_MARKER: return x + 0.5, y + 0.5
        return None

    def _morg_sync_panel(self):
        """Показывает панель Моргарта только если на карте есть его маркер; без маркера прячет и выключает режим."""
        has = self._boss_marker() is not None
        if has and not self.morg_shown:
            self.morg_box.pack(fill="x", pady=(6, 0)); self.morg_shown = True
        elif not has and self.morg_shown:
            self.morg_box.pack_forget(); self.morg_shown = False
            if self.morg_mode.get(): self.morg_mode.set(False); self.status.set("Маркер Моргарта убран — режим Моргарта выключен.")

    def _head_cells(self):
        """Центр головы в клетках карты: якорь > маркер C/B > стандартное место (та же логика, что в игре)."""
        if self.morg_head: return self.morg_head[0] * self.map_w, self.morg_head[1] * self.map_h
        marker = self._boss_marker()
        if marker: return marker
        return HEAD_DEFAULT[0] * self.map_w, HEAD_DEFAULT[1] * self.map_h

    def _morg_visible(self):
        return self._boss_marker() is not None      # нет маркера C — на карте ничего про Моргарта не рисуем

    def _hand_cells(self, sid):
        hx, hy = self._head_cells(); dx, dy = self.morg_offset[sid]
        return hx + dx, hy + dy      # смещение хранится в клетках, как и карта

    def _draw_morgart_anchors(self):
        if not self._morg_visible(): return
        px = CELL / TILE
        hx, hy = self._head_cells(); hx, hy = hx * CELL, hy * CELL
        sel = self.morg_part.get()
        for sid in self.slots:
            if not self.morg_on[sid].get(): continue
            cx, cy = (v * CELL for v in self._hand_cells(sid)); col = SLOT_COLORS.get(sid, "#ffffff")
            bw, bh = self.hand_size[0] * px, self.hand_size[1] * px
            self.canvas.create_line(hx, hy, cx, cy, fill=col, dash=(3, 3), tags=("morgart_anchor",))
            self.canvas.create_rectangle(cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2, outline=col, width=3 if sel == sid else 1, tags=("morgart_anchor",))
            self.canvas.create_oval(cx - 4, cy - 4, cx + 4, cy + 4, fill=col, outline="", tags=("morgart_anchor",))
            label = f"{SLOT_TITLES.get(sid, sid)}  HP {self.morg_hp[sid].get() or '—'}  [{self.morg_pat[sid].get() or '—'}]"
            self.canvas.create_text(cx - bw / 2, cy - bh / 2 - 2, text=label, fill=col, anchor="sw", font=("Arial", 8, "bold"), tags=("morgart_anchor",))
        col = "#fff36b"
        self.canvas.create_oval(hx - 14, hy - 14, hx + 14, hy + 14, outline=col, width=3 if sel == "head" else 2, tags=("morgart_anchor",))
        self.canvas.create_line(hx - 20, hy, hx + 20, hy, fill=col, width=2, tags=("morgart_anchor",))
        self.canvas.create_line(hx, hy - 20, hx, hy + 20, fill=col, width=2, tags=("morgart_anchor",))
        self.canvas.create_text(hx + 16, hy - 16, text="ГОЛОВА", fill=col, anchor="sw", font=("Arial", 9, "bold"), tags=("morgart_anchor",))

    def _morg_refresh_info(self):
        hx, hy = self._head_cells()
        src = "якорь карты" if self.morg_head else ("маркер B/C" if self._boss_marker() else "по умолчанию")
        self.head_info.set(f"клетка ({hx:.1f}; {hy:.1f}) — {src}")
        for sid in self.slots:
            dx, dy = self.morg_offset[sid]
            self.off_vars[sid].set(f"dx {dx:+.2f}, dy {dy:+.2f} клеток" + ("" if self.morg_on[sid].get() else "  (отключена)"))

    def _morg_changed(self):
        self.morg_touched = True; self._morg_refresh_info(); self._draw_all()

    def _morg_mode_changed(self):
        if self.morg_mode.get():
            self.status.set("Режим Моргарта: выбери часть справа (голова / рука) и щёлкни или перетащи по карте. Клетки не рисуются.")
        else:
            self.status.set("Режим рисования клеток.")
        self._draw_all()

    def _morg_pick_nearest(self, x, y):
        """Метка (голова или рука) ближе всего к точке (пиксели холста), если она в пределах ~40 px."""
        best, dist = None, 40.0
        hx, hy = (v * CELL for v in self._head_cells())
        cand = [("head", hx, hy)] + [(sid, *(v * CELL for v in self._hand_cells(sid))) for sid in self.slots if self.morg_on[sid].get()]
        for part, px_, py_ in cand:
            d = ((px_ - x) ** 2 + (py_ - y) ** 2) ** .5
            if d < dist: best, dist = part, d
        return best

    def morgart_click(self, event, press):
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        if press:
            near = self._morg_pick_nearest(x, y)
            if near: self.morg_part.set(near)
        part = self.morg_part.get()
        cx, cy = x / CELL, y / CELL                      # клетки карты
        cx = max(0.0, min(float(self.map_w), cx)); cy = max(0.0, min(float(self.map_h), cy))
        if part == "head":
            self.morg_head = [round(cx / self.map_w, 4), round(cy / self.map_h, 4)]
        elif part in self.slots:
            hx, hy = self._head_cells()
            self.morg_offset[part] = [round((cx - hx) * 4) / 4, round((cy - hy) * 4) / 4]
            self.morg_on[part].set(True)
        self.morg_touched = True; self._morg_refresh_info(); self._draw_all()
        label = "голова" if part == "head" else SLOT_TITLES.get(part, part)
        self.status.set(f"Моргарт: {label} — клетка ({cx:.1f}; {cy:.1f}). Сохрани карту, чтобы применить.")

    def reset_morgart_layout(self):
        self.morg_head = None; self.morg_touched = False; self.meta.pop("morgart_layout", None)
        for sid, d in self.slots.items():
            self.morg_on[sid].set(True); self.morg_hp[sid].set(str(d.get("hp", ""))); self.morg_pat[sid].set(str(d.get("pattern", "")))
            self.morg_offset[sid] = list(d.get("offset", [0, 0]))
        self._morg_refresh_info(); self._draw_all(); self.status.set("Раскладка Моргарта сброшена к стандартной.")

    def _morg_layout(self):
        """Запись morgart_layout для карты (смещения рук — в клетках от головы)."""
        layout = {"anchors": {}, "hands": {}}
        if self.morg_head: layout["anchors"]["head"] = list(self.morg_head)
        for sid in self.slots:
            entry = {"enabled": bool(self.morg_on[sid].get()), "offset": [round(float(v), 2) for v in self.morg_offset[sid]]}
            hp = self.morg_hp[sid].get().strip()
            if hp:
                try: entry["hp"] = max(1, int(float(hp)))
                except ValueError: pass
            if self.morg_pat[sid].get(): entry["pattern"] = self.morg_pat[sid].get()
            layout["hands"][sid] = entry
        return layout

    def _morg_load(self, layout):
        """Загрузить morgart_layout карты в панель (старый формат с двумя руками переводится в смещения)."""
        self.reset_morgart_layout()
        if not isinstance(layout, dict) or not layout: return
        anchors = layout.get("anchors", layout) if isinstance(layout.get("anchors", layout), dict) else {}
        head = anchors.get("head")
        if isinstance(head, list) and len(head) == 2: self.morg_head = [float(head[0]), float(head[1])]
        hands = layout.get("hands") if isinstance(layout.get("hands"), dict) else {}
        hx, hy = self._head_cells()
        for sid, d in self.slots.items():
            ov = hands.get(sid) if isinstance(hands.get(sid), dict) else None
            if ov is None:
                legacy = anchors.get("left_hand" if "left" in sid else "right_hand")
                if isinstance(legacy, list) and len(legacy) == 2 and not hands:
                    lower = 72.0 / TILE if sid.startswith("lower") else 0.0
                    self.morg_offset[sid] = [legacy[0] * self.map_w - hx, legacy[1] * self.map_h - hy + lower]
                continue
            self.morg_on[sid].set(ov.get("enabled", True) is not False)
            if isinstance(ov.get("offset"), list) and len(ov["offset"]) == 2: self.morg_offset[sid] = [float(ov["offset"][0]), float(ov["offset"][1])]
            if "hp" in ov: self.morg_hp[sid].set(str(ov["hp"]))
            if ov.get("pattern"): self.morg_pat[sid].set(str(ov["pattern"]))
        self.morg_touched = True; self._morg_refresh_info()

    def _light_panel(self, parent):
        """Панель «Свой свет»: вид светильника, цвет (готовый или любой), сила 1–5."""
        box = ttk.LabelFrame(parent, text="Свой свет (цвет и сила)", padding=6)
        box.pack(side="bottom", fill="x", pady=(8, 0))
        row = ttk.Frame(box); row.pack(fill="x")
        ttk.Label(row, text="Вид:").pack(side="left")
        kinds = ttk.Combobox(row, textvariable=self.light_kind, state="readonly", width=16, values=[a for a, _ in LIGHT_KINDS])
        kinds.pack(side="left", padx=4); kinds.bind("<<ComboboxSelected>>", lambda e: self._use_light())
        ttk.Label(box, text="Цвет:").pack(anchor="w", pady=(6, 2))
        sw = ttk.Frame(box); sw.pack(fill="x")
        for i, (name, rgb) in enumerate(LIGHT_COLORS):
            b = tk.Button(sw, bg=hex_color(rgb), activebackground=hex_color(rgb), width=2, relief="raised",
                          command=lambda c=rgb, n=name: self._pick_color(c, n))
            b.grid(row=i // 5, column=i % 5, padx=2, pady=2)
        row2 = ttk.Frame(box); row2.pack(fill="x", pady=(4, 0))
        self.color_preview = tk.Label(row2, text="      ", bg=hex_color(self.light_rgb), relief="sunken")
        self.color_preview.pack(side="left")
        self.color_name = ttk.Label(row2, text=LIGHT_COLORS[0][0]); self.color_name.pack(side="left", padx=6)
        ttk.Button(row2, text="Свой цвет…", command=self._custom_color).pack(side="right")
        ttk.Label(box, text="Сила (1 — слабый огонёк, 5 — очень яркий):").pack(anchor="w", pady=(6, 0))
        tk.Scale(box, from_=1, to=5, orient="horizontal", variable=self.light_strength, showvalue=True,
                 command=lambda v: self._use_light()).pack(fill="x")
        ttk.Button(box, text="Рисовать этим светом", command=self._use_light).pack(fill="x", pady=(4, 0))

    def _pick_color(self, rgb, name):
        self.light_rgb = list(rgb); self.color_preview.configure(bg=hex_color(rgb)); self.color_name.configure(text=name)
        self._use_light()

    def _custom_color(self):
        res = colorchooser.askcolor(color=hex_color(self.light_rgb), title="Цвет света")
        if res and res[0]:
            self._pick_color([int(v) for v in res[0]], "свой " + hex_color(res[0]))

    def _use_light(self):
        self.brush.set(LIGHT_BRUSH)
        self.status.set("Кисть: " + describe_light(self._light_definition()) + ". ЛКМ — поставить, ПКМ — стереть.")

    def _light_definition(self):
        preset = dict(LIGHT_KINDS).get(self.light_kind.get(), "torch")
        return {"type": "empty", "light": {"preset": preset, "color": list(self.light_rgb), "strength": int(self.light_strength.get())}}

    def _light_symbol(self):
        """Символ для текущего света: тот же, если такой свет уже есть, иначе свободная буква."""
        definition = self._light_definition()
        for sym, d in self.custom.items():
            if d == definition: return sym
        used = {ch for row in self.rows for ch in row} | set(GLOBAL_SYMBOLS) | {ch for ch, _, _ in PALETTE} \
               | set(self.meta.get("legend", {})) | set(self.custom)
        sym = next((c for c in SYMBOL_POOL if c not in used), None)
        if sym is None:
            messagebox.showerror("Свет", "Закончились свободные символы для разных источников света на этой карте."); return None
        self.custom[sym] = definition
        return sym

    def _cell_color(self, ch):
        if ch in self.custom: return hex_color(light_color(self.custom[ch].get("light")))
        return COLORS.get(ch, "#b08a5a")

    def _draw_cell(self, x, y, ch):
        x0, y0 = x * CELL, y * CELL
        rid = self.canvas.create_rectangle(x0, y0, x0 + CELL, y0 + CELL,
                                           fill="" if ch == "." else self._cell_color(ch),
                                           outline="#555563", width=1)
        if ch in self.custom:   # свой свет: кружок цвета света, размер = сила
            lvl = self.custom[ch].get("light", {}).get("strength", 3)
            r = 2 + int(lvl)
            self.canvas.create_oval(x0 + CELL/2 - r, y0 + CELL/2 - r, x0 + CELL/2 + r, y0 + CELL/2 + r, fill="#fffbe8", outline="#111118")
            self.rects[(x, y)] = rid
            return
        img = self.sprite_images.get(ch)
        if img:
            self.canvas.create_image(x0, y0, image=img, anchor="nw")
        elif ch != ".":
            self.canvas.create_text(x0 + CELL/2, y0 + CELL/2, text=ch, fill="#111118", font=("Arial", 9, "bold"))
        self.rects[(x, y)] = rid

    def _cell_from_event(self, event):
        x = int(self.canvas.canvasx(event.x)//CELL); y = int(self.canvas.canvasy(event.y)//CELL)
        return x, y

    def paint(self, event):
        if self.morg_mode.get():
            self.morgart_click(event, press="Press" in str(getattr(event, "type", "")) or str(getattr(event, "type", "")) == "4")
            return
        x, y = self._cell_from_event(event)
        if 0 <= x < self.map_w and 0 <= y < self.map_h:
            ch = self.brush.get()
            if ch == LIGHT_BRUSH:
                ch = self._light_symbol()
                if ch is None: return
            if self.rows[y][x] == ch: return
            self.rows[y][x] = ch
            label = describe_light(self.custom[ch]) if ch in self.custom else dict((a,b) for a,b,_ in PALETTE).get(ch, ch)
            self._draw_all(); self.status.set(f"Клетка ({x}, {y}): {label}")

    def erase(self, event):
        self.rows_at(event, ".")

    def rows_at(self, event, ch):
        x, y = self._cell_from_event(event)
        if 0 <= x < self.map_w and 0 <= y < self.map_h:
            self.rows[y][x] = ch; self._draw_all()

    def resize_map(self):
        try:
            new_w, new_h = int(self.width_var.get()), int(self.height_var.get())
            if not (5 <= new_w <= 300 and 5 <= new_h <= 300):
                raise ValueError("Размер должен быть от 5 до 300 клеток по каждой стороне.")
        except ValueError as e:
            messagebox.showerror("Некорректный размер", str(e) or "Введи целые числа от 5 до 300.")
            return
        if new_w == self.map_w and new_h == self.map_h:
            return
        if not messagebox.askyesno("Изменить размер карты", f"Изменить размер на {new_w}×{new_h}?\nПри уменьшении края карты будут обрезаны."):
            self.width_var.set(str(self.map_w)); self.height_var.set(str(self.map_h))
            return
        old_rows = self.rows
        self.rows = [[old_rows[y][x] if y < len(old_rows) and x < len(old_rows[y]) else "."
                      for x in range(new_w)] for y in range(new_h)]
        self.map_w, self.map_h = new_w, new_h
        self.canvas.configure(scrollregion=(0, 0, self.map_w * CELL, self.map_h * CELL))
        self._draw_all()
        self.status.set(f"Размер карты: {self.map_w}×{self.map_h} клеток")

    def clear(self):
        if messagebox.askyesno("Очистить карту", "Очистить всю сетку?"):
            self.rows = [["." for _ in range(self.map_w)] for _ in range(self.map_h)]; self._draw_all()

    def open_map(self):
        path = filedialog.askopenfilename(initialdir=MAP_DIR, filetypes=[("JSON карты", "*.json")])
        if not path: return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            rows = data.get("rows", [])
            self.map_h = max(5, len(rows) or H)
            self.map_w = max(5, max((len(row) for row in rows), default=W))
            self.rows = [[rows[y][x] if y < len(rows) and x < len(rows[y]) else "." for x in range(self.map_w)] for y in range(self.map_h)]
            self.width_var.set(str(self.map_w)); self.height_var.set(str(self.map_h))
            self.meta = {k:v for k,v in data.items() if k != "rows"}; self.current_path = Path(path)
            self.custom = {k: v for k, v in data.get("legend", {}).items() if isinstance(v, dict) and isinstance(v.get("light"), dict)}
            dk = data.get("darkness")
            self.darkness_var.set("" if dk is None else str(int(round(float(dk) * 100))))
            bg_path = data.get("background", "")
            bg_name = Path(bg_path).name if bg_path else ""
            bg_label = {"ruins.png": "Руины", "cave.png": "Пещера", "crypt.png": "Склеп", "bricks_tile.png": "Кирпичная плитка"}.get(bg_name, "Без фона")
            self.background.set(bg_label)
            self.map_id.set(Path(path).stem); self.name.set(data.get("name", Path(path).stem))
            self._morg_load(data.get("morgart_layout")); self._draw_all()
            self.status.set(f"Загружена карта: {path}")
        except Exception as e: messagebox.showerror("Ошибка", f"Не удалось открыть карту:\n{e}")

    def save_map(self):
        mid = self.map_id.get().strip()
        if not mid or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in mid):
            messagebox.showerror("Некорректный ID", "Используй латинские буквы, цифры, _ и -."); return
        MAP_DIR.mkdir(parents=True, exist_ok=True)
        path = MAP_DIR / f"{mid}.json"
        old_path = self.current_path
        # При изменении ID у открытой карты переносим файл и обновляем order.
        if path.exists() and path != old_path and not messagebox.askyesno("Перезапись", f"{path.name} уже существует. Перезаписать?"): return
        data = dict(self.meta); data["name"] = self.name.get().strip() or mid
        bg_paths = {"Руины": "backgrounds/ruins.png", "Пещера": "backgrounds/cave.png",
                    "Склеп": "backgrounds/crypt.png", "Кирпичная плитка": "backgrounds/bricks_tile.png"}
        if self.background.get() in bg_paths:
            data["background"] = bg_paths[self.background.get()]
            data["bg_mode"] = "tile" if self.background.get() == "Кирпичная плитка" else "cover"
        else:
            data.pop("background", None)
            data.pop("bg_mode", None)
        data["rows"] = ["".join(row) for row in self.rows]
        dk = self.darkness_var.get().strip()
        if dk:
            try: data["darkness"] = max(0, min(100, int(float(dk)))) / 100
            except ValueError: messagebox.showerror("Темнота", "Темнота — число от 0 до 100"); return
        else: data.pop("darkness", None)
        # Сохраняем используемую палитру в легенду, включая конкретные варианты текстур.
        used = {ch for row in self.rows for ch in row}
        legend = dict(data.get("legend", {}))
        for ch, _, definition in PALETTE:
            if ch in used and ch not in GLOBAL_SYMBOLS:
                legend[ch] = definition
        for ch in used:   # свои источники света (цвет и сила)
            if ch in self.custom: legend[ch] = self.custom[ch]
        data["legend"] = legend
        if self.morg_touched or "morgart_layout" in self.meta: data["morgart_layout"] = self._morg_layout()
        try:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if MAP_CONFIG.exists():
                config = json.loads(MAP_CONFIG.read_text(encoding="utf-8"))
                config.setdefault("order", [])
                if old_path and old_path != path:
                    old_id = old_path.stem
                    config["order"] = [item for item in config["order"] if item != old_id]
                if mid not in config["order"]: config["order"].append(mid)
                config["order"] = list(dict.fromkeys(config["order"]))
                MAP_CONFIG.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if old_path and old_path != path and old_path.exists():
                old_path.unlink()
            self.current_path = path
            self.status.set(f"Сохранено: {path.relative_to(ROOT)} (карта добавлена в порядок загрузки)")
            messagebox.showinfo("Карта сохранена", f"Сохранено в:\n{path}\n\nЕсли игра уже запущена, нажми F5 для перезагрузки данных.")
        except Exception as e: messagebox.showerror("Ошибка сохранения", str(e))

if __name__ == "__main__":
    root = tk.Tk(); Editor(root); root.mainloop()
