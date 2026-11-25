"""Вкладка «Торговцы» редактора (map_editor.py): выбор существующего NPC-торговца и настройка его ассортимента.

Данные лежат в data/npcs.json -> "npcs" (их читает npc.py, окно торговли — trade.py).
    "trader": {"name": "...", "description": "...", "trader": true, "price_mult": 1.0,
               "speed": 34, "assortment": ["rusty_sword", "stub_helmet", ...]}
Ассортимент: список id предметов (data/weapons.json и assets/inventory.json -> items).
Пустой/не задан — торговец продаёт ВСЕ предметы игры. Внешность торговца — в ассетах
(assets/npcs/<id>/npc.json + кадры idle/, move/ или один скин assets/npcs/<id>.png).
Расстановка NPC по картам — вкладка «NPC» редактора карт (npc_panel.py).
Запуск отдельно: python trader_editor.py
"""
import copy, json, re
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox

ROOT = Path(__file__).resolve().parent
NPCS_FILE = ROOT / "data" / "npcs.json"
WEAPONS_FILE = ROOT / "data" / "weapons.json"
INV_FILE = ROOT / "assets" / "inventory.json"

ID_RE = re.compile(r"^[a-z0-9_]+$")
DEFAULTS = {"name": "Торговец", "description": "", "trader": True, "w": 20, "h": 34,
            "speed": 34, "price_mult": 1.0, "assortment": [], "color": [210, 170, 90]}

try:
    from npc import TYPE_PRICES, DEFAULT_PRICE, base_price, sell_price_of, sell_ratio
except Exception:   # вкладка работает и без игровой части (npc.py тянет pygame) — цены считаем грубо
    TYPE_PRICES = {"weapon": 80, "resource": 15}
    DEFAULT_PRICE = 45
    def base_price(wid): return float(_item_def(wid).get("price") or TYPE_PRICES.get(_item_type(wid), DEFAULT_PRICE))
    def sell_price_of(wid): return max(1, int(base_price(wid) * 0.4))
    def sell_ratio(): return 0.4


def _load(path, default):
    try: return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError): return default


def _items_data():
    """Все торговые предметы игры: {id: {...}} из weapons.json + assets/inventory.json -> items."""
    out = {}
    for wid, d in (_load(WEAPONS_FILE, {}) or {}).items():
        if not wid.startswith("_") and isinstance(d, dict): out[wid] = d
    for wid, d in ((_load(INV_FILE, {}) or {}).get("items") or {}).items():
        if not wid.startswith("_") and isinstance(d, dict) and not d.get("count"): out.setdefault(wid, d)
    return out


def _item_def(wid): return _items_data().get(wid) or {}
def _item_type(wid): return str(_item_def(wid).get("type", "weapon" if wid in (_load(WEAPONS_FILE, {}) or {}) else "misc"))
def _item_name(wid): return str(_item_def(wid).get("name") or wid)


class TraderTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.cur = None                 # id выбранного NPC
        self._loading = False
        self.status = tk.StringVar(value="")
        self.v = {k: tk.StringVar() for k in ("id", "name", "price_mult", "speed", "w", "h")}
        self.all_items = _items_data()
        self.data = _load(NPCS_FILE, None)
        if not isinstance(self.data, dict):
            ttk.Label(self, text=f"Не удалось прочитать {NPCS_FILE}", foreground="#b00020").pack(padx=16, pady=16, anchor="nw")
            self.npcs = {}; self.saved = ""; return
        self.data.setdefault("sell_ratio", 0.4)
        self.npcs = self.data.setdefault("npcs", {})
        self.saved = self._dump()
        self._build()
        self._refresh_list()
        ids = self._ids()
        if ids: self.select(ids[0])

    # ---------- данные ----------
    def _ids(self): return [k for k, v in self.npcs.items() if not k.startswith("_") and isinstance(v, dict)]
    def _dump(self): return json.dumps(self.data, ensure_ascii=False, sort_keys=True)
    def dirty(self): return self._dump() != self.saved

    # ---------- UI ----------
    def _build(self):
        left = ttk.Frame(self, padding=6); left.pack(side="left", fill="y")
        ttk.Label(left, text="NPC и торговцы", font=("Arial", 12, "bold")).pack(anchor="w")
        self.lb = tk.Listbox(left, width=32, height=30, exportselection=False); self.lb.pack(fill="y", expand=True, pady=4)
        self.lb.bind("<<ListboxSelect>>", self._on_list)
        b = ttk.Frame(left); b.pack(fill="x")
        ttk.Button(b, text="Новый торговец", command=self.new).pack(side="left", padx=2)
        ttk.Button(b, text="Копия", command=self.copy).pack(side="left", padx=2)
        ttk.Button(b, text="Удалить", command=self.delete).pack(side="left", padx=2)
        ttk.Label(left, text="Торговцы помечены «●».\nРасстановка NPC по картам — вкладка «NPC»\nв разделе «Карты».\nВнешность — assets/npcs/<id>/.",
                  foreground="#6a6a78", justify="left").pack(anchor="w", pady=(6, 0))

        wrap = ttk.Frame(self); wrap.pack(side="left", fill="both", expand=True, padx=8, pady=6)
        cv = tk.Canvas(wrap, highlightthickness=0, width=520)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=cv.yview); cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y"); cv.pack(side="left", fill="both", expand=True)
        f = ttk.Frame(cv); cv.create_window((0, 0), window=f, anchor="nw")
        f.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))

        def row(parent, label, var, width=24):
            r = ttk.Frame(parent); r.pack(fill="x", pady=2)
            ttk.Label(r, text=label, width=22).pack(side="left")
            w = ttk.Entry(r, textvariable=var, width=width); w.pack(side="left"); return r, w

        row(f, "ID (англ., a-z 0-9 _):", self.v["id"])
        row(f, "Имя:", self.v["name"], 36)
        self.trader = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text="Это торговец (на E у него открывается торговля)", variable=self.trader).pack(anchor="w", pady=(4, 2))
        row(f, "Множитель цен (price_mult):", self.v["price_mult"], 10)
        row(f, "Скорость ходьбы (px/с):", self.v["speed"], 10)
        hb = ttk.Frame(f); hb.pack(fill="x", pady=2)
        ttk.Label(hb, text="Хитбокс: ширина / высота", width=22).pack(side="left")
        ttk.Entry(hb, textvariable=self.v["w"], width=6).pack(side="left"); ttk.Entry(hb, textvariable=self.v["h"], width=6).pack(side="left", padx=(4, 0))
        ttk.Label(f, text="Краткое описание (видно в окне торговли):").pack(anchor="w", pady=(6, 0))
        self.desc = tk.Text(f, width=58, height=3, wrap="word"); self.desc.pack(fill="x")

        # ---------- ассортимент ----------
        af = ttk.LabelFrame(f, text="Ассортимент (что продаёт этот торговец)", padding=6); af.pack(fill="x", pady=8)
        self.everything = tk.BooleanVar(value=True)
        ttk.Checkbutton(af, text="Продаёт ВСЕ предметы игры (пока у торговца не задан свой ассортимент)",
                        variable=self.everything, command=self._toggle_assortment).pack(anchor="w")
        self.tree = ttk.Treeview(af, columns=("item", "name", "buy", "sell"), show="headings", height=9)
        for col, title, w in (("item", "ID предмета", 150), ("name", "Название", 180), ("buy", "Цена покупки", 80), ("sell", "Цена продажи", 80)):
            self.tree.heading(col, text=title); self.tree.column(col, width=w, anchor="w")
        self.tree.pack(fill="x", pady=4)
        ar = ttk.Frame(af); ar.pack(fill="x")
        ttk.Label(ar, text="Добавить предмет:").pack(side="left")
        self.item_box = ttk.Combobox(ar, width=26, state="readonly"); self.item_box.pack(side="left", padx=4)
        ttk.Button(ar, text="+ Добавить", command=self.add_item).pack(side="left", padx=2)
        ttk.Button(ar, text="− Убрать выбранный", command=self.remove_item).pack(side="left", padx=2)
        self._fill_items()

        ttk.Button(f, text="💾 Сохранить", command=self.save).pack(fill="x", pady=8)
        ttk.Label(f, textvariable=self.status, foreground="#2a6", wraplength=460).pack(fill="x")
        self._toggle_assortment()

    def _fill_items(self):
        ids = sorted(self.all_items, key=lambda wid: _item_name(wid).lower())
        self.item_box["values"] = ids
        if ids: self.item_box.set(ids[0])
        self.item_box.state(["readonly"])

    # ---------- список ----------
    def _refresh_list(self, select=None):
        self.lb.delete(0, "end")
        for i, k in enumerate(self._ids()):
            d = self.npcs[k]
            mark = "● " if d.get("trader") else "  "
            n = len(d.get("assortment") or [])
            tail = "" if n == 0 else f"  [{n} товаров]"
            self.lb.insert("end", f"{mark}{k} — {d.get('name', '')}{tail}")
            if k == select: self.lb.selection_set(i); self.lb.see(i)

    def _on_list(self, _e=None):
        sel = self.lb.curselection()
        if not sel or self._loading: return
        nid = self._ids()[sel[0]]
        if nid == self.cur: return
        if self.cur is not None and not self.commit(quiet=True):
            self._refresh_list(self.cur); return
        self.select(nid)

    def select(self, iid):
        self._loading = True
        self.cur = iid; d = copy.deepcopy(DEFAULTS); d.update(self.npcs.get(iid, {}))
        self.v["id"].set(iid); self.v["name"].set(str(d.get("name") or iid))
        self.trader.set(bool(d.get("trader")))
        self.v["price_mult"].set(str(d.get("price_mult", 1.0)))
        self.v["speed"].set(str(d.get("speed", 34)))
        self.v["w"].set(str(d.get("w", 20))); self.v["h"].set(str(d.get("h", 34)))
        self.desc.delete("1.0", "end"); self.desc.insert("1.0", str(d.get("description") or ""))
        self.everything.set(not (d.get("assortment") or []))
        self._fill_assortment()
        self._refresh_list(iid)
        self._toggle_assortment()
        self.status.set("")
        self._loading = False

    # ---------- ассортимент ----------
    def _fill_assortment(self):
        self.tree.delete(*self.tree.get_children())
        d = self.npcs.get(self.cur) or {}
        for wid in (d.get("assortment") or []):
            if not isinstance(wid, str): continue
            self.tree.insert("", "end", values=(wid, _item_name(wid), base_price(wid), sell_price_of(wid)))

    def _toggle_assortment(self):
        st = "disabled" if self.everything.get() else "normal"
        for w in (self.tree, self.item_box):
            try: w.configure(state=st)
            except tk.TclError: pass

    def add_item(self):
        if self.cur is None or self.everything.get(): return
        wid = self.item_box.get().strip()
        if not wid: return
        d = self.npcs.setdefault(self.cur, {})
        a = d.setdefault("assortment", [])
        if wid not in a: a.append(wid)
        self._fill_assortment(); self._refresh_list(self.cur)
        self.status.set("Предмет добавлен — не забудь «Сохранить».")

    def remove_item(self):
        if self.cur is None or self.everything.get(): return
        sel = self.tree.selection()
        if not sel: return
        wid = self.tree.item(sel[0], "values")[0]
        d = self.npcs.get(self.cur) or {}
        a = d.get("assortment") or []
        if wid in a: a.remove(wid)
        self._fill_assortment(); self._refresh_list(self.cur)
        self.status.set("Предмет убран — не забудь «Сохранить».")

    # ---------- форма -> данные ----------
    def commit(self, quiet=False):
        if self.cur is None: return True
        old = self.cur; nid = self.v["id"].get().strip()
        def err(msg):
            if not quiet: messagebox.showerror("Торговец", msg)
            return False
        if not ID_RE.match(nid): return err("ID: только маленькие латинские буквы, цифры и _.")
        if nid != old and nid in self.npcs: return err(f"ID «{nid}» уже занят.")
        try: mult = max(0.1, float((self.v["price_mult"].get() or "1").replace(",", ".")))
        except ValueError: return err("Множитель цен: нужно число (1 — обычные цены).")
        try: speed = max(0.0, float((self.v["speed"].get() or "34").replace(",", ".")))
        except ValueError: return err("Скорость: нужно число.")
        try: w, h = max(6, int(self.v["w"].get() or 20)), max(8, int(self.v["h"].get() or 34))
        except ValueError: return err("Хитбокс: ширина и высота — целые числа.")
        it = copy.deepcopy(self.npcs.get(old, {}))
        it["name"] = self.v["name"].get().strip() or nid
        it["trader"] = bool(self.trader.get())
        it["price_mult"] = round(mult, 3)
        it["speed"] = speed
        it["w"], it["h"] = w, h
        desc = self.desc.get("1.0", "end").strip()
        if desc: it["description"] = desc
        else: it.pop("description", None)
        if not self.everything.get():
            a = [x for x in (it.get("assortment") or []) if isinstance(x, str)]
            it["assortment"] = a
        else:
            it["assortment"] = []   # пусто = торгует всеми предметами игры
        if nid != old:   # переименование: сохранить позицию в словаре
            pairs = list(self.npcs.items()); self.npcs.clear()
            for k, val in pairs: self.npcs[nid if k == old else k] = it if k == old else val
            self.cur = nid
        else:
            self.npcs[old] = it
        self._refresh_list(self.cur)
        return True

    def _free_id(self, base):
        n = 1
        while f"{base}_{n}" in self.npcs: n += 1
        return f"{base}_{n}"

    def new(self):
        if self.cur is not None and not self.commit(quiet=True): return
        nid = self._free_id("trader")
        self.npcs[nid] = {"name": "Новый торговец", "description": "", "trader": True, "w": 20, "h": 34,
                          "speed": 34, "price_mult": 1.0, "assortment": []}
        self._refresh_list(nid); self.select(nid)
        self.status.set("Создан в памяти — не забудь «Сохранить».")

    def copy(self):
        if self.cur is None or not self.commit(quiet=True): return
        nid = self._free_id(self.cur)
        self.npcs[nid] = copy.deepcopy(self.npcs[self.cur]); self.npcs[nid]["name"] = self.npcs[nid].get("name", "") + " (копия)"
        self.select(nid)

    def delete(self):
        if self.cur is None: return
        if not messagebox.askyesno("Удалить", f"Удалить NPC «{self.cur}»?\n(Изменение запишется при сохранении.)"): return
        ids = self._ids(); i = ids.index(self.cur)
        del self.npcs[self.cur]
        self.cur = None; ids = self._ids()
        if ids: self.select(ids[min(i, len(ids) - 1)])
        else: self._refresh_list()
        self.status.set("Удалён — нажми «Сохранить», чтобы записать в файл.")

    def save(self):
        if not self.commit(): return False
        try:
            NPCS_FILE.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError as e:
            messagebox.showerror("Ошибка сохранения", str(e)); return False
        self.saved = self._dump()
        self.status.set("Сохранено в data/npcs.json. В игре — F5, чтобы перечитать; в редакторе карт — перезакрой карту.")
        return True

    def confirm_close(self):
        if not hasattr(self, "lb"): return True
        if self.cur is not None and not self.commit(quiet=True): return False
        if not self.dirty(): return True
        ans = messagebox.askyesnocancel("Торговцы", "Сохранить изменения торговцев?")
        if ans is None: return False
        return self.save() if ans else True


if __name__ == "__main__":
    root = tk.Tk(); root.title("DEAD ROOMS — торговцы"); root.geometry("1100x760")
    tab = TraderTab(root); tab.pack(fill="both", expand=True)
    root.protocol("WM_DELETE_WINDOW", lambda: tab.confirm_close() and root.destroy())
    root.mainloop()
