"""Панель «Механизмы» редактора карт (map_editor.py): рычаги, кнопки, двери, лифты, телепорты, платформы.

Включи «Режим механизмов» — и на карте:
  ЛКМ по пустой клетке — поставить механизм (с настройками кисти);
  ЛКМ по механизму      — выбрать его: панель покажет и позволит менять его настройки;
  ПКМ по механизму      — убрать.

Провода (только редактор: в игре их не видно — но провод между двумя ПОРТАЛАМИ настраивает их «Пару (id)»):
  Галочка «Провода» — ЛКМ по механизму выбирает источник, ЛКМ по второму механизму — провод между ними.
  Источник остаётся выбранным: одним рычагом можно соединить сразу несколько дверей. ЛКМ по пустому месту
  или ПКМ — сбросить выбор. ЛКМ по линии провода — удалить провод; ПКМ по механизму — убрать все его провода.
  Цвет провода: зелёный — связь согласована (у пары «источник → слушатель» совпадает канал, или у пары
  порталов настроены поля «Пара (id)» друг на друга); оранжевый — провод есть, но канал/пара НЕ совпадают
  (проверь настройки механизмов); провода хранятся в карте полем "wires": [{"a": id, "b": id}, ...].
  Провод между двумя порталами автоматически настраивает их пару (в игре они телепортируют друг в друга);
  удаление провода снимает пару, удаление портала сбрасывает «пару» у оставшегося.

Пути платформ и лифты:
  «Режим пути» (для выбранной платформы-движка): ЛКМ по пустой клетке — добавить точку маршрута,
  ЛКМ по точке + тянуть — передвинуть её, ПКМ по точке — удалить. Линии со стрелками показывают порядок
  обхода точек, у выбранной платформы точки подписаны номерами; галочка «По кругу» замыкает маршрут,
  кнопка «Развернуть путь» меняет порядок точек на обратный.
  Лифт точек пути не имеет: ход задаётся клетками в поле «Ход лифта», и на карте голубым пунктиром
  показано его верхнее положение (куда поднимется при активном канале) со стрелкой хода.
  Кнопка «Снять выбор» — снова править кисть для новых механизмов.

Результат пишется в карту: поле "mechanisms" (формат — mechs.py) и поле "wires" (только для редактора).
"""
import copy
import json
import math
import tkinter as tk
from tkinter import ttk, messagebox

MECH_TYPES = ("lever", "button", "door", "elevator", "teleporter", "mover")
TYPE_LABEL = {"lever": "Рычаг", "button": "Кнопка", "door": "Дверь", "elevator": "Лифт",
              "teleporter": "Телепорт", "mover": "Подвижная платформа"}
ROWS_NEEDED = {"door": 0, "teleporter": 0}   # высота в клетках по умолчанию (h)
CONTROLS = ("lever", "button")               # источники сигнала (как в mechs.py)

WIRE_COLORS = {"ok": "#58d68d", "warn": "#e8a33d", "broken": "#ff5c5c"}
WIRE_SRC = "#ffd54a"                         # жёлтый выбор источника провода и пунктир «тянется за мышью»


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
        self.wires = []                                  # [{"a": id, "b": id}] — соединения механизмов (только редактор)
        self.wire_src = None                             # выбранный источник провода (запись механизма) или None
        self._mouse_px = None                            # последняя позиция мыши на канвасе (canvasx, canvasy)
        self._drag_pt = None                             # индекс точки пути, которую тянут мышью
        self._redraw_soon = False                        # отложенная перерисовка при перетаскивании
        self.brush = {"type": "lever", "x": 0, "y": 0, "id": 0, "channel": "ch1", "w": 1, "h": 1,
                      "range": 4, "mode": "control", "speed": 60.0, "pair": None, "path": [], "loop": True}
        self.mode = tk.BooleanVar(value=False)
        self.path_mode = tk.BooleanVar(value=False)      # ЛКМ добавляет точку пути платформы
        self.wire_mode = tk.BooleanVar(value=False)      # ЛКМ соединяет механизмы проводами
        self.type_var = tk.StringVar(value="Рычаг")
        self.ch_var = tk.StringVar(value="ch1")
        self.w_var = tk.StringVar(value="1"); self.h_var = tk.StringVar(value="1")
        self.range_var = tk.StringVar(value="4"); self.speed_var = tk.StringVar(value="60")
        self.mode_var = tk.StringVar(value="control")
        self.pair_var = tk.StringVar(value="")
        self.loop_var = tk.BooleanVar(value=True)
        self.title_var = tk.StringVar(); self.info_var = tk.StringVar()
        self.pt_label_var = tk.StringVar(value="0 точек")
        self.wires_var = tk.StringVar(value="0 проводов")
        self._busy = False
        self._ui(parent)
        self._bind_canvas()
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
        ttk.Label(row, text="Пара (id, для порталов):").pack(side="left", padx=(8, 0))
        pr = ttk.Entry(row, textvariable=self.pair_var, width=4); pr.pack(side="left", padx=3)
        pr.bind("<FocusOut>", lambda e: self._fields_changed()); pr.bind("<Return>", lambda e: self._fields_changed())
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
        ttk.Checkbutton(row2, text="По кругу (платформа)", variable=self.loop_var, command=self._fields_changed).pack(side="left", padx=(8, 0))
        for ww in (w, h, r, sp, pr): ww.bind("<FocusOut>", lambda e: self._fields_changed()); ww.bind("<Return>", lambda e: self._fields_changed())
        path = ttk.Frame(box); path.pack(fill="x", pady=(4, 0))
        ttk.Checkbutton(path, text="Режим пути: ЛКМ — добавить точку, ЛКМ по точке — тянуть, ПКМ по точке — удалить",
                        variable=self.path_mode, command=self._path_mode_changed).pack(side="left")
        ttk.Label(path, textvariable=self.pt_label_var, foreground="#555").pack(side="left", padx=8)
        ttk.Button(path, text="Очистить путь", command=self.clear_path).pack(side="left", padx=4)
        ttk.Button(path, text="Развернуть путь", command=self.reverse_path).pack(side="left", padx=4)
        wires = ttk.Frame(box); wires.pack(fill="x", pady=(4, 0))
        ttk.Checkbutton(wires, text="Провода: ЛКМ по механизму — источник, ЛКМ по второму — провод; ЛКМ по линии — убрать провод",
                        variable=self.wire_mode, command=self._wire_mode_changed).pack(side="left")
        ttk.Label(wires, textvariable=self.wires_var, foreground="#555").pack(side="left", padx=8)
        ttk.Button(wires, text="Убрать все провода", command=self.clear_wires).pack(side="left", padx=4)
        ttk.Button(wires, text="Снять выбор (править кисть)", command=self.deselect).pack(side="right")
        ttk.Label(box, text="Связь механизмов: рычаг/кнопка выдаёт сигнал в СВОЙ канал, дверь/лифт/портал/платформа слушает тот же канал "
                            "(уникальное имя канала — своя кнопка у каждого механизма; один канал — группа дверей). Порталы связываются "
                            "полем «Пара (id)»: соединил два портала проводом — пара настроится сама (в игре они телепортируют друг в друга), "
                            "убрал провод — пара снялась. Провода не видны в игре и ни на что не влияют — они показывают, что с чем соединено: "
                            "зелёный — канал/пара совпадают, оранжевый — не совпадают (проверь настройки). Лифт: control — активный канал "
                            "ведёт вверх, auto — ездит сам; голубой пунктир на карте — его верхнее положение.",
                  wraplength=900, foreground="#555").pack(anchor="w", pady=(4, 0))

    def _bind_canvas(self):
        """Свои обработчики канваса (поверх базовых, add="+"): движение мыши и отпускание кнопки."""
        c = self.ed.canvas
        c.bind("<Motion>", self._canvas_motion, add="+")
        c.bind("<ButtonRelease-1>", self._canvas_release, add="+")

    # ---------- кисть / выбранный механизм ----------
    def active(self): return bool(self.mode.get())

    def _mode_changed(self):
        if self.mode.get():
            self.ed.morg_mode.set(False)
            for attr in ("dpanel",):
                dp = getattr(self.ed, attr, None)
                if dp: dp.mode.set(False); dp.body.pack_forget(); dp.sel = None
            if getattr(self.ed, "cpanel", None): self.ed.cpanel.mode.set(False)
            self.ed.status.set("Режим механизмов: ЛКМ — поставить механизм (настройки кисти) или выбрать, ПКМ — убрать. "
                               "Для соединений включи «Провода», для маршрута платформы — «Режим пути».")
        else:   # режим выключен — сбросить подрежимы и недоделанные соединения
            self.wire_mode.set(False); self.path_mode.set(False)
            self.wire_src = None; self._drag_pt = None
            self._drop_pending()
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
            extra = ", пара №%s" % c["pair"] if c.get("type") == "teleporter" and c.get("pair") is not None else ""
            self.title_var.set("Выбран механизм №%d: «%s», клетка (%d, %d), канал «%s»%s" % (
                c["id"], TYPE_LABEL.get(c["type"], c["type"]), c["x"], c["y"], c.get("channel", ""), extra))
        self.pt_label_var.set("%d точек пути" % len(c.get("path", []) or []))
        self.wires_var.set("%d проводов" % len(self.wires))

    # ---------- провода ----------
    def _by_id(self, mid):
        try: mid = int(mid)
        except (TypeError, ValueError): return None
        for s in self.ed.mechs:
            if int(s.get("id", -1)) == mid: return s
        return None

    def _wire_state(self, w):
        """('ok'|'warn'|'broken', пояснение): согласованы ли настройки соединённых механизмов."""
        a, b = self._by_id(w.get("a")), self._by_id(w.get("b"))
        if a is None or b is None: return "broken", "механизм удалён"
        if a is b: return "warn", "механизм соединён с самим собой"
        ta, tb = a.get("type", ""), b.get("type", "")
        if ta == "teleporter" and tb == "teleporter":
            if a.get("pair") == b.get("id") and b.get("pair") == a.get("id"):
                return "ok", "пара порталов настроена: телепортируют друг в друга"
            return "warn", "пара (id) порталов не настроена друг на друга — пересоедини их проводом, настроится сама"
        if (ta in CONTROLS) != (tb in CONTROLS):
            src, lst = (a, b) if ta in CONTROLS else (b, a)
            if src.get("channel") and str(src.get("channel")) == str(lst.get("channel")):
                return "ok", "общий канал «%s»" % src.get("channel")
            return "warn", "каналы различаются: «%s» и «%s» — сигнал не дойдёт" % (a.get("channel") or "пусто", b.get("channel") or "пусто")
        return "warn", "оба механизма — %s: соединять есть смысл только источник (рычаг/кнопку) со слушателем" % (
            "источники сигнала" if ta in CONTROLS else "слушатели без канала")

    def _portals_pair(self, a, b):
        """Провод между двумя порталами = их связь в игре: поля «Пара (id)» настраиваются сами."""
        if a.get("type") != "teleporter" or b.get("type") != "teleporter": return False
        a["pair"], b["pair"] = int(b.get("id", 0)), int(a.get("id", 0))
        return True

    def _portals_unpair(self, a_id, b_id):
        """Провод удалён: если порталы были настроены друг на друга — разъединяем и в игре."""
        a, b = self._by_id(a_id), self._by_id(b_id)
        if a is None or b is None: return False
        if a.get("type") != "teleporter" or b.get("type") != "teleporter": return False
        if a.get("pair") == b.get("id") and b.get("pair") == a.get("id"):
            a["pair"] = b["pair"] = None
            return True
        return False

    def _fix_orphan_pairs(self):
        """После удаления/обрезки механизмов: «Пара (id)», указывающая на несуществующий портал, сбрасывается."""
        ids = {int(s.get("id", 0)) for s in self.ed.mechs}
        changed = False
        for s in self.ed.mechs:
            if s.get("type") != "teleporter" or s.get("pair") is None: continue
            try: alive = int(s["pair"]) in ids
            except (TypeError, ValueError): alive = False
            if not alive: s["pair"] = None; changed = True
        return changed

    def _wire_click(self, event, i):
        if i is not None:
            s = self.ed.mechs[i]
            if self.wire_src is None:
                self.wire_src = s; self._pending_follow()
                self.ed.status.set("Провод: источник — %s №%d. ЛКМ по другому механизму — соединить (можно несколько подряд); "
                                   "ЛКМ по нему же или по пустому месту — отмена." % (TYPE_LABEL.get(s["type"], s["type"]), s["id"]))
                return
            if self.wire_src is s:
                self.wire_src = None; self._drop_pending()
                self.ed.status.set("Провод: выбор источника отменён."); return
            a, b = int(self.wire_src.get("id", 0)), int(s.get("id", 0))
            if any({int(w.get("a", -1)), int(w.get("b", -1))} == {a, b} for w in self.wires):
                self.ed.status.set("Эти механизмы уже соединены: ЛКМ по линии провода — убрать его."); return
            w = {"a": a, "b": b}; self.wires.append(w)
            paired = self._portals_pair(self.wire_src, s)   # провод между порталами = их пара в игре
            st, why = self._wire_state(w)
            if paired:
                self.ed.status.set("Порталы №%d и №%d соединены — пара настроилась сама: в игре они телепортируют друг в друга. "
                                   "Источник остался выбранным; ПКМ или пустое место — завершить." % (a, b))
            elif st == "ok":
                self.ed.status.set("Провод: №%d → №%d (%s). Источник остался выбранным — можно соединить ещё; ПКМ или пустое место — завершить." % (a, b, why))
            else:
                self.ed.status.set("Провод №%d → №%d поставлен, но: %s (оранжевый). Проверь канал/пару в настройках механизмов." % (a, b, why))
            self._refresh(); self._refresh_info()
            if paired: self._load_fields()   # обновить поле «Пара (id)», если правили один из этих порталов
            return
        wi = self._wire_at_event(event)
        if wi is not None:
            gone = self.wires.pop(wi); self._drop_pending()
            unp = self._portals_unpair(gone.get("a"), gone.get("b"))
            if unp: self._load_fields()
            self.ed.status.set("Провод №%s→№%s удалён%s." % (gone.get("a"), gone.get("b"),
                               ", пара порталов разъединена" if unp else ""))
            self._refresh(); self._refresh_info(); return
        if self.wire_src is not None:
            self.wire_src = None; self._drop_pending()
            self.ed.status.set("Провод: выбор источника сброшен.")

    def _wire_mode_changed(self):
        if self.wire_mode.get(): self.wire_src = None
        else: self.wire_src = None; self._drag_pt = None
        self._drop_pending(); self._refresh()
        if self.wire_mode.get():
            self.ed.status.set("Режим проводов (видны только в редакторе): ЛКМ — источник, ЛКМ по второму механизму — провод; "
                               "ЛКМ по линии — убрать провод; ПКМ по механизму — убрать все его провода. "
                               "Провод между двумя порталами сам настраивает их пару.")

    def clear_wires(self):
        gone, self.wires = self.wires, []
        unp = sum(1 for w in gone if self._portals_unpair(w.get("a"), w.get("b")))
        self.wire_src = None; self._drop_pending()
        if unp: self._load_fields()
        self._refresh(); self._refresh_info()
        msg = "Убрано проводов: %d." % len(gone)
        if unp: msg += " Пар порталов разъединено: %d." % unp
        self.ed.status.set(msg)

    def _wire_at_event(self, event):
        """Индекс провода под курсором (близко к линии) или None."""
        if not self.wires: return None
        cv = self.ed.canvas
        try: px, py = cv.canvasx(event.x), cv.canvasy(event.y)
        except (AttributeError, tk.TclError): return None
        tol = max(6.0, self.ed.cell_size() * 0.25)
        for wi, w in enumerate(self.wires):
            a, b = self._by_id(w.get("a")), self._by_id(w.get("b"))
            if a is None or b is None: continue
            if self._dist_to_seg(px, py, self._center_px(a), self._center_px(b)) <= tol: return wi
        return None

    def _pending_follow(self):
        """Жёлтый пунктир от источника провода к курсору (двигается без перерисовки всей карты)."""
        if self.wire_src is None or self._mouse_px is None: return
        cv = self.ed.canvas
        x0, y0 = self._center_px(self.wire_src); x1, y1 = self._mouse_px
        items = cv.find_withtag("wirepend")
        if items:
            cv.coords(items[0], x0, y0, x1, y1); cv.tag_raise(items[0])
        else:
            cv.create_line(x0, y0, x1, y1, fill=WIRE_SRC, dash=(5, 4), width=2, tags=("wirepend",))

    def _drop_pending(self):
        try:
            for it in self.ed.canvas.find_withtag("wirepend"): self.ed.canvas.delete(it)
        except (tk.TclError, AttributeError): pass

    @staticmethod
    def _dist_to_seg(px, py, a, b):
        ax, ay = a; bx, by = b
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        if L2 == 0: return math.hypot(px - ax, py - ay)
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
        return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

    # ---------- путь платформы ----------
    def _active_mover(self):
        """Выбранная подвижная платформа (запись) или None."""
        if self.sel is not None and 0 <= self.sel < len(self.ed.mechs):
            s = self.ed.mechs[self.sel]
            if s.get("type") == "mover": return s
        return None

    def _path_point_at(self, s, x, y):
        for pi, p in enumerate(s.get("path") or []):
            if int(p[0]) == x and int(p[1]) == y: return pi
        return None

    def _path_mode_changed(self):
        if self.path_mode.get():
            if not (self.sel is not None and 0 <= self.sel < len(self.ed.mechs) and self.ed.mechs[self.sel].get("type") == "mover"):
                tid = self.type_from_label(self.type_var.get())
                if tid != "mover": self.type_var.set(self.type_label("mover")); self._type_changed()
            self.ed.status.set("Режим пути: ЛКМ по пустой клетке — добавить точку маршрута платформы; ЛКМ по точке — тянуть; ПКМ по точке — удалить.")
        self._refresh()

    def _path_click(self, x, y):
        s = self._active_mover()
        if s is None:
            tid = self.type_from_label(self.type_var.get())
            if tid != "mover":
                self.ed.status.set("Режим пути: сначала выбери подвижную платформу на карте (или тип «Подвижная платформа» в кисти)."); return
            s = self._new_spec(x, y, "mover")
            ok, why = self.can_place(s)
            if not ok: self.ed.status.set("Платформу сюда не поставить: " + why + "."); return
            s["id"] = self._next_mech_id(); self.ed.mechs.append(s); self.sel = len(self.ed.mechs) - 1
            self._load_fields(); self._refresh()
            self.ed.status.set("Создана платформа №%d. Продолжай кликать по клеткам — точки пути добавляются." % s["id"])
            return
        path = s.setdefault("path", [])
        if (x, y) in [(int(p[0]), int(p[1])) for p in path]:
            self.ed.status.set("Такая точка уже есть в пути платформы №%d (ЛКМ по ней — тянуть, ПКМ — удалить)." % s["id"]); return
        path.append([x, y]); self._refresh(); self._refresh_info()
        self.ed.status.set("Платформа №%d: добавлена точка %d (%d, %d). Всего точек: %d." % (s["id"], len(path), x, y, len(path)))

    def clear_path(self):
        c = self.cur()
        if c.get("type") == "mover": c["path"] = []
        self._refresh_info(); self._refresh()
        self.ed.status.set("Путь очищен: платформа будет стоять на месте (или заново кликни точки в режиме пути).")

    def reverse_path(self):
        s = self._active_mover()
        if s is None: self.ed.status.set("«Развернуть путь»: сначала выбери подвижную платформу на карте."); return
        path = s.get("path") or []
        if len(path) >= 2:
            s["path"] = [list(p) for p in reversed(path)]
            self._refresh(); self._refresh_info()
            self.ed.status.set("Путь платформы №%d развернут: платформа поедет в обратном порядке точек." % s["id"])
        else:
            self.ed.status.set("Разворачивать нечего: в пути платформы №%d меньше двух точек." % s["id"])

    # ---------- мышь канваса ----------
    def _canvas_motion(self, event):
        if not self.active(): return
        cv = self.ed.canvas
        try: self._mouse_px = (cv.canvasx(event.x), cv.canvasy(event.y))
        except (AttributeError, tk.TclError): return
        if self.wire_mode.get() and self.wire_src is not None: self._pending_follow()

    def drag_motion(self, event):
        """Протягивание ЛКМ в режиме механизмов: тянем точку пути выбранной платформы."""
        if self._drag_pt is None: return
        s = self._active_mover()
        if s is None: self._drag_pt = None; return
        x, y = self.ed._cell_from_event(event)
        if not (0 <= x < self.ed.map_w and 0 <= y < self.ed.map_h): return
        path = s.setdefault("path", [])
        if not (0 <= self._drag_pt < len(path)): self._drag_pt = None; return
        if (x, y) == (int(path[self._drag_pt][0]), int(path[self._drag_pt][1])): return
        if any((x, y) == (int(p[0]), int(p[1])) for j, p in enumerate(path) if j != self._drag_pt): return
        path[self._drag_pt] = [x, y]
        self.ed.status.set("Платформа №%d: точка %d → (%d, %d)" % (s["id"], self._drag_pt + 1, x, y))
        self._refresh_soon()

    def _canvas_release(self, event=None):
        if not self.active() or self._drag_pt is None: return
        self._drag_pt = None
        s = self._active_mover()
        if s is not None:
            self.ed.status.set("Путь платформы №%d: %d точек. ЛКМ по точке — тянуть, ПКМ — удалить, «По кругу» — замкнуть." % (s.get("id", 0), len(s.get("path") or [])))

    def _refresh_soon(self):
        """Перерисовка не чаще одного раза на кадр (при перетаскивании точки пути)."""
        if self._redraw_soon: return
        self._redraw_soon = True
        try: self.ed.root.after_idle(self._refresh_soon_now)
        except (AttributeError, tk.TclError): self._refresh_soon_now()

    def _refresh(self): self.ed._draw_all()

    def _refresh_soon_now(self):
        self._redraw_soon = False; self._refresh()

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
        self.ed.canvas.focus_set()
        x, y = self.ed._cell_from_event(event)
        if not (0 <= x < self.ed.map_w and 0 <= y < self.ed.map_h): return
        i = self.at(x, y)
        if self.wire_mode.get():                       # режим проводов: соединяем механизмы
            self._wire_click(event, i); return
        if self.path_mode.get():                       # режим пути: тянем точку / выбираем / добавляем точку
            s = self._active_mover()
            pi = self._path_point_at(s, x, y) if s is not None else None
            if pi is not None:                         # ЛКМ по существующей точке пути — перетащить её
                self._drag_pt = pi; self._refresh()
                self.ed.status.set("Платформа №%d: тяни точку %d пути мышью; ПКМ по точке — удалить." % (s["id"], pi + 1))
                return
            if i is not None:                          # выбрали механизм (например, другую платформу)
                self.sel = i; self._load_fields(); self._refresh()
                s = self.ed.mechs[i]
                self.ed.status.set("Выбран %s №%d: настройки в панели ниже; ПКМ — убрать." % (TYPE_LABEL.get(s["type"], s["type"]), s["id"]))
                return
            self._path_click(x, y); return
        if i is not None:
            self.sel = i; self._load_fields(); self._refresh()
            s = self.ed.mechs[i]
            self.ed.status.set("Выбран %s №%d: настройки в панели ниже; ПКМ — убрать." % (TYPE_LABEL.get(s["type"], s["type"]), s["id"]))
            return
        tid = self.type_from_label(self.type_var.get())
        if tid not in self.types: messagebox.showerror("Механизмы", "Нет типов механизмов: проверь data/mechs.json."); return
        s = self._new_spec(x, y, tid)
        ok, why = self.can_place(s)
        if not ok: self.ed.status.set("Сюда механизм не поставить: " + why + "."); return
        s["id"] = self._next_mech_id()
        self.ed.mechs.append(s); self._refresh()
        extra = " Продолжай кликать — добавляются точки пути." if self.path_mode.get() and tid == "mover" else ""
        self.ed.status.set("Поставлен «%s» №%d в клетку (%d, %d).%s" % (TYPE_LABEL.get(tid, tid), s["id"], x, y, extra))

    def _new_spec(self, x, y, tid):
        b = self.brush
        return {"id": 0, "type": tid, "x": x, "y": y,
                "channel": str(b.get("channel") or ""), "w": int(b.get("w", 1)), "h": int(b.get("h", 1)),
                "range": int(b.get("range", 4)), "speed": float(b.get("speed", 60)),
                "mode": b.get("mode"), "pair": b.get("pair"), "path": [[x, y]], "loop": bool(b.get("loop", True))}

    def erase(self, event):
        x, y = self.ed._cell_from_event(event)
        if self.wire_mode.get():                       # ПКМ в режиме проводов: убрать провода, не механизмы
            i = self.at(x, y)
            if i is not None:
                sid = int(self.ed.mechs[i].get("id", 0)); before = len(self.wires)
                gone = [w for w in self.wires if sid in (int(w.get("a", -1)), int(w.get("b", -1)))]
                self.wires = [w for w in self.wires if sid not in (int(w.get("a", -1)), int(w.get("b", -1)))]
                unp = sum(1 for w in gone if self._portals_unpair(w.get("a"), w.get("b")))
                if unp: self._load_fields()
                if self.wire_src is not None and int(self.wire_src.get("id", -1)) == sid: self.wire_src = None; self._drop_pending()
                self._refresh(); self._refresh_info()
                msg = "У механизма №%d убрано проводов: %d." % (sid, before - len(self.wires))
                if unp: msg += " Пара порталов разъединена."
                self.ed.status.set(msg)
            else:
                wi = self._wire_at_event(event)
                if wi is not None:
                    gone = self.wires.pop(wi); self._drop_pending()
                    unp = self._portals_unpair(gone.get("a"), gone.get("b"))
                    if unp: self._load_fields()
                    self._refresh(); self._refresh_info()
                    self.ed.status.set("Провод №%s→№%s удалён%s." % (gone.get("a"), gone.get("b"),
                                       ", пара порталов разъединена" if unp else ""))
            return
        if self.path_mode.get() and self._active_mover() is not None:   # ПКМ по точке пути — удалить точку
            s = self._active_mover()
            pi = self._path_point_at(s, x, y)
            if pi is not None:
                del s["path"][pi]; self._drag_pt = None
                self._refresh(); self._refresh_info()
                self.ed.status.set("Платформа №%d: удалена точка пути (осталось %d). ПКМ по механизму — убрать механизм целиком." % (s["id"], len(s.get("path") or [])))
                return
        i = self.at(x, y)
        if i is None: return
        sid = int(self.ed.mechs[i].get("id", 0))
        del self.ed.mechs[i]
        self.wires = [w for w in self.wires if sid not in (int(w.get("a", -1)), int(w.get("b", -1)))]   # провода к нему тоже
        orphan = self._fix_orphan_pairs()   # «пара» оставшихся порталов на удалённый id — сбросить
        if self.wire_src is not None and int(self.wire_src.get("id", -1)) == sid: self.wire_src = None; self._drop_pending()
        if self.sel is not None: self.sel = None if self.sel == i else (self.sel - 1 if self.sel > i else self.sel)
        self._load_fields(); self._refresh(); self._refresh_info()
        msg = "Механизм убран (и его провода). Осталось: %d." % len(self.ed.mechs)
        if orphan: msg += " «Пара (id)» порталов, указывавших на него, сброшена."
        self.ed.status.set(msg)

    # ---------- рисование ----------
    def _rect_px(self, s):
        """Прямоугольник механизма на канвасе (экранные px с масштабом): (x0, y0, x1, y1)."""
        cs = self.ed.cell_size()
        cells = self.cells_of(s)
        xs = [c for c, _ in cells]; ys = [r for _, r in cells]
        return min(xs) * cs, min(ys) * cs, (max(xs) + 1) * cs, (max(ys) + 1) * cs

    def _center_px(self, s):
        x0, y0, x1, y1 = self._rect_px(s)
        return (x0 + x1) / 2.0, (y0 + y1) / 2.0

    def _edge_toward(self, s, tx, ty):
        """Точка на границе прямоугольника механизма на линии к (tx, ty) — там рисуется «контакт» провода."""
        x0, y0, x1, y1 = self._rect_px(s)
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        dx, dy = tx - cx, ty - cy
        if dx == 0 and dy == 0: return cx, cy
        k = min((x1 - x0) / 2.0 / abs(dx) if dx else 1e9, (y1 - y0) / 2.0 / abs(dy) if dy else 1e9)
        return cx + dx * k, cy + dy * k

    def _draw_wire_lines(self):
        """Линии проводов — ПОД механизмами (видны между ними), пунктир; цвет — по согласованности связи."""
        cv = self.ed.canvas
        for w in self.wires:
            a, b = self._by_id(w.get("a")), self._by_id(w.get("b"))
            if a is None or b is None: continue      # битые провода не рисуем (и при сохранении не пишутся)
            st, _why = self._wire_state(w)
            x0, y0 = self._center_px(a); x1, y1 = self._center_px(b)
            cv.create_line(x0, y0, x1, y1, fill=WIRE_COLORS[st], width=2, dash=(6, 4), tags=("mc",))

    def _draw_wire_dots(self):
        """«Контакты» проводов поверх механизмов; у сомнительных связей — восклицательный знак на линии."""
        cv, cs = self.ed.canvas, self.ed.cell_size()
        r = max(3, int(cs * 0.12))
        for w in self.wires:
            a, b = self._by_id(w.get("a")), self._by_id(w.get("b"))
            if a is None or b is None: continue
            st, _why = self._wire_state(w)
            x0, y0 = self._center_px(a); x1, y1 = self._center_px(b)
            for ex, ey in (self._edge_toward(a, x1, y1), self._edge_toward(b, x0, y0)):
                cv.create_oval(ex - r, ey - r, ex + r, ey + r, fill=WIRE_COLORS[st], outline="#101018", tags=("mc",))
            if st == "warn":
                mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
                cv.create_oval(mx - r * 1.4, my - 8 - r * 1.4, mx + r * 1.4, my - 8 + r * 1.4,
                               fill=WIRE_COLORS["warn"], outline="#101018", tags=("mc",))
                cv.create_text(mx, my - 8, text="!", fill="#101018", font=("Arial", 9, "bold"), tags=("mc",))

    def _draw_mover_path(self, s, is_sel):
        """Маршрут платформы: линии со стрелками (порядок обхода), точки; у выбранной — номера точек."""
        cv, cs = self.ed.canvas, self.ed.cell_size()
        path = s.get("path") or []
        if not path: return
        pts = [(int(p[0]) * cs + cs / 2.0, int(p[1]) * cs + cs / 2.0) for p in path]
        col = "#ffdf70" if is_sel else "#a8934a"
        if len(pts) >= 2:
            seq = pts + ([pts[0]] if s.get("loop") else [])
            for si in range(len(seq) - 1):
                p0, p1 = seq[si], seq[si + 1]
                if p0 == p1: continue
                closing = s.get("loop") and si == len(seq) - 2   # замыкающий отрезок — пунктиром
                cv.create_line(p0[0], p0[1], p1[0], p1[1], fill=col, width=2 if is_sel else 1,
                               arrow="last", dash=(4, 3) if closing else None, tags=("mc",))
        for idx, (px, py) in enumerate(pts):
            hot = is_sel and idx == self._drag_pt
            r = cs * (0.34 if hot else 0.2)
            cv.create_oval(px - r, py - r, px + r, py + r, fill=col, outline="#101018" if not is_sel else "#fff", tags=("mc",))
            if is_sel:
                cv.create_text(px, py, text=str(idx + 1), fill="#101018", font=("Arial", max(7, int(cs * 0.32)), "bold"), tags=("mc",))

    def _draw_elevator_ghost(self, s):
        """Лифт: голубой пунктир — верхнее положение (ход лифта), стрелка хода и подпись."""
        cv, cs = self.ed.canvas, self.ed.cell_size()
        rg = int(s.get("range", 4) or 0)
        if rg <= 0: return
        x0, y0, x1, _y1 = self._rect_px(s)
        ty = (int(s["y"]) - rg) * cs
        cx = (x0 + x1) / 2.0
        cv.create_rectangle(x0 + 2, ty + 2, x1 - 2, y0 - 2, outline="#7fb2ff", dash=(5, 3), tags=("mc",))
        cv.create_line(cx, y0 - 3, cx, ty + 3, fill="#7fb2ff", arrow="both", width=2, tags=("mc",))
        cv.create_text(cx + 7, (y0 + ty) / 2.0, text="ход %d" % rg, fill="#7fb2ff", font=("Arial", 8, "bold"), anchor="w", tags=("mc",))

    def draw(self):
        """Механизмы поверх сетки: цвет типа, подпись, канал; выбранный — белая рамка; источник провода — жёлтая.
        Плюс: пути платформ со стрелками, пунктир хода лифта, провода между механизмами (только редактор)."""
        cv, cs = self.ed.canvas, self.ed.cell_size()
        self._draw_wire_lines()
        for i, s in enumerate(self.ed.mechs):
            d = self.types.get(s["type"], {})
            x0, y0, x1, y1 = self._rect_px(s)
            cv.create_rectangle(x0 + 1, y0 + 1, x1 - 1, y1 - 1, fill=hexc(d.get("color", [150, 150, 170])),
                                outline="#ffffff" if i == self.sel else "#223044", width=3 if i == self.sel else 2, tags=("mc",))
            if self.wire_mode.get() and self.wire_src is s:
                cv.create_rectangle(x0 + 1, y0 + 1, x1 - 1, y1 - 1, outline=WIRE_SRC, width=3, dash=(4, 2), tags=("mc",))
            label = "%s №%d" % (TYPE_LABEL.get(s["type"], s["type"])[:1], int(s.get("id", 0)))
            cv.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=label, fill="#0c0c14", font=("Arial", 9, "bold"), tags=("mc",))
            ch = s.get("channel", "")
            if ch: cv.create_text((x0 + x1) / 2, y1 - 3, text=ch, fill="#cfe3ff", font=("Arial", 8), tags=("mc",))
            if s.get("type") == "mover": self._draw_mover_path(s, i == self.sel)
            elif s.get("type") == "elevator": self._draw_elevator_ghost(s)
        self._draw_wire_dots()
        if self.wire_mode.get() and self.wire_src is not None and self._mouse_px is not None:
            x0, y0 = self._center_px(self.wire_src)
            for it in cv.find_withtag("wirepend"): cv.delete(it)   # одна линия-пунктир, а не копия на каждую перерисовку
            cv.create_line(x0, y0, self._mouse_px[0], self._mouse_px[1], fill=WIRE_SRC, dash=(5, 4), width=2, tags=("wirepend",))

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
        self.sel = None; self.wire_src = None; self._drag_pt = None
        self._load_fields()

    def load_wires(self, wires):
        """Провода из файла карты (поле "wires"): [{"a": id, "b": id}]. Только для редактора."""
        self.wires = []
        for w in wires or []:
            if isinstance(w, dict) and "a" in w and "b" in w:
                try: self.wires.append({"a": int(w["a"]), "b": int(w["b"])})
                except (TypeError, ValueError): continue
        self.wire_src = None; self._drop_pending(); self._refresh_info()

    def dump_wires(self):
        """Провода для файла карты: только между существующими разными механизмами."""
        ids = {int(s.get("id", 0)) for s in self.ed.mechs}
        out = []
        for w in self.wires:
            try: a, b = int(w["a"]), int(w["b"])
            except (TypeError, ValueError, KeyError): continue
            if a != b and a in ids and b in ids: out.append({"a": a, "b": b})
        return out

    def dump(self):
        return [clean_spec(s) for s in self.ed.mechs]

    def crop(self, w, h):
        keep = [s for s in self.ed.mechs if all(0 <= c < w and 0 <= r < h for c, r in self.cells_of(s))]
        for s in keep:
            if s.get("path"):
                s["path"] = [p for p in s["path"] if 0 <= int(p[0]) < w and 0 <= int(p[1]) < h]
        if len(keep) != len(self.ed.mechs): self.ed.status.set("Убрано механизмов за краем карты: %d." % (len(self.ed.mechs) - len(keep)))
        self.ed.mechs = keep
        ids = {int(s.get("id", 0)) for s in keep}
        self.wires = [w for w in self.wires if int(w.get("a", -1)) in ids and int(w.get("b", -1)) in ids]
        self._fix_orphan_pairs()
        self.sel = None; self.wire_src = None; self._drag_pt = None; self._load_fields()

    def reset(self):
        self.ed.mechs = []; self.sel = None
        self.wires = []; self.wire_src = None; self._drag_pt = None
        self._drop_pending(); self._load_fields(); self._refresh_info()
