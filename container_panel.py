"""Панель «Ящики и сундуки» редактора карт (map_editor.py): расстановка и содержимое.

Включи «Режим ящиков» — и на карте:
  ЛКМ по пустой клетке  — поставить ящик с настройками «кисти» (тип, шанс появления, содержимое);
  ЛКМ по ящику          — выбрать его: панель покажет и позволит менять его настройки;
  ПКМ по ящику          — убрать.
Ящик ставится так, что нажатая клетка — его нижняя левая клетка (ящик 2×2 займёт эту клетку, клетку справа и две вверх).
Содержимое: пункты «предмет — шанс — сколько штук». Пока своего списка нет, ящик берёт содержимое типа из data/containers.json.
Результат пишется в карту, поле "containers" (формат — в containers.py).
"""
import copy
import json
import tkinter as tk
from tkinter import ttk, messagebox

RANDOM = "random_weapon"
MODES = [("independent", "каждый предмет бросает свой шанс"), ("pick_one", "выпадает не более одного предмета")]
MODE_LABEL = dict(MODES)
BLOCKING = ("wall", "ladder")            # такие клетки ящиком не занять
BLOCKING_MARKS = ("player", "exit", "boss")   # и клетки со стартом игрока, выходом, боссом

def hexc(rgb):
    try: return "#%02x%02x%02x" % tuple(max(0, min(255, int(v))) for v in rgb[:3])
    except (TypeError, ValueError): return "#aa7744"

def clean_loot(loot):
    """Список пунктов содержимого без мусора: у каждого item, chance 0..1, min >= 1, max >= min."""
    out = []
    for e in loot or []:
        if not isinstance(e, dict) or not e.get("item"): continue
        lo = max(1, int(e.get("min", 1))); hi = max(lo, int(e.get("max", lo)))
        item = {"item": str(e["item"]), "chance": round(max(0.0, min(1.0, float(e.get("chance", 1)))), 4)}
        if lo != 1 or hi != 1: item["min"], item["max"] = lo, hi
        out.append(item)
    return out

def clean_spec(spec):
    """Запись ящика для файла карты: только то, что отличается от умолчаний."""
    out = {"type": spec["type"], "x": int(spec["x"]), "y": int(spec["y"])}
    if spec.get("chance") is not None and float(spec["chance"]) < 1: out["chance"] = round(max(0.0, float(spec["chance"])), 4)
    if spec.get("hp") not in (None, ""): out["hp"] = float(spec["hp"]) if float(spec["hp"]) % 1 else int(spec["hp"])
    if spec.get("loot_mode") in MODE_LABEL: out["loot_mode"] = spec["loot_mode"]
    if spec.get("loot") is not None: out["loot"] = clean_loot(spec["loot"])
    return out


class ContainerPanel:
    def __init__(self, ed, parent, root, cell, palette):
        """ed — Editor; parent — куда положить панель; root — папка игры; cell — размер клетки в редакторе (px);
        palette — PALETTE редактора (символ, название, запись легенды): по ней определяем, куда ящик ставить нельзя."""
        self.ed, self.cell, self.root = ed, cell, root
        self.types, self.items = self._load_types(), self._load_items()
        self.sel = None                                  # индекс выбранного ящика в ed.containers или None (тогда правится «кисть»)
        first = next(iter(self.types), "")
        self.brush = {"type": first, "chance": 1.0, "loot_mode": None, "loot": None, "hp": None}
        self.blocked = {ch for ch, _, d in palette if d.get("type") in BLOCKING or any(k in d for k in BLOCKING_MARKS)}
        self.mode = tk.BooleanVar(value=False)
        self.type_var, self.chance_var, self.hp_var = tk.StringVar(), tk.StringVar(value="100"), tk.StringVar()
        self.lmode_var = tk.StringVar(value=MODES[0][1])
        self.item_var, self.pct_var, self.min_var, self.max_var = tk.StringVar(), tk.StringVar(value="50"), tk.StringVar(value="1"), tk.StringVar(value="1")
        self.title_var, self.info_var = tk.StringVar(), tk.StringVar()
        self._busy = False
        self._ui(parent)
        self._load_fields()

    # ---------- данные игры ----------
    def _read(self, rel):
        try: return json.loads((self.root / rel).read_text(encoding="utf-8"))
        except (OSError, ValueError): return {}

    def _load_types(self):
        d = self._read("data/containers.json").get("containers", {})
        return {tid: v for tid, v in d.items() if isinstance(v, dict)}

    def _load_items(self):
        """Предметы, которые можно положить в ящик: подпись -> id (оружие, предметы инвентаря, случайное оружие)."""
        out = {"Случайное оружие  [%s]" % RANDOM: RANDOM}
        for wid, w in sorted(self._read("data/weapons.json").items()):
            if isinstance(w, dict) and not wid.startswith("_"): out["%s  [%s]" % (w.get("name", wid), wid)] = wid
        for wid, it in sorted((self._read("assets/inventory.json").get("items") or {}).items()):
            if isinstance(it, dict) and wid not in {v for v in out.values()}: out["%s  [%s]" % (it.get("name", wid), wid)] = wid
        return out

    def type_label(self, tid): return "%s  [%s]" % (self.types.get(tid, {}).get("name", tid), tid)
    def type_from_label(self, label):
        label = label.strip(); return label[label.rindex("[") + 1:-1] if "[" in label and label.endswith("]") else label
    def item_label(self, wid): return next((k for k, v in self.items.items() if v == wid), wid)
    def item_from_label(self, label): return self.items.get(label.strip(), label.strip())
    def type_size(self, tid):
        d = self.types.get(tid, {}); return max(1, int(d.get("w", 1))), max(1, int(d.get("h", 1)))
    def default_loot(self, tid): return clean_loot(self.types.get(tid, {}).get("loot"))

    # ---------- интерфейс ----------
    def _ui(self, parent):
        box = ttk.LabelFrame(parent, text="Ящики и сундуки (расстановка и содержимое)", padding=5)
        box.pack(fill="x", pady=(8, 0)); self.box = box
        top = ttk.Frame(box); top.pack(fill="x")
        ttk.Checkbutton(top, text="Режим ящиков: ЛКМ — поставить / выбрать, ПКМ — убрать (клетки не рисуются)", variable=self.mode, command=self._mode_changed).pack(side="left")
        ttk.Label(top, textvariable=self.info_var, foreground="#555").pack(side="right")
        ttk.Label(box, textvariable=self.title_var, font=("Arial", 9, "bold")).pack(anchor="w", pady=(4, 2))
        row = ttk.Frame(box); row.pack(fill="x")
        ttk.Label(row, text="Тип:").pack(side="left")
        self.type_cb = ttk.Combobox(row, textvariable=self.type_var, state="readonly", width=26, values=[self.type_label(t) for t in self.types])
        self.type_cb.pack(side="left", padx=4); self.type_cb.bind("<<ComboboxSelected>>", lambda e: self._fields_changed())
        ttk.Label(row, text="Шанс появления, %:").pack(side="left", padx=(8, 0))
        ch = ttk.Spinbox(row, from_=0, to=100, increment=5, textvariable=self.chance_var, width=5, command=self._fields_changed); ch.pack(side="left", padx=4)
        ttk.Label(row, text="HP (пусто — как у типа):").pack(side="left", padx=(8, 0))
        hp = ttk.Entry(row, textvariable=self.hp_var, width=6); hp.pack(side="left", padx=4)
        for w in (ch, hp): w.bind("<FocusOut>", lambda e: self._fields_changed()); w.bind("<Return>", lambda e: self._fields_changed())
        row2 = ttk.Frame(box); row2.pack(fill="x", pady=(4, 0))
        ttk.Label(row2, text="Выпадение:").pack(side="left")
        self.lmode_cb = ttk.Combobox(row2, textvariable=self.lmode_var, state="readonly", width=38, values=[t for _, t in MODES])
        self.lmode_cb.pack(side="left", padx=4); self.lmode_cb.bind("<<ComboboxSelected>>", lambda e: self._fields_changed())
        ttk.Button(row2, text="Снять выбор (править кисть)", command=self.deselect).pack(side="right")
        body = ttk.Frame(box); body.pack(fill="x", pady=(6, 0))
        left = ttk.Frame(body); left.pack(side="left", fill="x", expand=True)
        self.tree = ttk.Treeview(left, columns=("item", "pct", "min", "max"), show="headings", height=4, selectmode="browse")
        for col, text, w in (("item", "Предмет", 230), ("pct", "Шанс %", 60), ("min", "От", 40), ("max", "До", 40)):
            self.tree.heading(col, text=text); self.tree.column(col, width=w, anchor="w" if col == "item" else "center")
        sb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview); self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="x", expand=True); sb.pack(side="left", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._row_selected())
        form = ttk.Frame(body); form.pack(side="left", padx=(10, 0), anchor="n")
        ttk.Label(form, text="Предмет:").grid(row=0, column=0, sticky="w")
        self.item_cb = ttk.Combobox(form, textvariable=self.item_var, width=34, values=list(self.items)); self.item_cb.grid(row=0, column=1, columnspan=4, sticky="we", padx=4)
        ttk.Label(form, text="Шанс, %:").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Spinbox(form, from_=0, to=100, increment=5, textvariable=self.pct_var, width=5).grid(row=1, column=1, sticky="w", padx=4)
        ttk.Label(form, text="Штук от").grid(row=1, column=2, sticky="e"); ttk.Spinbox(form, from_=1, to=20, textvariable=self.min_var, width=3).grid(row=1, column=3, padx=2)
        ttk.Label(form, text="до").grid(row=1, column=4, sticky="e"); ttk.Spinbox(form, from_=1, to=20, textvariable=self.max_var, width=3).grid(row=1, column=5, padx=2)
        btns = ttk.Frame(form); btns.grid(row=2, column=0, columnspan=6, sticky="w", pady=(4, 0))
        ttk.Button(btns, text="Добавить", command=self.add_entry).pack(side="left")
        ttk.Button(btns, text="Заменить выбранный", command=self.replace_entry).pack(side="left", padx=4)
        ttk.Button(btns, text="Удалить", command=self.delete_entry).pack(side="left")
        ttk.Button(btns, text="Как у типа", command=self.reset_loot).pack(side="left", padx=4)
        ttk.Label(box, text="Шанс 100% — предмет выпадает всегда. «Один из»: шансы — доли от 100% (в сумме не больше 100). "
                            "Нет своего списка — ящик берёт содержимое типа из data/containers.json. Список предметов — оружие и вещи из assets/inventory.json -> items; можно вписать и свой id.",
                  wraplength=900, foreground="#555").pack(anchor="w", pady=(4, 0))

    # ---------- кисть / выбранный ящик ----------
    def active(self): return bool(self.mode.get())

    def _mode_changed(self):
        if self.mode.get():
            self.ed.morg_mode.set(False)
            dp = getattr(self.ed, "dpanel", None)
            if dp: dp.mode.set(False); dp.body.pack_forget(); dp.sel = None
            self.ed.status.set("Режим ящиков: ЛКМ — поставить ящик (по настройкам кисти) или выбрать, ПКМ — убрать.")
        self._refresh()

    def cur(self):
        """Настройки, которые сейчас правит панель: выбранный на карте ящик или кисть для новых."""
        if self.sel is not None and 0 <= self.sel < len(self.ed.containers): return self.ed.containers[self.sel]
        self.sel = None; return self.brush

    def deselect(self): self.sel = None; self._load_fields(); self._refresh()

    def _load_fields(self):
        """Показать настройки cur() в полях панели."""
        c = self.cur(); self._busy = True
        try:
            tid = c.get("type", ""); self.type_var.set(self.type_label(tid) if tid else "")
            self.chance_var.set(str(int(round(float(c.get("chance", 1.0)) * 100))))
            self.hp_var.set("" if c.get("hp") in (None, "") else str(c["hp"]))
            self.lmode_var.set(MODE_LABEL.get(c.get("loot_mode") or self.types.get(tid, {}).get("loot_mode", "independent"), MODES[0][1]))
        finally: self._busy = False
        self._fill_tree()
        if self.sel is None: self.title_var.set("Кисть: настройки для НОВЫХ ящиков. Выбери ящик на карте, чтобы править его самого.")
        else:
            c = self.ed.containers[self.sel]; self.title_var.set("Выбран ящик №%d: «%s», клетка (%d, %d)" % (self.sel + 1, self.types.get(c["type"], {}).get("name", c["type"]), c["x"], c["y"]))

    def _fields_changed(self):
        """Поля панели -> настройки кисти или выбранного ящика."""
        if self._busy: return
        c = self.cur(); tid = self.type_from_label(self.type_var.get())
        if tid in self.types:
            if tid != c.get("type"): c["type"] = tid; c["loot"] = None if self.sel is None else c.get("loot")
        try: c["chance"] = max(0.0, min(1.0, float(self.chance_var.get()) / 100))
        except ValueError: pass
        hp = self.hp_var.get().strip()
        try: c["hp"] = float(hp) if hp else None
        except ValueError: pass
        c["loot_mode"] = next((k for k, t in MODES if t == self.lmode_var.get()), None)
        if c["loot_mode"] == self.types.get(c.get("type"), {}).get("loot_mode", "independent") and c.get("loot") is None: c["loot_mode"] = None
        self._fill_tree(); self._refresh()

    # ---------- таблица содержимого ----------
    def effective_loot(self):
        c = self.cur(); return clean_loot(c["loot"]) if c.get("loot") is not None else self.default_loot(c.get("type"))

    def _fill_tree(self, select=None):
        self.tree.delete(*self.tree.get_children())
        for i, e in enumerate(self.effective_loot()):
            self.tree.insert("", "end", iid=str(i), values=(self.item_label(e["item"]), "%g" % round(e["chance"] * 100, 2), e.get("min", 1), e.get("max", e.get("min", 1))))
        own = self.cur().get("loot") is not None
        self.info_var.set(("своё содержимое" if own else "содержимое типа по умолчанию") + (" (пока пусто)" if not self.effective_loot() else ""))
        if select is not None and str(select) in self.tree.get_children(): self.tree.selection_set(str(select))

    def _row_selected(self):
        sel = self.tree.selection()
        if not sel: return
        e = self.effective_loot()[int(sel[0])]
        self.item_var.set(self.item_label(e["item"])); self.pct_var.set("%g" % round(e["chance"] * 100, 2)); self.min_var.set(str(e.get("min", 1))); self.max_var.set(str(e.get("max", e.get("min", 1))))

    def _entry_from_form(self):
        item = self.item_from_label(self.item_var.get())
        if not item: messagebox.showerror("Ящики", "Выбери предмет."); return None
        try:
            pct = float(self.pct_var.get().replace(",", ".")); lo = int(self.min_var.get()); hi = int(self.max_var.get())
        except ValueError: messagebox.showerror("Ящики", "Шанс и количество — числа."); return None
        if not 0 <= pct <= 100: messagebox.showerror("Ящики", "Шанс — от 0 до 100 %."); return None
        return {"item": item, "chance": pct / 100, "min": max(1, lo), "max": max(1, lo, hi)}

    def _own_loot(self):
        """Своё содержимое cur(): первая правка копирует содержимое типа, чтобы дальше менять его."""
        c = self.cur()
        if c.get("loot") is None: c["loot"] = copy.deepcopy(self.default_loot(c.get("type")))
        return c["loot"]

    def add_entry(self):
        e = self._entry_from_form()
        if e is None: return
        loot = self._own_loot(); loot.append(e); self._after_loot(len(loot) - 1)

    def replace_entry(self):
        sel = self.tree.selection(); e = self._entry_from_form()
        if not sel or e is None:
            if not sel: messagebox.showinfo("Ящики", "Выбери строку в таблице.")
            return
        loot = self._own_loot(); loot[int(sel[0])] = e; self._after_loot(int(sel[0]))

    def delete_entry(self):
        sel = self.tree.selection()
        if not sel: return
        loot = self._own_loot(); del loot[int(sel[0])]; self._after_loot(None)

    def reset_loot(self):
        self.cur()["loot"] = None; self._after_loot(None)

    def _after_loot(self, select):
        self._fill_tree(select); self._refresh()

    # ---------- карта ----------
    def cells_of(self, spec):
        w, h = self.type_size(spec["type"]); return [(spec["x"] + i, spec["y"] - j) for j in range(h) for i in range(w)]

    def at(self, x, y):
        for i, s in enumerate(self.ed.containers):
            if (x, y) in self.cells_of(s): return i
        return None

    def can_place(self, spec):
        """(можно, причина): ящик целиком на карте, не на стене/выходе/старте и не поверх другого ящика."""
        cells = self.cells_of(spec)
        for x, y in cells:
            if not (0 <= x < self.ed.map_w and 0 <= y < self.ed.map_h): return False, "ящик не помещается на карту"
            ch = self.ed.rows[y][x]
            if ch in self.blocked or ch in self._blocking_custom(): return False, "здесь стена, лестница, выход или старт"
            if self.at(x, y) is not None: return False, "здесь уже стоит ящик"
        return True, ""

    def _blocking_custom(self):
        leg = self.ed.meta.get("legend", {}) if isinstance(self.ed.meta, dict) else {}
        return {ch for ch, d in leg.items() if isinstance(d, dict) and (d.get("type") in BLOCKING or any(k in d for k in BLOCKING_MARKS))}

    def click(self, event):
        x, y = self.ed._cell_from_event(event)
        if not (0 <= x < self.ed.map_w and 0 <= y < self.ed.map_h): return
        i = self.at(x, y)
        if i is not None:
            self.sel = i; self._load_fields(); self._refresh()
            self.ed.status.set("Выбран ящик №%d. Меняй настройки в панели ниже; ПКМ — убрать." % (i + 1)); return
        tid = self.brush.get("type")
        if tid not in self.types: messagebox.showerror("Ящики", "Нет типов ящиков: проверь data/containers.json."); return
        spec = {"type": tid, "x": x, "y": y}
        for k in ("chance", "hp", "loot_mode"):
            if self.brush.get(k) is not None: spec[k] = self.brush[k]
        if self.brush.get("loot") is not None: spec["loot"] = copy.deepcopy(self.brush["loot"])
        ok, why = self.can_place(spec)
        if not ok: self.ed.status.set("Сюда ящик не поставить: " + why + "."); return
        self.ed.containers.append(spec); self._refresh()
        self.ed.status.set("Поставлен «%s» в клетку (%d, %d). Всего ящиков: %d." % (self.types[tid].get("name", tid), x, y, len(self.ed.containers)))

    def erase(self, event):
        x, y = self.ed._cell_from_event(event); i = self.at(x, y)
        if i is None: return
        del self.ed.containers[i]
        if self.sel is not None: self.sel = None if self.sel == i else (self.sel - 1 if self.sel > i else self.sel)
        self._load_fields(); self._refresh(); self.ed.status.set("Ящик убран. Осталось: %d." % len(self.ed.containers))

    def _refresh(self): self.ed._draw_all()

    def draw(self):
        """Ящики поверх сетки: цвет типа, подпись, шанс появления; выбранный — белая рамка."""
        cv, cs = self.ed.canvas, self.cell
        for i, s in enumerate(self.ed.containers):
            w, h = self.type_size(s["type"]); d = self.types.get(s["type"], {})
            x0, y0 = s["x"] * cs, (s["y"] - h + 1) * cs; x1, y1 = x0 + w * cs, y0 + h * cs
            cv.create_rectangle(x0 + 1, y0 + 1, x1 - 1, y1 - 1, fill=hexc(d.get("color", [170, 120, 60])), outline="#ffffff" if i == self.sel else "#3a2a18", width=3 if i == self.sel else 2, tags=("ct",))
            label = (d.get("name") or s["type"])[:1].upper()
            pct = int(round(float(s.get("chance", 1.0)) * 100))
            cv.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=label if pct >= 100 else "%s %d%%" % (label, pct), fill="#1a1208", font=("Arial", 8 if pct < 100 else 10, "bold"), tags=("ct",))

    # ---------- сохранение / загрузка / правки карты ----------
    def load(self, containers):
        """Ящики из файла карты. Неизвестные типы остаются как есть (их просто не будет видно в игре)."""
        self.ed.containers = []
        for s in containers or []:
            if isinstance(s, dict) and "type" in s and "x" in s and "y" in s:
                try: spec = {"type": str(s["type"]), "x": int(s["x"]), "y": int(s["y"])}
                except (TypeError, ValueError): continue
                for k in ("chance", "hp", "loot_mode"):
                    if k in s: spec[k] = s[k]
                if isinstance(s.get("loot"), list): spec["loot"] = copy.deepcopy(s["loot"])
                self.ed.containers.append(spec)
        self.sel = None; self._load_fields()

    def dump(self):
        """Ящики для записи в карту (или пустой список)."""
        return [clean_spec(s) for s in self.ed.containers]

    def crop(self, w, h):
        """После изменения размера карты: убрать ящики, которые не помещаются."""
        keep = [s for s in self.ed.containers if all(0 <= x < w and 0 <= y < h for x, y in self.cells_of(s))]
        if len(keep) != len(self.ed.containers): self.ed.status.set("Убрано ящиков за краем карты: %d." % (len(self.ed.containers) - len(keep)))
        self.ed.containers = keep; self.sel = None; self._load_fields()

    def reset(self):
        self.ed.containers = []; self.sel = None; self._load_fields()
