"""Панель «Механизмы» редактора карт (map_editor.py): рычаги, кнопки, двери, лифты, телепорты, платформы.

Включи «Режим механизмов» — и на карте:
  ЛКМ по пустой клетке — поставить механизм (с настройками кисти);
  ЛКМ по механизму      — выбрать его: панель покажет и позволит менять его настройки;
  ПКМ по механизму      — убрать.
Для подвижной платформы (тип «mover») ЛКМ добавляет точку пути: поставь платформу, затем кликами
по клеткам нарисуй маршрут (точки-клетки). Точки видны списком и как звёзды на карте.

Связь: у рычага/кнопки задай «Канал», у двери/лифта/портала/платформы — тот же «Канал».
Чтобы каждый механизм имел СВОЮ кнопку, дай паре уникальное имя канала (или идентификатор).
Портал связывается с партнёром полем «Пара (id)» — работает только со своим партнёром.
Результат пишется в карту, поле "mechanisms" (формат — mechs.py).
"""
import copy
import json
import tkinter as tk
from tkinter import ttk, messagebox

MECH_TYPES = ("lever", "button", "door", "elevator", "teleporter", "mover")
TYPE_LABEL = {"lever": "Рычаг", "button": "Кнопка", "door": "Дверь", "elevator": "Лифт",
              "teleporter": "Телепорт", "mover": "Подвижная платформа"}
ROWS_NEEDED = {"door": 0, "teleporter": 0}   # высота в клетках по умолчанию (h)

def hexc(rgb):
    try: return "#%02x%02x%02x" % tuple(max(0, min(255, int(v))) for v in rgb[:3])
    except (TypeError, ValueError): return "#8a8a9a"


def clean_spec(s):
    """Запись механизма для файла карты: только то, что отличается от умолчаний."""
    out = {"id": int(s["id"]), "type": s["type"], "x": int(s["x"]), "y": int(s["y"])}
    if s.get("channel"): out["channel"] = s["channel"]
    if s.get("w", 0) and int(s["w"]) != 1: out["w"] = int(s["w"])
    if s.get("h", 0) and int(s["h"]) != 1: out["h"] = int(s["h"])
    if s.get("range") is not None and int(s.get("range", 0)) != 0: out["range"] = int(s["range"])
    if s.get("mode"): out["mode"] = s["mode"]
    if s.get("speed") is not None and float(s.get("speed", 60)) != 60: out["speed"] = round(float(s["speed"]), 2)
    if s.get("pair") is not None: out["pair"] = int(s["pair"])
    if s.get("path") and len(s["path"]) > 1: out["path"] = [[int(p[0]), int(p[1])] for p in s["path"]]
    if s.get("loop"): out["loop"] = True
    return out


class MechPanel:
    def __init__(self, ed, parent, root, cell, palette):
        """ed — Editor; parent — куда положить панель; root — папка игры; cell — размер клетки в редакторе (px)."""
        self.ed, self.cell, self.root = ed, cell, root
        self.types = self._load_types()
        self.sel = None                                  # индекс выбранного механизма в ed.mechs или None (кисть)
        self.next_id = 1
        self.brush = {"type": "lever", "x": 0, "y": 0, "id": 0, "channel": "ch1", "w": 1, "h": 1,
                      "range": 4, "mode": "control", "speed": 60.0, "pair": None, "path": [], "loop": True}
        self.mode = tk.BooleanVar(value=False)
        self.path_mode = tk.BooleanVar(value=False)      # ЛКМ добавляет точку пути платформы
        self.type_var = tk.StringVar(value="Рычаг")
        self.ch_var = tk.StringVar(value="ch1")
        self.w_var = tk.StringVar(value="1"); self.h_var = tk.StringVar(value="1")
        self.range_var = tk.StringVar(value="4"); self.speed_var = tk.StringVar(value="60")
        self.mode_var = tk.StringVar(value="control")
        self.pair_var = tk.StringVar(value="")
        self.loop_var = tk.BooleanVar(value=True)
        self.title_var = tk.StringVar(); self.info_var = tk.StringVar()
        self._busy = False
        self._ui(parent)
        self._load_fields()

    # ---------- данные игры ----------
    def _read(self, rel):
        try: return json.loads((self.root / rel).read_text(encoding="utf-8"))
        except (OSError, ValueError): return {}

    def _load_types(self):
        d = self._read("data/mechs.json").get("mechs", {})
        return {tid: v for tid, v in d.items() if isinstance(v, dict)}

    def type_label(self, tid): return "%s [%s]" % (TYPE_LABEL.get(tid, tid), tid)
    def type_from_label(self, label):
        label = label.strip(); return label[label.rindex("[") + 1:-1] if "[" in label and label.endswith("]") else label
    def type_size(self, tid):
        d = self.types.get(tid, {})
        return max(1, int(d.get("w", 1))), max(1, int(d.get("h", 1)))

    # ---------- интерфейс ----------
    def _ui(self, parent):
        box = ttk.LabelFrame(parent, text="Механизмы (рычаги, кнопки, двери, лифты, порталы, платформы)", padding=5)
        box.pack(fill="x", pady=(8, 0)); self.box = box
        top = ttk.Frame(box); top.pack(fill="x")
        ttk.Checkbutton(top, text="Режим механизмов: ЛКМ — поставить / выбрать, ПКМ — убрать (клетки не рисуются)",
                        variable=self.mode, command=self._mode_changed).pack(side="left")
        ttk.Label(top, textvariable=self.info_var, foreground="#555").pack(side="right")
        ttk.Label(box, textvariable=self.title_var, font=("Arial", 9, "bold")).pack(anchor="w", pady=(4, 2))
        row = ttk.Frame(box); row.pack(fill="x")
        ttk.Label(row, text="Тип:").pack(side="left")
        self.type_cb = ttk.Combobox(row, textvariable=self.type_var, state="readonly", width=24,
                                    values=[self.type_label(t) for t in MECH_TYPES])
        self.type_cb.pack(side="left", padx=4); self.type_cb.bind("<<ComboboxSelected>>", lambda e: self._type_changed())
        ttk.Label(row, text="Канал (связь кнопка->дверь/лифт/портал/платформа):").pack(side="left", padx=(8, 0))
        ch = ttk.Entry(row, textvariable=self.ch_var, width=10); ch.pack(side="left", padx=4)
        ch.bind("<FocusOut>", lambda e: self._fields_changed()); ch.bind("<Return>", lambda e: self._fields_changed())
        row2 = ttk.Frame(box); row2.pack(fill="x", pady=(4, 0))
        ttk.Label(row2, text="Ширина W:").pack(side="left")
        w = ttk.Spinbox(row2, from_=1, to=10, textvariable=self.w_var, width=3, command=self._fields_changed); w.pack(side="left", padx=3)
        ttk.Label(row2, text="Высота H:").pack(side="left")
        h = ttk.Spinbox(row2, from_=1, to=10, textvariable=self.h_var, width=3, command=self._fields_changed); h.pack(side="left", padx=3)
        ttk.Label(row2, text="Ход лифта (клеток):").pack(side="left", padx=(10, 0))
        r = ttk.Spinbox(row2, from_=0, to=30, textvariable=self.range_var, width=4, command=self._fields_changed); r.pack(side="left", padx=3)
        ttk.Label(row2, text="Скорость:").pack(side="left", padx=(10, 0))
        sp = ttk.Spinbox(row2, from_=10, to=600, increment=10, textvariable=self.speed_var, width=5, command=self._fields_changed); sp.pack(side="left", padx=3)
        ttk.Label(row2, text="Режим лифта:").pack(side="left", padx=(10, 0))
        md = ttk.Combobox(row2, textvariable=self.mode_var, state="readonly", width=11, values=["control", "auto"])
        md.pack(side="left", padx=3); md.bind("<<ComboboxSelected>>", lambda e: self._fields_changed())
        ttk.Label(row2, text="Пара (id):").pack(side="left", padx=(10, 0))
        pr = ttk.Entry(row2, textvariable=self.pair_var, width=4); pr.pack(side="left", padx=3)
        pr.bind("<FocusOut>", lambda e: self._fields_changed()); pr.bind("<Return>", lambda e: self._fields_changed())
        ttk.Checkbutton(row2, text="По кругу", variable=self.loop_var, command=self._fields_changed).pack(side="left", padx=(8, 0))
        for ww in (w, h, r, sp, pr): ww.bind("<FocusOut>", lambda e: self._fields_changed()); ww.bind("<Return>", lambda e: self._fields_changed())
        path = ttk.Frame(box); path.pack(fill="x", pady=(4, 0))
        ttk.Checkbutton(path, text="Путь платформы: ЛКМ добавляет точку", variable=self.path_mode, command=self._path_mode_changed).pack(side="left")
        self.pt_label = ttk.Label(path, text="0 точек", foreground="#555"); self.pt_label.pack(side="left", padx=8)
        ttk.Button(path, text="Очистить путь", command=self.clear_path).pack(side="left", padx=4)
        ttk.Button(path, text="Снять выбор (править кисть)", command=self.deselect).pack(side="right")
        ttk.Label(box, text="Канал — имя связи: рычаг/кнопка выдаёт сигнал, дверь/лифт/портал/платформа слушает. "
                            "Уникальное имя — своя кнопка у каждого механизма. Порталы связываются полем «Пара (id)». "
                            "Лифт: control — активный канал вверх, auto — ездит сам. Платформа: путь из точек-клеток.",
                  wraplength=900, foreground="#555").pack(anchor="w", pady=(4, 0))

    # ---------- кисть / выбранный механизм ----------
    def active(self): return bool(self.mode.get())

    def _mode_changed(self):
        if self.mode.get():
            self.ed.morg_mode.set(False)
            for attr in ("dpanel",):
                dp = getattr(self.ed, attr, None)
                if dp: dp.mode.set(False); dp.body.pack_forget(); dp.sel = None
            if getattr(self.ed, "cpanel", None): self.ed.cpanel.mode.set(False)
            self.ed.status.set("Режим механизмов: ЛКМ — поставить механизм (настройки кисти) или выбрать, ПКМ — убрать. У платформ ЛКМ добавляет точки пути.")
        self._refresh()

    def cur(self):
        if self.sel is not None and 0 <= self.sel < len(self.ed.mechs): return self.ed.mechs[self.sel]
        self.sel = None; return self.brush

    def deselect(self): self.sel = None; self._load_fields(); self._refresh()

    def _type_changed(self):
        tid = self.type_from_label(self.type_var.get())
        c = self.cur()
        if tid in self.types:
            c["type"] = tid
            w, h = self.type_size(tid); c["w"], c["h"] = w, h
            self.w_var.set(str(w)); self.h_var.set(str(h))
        self._load_fields(); self._refresh()

    def _load_fields(self):
        c = self.cur(); self._busy = True
        try:
            self.type_var.set(self.type_label(c.get("type", "lever")))
            self.ch_var.set(str(c.get("channel", "")))
            self.w_var.set(str(int(c.get("w", self.type_size(c.get("type", "lever"))[0]))))
            self.h_var.set(str(int(c.get("h", self.type_size(c.get("type", "lever"))[1]))))
            self.range_var.set(str(int(c.get("range", 4))))
            self.speed_var.set(str(float(c.get("speed", 60))))
            self.mode_var.set(c.get("mode") or ("control" if c.get("type") == "elevator" else "auto"))
            self.pair_var.set("" if c.get("pair") is None else str(c["pair"]))
            self.loop_var.set(bool(c.get("loop", True)))
        finally: self._busy = False
        self._refresh_info()

    def _fields_changed(self):
        if self._busy: return
        c = self.cur()
        tid = self.type_from_label(self.type_var.get())
        if tid in self.types and tid != c.get("type"):
            c["type"] = tid
        try:
            c["channel"] = self.ch_var.get().strip() or ""
            c["w"] = max(1, min(10, int(self.w_var.get()))); c["h"] = max(1, min(10, int(self.h_var.get())))
            c["range"] = max(0, min(30, int(self.range_var.get())))
            c["speed"] = max(10, min(600, float(self.speed_var.get())))
            c["mode"] = self.mode_var.get() or None
            pv = self.pair_var.get().strip()
            c["pair"] = int(pv) if pv.isdigit() else None
            c["loop"] = bool(self.loop_var.get())
        except ValueError: pass
        self._refresh_info(); self._refresh()

    def _refresh_info(self):
        c = self.cur(); tid = c.get("type", "lever")
        if self.sel is None:
            self.title_var.set("Кисть: настройки для НОВЫХ механизмов. Выбери механизм на карте, чтобы править его.")
        else:
            c = self.ed.mechs[self.sel]
            self.title_var.set("Выбран механизм №%d: «%s», клетка (%d, %d), канал «%s»" % (
                c["id"], TYPE_LABEL.get(c["type"], c["type"]), c["x"], c["y"], c.get("channel", "")))
        self.pt_label.configure(text="%d точек пути" % len(c.get("path", [])))

    # ---------- карта ----------
    def cells_of(self, s):
        w, h = int(s.get("w", 1)), int(s.get("h", 1))
        if s.get("type") in ("elevator", "mover"):
            return [(s["x"] + i, s["y"]) for i in range(w)]
        return [(s["x"] + i, s["y"] + j) for j in range(h) for i in range(w)]

    def at(self, x, y):
        for i, s in enumerate(self.ed.mechs):
            if (x, y) in self.cells_of(s): return i
        return None

    def can_place(self, s):
        for x, y in self.cells_of(s):
            if not (0 <= x < self.ed.map_w and 0 <= y < self.ed.map_h): return False, "механизм не помещается на карту"
            if self.at(x, y) is not None: return False, "здесь уже стоит механизм"
        return True, ""

    def _next_mech_id(self):
        used = {int(s.get("id", 0)) for s in self.ed.mechs}
        while self.next_id in used: self.next_id += 1
        i = self.next_id; self.next_id += 1; return i

    def click(self, event):
        x, y = self.ed._cell_from_event(event)
        if not (0 <= x < self.ed.map_w and 0 <= y < self.ed.map_h): return
        i = self.at(x, y)
        if i is not None:
            self.sel = i; self._load_fields(); self._refresh()
            self.ed.status.set("Выбран механизм №%d. Меняй настройки в панели ниже; ПКМ — убрать." % (self.ed.mechs[i]["id"]))
            return
        # Режим пути: к выбранной платформе добавляем точку (создаём платформу, если её нет).
        tid = self.type_from_label(self.type_var.get())
        if self.path_mode.get() and (tid == "mover" or (self.sel is not None and self.ed.mechs[self.sel].get("type") == "mover")):
            if self.sel is None:
                s = self._new_spec(x, y, "mover"); self.ed.mechs.append(s); self.sel = len(self.ed.mechs) - 1
            self.ed.mechs[self.sel].setdefault("path", [])
            path = self.ed.mechs[self.sel]["path"]
            if (x, y) not in [(int(p[0]), int(p[1])) for p in path]:
                path.append([x, y])
                self.path_mode.set(False)   # одна точка за клик — не растянуть по случайным кликам
            self._load_fields(); self._refresh()
            self.ed.status.set("Точка пути добавлена у платформы №%d. Всего точек: %d." % (self.ed.mechs[self.sel]["id"], len(path)))
            return
        if tid not in self.types: messagebox.showerror("Механизмы", "Нет типов механизмов: проверь data/mechs.json."); return
        s = self._new_spec(x, y, tid)
        ok, why = self.can_place(s)
        if not ok: self.ed.status.set("Сюда механизм не поставить: " + why + "."); return
        s["id"] = self._next_mech_id()
        self.ed.mechs.append(s); self._refresh()
        self.ed.status.set("Поставлен «%s» №%d в клетку (%d, %d)." % (TYPE_LABEL.get(tid, tid), s["id"], x, y))

    def _new_spec(self, x, y, tid):
        b = self.brush
        return {"id": 0, "type": tid, "x": x, "y": y,
                "channel": str(b.get("channel") or ""), "w": int(b.get("w", 1)), "h": int(b.get("h", 1)),
                "range": int(b.get("range", 4)), "speed": float(b.get("speed", 60)),
                "mode": b.get("mode"), "pair": b.get("pair"), "path": [[x, y]], "loop": bool(b.get("loop", True))}

    def clear_path(self):
        c = self.cur()
        if c.get("type") == "mover": c["path"] = []
        self._refresh_info(); self._refresh()

    def erase(self, event):
        x, y = self.ed._cell_from_event(event); i = self.at(x, y)
        if i is None: return
        del self.ed.mechs[i]
        if self.sel is not None: self.sel = None if self.sel == i else (self.sel - 1 if self.sel > i else self.sel)
        self._load_fields(); self._refresh(); self.ed.status.set("Механизм убран. Осталось: %d." % len(self.ed.mechs))

    def _path_mode_changed(self):
        if self.path_mode.get():
            # режим пути работает по ближайшей выбранной платформе (или кисти-mover)
            if not (self.sel is not None and self.ed.mechs[self.sel].get("type") == "mover"):
                tid = self.type_from_label(self.type_var.get())
                if tid != "mover": self.type_var.set(self.type_label("mover")); self._type_changed()
            self.ed.status.set("Режим пути: кликай по клеткам — точки добавляются в путь выбранной платформы.")
        self._refresh()

    def _refresh(self): self.ed._draw_all()

    def draw(self):
        """Механизмы поверх сетки: цвет типа, подпись, канал; выбранный — белая рамка; у платформ — точки пути."""
        cv, cs = self.ed.canvas, self.ed.cell_size()
        for i, s in enumerate(self.ed.mechs):
            d = self.types.get(s["type"], {})
            cells = self.cells_of(s)
            xs = [c for c, _ in cells]; ys = [r for _, r in cells]
            x0, y0 = min(xs) * cs, min(ys) * cs
            x1, y1 = (max(xs) + 1) * cs, (max(ys) + 1) * cs
            cv.create_rectangle(x0 + 1, y0 + 1, x1 - 1, y1 - 1, fill=hexc(d.get("color", [150, 150, 170])),
                                outline="#ffffff" if i == self.sel else "#223044", width=3 if i == self.sel else 2, tags=("mc",))
            label = "%s №%d" % (TYPE_LABEL.get(s["type"], s["type"])[:1], int(s.get("id", 0)))
            cv.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=label, fill="#0c0c14", font=("Arial", 9, "bold"), tags=("mc",))
            ch = s.get("channel", "")
            if ch: cv.create_text((x0 + x1) / 2, y1 - 3, text=ch, fill="#cfe3ff", font=("Arial", 8), tags=("mc",))
            if s.get("type") in ("mover", "elevator") and s.get("path"):
                for p in s["path"]:
                    cv.create_text(int(p[0]) * cs + cs / 2, int(p[1]) * cs + cs / 2, text="•", fill="#ffdf70",
                                   font=("Arial", 12, "bold"), tags=("mc",))

    # ---------- сохранение / загрузка / правки карты ----------
    def load(self, mechanisms):
        """Механизмы из файла карты. Неизвестные типы остаются как есть."""
        self.ed.mechs = []
        self.next_id = 1
        for s in mechanisms or []:
            if isinstance(s, dict) and "type" in s and "x" in s and "y" in s:
                try:
                    spec = {"type": str(s["type"]), "x": int(s["x"]), "y": int(s["y"]),
                            "id": int(s.get("id", self.next_id))}
                    if spec["id"] >= self.next_id: self.next_id = spec["id"] + 1
                except (TypeError, ValueError): continue
                for k in ("channel", "w", "h", "range", "mode", "speed", "pair", "loop"):
                    if k in s: spec[k] = s[k]
                if isinstance(s.get("path"), list): spec["path"] = copy.deepcopy(s["path"])
                if spec.get("path") is None or not isinstance(spec.get("path"), list):
                    spec["path"] = [[spec["x"], spec["y"]]]
                self.ed.mechs.append(spec)
        self.sel = None; self._load_fields()

    def dump(self):
        return [clean_spec(s) for s in self.ed.mechs]

    def crop(self, w, h):
        keep = [s for s in self.ed.mechs if all(0 <= c < w and 0 <= r < h for c, r in self.cells_of(s))]
        for s in keep:
            if s.get("path"):
                s["path"] = [p for p in s["path"] if 0 <= int(p[0]) < w and 0 <= int(p[1]) < h]
        if len(keep) != len(self.ed.mechs): self.ed.status.set("Убрано механизмов за краем карты: %d." % (len(self.ed.mechs) - len(keep)))
        self.ed.mechs = keep; self.sel = None; self._load_fields()

    def reset(self):
        self.ed.mechs = []; self.sel = None; self._load_fields()
