"""Панель «Мелкие детали» редактора карт (map_editor.py): декор с точностью до пикселя.

Обычные символы карты стоят строго по клеткам 32x32. Эта панель добавляет поверх них отдельный слой
мелких картинок (черепа, трещины, мох, паутина, камешки, надписи...) с произвольными координатами.
Детали ни на что не влияют в физике — это только картинка, как и поле draw/offset в легенде,
но у каждой детали своё положение, размер, отражение и слой, а символов в легенде для них не нужно.

Включи «Режим деталей» — и на карте:
  ЛКМ по пустому месту    — поставить деталь с настройками кисти (картинка, размер, слой);
  ЛКМ по детали + тянуть  — выбрать и двигать (с привязкой к шагу: 1/2/4/8/16/32 px);
  Ctrl + ЛКМ              — поставить новую деталь, даже если под курсором уже есть другая;
  ПКМ по детали           — удалить;
  стрелки (холст в фокусе)— сдвиг выбранной на 1 px, Shift + стрелка — на 8 px;
  Delete / Escape / Ctrl+D — удалить / снять выбор / дублировать.
Холст редактора показывает карту вдвое меньше игры (1 px игры = 0.5 px экрана), поэтому справа есть ЛУПА:
она увеличивает в 4 раза область вокруг выбранной детали (или курсора) — смещения на 1 px видны сразу.

Результат пишется в карту, поле "decor" (читает maps.GameMap.draw_decor):
  {"sprite": "environment/wall_1.png", "x": 330, "y": 478, "w": 12, "h": 12, "flip": true, "z": "back"}
x, y — левый верхний угол в пикселях карты (клетка с, р = x // 32, y // 32); w, h — размер в игре;
flip — отразить по горизонтали (по умолчанию нет); z — "back" под клетками карты, иначе поверх них.
"""
import tkinter as tk
from fractions import Fraction
from pathlib import Path
from tkinter import ttk, filedialog

TILE = 32                                   # размер клетки в игре (px)
STEPS = [1, 2, 4, 8, 16, 32]                # шаги привязки, px игры
LAYERS = [("front", "поверх клеток"), ("back", "позади клеток")]
LAYER_LABEL = dict(LAYERS)
SPRITE_DIRS = ("environment", "tiles", "containers", "icons", "weapons", "projectiles")
MAX_SIZE = 1024                             # больше деталь быть не может
LOUPE_S, LOUPE_W, LOUPE_H = 4, 64, 48       # лупа: увеличение, видимая область в px игры
SEL_COLOR, ITEM_COLOR = "#ffd54a", "#6fa8dc"


def _int(v, default):
    try: return int(round(float(str(v).strip().replace(",", "."))))
    except (TypeError, ValueError): return default


class DecorPanel:
    def __init__(self, ed, parent, root, cell, palette=None):
        """ed — Editor; parent — куда положить панель; root — папка игры; cell — размер клетки в редакторе (px)."""
        self.ed, self.cell, self.root = ed, cell, Path(root)
        self.assets = self.root / "assets"
        self.items = []                     # записи деталей (пиксели игры), порядок = порядок рисования
        self.sel = None                     # индекс выбранной детали или None (тогда поля задают «кисть»)
        self.drag = None                    # (dx, dy): где схватили деталь относительно её левого верхнего угла
        self.last_pt = None                 # последняя точка курсора (px игры) — центр лупы, пока ничего не выбрано
        self.mode = tk.BooleanVar(value=False)
        self.sprite_var = tk.StringVar()
        self.w_var, self.h_var = tk.StringVar(value="32"), tk.StringVar(value="32")
        self.x_var, self.y_var = tk.StringVar(), tk.StringVar()
        self.flip_var = tk.BooleanVar(value=False)
        self.layer_var = tk.StringVar(value=LAYER_LABEL["front"])
        self.snap_var = tk.StringVar(value="4")
        self.title_var, self.info_var = tk.StringVar(), tk.StringVar()
        self._base_cache, self._photo_cache, self._cell_cache = {}, {}, {}
        self._busy = False
        self._ui(parent)
        self._bind_keys()
        self._sync_fields()

    # ---------- интерфейс ----------
    def _ui(self, parent):
        box = ttk.LabelFrame(parent, text="Мелкие детали (картинки с точностью до пикселя)", padding=5)
        box.pack(fill="x", pady=(8, 0)); self.box = box
        top = ttk.Frame(box); top.pack(fill="x")
        ttk.Checkbutton(top, text="Режим деталей: ЛКМ — поставить / выбрать и двигать, ПКМ — удалить (клетки не рисуются)",
                        variable=self.mode, command=self._mode_changed).pack(side="left")
        ttk.Label(top, textvariable=self.info_var, foreground="#555").pack(side="right")
        self.body = ttk.Frame(box)          # настройки видны, только пока включён режим
        ttk.Label(self.body, textvariable=self.title_var, font=("Arial", 9, "bold")).pack(anchor="w", pady=(4, 2))
        cols = ttk.Frame(self.body); cols.pack(fill="x")
        ctl = ttk.Frame(cols); ctl.pack(side="left", fill="x", expand=True)
        r1 = ttk.Frame(ctl); r1.pack(fill="x")
        ttk.Label(r1, text="Картинка:").pack(side="left")
        self.sprite_cb = ttk.Combobox(r1, textvariable=self.sprite_var, width=30, values=self._sprite_list())
        self.sprite_cb.pack(side="left", padx=4)
        self.sprite_cb.bind("<<ComboboxSelected>>", lambda e: self._sprite_changed())
        self.sprite_cb.bind("<Return>", lambda e: self._sprite_changed())
        ttk.Button(r1, text="Файл…", command=self._pick_file).pack(side="left")
        r2 = ttk.Frame(ctl); r2.pack(fill="x", pady=(4, 0))
        ttk.Label(r2, text="Размер, px:").pack(side="left")
        for var in (self.w_var, self.h_var):
            sp = ttk.Spinbox(r2, from_=1, to=MAX_SIZE, increment=1, textvariable=var, width=5, command=self._fields_changed)
            sp.pack(side="left", padx=2)
            sp.bind("<FocusOut>", lambda e: self._fields_changed()); sp.bind("<Return>", lambda e: self._fields_changed())
            if var is self.w_var: ttk.Label(r2, text="×").pack(side="left")
        ttk.Button(r2, text="по картинке", command=self._natural_size).pack(side="left", padx=4)
        ttk.Checkbutton(r2, text="отразить", variable=self.flip_var, command=self._fields_changed).pack(side="left", padx=4)
        r3 = ttk.Frame(ctl); r3.pack(fill="x", pady=(4, 0))
        ttk.Label(r3, text="Слой:").pack(side="left")
        lc = ttk.Combobox(r3, textvariable=self.layer_var, state="readonly", width=14, values=[t for _, t in LAYERS])
        lc.pack(side="left", padx=(2, 12)); lc.bind("<<ComboboxSelected>>", lambda e: self._fields_changed())
        ttk.Label(r3, text="Шаг привязки, px:").pack(side="left")
        ttk.Combobox(r3, textvariable=self.snap_var, state="readonly", width=3, values=[str(s) for s in STEPS]).pack(side="left", padx=2)
        r4 = ttk.Frame(ctl); r4.pack(fill="x", pady=(4, 0))
        ttk.Label(r4, text="Положение X, Y (px карты):").pack(side="left")
        for var in (self.x_var, self.y_var):
            en = ttk.Entry(r4, textvariable=var, width=6); en.pack(side="left", padx=2)
            en.bind("<FocusOut>", lambda e: self._fields_changed()); en.bind("<Return>", lambda e: self._fields_changed())
        for text, dx, dy in (("◄", -1, 0), ("►", 1, 0), ("▲", 0, -1), ("▼", 0, 1)):
            ttk.Button(r4, text=text, width=3, command=lambda dx=dx, dy=dy: self.nudge(dx, dy)).pack(side="left", padx=1)
        r5 = ttk.Frame(ctl); r5.pack(fill="x", pady=(4, 0))
        for text, cmd in (("Дублировать", self.duplicate), ("Удалить", self.delete_selected), ("Снять выбор", self.deselect),
                          ("Выше", lambda: self.reorder(1)), ("Ниже", lambda: self.reorder(-1))):
            ttk.Button(r5, text=text, command=cmd).pack(side="left", padx=(0, 4))
        ttk.Label(ctl, text="◄ ► ▲ ▼ и стрелки на клавиатуре (щёлкни по карте, чтобы дать ей фокус) двигают на 1 px, Shift — на 8 px. "
                            "Выше / Ниже — порядок рисования внутри слоя.",
                  wraplength=470, foreground="#555").pack(anchor="w", pady=(4, 0))
        loupe_box = ttk.Frame(cols); loupe_box.pack(side="left", padx=(10, 0), anchor="n")
        ttk.Label(loupe_box, text="Лупа ×%d (яркие линии — клетки, слабые — 4 px)" % LOUPE_S, foreground="#555").pack(anchor="w")
        self.loupe = tk.Canvas(loupe_box, width=LOUPE_W * LOUPE_S, height=LOUPE_H * LOUPE_S, bg="#101016", highlightthickness=1,
                               highlightbackground="#555563")
        self.loupe.pack()

    def _sprite_list(self):
        out = []
        for d in SPRITE_DIRS:
            base = self.assets / d
            if base.is_dir():
                out += sorted(p.relative_to(self.assets).as_posix() for p in base.rglob("*.png"))
        return out[:600]

    def _bind_keys(self):
        c = self.ed.canvas
        for key, dx, dy in (("Left", -1, 0), ("Right", 1, 0), ("Up", 0, -1), ("Down", 0, 1)):
            c.bind("<%s>" % key, lambda e, dx=dx, dy=dy: self._arrow(e, dx, dy), add="+")
        c.bind("<Delete>", lambda e: self._key(self.delete_selected), add="+")
        c.bind("<BackSpace>", lambda e: self._key(self.delete_selected), add="+")
        c.bind("<Escape>", lambda e: self._key(self.deselect), add="+")
        c.bind("<Control-d>", lambda e: self._key(self.duplicate), add="+")
        c.bind("<Motion>", self._motion, add="+")

    def _key(self, fn):
        if not self.active(): return None
        fn(); return "break"

    def _arrow(self, event, dx, dy):
        if not self.active() or self.cur() is None: return None
        k = 8 if event.state & 0x1 else 1
        self.nudge(dx * k, dy * k); return "break"

    # ---------- режим ----------
    def active(self): return bool(self.mode.get())

    def _mode_changed(self):
        if self.mode.get():
            self.ed.morg_mode.set(False)
            if self.ed.cpanel: self.ed.cpanel.mode.set(False)
            self.body.pack(fill="x", pady=(2, 0))
            self.ed.status.set("Режим деталей: ЛКМ — поставить или схватить и двигать, ПКМ — удалить, стрелки — сдвиг на 1 px. Клетки не рисуются.")
        else:
            self.body.pack_forget(); self.sel = None; self.drag = None
            self.ed.status.set("Режим рисования клеток.")
        self._sync_fields(); self.ed._draw_all()

    # ---------- данные ----------
    def cur(self):
        return self.items[self.sel] if self.sel is not None and 0 <= self.sel < len(self.items) else None

    def step(self):
        v = _int(self.snap_var.get(), 1)
        return v if v in STEPS else 1

    def _snap(self, v):
        st = self.step(); return int(round(v / st) * st)

    def _clamp(self, it):
        it["x"] = max(1 - it["w"], min(self.ed.map_w * TILE - 1, it["x"]))
        it["y"] = max(1 - it["h"], min(self.ed.map_h * TILE - 1, it["y"]))

    @staticmethod
    def _clean(d):
        sprite = str(d["sprite"]).replace("\\", "/")
        return {"sprite": sprite, "x": _int(d.get("x", 0), 0), "y": _int(d.get("y", 0), 0),
                "w": max(1, min(MAX_SIZE, _int(d.get("w", TILE), TILE))), "h": max(1, min(MAX_SIZE, _int(d.get("h", TILE), TILE))),
                "flip": bool(d.get("flip", False)), "z": "back" if d.get("z") == "back" else "front"}

    def _brush(self):
        rel = self.sprite_var.get().strip()
        if not rel: return None
        return {"sprite": rel, "x": 0, "y": 0, "w": max(1, min(MAX_SIZE, _int(self.w_var.get(), TILE))),
                "h": max(1, min(MAX_SIZE, _int(self.h_var.get(), TILE))), "flip": bool(self.flip_var.get()),
                "z": next((k for k, t in LAYERS if t == self.layer_var.get()), "front")}

    def _sync_fields(self):
        """Поля панели <- выбранная деталь (или кисть, если ничего не выбрано)."""
        self._busy = True
        it = self.cur()
        if it:
            self.sprite_var.set(it["sprite"]); self.w_var.set(str(it["w"])); self.h_var.set(str(it["h"]))
            self.flip_var.set(bool(it.get("flip"))); self.layer_var.set(LAYER_LABEL[it.get("z", "front")])
            self.x_var.set(str(it["x"])); self.y_var.set(str(it["y"]))
            self.title_var.set("Выбрана деталь №%d — клетка (%d, %d). Поля ниже правят её." % (self.sel + 1, it["x"] // TILE, it["y"] // TILE))
        else:
            self.x_var.set(""); self.y_var.set("")
            self.title_var.set("Деталь не выбрана — поля задают кисть для новых деталей.")
        self.info_var.set("деталей на карте: %d" % len(self.items))
        self._busy = False

    def _fields_changed(self):
        if self._busy: return
        it = self.cur()
        if it is None: return                      # кисть: значения просто лежат в полях
        it["sprite"] = self.sprite_var.get().strip() or it["sprite"]
        it["w"] = max(1, min(MAX_SIZE, _int(self.w_var.get(), it["w"])))
        it["h"] = max(1, min(MAX_SIZE, _int(self.h_var.get(), it["h"])))
        it["flip"] = bool(self.flip_var.get())
        it["z"] = next((k for k, t in LAYERS if t == self.layer_var.get()), "front")
        it["x"] = _int(self.x_var.get(), it["x"]); it["y"] = _int(self.y_var.get(), it["y"])
        self._clamp(it); self._sync_fields(); self._refresh()

    def _sprite_changed(self):
        if self._busy: return
        if self.cur() is None: self._natural_size()        # у кисти размер берём по картинке
        else: self._fields_changed()

    def _natural_size(self):
        base = self._base(self.sprite_var.get().strip())
        if not base:
            self.ed.status.set("Не удалось загрузить картинку: assets/%s" % self.sprite_var.get().strip()); return
        self._busy = True
        self.w_var.set(str(min(base.width(), MAX_SIZE))); self.h_var.set(str(min(base.height(), MAX_SIZE)))
        self._busy = False
        if self.cur() is not None: self._fields_changed()

    def _pick_file(self):
        path = filedialog.askopenfilename(initialdir=self.assets, filetypes=[("PNG", "*.png")])
        if not path: return
        try: rel = Path(path).resolve().relative_to(self.assets.resolve()).as_posix()
        except ValueError:
            self.ed.status.set("Картинка должна лежать внутри папки assets игры."); return
        self.sprite_var.set(rel)
        if rel not in self.sprite_cb["values"]: self.sprite_cb["values"] = list(self.sprite_cb["values"]) + [rel]
        self._sprite_changed()

    # ---------- действия над деталями ----------
    def select(self, i):
        self.sel = i; self._sync_fields(); self._refresh()

    def deselect(self):
        self.sel = None; self.drag = None; self._sync_fields(); self._refresh()

    def nudge(self, dx, dy):
        it = self.cur()
        if it is None: self.ed.status.set("Сначала выбери деталь (ЛКМ по ней)."); return
        it["x"] += dx; it["y"] += dy; self._clamp(it); self._sync_fields(); self._refresh()
        self.ed.status.set("Деталь №%d: x=%d, y=%d" % (self.sel + 1, it["x"], it["y"]))

    def duplicate(self):
        it = self.cur()
        if it is None: return
        cp = dict(it); off = max(4, self.step()); cp["x"] += off; cp["y"] += off; self._clamp(cp)
        self.items.append(cp); self.select(len(self.items) - 1)

    def delete_selected(self):
        if self.cur() is None: return
        del self.items[self.sel]; self.sel = None; self.drag = None
        self._sync_fields(); self._refresh()

    def reorder(self, d):
        j = None if self.sel is None else self.sel + d
        if j is None or not 0 <= j < len(self.items): return
        self.items[self.sel], self.items[j] = self.items[j], self.items[self.sel]
        self.sel = j; self._sync_fields(); self._refresh()

    # ---------- мышь ----------
    def _point(self, event):
        s = self.cell / TILE
        return self.ed.canvas.canvasx(event.x) / s, self.ed.canvas.canvasy(event.y) / s

    def hit(self, p):
        """Индекс верхней детали под точкой p (px игры) или None. Верхние: слой «поверх», затем поздние в списке."""
        order = sorted(range(len(self.items)), key=lambda i: (self.items[i].get("z") != "back", i))
        for i in reversed(order):
            it = self.items[i]
            if it["x"] <= p[0] < it["x"] + it["w"] and it["y"] <= p[1] < it["y"] + it["h"]: return i
        return None

    def press(self, event):
        self.ed.canvas.focus_set()
        p = self._point(event); self.last_pt = p
        i = None if event.state & 0x4 else self.hit(p)          # Ctrl — всегда новая деталь
        if i is not None:
            it = self.items[i]; self.drag = (p[0] - it["x"], p[1] - it["y"]); self.select(i)
            self.ed.status.set("Деталь №%d: x=%d, y=%d (тяни мышью, стрелки — 1 px)" % (i + 1, it["x"], it["y"])); return
        spec = self._brush()
        if spec is None:
            self.ed.status.set("Сначала выбери картинку в поле «Картинка»."); return
        spec["x"] = self._snap(p[0] - spec["w"] / 2); spec["y"] = self._snap(p[1] - spec["h"] / 2)
        self._clamp(spec)
        self.items.append(spec); self.drag = (p[0] - spec["x"], p[1] - spec["y"]); self.select(len(self.items) - 1)
        self.ed.status.set("Поставлена деталь №%d: x=%d, y=%d" % (len(self.items), spec["x"], spec["y"]))

    def motion_drag(self, event):
        it = self.cur()
        if self.drag is None or it is None: return
        p = self._point(event); self.last_pt = p
        it["x"] = self._snap(p[0] - self.drag[0]); it["y"] = self._snap(p[1] - self.drag[1]); self._clamp(it)
        self._sync_fields(); self._refresh()

    def release(self, event=None):
        if self.drag is not None and self.cur() is not None:
            it = self.cur(); self.ed.status.set("Деталь №%d: x=%d, y=%d" % (self.sel + 1, it["x"], it["y"]))
        self.drag = None

    def erase(self, event):
        i = self.hit(self._point(event))
        if i is None: return
        del self.items[i]
        if self.sel == i: self.sel = None
        elif self.sel is not None and self.sel > i: self.sel -= 1
        self.drag = None; self._sync_fields(); self._refresh()
        self.ed.status.set("Деталь удалена. Осталось: %d" % len(self.items))

    def _motion(self, event):
        if not self.active() or self.drag is not None or self.cur() is not None: return
        self.last_pt = self._point(event); self.draw_loupe()

    # ---------- картинки (Tk PhotoImage, без Pillow) ----------
    def _base(self, rel):
        if rel not in self._base_cache:
            try: self._base_cache[rel] = tk.PhotoImage(file=str(self.assets / rel))
            except (tk.TclError, OSError): self._base_cache[rel] = None
        return self._base_cache[rel]

    def _photo(self, rel, tw, th, flip=False):
        """Картинка assets/rel размером tw x th экранных пикселей (дробным масштабом: zoom / subsample) или None."""
        key = (rel, tw, th, bool(flip))
        if key in self._photo_cache: return self._photo_cache[key]
        if len(self._photo_cache) > 400: self._photo_cache.clear()
        img, base = None, self._base(rel)
        if base:
            nw, nh = base.width(), base.height()
            fx, fy = Fraction(tw, nw).limit_denominator(16), Fraction(th, nh).limit_denominator(16)
            ax, ay, bx, by = max(1, fx.numerator), max(1, fy.numerator), max(1, fx.denominator), max(1, fy.denominator)
            try:
                if nw * ax * nh * ay > 4_000_000:                      # слишком большая промежуточная картинка
                    img = base.subsample(max(1, nw // max(1, tw)), max(1, nh // max(1, th)))
                else:
                    img = base.zoom(ax, ay)
                    if bx > 1 or by > 1: img = img.subsample(bx, by)
                if flip:
                    try: img = img.subsample(-1, 1)                    # отрицательный subsample зеркалит картинку
                    except tk.TclError: pass
            except tk.TclError: img = None
        self._photo_cache[key] = img
        return img

    # ---------- рисование ----------
    def _refresh(self):
        self.redraw_items(); self.draw_loupe()

    def draw(self):
        """Вызывается из Editor._draw_all после клеток."""
        self.redraw_items(); self.draw_loupe()

    def redraw_items(self):
        c, s = self.ed.canvas, self.cell / TILE
        c.delete("decor")
        for i, it in enumerate(self.items):
            x0, y0 = it["x"] * s, it["y"] * s
            x1, y1 = x0 + it["w"] * s, y0 + it["h"] * s
            tags = ("decor", "decor_back" if it.get("z") == "back" else "decor_front")
            img = self._photo(it["sprite"], max(1, round(it["w"] * s)), max(1, round(it["h"] * s)), it.get("flip"))
            if img: c.create_image(x0, y0, image=img, anchor="nw", tags=tags)
            else:
                c.create_rectangle(x0, y0, x1, y1, outline="#ff6a6a", dash=(2, 2), tags=tags)
                c.create_text((x0 + x1) / 2, (y0 + y1) / 2, text="?", fill="#ff6a6a", tags=tags)
            if self.active():
                sel = i == self.sel
                c.create_rectangle(x0, y0, x1, y1, outline=SEL_COLOR if sel else ITEM_COLOR, width=2 if sel else 1,
                                   dash=() if sel else (2, 2), tags=("decor",))
        c.tag_lower("decor_back"); c.tag_lower("background")      # «позади клеток» — под клетками и над фоном

    def _cell_image(self, ch):
        """Превью клетки в лупе: 16-пиксельная картинка палитры, увеличенная до TILE*LOUPE_S."""
        if ch not in self._cell_cache:
            base = self.ed.sprite_images.get(ch)
            img = None
            if base:
                try: img = base.zoom(max(1, TILE * LOUPE_S // max(1, base.width())), max(1, TILE * LOUPE_S // max(1, base.height())))
                except tk.TclError: img = None
            self._cell_cache[ch] = img
        return self._cell_cache[ch]

    def _loupe_item(self, c, it, x0, y0, sel=False):
        S = LOUPE_S
        lx, ly = (it["x"] - x0) * S, (it["y"] - y0) * S
        lw, lh = it["w"] * S, it["h"] * S
        if lx > LOUPE_W * S or ly > LOUPE_H * S or lx + lw < 0 or ly + lh < 0: return
        img = self._photo(it["sprite"], lw, lh, it.get("flip")) if lw * lh <= 4_000_000 else None
        if img: c.create_image(lx, ly, image=img, anchor="nw")
        else: c.create_rectangle(lx, ly, lx + lw, ly + lh, outline="#ff6a6a", dash=(2, 2))
        if sel: c.create_rectangle(lx, ly, lx + lw, ly + lh, outline=SEL_COLOR, width=1)

    def draw_loupe(self):
        c, S, ed = self.loupe, LOUPE_S, self.ed
        c.delete("all")
        it = self.cur()
        if it: cx, cy = it["x"] + it["w"] / 2, it["y"] + it["h"] / 2
        elif self.last_pt: cx, cy = self.last_pt
        else: cx, cy = TILE, TILE
        x0, y0 = cx - LOUPE_W / 2, cy - LOUPE_H / 2
        for i, d in enumerate(self.items):                                # позади клеток
            if d.get("z") == "back": self._loupe_item(c, d, x0, y0, d is it)
        c0, c1 = int(x0 // TILE), int((x0 + LOUPE_W) // TILE)
        r0, r1 = int(y0 // TILE), int((y0 + LOUPE_H) // TILE)
        for r in range(r0, r1 + 1):
            for col in range(c0, c1 + 1):
                if not (0 <= r < ed.map_h and 0 <= col < ed.map_w): continue
                ch = ed.rows[r][col]
                if ch == ".": continue
                lx, ly = (col * TILE - x0) * S, (r * TILE - y0) * S
                img = self._cell_image(ch)
                if img: c.create_image(lx, ly, image=img, anchor="nw")
                else: c.create_rectangle(lx, ly, lx + TILE * S, ly + TILE * S, fill=ed._cell_color(ch), outline="")
        for d in self.items:                                                # поверх клеток
            if d.get("z") != "back": self._loupe_item(c, d, x0, y0, d is it)
        # сетка: линии клеток ярче, каждые 4 px — слабые
        g0, g1 = int(x0) - 1, int(x0 + LOUPE_W) + 1
        for gx in range(g0 - g0 % 4, g1 + 1, 4):
            if gx % TILE == 0: c.create_line((gx - x0) * S, 0, (gx - x0) * S, LOUPE_H * S, fill="#7d7d96")
            else: c.create_line((gx - x0) * S, 0, (gx - x0) * S, LOUPE_H * S, fill="#2a2a38")
        g0, g1 = int(y0) - 1, int(y0 + LOUPE_H) + 1
        for gy in range(g0 - g0 % 4, g1 + 1, 4):
            if gy % TILE == 0: c.create_line(0, (gy - y0) * S, LOUPE_W * S, (gy - y0) * S, fill="#7d7d96")
            else: c.create_line(0, (gy - y0) * S, LOUPE_W * S, (gy - y0) * S, fill="#2a2a38")
        if it:
            c.create_text(4, 4, anchor="nw", fill=SEL_COLOR, text="x=%d  y=%d  (%d×%d)" % (it["x"], it["y"], it["w"], it["h"]))
        elif self.last_pt:
            c.create_text(4, 4, anchor="nw", fill="#aaaabb", text="курсор: x=%d  y=%d" % (self.last_pt[0], self.last_pt[1]))

    # ---------- файл карты ----------
    def load(self, data):
        self.items = []; self.sel = None; self.drag = None
        for d in data or []:
            if not isinstance(d, dict) or not d.get("sprite"): continue
            try: self.items.append(self._clean(d))
            except (TypeError, ValueError, KeyError): continue
        self._sync_fields()

    def dump(self):
        """Список деталей для файла карты (только непустые поля: flip — если отражена, z — если «позади»)."""
        out = []
        for it in self.items:
            d = {"sprite": it["sprite"], "x": int(it["x"]), "y": int(it["y"]), "w": int(it["w"]), "h": int(it["h"])}
            if it.get("flip"): d["flip"] = True
            if it.get("z") == "back": d["z"] = "back"
            out.append(d)
        return out

    def crop(self, w, h):
        """Карта изменила размер до w x h клеток: детали целиком за краем убираем."""
        self.items = [it for it in self.items if it["x"] < w * TILE and it["y"] < h * TILE
                      and it["x"] + it["w"] > 0 and it["y"] + it["h"] > 0]
        self.sel = None; self.drag = None; self._sync_fields()

    def reset(self):
        self.items = []; self.sel = None; self.drag = None; self._sync_fields()
