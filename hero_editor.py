# -*- coding: utf-8 -*-
"""Вкладка «Герои» редактора (map_editor.py): играбельные персонажи из data/characters.json и оформление меню
навыков (assets/skill_menu.json) — без ручной правки JSON.

Слева — список героев (кнопки «Новый…», «Копия…», «Удалить»). В центре — подвкладки:
  · «Дерево навыков» — порядок открытия скилов: базовые навыки и слоты дерева с уровнями; ↑/↓ переставляют,
    «Добавить…»/«Удалить» меняют состав, форма справа правит выбранный слот;
  · «Меню навыков» — внешний вид окна открытия скилов: окно 4×2, сетка, размеры, цвета, тексты, прокрутка;
  · «Персонаж» — название, роль, описание, особенности;
  · «JSON» — любое поле героя, которого нет в формах.
Справа — предпросмотр меню навыков (tk.Canvas): сетка ячеек с цветами навыков, тексты и стрелки прокрутки —
рисуется так, как меню выглядит в игре.

Сохранение: «Сохранить» пишет data/characters.json; на подвкладке «Меню навыков» — своя кнопка
(assets/skill_menu.json). В запущенной игре нажми F5, чтобы подхватить изменения.
"""
import copy, json
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox, simpledialog

from mob_data import F
from mob_editor import Form, ScrollFrame

ROOT = Path(__file__).resolve().parent
CHARS_PATH = ROOT / "data" / "characters.json"
MENU_PATH = ROOT / "assets" / "skill_menu.json"
SKILLS_PATH = ROOT / "data" / "skills.json"
GRAY = "#7a7a85"

GAME_W, GAME_H = 960, 512      # окно игры (30×16 тайлов) — предпросмотр рисует его пропорции

# ---------------------------------------------------------------- описание полей форм
def _tree_fields(skills):
    return [
        F("skill", "Навык слота", "choice", "", "Что откроется в этой ячейке. Список — data/skills.json.", tuple(skills)),
        F("unlock_level", "Уровень открытия", "int", "1", "Навык открывается автоматически по порядку при достижении уровня."),
        F("lock_icon", "Иконка замка", "text", "авто", "Путь в assets (по умолчанию icons/locks/<id>_lock.png)."),
    ]
CHAR_FIELDS = [
    F("name", "Название", "text", "", "Имя героя (карточка выбора, HUD)."),
    F("role", "Роль", "text", "", "Подпись на карточке выбора (например «Танк»)."),
    F("description", "Описание", "text", "", "Текст панели описания героя."),
    F("spellcaster", "Чистый заклинатель", "bool", "нет", "ЛКМ кастует, оружие только в правой руке; у мага отключено в пользу силы каста."),
    F("cast_power", "Сила каста (планшет)", "bool", "нет", "Ползунок силы заклинаний на планшете мага (только у мага)."),
]
MENU_GROUPS = [
    ("Окно меню", [
        F("columns", "Столбцов в окне", "int", "4", "Окно видимых ячеек: 4×2 = 8 карточек. Остальные листаются колесом."),
        F("rows", "Строк в окне", "int", "2", "Окно видимых ячеек: 4×2 = 8 карточек. Остальные листаются колесом."),
        F("background_image", "Фон (путь в assets)", "text", "ui/skill_menu_background.png", "Пусто — заливается цветом overlay_color."),
        F("overlay_color", "Цвет затемнения", "rgb", "", "Работает без background_image."),
        F("overlay_alpha", "Плотность затемнения", "int", "242", "0–255."),
    ]),
    ("Сетка ячеек", [
        F("cell_width", "Ширина ячейки", "int", "180", "Пусто — подбирается автоматически под окно."),
        F("cell_height", "Высота ячейки", "int", "150", ""),
        F("gap_x", "Отступ по горизонтали", "int", "14", ""),
        F("gap_y", "Отступ по вертикали", "int", "16", ""),
        F("grid_x", "Сетка: X", "int", "по центру", "Пусто — сетка центрируется."),
        F("grid_y", "Сетка: Y", "int", "125", "Отступ сетки от верха окна."),
        F("corner_radius", "Скругление углов", "int", "10", ""),
        F("border_width", "Толщина рамки", "int", "3", "0 — без рамки."),
    ]),
    ("Содержимое карточки", [
        F("icon_size", "Иконка: размер", "int", "52", ""),
        F("icon_y", "Иконка: отступ сверху", "int", "42", ""),
        F("name_y", "Название: отступ", "int", "82", ""),
        F("status_y", "Статус: отступ", "int", "106", ""),
        F("show_skill_names", "Показывать названия", "bool", "да", ""),
        F("show_status", "Показывать статус", "bool", "да", ""),
        F("show_slot_numbers", "Показывать номера", "bool", "да", ""),
        F("slot_number_bottom_offset", "Номера: отступ снизу", "int", "23", ""),
        F("mark_passive", "Помечать пассивки", "bool", "да", "Префикс passive_prefix."),
        F("passive_prefix", "Префикс пассивок", "text", "[ПАССИВ] ", ""),
    ]),
    ("Тексты", [
        F("title", "Заголовок", "text", "НОВЫЙ УРОВЕНЬ: {level}", "{level} — номер уровня."),
        F("title_x", "Заголовок: X", "int", "центр", ""), F("title_y", "Заголовок: Y", "int", "48", ""),
        F("show_subtitle", "Показывать подзаголовок", "bool", "да", ""),
        F("subtitle", "Подзаголовок", "text", "", ""),
        F("subtitle_x", "Подзаголовок: X", "int", "центр", ""), F("subtitle_y", "Подзаголовок: Y", "int", "88", ""),
        F("footer", "Подпись снизу", "text", "", ""),
        F("footer_x", "Подпись: X", "int", "центр", ""), F("footer_y", "Подпись: Y", "int", "низ", ""),
        F("locked_name", "Имя закрытого", "text", "ЗАБЛОКИРОВАНО", ""),
        F("locked_status_format", "Статус закрытого", "text", "Уровень {level}", ""),
        F("unlocked_status", "Статус открытого", "text", "Открыт/Доступен", ""),
        F("unlocked_passive_status", "Статус пассивки", "text", "Пассив активен", ""),
    ]),
    ("Текстуры карточек", [
        F("slot_image", "Карточка (общая)", "text", "", "Путь в assets."),
        F("slot_unlocked_image", "Карточка открытая", "text", "как slot_image", ""),
        F("slot_locked_image", "Карточка закрытая", "text", "как slot_image", ""),
        F("tint_slot_images", "Тонировать карточки", "bool", "нет", "Полупрозрачный слой цвета поверх текстуры."),
        F("fallback_lock_draw", "Замок без текстуры", "bool", "да", "Рисовать замок линиями, если PNG не найден."),
    ]),
    ("Прокрутка дерева", [
        F("scroll_arrow_color", "Цвет стрелок ▲/▼", "rgb", "", "И счётчика скрытых ячеек."),
        F("scroll_gap_top", "Отступ стрелки сверху", "int", "14", ""),
        F("scroll_gap_bottom", "Отступ стрелки снизу", "int", "6", ""),
    ]),
]
COLOR_FIELDS = {
    "title_color": "Заголовок", "subtitle_color": "Подзаголовок", "footer_color": "Подпись снизу",
    "unlocked_bg": "Открытая карточка", "locked_bg": "Закрытая карточка", "locked_border": "Рамка закрытой",
    "name_unlocked_color": "Название открытого", "name_locked_color": "Название закрытого",
    "status_unlocked_color": "Статус открытого", "status_locked_color": "Статус закрытого",
    "slot_number_color": "Номера слотов", "scroll_arrow_color": "Стрелки прокрутки",
}


def hex_of(c, default="#20222e"):
    try:
        return "#%02x%02x%02x" % tuple(max(0, min(255, int(v))) for v in c[:3])
    except (TypeError, ValueError):
        return default


class HeroTab(ttk.Frame):
    """Вкладка «Герои»: персонажи (data/characters.json) + меню навыков (assets/skill_menu.json)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.chars, self.chars_saved = {}, ""
        self.menu, self.menu_saved = {}, ""
        self.skills = {}
        self.cur = None; self.sel = None; self._loading = False
        self.help, self.status = tk.StringVar(), tk.StringVar()
        self._load_data(); self._build()

    # ---------------------------------------------------------------- данные
    @property
    def order(self):
        order = self.chars.get("order") or list(self.chars.get("characters", {}).keys())
        return [c for c in order if c in self.chars.get("characters", {})]

    @property
    def hero(self): return self.chars.get("characters", {}).get(self.cur, {})

    @property
    def chars_dirty(self): return self._dump(self.chars) != self.chars_saved

    @property
    def menu_dirty(self): return self._dump(self.menu) != self.menu_saved

    @property
    def dirty(self): return self.chars_dirty or self.menu_dirty

    @staticmethod
    def _dump(d): return json.dumps(d, ensure_ascii=False, indent=2, sort_keys=True)

    def _load_data(self):
        for attr, path, default in (("chars", CHARS_PATH, {"order": [], "characters": {}}),
                                    ("menu", MENU_PATH, {}), ("skills", SKILLS_PATH, {})):
            try:
                obj = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                obj = default
            setattr(self, attr, obj)
        self.chars_saved = self._dump(self.chars); self.menu_saved = self._dump(self.menu)
        if not self.order and self.chars.get("characters"):
            self.cur = next(iter(self.chars["characters"]))
        elif self.order:
            self.cur = self.order[0]

    # ---------------------------------------------------------------- построение
    def _build(self):
        bar = ttk.Frame(self); bar.pack(side="bottom", fill="x", pady=(6, 0))
        ttk.Button(bar, text="Сохранить в data/characters.json", command=self.save).pack(side="left")
        ttk.Button(bar, text="Отменить все изменения", command=self.revert).pack(side="left", padx=6)
        ttk.Label(bar, textvariable=self.status).pack(side="left", padx=10)
        ttk.Label(self, textvariable=self.help, foreground=GRAY, wraplength=1100).pack(side="bottom", fill="x", pady=(4, 0))
        paned = ttk.PanedWindow(self, orient="horizontal"); paned.pack(fill="both", expand=True)
        left, center, right = ttk.Frame(paned), ttk.Frame(paned), ttk.Frame(paned)
        paned.add(left, weight=0); paned.add(center, weight=1); paned.add(right, weight=0)
        self._build_list(left)
        self.nb = ttk.Notebook(center); self.nb.pack(fill="both", expand=True, padx=6)
        self._build_tree(); self._build_menu(); self._build_char(); self._build_json()
        self._build_preview(right)
        self._refresh_list(); self._refresh_tree(); self._refresh_preview(); self._update_status(); self._load_all_forms()

    def _build_list(self, parent):
        box = ttk.LabelFrame(parent, text="Герои", padding=4); box.pack(fill="both", expand=True)
        row = ttk.Frame(box); row.pack(side="bottom", fill="x", pady=(4, 0))
        for text, cmd in (("Новый…", self.new_hero), ("Копия…", self.copy_hero), ("Удалить", self.delete_hero)):
            ttk.Button(row, text=text, command=cmd, width=7).pack(side="left", padx=1)
        sb = ttk.Scrollbar(box, orient="vertical"); sb.pack(side="right", fill="y")
        self.lb = tk.Listbox(box, width=22, exportselection=False, activestyle="none", yscrollcommand=sb.set); sb.configure(command=self.lb.yview)
        self.lb.pack(side="left", fill="both", expand=True); self.lb.bind("<<ListboxSelect>>", lambda e: self._on_list())

    def _tab(self, title):
        f = ttk.Frame(self.nb, padding=10); self.nb.add(f, text=title); return f

    # ---------- подвкладка: дерево навыков
    def _build_tree(self):
        tab = self._tab("  Дерево навыков  ")
        head = ttk.Label(tab, text="Порядок в списке = порядок открытия навыков. Слотов может быть сколько угодно — "
                                   "в игре окно 4×2 листается колесом мыши.", foreground=GRAY, wraplength=700)
        head.pack(anchor="w", pady=(0, 6))
        top = ttk.Frame(tab); top.pack(fill="x", pady=(0, 8))
        bs = ttk.LabelFrame(top, text="Базовые навыки (с самого начала)", padding=6); bs.pack(side="left", fill="both", expand=True, padx=(0, 8))
        sb = ttk.Scrollbar(bs, orient="vertical"); sb.pack(side="right", fill="y")
        self.bs_lb = tk.Listbox(bs, height=4, exportselection=False, activestyle="none", yscrollcommand=sb.set); sb.configure(command=self.bs_lb.yview)
        self.bs_lb.pack(fill="both", expand=True)
        row = ttk.Frame(bs); row.pack(fill="x", pady=(4, 0))
        self.bs_cb = ttk.Combobox(row, values=self._skill_ids(), state="readonly", width=22); self.bs_cb.pack(side="left")
        ttk.Button(row, text="+", width=3, command=self._bs_add).pack(side="left", padx=2)
        ttk.Button(row, text="−", width=3, command=self._bs_del).pack(side="left")

        tr = ttk.LabelFrame(top, text="Дерево (слоты по порядку)", padding=6); tr.pack(side="left", fill="both", expand=True)
        brow = ttk.Frame(tr); brow.pack(fill="x")
        for text, cmd in (("↑", lambda: self._tree_move(-1)), ("↓", lambda: self._tree_move(1)),
                          ("Добавить…", self._tree_add), ("Удалить", self._tree_del)):
            ttk.Button(brow, text=text, command=cmd, width=9).pack(side="left", padx=1)
        sb2 = ttk.Scrollbar(tr, orient="vertical"); sb2.pack(side="right", fill="y")
        self.tree_lb = tk.Listbox(tr, height=10, exportselection=False, activestyle="none", yscrollcommand=sb2.set); sb2.configure(command=self.tree_lb.yview)
        self.tree_lb.pack(fill="both", expand=True); self.tree_lb.bind("<<ListboxSelect>>", lambda e: self._on_slot())
        form_box = ttk.LabelFrame(tab, text="Выбранный слот", padding=8); form_box.pack(fill="x", pady=(8, 0))
        self.slot_form = Form(form_box, _tree_fields(self._skill_ids()), lambda: self._slot(), self._slot_change, self.help.set)
        self.slot_form.pack(fill="x")

    def _skill_ids(self):
        return sorted(k for k in self.skills if not str(k).startswith("_"))

    # ---------- подвкладка: меню навыков
    def _build_menu(self):
        tab = self._tab("  Меню навыков  ")
        bar = ttk.Frame(tab); bar.pack(side="bottom", fill="x", pady=(6, 0))
        ttk.Button(bar, text="Сохранить в assets/skill_menu.json", command=self.save_menu).pack(side="left")
        ttk.Button(bar, text="Отменить изменения меню", command=self.revert_menu).pack(side="left", padx=6)
        ttk.Label(tab, text="Окно видимых ячеек задают columns × rows (сейчас 4×2 = 8). Остальные строки листаются колесом.",
                  foreground=GRAY).pack(anchor="w", pady=(0, 6))
        sc = ScrollFrame(tab); sc.pack(fill="both", expand=True)
        self.menu_forms = []
        for title, fields in MENU_GROUPS:
            lf = ttk.LabelFrame(sc.inner, text=title, padding=8); lf.pack(fill="x", pady=(0, 8), padx=(0, 6))
            form = Form(lf, fields, lambda: self.menu, lambda k: self.touch_menu(), self.help.set)
            form.pack(fill="x"); self.menu_forms.append(form)
        # цвета отдельным блоком (rgb-поля)
        cf = ttk.LabelFrame(sc.inner, text="Цвета", padding=8); cf.pack(fill="x", pady=(0, 8), padx=(0, 6))
        self.color_form = Form(cf, [F(k, v, "rgb", "", "") for k, v in COLOR_FIELDS.items()],
                               lambda: self.menu, lambda k: self.touch_menu(), self.help.set)
        self.color_form.pack(fill="x")

    # ---------- подвкладка: персонаж
    def _build_char(self):
        tab = self._tab("  Персонаж  ")
        lf = ttk.LabelFrame(tab, text="Основное", padding=8); lf.pack(fill="x")
        self.char_form = Form(lf, CHAR_FIELDS, lambda: self.hero, lambda k: self.touch(), self.help.set)
        self.char_form.pack(fill="x")
        ttk.Label(tab, text="Характеристики (stats), оружие, арбалеты и прочие поля героя — на подвкладке «JSON».",
                  foreground=GRAY).pack(anchor="w", pady=(8, 0))

    # ---------- подвкладка: JSON
    def _build_json(self):
        tab = self._tab("  JSON  ")
        self.json_text = tk.Text(tab, height=18, font=("Consolas", 10)); self.json_text.pack(fill="both", expand=True)
        row = ttk.Frame(tab); row.pack(fill="x", pady=(6, 0))
        ttk.Button(row, text="Применить к герою", command=self._json_apply).pack(side="left")
        ttk.Label(row, text="JSON текущего героя (stats, weapons, skill_overrides…).", foreground=GRAY).pack(side="left", padx=8)

    def _json_apply(self):
        try:
            data = json.loads(self.json_text.get("1.0", "end"))
        except ValueError as e:
            messagebox.showerror("JSON", f"Не удалось разобрать JSON:\n{e}"); return
        self.chars["characters"][self.cur] = data
        self.touch(structural=True); self._refresh_json(); self._refresh_tree()

    def _refresh_json(self):
        self.json_text.delete("1.0", "end"); self.json_text.insert("1.0", self._dump(self.hero))

    # ---------- предпросмотр меню
    def _build_preview(self, parent):
        box = ttk.LabelFrame(parent, text="Предпросмотр меню", padding=4); box.pack(fill="both", expand=True)
        self.pv = tk.Canvas(box, width=480, height=300, bg="#14141f", highlightthickness=0)
        self.pv.pack(fill="both", expand=True)

    def _refresh_preview(self):
        c = self.pv; c.delete("all")
        w = max(c.winfo_width(), 40); h = max(c.winfo_height(), 40)
        if w <= 41: w, h = 480, 300                       # до первого показа окна размер 1
        S = min(w / GAME_W, h / GAME_H)
        m = self.menu
        def X(v): return v * S
        c.create_rectangle(X(6), X(6), X(GAME_W - 6), X(GAME_H - 6), fill="#0d0d1c", outline="#2c2c40")
        cols = max(1, int(m.get("columns", 4))); rows = max(1, int(m.get("rows", 2)))
        cw = int(m.get("cell_width", 180)); ch = int(m.get("cell_height", 150))
        gx = int(m.get("gap_x", 14)); gy = int(m.get("gap_y", 16))
        total_w = cols * cw + (cols - 1) * gx
        ox = int(m.get("grid_x", (GAME_W - total_w) // 2)); oy = int(m.get("grid_y", 125))
        slots = list(self.hero.get("skill_tree", []))
        while len(slots) < cols * rows: slots.append({"skill": None, "unlock_level": 999})
        # заголовок/подзаголовок
        t = str(m.get("title", "НОВЫЙ УРОВЕНЬ: {level}")).format(level=self._menu_level())
        c.create_text(X(m.get("title_x", GAME_W // 2)), X(m.get("title_y", 48)), text=t[:40],
                      fill=hex_of(m.get("title_color", (255, 220, 130))), font=("Segoe UI", max(8, int(13 * S + 6))))
        if m.get("show_subtitle", True) and m.get("subtitle"):
            c.create_text(X(m.get("subtitle_x", GAME_W // 2)), X(m.get("subtitle_y", 88)), text=str(m.get("subtitle"))[:60],
                          fill=hex_of(m.get("subtitle_color", (215, 215, 235))), font=("Segoe UI", max(7, int(9 * S + 4))))
        # ячейки
        for i, slot in enumerate(slots[:cols * rows]):
            sid = slot.get("skill"); col, row = i % cols, i // cols
            x, y = ox + col * (cw + gx), oy + row * (ch + gy)
            sk = self.skills.get(sid, {}) if sid else {}
            border = hex_of(sk.get("color", (110, 110, 135)))
            unlocked_bg = hex_of(m.get("unlocked_bg", (35, 55, 50)))
            c.create_rectangle(X(x), X(y), X(x + cw), X(y + ch), fill=unlocked_bg, outline=border, width=max(1, int(2 * S + 1)))
            if sid:
                ic = int(m.get("icon_size", 52)); iy = int(m.get("icon_y", 42))
                c.create_rectangle(X(x + cw / 2 - ic / 2), X(y + iy - ic / 2), X(x + cw / 2 + ic / 2), X(y + iy + ic / 2),
                                   fill=hex_of(sk.get("color", (90, 90, 110))), outline="")
                name = str(sk.get("name", sid))
                if sk.get("category") == "passive" and m.get("mark_passive", True):
                    name = str(m.get("passive_prefix", "[ПАССИВ] ")) + name
                ny = int(m.get("name_y", 82))
                c.create_text(X(x + cw / 2), X(y + ny), text=name[:18],
                              fill=hex_of(m.get("name_unlocked_color", (255, 240, 190))), font=("Segoe UI", max(7, int(8 * S + 4))))
            else:
                c.create_text(X(x + cw / 2), X(y + ch / 2), text="—", fill="#55556a", font=("Segoe UI", 10))
        # стрелки прокрутки
        total_rows = (len(list(self.hero.get("skill_tree", []))) + cols - 1) // cols
        max_scroll = max(0, total_rows - rows)
        if max_scroll > 0:
            acol = hex_of(m.get("scroll_arrow_color", (255, 220, 130)))
            cx = ox + total_w / 2
            c.create_text(X(cx), X(oy - int(m.get("scroll_gap_top", 14)) - 4), text="▲", fill=acol, font=("Segoe UI", 9))
            c.create_text(X(cx), X(oy + rows * (ch + gy) + int(m.get("scroll_gap_bottom", 6)) + 4),
                          text=f"▼ ещё {(total_rows - rows) * cols}", fill=acol, font=("Segoe UI", 9))
        # подпись снизу
        if m.get("show_footer", True) and m.get("footer"):
            c.create_text(X(m.get("footer_x", GAME_W // 2)), X(m.get("footer_y", GAME_H - 20)), text=str(m.get("footer"))[:70],
                          fill=hex_of(m.get("footer_color", (210, 210, 225))), font=("Segoe UI", max(7, int(8 * S + 4))))

    def _menu_level(self):
        return 1 + len(self.hero.get("base_skills", [])) // 3

    # ---------------------------------------------------------------- списки
    def _refresh_list(self):
        self.lb.delete(0, "end")
        for cid in self.order:
            self.lb.insert("end", f"{self.chars['characters'][cid].get('name', cid)}  ({cid})")
        if self.cur in self.order:
            self.lb.selection_set(self.order.index(self.cur))

    def _on_list(self):
        sel = self.lb.curselection()
        if not sel: return
        self.cur = self.order[sel[0]]
        self._refresh_tree(); self._refresh_json(); self._refresh_char_form(); self._refresh_preview()
    def _refresh_char_form(self):
        self.char_form.load()

    def _load_all_forms(self):
        self.char_form.load()
        for f in self.menu_forms: f.load()
        self.color_form.load()

    def _refresh_tree(self, keep_sel=False):
        keep = self.sel if keep_sel else None
        self.bs_lb.delete(0, "end")
        for sid in self.hero.get("base_skills", []): self.bs_lb.insert("end", sid)
        self.tree_lb.delete(0, "end")
        for i, slot in enumerate(self.hero.get("skill_tree", [])):
            lvl = slot.get("unlock_level", "?")
            self.tree_lb.insert("end", f"{i + 1:>2}.  ур. {lvl:<4} {slot.get('skill') or '— пусто —'}")
        self.sel = None
        if keep is not None and 0 <= keep < self.tree_lb.size():
            self.tree_lb.selection_set(keep); self.tree_lb.see(keep); self.sel = keep
        self._load_slot_form()

    def _slot(self):
        slots = self.hero.get("skill_tree", [])
        if self.sel is None or self.sel >= len(slots): return {}
        return slots[self.sel]

    def _on_slot(self):
        s = self.tree_lb.curselection()
        self.sel = s[0] if s else None
        self._load_slot_form()

    def _load_slot_form(self):
        self._loading = True
        reg = self.slot_form.w.get("skill", {})
        if "cb" in reg: reg["cb"].set(self._slot().get("skill") or "по умолчанию")
        reg = self.slot_form.w.get("unlock_level", {})
        if "var" in reg: reg["var"].set(str(self._slot().get("unlock_level", "")))
        reg = self.slot_form.w.get("lock_icon", {})
        if "var" in reg: reg["var"].set(str(self._slot().get("lock_icon", "") or ""))
        self._loading = False

    def _slot_change(self, key):
        # Form._commit сам записал значение в слот (пустое поле — ключ удалён)
        if self._loading or self.sel is None: return
        self.touch(structural=True)

    # ---------------------------------------------------------------- правки дерева
    def _tree_move(self, d):
        slots = self.hero.get("skill_tree", [])
        if self.sel is None or not (0 <= self.sel + d < len(slots)) or not slots: return
        slots[self.sel], slots[self.sel + d] = slots[self.sel + d], slots[self.sel]
        self.sel += d
        self.touch(structural=True)

    def _tree_add(self):
        dlg = _SlotDialog(self, self._skill_ids())
        self.wait_window(dlg)
        if dlg.result is None: return
        sid, lvl = dlg.result
        self.hero.setdefault("skill_tree", []).append({"skill": sid, "unlock_level": lvl})
        self.sel = len(self.hero["skill_tree"]) - 1
        self.touch(structural=True)

    def _tree_del(self):
        slots = self.hero.get("skill_tree", [])
        if self.sel is None or self.sel >= len(slots): return
        del slots[self.sel]
        if self.sel >= len(slots): self.sel = len(slots) - 1 if slots else None
        self.touch(structural=True)

    def _bs_add(self):
        sid = self.bs_cb.get()
        if sid in ("", "по умолчанию"): return
        bs = self.hero.setdefault("base_skills", [])
        if sid not in bs: bs.append(sid)
        self.touch(structural=True)

    def _bs_del(self):
        sel = self.bs_lb.curselection()
        bs = self.hero.get("base_skills", [])
        if sel and sel[0] < len(bs): del bs[sel[0]]
        self.touch(structural=True)

    # ---------------------------------------------------------------- герои: новый/копия/удаление
    def new_hero(self):
        cid = simpledialog.askstring("Новый герой", "ID героя (латиницей, например paladin):", parent=self)
        if not cid: return
        cid = cid.strip()
        if not cid or cid in self.chars.get("characters", {}):
            messagebox.showwarning("Герои", "Такой ID уже есть."); return
        self.chars.setdefault("characters", {})[cid] = {"name": cid, "role": "", "description": "",
                                                        "stats": {}, "weapons": [None, None],
                                                        "base_skills": [], "skill_tree": []}
        self.chars.setdefault("order", []).append(cid)
        self.cur = cid; self.touch(structural=True)

    def copy_hero(self):
        if not self.cur: return
        cid = simpledialog.askstring("Копия героя", "ID копии:", parent=self)
        if not cid: return
        cid = cid.strip()
        if not cid or cid in self.chars.get("characters", {}):
            messagebox.showwarning("Герои", "Такой ID уже есть."); return
        self.chars.setdefault("characters", {})[cid] = copy.deepcopy(self.chars["characters"][self.cur])
        self.chars.setdefault("order", []).append(cid)
        self.cur = cid; self.touch(structural=True)

    def delete_hero(self):
        if not self.cur or len(self.order) <= 1:
            messagebox.showwarning("Герои", "Последнего героя удалить нельзя."); return
        if not messagebox.askyesno("Герои", f"Удалить героя «{self.cur}» вместе с деревом навыков?"): return
        self.chars["characters"].pop(self.cur, None)
        if self.cur in self.chars.get("order", []): self.chars["order"].remove(self.cur)
        if self.chars.get("default") == self.cur: self.chars["default"] = self.order[0] if self.order else None
        self.cur = self.order[0] if self.order else None
        self.touch(structural=True)

    # ---------------------------------------------------------------- сохранение / статус
    def touch(self, structural=False):
        if structural:
            self._refresh_list(); self._refresh_tree(keep_sel=True)
        self._refresh_json(); self._refresh_preview(); self._update_status()

    def touch_menu(self):
        self._refresh_preview(); self._update_status()

    def _update_status(self):
        parts = []
        if self.chars_dirty: parts.append("персонажи не сохранены")
        if self.menu_dirty: parts.append("меню не сохранено")
        self.status.set("Есть несохранённые изменения: " + ", ".join(parts) if parts else "Всё сохранено")

    def save(self):
        try:
            CHARS_PATH.write_text(json.dumps(self.chars, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError as e:
            messagebox.showerror("Сохранение", str(e)); return False
        self.chars_saved = self._dump(self.chars); self._update_status()
        self.status.set(f"Сохранено: data/characters.json. В запущенной игре нажми F5.")
        return True

    def save_menu(self):
        try:
            MENU_PATH.write_text(json.dumps(self.menu, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError as e:
            messagebox.showerror("Сохранение", str(e)); return False
        self.menu_saved = self._dump(self.menu); self._update_status()
        self.status.set("Сохранено: assets/skill_menu.json. В запущенной игре нажми F5.")
        return True

    def revert(self):
        self._load_data()
        self.cur = self.order[0] if self.order else None
        self._load_all_forms(); self.touch(structural=True)

    def revert_menu(self):
        try: self.menu = json.loads(MENU_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError): self.menu = {}
        self.menu_saved = self._dump(self.menu)
        for f in self.menu_forms: f.load()
        self.color_form.load(); self.touch_menu()

    def confirm_close(self):
        """True — можно закрывать окно (изменения сохранены или отброшены)."""
        if not self.dirty: return True
        a = messagebox.askyesnocancel("Герои", "Есть несохранённые изменения. Сохранить их перед выходом?")
        if a is None: return False
        if not a: return True
        ok = True
        if self.chars_dirty: ok = self.save()
        if self.menu_dirty and ok: ok = self.save_menu()
        return ok


class _SlotDialog(tk.Toplevel):
    """Диалог «Добавить слот»: навык + уровень открытия."""
    def __init__(self, parent, skills):
        super().__init__(parent); self.title("Новый слот дерева"); self.resizable(False, False)
        self.result = None; self.transient(parent); self.grab_set()
        ttk.Label(self, text="Навык:").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        self.cb = ttk.Combobox(self, values=skills, state="readonly", width=28); self.cb.grid(row=0, column=1, padx=8, pady=6)
        if skills: self.cb.current(0)
        ttk.Label(self, text="Уровень:").grid(row=1, column=0, sticky="w", padx=8, pady=6)
        self.sp = ttk.Spinbox(self, from_=1, to=99, width=6); self.sp.set(1); self.sp.grid(row=1, column=1, sticky="w", padx=8, pady=6)
        row = ttk.Frame(self); row.grid(row=2, column=0, columnspan=2, pady=(2, 8))
        ttk.Button(row, text="Добавить", command=self._ok).pack(side="left", padx=4)
        ttk.Button(row, text="Отмена", command=self.destroy).pack(side="left")
    def _ok(self):
        sid = self.cb.get()
        try: lvl = max(1, int(float(self.sp.get())))
        except ValueError: lvl = 1
        if sid: self.result = (sid, lvl)
        self.destroy()
