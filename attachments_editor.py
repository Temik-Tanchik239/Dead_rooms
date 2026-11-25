# -*- coding: utf-8 -*-
"""Частицы-эффекты в редакторе игры (map_editor.py) — код игры: effects.py.

Два уровня правки (оба пишут в data/attachments.json сразу; в игре данные подхватываются по F5):
  · AttachmentPanel — компактная панель «Частицы» для одного контекста, встроена в нужные вкладки:
    «Навыки» — событие skill_cast (id = выбранный навык), «Мобы» — mob_hit/mob_attack/mob_death/walk
    (id = выбранный моб), «Ящики» — container_break/container_open (id = выбранный тип ящика);
  · EffectTab — вкладка «Эффекты»: список ВСЕХ привязок (добавление/удаление, любой id, в т.ч. «*» — ко всем).

Привязка: {"hook": событие, "id": id цели или "*", "effect": id эффекта, "count": сколько частиц,
"motion": движение, "angle"?: угол конуса, "spin"?: сила вихря}. События и их цели — см. HOOKS.
Внешний вид самих частиц (цвета, размер, жизнь, скорость, гравитация, glow) — в data/effects.json.
"""
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

# hook -> (русское название, из какого json брать id целей; None — событие относится к самому герою)
HOOKS = [
    ("weapon_hit", "Попадание оружием", "weapons"),
    ("weapon_swing", "Замах оружием", "weapons"),
    ("skill_cast", "Применение навыка", "skills"),
    ("walk", "Шаги", "mobs"),
    ("jump", "Прыжок", None),
    ("land", "Приземление", None),
    ("player_hurt", "Герой получил урон", None),
    ("mob_hit", "Попадание по мобу", "mobs"),
    ("mob_attack", "Моб начал атаку", "mobs"),
    ("mob_death", "Моб умер", "mobs"),
    ("container_break", "Ящик сломан", "containers"),
    ("container_open", "Сундук открыт", "containers"),
    ("projectile_hit", "Пуля исчезла", "projectiles"),
]
HOOK_RU = {h: ru for h, ru, _ in HOOKS}
HOOK_SRC = {h: src for h, _, src in HOOKS}
MOTIONS = ["burst", "spray", "puff", "rise", "fall", "twinkle", "spiral"]
MOTION_RU = {
    "burst": "Разлёт во все стороны",
    "spray": "Конус по направлению",
    "puff": "Ленивая пыль",
    "rise": "Вверх (дым)",
    "fall": "Падение сверху",
    "twinkle": "Мерцание на месте",
    "spiral": "Вихрь вокруг точки",
}


# ---------- данные (без Tk — можно тестировать отдельно) ----------
def _read(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def load_bindings():
    """data/attachments.json -> список привязок (пустой список, если файла нет)."""
    v = _read(DATA / "attachments.json", [])
    return [b for b in v if isinstance(b, dict)] if isinstance(v, list) else []


def save_bindings(bs):
    (DATA / "attachments.json").write_text(json.dumps(bs, ensure_ascii=False, indent=2), encoding="utf-8")


def effect_ids():
    """id эффектов из data/effects.json (без служебных "_"-ключей)."""
    d = _read(DATA / "effects.json", {})
    return [k for k, v in d.items() if isinstance(v, dict)] if isinstance(d, dict) else []


def hook_ids(hook):
    """Какие id имеют смысл как цель для события hook («*» — ко всем — всегда первый)."""
    src = HOOK_SRC.get(hook)
    if not src:
        return ["*"]   # jump/land/player_hurt — только герой
    d = _read(DATA / f"{src}.json", {})
    if isinstance(d, dict) and isinstance(d.get("containers"), dict):
        d = d["containers"]   # containers.json: {"containers": {...}}
    ids = [k for k, v in d.items() if isinstance(v, dict)] if isinstance(d, dict) else []
    return ["*"] + sorted(ids)


def find_binding(bs, hook, cid):
    """Индекс привязки (hook, id) в списке или -1."""
    for i, b in enumerate(bs):
        if b.get("hook") == hook and str(b.get("id", "*")) == str(cid):
            return i
    return -1


def row_label(b):
    """Строка для списка: «Событие · цель · эффект ×сила · движение»."""
    hook = b.get("hook", "?"); cid = b.get("id", "*")
    eff = b.get("effect", "?"); cnt = b.get("count", "?"); mot = b.get("motion", "?")
    extra = []
    if b.get("angle") not in (None, ""): extra.append(f"угол {b['angle']}")
    if b.get("spin") not in (None, ""): extra.append(f"вихрь {b['spin']}")
    return f"{HOOK_RU.get(hook, hook)} · {cid} · {eff} ×{cnt} · {MOTION_RU.get(mot, mot)}" + (" · " + ", ".join(extra) if extra else "")


def parse_int(text, default, lo=1, hi=200):
    try:
        return max(lo, min(hi, int(str(text).strip())))
    except (ValueError, TypeError):
        return default


def parse_float(text):
    text = str(text).strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


# ---------- встроенная панель «Частицы» для одной вкладки ----------
class AttachmentPanel(ttk.Frame):
    """Панель «Частицы» для одного контекста (навык / моб / тип ящика).

    hooks — какие события показывать; get_id — callable -> id контекста ("" или None — контекст не выбран).
    Каждая строка: событие · эффект · частиц · движение · угол · вихрь. Правка сразу пишется в файл.
    """

    def __init__(self, parent, hooks, get_id, title="Частицы", help=None, width=560):
        super().__init__(parent)
        self.hooks = list(hooks)
        self.get_id = get_id
        self.help = help or (lambda s: None)
        lf = ttk.LabelFrame(self, text=title, padding=6); lf.pack(fill="x")
        head = ttk.Frame(lf); head.pack(fill="x")
        for text, w in (("Событие", 16), ("Эффект", 11), ("Частиц", 5), ("Движение", 13), ("Угол°", 4), ("Вихрь", 4)):
            ttk.Label(head, text=text, width=w, anchor="w").pack(side="left", padx=(0, 2))
        self.rows = {}
        effs = effect_ids()
        for hook in self.hooks:
            r = ttk.Frame(lf); r.pack(fill="x", pady=1)
            ttk.Label(r, text=HOOK_RU[hook], width=16, anchor="w").pack(side="left")
            eff = ttk.Combobox(r, width=10, state="readonly", values=[""] + effs); eff.pack(side="left", padx=2)
            cnt = ttk.Spinbox(r, from_=1, to=200, width=5); cnt.pack(side="left", padx=2)
            mot = ttk.Combobox(r, width=13, state="readonly", values=[""] + MOTIONS); mot.pack(side="left", padx=2)
            ang = ttk.Entry(r, width=5); ang.pack(side="left", padx=2)
            spn = ttk.Entry(r, width=5); spn.pack(side="left", padx=2)
            self.rows[hook] = dict(eff=eff, cnt=cnt, mot=mot, ang=ang, spn=spn)
            for w in (eff, mot):
                w.bind("<<ComboboxSelected>>", lambda e, h=hook: self._commit(h))
            for w in (cnt, ang, spn):
                w.bind("<FocusOut>", lambda e, h=hook: self._commit(h))
                w.bind("<Return>", lambda e, h=hook: self._commit(h))
        ttk.Label(lf, text="Пустой эффект — на событие частиц нет. «Угол°» — для конуса (spray), «Вихрь» — для spiral; пусто — как в коде. "
                           "Правка сразу пишется в data/attachments.json — в игре нажми F5.",
                  wraplength=width, foreground="#666").pack(anchor="w", pady=(4, 0))
        self.refresh()

    # ---- виджеты <-> файл ----
    def _get(self, hook):
        return self.rows[hook]

    def refresh(self):
        """Перечитать привязки под текущий id контекста (после смены навыка/моба/типа)."""
        cid = (str(self.get_id() or "")).strip()
        bs = load_bindings()
        for hook, w in self.rows.items():
            b = next((x for x in bs if x.get("hook") == hook and str(x.get("id", "*")) == cid), None) if cid else None
            vals = dict(eff=(b or {}).get("effect", ""), mot=(b or {}).get("motion", ""),
                        cnt=str((b or {}).get("count", 8)), ang="" if not (b or {}).get("angle") else str(b["angle"]),
                        spn="" if not (b or {}).get("spin") else str(b["spin"]))
            for key, wid in w.items():
                wid.configure(state="normal")
                if key in ("eff", "mot"):
                    wid.set(vals[key])
                else:
                    wid.delete(0, "end"); wid.insert(0, vals[key])
                if not cid:
                    wid.configure(state="disabled")

    def _commit(self, hook):
        """Правка строки -> data/attachments.json (создать/обновить/убрать привязку)."""
        cid = (str(self.get_id() or "")).strip()
        w = self._get(hook)
        if not cid:
            return
        bs = load_bindings()
        i = find_binding(bs, hook, cid)
        eff = w["eff"].get().strip()
        if not eff:   # эффект пуст — привязка не нужна
            if i >= 0:
                del bs[i]; save_bindings(bs); self.help("Частицы события убраны (data/attachments.json; в игре F5).")
            return
        row = dict(bs[i]) if i >= 0 else {}
        row.update({"hook": hook, "id": cid, "effect": eff,
                    "count": parse_int(w["cnt"].get(), 8), "motion": w["mot"].get().strip() or "burst"})
        ang, spn = parse_float(w["ang"].get()), parse_float(w["spn"].get())
        for key, v in (("angle", ang), ("spin", spn)):
            if v is None: row.pop(key, None)
            else: row[key] = v
        if i >= 0:
            bs[i] = row
        else:
            bs.append(row)
        save_bindings(bs)
        self.help("Частицы записаны в data/attachments.json — в игре нажми F5 (или перезапусти забег).")


# ---------- вкладка «Эффекты»: все привязки ----------
class EffectTab(ttk.Frame):
    """Полный редактор привязок: список из data/attachments.json + форма (событие, цель, эффект, сила, движение)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.sel = None   # индекс выбранной привязки
        self._busy = False
        top = ttk.Frame(self); top.pack(fill="x", pady=(8, 4))
        ttk.Label(top, text="Частицы-эффекты: что и где появляется (data/attachments.json). "
                            "Вид самих частиц — data/effects.json. В игре данные перечитываются по F5.",
                  foreground="#444", wraplength=900).pack(anchor="w")
        body = ttk.Frame(self); body.pack(fill="both", expand=True)
        # слева — список привязок
        left = ttk.LabelFrame(body, text="Привязки (клик — править)", padding=4); left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        sb = ttk.Scrollbar(left, orient="vertical"); sb.pack(side="right", fill="y")
        self.lb = tk.Listbox(left, width=64, exportselection=False, activestyle="none", yscrollcommand=sb.set)
        self.lb.pack(side="left", fill="both", expand=True); sb.configure(command=self.lb.yview)
        self.lb.bind("<<ListboxSelect>>", self._on_lb)
        brow = ttk.Frame(left); brow.pack(fill="x", pady=(4, 0))
        ttk.Button(brow, text="Добавить", command=self.add).pack(side="left")
        ttk.Button(brow, text="Удалить выбранный", command=self.delete).pack(side="left", padx=6)
        # справа — форма
        form = ttk.LabelFrame(body, text="Привязка", padding=6); form.pack(side="left", fill="y")
        self.f_hook = tk.StringVar(); self.f_id = tk.StringVar(value="*")
        self.f_eff = tk.StringVar(); self.f_cnt = tk.StringVar(value="8")
        self.f_mot = tk.StringVar(value="burst"); self.f_ang = tk.StringVar(); self.f_spn = tk.StringVar()
        def row(label, widget):
            r = ttk.Frame(form); r.pack(fill="x", pady=2)
            ttk.Label(r, text=label, width=11).pack(side="left"); widget.pack(side="left", fill="x", expand=True)
            return widget
        self.hook_cb = row("Событие:", ttk.Combobox(form, textvariable=self.f_hook, state="readonly", width=26, values=[ru for h, ru, _ in HOOKS]))
        self.hook_cb.bind("<<ComboboxSelected>>", self._hook_changed)
        row("Цель (id):", ttk.Combobox(form, textvariable=self.f_id, width=26, values=["*"]))
        row("Эффект:", ttk.Combobox(form, textvariable=self.f_eff, state="readonly", width=26, values=effect_ids()))
        r = ttk.Frame(form); r.pack(fill="x", pady=2)
        ttk.Label(r, text="Сила:", width=11).pack(side="left")
        ttk.Spinbox(r, from_=1, to=200, width=6, textvariable=self.f_cnt).pack(side="left")
        ttk.Label(r, text="  Движение:").pack(side="left")
        ttk.Combobox(r, textvariable=self.f_mot, state="readonly", width=14, values=MOTIONS).pack(side="left")
        r2 = ttk.Frame(form); r2.pack(fill="x", pady=2)
        ttk.Label(r2, text="Угол°:", width=11).pack(side="left")
        ttk.Entry(r2, width=6, textvariable=self.f_ang).pack(side="left")
        ttk.Label(r2, text="  Вихрь:").pack(side="left")
        ttk.Entry(r2, width=6, textvariable=self.f_spn).pack(side="left")
        for var in (self.f_id, self.f_cnt, self.f_ang, self.f_spn):
            var.trace_add("write", self._form_changed)
        for var in (self.f_eff, self.f_mot):
            var.trace_add("write", self._form_changed)
        ttk.Label(form, text="Цель: id оружия/навыка/моба/ящика/пули — или «*» (ко всем событиям этого типа). "
                             "Угол — для конуса (spray), вихрь — для spiral; пусто — значения из кода.",
                  wraplength=340, foreground="#666").pack(anchor="w", pady=(8, 0))
        self.status = tk.StringVar()
        ttk.Label(self, textvariable=self.status, foreground="#2a6", wraplength=960).pack(anchor="w", fill="x", pady=(4, 0))
        self.reload()

    # ---- helpers ----
    def _key(self):
        """(hook, ru) выбранного события."""
        ru = self.f_hook.get()
        return next(((h, r) for h, r, _ in HOOKS if r == ru), (HOOKS[0][0], HOOKS[0][1]))

    def _binding_from_form(self):
        """Форма -> привязка (или None, если не заполнено)."""
        h, _ = self._key(); cid = self.f_id.get().strip() or "*"; eff = self.f_eff.get().strip()
        if not eff:
            return None
        row = {"hook": h, "id": cid, "effect": eff, "count": parse_int(self.f_cnt.get(), 8), "motion": self.f_mot.get().strip() or "burst"}
        ang, spn = parse_float(self.f_ang.get()), parse_float(self.f_spn.get())
        if ang is not None: row["angle"] = ang
        if spn is not None: row["spin"] = spn
        return row

    def _form_to_widgets(self, b):
        self._busy = True
        try:
            self.f_hook.set(HOOK_RU.get(b.get("hook"), b.get("hook", "")))
            self.f_id.set(str(b.get("id", "*")))
            self.f_eff.set(b.get("effect", ""))
            self.f_cnt.set(str(b.get("count", 8)))
            self.f_mot.set(b.get("motion", "burst"))
            self.f_ang.set("" if b.get("angle") in (None, "") else str(b["angle"]))
            self.f_spn.set("" if b.get("spin") in (None, "") else str(b["spin"]))
        finally:
            self._busy = False

    def _write_selected(self):
        """Правка формы -> выбранная привязка в файле (сразу)."""
        if self._busy or self.sel is None:
            return
        row = self._binding_from_form()
        if row is None:
            return
        bs = load_bindings()
        if 0 <= self.sel < len(bs):
            bs[self.sel] = row; save_bindings(bs); self._refresh_lb()
            self.status.set("Записано в data/attachments.json — в игре нажми F5.")

    # ---- события ----
    def reload(self):
        self.sel = None; self._refresh_lb()
        if self.f_hook.get() == "":
            self._hook_changed(set_values=True)
        self.status.set("")

    def _refresh_lb(self):
        bs = load_bindings()
        self.lb.delete(0, "end")
        for b in bs:
            self.lb.insert("end", row_label(b))
        if self.sel is not None and not 0 <= self.sel < len(bs):
            self.sel = None

    def _on_lb(self, _e=None):
        sel = self.lb.curselection()
        if not sel:
            return
        self.sel = sel[0]
        bs = load_bindings()
        if 0 <= self.sel < len(bs):
            self._form_to_widgets(bs[self.sel])

    def _hook_changed(self, _e=None, set_values=False):
        """Сменилось событие — подставить подходящие цели."""
        h, ru = self._key()
        ids = hook_ids(h)
        if set_values or self.f_id.get() not in ids:
            self.f_id.set(ids[0] if ids else "*")
        if set_values:
            self.f_hook.set(HOOK_RU[h])

    def add(self):
        """Добавить привязку из формы (если там есть эффект)."""
        row = self._binding_from_form()
        if row is None:
            self.status.set("Выбери эффект — и нажми «Добавить» ещё раз."); return
        bs = load_bindings()
        i = find_binding(bs, row["hook"], row["id"])
        if i >= 0:
            bs[i] = row; self.status.set("Такая пара «событие+цель» уже была — привязка заменена.")
        else:
            bs.append(row); self.status.set("Привязка добавлена в data/attachments.json — в игре нажми F5.")
        save_bindings(bs)
        self.sel = len(bs) - 1 if i < 0 else i
        self._refresh_lb()
        self.lb.selection_clear(0, "end"); self.lb.selection_set(self.sel); self.lb.see(self.sel)

    def delete(self):
        if self.sel is None:
            self.status.set("Выбери привязку в списке слева."); return
        bs = load_bindings()
        if 0 <= self.sel < len(bs):
            gone = bs.pop(self.sel); save_bindings(bs)
            self.status.set(f"Привязка «{row_label(gone)}» удалена.")
            self.sel = None; self._refresh_lb()

    def _form_changed(self, *_a):
        if not self._busy:
            self._write_selected()
