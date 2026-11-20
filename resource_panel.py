"""Панель «Ресурсы» редактора карт (вкладка «  Ресурсы  » в редакторе карт).

Здесь можно:
  • выбрать кисть ресурса (древесина/металл/кристалл/огонь/случайный) и рисовать им
    прямо по сетке карты — на каждой клетке появится точка спавна ресурса (в игре
    это crafting.ResourceDrop, ставится в room.drops через maps.GameMap);
  • переопределить случайный разброс ресурсов именно для этой карты: сколько ресурсов
    разбрасывать при входе (per_room) и веса типов (weights). Настройки пишутся в файл
    карты в поле "resources" и работают только для неё (глобальные — в data/crafting.json).

Панель не перехватывает клики по холсту (active() == False) — ресурсы ставятся как
обычные клетки той кистью, что выбрана здесь или во вкладке «Сетка».
"""
import tkinter as tk
from tkinter import ttk

# (char, заголовок, подсказка) — кисти ресурсов. Эти символы уже есть в PALETTE редактора,
# здесь они продублированы, чтобы «Ресурсы» были отдельной вкладкой.
RESOURCE_BRUSHES = [
    ("W", "Древесина", "wood", "#a26e3e"),
    ("N", "Металл", "metal", "#96a2b9"),
    ("K", "Кристалл", "crystal", "#78dcff"),
    ("F", "Огонь", "fire", "#ff9628"),
    ("Z", "Случайный", "random", "#e8d8a0"),
]

RESOURCE_IDS = ["wood", "metal", "crystal", "fire"]
RESOURCE_NAMES = {"wood": "Древесина", "metal": "Металл", "crystal": "Кристалл", "fire": "Огонь"}


class ResourcePanel:
    """Настройки ресурсов карты (расстановка + случайный разброс). Не создаёт записи — только кисти и поля."""

    def __init__(self, ed, parent, root, cell, palette):
        self.ed = ed
        self.root = root
        self.cell = cell
        self.palette = palette
        self.scatter_enabled = tk.BooleanVar(value=False)
        self.per_room = tk.StringVar(value="")
        self.weights = {rid: tk.StringVar(value="") for rid in RESOURCE_IDS}
        self._ui(parent)

    # ---- интерфейс ----
    def _ui(self, parent):
        body = ttk.Frame(parent, padding=6); body.pack(fill="x")
        ttk.Label(body, text="Кисть ресурса (рисуй по сетке — клетка станет точкой спавна):",
                  foreground="#9a9aa8").pack(anchor="w")
        grid = ttk.Frame(body); grid.pack(fill="x", pady=(4, 8))
        for i, (ch, title, _rid, color) in enumerate(RESOURCE_BRUSHES):
            ttk.Radiobutton(grid, text="%s  %s" % (ch, title), value=ch,
                            variable=self.ed.brush).grid(row=0, column=i, padx=(0, 10), sticky="w")
        ttk.Label(body, text="Точки спавна рисуются той кистью, что выбрана слева "
                             "(или во вкладке «Сетка»). В игре ресурс появляется на этой клетке. "
                             "Случайный — берёт любой из четырёх ресурсов.",
                  foreground="#6a6a78", wraplength=560).pack(anchor="w", pady=(0, 8))
        ttk.Separator(body).pack(fill="x", pady=6)

        # ---- случайный разброс именно этой карты (перекрывает data/crafting.json -> scatter) ----
        ttk.Label(body, text="Свой разброс ресурсов для этой карты (пусто — общий из data/crafting.json):",
                  foreground="#9a9aa8").pack(anchor="w")
        ttk.Checkbutton(body, text="Переопределить разброс на этой карте", variable=self.scatter_enabled,
                        command=self._toggle_scatter).pack(anchor="w", pady=(2, 4))
        row = ttk.Frame(body); row.pack(fill="x", pady=4)
        ttk.Label(row, text="Ресурсов в комнате:").pack(side="left")
        self._spins = [ttk.Spinbox(row, from_=0, to=60, increment=1, textvariable=self.per_room, width=6)]
        self._spins[0].pack(side="left", padx=6)
        wf = ttk.LabelFrame(body, text="Веса типов (чем больше — тем чаще):")
        wf.pack(fill="x", pady=4)
        for i, rid in enumerate(RESOURCE_IDS):
            ttk.Label(wf, text=RESOURCE_NAMES[rid]).grid(row=0, column=i * 2, padx=(8, 3), pady=4, sticky="e")
            sp = ttk.Spinbox(wf, from_=0, to=100, increment=0.5, textvariable=self.weights[rid], width=6)
            sp.grid(row=0, column=i * 2 + 1, padx=(0, 10), pady=4, sticky="w")
            self._spins.append(sp)
        self._toggle_scatter()
        ttk.Label(body, text="Поле \"resources\" в файле карты: {«per_room», «weights»}. "
                             "Сохраняется при нажатии «Сохранить».",
                  foreground="#6a6a78", wraplength=560).pack(anchor="w", pady=4)

    def _toggle_scatter(self):
        st = "normal" if self.scatter_enabled.get() else "disabled"
        for child in getattr(self, "_spins", ()):
            try: child.configure(state=st)
            except tk.TclError: pass

    def active(self):
        """Ресурсы не перехватывают клики по холсту — рисуются как обычные клетки."""
        return False

    def cur(self):
        return None

    # ---- сохранение / загрузка ----
    def dump(self):
        """Поле \"resources\" карты: None или словарь разброса."""
        if not self.scatter_enabled.get():
            return None
        out = {}
        try:
            n = int(float(self.per_room.get() or 0))
            if n > 0: out["per_room"] = n
        except (ValueError, TypeError): pass
        wts = {}
        for rid, var in self.weights.items():
            try:
                v = float(var.get())
                if v > 0: wts[rid] = round(v * 10) / 10
            except (ValueError, TypeError): pass
        if wts: out["weights"] = wts
        return out or None

    def load(self, data):
        """Загрузить разброс из файла карты (data.get(\"resources\"))."""
        data = data if isinstance(data, dict) else {}
        self.scatter_enabled.set(bool(data) and bool(
            ("per_room" in data) or ("weights" in data)))
        self.per_room.set(str(data.get("per_room", "")) if data.get("per_room") is not None else "")
        for rid, var in self.weights.items():
            w = data.get("weights") or {}
            var.set(str(w[rid]) if rid in w else "")
        self._toggle_scatter()

    def reset(self):
        self.scatter_enabled.set(False); self.per_room.set("")
        for var in self.weights.values(): var.set("")
        self._toggle_scatter()

    def crop(self, w, h):
        pass   # ресурсы — клетки сетки и настройки, ничего резать не нужно
