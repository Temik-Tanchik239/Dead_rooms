"""Редактор текстур (вкладка «  Текстуры  »): пиксель-арт для ресурсов, турели и огненного меча.

Рисуется на небольшой сетке (каждые 4 пикселя текстуры = 1 «клетка» кисти), результат
сохраняется в PNG:
  • ресурсы   -> assets/resources/<id>.png  (используются и как иконка в инвентаре)
  • турель    -> assets/buildings/turret.png (текстура постройки, см. data/crafting.json build.image)
  • меч       -> assets/weapons/fire_sword.png (скин оружия, берётся из weapons.json skin)

ЛКМ рисует выбранным цветом, ПКМ стирает (прозрачный пиксель). Цвет из палитры внизу.
Сохранение — кнопка «Сохранить» (пишет файл сразу; игра видит его после нажатия F5).
Прозрачный фон: клетки, в которых ничего не нарисовано.
"""
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

PX = 24                       # экранных пикселей на клетку кисти (1 клетка = 4 пикселя текстуры)
FACTOR = 4                    # во сколько реальных пикселей больше (разрешение сохранённого PNG)

# id, имя, путь в assets, ширина/высота в клетках. Размер файла = клетки * FACTOR.
ENTITIES = [
    ("wood", "Ресурс: древесина", "resources/wood.png", 8, 8),
    ("metal", "Ресурс: металл", "resources/metal.png", 8, 8),
    ("crystal", "Ресурс: кристалл", "resources/crystal.png", 8, 8),
    ("fire", "Ресурс: огонь", "resources/fire.png", 8, 8),
    ("turret", "Турель", "buildings/turret.png", 8, 9),
    ("fire_sword", "Огненный меч", "weapons/fire_sword.png", 9, 12),
]

PALETTE = ["#ffffff", "#cfcfcf", "#9a9aa8", "#55555f",
           "#000000", "#a26e3e", "#6b4420", "#96a2b9",
           "#3f5ca8", "#78dcff", "#2a7fb0", "#ff9628",
           "#ffdd6a", "#e8563c", "#9be36a", "#c148d8"]


class TextureTab(ttk.Frame):
    """Рисовалка текстур. Один виджет на вкладку; не зависит от реальной игры."""

    def __init__(self, parent, root=None):
        super().__init__(parent)
        self.root = Path(root) if root is not None else Path(__file__).resolve().parent
        self.entity = tk.StringVar(value=ENTITIES[0][0])
        self.color = tk.StringVar(value=PALETTE[0])
        self.erase = tk.BooleanVar(value=False)
        self.pixels = {}      # (x, y) -> hex цвет или None (прозрачно)
        self.rects = {}       # (x, y) -> id прямоугольника на канвасе
        self._ui()
        self.entity.trace_add("write", lambda *_: self._switch())
        self._switch()

    # ---- интерфейс ----
    def _ui(self):
        bar = ttk.Frame(self); bar.pack(fill="x", padx=6, pady=(6, 4))
        ttk.Label(bar, text="Текстура:").pack(side="left")
        self.ent = ttk.Combobox(bar, textvariable=self.entity, state="readonly", width=22,
                                values=[e[1] for e in ENTITIES])
        self.ent.pack(side="left", padx=6)
        ttk.Label(bar, text="(ЛКМ — цвет, ПКМ — стереть)", foreground="#8a8a98").pack(side="left", padx=8)
        ttk.Button(bar, text="Очистить", command=self.clear).pack(side="right", padx=2)
        ttk.Button(bar, text="Сохранить", command=self.save).pack(side="right", padx=2)

        frm = ttk.Frame(self); frm.pack(fill="both", expand=True, padx=6, pady=4)
        self.canvas = tk.Canvas(frm, bg="#101014", highlightthickness=0)
        vs = ttk.Scrollbar(frm, orient="vertical", command=self.canvas.yview)
        hs = ttk.Scrollbar(frm, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(xscrollcommand=hs.set, yscrollcommand=vs.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns"); hs.grid(row=1, column=0, sticky="ew")
        frm.rowconfigure(0, weight=1); frm.columnconfigure(0, weight=1)

        pal = ttk.Frame(self); pal.pack(fill="x", padx=6, pady=4)
        for hexc in PALETTE:
            b = tk.Button(pal, bg=hexc, activebackground=hexc, width=3, relief="flat",
                          command=lambda c=hexc: (self.erase.set(False), self.color.set(c), self._mark_color()))
            b.pack(side="left", padx=1, pady=2)
        self.eraser = ttk.Checkbutton(pal, text="Ластик (прозрачный)", variable=self.erase,
                                      command=lambda: self.color.set(self.color.get()))
        self.eraser.pack(side="left", padx=14)
        ttk.Checkbutton(pal, text="Показ сетки", variable=tk.BooleanVar(value=True),
                        command=self._redraw).pack(side="left", padx=4)

        self.status_var = tk.StringVar(self, value="")
        self.status = ttk.Label(self, textvariable=self.status_var, foreground="#8a8a98")
        self.status.pack(fill="x", padx=6, pady=(0, 4))

        self.canvas.bind("<Button-1>", lambda e: self._paint(e, erase=False))
        self.canvas.bind("<B1-Motion>", lambda e: self._paint(e, erase=False))
        self.canvas.bind("<Button-3>", lambda e: self._paint(e, erase=True))
        self.canvas.bind("<B3-Motion>", lambda e: self._paint(e, erase=True))

    # ---- выбранная текстура ----
    def _cur(self):
        for ent in ENTITIES:
            if ent[0] == self.entity.get(): return ent
        return ENTITIES[0]

    def _path(self):
        return self.root / "assets" / self._cur()[2]

    def _switch(self):
        """Загрузить текстуру выбранной сущности (или пустую сетку)."""
        import pygame as pg
        ent = self._cur()
        w, h = ent[3], ent[4]
        px = {}
        p = self._path()
        if p.exists():
            try:
                img = pg.image.load(str(p))   # без convert_alpha: у редактора нет pygame-дисплея
                for j in range(h):
                    for i in range(w):
                        r, g, b, a = img.get_at((min(i * FACTOR, img.get_width() - 1),
                                                  min(j * FACTOR, img.get_height() - 1)))
                        px[(i, j)] = ("#%02x%02x%02x" % (r, g, b)) if a > 110 else None
            except Exception:
                px = {}
        self.pixels = px
        self._redraw()
        self.status_var.set("Текстура: %s  ->  %s" % (ent[1], ent[2]))

    # ---- рисование ----
    def _redraw(self):
        self.canvas.delete("all")
        self.rects = {}
        ent = self._cur()
        w, h = ent[3] * PX, ent[4] * PX
        self.canvas.configure(scrollregion=(0, 0, w, h))
        # шахматная подложка (виден прозрачный фон)
        for j in range(ent[4]):
            for i in range(ent[3]):
                bg = "#20202a" if (i + j) % 2 == 0 else "#1a1a22"
                x, y = i * PX, j * PX
                rid = self.canvas.create_rectangle(x, y, x + PX, y + PX, fill=bg, outline="", tags="px")
                self.rects[(i, j)] = rid
                col = self.pixels.get((i, j))
                if col:
                    self.canvas.itemconfigure(rid, fill=col)
        self._mark_color()

    def _mark_color(self):
        pass

    def _paint(self, ev, erase):
        ent = self._cur()
        x = ev.x // PX; y = ev.y // PX
        if not (0 <= x < ent[3] and 0 <= y < ent[4]): return
        if erase or self.erase.get():
            self.pixels[(x, y)] = None
            bg = "#20202a" if (x + y) % 2 == 0 else "#1a1a22"
            self.canvas.itemconfigure(self.rects[(x, y)], fill=bg)
        else:
            col = self.color.get()
            self.pixels[(x, y)] = col
            self.canvas.itemconfigure(self.rects[(x, y)], fill=col)

    def clear(self):
        self.pixels = {}
        self._redraw()

    # ---- сохранение ----
    def save(self):
        import pygame as pg
        ent = self._cur()
        w, h = ent[3] * FACTOR, ent[4] * FACTOR
        surf = pg.Surface((w, h), pg.SRCALPHA)
        surf.fill((0, 0, 0, 0))
        for (i, j), col in self.pixels.items():
            if not col: continue
            r, g, b = int(col[1:3], 16), int(col[3:5], 16), int(col[5:7], 16)
            surf.fill((r, g, b, 255), (i * FACTOR, j * FACTOR, FACTOR, FACTOR))
        p = self._path()
        p.parent.mkdir(parents=True, exist_ok=True)
        pg.image.save(surf, str(p))
        self.status_var.set("Сохранено: %s  (%dx%d)" % (p.relative_to(self.root), w, h))
        messagebox.showinfo("Текстура сохранена",
                            "Сохранено:\n%s\n\nЕсли игра запущена — нажмите F5, чтобы увидеть новую текстуру." % p)
