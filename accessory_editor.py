"""Вкладка «Аксессуары» редактора (map_editor.py): создание и правка надеваемых предметов.

Аксессуары лежат в assets/inventory.json -> "items" (там же, где их читает инвентарь игры, см. inventory.py).
Записи, чей id есть в data/weapons.json, — описания оружия: здесь они не показываются и не меняются.
Формат аксессуара:
    "ring": {"name": "...", "type": "artifact", "rarity": "rare", "description": "...", "icon": "icons/ring.png",
             "bonuses": {"max_hp": 20, "max_mana": 10, "hp_regen": 1, "damage": 10, "move_speed": 5, "mana_regen": 20, "armor": 10},
             "skill": "dash", "effect": {"burn": {"time": 3, "dps": 10}}}
Запуск отдельно: python accessory_editor.py
"""
import copy, json, re, shutil
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
INV_FILE = ASSETS / "inventory.json"
WEAPONS_FILE = ROOT / "data" / "weapons.json"
SKILLS_FILE = ROOT / "data" / "skills.json"
ICON_DIR = ASSETS / "icons"

BONUSES = [("max_hp", "Макс. HP (+)"), ("max_mana", "Макс. мана (+)"), ("hp_regen", "Реген HP (+ед/с)"),
           ("damage", "Урон, %"), ("move_speed", "Скорость, %"), ("mana_regen", "Реген маны, %"),
           ("armor", "Броня, % (снижение урона)")]
EFFECTS = [("", "нет"), ("freeze", "заморозка (freeze)"), ("stun", "оглушение (stun)"), ("burn", "горение (burn)")]
EFFECT_NAME = dict(EFFECTS)
EFFECT_ID = {v: k for k, v in EFFECTS}
DEFAULT_TYPES = ["head", "neck", "glove", "belt", "boot", "artifact"]
MANAGED = ("name", "type", "rarity", "description", "icon", "bonuses", "skill", "effect")
ID_RE = re.compile(r"^[a-z0-9_]+$")


def _load(path, default):
    try: return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError): return default


def _num(v):
    v = float(v)
    return int(v) if v == int(v) else v


class AccessoryTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.cur = None                 # id выбранного аксессуара
        self.icon = tk.StringVar(value="")
        self.status = tk.StringVar(value="")
        self.v = {k: tk.StringVar() for k in ("id", "name", "type", "rarity", "skill", "eff", "eff_t", "eff_dps")}
        self.bv = {k: tk.StringVar() for k, _ in BONUSES}
        self._imgs = {}
        self._loading = False
        self.data = _load(INV_FILE, None)
        if not isinstance(self.data, dict):
            ttk.Label(self, text=f"Не удалось прочитать {INV_FILE}", foreground="#b00020").pack(padx=16, pady=16, anchor="nw")
            self.items = {}; self.saved = ""; return
        self.data.setdefault("items", {})
        self.items = self.data["items"]
        self.weapons = set(_load(WEAPONS_FILE, {}) or {})
        self.skills = {k: v for k, v in (_load(SKILLS_FILE, {}) or {}).items() if not k.startswith("_") and isinstance(v, dict)}
        self.saved = self._dump()
        self._build()
        self._refresh_list()
        ids = self._ids()
        if ids: self.select(ids[0])

    # ---------- данные ----------
    def _ids(self): return [k for k, v in self.items.items() if k not in self.weapons and isinstance(v, dict)]
    def _dump(self): return json.dumps(self.items, ensure_ascii=False, sort_keys=True)
    def dirty(self): return self._dump() != self.saved

    def _types(self):
        t = []
        for s in (self.data.get("equipment") or {}).get("slots", []):
            for a in s.get("accepts", []):
                if a != "*" and a not in t: t.append(a)
        for a in DEFAULT_TYPES:
            if a not in t: t.append(a)
        return t

    def _rarities(self): return list((self.data.get("rarities") or {"common": {}}).keys())

    # ---------- UI ----------
    def _build(self):
        left = ttk.Frame(self, padding=6); left.pack(side="left", fill="y")
        ttk.Label(left, text="Аксессуары", font=("Arial", 12, "bold")).pack(anchor="w")
        self.lb = tk.Listbox(left, width=34, height=30, exportselection=False); self.lb.pack(fill="y", expand=True, pady=4)
        self.lb.bind("<<ListboxSelect>>", self._on_list)
        b = ttk.Frame(left); b.pack(fill="x")
        ttk.Button(b, text="Новый", command=self.new).pack(side="left", padx=2)
        ttk.Button(b, text="Копия", command=self.copy).pack(side="left", padx=2)
        ttk.Button(b, text="Удалить", command=self.delete).pack(side="left", padx=2)

        # середина — прокручиваемая форма
        wrap = ttk.Frame(self); wrap.pack(side="left", fill="both", expand=True, padx=8, pady=6)
        cv = tk.Canvas(wrap, highlightthickness=0, width=470)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=cv.yview); cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y"); cv.pack(side="left", fill="both", expand=True)
        f = ttk.Frame(cv); cv.create_window((0, 0), window=f, anchor="nw")
        f.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        self._wheel(cv, cv)

        def row(parent, label, var, width=28, combo=None, readonly=False):
            r = ttk.Frame(parent); r.pack(fill="x", pady=2)
            ttk.Label(r, text=label, width=24).pack(side="left")
            if combo is None: w = ttk.Entry(r, textvariable=var, width=width)
            else: w = ttk.Combobox(r, textvariable=var, values=combo, width=width - 2, state="readonly" if readonly else "normal")
            w.pack(side="left"); return r, w

        row(f, "ID (англ., a-z 0-9 _):", self.v["id"])
        row(f, "Название:", self.v["name"], 36)
        row(f, "Слот (тип):", self.v["type"], 20, self._types())
        r, _ = row(f, "Редкость:", self.v["rarity"], 20, self._rarities(), True)
        self.rar_lbl = ttk.Label(r, foreground="#666"); self.rar_lbl.pack(side="left", padx=6)
        self.v["rarity"].trace_add("write", self._upd_labels)
        ttk.Label(f, text="Описание:").pack(anchor="w", pady=(4, 0))
        self.desc = tk.Text(f, width=56, height=4, wrap="word"); self.desc.pack(fill="x")

        st = ttk.LabelFrame(f, text="Статы (пусто или 0 — нет)", padding=6); st.pack(fill="x", pady=6)
        for k, lbl in BONUSES: row(st, lbl, self.bv[k], 10)

        sk = ttk.LabelFrame(f, text="Навык при надевании", padding=6); sk.pack(fill="x", pady=6)
        r, _ = row(sk, "Навык:", self.v["skill"], 26, [""] + sorted(self.skills), True)
        self.skill_lbl = ttk.Label(r, foreground="#666"); self.skill_lbl.pack(side="left", padx=6)
        self.v["skill"].trace_add("write", self._upd_labels)
        ttk.Label(sk, text="Навык выдаётся герою, пока предмет надет (снял — навык пропал).", foreground="#888").pack(anchor="w")

        ef = ttk.LabelFrame(f, text="Эффект при ударе", padding=6); ef.pack(fill="x", pady=6)
        row(ef, "Эффект:", self.v["eff"], 24, [n for _, n in EFFECTS], True)
        row(ef, "Секунды:", self.v["eff_t"], 10)
        row(ef, "Урон/с (только горение):", self.v["eff_dps"], 10)
        ttk.Label(ef, text="Накладывается на врага при ударе оружием (и пулями оружия).", foreground="#888").pack(anchor="w")

        ttk.Button(f, text="💾 Сохранить", command=self.save).pack(fill="x", pady=8)
        ttk.Label(f, textvariable=self.status, foreground="#2a6", wraplength=460).pack(fill="x")

        # справа — текстура
        right = ttk.LabelFrame(self, text="Текстура", padding=6); right.pack(side="left", fill="y", padx=6, pady=6)
        self.prev = tk.Canvas(right, width=96, height=96, bg="#22243a", highlightthickness=1); self.prev.pack(pady=4)
        ttk.Label(right, textvariable=self.icon, foreground="#666", wraplength=230).pack()
        bb = ttk.Frame(right); bb.pack(pady=4)
        ttk.Button(bb, text="Выбрать PNG…", command=self.pick_png).pack(side="left", padx=2)
        ttk.Button(bb, text="Убрать", command=lambda: self.icon.set("")).pack(side="left", padx=2)
        self.icon.trace_add("write", lambda *a: self._draw_preview())
        ttk.Label(right, text="Иконки из assets/icons:", foreground="#888").pack(anchor="w", pady=(6, 0))
        gw = ttk.Frame(right); gw.pack(fill="both", expand=True)
        gc = tk.Canvas(gw, width=232, height=420, highlightthickness=0)
        gs = ttk.Scrollbar(gw, orient="vertical", command=gc.yview); gc.configure(yscrollcommand=gs.set)
        gs.pack(side="right", fill="y"); gc.pack(side="left", fill="both", expand=True)
        self.grid_frame = ttk.Frame(gc); gc.create_window((0, 0), window=self.grid_frame, anchor="nw")
        self.grid_frame.bind("<Configure>", lambda e: gc.configure(scrollregion=gc.bbox("all")))
        self._wheel(gc, gc)
        self._fill_icons()

    def _wheel(self, widget, canvas):
        """Колесо мыши прокручивает canvas, только пока курсор над ним (другие вкладки не задеваются)."""
        def on(e): canvas.yview_scroll(int(-e.delta / 120) if e.delta else 0, "units")
        def lin(e): canvas.yview_scroll(-1 if e.num == 4 else 1, "units")
        saved = {}
        def enter(_):
            for s, fn in (("<MouseWheel>", on), ("<Button-4>", lin), ("<Button-5>", lin)):
                saved[s] = widget.bind_all(s); widget.bind_all(s, fn)
        def leave(_):   # вернуть чужие глобальные привязки (вкладка «Навыки» вешает колесо на bind_all)
            for s in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                widget.unbind_all(s)
                if saved.get(s): widget.bind_all(s, saved[s])
        widget.bind("<Enter>", enter); widget.bind("<Leave>", leave)

    def _photo(self, rel, size):
        key = (rel, size)
        if key not in self._imgs:
            img = None
            try:
                img = tk.PhotoImage(file=str(ASSETS / rel))
                k = max(1, -(-max(img.width(), img.height()) // size))
                if k > 1: img = img.subsample(k, k)
            except (tk.TclError, OSError): img = None
            self._imgs[key] = img
        return self._imgs[key]

    def _fill_icons(self):
        for w in self.grid_frame.winfo_children(): w.destroy()
        files = sorted(ICON_DIR.glob("*.png")) if ICON_DIR.is_dir() else []
        for i, p in enumerate(files):
            rel = f"icons/{p.name}"; img = self._photo(rel, 48)
            b = tk.Button(self.grid_frame, image=img, text="" if img else p.stem[:6], width=48 if img else 6, height=48 if img else 3,
                          command=lambda r=rel: self.icon.set(r))
            b.grid(row=i // 4, column=i % 4, padx=1, pady=1)
            _Tip(b, p.stem)

    def _draw_preview(self):
        c = self.prev; c.delete("all"); rel = self.icon.get()
        if not rel and self.cur:   # без поля icon игра берёт assets/icons/<id>.png
            img = self._photo(f"icons/{self.cur}.png", 96)
            if img:
                c.create_image(48, 48, image=img); c.create_text(48, 90, text="по id", fill="#ccc"); return
        img = self._photo(rel, 96) if rel else None
        if img: c.create_image(48, 48, image=img)
        else:
            c.create_rectangle(8, 8, 88, 88, fill="#555", outline="#888")
            c.create_text(48, 48, text="нет" if not rel else "нет файла", fill="#ddd")

    def _upd_labels(self, *_):
        r = (self.data.get("rarities") or {}).get(self.v["rarity"].get(), {})
        self.rar_lbl.configure(text=r.get("name", ""))
        self.skill_lbl.configure(text=self.skills.get(self.v["skill"].get(), {}).get("name", ""))

    # ---------- список ----------
    def _refresh_list(self, select=None):
        self.lb.delete(0, "end")
        for i, k in enumerate(self._ids()):
            self.lb.insert("end", f"{k} — {self.items[k].get('name', '')}")
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
        self.cur = iid; it = self.items.get(iid, {})
        self.v["id"].set(iid); self.v["name"].set(it.get("name", ""))
        self.v["type"].set(it.get("type", "artifact")); self.v["rarity"].set(it.get("rarity", "common"))
        self.desc.delete("1.0", "end"); self.desc.insert("1.0", it.get("description", ""))
        b = it.get("bonuses") if isinstance(it.get("bonuses"), dict) else {}
        for k, _ in BONUSES: self.bv[k].set("" if not b.get(k) else str(b[k]))
        self.v["skill"].set(it.get("skill", "") or "")
        eff = it.get("effect") if isinstance(it.get("effect"), dict) else {}
        kind = next((k for k, _ in EFFECTS if k and k in eff), "")
        self.v["eff"].set(EFFECT_NAME[kind]); self.v["eff_t"].set(""); self.v["eff_dps"].set("")
        if kind == "burn" and isinstance(eff["burn"], dict):
            self.v["eff_t"].set(str(eff["burn"].get("time", ""))); self.v["eff_dps"].set(str(eff["burn"].get("dps", "")))
        elif kind: self.v["eff_t"].set(str(eff[kind]))
        self.icon.set(it.get("icon", "") or ""); self._draw_preview()
        self._refresh_list(iid); self._upd_labels()
        self.status.set("")
        self._loading = False

    def _free_id(self, base):
        n = 1
        while f"{base}_{n}" in self.items or f"{base}_{n}" in self.weapons: n += 1
        return f"{base}_{n}"

    def new(self):
        if self.cur is not None and not self.commit(quiet=True): return
        nid = self._free_id("accessory")
        self.items[nid] = {"name": "Новый аксессуар", "type": "artifact", "rarity": "common", "description": "", "bonuses": {}}
        self._refresh_list(nid); self.select(nid)
        self.status.set("Создан в памяти — не забудь «Сохранить».")

    def copy(self):
        if self.cur is None or not self.commit(quiet=True): return
        nid = self._free_id(self.cur)
        self.items[nid] = copy.deepcopy(self.items[self.cur]); self.items[nid]["name"] = self.items[nid].get("name", "") + " (копия)"
        self.select(nid)

    def delete(self):
        if self.cur is None: return
        if not messagebox.askyesno("Удалить", f"Удалить аксессуар «{self.cur}»?\n(Изменение запишется при сохранении.)"): return
        ids = self._ids(); i = ids.index(self.cur)
        del self.items[self.cur]
        for lst in (self.data.get("start_items") or {}).values():
            if isinstance(lst, list): lst[:] = [x for x in lst if x != self.cur]
        self.cur = None; ids = self._ids()
        if ids: self.select(ids[min(i, len(ids) - 1)])
        else:
            self._refresh_list()
        self.status.set("Удалён — нажми «Сохранить», чтобы записать в файл.")

    # ---------- форма -> данные ----------
    def commit(self, quiet=False):
        """Перенести форму в self.items[cur]. False — ошибка (сообщение уже показано)."""
        if self.cur is None: return True
        old = self.cur; nid = self.v["id"].get().strip()
        def err(msg): messagebox.showerror("Аксессуар", msg); return False
        if not ID_RE.match(nid): return err("ID: только маленькие латинские буквы, цифры и _.")
        if nid != old and (nid in self.items or nid in self.weapons): return err(f"ID «{nid}» уже занят.")
        bon = {}
        for k, lbl in BONUSES:
            t = self.bv[k].get().strip().replace(",", ".")
            if not t: continue
            try: val = _num(t)
            except ValueError: return err(f"«{lbl}»: нужно число.")
            if val: bon[k] = val
        kind = EFFECT_ID.get(self.v["eff"].get(), "")
        effect = None
        if kind:
            try:
                tt = _num(self.v["eff_t"].get().strip().replace(",", ".") or 0)
                dps = _num(self.v["eff_dps"].get().strip().replace(",", ".") or 0)
            except ValueError: return err("Эффект: секунды и урон/с — числа.")
            if tt <= 0: return err("Эффект: укажи длительность в секундах (> 0).")
            effect = {"burn": {"time": tt, "dps": dps}} if kind == "burn" else {kind: tt}
        it = copy.deepcopy(self.items.get(old, {}))
        it["name"] = self.v["name"].get().strip() or nid
        it["type"] = self.v["type"].get().strip() or "artifact"
        it["rarity"] = self.v["rarity"].get() or "common"
        desc = self.desc.get("1.0", "end").strip()
        for key, val in (("description", desc), ("icon", self.icon.get().strip()), ("skill", self.v["skill"].get().strip()), ("effect", effect)):
            if val: it[key] = val
            else: it.pop(key, None)
        it["bonuses"] = bon
        if nid != old:   # переименование: сохранить позицию в словаре и ссылки в start_items
            pairs = list(self.items.items()); self.items.clear()
            for k, v in pairs: self.items[nid if k == old else k] = it if k == old else v
            for lst in (self.data.get("start_items") or {}).values():
                if isinstance(lst, list): lst[:] = [nid if x == old else x for x in lst]
            self.cur = nid
        else:
            self.items[old] = it
        self._refresh_list(self.cur)
        return True

    def save(self):
        if not self.commit(): return False
        try:
            INV_FILE.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError as e:
            messagebox.showerror("Ошибка сохранения", str(e)); return False
        self.saved = self._dump()
        self.status.set(f"Сохранено в assets/inventory.json. В игре — F5, чтобы перечитать.")
        return True

    def pick_png(self):
        if self.cur is None: return
        p = filedialog.askopenfilename(title="Текстура аксессуара", filetypes=[("PNG", "*.png")], initialdir=str(ICON_DIR))
        if not p: return
        p = Path(p).resolve()
        try: rel = p.relative_to(ASSETS.resolve()).as_posix()
        except ValueError:
            name = (self.v["id"].get().strip() or self.cur) + ".png"; dst = ICON_DIR / name
            if dst.exists() and not messagebox.askyesno("Файл есть", f"assets/icons/{name} уже существует. Заменить?"): return
            try: ICON_DIR.mkdir(parents=True, exist_ok=True); shutil.copyfile(p, dst)
            except OSError as e: messagebox.showerror("Копирование", str(e)); return
            rel = f"icons/{name}"
            self._imgs = {k: v for k, v in self._imgs.items() if k[0] != rel}
            self._fill_icons()
        self.icon.set(rel)

    def confirm_close(self):
        if not hasattr(self, "lb"): return True
        if self.cur is not None and not self.commit(quiet=True): return False
        if not self.dirty(): return True
        ans = messagebox.askyesnocancel("Аксессуары", "Сохранить изменения аксессуаров?")
        if ans is None: return False
        return self.save() if ans else True


class _Tip:
    """Всплывающая подсказка с именем файла над кнопкой иконки."""
    def __init__(self, w, text):
        self.w, self.text, self.tip = w, text, None
        w.bind("<Enter>", self.show, add="+"); w.bind("<Leave>", self.hide, add="+")
    def show(self, _):
        self.tip = tk.Toplevel(self.w); self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{self.w.winfo_rootx() + 20}+{self.w.winfo_rooty() + 52}")
        tk.Label(self.tip, text=self.text, bg="#ffffe0", relief="solid", borderwidth=1).pack()
    def hide(self, _):
        if self.tip: self.tip.destroy(); self.tip = None


if __name__ == "__main__":
    root = tk.Tk(); root.title("DEAD ROOMS — аксессуары"); root.geometry("1200x820")
    tab = AccessoryTab(root); tab.pack(fill="both", expand=True)
    root.protocol("WM_DELETE_WINDOW", lambda: tab.confirm_close() and root.destroy())
    root.mainloop()
