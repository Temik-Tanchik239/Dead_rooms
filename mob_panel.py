"""Панель «Мобы» редактора карт (вкладка «  Мобы  »): расстановка мобов по карте.

Здесь можно:
  • выбрать моба из data/mobs.json -> CFG["mobs"] (ротлинг, костяной стрелок... свои типы
    добавляются на вкладке «Мобы» — там же редактор мобов);
  • ЛКМ — поставить выбранного моба на клетку, ПКМ — убрать моба с клетки;
  • в одной клетке один моб; моб не ставится в стену, лестницу, шипы, старт героя и клетку выхода.

Записи пишутся в файл карты в поле "mobs": [{"mob": "rotling", "x": клетка, "y": клетка}].
В игре карта спавнит их при входе (maps.py -> GameMap.spawn), как и мобов из легенды (символ S и др.).
"""
import tkinter as tk
from tkinter import ttk

try:
    from core import CFG
except Exception:
    CFG = {}


def mob_defs():
    """Регистр мобов (data/mobs.json -> CFG["mobs"]); файл может отсутствовать."""
    return (CFG.get("mobs") or {})


def mob_title(mid):
    """«rotling — marionetka» для списка."""
    d = mob_defs().get(mid) or {}
    name = d.get("name", mid)
    return f"{mid} — {name}" if name and name != mid else mid


def mob_color(mid, default="#d58bff"):
    """Цвет клетки-моба на холсте: цвет моба из data/mobs.json, иначе сиреневый."""
    d = mob_defs().get(mid) or {}
    c = d.get("color")
    if isinstance(c, (list, tuple)) and len(c) >= 3:
        return "#%02x%02x%02x" % tuple(max(0, min(255, int(v))) for v in c[:3])
    return default


def alive_ids():
    """Мобы, которых можно ставить (служебные имена вида __boss__ не показываются)."""
    return [mid for mid in mob_defs() if not str(mid).startswith("__")]


class MobPanel:
    """Кисть мобов: ЛКМ — поставить, ПКМ — убрать (как у NPC)."""

    def __init__(self, ed, parent, root, cell, palette):
        self.ed = ed
        self.root = root
        self.cell = cell
        self.palette = palette
        self.mode = tk.BooleanVar(value=False)   # режим мобов: клики по холсту — расстановка
        self.mob = tk.StringVar(value=next(iter(alive_ids()), ""))
        self.entries = []                        # [{"mob", "x", "y"}] — записи текущей карты
        self._ui(parent)
        self.mode.trace_add("write", lambda *_: self._mode_changed())

    # ---- интерфейс ----
    def _ui(self, parent):
        body = ttk.Frame(parent, padding=6); body.pack(fill="x")
        row = ttk.Frame(body); row.pack(fill="x", pady=(0, 4))
        ttk.Checkbutton(row, text="Режим мобов (ЛКМ — поставить, ПКМ — убрать)", variable=self.mode).pack(side="left")
        ttk.Label(body, text="Моб:").pack(anchor="w")
        self.box = ttk.Combobox(body, textvariable=self.mob, state="readonly", width=40)
        self.box.pack(anchor="w", pady=(2, 4))
        self.refresh()
        ttk.Label(body, text="Моб ставится на пол клетки и в игре появляется при входе на карту. Характеристики, атаки и "
                             "поведения моба — на вкладке «Мобы» (редактор мобов, data/mobs.json); там же задаются новые "
                             "атаки (рывок, луч, бомба-лужа, лечение, призыв) и поведения (охрана поста, бегство, телепорт, нырок).",
                  foreground="#6a6a78", wraplength=560).pack(anchor="w")
        self.hint = tk.StringVar(value="")

    def refresh(self):
        """Перечитать список мобов (после правки data/mobs.json или F5)."""
        ids = alive_ids()
        self.box["values"] = [mob_title(mid) for mid in ids]
        self._ids = ids
        if self.mob.get() not in ids and ids:
            self.mob.set(ids[0])

    def _mode_changed(self):
        self.hint.set("Режим мобов: ЛКМ — поставить выбранного моба, ПКМ — убрать." if self.mode.get() else "")

    def active(self):
        return self.mode.get()

    def cur(self):
        """id выбранного моба (для статуса)."""
        return self.mob.get()

    # ---- расстановка
    def place(self, x, y):
        """ЛКМ: поставить моба на клетку (x, y)."""
        mid = self.mob.get()
        if not mid: return
        for e in self.entries:   # в одной клетке один моб
            if e.get("x") == x and e.get("y") == y: return
        self.entries.append({"mob": mid, "x": x, "y": y})
        self.ed.status.set(f"Моб «{mob_title(mid)}» поставлен в клетку ({x}, {y})")

    def erase(self, event):
        """ПКМ: убрать моба с клетки."""
        x, y = self.ed._cell_from_event(event)
        for e in list(self.entries):
            if e.get("x") == x and e.get("y") == y:
                self.entries.remove(e)
                self.ed.status.set(f"Моб в клетке ({x}, {y}) убран")
                return

    def click(self, event):
        x, y = self.ed._cell_from_event(event)
        if not (0 <= x < self.ed.map_w and 0 <= y < self.ed.map_h): return
        self.place(x, y)

    def can_place(self, x, y):
        """Клетка годится: не стена, не лестница, не шипы, не старт героя и не клетка выхода."""
        rows = self.ed.rows
        if not (0 <= x < self.ed.map_w and 0 <= y < self.ed.map_h): return False
        if rows[y][x] in "#=HxP": return False
        return True

    # ---- отрисовка на холсте
    def draw(self):
        cv = self.ed.canvas; k = self.ed.cell_size()
        for e in self.entries:
            x, y, mid = e.get("x"), e.get("y"), e.get("mob")
            if not isinstance(x, int) or not isinstance(y, int): continue
            color = mob_color(mid)
            cv.create_rectangle(x * k + 2, y * k + 2, (x + 1) * k - 2, (y + 1) * k - 2, fill=color, outline="#ffe0ff", width=2, tags="mobsc")
            label = (mob_defs().get(mid, {}).get("name") or str(mid))[:5]
            cv.create_text((x + 0.5) * k, (y + 0.5) * k, text=label, fill="#241a10", font=("TkDefaultFont", max(7, int(k / 4)), "bold"), tags="mobsc")

    # ---- сохранение / загрузка
    def clean(self):
        """Убрать битые записи: неизвестный моб, не числа, стена/выход, клетка за краем, дубли."""
        out = []
        for e in self.entries:
            if not isinstance(e, dict) or e.get("mob") not in mob_defs(): continue
            try: x, y = int(e["x"]), int(e["y"])
            except (TypeError, ValueError): continue
            if not self.can_place(x, y): continue
            if any(o.get("x") == x and o.get("y") == y for o in out): continue
            out.append({"mob": e["mob"], "x": x, "y": y})
        return out

    def dump(self):
        """Поле "mobs" карты: [] если мобов нет."""
        return self.clean()

    def load(self, data):
        """Загрузить записи из файла карты (data.get("mobs"))."""
        self.entries = [dict(e) for e in (data or []) if isinstance(e, dict)]

    def reset(self):
        self.entries = []

    def crop(self, w, h):
        self.entries = [e for e in self.entries if isinstance(e.get("x"), int) and isinstance(e.get("y"), int)
                        and 0 <= e["x"] < w and 0 <= e["y"] < h]
