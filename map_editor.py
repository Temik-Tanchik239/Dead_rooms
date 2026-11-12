"""Простой редактор карт DEAD ROOMS. Запуск: python map_editor.py"""
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAP_DIR = ROOT / "data" / "maps"
MAP_CONFIG = ROOT / "data" / "maps.json"
BOSS_CONFIG = ROOT / "assets" / "boss" / "boss.json"
SKILLS_CONFIG = ROOT / "data" / "skills.json"
CHARS_CONFIG = ROOT / "data" / "characters.json"
PROJ_CONFIG = ROOT / "data" / "projectiles.json"
ICON_DIR = ROOT / "assets" / "icons"
SKILLS_ASSET_DIR = ROOT / "assets" / "skills"
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
    def __init__(self, container, window=None):
        self.root = container
        if window is not None:
            window.title("DEAD ROOMS — редактор карт")
            window.geometry("1100x820")
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

# ======================================================================================
#  РЕДАКТОР НАВЫКОВ  (вторая вкладка; пишет data/skills.json и привязки в data/characters.json)
# ======================================================================================

# Типы навыков. active — заклинания/активные навыки (@spell в spells.py); passive — пассивки;
# ammo — виды снарядов мини-арбалетов Тени (crossbow.py, окна снарядов в HUD): тип тоже "ammo".
ACTIVE_TYPES = ["dash", "nova", "heal", "shield", "projectile", "chain_lightning", "strike_area",
                "telekinesis", "telekinesis_cone", "telekinesis_hold"]
PASSIVE_TYPES = ["double_jump", "max_hp", "max_mana", "mana_regen", "mana_cost_reduction",
                 "damage", "move_speed"]
AMMO_TYPES = ["ammo"]

# Числовые/текстовые поля навыка. (ключ, подпись, тип). Пустое поле не пишется в JSON.
# "подсказка" справа поясняет, для каких типов поле нужно.
SKILL_FIELDS = [
    ("mana_cost", "Расход маны", "float", "активные"),
    ("cooldown", "Перезарядка, с", "float", "активные"),
    ("recharge", "Восстановление, с", "float", "поток: за сколько секунд запас восстанавливается с нуля до полного"),
    ("recharge_delay", "Пауза восстановл., с", "float", "поток: пауза перед началом восстановления"),
    ("interval", "Период эффекта, с", "float", "поток: как часто повторяется эффект, пока зажато"),
    ("unlock_level", "Открывается на ур.", "int", "в дереве навыков"),
    ("damage", "Урон", "float", "nova/strike_area/projectile/chain_lightning/telekinesis*"),
    ("radius", "Радиус", "float", "nova/heal/shield/strike_area/telekinesis"),
    ("range", "Дальность", "float", "chain_lightning/strike_area/telekinesis*"),
    ("knockback", "Отбрасывание", "float", "nova/strike_area/telekinesis*"),
    ("duration", "Длительность, с", "float", "shield/telekinesis_hold"),
    ("speed", "Скорость", "float", "dash"),
    ("invulnerability", "Неуязвимость, с", "float", "dash"),
    ("amount", "Количество (лечение/бонус)", "float", "heal/max_hp/max_mana"),
    ("multiplier", "Множитель", "float", "damage/move_speed/mana_regen"),
    ("capacity", "Ёмкость щита", "float", "shield"),
    ("stun", "Оглушение, с", "float", "strike_area"),
    ("chains", "Прыжков молнии", "int", "chain_lightning"),
    ("chain_range", "Радиус прыжка", "float", "chain_lightning"),
    ("falloff", "Спад урона (0..1)", "float", "chain_lightning"),
    ("force", "Сила притяжения", "float", "telekinesis"),
    ("grip", "Радиус захвата", "float", "telekinesis"),
    ("angle", "Угол конуса, °", "float", "telekinesis_cone"),
    ("count", "Снарядов за выстрел", "int", "projectile"),
    ("spread", "Разброс, рад", "float", "projectile"),
]

# Какие числовые поля показывать для каждого типа (остальные скрыты). Для всех активных
# добавляются mana_cost/cooldown, для всех — unlock_level. Неизвестный тип -> показываем все.
TYPE_FIELDS = {
    "dash": {"speed", "invulnerability", "radius"},
    "nova": {"radius", "damage", "knockback"},
    "heal": {"amount", "radius"},
    "shield": {"duration", "capacity", "radius"},
    "projectile": {"damage", "count", "spread"},
    "ammo": {"damage", "count", "spread"},
    "chain_lightning": {"damage", "range", "chain_range", "chains", "falloff", "knockback"},
    "strike_area": {"radius", "damage", "range", "knockback", "stun"},
    "telekinesis": {"range", "radius", "force", "grip", "damage"},
    "telekinesis_cone": {"range", "angle", "knockback", "damage"},
    "telekinesis_hold": {"range", "duration", "damage"},
    "double_jump": set(),
    "max_hp": {"amount"}, "max_mana": {"amount"},
    "mana_regen": {"multiplier"}, "mana_cost_reduction": {"amount"},
    "damage": {"multiplier"}, "move_speed": {"multiplier"},
}
PROJECTILE_TYPES = {"projectile", "ammo"}          # у кого есть снаряд-«оболочка»
EFFECT_TYPES = {"nova", "strike_area"}     # у кого осмыслен эффект на врага
# Порядок полей/блоков в середине (токен = ключ поля либо спец-блок __имя__).
LAYOUT_ORDER = ["mana_cost", "cooldown", "recharge", "recharge_delay", "interval", "unlock_level", "__projectile__",
                "damage", "radius", "range", "knockback", "duration", "speed",
                "invulnerability", "amount", "multiplier", "capacity", "stun",
                "chains", "chain_range", "falloff", "force", "grip", "angle",
                "count", "spread", "__weapons__", "__effect__", "__cast__"]
FIELD_KIND = {k: kind for k, _, kind, _ in SKILL_FIELDS}
FIELD_LABEL = {k: lbl for k, lbl, _, _ in SKILL_FIELDS}

# Вид каста активного навыка (поля skills.json: ничего / "channel": true / "hold": true; если заданы оба — работает channel).
CAST_MODES = [("normal", "Обычный"),
              ("channel", "С зажатием (стоя на месте)"),
              ("hold", "Поток (зажать: запас + мана в секунду)")]
CAST_MODE_NAME = dict(CAST_MODES)                         # ключ -> подпись
CAST_MODE_KEY = {name: key for key, name in CAST_MODES}   # подпись -> ключ
CAST_MODE_HINT = {
    "normal": "Нажал — сработало. Мана списывается за каждое применение, затем перезарядка.",
    "channel": "Зажать и стоять на месте: эффект идёт, пока держишь (не дольше «Макс. удержание»). Движение, прыжок, удар, "
               "получение урона или отпущенная клавиша прерывают каст — тогда начинается перезарядка.",
    "hold": "Зажать можно в любой момент, даже на бегу. «Запас» тратится, пока держишь, мана — «Мана в секунду». Отпустил — запас "
             "восстанавливается с того места, где остановился; пока в запасе что-то есть, навык можно включить снова.",
}
HOLD_ONLY_FIELDS = {"recharge", "recharge_delay", "interval"}   # поля только режима «поток»
HOOK_TYPES = {"telekinesis_hold"}      # типы со своим ведением эффекта: «период эффекта» им не нужен
MODE_LABELS = {                          # подписи полей, которые в режимах называются иначе
    "channel": {"duration": "Макс. удержание, с", "cooldown": "Перезарядка после, с"},
    "hold": {"duration": "Запас, с", "mana_cost": "Мана в секунду"},
}


class SkillEditor:
    def __init__(self, container):
        self.root = container
        self.skills = {}
        self.chars = {}
        self.projectiles = []
        self.editing_id = None          # id навыка, который сейчас редактируется (None — новый)
        self.icon_var = tk.StringVar(value="")     # относительный путь иконки ("" — нет)
        self.color_rgb = [150, 150, 255]
        self.icon_images = {}           # кэш PhotoImage иконок (чтобы Tk не удалил их)
        self.icon_buttons = {}
        self.vars = {}                  # поле -> StringVar
        self.cat_var = tk.StringVar(value="active")
        self.type_var = tk.StringVar(value="projectile")
        self.proj_var = tk.StringVar(value="")
        self.proj_skin_var = tk.StringVar(value="")  # свой спрайт снаряда ("" — по типу / по id навыка)
        self.proj_defs = {}
        self._thumbs = {}            # кэш превью: (путь, размер) -> PhotoImage
        self._preview_refs = []      # ссылки на картинки превью (чтобы Tk их не удалил)
        self.proj_buttons = {}       # тип снаряда -> кнопка
        self.proj_skin_buttons = {}  # путь спрайта -> кнопка
        self.roww = {}               # токен LAYOUT_ORDER -> виджет-строка/блок (для показа/скрытия)
        self.mode_var = tk.StringVar(value=CAST_MODE_NAME["normal"])   # вид каста (подпись из CAST_MODES)
        self.field_labels = {}       # поле -> ttk.Label (подпись меняется от вида каста)
        self.effect_kind = tk.StringVar(value="нет")
        self.effect_a = tk.StringVar(value="")   # freeze/stun: секунды; burn: время
        self.effect_b = tk.StringVar(value="")   # burn: dps
        self.cast_anim = tk.StringVar(value="")
        self.cast_w = tk.StringVar(value=""); self.cast_h = tk.StringVar(value="")
        self.cast_dx = tk.StringVar(value=""); self.cast_dy = tk.StringVar(value="")
        self.cast_dur = tk.StringVar(value="")
        self.weapons_var = tk.StringVar(value="")      # для пассивки mana_cost_reduction
        self.status = tk.StringVar(value="Выбери навык слева или нажми «Новый навык».")
        self.char_rows = {}             # cid -> (in_tree BooleanVar, base BooleanVar, level StringVar)
        self._load_data()
        self._ui()
        self._refresh_list()

    # ---------- данные ----------
    def _load_data(self):
        try:
            self.skills = json.loads(SKILLS_CONFIG.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.skills = {}
        try:
            self.chars = json.loads(CHARS_CONFIG.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.chars = {"order": [], "characters": {}}
        try:
            self.proj_defs = json.loads(PROJ_CONFIG.read_text(encoding="utf-8"))
            self.projectiles = sorted(self.proj_defs.keys())
        except (OSError, ValueError):
            self.proj_defs = {}; self.projectiles = []

    def _skill_ids(self):
        return [k for k in self.skills if not k.startswith("_")]

    def _char_order(self):
        order = self.chars.get("order") or list(self.chars.get("characters", {}).keys())
        return [c for c in order if c in self.chars.get("characters", {})]

    def _cast_anim_options(self):
        opts = [""]
        if SKILLS_ASSET_DIR.is_dir():
            for d in sorted(SKILLS_ASSET_DIR.iterdir()):
                if d.is_dir() and (d / "cast").is_dir():
                    opts.append(f"skills/{d.name}/cast")
                elif d.is_dir() and (d / "cast.png").exists():
                    opts.append(f"skills/{d.name}/cast.png")
        return opts

    # ---------- превью-картинки ----------
    def _thumb(self, rel, maxsize=48):
        """PhotoImage файла assets/<rel>, уменьшенный до maxsize (с кэшем). None — если нет файла."""
        if not rel:
            return None
        key = (rel, maxsize)
        if key in self._thumbs:
            return self._thumbs[key]
        img = None
        try:
            img = tk.PhotoImage(file=str(ROOT / "assets" / rel))
            while img.width() > maxsize or img.height() > maxsize:
                img = img.subsample(2, 2)
        except tk.TclError:
            img = None
        self._thumbs[key] = img
        return img

    def _proj_thumb(self, ptype, maxsize=40):
        skin = self.proj_defs.get(ptype, {}).get("skin")
        return self._thumb(skin, maxsize) if skin else None

    # ---------- UI ----------
    def _ui(self):
        outer = ttk.Frame(self.root, padding=8); outer.pack(fill="both", expand=True)

        # левая колонка — список навыков
        left = ttk.Frame(outer); left.pack(side="left", fill="y")
        ttk.Label(left, text="Навыки", font=("Arial", 12, "bold")).pack(anchor="w")
        self.listbox = tk.Listbox(left, width=24, height=28, exportselection=False)
        self.listbox.pack(fill="y", expand=True, pady=4)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        btns = ttk.Frame(left); btns.pack(fill="x")
        ttk.Button(btns, text="Новый", command=self._new_skill).pack(side="left", padx=2)
        ttk.Button(btns, text="Удалить", command=self._delete_skill).pack(side="left", padx=2)

        # середина — форма полей (прокручиваемая)
        mid_wrap = ttk.Frame(outer); mid_wrap.pack(side="left", fill="both", expand=True, padx=10)
        canvas = tk.Canvas(mid_wrap, highlightthickness=0, width=440)
        scroll = ttk.Scrollbar(mid_wrap, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y"); canvas.pack(side="left", fill="both", expand=True)
        mid = ttk.Frame(canvas); canvas.create_window((0, 0), window=mid, anchor="nw")
        mid.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))

        self._row(mid, "ID навыка (англ.):", "id", width=24)
        self._row(mid, "Название:", "name", width=30)
        r = ttk.Frame(mid); r.pack(fill="x", pady=2)
        ttk.Label(r, text="Категория:", width=18).pack(side="left")
        ttk.Combobox(r, textvariable=self.cat_var, width=12, state="readonly",
                     values=["active", "passive", "ammo"]).pack(side="left")
        r2 = ttk.Frame(mid); r2.pack(fill="x", pady=2)
        ttk.Label(r2, text="Тип:", width=18).pack(side="left")
        self.type_combo = ttk.Combobox(r2, textvariable=self.type_var, width=22,
                                       values=ACTIVE_TYPES + PASSIVE_TYPES + AMMO_TYPES)
        self.type_combo.pack(side="left")
        self.mode_row = ttk.Frame(mid); self.mode_row.pack(fill="x", pady=2)
        ttk.Label(self.mode_row, text="Вид каста:", width=18).pack(side="left")
        self.mode_combo = ttk.Combobox(self.mode_row, textvariable=self.mode_var, width=36, state="readonly",
                                       values=[name for _, name in CAST_MODES])
        self.mode_combo.pack(side="left")
        self.mode_hint = ttk.Label(mid, text="", foreground="#888", wraplength=430, justify="left")
        self.mode_hint.pack(fill="x", pady=(0, 3))

        # динамический блок: все поля/блоки строятся сюда, показываются по типу навыка
        self.dyn = ttk.Frame(mid); self.dyn.pack(fill="x")
        for key in FIELD_KIND:                       # числовые/текстовые поля
            self._field_row(self.dyn, key)
        self._projectile_block(self.dyn)             # __projectile__
        self._weapons_block(self.dyn)                # __weapons__
        self._effect_block(self.dyn)                 # __effect__
        self._cast_block(self.dyn)                   # __cast__

        # описание
        ttk.Label(mid, text="Описание:").pack(anchor="w", pady=(4, 0))
        self.desc_text = tk.Text(mid, width=52, height=3, wrap="word")
        self.desc_text.pack(fill="x")
        ttk.Button(mid, text="💾 Сохранить навык", command=self._save_skill).pack(fill="x", pady=8)
        ttk.Label(mid, textvariable=self.status, wraplength=430, foreground="#2a6").pack(fill="x")

        # правая колонка — превью, иконка, цвет, привязка к героям
        right = ttk.Frame(outer); right.pack(side="left", fill="y", padx=(6, 0))
        self._preview_panel(right)
        self._icon_panel(right)
        self._color_panel(right)
        self._char_panel(right)

        # перестраивать видимость при смене категории/типа (и обновлять превью)
        self.cat_var.trace_add("write", self._relayout)
        self.type_var.trace_add("write", self._relayout)
        self.mode_var.trace_add("write", self._relayout)
        self.effect_kind.trace_add("write", lambda *a: self._update_preview())
        self._relayout()

    def _row(self, parent, label, key, width=20, var=None, hint=None):
        """Строка «подпись + Entry» (для всегда видимых id/name)."""
        if var is None:
            var = tk.StringVar(value=""); self.vars[key] = var
        row = ttk.Frame(parent); row.pack(fill="x", pady=1)
        ttk.Label(row, text=label, width=18).pack(side="left")
        ttk.Entry(row, textvariable=var, width=width).pack(side="left")
        var.trace_add("write", lambda *a: self._update_preview())
        if hint:
            ttk.Label(row, text=hint, foreground="#888").pack(side="left", padx=6)

    def _field_row(self, parent, key):
        """Одно числовое поле внутри self.dyn (пакуется/скрывается в _relayout)."""
        self.vars[key] = tk.StringVar(value="")
        row = ttk.Frame(parent)
        lab = ttk.Label(row, text=FIELD_LABEL[key] + ":", width=20); lab.pack(side="left")
        self.field_labels[key] = lab
        ttk.Entry(row, textvariable=self.vars[key], width=10).pack(side="left")
        self.vars[key].trace_add("write", lambda *a: self._update_preview())
        self.roww[key] = row

    def _projectile_block(self, parent):
        """Блок снаряда: тип (поведение) + сетка иконок типов + свой спрайт («оболочка» навыка)."""
        f = ttk.LabelFrame(parent, text="Снаряд этого навыка", padding=4)
        top = ttk.Frame(f); top.pack(fill="x")
        ttk.Label(top, text="Поведение (тип):").pack(side="left")
        ttk.Combobox(top, textvariable=self.proj_var, width=16, state="readonly",
                     values=[""] + self.projectiles).pack(side="left", padx=4)
        self.proj_var.trace_add("write", lambda *a: (self._sync_proj_buttons(), self._update_preview()))
        ttk.Label(f, text="Иконки снарядов (клик — выбрать тип):", foreground="#888").pack(anchor="w", pady=(4, 0))
        grid = ttk.Frame(f); grid.pack(fill="x")
        for i, pt in enumerate(self.projectiles):
            img = self._proj_thumb(pt)
            b = tk.Button(grid, image=img, text=("" if img else pt[:6]), compound="center",
                          width=(40 if img else 7), height=(40 if img else 2),
                          command=lambda p=pt: self.proj_var.set(p))
            if img:
                b.image = img
            b.grid(row=i // 5, column=i % 5, padx=2, pady=2)
            self.proj_buttons[pt] = b
        ttk.Label(f, text="Свой спрайт (перекрывает картинку типа, assets/projectiles):",
                  foreground="#888", wraplength=300).pack(anchor="w", pady=(4, 0))
        sgrid = ttk.Frame(f); sgrid.pack(fill="x")
        skins = [("", "авто")]
        pdir = ROOT / "assets" / "projectiles"
        if pdir.is_dir():
            skins += [(f"projectiles/{p.name}", p.stem) for p in sorted(pdir.glob("*.png"))]
        for i, (rel, name) in enumerate(skins):
            img = self._thumb(rel, 40) if rel else None
            b = tk.Button(sgrid, image=img, text=("" if img else "авто"), compound="center",
                          width=(40 if img else 6), height=(40 if img else 2),
                          command=lambda r=rel: self._pick_proj_skin(r))
            if img:
                b.image = img
            b.grid(row=i // 5, column=i % 5, padx=2, pady=2)
            self.proj_skin_buttons[rel] = b
        self.roww["__projectile__"] = f

    def _weapons_block(self, parent):
        f = ttk.Frame(parent)
        ttk.Label(f, text="Оружие (через запятую):", width=20).pack(side="left")
        ttk.Entry(f, textvariable=self.weapons_var, width=26).pack(side="left")
        self.roww["__weapons__"] = f

    def _effect_block(self, parent):
        ef = ttk.LabelFrame(parent, text="Эффект (накладывается на врага)", padding=4)
        er = ttk.Frame(ef); er.pack(fill="x")
        ttk.Label(er, text="Эффект:").pack(side="left")
        ttk.Combobox(er, textvariable=self.effect_kind, width=10, state="readonly",
                     values=["нет", "freeze", "stun", "burn"]).pack(side="left", padx=4)
        ttk.Label(er, text="время/сек:").pack(side="left")
        ttk.Entry(er, textvariable=self.effect_a, width=6).pack(side="left", padx=2)
        ttk.Label(er, text="dps (burn):").pack(side="left")
        ttk.Entry(er, textvariable=self.effect_b, width=6).pack(side="left", padx=2)
        self.roww["__effect__"] = ef

    def _cast_block(self, parent):
        af = ttk.LabelFrame(parent, text="Анимация применения (своя, assets/skills/<...>)", padding=4)
        ar = ttk.Frame(af); ar.pack(fill="x")
        ttk.Label(ar, text="Кадры:").pack(side="left")
        ttk.Combobox(ar, textvariable=self.cast_anim, width=26,
                     values=self._cast_anim_options()).pack(side="left", padx=4)
        ar2 = ttk.Frame(af); ar2.pack(fill="x", pady=2)
        for lbl, v in (("Ш", self.cast_w), ("В", self.cast_h),
                       ("dx", self.cast_dx), ("dy", self.cast_dy), ("длит.с", self.cast_dur)):
            ttk.Label(ar2, text=lbl).pack(side="left")
            ttk.Entry(ar2, textvariable=v, width=5).pack(side="left", padx=2)
        self.roww["__cast__"] = af

    # ---------- показ/скрытие по типу ----------
    def mode_key(self):
        """Выбранный вид каста: normal / channel / hold (у пассивок — всегда normal)."""
        if self.cat_var.get() != "active":
            return "normal"
        return CAST_MODE_KEY.get(self.mode_var.get(), "normal")

    def _label(self, key):
        """Подпись поля с учётом вида каста (напр. «Запас, с» вместо «Длительность, с» у потока)."""
        return MODE_LABELS.get(self.mode_key(), {}).get(key, FIELD_LABEL[key])

    def _visible(self):
        """(category, type, set видимых токенов) — какие поля/блоки показывать для текущего типа."""
        cat = self.cat_var.get(); typ = self.type_var.get().strip()
        known = typ in TYPE_FIELDS
        fields = set(TYPE_FIELDS[typ]) if known else set(FIELD_KIND)   # неизвестный тип -> всё
        fields.add("unlock_level")
        if cat in ("active", "ammo"):   # у снаряда арбалета «перезарядка» — пауза между выстрелами этого арбалета
            fields.update({"mana_cost", "cooldown"})
        mode = self.mode_key()
        fields -= HOLD_ONLY_FIELDS                      # recharge/interval... — только у потока
        if mode == "channel":
            fields.add("duration")                      # максимум удержания
        elif mode == "hold":
            fields.update({"duration", "recharge", "recharge_delay"})   # запас и его восстановление
            fields.discard("cooldown")                  # у потока вместо перезарядки — восстановление запаса
            if typ not in HOOK_TYPES:
                fields.add("interval")                  # как часто повторять эффект
        show = set(fields)
        if typ in PROJECTILE_TYPES or not known:
            show.add("__projectile__")
        if typ in EFFECT_TYPES or not known:
            show.add("__effect__")
        if cat == "active":
            show.add("__cast__")
        if typ == "mana_cost_reduction" or not known:
            show.add("__weapons__")
        return cat, typ, show

    def _relayout(self, *_):
        cat, typ, show = self._visible()
        for tok in LAYOUT_ORDER:
            self.roww[tok].pack_forget()
        for tok in LAYOUT_ORDER:
            if tok in show:
                self.roww[tok].pack(fill="x", pady=1, anchor="w")
        for key, lab in self.field_labels.items():      # подписи полей зависят от вида каста
            lab.configure(text=self._label(key) + ":")
        if cat == "active":
            self.mode_row.pack(fill="x", pady=2, before=self.dyn)
            self.mode_hint.pack(fill="x", pady=(0, 3), before=self.dyn)
            self.mode_hint.configure(text=CAST_MODE_HINT[self.mode_key()])
        else:
            self.mode_row.pack_forget(); self.mode_hint.pack_forget()
        self._sync_proj_buttons()
        self._update_preview()

    def _sync_proj_buttons(self):
        pt = self.proj_var.get()
        for p, b in self.proj_buttons.items():
            b.configure(relief="sunken" if p == pt else "raised")
        sk = self.proj_skin_var.get()
        for rel, b in self.proj_skin_buttons.items():
            b.configure(relief="sunken" if rel == sk else "raised")

    def _pick_proj_skin(self, rel):
        self.proj_skin_var.set(rel or "")
        self._sync_proj_buttons(); self._update_preview()

    # ---------- превью «собранного навыка» ----------
    def _preview_panel(self, parent):
        box = ttk.LabelFrame(parent, text="Собранный навык", padding=4); box.pack(fill="x")
        self.preview = tk.Canvas(box, width=232, height=300, bg="#1b1b24", highlightthickness=0)
        self.preview.pack()

    def _update_preview(self, *_):
        c = getattr(self, "preview", None)
        if c is None:
            return
        c.delete("all"); self._preview_refs = []
        col = hex_color(self.color_rgb)
        icon = self.icon_var.get()
        img = self._thumb(icon, 64) if icon else None
        if img:
            c.create_image(16, 14, image=img, anchor="nw"); self._preview_refs.append(img)
        else:
            c.create_oval(18, 16, 78, 76, fill=col, outline="")
        name = self.vars["name"].get() or self.vars["id"].get() or "новый навык"
        c.create_text(90, 16, text=name, fill="#ffffff", anchor="nw", font=("Arial", 12, "bold"), width=132)
        c.create_text(90, 42, text=f"{self.cat_var.get()} · {self.type_var.get()}", fill="#9ad0ff",
                      anchor="nw", font=("Arial", 9), width=132)
        if self.mode_key() != "normal":
            c.create_text(90, 60, text="с зажатием" if self.mode_key() == "channel" else "поток",
                          fill="#ffcf8a", anchor="nw", font=("Arial", 8))
        c.create_rectangle(16, 86, 216, 92, fill=col, outline="")
        _, typ, show = self._visible()
        y = 100
        for key in LAYOUT_ORDER:
            if key.startswith("__") or key not in show:
                continue
            val = self.vars[key].get().strip()
            if val:
                c.create_text(16, y, text=f"{self._label(key)}: {val}", fill="#cfd4e0",
                              anchor="nw", font=("Arial", 9)); y += 15
        if self.effect_kind.get() != "нет" and "__effect__" in show:
            c.create_text(16, y, text=f"эффект: {self.effect_kind.get()} {self.effect_a.get()}".strip(),
                          fill="#a0e0c0", anchor="nw", font=("Arial", 9)); y += 15
        if "__projectile__" in show:
            skin = self.proj_skin_var.get() or self.proj_defs.get(self.proj_var.get(), {}).get("skin")
            c.create_text(16, y + 4, text=f"снаряд: {self.proj_var.get() or '—'}", fill="#9ad0ff",
                          anchor="nw", font=("Arial", 9))
            pim = self._thumb(skin, 44) if skin else None
            if pim:
                c.create_image(150, y, image=pim, anchor="nw"); self._preview_refs.append(pim)
            y += 26
        if "__cast__" in show and self.cast_anim.get().strip():
            c.create_text(16, y, text=f"каст: {self.cast_anim.get()}", fill="#c9b3ff",
                          anchor="nw", font=("Arial", 8), width=200)

    def _icon_panel(self, parent):
        box = ttk.LabelFrame(parent, text="Иконка навыка (своя, assets/icons)", padding=4); box.pack(fill="x", pady=6)
        ttk.Label(box, textvariable=self.icon_var, foreground="#888", wraplength=210).pack(anchor="w")
        canvas = tk.Canvas(box, width=224, height=150, highlightthickness=0)
        sc = ttk.Scrollbar(box, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sc.set)
        sc.pack(side="right", fill="y"); canvas.pack(side="left")
        grid = ttk.Frame(canvas); canvas.create_window((0, 0), window=grid, anchor="nw")
        grid.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        options = [("", "нет")]
        if ICON_DIR.is_dir():
            for p in sorted(ICON_DIR.glob("*.png")):
                options.append((f"icons/{p.name}", p.stem))
        col_n = 4
        for i, (rel, name) in enumerate(options):
            img = self._thumb(rel, 48) if rel else None
            b = tk.Button(grid, image=img, text=("✖" if not rel else ""), width=(48 if img else 4),
                          height=(48 if img else 2), compound="center",
                          command=lambda r=rel: self._pick_icon(r))
            if img:
                b.image = img
            b.grid(row=i // col_n, column=i % col_n, padx=2, pady=2)
            self.icon_buttons[rel] = b

    def _pick_icon(self, rel):
        for r, b in self.icon_buttons.items():
            b.configure(relief="sunken" if r == rel else "raised")
        self.icon_var.set(rel or "")
        self._update_preview()

    def _color_panel(self, parent):
        box = ttk.LabelFrame(parent, text="Цвет навыка", padding=4); box.pack(fill="x", pady=6)
        self.color_preview = tk.Label(box, text="      ", bg=hex_color(self.color_rgb), relief="sunken")
        self.color_preview.pack(side="left", padx=4)
        ttk.Button(box, text="Выбрать цвет…", command=self._pick_color).pack(side="left")

    def _pick_color(self):
        res = colorchooser.askcolor(color=hex_color(self.color_rgb), title="Цвет навыка")
        if res and res[0]:
            self.color_rgb = [int(v) for v in res[0]]
            self.color_preview.configure(bg=hex_color(self.color_rgb))
            self._update_preview()

    def _char_panel(self, parent):
        box = ttk.LabelFrame(parent, text="Каким героям доступен навык", padding=4); box.pack(fill="x")
        ttk.Label(box, text="☑ в дереве · ☑ с начала · уровень", foreground="#888").pack(anchor="w")
        for cid in self._char_order():
            name = self.chars["characters"][cid].get("name", cid)
            row = ttk.Frame(box); row.pack(fill="x", pady=1)
            in_tree = tk.BooleanVar(value=False); base = tk.BooleanVar(value=False); lvl = tk.StringVar(value="1")
            ttk.Checkbutton(row, variable=in_tree).pack(side="left")
            ttk.Checkbutton(row, variable=base).pack(side="left")
            ttk.Entry(row, textvariable=lvl, width=3).pack(side="left", padx=2)
            ttk.Label(row, text=f"{name} ({cid})").pack(side="left")
            self.char_rows[cid] = (in_tree, base, lvl)

    # ---------- список / выбор ----------
    def _refresh_list(self, select=None):
        self.listbox.delete(0, "end")
        self._ids_in_list = sorted(self._skill_ids())
        for sid in self._ids_in_list:
            s = self.skills[sid]
            self.listbox.insert("end", f"{sid} — {s.get('name', '')}")
        if select in self._ids_in_list:
            i = self._ids_in_list.index(select)
            self.listbox.selection_set(i); self.listbox.see(i)

    def _on_select(self, _event=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        sid = self._ids_in_list[sel[0]]
        self._load_skill(sid)

    def _load_skill(self, sid):
        s = self.skills.get(sid, {})
        self.editing_id = sid
        self.vars["id"].set(sid)
        self.vars["name"].set(s.get("name", ""))
        self.cat_var.set(s.get("category", "active"))
        self.type_var.set(s.get("type", ""))
        self.proj_var.set(s.get("projectile", "") if isinstance(s.get("projectile"), str) else "")
        self.proj_skin_var.set(s.get("projectile_skin", "") or "")
        self.mode_var.set(CAST_MODE_NAME["channel" if s.get("channel") else "hold" if s.get("hold") else "normal"])   # channel сильнее hold
        for key, _, _, _ in SKILL_FIELDS:
            v = s.get(key, "")
            self.vars[key].set("" if v == "" else str(v))
        self.weapons_var.set(", ".join(s.get("weapons", [])) if isinstance(s.get("weapons"), list) else "")
        # цвет
        col = s.get("color")
        if isinstance(col, list) and len(col) >= 3:
            self.color_rgb = [int(c) for c in col[:3]]
        self.color_preview.configure(bg=hex_color(self.color_rgb))
        # иконка
        self._pick_icon(s.get("icon", "") or "")
        # эффект
        eff = s.get("effect")
        self.effect_kind.set("нет"); self.effect_a.set(""); self.effect_b.set("")
        if isinstance(eff, dict):
            if "freeze" in eff: self.effect_kind.set("freeze"); self.effect_a.set(str(eff["freeze"]))
            elif "stun" in eff: self.effect_kind.set("stun"); self.effect_a.set(str(eff["stun"]))
            elif "burn" in eff and isinstance(eff["burn"], dict):
                self.effect_kind.set("burn"); self.effect_a.set(str(eff["burn"].get("time", "")))
                self.effect_b.set(str(eff["burn"].get("dps", "")))
        # анимация каста
        self.cast_anim.set(s.get("cast_anim", "") or "")
        cs = s.get("cast_size") or ["", ""]; self.cast_w.set(str(cs[0])); self.cast_h.set(str(cs[1]))
        co = s.get("cast_offset") or ["", ""]; self.cast_dx.set(str(co[0])); self.cast_dy.set(str(co[1]))
        self.cast_dur.set(str(s.get("cast_animation", "")) if s.get("cast_animation") is not None else "")
        # описание
        self.desc_text.delete("1.0", "end"); self.desc_text.insert("1.0", s.get("description", ""))
        # привязка к героям
        self._load_char_assignment(sid)
        self._relayout()        # показать только нужные поля для этого типа + обновить превью
        self.status.set(f"Редактируется навык: {sid}")

    def _load_char_assignment(self, sid):
        for cid, (in_tree, base, lvl) in self.char_rows.items():
            cdef = self.chars["characters"].get(cid, {})
            in_tree.set(False); base.set(False); lvl.set("1")
            for entry in cdef.get("skill_tree", []):
                if isinstance(entry, dict) and entry.get("skill") == sid:
                    in_tree.set(True); lvl.set(str(entry.get("unlock_level", 1))); break
            if sid in cdef.get("base_skills", []):
                base.set(True)

    def _new_skill(self):
        self.editing_id = None
        self.listbox.selection_clear(0, "end")
        for v in self.vars.values():
            v.set("")
        self.vars["unlock_level"].set("1")
        self.cat_var.set("active"); self.type_var.set("projectile")
        self.proj_var.set(""); self.proj_skin_var.set("")
        self.mode_var.set(CAST_MODE_NAME["normal"]); self.weapons_var.set("")
        self.effect_kind.set("нет"); self.effect_a.set(""); self.effect_b.set("")
        self.cast_anim.set(""); self.cast_w.set(""); self.cast_h.set("")
        self.cast_dx.set(""); self.cast_dy.set(""); self.cast_dur.set("")
        self.color_rgb = [150, 150, 255]; self.color_preview.configure(bg=hex_color(self.color_rgb))
        self._pick_icon("")
        self.desc_text.delete("1.0", "end")
        for in_tree, base, lvl in self.char_rows.values():
            in_tree.set(False); base.set(False); lvl.set("1")
        self._relayout()
        self.status.set("Новый навык: заполни поля и сохрани.")

    def _delete_skill(self):
        if not self.editing_id or self.editing_id not in self.skills:
            messagebox.showinfo("Удаление", "Сначала выбери сохранённый навык в списке."); return
        sid = self.editing_id
        if not messagebox.askyesno("Удалить навык", f"Удалить «{sid}» из skills.json и из всех героев?"):
            return
        self.skills.pop(sid, None)
        for cdef in self.chars.get("characters", {}).values():
            cdef["skill_tree"] = [e for e in cdef.get("skill_tree", []) if not (isinstance(e, dict) and e.get("skill") == sid)]
            cdef["base_skills"] = [s for s in cdef.get("base_skills", []) if s != sid]
            cdef.get("skill_overrides", {}).pop(sid, None)
        self._write_all()
        self._new_skill(); self._refresh_list()
        self.status.set(f"Навык «{sid}» удалён.")

    # ---------- сохранение ----------
    def _num(self, text, kind):
        text = text.strip().replace(",", ".")
        if not text:
            return None
        try:
            val = float(text)
        except ValueError:
            raise ValueError(f"«{text}» — не число")
        if kind == "int" or val.is_integer():
            return int(val)       # целое пишем как целое (42, а не 42.0)
        return val

    def _save_skill(self):
        sid = self.vars["id"].get().strip()
        if not sid or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for c in sid):
            messagebox.showerror("ID", "ID навыка: латинские буквы, цифры и _ (без пробелов)."); return
        # начинаем с копии старого навыка, чтобы не потерять незнакомые поля (visual и т.п.)
        base = dict(self.skills.get(self.editing_id, {})) if self.editing_id else {}
        try:
            s = self._build_skill(base)
        except ValueError as e:
            messagebox.showerror("Число", str(e)); return
        # переименование
        if self.editing_id and self.editing_id != sid:
            self.skills.pop(self.editing_id, None)
            self._rename_in_chars(self.editing_id, sid)
        self.skills[sid] = s
        self._apply_char_assignment(sid)
        self.editing_id = sid
        self._write_all()
        self._refresh_list(select=sid)
        self.status.set(f"Навык «{sid}» сохранён. В игре нажми F5.")
        messagebox.showinfo("Навык сохранён", f"«{sid}» записан в data/skills.json и привязан к героям.\n\nЕсли игра запущена — нажми F5.")

    def _build_skill(self, base):
        # пишем только поля/блоки, видимые для текущего типа — так навык не тянет чужие настройки
        _, typ, show = self._visible()
        s = dict(base)
        s["name"] = self.vars["name"].get().strip() or self.vars["id"].get().strip()
        s["category"] = self.cat_var.get()
        if self.type_var.get().strip():
            s["type"] = self.type_var.get().strip()
        # вид каста (только активные): channel — «с зажатием стоя», hold — «поток»; для обычного оба флага убираются
        mode = self.mode_key()
        s.pop("channel", None); s.pop("hold", None)
        if mode == "channel":
            s["channel"] = True
        elif mode == "hold":
            s["hold"] = True
        # снаряд и свой спрайт (только для типов со снарядом)
        if "__projectile__" in show and self.proj_var.get().strip():
            s["projectile"] = self.proj_var.get().strip()
        else:
            s.pop("projectile", None)
        if "__projectile__" in show and self.proj_skin_var.get().strip():
            s["projectile_skin"] = self.proj_skin_var.get().strip()
        else:
            s.pop("projectile_skin", None)
        # числовые поля: пишем только видимые, остальные удаляем
        for key, _, kind, _ in SKILL_FIELDS:
            if key not in show:
                s.pop(key, None); continue
            val = self._num(self.vars[key].get(), kind)
            if val is None:
                s.pop(key, None)
            else:
                s[key] = val
        # оружие (пассивка mana_cost_reduction)
        weps = [w.strip() for w in self.weapons_var.get().split(",") if w.strip()]
        if "__weapons__" in show and weps:
            s["weapons"] = weps
        else:
            s.pop("weapons", None)
        # цвет
        s["color"] = [int(c) for c in self.color_rgb]
        # иконка
        if self.icon_var.get():
            s["icon"] = self.icon_var.get()
        else:
            s.pop("icon", None)
        # эффект (только для типов с эффектом)
        kind = self.effect_kind.get()
        if "__effect__" not in show or kind == "нет":
            s.pop("effect", None)
        elif kind in ("freeze", "stun"):
            s["effect"] = {kind: self._num(self.effect_a.get(), "float") or 0}
        elif kind == "burn":
            s["effect"] = {"burn": {"time": self._num(self.effect_a.get(), "float") or 0,
                                     "dps": self._num(self.effect_b.get(), "float") or 0}}
        # анимация каста (только активные)
        if "__cast__" in show and self.cast_anim.get().strip():
            s["cast_anim"] = self.cast_anim.get().strip()
        else:
            s.pop("cast_anim", None)
        cw, ch = self._num(self.cast_w.get(), "int"), self._num(self.cast_h.get(), "int")
        if "__cast__" in show and cw is not None and ch is not None:
            s["cast_size"] = [cw, ch]
        else:
            s.pop("cast_size", None)
        dx, dy = self._num(self.cast_dx.get(), "int"), self._num(self.cast_dy.get(), "int")
        if "__cast__" in show and dx is not None and dy is not None:
            s["cast_offset"] = [dx, dy]
        else:
            s.pop("cast_offset", None)
        dur = self._num(self.cast_dur.get(), "float")
        if "__cast__" in show and dur is not None:
            s["cast_animation"] = dur
        else:
            s.pop("cast_animation", None)
        # описание
        desc = self.desc_text.get("1.0", "end").strip()
        if desc:
            s["description"] = desc
        else:
            s.pop("description", None)
        return s

    def _rename_in_chars(self, old, new):
        for cdef in self.chars.get("characters", {}).values():
            for e in cdef.get("skill_tree", []):
                if isinstance(e, dict) and e.get("skill") == old:
                    e["skill"] = new
            cdef["base_skills"] = [new if s == old else s for s in cdef.get("base_skills", [])]
            ov = cdef.get("skill_overrides", {})
            if old in ov:
                ov[new] = ov.pop(old)

    def _apply_char_assignment(self, sid):
        for cid, (in_tree, base, lvl) in self.char_rows.items():
            cdef = self.chars["characters"].setdefault(cid, {})
            tree = cdef.setdefault("skill_tree", [])
            bs = cdef.setdefault("base_skills", [])
            if in_tree.get():
                try:
                    level = int(float(lvl.get()))
                except ValueError:
                    level = 1
                found = False
                for e in tree:
                    if isinstance(e, dict) and e.get("skill") == sid:
                        e["unlock_level"] = level; found = True; break
                if not found:
                    tree.append({"skill": sid, "unlock_level": level})
            else:
                cdef["skill_tree"] = [e for e in tree if not (isinstance(e, dict) and e.get("skill") == sid)]
            if base.get():
                if sid not in bs:
                    bs.append(sid)
            else:
                cdef["base_skills"] = [s for s in bs if s != sid]

    def _write_all(self):
        try:
            SKILLS_CONFIG.write_text(json.dumps(self.skills, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            CHARS_CONFIG.write_text(json.dumps(self.chars, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception as e:
            messagebox.showerror("Ошибка сохранения", str(e))


def _apply_editor_icon(root):
    """Иконка окна/ярлыка редактора — из assets (меняется без правки кода).
    Приоритет: assets/app/editor_icon.png, затем assets/app/icon.png (общая с игрой)."""
    for name in ("editor_icon.png", "icon.png"):
        p = ROOT / "assets" / "app" / name
        if p.is_file():
            try:
                img = tk.PhotoImage(file=str(p))
                root.iconphoto(True, img)
                root._editor_icon_ref = img   # держим ссылку, иначе Tk удалит картинку
                return
            except Exception as e:
                print("иконка редактора не загружена:", e)


def _build_mobs_tab(nb, root):
    """Вкладка «Мобы» (mob_editor.py). Если она не запустилась (нет файла/ошибка) — редактор карт всё равно открывается,
    а на вкладке показан текст ошибки, а не пустое окно и не молчаливый вылет."""
    tab = ttk.Frame(nb); nb.add(tab, text="  Мобы  ")
    try:
        import mob_editor
        mobs = mob_editor.MobTab(tab); mobs.pack(fill="both", expand=True, padx=6, pady=6)
        return mobs
    except Exception as e:
        import traceback; traceback.print_exc()
        ttk.Label(tab, text="Вкладка «Мобы» не запустилась:\n\n%s: %s\n\nПодробности — в консоли." % (type(e).__name__, e),
                  justify="left", foreground="#b00020").pack(anchor="nw", padx=16, pady=16)
        return None


def _build_accessories_tab(nb):
    """Вкладка «Аксессуары» (accessory_editor.py): надеваемые предметы в assets/inventory.json -> items."""
    tab = ttk.Frame(nb); nb.add(tab, text="  Аксессуары  ")
    try:
        import accessory_editor
        acc = accessory_editor.AccessoryTab(tab); acc.pack(fill="both", expand=True)
        return acc
    except Exception as e:
        import traceback; traceback.print_exc()
        ttk.Label(tab, text="Вкладка «Аксессуары» не запустилась:\n\n%s: %s" % (type(e).__name__, e),
                  justify="left", foreground="#b00020").pack(anchor="nw", padx=16, pady=16)
        return None


if __name__ == "__main__":
    root = tk.Tk()
    root.title("DEAD ROOMS — редакторы")
    root.geometry("1280x880")
    _apply_editor_icon(root)
    nb = ttk.Notebook(root); nb.pack(fill="both", expand=True)
    maps_tab = ttk.Frame(nb); nb.add(maps_tab, text="  Карты  ")
    skills_tab = ttk.Frame(nb); nb.add(skills_tab, text="  Навыки  ")
    Editor(maps_tab, window=None)
    SkillEditor(skills_tab)
    mobs_tab = _build_mobs_tab(nb, root)
    acc_tab = _build_accessories_tab(nb)

    def _on_close():
        # несохранённые правки мобов: спросить, как это делает сама вкладка
        if mobs_tab is not None and not mobs_tab.confirm_close():
            return
        if acc_tab is not None and not acc_tab.confirm_close():
            return
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", _on_close)
    root.mainloop()
