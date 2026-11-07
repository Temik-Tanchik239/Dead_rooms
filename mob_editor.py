"""Вкладка «Мобы» редактора (map_editor.py): настройка мобов из data/mobs.json без ручной правки JSON.

Слева — список мобов. В центре — вкладки: «Основное» (характеристики, поведение, свет), «Текстура и хитбокс», «Движение»,
«Атаки» (у каждой атаки свои параметры, свои тайминги и свои анимации фаз), «Анимации» (кадры PNG для любого состояния),
«JSON» (любое поле, которого нет в формах). Справа — окно с мобом: выбери любую анимацию (покой, ходьба, фазы любой атаки,
атака целиком, свои анимации) и смотри, как она выглядит в игре; поверх можно включить хитбокс, рамку картинки и зону атаки.

Логика данных — mob_data.py, рисование окна — mob_preview.py (нужен pygame; без него вкладка работает, но без окна просмотра).
Сохранение пишет data/mobs.json; в запущенной игре нажми F5, чтобы подхватить изменения.
"""
import copy, json, os, subprocess, sys, time
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox, colorchooser, simpledialog

import mob_data as md
try:
    from mob_preview import Preview
except Exception as _e:      # нет pygame — вкладка всё равно работает, просто без окна просмотра
    Preview = None; PREVIEW_ERROR = str(_e)

DEF_TEXT = "по умолчанию"
GRAY = "#7a7a85"
TYPE_RU = {k: v[0] for k, v in md.ATTACK_TYPES.items()}
MOVE_RU = {k: v[0] for k, v in md.MOVES.items()}
ANIM_ROWS = md.STD_STATES + [("windup", "Замах (общий для всех атак)"), ("attack", "Удар (общий для всех атак)"),
                             ("recovery", "Отдых (общий для всех атак)")]
TEX_FIELDS = [
    md.F("skin", "Картинка (путь в assets)", "text", "", "Файл PNG моба. Лучше положить его в assets/mobs/<id>/."),
    md.F("w", "Хитбокс: ширина, px", "int", "", "Физический размер моба (зелёная рамка в окне справа)."),
    md.F("h", "Хитбокс: высота, px", "int", "", "Физический размер моба (зелёная рамка в окне справа)."),
    md.F("draw", "Размер картинки [ширина, высота]", "vec2", "= хитбокс", "Во сколько пикселей растягивается PNG (синяя рамка). Низ картинки совпадает с низом хитбокса."),
    md.F("color", "Цвет-заглушка", "rgb", "", "Если картинки нет, моб рисуется прямоугольником этого цвета."),
]
ANIM_FIELDS = [
    md.F("fps", "Кадров в секунду", "num", "по анимации", "Пусто: у атак кадры растягиваются на длительность фазы, у остального — «Скорость по умолчанию»."),
    md.F("loop", "Зацикливать", "bool", "зависит от состояния", "Покой, ходьба, прыжок — зациклены; замах, удар, отдых, урон — нет."),
]
ANIM_DEFAULT_FIELDS = [md.F("anim_fps", "Скорость анимаций по умолчанию, к/с", "num", "10", "Для анимаций без своего fps (кроме фаз атак).")]


def hex_of(rgb): return "#%02x%02x%02x" % tuple(max(0, min(255, int(c))) for c in rgb[:3])


# ================================================================ вспомогательные виджеты
class ScrollFrame(ttk.Frame):
    """Фрейм с вертикальной прокруткой (колесо мыши работает, пока курсор над ним). Содержимое — .inner."""
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview); self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y"); self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = ttk.Frame(self.canvas); self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        for w in (self.canvas, self.inner):
            w.bind("<Enter>", self._on_enter); w.bind("<Leave>", self._on_leave)
    def _on_enter(self, _):
        self.canvas.bind_all("<MouseWheel>", self._wheel); self.canvas.bind_all("<Button-4>", self._wheel); self.canvas.bind_all("<Button-5>", self._wheel)
    def _on_leave(self, _):
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"): self.canvas.unbind_all(ev)
    def _wheel(self, e):
        step = -1 if (e.num == 4 or getattr(e, "delta", 0) > 0) else 1
        self.canvas.yview_scroll(step * 2, "units")


class Form(ttk.Frame):
    """Столбик полей по списку md.F: название | поле ввода | серая подсказка «по умолч.».
    getter() отдаёт редактируемый словарь, on_change(key) вызывается после каждой правки. Пустое поле = ключ удаляется
    (в игре действует значение по умолчанию). Неверное число подсвечивается красным и не записывается."""
    def __init__(self, parent, fields, getter, on_change, help_cb=None, defaults=None, refs=None):
        super().__init__(parent)
        self.fields, self.getter, self.on_change, self.help_cb = fields, getter, on_change, help_cb
        self.defaults, self.refs = defaults or {}, refs
        self.w = {}; self._loading = False
        self.columnconfigure(2, weight=1)
        for r, f in enumerate(fields): self._row(r, f)

    # ---------- построение
    def _row(self, r, f):
        ttk.Label(self, text=f.label).grid(row=r, column=0, sticky="w", padx=(0, 8), pady=1)
        box = ttk.Frame(self); box.grid(row=r, column=1, sticky="w", pady=1)
        hint = self.defaults.get(f.key, f.hint)
        ttk.Label(self, text=f"по умолч.: {hint}" if hint else "", foreground=GRAY).grid(row=r, column=2, sticky="w", padx=8)
        k, reg, widgets = f.kind, {}, []
        trace = lambda *_a, f=f: self._commit(f)
        if k in ("num", "int", "text"):
            var = tk.StringVar(); var.trace_add("write", trace)
            e = (ttk.Spinbox(box, from_=-99999, to=99999, increment=1, textvariable=var, width=9) if k == "int"
                 else ttk.Entry(box, textvariable=var, width=26 if k == "text" else 11))
            e.pack(); reg = {"var": var}; widgets = [e]
        elif k == "bool":
            cb = ttk.Combobox(box, values=[DEF_TEXT, "да", "нет"], state="readonly", width=14); cb.pack(); reg = {"cb": cb}; widgets = [cb]
        elif k in ("choice", "ref", "proj"):
            cb = ttk.Combobox(box, values=[DEF_TEXT, *f.choices], state="readonly", width=18); cb.pack(); reg = {"cb": cb}; widgets = [cb]
        elif k == "vec2":
            va, vb = tk.StringVar(), tk.StringVar(); va.trace_add("write", trace); vb.trace_add("write", trace)
            ea, eb = ttk.Entry(box, textvariable=va, width=7), ttk.Entry(box, textvariable=vb, width=7)
            ea.pack(side="left"); ttk.Label(box, text=" × ").pack(side="left"); eb.pack(side="left"); reg = {"va": va, "vb": vb}; widgets = [ea, eb]
        elif k == "rgb":
            btn = tk.Button(box, width=6, relief="groove", command=lambda f=f: self._pick(f)); btn.pack(side="left")
            ttk.Button(box, text="×", width=2, command=lambda f=f: self._set_rgb(f, None)).pack(side="left", padx=2)
            reg = {"btn": btn, "rgb": None}; widgets = [btn]
        elif k == "points":
            t = tk.Text(box, width=22, height=3, font=("Consolas", 9)); t.pack(); t.bind("<KeyRelease>", trace); t.bind("<FocusOut>", trace); reg = {"text": t}; widgets = [t]
        if "cb" in reg: reg["cb"].bind("<<ComboboxSelected>>", trace)
        for w in widgets:
            if f.help: w.bind("<Enter>", lambda e, h=f.help: self.help_cb and self.help_cb(h)); w.bind("<FocusIn>", lambda e, h=f.help: self.help_cb and self.help_cb(h))
        reg["widgets"] = widgets; self.w[f.key] = reg

    # ---------- чтение / запись значений
    def _read(self, f):
        r, k = self.w[f.key], f.kind
        if k in ("num", "int"): return md.parse_num(r["var"].get(), k == "int")
        if k == "text": return True, r["var"].get().strip() or None
        if k == "bool": return True, {DEF_TEXT: None, "да": True, "нет": False}.get(r["cb"].get())
        if k in ("choice", "ref", "proj"):
            s = r["cb"].get(); return True, None if s in ("", DEF_TEXT) else s
        if k == "vec2":
            oka, a = md.parse_num(r["va"].get()); okb, b = md.parse_num(r["vb"].get())
            if oka and okb and a is None and b is None: return True, None
            return (True, [a, b]) if oka and okb and a is not None and b is not None else (False, None)
        if k == "rgb": return True, r["rgb"]
        if k == "points":
            v = md.parse_points(r["text"].get("1.0", "end")); return (v is not False), (v or None)
        return True, None

    def _mark(self, f, ok):
        for w in self.w[f.key]["widgets"]:
            try: w.configure(foreground="" if ok else "#d32f2f") if isinstance(w, (ttk.Entry, ttk.Spinbox)) else None
            except tk.TclError: pass

    def _commit(self, f, *_):
        if self._loading: return
        d = self.getter()
        if d is None: return
        ok, val = self._read(f); self._mark(f, ok)
        if ok:
            md.set_path(d, f.key, val); self.on_change(f.key)

    def _write(self, f, v):
        r, k = self.w[f.key], f.kind
        if k in ("num", "int", "text"): r["var"].set("" if v is None else md.fmt_num(v) if k != "text" else str(v))
        elif k == "bool": r["cb"].set(DEF_TEXT if v is None else "да" if v else "нет")
        elif k in ("choice", "ref", "proj"):
            vals = list(r["cb"].cget("values"))
            if v is not None and v not in vals: r["cb"].configure(values=vals + [v])
            r["cb"].set(DEF_TEXT if v is None else v)
        elif k == "vec2":
            ok = isinstance(v, (list, tuple)) and len(v) == 2
            r["va"].set(md.fmt_num(v[0]) if ok else ""); r["vb"].set(md.fmt_num(v[1]) if ok else "")
        elif k == "rgb": self._set_rgb(f, v if isinstance(v, (list, tuple)) and len(v) >= 3 else None, commit=False)
        elif k == "points": r["text"].delete("1.0", "end"); r["text"].insert("1.0", md.points_text(v))

    def _pick(self, f):
        cur = self.w[f.key]["rgb"] or [200, 200, 200]
        c = colorchooser.askcolor(color=hex_of(cur), title=f.label)
        if c and c[0]: self._set_rgb(f, [int(x) for x in c[0]])

    def _set_rgb(self, f, rgb, commit=True):
        r = self.w[f.key]; r["rgb"] = rgb
        r["btn"].configure(background=hex_of(rgb) if rgb else self.winfo_toplevel().cget("background"), text="" if rgb else "нет")
        if commit: self._commit(f)

    def load(self):
        """Заполнить поля из getter(); ссылочные списки (id атак, снаряды) подтягиваются заново."""
        d = self.getter() or {}
        self._loading = True
        try:
            for f in self.fields:
                if f.kind in ("ref", "proj") and self.refs:
                    self.w[f.key]["cb"].configure(values=[DEF_TEXT, *self.refs(f.kind)])
                self._write(f, md.get_path(d, f.key)); self._mark(f, True)
        finally: self._loading = False


# ================================================================ вкладка «Мобы»
class MobTab(ttk.Frame):
    PV_SIZE = (344, 300)

    def __init__(self, parent, data_dir=None, assets_dir=None):
        super().__init__(parent)
        self.data_dir = Path(data_dir or md.DATA_DIR); self.assets = Path(assets_dir or md.ASSETS_DIR)
        self.mobs_path = self.data_dir / "mobs.json"
        self.mobs, self.saved_text, self.cur, self.atk_i = {}, "", None, None
        self.projectiles = md.load_projectiles(self.data_dir)
        self.pv = Preview(self.assets, self.PV_SIZE) if Preview else None
        self.help, self.status = tk.StringVar(), tk.StringVar()
        self._entries, self._entry, self._photo = [], None, None
        self._paused, self._t0, self._t_acc, self._speed = False, time.monotonic(), 0.0, 1.0
        self._loading = False; self._an_sel = None; self._an_spec = {}; self._skin_size = {}
        self._build(); self.reload(first=True); self._tick()

    @property
    def mob(self): return self.mobs.get(self.cur)

    @property
    def dirty(self): return md.dump_mobs(self.mobs) != self.saved_text

    # ---------------------------------------------------------------- построение интерфейса
    def _build(self):
        bar = ttk.Frame(self); bar.pack(side="bottom", fill="x", pady=(6, 0))
        ttk.Button(bar, text="Сохранить в data/mobs.json", command=self.save).pack(side="left")
        ttk.Button(bar, text="Отменить все изменения", command=self.revert).pack(side="left", padx=6)
        ttk.Label(bar, textvariable=self.status).pack(side="left", padx=10)
        ttk.Label(self, textvariable=self.help, foreground=GRAY, wraplength=1100).pack(side="bottom", fill="x", pady=(4, 0))
        paned = ttk.PanedWindow(self, orient="horizontal"); paned.pack(fill="both", expand=True)
        left, center, right = ttk.Frame(paned), ttk.Frame(paned), ttk.Frame(paned)
        paned.add(left, weight=0); paned.add(center, weight=1); paned.add(right, weight=0)
        self._build_list(left)
        self.nb = ttk.Notebook(center); self.nb.pack(fill="both", expand=True, padx=6)
        self.nb.bind("<<NotebookTabChanged>>", self._tab_changed)
        self._build_main(); self._build_tex(); self._build_move(); self._build_attacks(); self._build_anims(); self._build_json()
        self._build_preview(right)

    def _form(self, parent, fields, getter, on_change=None, **kw):
        return Form(parent, fields, getter, on_change or (lambda k: self.touch()), self.help.set, **kw)

    def _build_list(self, parent):
        box = ttk.LabelFrame(parent, text="Мобы", padding=4); box.pack(fill="both", expand=True)
        row = ttk.Frame(box); row.pack(side="bottom", fill="x", pady=(4, 0))
        for text, cmd in (("Новый…", self.new_mob), ("Копия…", self.copy_mob), ("Удалить", self.delete_mob)):
            ttk.Button(row, text=text, command=cmd, width=7).pack(side="left", padx=1)
        sb = ttk.Scrollbar(box, orient="vertical"); sb.pack(side="right", fill="y")
        self.lb = tk.Listbox(box, width=21, exportselection=False, activestyle="none", yscrollcommand=sb.set); sb.configure(command=self.lb.yview)
        self.lb.pack(side="left", fill="both", expand=True); self.lb.bind("<<ListboxSelect>>", lambda e: self._on_list())

    def _tab(self, title):
        f = ttk.Frame(self.nb, padding=10); self.nb.add(f, text=title); return f

    def _build_main(self):
        tab = self._tab("Основное"); self.main_forms = []
        sc = ScrollFrame(tab); sc.pack(fill="both", expand=True)
        for title, fields in md.STAT_GROUPS:
            lf = ttk.LabelFrame(sc.inner, text=title, padding=8); lf.pack(fill="x", pady=(0, 8), padx=(0, 6))
            form = self._form(lf, fields, lambda: self.mob); form.pack(fill="x"); self.main_forms.append(form)

    def _build_tex(self):
        tab = self._tab("Текстура и хитбокс")
        lf = ttk.LabelFrame(tab, text="Картинка и размеры", padding=8); lf.pack(fill="x")
        self.f_tex = self._form(lf, TEX_FIELDS, lambda: self.mob); self.f_tex.pack(fill="x")
        row = ttk.Frame(lf); row.pack(fill="x", pady=(8, 0))
        for text, cmd in (("Выбрать PNG…", self._pick_skin), ("Убрать картинку", self._clear_skin),
                          ("Размер = размеру PNG", self._draw_from_png), ("Хитбокс = 70%", self._hitbox_from_draw)):
            ttk.Button(row, text=text, command=cmd).pack(side="left", padx=(0, 6))
        self.skin_info = tk.StringVar(); ttk.Label(lf, textvariable=self.skin_info, foreground=GRAY).pack(anchor="w", pady=(6, 0))
        ttk.Label(tab, text="Выбранный PNG копируется в assets/mobs/<id>/ (если он лежит вне assets). В окне справа зелёная рамка — хитбокс, "
                            "синяя — размер картинки (включается галочкой). Низ картинки всегда совпадает с низом хитбокса; у летающих "
                            "мобов картинка центрируется по хитбоксу.", wraplength=620, foreground=GRAY).pack(anchor="w", pady=(10, 0))

    def _build_move(self):
        tab = self._tab("Движение")
        row = ttk.Frame(tab); row.pack(fill="x")
        ttk.Label(row, text="Вид движения:").pack(side="left")
        self.move_cb = ttk.Combobox(row, values=list(MOVE_RU.values()), state="readonly", width=24); self.move_cb.pack(side="left", padx=6)
        self.move_cb.bind("<<ComboboxSelected>>", self._move_type_changed)
        self.move_desc = tk.StringVar(); ttk.Label(tab, textvariable=self.move_desc, wraplength=640, foreground=GRAY).pack(anchor="w", pady=(6, 8))
        self.move_box = ttk.LabelFrame(tab, text="Параметры", padding=8); self.move_box.pack(fill="x")
        self.f_move = None

    def _build_attacks(self):
        tab = self._tab("Атаки")
        top = ttk.Frame(tab); top.pack(fill="x")
        ttk.Label(top, text="Атаки моба: он берёт первую готовую, до которой хватает расстояния. У каждой атаки свои настройки и анимации.",
                  foreground=GRAY, wraplength=620).pack(anchor="w")
        row = ttk.Frame(top); row.pack(fill="x", pady=4)
        self.atk_lb = tk.Listbox(row, height=5, exportselection=False, activestyle="none"); self.atk_lb.pack(side="left", fill="x", expand=True)
        self.atk_lb.bind("<<ListboxSelect>>", lambda e: self._atk_pick())
        col = ttk.Frame(row); col.pack(side="left", padx=(6, 0))
        mb = ttk.Menubutton(col, text="Добавить ▾", width=10); menu = tk.Menu(mb, tearoff=0); mb["menu"] = menu
        for k, name in TYPE_RU.items(): menu.add_command(label=name, command=lambda k=k: self._atk_add(k))
        mb.grid(row=0, column=0, columnspan=2, sticky="ew", pady=1)
        for n, (text, cmd) in enumerate((("Копия", self._atk_dup), ("Удалить", self._atk_delete), ("▲ Выше", lambda: self._atk_move(-1)), ("▼ Ниже", lambda: self._atk_move(1)))):
            ttk.Button(col, text=text, command=cmd, width=7).grid(row=1 + n // 2, column=n % 2, pady=1, padx=1)
        self.atk_scroll = ScrollFrame(tab); self.atk_scroll.pack(fill="both", expand=True, pady=(4, 0))
        inner = self.atk_scroll.inner
        head = ttk.Frame(inner); head.pack(fill="x", pady=(0, 4))
        ttk.Label(head, text="Вид атаки:").pack(side="left")
        self.atk_type_cb = ttk.Combobox(head, values=list(TYPE_RU.values()), state="readonly", width=22); self.atk_type_cb.pack(side="left", padx=6)
        self.atk_type_cb.bind("<<ComboboxSelected>>", self._atk_type_changed)
        self.atk_desc = tk.StringVar(); ttk.Label(inner, textvariable=self.atk_desc, wraplength=600, foreground=GRAY).pack(anchor="w")
        self.atk_common_box = ttk.LabelFrame(inner, text="Тайминги и условия", padding=8); self.atk_common_box.pack(fill="x", pady=(6, 6), padx=(0, 6))
        self.atk_type_box = ttk.LabelFrame(inner, text="Параметры вида атаки", padding=8); self.atk_type_box.pack(fill="x", pady=(0, 6), padx=(0, 6))
        self.atk_anim_box = ttk.LabelFrame(inner, text="Анимации этой атаки (если не заданы — общие для моба)", padding=8); self.atk_anim_box.pack(fill="x", pady=(0, 6), padx=(0, 6))
        self.f_atk_common = self._form(self.atk_common_box, md.ATTACK_COMMON, self._atk_cur,
                                       lambda k: self.touch(structural=k in ("id", "next")), refs=self._refs, defaults={})
        self.f_atk_common.pack(fill="x"); self.f_atk_type = None
        self.atk_anim_cb = {}
        for r, ph in enumerate(md.PHASES):
            ttk.Label(self.atk_anim_box, text=f"{md.PHASE_RU[ph].capitalize()}:").grid(row=r, column=0, sticky="w", pady=2)
            cb = ttk.Combobox(self.atk_anim_box, width=28); cb.grid(row=r, column=1, padx=6, pady=2); self.atk_anim_cb[ph] = cb
            cb.bind("<<ComboboxSelected>>", lambda e, ph=ph: self._atk_anim_set(ph)); cb.bind("<Return>", lambda e, ph=ph: self._atk_anim_set(ph))
            cb.bind("<FocusOut>", lambda e, ph=ph: self._atk_anim_set(ph))
            ttk.Button(self.atk_anim_box, text="Создать…", width=10, command=lambda ph=ph: self._atk_anim_create(ph)).grid(row=r, column=2, pady=2)
        ttk.Label(self.atk_anim_box, text="Имя анимации — папка с кадрами assets/mobs/<id>/<имя>/ (кадры добавляются на вкладке «Анимации»).",
                  wraplength=560, foreground=GRAY).grid(row=3, column=0, columnspan=3, sticky="w", pady=(4, 0))

    def _build_anims(self):
        tab = self._tab("Анимации")
        row = ttk.Frame(tab); row.pack(fill="x")
        self.an_lb = tk.Listbox(row, height=7, exportselection=False, activestyle="none"); self.an_lb.pack(side="left", fill="x", expand=True)
        self.an_lb.bind("<<ListboxSelect>>", lambda e: self._an_pick())
        col = ttk.Frame(row); col.pack(side="left", padx=(6, 0))
        ttk.Button(col, text="Новая анимация…", command=self._an_new).pack(fill="x", pady=1)
        ttk.Button(col, text="Убрать запись", command=self._an_delete).pack(fill="x", pady=1)
        sc = ScrollFrame(tab); sc.pack(fill="both", expand=True, pady=(6, 0)); right = sc.inner
        self.an_title = tk.StringVar(); ttk.Label(right, textvariable=self.an_title, font=("Arial", 11, "bold")).pack(anchor="w")
        self.an_source = tk.StringVar(); ttk.Label(right, textvariable=self.an_source, foreground=GRAY, wraplength=600).pack(anchor="w", pady=(2, 6))
        srow = ttk.Frame(right); srow.pack(fill="x")
        ttk.Button(srow, text="Другая папка кадров…", command=self._an_pick_folder).pack(side="left")
        ttk.Button(srow, text="Папка по умолчанию", command=self._an_reset_folder).pack(side="left", padx=6)
        ttk.Button(srow, text="Открыть папку", command=self._an_open_folder).pack(side="left")
        self.f_anim = self._form(right, ANIM_FIELDS, lambda: self._an_spec, self._an_spec_changed); self.f_anim.pack(fill="x", pady=(8, 4))
        frm = ttk.LabelFrame(right, text="Кадры (по порядку)", padding=6); frm.pack(fill="x", pady=(4, 0), padx=(0, 6))
        self.fr_lb = tk.Listbox(frm, height=7, exportselection=False, activestyle="none"); self.fr_lb.pack(side="left", fill="x", expand=True)
        self.fr_lb.bind("<<ListboxSelect>>", lambda e: self._fr_pick())
        col = ttk.Frame(frm); col.pack(side="left", padx=(6, 0))
        for text, cmd in (("Добавить PNG…", self._fr_add), ("Удалить кадр", self._fr_remove), ("▲ Раньше", lambda: self._fr_move(-1)), ("▼ Позже", lambda: self._fr_move(1))):
            ttk.Button(col, text=text, command=cmd, width=14).pack(pady=2)
        self.f_anim_def = self._form(right, ANIM_DEFAULT_FIELDS, lambda: self.mob); self.f_anim_def.pack(fill="x", pady=(8, 0))
        self.an_note = tk.StringVar(); ttk.Label(right, textvariable=self.an_note, foreground="#b26a00", wraplength=600).pack(anchor="w", pady=(4, 0))

    def _build_json(self):
        tab = self._tab("JSON")
        ttk.Label(tab, text="Весь моб как JSON — для полей, которых нет в формах (boss, requires и т. п.). «Применить» заменяет настройки "
                            "выбранного моба тем, что написано здесь.", wraplength=640, foreground=GRAY).pack(anchor="w")
        row = ttk.Frame(tab); row.pack(fill="x", pady=6)
        ttk.Button(row, text="Применить", command=self._json_apply).pack(side="left")
        ttk.Button(row, text="Обновить из редактора", command=self._json_refresh).pack(side="left", padx=6)
        self.json_note = tk.StringVar(); ttk.Label(row, textvariable=self.json_note, foreground="#d32f2f").pack(side="left", padx=8)
        box = ttk.Frame(tab); box.pack(fill="both", expand=True)
        sb = ttk.Scrollbar(box, orient="vertical"); sb.pack(side="right", fill="y")
        self.json_text = tk.Text(box, font=("Consolas", 10), wrap="none", undo=True, yscrollcommand=sb.set); sb.configure(command=self.json_text.yview)
        self.json_text.pack(side="left", fill="both", expand=True)

    def _build_preview(self, parent):
        box = ttk.LabelFrame(parent, text="Окно моба", padding=6); box.pack(fill="both", expand=True, padx=(0, 4))
        if not self.pv:
            ttk.Label(box, text="Окно просмотра недоступно:\nне найден pygame.\n\nУстанови его:\npip install pygame-ce\n\nОстальные вкладки работают.", justify="left").pack(padx=10, pady=20)
            self.pv_combo = None; return
        self.pv_combo = ttk.Combobox(box, state="readonly", width=44); self.pv_combo.pack(fill="x")
        self.pv_combo.bind("<<ComboboxSelected>>", lambda e: self._pv_chosen())
        W, H = self.PV_SIZE; self.pv_canvas = tk.Canvas(box, width=W, height=H, highlightthickness=1, highlightbackground="#444", bg="#1c1c26")
        self.pv_canvas.pack(pady=6); self._pv_img = self.pv_canvas.create_image(0, 0, anchor="nw")
        r1 = ttk.Frame(box); r1.pack(fill="x")
        self.pv_play = ttk.Button(r1, text="Пауза", width=9, command=self._pv_toggle); self.pv_play.pack(side="left")
        ttk.Button(r1, text="< кадр", width=7, command=lambda: self._pv_step(-1)).pack(side="left", padx=2)
        ttk.Button(r1, text="кадр >", width=7, command=lambda: self._pv_step(1)).pack(side="left", padx=2)
        ttk.Button(r1, text="Сначала", width=8, command=self._pv_restart).pack(side="left", padx=2)
        r2 = ttk.Frame(box); r2.pack(fill="x", pady=(4, 0))
        ttk.Label(r2, text="Скорость").pack(side="left")
        self.pv_speed = ttk.Combobox(r2, values=["0.25×", "0.5×", "1×", "2×"], state="readonly", width=6); self.pv_speed.set("1×"); self.pv_speed.pack(side="left", padx=(4, 10))
        self.pv_speed.bind("<<ComboboxSelected>>", self._pv_speed_changed)
        ttk.Label(r2, text="Масштаб").pack(side="left")
        self.pv_zoom = ttk.Combobox(r2, values=["1×", "2×", "3×", "4×"], state="readonly", width=5); self.pv_zoom.set("2×"); self.pv_zoom.pack(side="left", padx=4)
        self.pv_opt = {k: tk.BooleanVar(value=v) for k, v in (("hitbox", True), ("box", False), ("zone", True), ("player", True), ("flip", False))}
        r3 = ttk.Frame(box); r3.pack(fill="x", pady=(6, 0))
        for i, (k, text) in enumerate((("hitbox", "Хитбокс"), ("box", "Рамка картинки"), ("zone", "Зона атаки"), ("player", "Игрок (масштаб)"), ("flip", "Отразить"))):
            ttk.Checkbutton(r3, text=text, variable=self.pv_opt[k]).grid(row=i // 2, column=i % 2, sticky="w", padx=4)
        self.pv_info = tk.StringVar(); ttk.Label(box, textvariable=self.pv_info, wraplength=340, foreground="#9bb").pack(anchor="w", pady=(8, 0))

    # ---------------------------------------------------------------- данные: загрузка / сохранение
    def reload(self, first=False):
        try: self.mobs = md.load_mobs(self.mobs_path)
        except Exception as e:
            messagebox.showerror("Мобы", f"Не удалось прочитать {self.mobs_path.name}:\n{e}"); self.mobs = {}
        self.saved_text = md.dump_mobs(self.mobs); fixed = []
        for mid, m in self.mobs.items():                 # чиним сломанные пути к скинам (например, rotling: «mobs\rotling\rotling»)
            if isinstance(m.get("skin"), str):
                fx = md.fix_skin(m["skin"], self.assets)
                if fx != m["skin"]: m["skin"] = fx; fixed.append(mid)
        self.cur = None; self._refresh_list()
        if self.mobs: self.select(next(iter(self.mobs)))
        self._update_status()
        if fixed: self.status.set(f"Исправлены пути к картинкам у: {', '.join(fixed)} — нажми «Сохранить», чтобы записать.")

    def save(self):
        warn = md.validate(self.mobs, self.assets, self.projectiles)
        try: md.save_mobs(self.mobs, self.mobs_path)
        except Exception as e: messagebox.showerror("Сохранение", str(e)); return False
        self.saved_text = md.dump_mobs(self.mobs); self._refresh_list(); self._update_status()
        msg = f"Сохранено: {self.mobs_path.name}. В запущенной игре нажми F5."
        self.status.set(msg)
        if warn:
            lines = "\n".join(f"• {mid}: {t}" for mid, t in warn[:14]) + (f"\n… и ещё {len(warn) - 14}" if len(warn) > 14 else "")
            messagebox.showwarning("Сохранено, но есть замечания", lines)
        return True

    def revert(self):
        if self.dirty and not messagebox.askyesno("Отменить изменения", "Все несохранённые правки мобов будут потеряны. Продолжить?"): return
        keep = self.cur; self.reload()
        if keep in self.mobs: self.select(keep)

    def confirm_close(self):
        """True — можно закрывать окно (изменения сохранены или отброшены)."""
        if not self.dirty: return True
        a = messagebox.askyesnocancel("Мобы", "В мобах есть несохранённые изменения. Сохранить их перед выходом?")
        if a is None: return False
        return self.save() if a else True

    def _update_status(self):
        base = "Есть несохранённые изменения" if self.dirty else "Всё сохранено"
        self.status.set(base)

    def touch(self, structural=False):
        """Любая правка модели: сбросить кэш картинок, обновить подписи, статус, при структурных правках — списки."""
        if self.pv: self.pv.invalidate()
        if structural:
            self._atk_refresh_list(keep=True); self._refresh_entries(keep=True); self._an_refresh(keep=True)
        self._refresh_list(); self._update_status()

    # ---------------------------------------------------------------- список мобов
    def _label(self, mid):
        saved = json.loads(self.saved_text).get(mid) if self.saved_text else None
        mark = " *" if saved != self.mobs[mid] else ""
        return f"{mid}  ·  {self.mobs[mid].get('name', '')}{mark}"

    def _refresh_list(self):
        self._loading = True
        self.lb.delete(0, "end")
        for mid in self.mobs: self.lb.insert("end", self._label(mid))
        if self.cur in self.mobs:
            i = list(self.mobs).index(self.cur); self.lb.selection_set(i); self.lb.see(i)
        self._loading = False

    def _on_list(self):
        sel = self.lb.curselection()
        if self._loading or not sel: return
        self.select(list(self.mobs)[sel[0]])

    def select(self, mid):
        self.cur = mid; self.atk_i = None; self._an_sel = None; self._entry = None
        if self.pv: self.pv.invalidate()
        for f in self.main_forms: f.load()
        self.f_tex.load(); self.f_anim_def.load(); self._load_move(); self._json_refresh(); self._update_skin_info()
        self._atk_refresh_list(select=0 if self.mob.get("attacks") else None)
        self._an_refresh(select=0); self._refresh_entries(keep=False); self._refresh_list()

    def _prompt_id(self, title):
        mid = simpledialog.askstring(title, "ID моба (латиница, цифры, _ и -):", parent=self)
        if mid is None: return None
        mid = mid.strip(); err = md.new_mob_id_ok(mid, self.mobs)
        if err: messagebox.showerror(title, err); return None
        return mid

    def new_mob(self):
        mid = self._prompt_id("Новый моб")
        if not mid: return
        self.mobs[mid] = md.new_mob(); self.select(mid); self.touch()

    def copy_mob(self):
        if not self.cur: return
        mid = self._prompt_id(f"Копия моба «{self.cur}»")
        if not mid: return
        have = (self.assets / "mobs" / self.cur).is_dir()
        cp = have and messagebox.askyesno("Копия", "Скопировать и картинки/анимации (папку assets/mobs/%s)?\nНет — копия будет ссылаться на те же файлы." % self.cur)
        self.mobs[mid] = md.copy_mob(self.mobs, self.cur, mid, cp, self.assets); self.select(mid); self.touch()

    def delete_mob(self):
        if not self.cur: return
        refs = md.references(self.cur, self.data_dir)
        text = f"Удалить моба «{self.cur}»? Файлы картинок останутся на диске."
        if refs: text += "\n\nНа него ссылаются карты (после удаления они перестанут его создавать):\n• " + "\n• ".join(refs[:8])
        if not messagebox.askyesno("Удалить моба", text): return
        ids = list(self.mobs); i = ids.index(self.cur); del self.mobs[self.cur]
        self.cur = None; self._refresh_list()
        if self.mobs: self.select(list(self.mobs)[min(i, len(self.mobs) - 1)])
        self._update_status()

    # ---------------------------------------------------------------- текстура
    def _png_size(self, rel):
        p = self.assets / rel
        try:
            key = (str(p), p.stat().st_mtime)
            if key not in self._skin_size:
                img = tk.PhotoImage(file=str(p)); self._skin_size[key] = (img.width(), img.height())
            return self._skin_size[key]
        except Exception: return None

    def _update_skin_info(self):
        skin = (self.mob or {}).get("skin")
        if not skin: self.skin_info.set("Картинка не задана — моб рисуется цветным прямоугольником."); return
        sz = self._png_size(skin)
        self.skin_info.set(f"{skin}: {sz[0]}×{sz[1]} px" if sz else f"Файл не найден: {skin}")

    def _pick_skin(self):
        if not self.mob: return
        f = filedialog.askopenfilename(title="Картинка моба", filetypes=[("PNG", "*.png"), ("Все файлы", "*.*")], initialdir=str(self.assets / "mobs"))
        if not f: return
        try: self.mob["skin"] = md.import_skin(f, self.cur, self.assets)
        except Exception as e: messagebox.showerror("Картинка", str(e)); return
        self.f_tex.load(); self._update_skin_info(); self.touch()

    def _clear_skin(self):
        if self.mob: self.mob.pop("skin", None); self.f_tex.load(); self._update_skin_info(); self.touch()

    def _draw_from_png(self):
        sz = self._png_size(self.mob.get("skin", "")) if self.mob else None
        if not sz: messagebox.showinfo("Картинка", "Сначала выбери существующий PNG."); return
        self.mob["draw"] = [sz[0], sz[1]]; self.f_tex.load(); self.touch()

    def _hitbox_from_draw(self):
        if not self.mob: return
        dw, dh = self.mob.get("draw") or [self.mob.get("w", 24), self.mob.get("h", 32)]
        self.mob["w"], self.mob["h"] = max(4, int(dw * .7)), max(4, int(dh * .7)); self.f_tex.load(); self.touch()

    # ---------------------------------------------------------------- движение
    def _load_move(self):
        mv = self.mob.setdefault("move", {"type": "chase"}) if self.mob else {}
        t = mv.get("type", "chase"); self.move_cb.set(MOVE_RU.get(t, t)); self._build_move_form(t)

    def _build_move_form(self, t):
        if self.f_move: self.f_move.destroy()
        name, desc, fields = md.MOVES.get(t, (t, "Неизвестный вид движения (задан вручную в JSON).", []))
        self.move_desc.set(desc)
        self.f_move = self._form(self.move_box, md.MOVE_COMMON + fields, lambda: self.mob.setdefault("move", {}) if self.mob else None); self.f_move.pack(fill="x")
        self.f_move.load()

    def _move_type_changed(self, _e=None):
        if not self.mob: return
        t = next((k for k, v in MOVE_RU.items() if v == self.move_cb.get()), None)
        if not t: return
        mv = self.mob.setdefault("move", {}); old = mv.get("type", "chase")
        keys = lambda x: {f.key for f in md.MOVES.get(x, ("", "", []))[2]}
        for k in keys(old) - keys(t) - {f.key for f in md.MOVE_COMMON}: mv.pop(k, None)
        mv["type"] = t; self._build_move_form(t); self.touch()

    # ---------------------------------------------------------------- атаки
    def _refs(self, kind):
        if kind == "proj": return self.projectiles
        return [a["id"] for i, a in enumerate(self.mob.get("attacks", [])) if a.get("id") and i != self.atk_i] if self.mob else []

    def _atk_cur(self):
        atks = self.mob.get("attacks", []) if self.mob else []
        return atks[self.atk_i] if self.atk_i is not None and 0 <= self.atk_i < len(atks) else None

    def _atk_refresh_list(self, select=None, keep=False):
        atks = self.mob.get("attacks", []) if self.mob else []
        if keep: select = self.atk_i
        self.atk_lb.delete(0, "end")
        for i, a in enumerate(atks): self.atk_lb.insert("end", md.attack_title(i, a))
        if select is not None and atks: select = max(0, min(select, len(atks) - 1)); self.atk_lb.selection_set(select); self.atk_lb.see(select)
        else: select = None
        changed = select != self.atk_i or not keep
        self.atk_i = select
        if changed or not keep: self._atk_load()

    def _atk_pick(self):
        sel = self.atk_lb.curselection()
        if not sel or sel[0] == self.atk_i: return
        self.atk_i = sel[0]; self._atk_load()
        self._pv_show_attack()

    def _atk_load(self):
        a = self._atk_cur()
        for box in (self.atk_common_box, self.atk_type_box, self.atk_anim_box): box.pack_forget() if a is None else None
        if a is None:
            self.atk_desc.set("У этого моба нет атак. Нажми «Добавить» слева."); self.atk_type_cb.set("")
            if self.f_atk_type: self.f_atk_type.destroy(); self.f_atk_type = None
            return
        self.atk_common_box.pack(fill="x", pady=(6, 6)); self.atk_type_box.pack(fill="x", pady=(0, 6)); self.atk_anim_box.pack(fill="x", pady=(0, 6))
        t = a.get("type", "melee"); self.atk_type_cb.set(TYPE_RU.get(t, t))
        self._atk_build_type_form(t)
        self.f_atk_common.defaults = md.ATTACK_DEFAULTS.get(t, {}); self._atk_update_hints(t); self.f_atk_common.load()
        self._atk_anim_load()

    def _atk_update_hints(self, t):
        """Серые подсказки «по умолч.» зависят от вида атаки — переписываем их в уже построенной форме."""
        defs = md.ATTACK_DEFAULTS.get(t, {})
        for r, f in enumerate(self.f_atk_common.fields):
            lbl = self.f_atk_common.grid_slaves(row=r, column=2)
            if lbl: lbl[0].configure(text=f"по умолч.: {defs.get(f.key, f.hint)}" if defs.get(f.key, f.hint) else "")

    def _atk_build_type_form(self, t):
        if self.f_atk_type: self.f_atk_type.destroy()
        name, desc, fields = md.ATTACK_TYPES.get(t, (t, "Неизвестный вид атаки.", []))
        self.atk_desc.set(desc)
        self.f_atk_type = self._form(self.atk_type_box, fields, self._atk_cur, refs=self._refs, defaults=md.ATTACK_DEFAULTS.get(t, {}))
        self.f_atk_type.pack(fill="x"); self.f_atk_type.load()

    def _atk_add(self, kind):
        if not self.mob: return
        atks = self.mob.setdefault("attacks", []); atks.append(md.new_attack(kind))
        self._atk_refresh_list(select=len(atks) - 1); self.touch(structural=True); self._pv_show_attack()

    def _atk_dup(self):
        a = self._atk_cur()
        if a is None: return
        b = copy.deepcopy(a); b.pop("id", None); self.mob["attacks"].insert(self.atk_i + 1, b)
        self._atk_refresh_list(select=self.atk_i + 1); self.touch(structural=True)

    def _atk_move(self, d):
        atks = self.mob.get("attacks", []) if self.mob else []; i, j = self.atk_i, (self.atk_i or 0) + d
        if i is None or not 0 <= j < len(atks): return
        atks[i], atks[j] = atks[j], atks[i]; self._atk_refresh_list(select=j); self.touch(structural=True)

    def _atk_delete(self):
        a = self._atk_cur()
        if a is None or not messagebox.askyesno("Удалить атаку", f"Удалить атаку «{md.attack_title(self.atk_i, a)}»?"): return
        del self.mob["attacks"][self.atk_i]; i = self.atk_i
        if not self.mob["attacks"]: self.mob.pop("attacks", None)
        self._atk_refresh_list(select=i); self.touch(structural=True)

    def _atk_type_changed(self, _e=None):
        a = self._atk_cur()
        t = next((k for k, v in TYPE_RU.items() if v == self.atk_type_cb.get()), None)
        if a is None or not t or t == a.get("type"): return
        md.change_attack_type(a, t); self._atk_load(); self.touch(structural=True)

    def _atk_anim_load(self):
        a = self._atk_cur()
        if a is None: return
        names = md.anim_names_all(self.cur, self.mob, self.assets)
        for ph, cb in self.atk_anim_cb.items():
            gen = md.phase_gen(a, ph); cb.configure(values=[f"(общая: {gen})", *names]); cb.set((a.get("anims") or {}).get(gen) or f"(общая: {gen})")

    def _atk_anim_set(self, ph):
        a = self._atk_cur()
        if a is None: return
        gen = md.phase_gen(a, ph); v = self.atk_anim_cb[ph].get().strip(); cur = (a.get("anims") or {}).get(gen)
        if v.startswith("(") or not v:
            if cur is None: return
            a["anims"].pop(gen, None)
            if not a["anims"]: a.pop("anims")
        else:
            if v == cur: return
            a.setdefault("anims", {})[gen] = v
            if v not in self.mob.get("anims", {}) and v not in md.STD_NAMES: md.set_anim_spec(self.mob, v)   # запись появится во вкладке «Анимации»
        self._atk_anim_load(); self.touch(structural=True); self._pv_show_attack(phase=ph)

    def _atk_anim_create(self, ph):
        a = self._atk_cur()
        if a is None: return
        gen = md.phase_gen(a, ph); taken = set(md.anim_names_all(self.cur, self.mob, self.assets)) | md.STD_NAMES
        base = f"{a.get('id') or a.get('type', 'atk') + str(self.atk_i + 1)}_{gen}"
        name = simpledialog.askstring("Новая анимация", f"Имя анимации для фазы «{md.PHASE_RU[ph]}» этой атаки:", initialvalue=md.unique_name(base, taken), parent=self)
        if not name: return
        name = name.strip()
        if not md.ID_RE.match(name) or name in md.STD_NAMES: messagebox.showerror("Новая анимация", "Имя: латиница, цифры, _ и -, не из стандартных (idle, move, ...)."); return
        a.setdefault("anims", {})[gen] = name; md.set_anim_spec(self.mob, name)
        self._atk_anim_load(); self.touch(structural=True); self._an_refresh(select_name=name)
        self.nb.select(self.nb.tabs()[4])
        self.status.set(f"Анимация «{name}» создана. Добавь кадры (PNG) кнопкой «Добавить PNG…» — они попадут в assets/mobs/{self.cur}/{name}/.")

    # ---------------------------------------------------------------- анимации и кадры
    def _an_rows(self):
        rows = [(n, t) for n, t in ANIM_ROWS]
        rows += [(n, f"Своя: {n}") for n in md.custom_anim_names(self.cur, self.mob, self.assets)]
        return rows

    def _an_refresh(self, select=None, keep=False, select_name=None):
        if not self.mob: return
        rows = self._an_rows(); names = [n for n, _ in rows]
        if keep and self._an_sel in names: select = names.index(self._an_sel)
        if select_name in names: select = names.index(select_name)
        self.an_lb.delete(0, "end")
        for n, title in rows:
            cnt = len(md.list_frames(md.anim_source(self.cur, self.mob, n, self.assets)[0], self.assets))
            self.an_lb.insert("end", f"{title}   —   {cnt} кадр." if cnt else f"{title}   —   нет кадров")
        if select is not None and rows:
            select = max(0, min(select, len(rows) - 1)); self.an_lb.selection_set(select); self.an_lb.see(select); self._an_sel = names[select]
        else: self._an_sel = None
        self._an_load_detail()

    def _an_pick(self):
        sel = self.an_lb.curselection()
        if not sel: return
        names = [n for n, _ in self._an_rows()]
        self._an_sel = names[sel[0]]; self._an_load_detail()
        title = dict(self._an_rows()).get(self._an_sel, self._an_sel)
        self._pv_set_entry({"kind": "state", "state": self._an_sel, "label": title, "key": "state:" + self._an_sel})

    def _an_load_detail(self):
        n = self._an_sel; self.fr_lb.delete(0, "end"); self.an_note.set("")
        if not n or not self.mob: self.an_title.set(""); self.an_source.set(""); return
        self._an_spec = md.anim_spec(self.mob, n); rel, kind = md.anim_source(self.cur, self.mob, n, self.assets)
        title = dict(self._an_rows()).get(n, n); self.an_title.set(title)
        where = {"dir": "папка", "glob": "шаблон", "file": "один файл", "none": "кадров пока нет — папка"}[kind]
        self.an_source.set(f"Кадры берутся отсюда ({where}): assets/{rel}")
        for i, f in enumerate(md.list_frames(rel, self.assets), 1): self.fr_lb.insert("end", f"{i}.  {Path(f).name}")
        self.f_anim.load()
        if not md.own_folder(self.cur, rel):
            self.an_note.set(f"Эта анимация берёт кадры не из папки assets/mobs/{self.cur}/ (или по шаблону) — файлы правь вручную, редактор их не перенумеровывает.")

    def _an_spec_changed(self, key):
        n = self._an_sel
        if not n or not self.mob: return
        md.set_anim_spec(self.mob, n, fps=self._an_spec.get("fps"), loop=self._an_spec.get("loop"), frames=self._an_spec.get("frames"))
        self.touch(structural=True)

    def _an_new(self):
        if not self.mob: return
        taken = set(md.anim_names_all(self.cur, self.mob, self.assets)) | md.STD_NAMES
        name = simpledialog.askstring("Новая анимация", "Имя анимации (латиница, цифры, _ и -):", initialvalue=md.unique_name("anim", taken), parent=self)
        if not name: return
        name = name.strip()
        if not md.ID_RE.match(name) or name in md.STD_NAMES: messagebox.showerror("Новая анимация", "Имя: латиница, цифры, _ и -, не из стандартных."); return
        if name in taken: messagebox.showerror("Новая анимация", f"Анимация «{name}» уже есть."); return
        md.set_anim_spec(self.mob, name); self.touch(structural=True); self._an_refresh(select_name=name); self._an_pick_after_refresh()

    def _an_pick_after_refresh(self):
        title = dict(self._an_rows()).get(self._an_sel, self._an_sel)
        if self._an_sel: self._pv_set_entry({"kind": "state", "state": self._an_sel, "label": title, "key": "state:" + self._an_sel})

    def _an_delete(self):
        n = self._an_sel
        if not n or not self.mob: return
        key = md.anim_key(self.mob, n)
        if key not in self.mob.get("anims", {}):
            messagebox.showinfo("Анимации", "У этого состояния нет своей записи в моба (кадры берутся из папки) — убирать нечего."); return
        if not messagebox.askyesno("Убрать запись", f"Убрать запись об анимации «{n}» из моба?\nФайлы кадров на диске останутся."): return
        del self.mob["anims"][key]
        if not self.mob["anims"]: del self.mob["anims"]
        for a in self.mob.get("attacks", []):                       # и снять назначение с атак
            for ph, v in list((a.get("anims") or {}).items()):
                if v == n: del a["anims"][ph]
            if "anims" in a and not a["anims"]: a.pop("anims")
        self.touch(structural=True); self._atk_anim_load()

    def _an_target(self):
        """Куда складывать кадры: (путь папки, можно ли) для выбранной анимации."""
        rel, kind = md.anim_source(self.cur, self.mob, self._an_sel, self.assets)
        if kind == "glob" or kind == "file": return rel, False
        return rel, md.own_folder(self.cur, rel)

    def _fr_add(self):
        if not self._an_sel: return
        rel, ok = self._an_target()
        if not ok: messagebox.showinfo("Кадры", "Эта анимация берёт кадры из чужой папки/шаблона. Нажми «Папка по умолчанию» или правь файлы вручную."); return
        files = filedialog.askopenfilenames(title="Кадры анимации (PNG)", filetypes=[("PNG", "*.png")], initialdir=str(self.assets / "mobs"))
        if not files: return
        try: n = md.add_frames(rel, files, self.assets)
        except Exception as e: messagebox.showerror("Кадры", str(e)); return
        self._frames_changed(f"Добавлено кадров: {n}")

    def _fr_remove(self):
        sel = self.fr_lb.curselection(); rel, ok = self._an_target() if self._an_sel else ("", False)
        if not sel or not ok: return
        if not messagebox.askyesno("Удалить кадр", "Файл кадра будет удалён с диска, остальные перенумерованы. Продолжить?"): return
        md.remove_frame(rel, sel[0], self.assets); self._frames_changed("Кадр удалён", select=max(0, sel[0] - 1))

    def _fr_move(self, d):
        sel = self.fr_lb.curselection(); rel, ok = self._an_target() if self._an_sel else ("", False)
        if not sel or not ok: return
        j = md.move_frame(rel, sel[0], d, self.assets); self._frames_changed("", select=j)

    def _frames_changed(self, msg, select=None):
        if self.pv: self.pv.invalidate()
        self._an_refresh(keep=True); self._an_load_detail()
        if select is not None and self.fr_lb.size(): self.fr_lb.selection_set(min(select, self.fr_lb.size() - 1))
        if msg: self.status.set(msg)
        self._atk_anim_load()

    def _fr_pick(self):
        sel = self.fr_lb.curselection()
        if not sel or not self._an_sel: return
        rel, _ = md.anim_source(self.cur, self.mob, self._an_sel, self.assets); files = md.list_frames(rel, self.assets)
        if sel[0] < len(files): self._pv_set_entry({"kind": "frame", "path": files[sel[0]], "label": f"Кадр {sel[0] + 1}: {files[sel[0]]}", "key": "frame"}, pause=True)

    def _an_pick_folder(self):
        if not self._an_sel: return
        d = filedialog.askdirectory(title="Папка с кадрами (внутри assets)", initialdir=str(self.assets / "mobs"), mustexist=True)
        if not d: return
        try: rel = Path(d).resolve().relative_to(self.assets.resolve()).as_posix()
        except ValueError: messagebox.showerror("Папка кадров", "Папка должна лежать внутри assets."); return
        self._an_spec["frames"] = rel; self._an_spec_changed("frames"); self._an_load_detail()

    def _an_reset_folder(self):
        if not self._an_sel: return
        self._an_spec.pop("frames", None); self._an_spec_changed("frames"); self._an_load_detail()

    def _an_open_folder(self):
        if not self._an_sel: return
        rel, _ = md.anim_source(self.cur, self.mob, self._an_sel, self.assets)
        p = self.assets / (str(Path(rel).parent) if "*" in rel else rel)
        if md.own_folder(self.cur, rel): p.mkdir(parents=True, exist_ok=True)     # своей папки ещё может не быть — создаём
        elif not p.is_dir(): p = p.parent
        try:
            if sys.platform.startswith("win"): os.startfile(str(p))
            elif sys.platform == "darwin": subprocess.Popen(["open", str(p)])
            else: subprocess.Popen(["xdg-open", str(p)])
        except Exception as e: messagebox.showinfo("Папка", f"{p}\n\n(не удалось открыть: {e})")

    # ---------------------------------------------------------------- JSON
    def _json_refresh(self):
        self.json_text.delete("1.0", "end"); self.json_note.set("")
        if self.mob is not None: self.json_text.insert("1.0", json.dumps(self.mob, ensure_ascii=False, indent=2))

    def _json_apply(self):
        try: d = json.loads(self.json_text.get("1.0", "end"))
        except ValueError as e: self.json_note.set(f"Ошибка JSON: {e}"); return
        if not isinstance(d, dict): self.json_note.set("Должен быть объект { ... }"); return
        self.mobs[self.cur] = d; self.json_note.set(""); keep = self.cur; self.select(keep); self.touch()

    # ---------------------------------------------------------------- окно моба
    def _tab_changed(self, e):
        if e.widget is self.nb and self.nb.index("current") == 5: self._json_refresh()

    def _refresh_entries(self, keep=True):
        if not self.pv or not self.mob: return
        old = self._entry["key"] if (keep and self._entry) else None
        self._entries = md.preview_entries(self.cur, self.mob, self.assets)
        self.pv_combo.configure(values=[e["label"] for e in self._entries])
        pick = next((e for e in self._entries if e["key"] == old), None) or (self._entries[0] if self._entries else None)
        if self._entry and self._entry["kind"] == "frame" and keep: return
        self._pv_set_entry(pick)

    def _pv_set_entry(self, entry, pause=False):
        if not self.pv or entry is None: return
        self._entry = entry; self.pv_combo.set(entry["label"]); self._pv_restart()
        if pause and not self._paused: self._pv_toggle()
        elif not pause and self._paused: self._pv_toggle()

    def _pv_chosen(self):
        i = self.pv_combo.current()
        if 0 <= i < len(self._entries): self._pv_set_entry(self._entries[i])

    def _pv_show_attack(self, phase=None):
        """Выбрали/изменили атаку — показать её в окне справа (всю или нужную фазу)."""
        if not self.pv or self.atk_i is None: return
        want = ("phase", phase) if phase else ("attack", None)
        for e in self._entries:
            if e["kind"] == want[0] and e.get("i") == self.atk_i and (phase is None or e.get("phase") == phase): self._pv_set_entry(e); return

    def _pv_toggle(self):
        if not self.pv: return
        now = time.monotonic()
        if self._paused: self._t0 = now; self._paused = False; self.pv_play.configure(text="Пауза")
        else: self._t_acc += (now - self._t0) * self._speed; self._paused = True; self.pv_play.configure(text="Играть")

    def _pv_restart(self):
        self._t0 = time.monotonic(); self._t_acc = 0.0

    def _pv_step(self, d):
        if not self.pv: return
        if not self._paused: self._pv_toggle()
        self._t_acc = max(0.0, self._t_acc + d * self.pv.frame_dt)

    def _pv_speed_changed(self, _e=None):
        t = self._time(); self._speed = float(self.pv_speed.get().rstrip("×")); self._t_acc = t; self._t0 = time.monotonic()

    def _time(self):
        return self._t_acc if self._paused else self._t_acc + (time.monotonic() - self._t0) * self._speed

    def _tick(self):
        try:
            if self.pv and self._entry and self.mob and self.winfo_viewable():
                opts = {k: v.get() for k, v in self.pv_opt.items()}
                opts["zoom"] = int(self.pv_zoom.get().rstrip("×"))
                on_attacks = self.nb.index("current") == 3     # зона выбранной атаки рисуется, пока открыта вкладка «Атаки»
                opts["zone"] = self.atk_i if (self.pv_opt["zone"].get() and self.atk_i is not None and on_attacks) else None
                data, info = self.pv.render(self.cur, self.mob, self._entry, self._time(), opts)
                self._photo = tk.PhotoImage(data=data); self.pv_canvas.itemconfigure(self._pv_img, image=self._photo)
                self.pv_info.set(info)
        except Exception as e:      # ошибка рисования не должна ронять редактор
            self.pv_info.set(f"Ошибка окна просмотра: {e}")
        self.after(33, self._tick)
