"""Простой редактор карт DEAD ROOMS. Запуск: python map_editor.py"""
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAP_DIR = ROOT / "data" / "maps"
MAP_CONFIG = ROOT / "data" / "maps.json"
W, H, CELL = 50, 50, 16

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
GLOBAL_SYMBOLS = (".", "#", "=", "H", "x", "<", ">", "L", "R", "U", "D", "P", "S", "?", "*", "o", "+", "%")
LEGEND = {ch: data for ch, _, data in PALETTE if ch not in GLOBAL_SYMBOLS}
LEGEND.update({".": "empty", "#": "wall", "=": "platform", "H": "ladder", "x": {"type": "spikes", "damage": 10},
               "<": {"exit": "prev"}, ">": {"exit": "next"}, "L": {"exit": "left"}, "R": {"exit": "right"},
               "U": {"exit": "up", "type": "ladder"}, "D": {"exit": "down", "type": "ladder"},
               "P": {"player": True}, "S": {"mob": "random"}, "?": {"item": "random"},
               "*": {"light": "torch"}, "o": {"light": "lantern"}, "+": {"light": "crystal"}, "%": {"light": "orb"}})

COLORS = {".": "#20202a", "#": "#85858c", "=": "#b08a5a", "H": "#c6a66b", "x": "#d94a4a",
          "P": "#62d6ff", "S": "#d58bff", "?": "#f5d75e", "<": "#8bd49b", ">": "#8bd49b",
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
        self.canvas = tk.Canvas(board, width=800, height=700, bg="#15151b", scrollregion=(0, 0, self.map_w*CELL, self.map_h*CELL), highlightthickness=0)
        sx = ttk.Scrollbar(board, orient="horizontal", command=self.canvas.xview); sy = ttk.Scrollbar(board, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=sx.set, yscrollcommand=sy.set)
        self.canvas.grid(row=0, column=0, sticky="nsew"); sy.grid(row=0, column=1, sticky="ns"); sx.grid(row=1, column=0, sticky="ew")
        board.rowconfigure(0, weight=1); board.columnconfigure(0, weight=1)
        self.canvas.bind("<Button-1>", self.paint); self.canvas.bind("<B1-Motion>", self.paint)
        self.canvas.bind("<Button-3>", self.erase)
        ttk.Label(right, textvariable=self.status, wraplength=800).pack(fill="x", pady=(8, 0))
        ttk.Label(right, text="Размер сетки настраивается сверху (от 5×5 до 300×300 клеток). ЛКМ — рисовать, ПКМ — стереть. Разные варианты платформ/стен/лестниц/шипов выбираются в палитре.").pack(anchor="w", pady=(4, 0))

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
            self.map_id.set(Path(path).stem); self.name.set(data.get("name", Path(path).stem)); self._draw_all()
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
