"""Панель «NPC» редактора карт (вкладка «  NPC  »): расстановка NPC по карте.

Здесь можно:
  • выбрать NPC из data/npcs.json -> npcs (торговец, житель, стражник — свои типы
    добавляются в data/npcs.json или на вкладке «Торговцы»);
  • ЛКМ — поставить выбранного NPC на клетку, ПКМ — убрать NPC с клетки;
  • NPC ставится на пол клетки (в стену, на шипы и клетку выхода не ставится).

Записи пишутся в файл карты в поле "npcs": [{"type": "trader", "x": клетка, "y": клетка}].
В игре NPC гуляют по карте; у торговца на E открывается окно торговли (npc.py, trade.py).
"""
import tkinter as tk
from tkinter import ttk

try:
    from core import CFG
except Exception:
    CFG = {}


def npc_defs():
    """Регистр NPC (data/npcs.json -> npcs); файл может отсутствовать."""
    return (CFG.get("npcs") or {}).get("npcs") or {}


def npc_color(tid, default="#c8aa78"):
    """Цвет клетки-NPC на холсте: цвет-заглушка из data/npcs.json, иначе бежевый."""
    d = npc_defs().get(tid) or {}
    c = d.get("color")
    if isinstance(c, (list, tuple)) and len(c) >= 3:
        return "#%02x%02x%02x" % tuple(max(0, min(255, int(v))) for v in c[:3])
    return default


class NpcPanel:
    """Кисть NPC: ЛКМ — поставить, ПКМ — убрать (как у ящиков)."""

    def __init__(self, ed, parent, root, cell, palette):
        self.ed = ed
        self.root = root
        self.cell = cell
        self.palette = palette
        self.mode = tk.BooleanVar(value=False)   # режим NPC: клики по холсту — расстановка
        self.npc = tk.StringVar(value=next(iter(npc_defs()), ""))
        self.entries = []                        # [{"type", "x", "y"}] — записи текущей карты
        self._ui(parent)
        self.mode.trace_add("write", lambda *_: self._mode_changed())

    # ---- интерфейс ----
    def _ui(self, parent):
        body = ttk.Frame(parent, padding=6); body.pack(fill="x")
        row = ttk.Frame(body); row.pack(fill="x", pady=(0, 4))
        ttk.Checkbutton(row, text="Режим NPC (ЛКМ — поставить, ПКМ — убрать)", variable=self.mode).pack(side="left")
        ttk.Label(body, text="NPC:").pack(anchor="w")
        self.box = ttk.Combobox(body, textvariable=self.npc, state="readonly", width=28)
        self.box.pack(anchor="w", pady=(2, 4))
        self.refresh()
        ttk.Label(body, text="NPC ставится на пол клетки и в игре гуляет по карте. У NPC с полем \"trader\": true "
                             "(в data/npcs.json) игрок на E открывает окно торговли. Ассортимент торговца — "
                             "на вкладке «Торговцы», внешность — в assets/npcs/<id>/npc.json.",
                  foreground="#6a6a78", wraplength=560).pack(anchor="w")
        self.hint = tk.StringVar(value="")

    def refresh(self):
        """Перечитать список NPC (после правки data/npcs.json или F5)."""
        ids = list(npc_defs())
        self.box["values"] = ids
        if self.npc.get() not in ids and ids: self.npc.set(ids[0])

    def info(self, tid):
        d = npc_defs().get(tid) or {}
        mark = " • торговец" if d.get("trader") else ""
        return f"{d.get('name', tid)}{mark}"

    def _mode_changed(self):
        self.hint.set("Режим NPC: ЛКМ — поставить выбранного NPC, ПКМ — убрать." if self.mode.get() else "")

    def active(self):
        return self.mode.get()

    def cur(self):
        """id выбранного NPC (для статуса)."""
        return self.npc.get()

    # ---- расстановка
    def place(self, x, y):
        """ЛКМ: поставить NPC на клетку (x, y)."""
        tid = self.npc.get()
        if not tid: return
        for e in self.entries:   # в одной клетке один NPC
            if e.get("x") == x and e.get("y") == y: return
        self.entries.append({"type": tid, "x": x, "y": y})
        self.ed.status.set(f"NPC {self.info(tid)} поставлен в клетку ({x}, {y})")

    def erase(self, event):
        """ПКМ: убрать NPC с клетки."""
        x, y = self.ed._cell_from_event(event)
        for e in list(self.entries):
            if e.get("x") == x and e.get("y") == y:
                self.entries.remove(e)
                self.ed.status.set(f"NPC в клетке ({x}, {y}) убран")
                return

    def click(self, event):
        x, y = self.ed._cell_from_event(event)
        if not (0 <= x < self.ed.map_w and 0 <= y < self.ed.map_h): return
        self.place(x, y)

    def can_place(self, x, y):
        """Клетка годится: не стена, не лестница, не шипы, не выход и не старт героя."""
        rows = self.ed.rows
        if not (0 <= x < self.ed.map_w and 0 <= y < self.ed.map_h): return False
        if rows[y][x] in "#=HxP": return False
        return True

    # ---- отрисовка на холсте
    def draw(self):
        cv = self.ed.canvas; k = self.ed.cell_size()
        for e in self.entries:
            x, y, tid = e.get("x"), e.get("y"), e.get("type")
            if not isinstance(x, int) or not isinstance(y, int): continue
            color = npc_color(tid)
            cv.create_rectangle(x * k + 2, y * k + 2, (x + 1) * k - 2, (y + 1) * k - 2, fill=color, outline="#fff8e0", width=2, tags="npcs")
            cv.create_text((x + 0.5) * k, (y + 0.5) * k, text="NPC", fill="#241a10", font=("TkDefaultFont", max(8, int(k / 3)), "bold"), tags="npcs")

    # ---- сохранение / загрузка
    def clean(self):
        """Убрать битые записи: неизвестный тип, не числа, стена/выход, клетка за краем."""
        out = []
        for e in self.entries:
            if not isinstance(e, dict) or not e.get("type") or e["type"] not in npc_defs(): continue
            try: x, y = int(e["x"]), int(e["y"])
            except (TypeError, ValueError): continue
            if not self.can_place(x, y): continue
            if any(o.get("x") == x and o.get("y") == y for o in out): continue
            out.append({"type": e["type"], "x": x, "y": y})
        return out

    def dump(self):
        """Поле "npcs" карты: [] если NPC нет."""
        return self.clean()

    def load(self, data):
        """Загрузить записи из файла карты (data.get("npcs"))."""
        self.entries = [dict(e) for e in (data or []) if isinstance(e, dict)]

    def reset(self):
        self.entries = []

    def crop(self, w, h):
        self.entries = [e for e in self.entries if isinstance(e.get("x"), int) and isinstance(e.get("y"), int)
                        and 0 <= e["x"] < w and 0 <= e["y"] < h]
