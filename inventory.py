"""Инвентарь: рюкзак, руки с оружием и «скелет» со слотами экипировки (клавиша Tab). Открывается у всех героев.

Всё оформление и правила лежат в assets/inventory.json — код трогать не нужно (F5 в игре перечитывает файл).
Нет файла или какого-то поля — берутся значения из DEFAULTS ниже.

Как это работает:
  • у каждого героя есть рюкзак pl.bag — список из bag_size ячеек (id предмета или None). Предмет — это оружие из
    data/weapons.json ИЛИ любой другой id, описанный в assets/inventory.json -> "items" (название, описание, редкость, иконка);
  • у каждого героя есть две «руки» pl.slots = [ЛКМ, ПКМ] — оружие в них бьёт на соответствующую кнопку. Но у некоторых героев кнопка
    занята способностью, и такая рука заблокирована («Занято»): у мага/инженера (spellcaster) и барда занята ЛКМ (заклинания, гитара),
    у Тени (crossbows) заняты обе (арбалеты). Какие руки открыты, решает open_hands(): поле weapon_hands в data/characters.json
    ([ЛКМ, ПКМ], true/false) или, если его нет, класс героя;
  • ПЕРЕНОС ПРЕДМЕТОВ: щелчок ЛКМ по предмету — он «берётся» и следует за курсором, следующий щелчок по ячейке — кладёт его
    (в занятую ячейку — предметы меняются местами). ПКМ или Esc во время переноса — отмена. X — выбросить предмет на пол.
    В любую из двух рук можно положить любое оружие, разрешённое герою (allowed_weapons); оружие может быть и в обеих руках сразу;
  • ПКМ по оружию в рюкзаке (когда ничего не несёшь) — быстро взять его в руку: в свободную, а если заняты обе — в ту, что указана в поле slot в weapons.json (1 — ЛКМ, 2 — ПКМ);
  • подбор с пола (E): предмет уходит в рюкзак (есть свободная открытая рука — оружие сразу в руку, рюкзак полон — для оружия обмен
    с рукой, как раньше); "pickup_mode": "swap" — старое поведение для оружия;
  • перенос — только интерфейс: данные меняются, когда игрок кладёт предмет (в сети это событие уходит хосту);
  • ЭКИПИРОВКА: слева «скелет» с десятью слотами pl.equip = {id слота: id предмета}: голова, шея, левая/правая перчатка, пояс,
    левый/правый ботинок (на своих местах тела) и три мультислота артефактов под скелетом. Слоты, их положение и то, какие
    предметы в них подходят, описаны в assets/inventory.json -> equipment.slots; предмет подходит слоту, если его "type"
    (поле предмета в items) есть в списке accepts слота ("*" — любой не-оружейный предмет). ПКМ по предмету в рюкзаке —
    надеть в подходящий слот (свободный, иначе первый), ПКМ по надетому — снять в рюкзак.
  • АКСЕССУАРЫ (создаются во вкладке «Аксессуары» редактора, accessory_editor.py): у надетого предмета работают поля
    bonuses (max_hp, max_mana, hp_regen — прибавка; damage, move_speed, mana_regen, armor — проценты; сумма — stat()),
    skill (навык выдаётся, пока предмет надет — sync_skills(), выданные так навыки в pl.item_skills) и effect
    (статус-эффект врагу при ударе оружием — hit_effects()). on_equipment_changed() пересчитывает всё при смене экипировки.

Сеть: действия — строки "inv:mv:<откуда>:<куда>", "inv:eq:<ячейка рюкзака>", "inv:ue:<ячейка>", "inv:dr:<ячейка>", где ячейка — "b3" (рюкзак),
"h0" (рука) или "ehead" (слот экипировки по id); их применяет хост (Game.apply_action), рюкзак и экипировка едут в снимке игрока
(ключи "bg" и "eq").
"""
import re
import pygame as pg
from core import CFG, ASSETS, W, VIEW_H, deep_merge, use_char
from anim import sprite
import weapon

DEFAULTS = {
    "enabled": True,
    "bag_size": 12,                 # сколько ячеек в рюкзаке
    "pickup_mode": "bag",           # "bag" — подбор в рюкзак; "swap" — как раньше (сразу обмен с рукой)
    "quick_equip_button": "right",  # "right" — ПКМ по оружию в рюкзаке берёт его в руку; "none" — отключить
    "outside_click": "cancel",      # щелчок мимо окна во время переноса: "cancel" — вернуть на место, "drop" — выбросить на пол
    "drop_key": "X",                # клавиша «выбросить» над ячейкой рюкзака
    "start_items": {"default": [], "knight": ["iron_pike", "short_bow"]},   # что лежит в рюкзаке на старте, по id героя
    "background_image": "", "overlay_color": [5, 5, 14], "overlay_alpha": 170,
    "panel": {"x": 20, "y": 8, "w": 920, "h": 496, "image": "ui/inventory_panel.png", "color": [22, 24, 36], "alpha": 238,
              "border_color": [120, 110, 160], "border_width": 2, "radius": 10},
    "title": "ИНВЕНТАРЬ", "title_size": 28, "title_color": [255, 220, 130], "title_x": 24, "title_y": 14,
    "label_color": [190, 190, 215],
    "bag_label": "РЮКЗАК  {used}/{total}", "bag_label_x": 290, "bag_label_y": 58,
    "hand_label": "В РУКАХ", "hand_label_x": 630, "hand_label_y": 58,
    "bag": {"x": 290, "y": 84, "cell": 72, "gap": 6, "columns": 4},
    "hand": {"x": 630, "y": 84, "cell": 90, "gap": 20},
    "hand_names": ["ЛКМ", "ПКМ"],
    "slot_image": "ui/inventory_slot.png", "hand_slot_image": "ui/inventory_slot_hand.png",
    "slot_color": [34, 38, 56], "slot_border": [88, 84, 120], "slot_hover_border": [255, 230, 150],
    "slot_hover_tint": [255, 255, 255, 26], "slot_corner_radius": 6,
    "valid_border": [110, 220, 130], "invalid_border": [230, 90, 90],   # рамка ячейки под курсором во время переноса
    "hold_alpha": 225, "hold_icon_size": 56,                              # предмет, который несёшь за курсором
    "msg_color": [255, 150, 130],
    "icon_size": 46, "hand_icon_size": 64,
    "show_names": True, "name_color": [225, 225, 240], "hand_key_color": [255, 230, 150],
    "info": {"x": 630, "y": 196, "w": 270, "h": 214, "color": [16, 18, 28], "alpha": 200, "border_color": [88, 84, 120],
             "name_size": 18, "text_color": [200, 200, 220], "stat_color": [150, 205, 255]},
    "show_stats": True,
    "stat_damage": "Урон: {damage}", "stat_combo": "Ударов в серии: {steps}", "stat_mana": "Мана: {mana}", "stat_type": "Тип: {type}",
    "types": {"weapon": "Оружие", "head": "Голова", "neck": "Шея", "glove": "Перчатка", "belt": "Пояс", "boot": "Ботинок", "artifact": "Артефакт"},
    "empty_slot": "Пустой слот", "slot_accepts": "Подходит: {types}",
    "empty_info": "Наведи курсор на предмет",
    "hint": "ЛКМ — взять / положить    ПКМ — надеть / снять    X — выбросить    Tab / Esc — закрыть",
    "hint_holding": "ЛКМ — положить    ПКМ / Esc — отмена    X — выбросить",
    "hint_no_hands": "ЛКМ — взять / положить    X — выбросить    Tab / Esc — закрыть",   # если у героя заняты обе руки (Тень): быстрой экипировки нет
    "locked_label": "Занято", "locked_color": [200, 150, 150],   # надпись на заблокированной руке
    "locked_hint": {"spellcaster": "ЛКМ занята заклинаниями. Оружие можно держать в правой руке (ПКМ).",
                    "bard": "ЛКМ занята игрой на гитаре. Оружие можно держать в правой руке (ПКМ).",
                    "crossbows": "Обе кнопки заняты арбалетами. Оружие в руках использовать нельзя, но его можно носить в рюкзаке.",
                    "default": "Эта рука занята."},
    "hint_x": 290, "hint_y": 466, "hint_color": [160, 220, 175],
    "rarities": {"common": {"name": "Обычное", "color": [170, 170, 185]},
                 "rare": {"name": "Редкое", "color": [90, 160, 255]},
                 "epic": {"name": "Эпическое", "color": [190, 110, 255]},
                 "legendary": {"name": "Легендарное", "color": [255, 170, 60]}},
    "default_rarity": "common",
    "items": {},   # id оружия -> {"description": "...", "rarity": "rare", "icon": "icons/мой_файл.png", "name": "..."}
    "texts": {"bag_full": "Рюкзак полон", "equipped": "{name}", "picked_bag": "+ {name}", "dropped": "Выброшено: {name}",
              "not_for_hero": "{name}: не для этого героя", "hand_locked": "{name}: эта рука занята",
              "not_weapon": "{name}: нельзя взять в руку", "wrong_slot": "{name}: не подходит для этого слота",
              "cannot_equip": "{name}: нельзя надеть"},
    # Экипировка: «скелет» и слоты на нём. Координаты — внутри панели (левый верхний угол слота), size — сторона слота.
    # accepts — какие "type" предметов подходят слоту ("*" — любой не-оружейный предмет). Свои слоты можно добавлять и убирать.
    "equipment": {
        "label": "ЭКИПИРОВКА", "label_x": 30, "label_y": 58,
        "multi_label": "АРТЕФАКТЫ", "multi_label_x": 43, "multi_label_y": 384,
        "model": {"image": "ui/inventory_skeleton.png", "x": 30, "y": 74, "w": 200, "h": 300},
        "slot_image": "", "slot_color": [16, 18, 30], "slot_alpha": 150, "slot_border": [150, 140, 190], "icon_scale": 0.78,
        "slots": [
        {"id": "head", "name": "Голова", "accepts": ["head"], "x": 106, "y": 80, "size": 48},
        {"id": "neck", "name": "Шея", "accepts": ["neck"], "x": 113, "y": 125, "size": 34},
        {"id": "glove_l", "name": "Левая перчатка", "accepts": ["glove"], "x": 39, "y": 259, "size": 42},
        {"id": "glove_r", "name": "Правая перчатка", "accepts": ["glove"], "x": 179, "y": 259, "size": 42},
        {"id": "belt", "name": "Пояс", "accepts": ["belt"], "x": 109, "y": 219, "size": 42},
        {"id": "boot_l", "name": "Левый ботинок", "accepts": ["boot"], "x": 87, "y": 335, "size": 42},
        {"id": "boot_r", "name": "Правый ботинок", "accepts": ["boot"], "x": 131, "y": 335, "size": 42},
        {"id": "art1", "name": "Артефакт 1", "accepts": ["artifact"], "x": 43, "y": 404, "size": 50},
        {"id": "art2", "name": "Артефакт 2", "accepts": ["artifact"], "x": 105, "y": 404, "size": 50},
        {"id": "art3", "name": "Артефакт 3", "accepts": ["artifact"], "x": 167, "y": 404, "size": 50}
        ],
    },
}

_state = {"raw": None, "cfg": None}
_images, _fonts = {}, {}

def cfg():
    """Настройки инвентаря = DEFAULTS + assets/inventory.json (собираются заново после F5)."""
    raw = CFG.get("inventory")
    if _state["cfg"] is None or _state["raw"] is not raw:
        _state["raw"] = raw; _state["cfg"] = deep_merge(DEFAULTS, raw if isinstance(raw, dict) else {})
        _images.clear()
    return _state["cfg"]

def clear_cache(): _images.clear(); _state["cfg"] = None

def uses_weapons(pl):
    """«Классический» герой с оружием (Рыцарь) — не маг/инженер, не бард и не Тень (у тех кнопки атаки заняты способностями)."""
    with use_char(pl.char_id):
        c = CFG.get("character", {})
        return not (c.get("spellcaster") or c.get("crossbows") or c.get("bard"))

def open_hands(pl):
    """[ЛКМ, ПКМ] -> True, если в этой руке можно держать оружие (кнопка атаки не занята способностью героя).
    Поле weapon_hands в data/characters.json ([true, false]) задаёт это явно; иначе: Тень — обе заняты (арбалеты),
    маг/инженер и бард — занята ЛКМ (заклинания / гитара), остальные — обе открыты."""
    with use_char(pl.char_id):
        c = CFG.get("character", {}); wh = c.get("weapon_hands")
        if isinstance(wh, (list, tuple)) and len(wh) >= 2: return [bool(wh[0]), bool(wh[1])]
        if c.get("crossbows"): return [False, False]
        if c.get("spellcaster") or c.get("bard"): return [False, True]
        return [True, True]

def lock_reason(pl):
    """Почему рука занята — текст для окна (assets/inventory.json -> locked_hint)."""
    with use_char(pl.char_id):
        c = CFG.get("character", {})
        key = "default" if isinstance(c.get("weapon_hands"), (list, tuple)) else ("crossbows" if c.get("crossbows") else "spellcaster" if c.get("spellcaster") else "bard" if c.get("bard") else "default")
    hints = cfg().get("locked_hint") or {}
    return hints.get(key, hints.get("default", ""))

def bag(pl):
    """Рюкзак игрока (список ячеек) — всегда нужной длины."""
    b = getattr(pl, "bag", None)
    if b is None: b = pl.bag = []
    n = max(0, int(cfg().get("bag_size", 12)))
    while len(b) < n: b.append(None)
    while len(b) > n and b[-1] is None: b.pop()
    return b

def init(pl):
    """Пустой рюкзак + стартовые предметы героя (start_items в assets/inventory.json). Вызывается из Player.__init__."""
    c = cfg(); pl.bag = [None] * max(0, int(c.get("bag_size", 12))); pl.equip = {}
    if not c.get("enabled", True): return
    items = c.get("start_items") or {}
    wanted = items.get(pl.char_id, items.get("default", []))
    with use_char(pl.char_id):
        for wid in wanted or []:
            if not is_item(wid) or None not in pl.bag: continue
            if wid in CFG["weapons"] and not (any(open_hands(pl)) and pl.can_use(wid)): continue   # оружие — только тем, кому оно разрешено и у кого есть открытая рука
            pl.bag[pl.bag.index(None)] = wid

def is_item(wid):
    """Известен ли такой предмет: оружие из weapons.json или предмет из assets/inventory.json -> items."""
    return isinstance(wid, str) and (wid in CFG["weapons"] or wid in CFG.get("weapons_base", {}) or wid in (cfg().get("items") or {}))

_ID = re.compile(r"^[A-Za-z0-9_]+$")

def slot_defs():
    """Слоты экипировки из assets/inventory.json -> equipment.slots (с неверными id и дубликатами пропускаются)."""
    out, seen = [], set()
    for s in (cfg().get("equipment") or {}).get("slots") or []:
        if isinstance(s, dict) and isinstance(s.get("id"), str) and _ID.match(s["id"]) and s["id"] not in seen: out.append(s); seen.add(s["id"])
    return out

def slot_def(sid):
    return next((s for s in slot_defs() if s["id"] == sid), None)

def equipment(pl):
    """Экипировка игрока: {id слота: id предмета}."""
    e = getattr(pl, "equip", None)
    if not isinstance(e, dict): e = pl.equip = {}
    return e

def equipped_items(pl):
    """[(id слота, id предмета)] надетых вещей — точка расширения: отсюда будущие бонусы и способности."""
    e = equipment(pl); return [(s["id"], e[s["id"]]) for s in slot_defs() if e.get(s["id"])]

def item_bonuses(wid):
    """Поле "bonuses" предмета из assets/inventory.json -> items: {стат: число}."""
    b = (cfg().get("items") or {}).get(wid, {}).get("bonuses")
    return b if isinstance(b, dict) else {}

def stat(pl, key):
    """Сумма бонуса key по всем надетым предметам (max_hp/max_mana/hp_regen — единицы; damage/move_speed/mana_regen/armor — %)."""
    total = 0.0
    for _, wid in equipped_items(pl):
        try: total += float(item_bonuses(wid).get(key, 0) or 0)
        except (TypeError, ValueError): pass
    return total

def stat_mult(pl, key):
    """Множитель от процентного бонуса: +10% -> 1.1 (не ниже 0)."""
    return max(0.0, 1.0 + stat(pl, key) / 100.0)

def hit_effects(pl):
    """Статус-эффекты (поле "effect") надетых предметов — накладываются на врага при ударе оружием."""
    items = cfg().get("items") or {}
    return [e for _, wid in equipped_items(pl) for e in [items.get(wid, {}).get("effect")] if isinstance(e, dict) and e]

BONUS_TEXT = {"max_hp": "+{v} к здоровью", "max_mana": "+{v} к мане", "hp_regen": "+{v} HP/с", "damage": "+{v}% урона",
              "move_speed": "+{v}% скорости", "mana_regen": "+{v}% регена маны", "armor": "+{v}% брони"}
EFFECT_TEXT = {"freeze": "замораживает", "stun": "оглушает", "burn": "поджигает"}

def bonus_lines(wid):
    """Строки подсказки аксессуара: статы, навык, эффект при ударе."""
    o = (cfg().get("items") or {}).get(wid, {}); out = []
    for k, v in item_bonuses(wid).items():
        try: v = float(v)
        except (TypeError, ValueError): continue
        if not v: continue
        txt = BONUS_TEXT.get(k, "+{v} " + k).format(v=("%g" % v))
        out.append(txt.replace("+-", "-"))
    sid = o.get("skill")
    if sid in CFG.get("skills", {}): out.append("Навык: " + str(CFG["skills"][sid].get("name", sid)))
    eff = o.get("effect")
    if isinstance(eff, dict):
        names = [EFFECT_TEXT.get(k, k) for k in eff if k in EFFECT_TEXT]
        if names: out.append("При ударе " + ", ".join(names))
    return out

def sync_skills(pl):
    """Навыки надетых предметов (поле "skill"): выдать недостающие, забрать навыки снятых. pl.item_skills — выданные предметами
    (навык, который герой и так знал, туда не попадает и при снятии не пропадает)."""
    skills = CFG.get("skills", {}); items = cfg().get("items") or {}
    want = []
    for _, wid in equipped_items(pl):
        sid = items.get(wid, {}).get("skill")
        if sid and sid in skills and sid not in want: want.append(sid)
    given = [s for s in getattr(pl, "item_skills", []) if s in pl.skills]
    for sid in given:
        if sid not in want:
            import spells   # сняли предмет посреди каста — остановить каст/поток этого навыка
            if (getattr(pl, "channel", None) or {}).get("sid") == sid: spells.channel_stop(pl, None, "swap")
            if (getattr(pl, "hold", None) or {}).get("sid") == sid: spells.hold_stop(pl, None, "swap")
            pl.skills.remove(sid)
    given = [s for s in given if s in want]
    for sid in want:
        if sid not in pl.skills:
            pl.skills.append(sid); given.append(sid); pl.skill_cooldowns.setdefault(sid, 0.0)
    pl.item_skills = given
    n = len([s for s in pl.skills if skills.get(s, {}).get("category", "active") == "active"])
    pl.skill_index = min(getattr(pl, "skill_index", 0), max(0, n - 1))

def on_equipment_changed(g, pl):
    """Вызывается после любой смены экипировки (надели, сняли, поменяли, выбросили): навыки предметов и запас HP/маны."""
    if not hasattr(pl, "skills"): return
    sync_skills(pl)
    if hasattr(pl, "refresh_mana"): pl.refresh_mana()

def item_type(wid):
    """Тип предмета: "weapon" для оружия, иначе поле "type" из assets/inventory.json -> items (head, neck, glove, belt, boot, artifact...)."""
    if wid in CFG["weapons"]: return "weapon"
    return str((cfg().get("items") or {}).get(wid, {}).get("type", "misc"))

def preferred_hand(pl, wid):
    """В какую руку класть оружие при быстрой экипировке и подборе (только среди открытых рук): сначала «любимая» (поле slot
    в weapons.json: 1 — ЛКМ, 2 — ПКМ), если она занята — другая, если свободна; обе заняты — любимая (её оружие уйдёт в обмен).
    None — если открытых рук нет (у Тени обе кнопки заняты арбалетами)."""
    opened = [n for n, ok in enumerate(open_hands(pl)) if ok]
    if not opened: return None
    pref = max(0, min(1, int(CFG["weapons"][wid].get("slot", 1)) - 1))
    for n in (pref, 1 - pref):
        if n in opened and (n >= len(pl.slots) or pl.slots[n] is None): return n
    return pref if pref in opened else opened[0]

def item_info(wid):
    """Название, редкость, описание и иконка предмета (data/weapons.json + assets/inventory.json -> items)."""
    c = cfg(); w = CFG["weapons"].get(wid, {}); o = (c.get("items") or {}).get(wid, {})
    rid = o.get("rarity", c.get("default_rarity", "common")); rar = c["rarities"].get(rid) or {"name": rid, "color": [170, 170, 185]}
    return {"name": o.get("name", w.get("name", wid)), "rarity": rar.get("name", rid), "color": _col(rar.get("color"), (170, 170, 185)),
            "desc": o.get("description", ""), "icon": o.get("icon") or w.get("icon") or f"icons/{wid}.png"}

# ---------------- ячейки: "b3" — рюкзак, "h0" — рука, "ehead" — слот экипировки ----------------
def parse_cell(tok):
    tok = str(tok)
    if tok.isdigit(): return ("b", int(tok))
    if len(tok) >= 2 and tok[0] in "bh" and tok[1:].isdigit(): return (tok[0], int(tok[1:]))
    if len(tok) >= 2 and tok[0] == "e" and _ID.match(tok[1:]): return ("e", tok[1:])
    return None

def cell_str(cell): return f"{cell[0]}{cell[1]}"

def valid_cell(pl, cell):
    if not cell: return False
    if cell[0] == "b": return 0 <= cell[1] < len(bag(pl))
    if cell[0] == "e": return slot_def(cell[1]) is not None
    return cell[0] == "h" and cell[1] in (0, 1)

def get(pl, cell):
    if not valid_cell(pl, cell): return None
    if cell[0] == "e": return equipment(pl).get(cell[1])
    return bag(pl)[cell[1]] if cell[0] == "b" else (pl.slots[cell[1]] if cell[1] < len(pl.slots) else None)

def put(pl, cell, wid):
    if cell[0] == "b": bag(pl)[cell[1]] = wid
    elif cell[0] == "e":
        if wid is None: equipment(pl).pop(cell[1], None)
        else: equipment(pl)[cell[1]] = wid
    else:
        while len(pl.slots) < 2: pl.slots.append(None)
        pl.slots[cell[1]] = wid

def allowed_in_hand(pl, wid, n):
    """(можно, ключ текста отказа): можно ли положить предмет wid в руку n (любую из двух): это должно быть оружие, разрешённое герою,
    а рука — не занята способностью героя (open_hands)."""
    if wid not in CFG["weapons"]: return False, "not_weapon"
    if not pl.can_use(wid): return False, "not_for_hero"
    if not open_hands(pl)[n]: return False, "hand_locked"
    return True, ""

def allowed_in_slot(pl, wid, sid):
    """(можно, ключ текста отказа): подходит ли предмет wid слоту экипировки sid (по "type" предмета и accepts слота; оружие — никогда)."""
    s = slot_def(sid)
    if s is None or wid in CFG["weapons"]: return False, "wrong_slot"
    acc = s.get("accepts") or []
    if "*" in acc or item_type(wid) in acc: return True, ""
    return False, "wrong_slot"

def fits(pl, wid, cell):
    """(можно, ключ текста отказа): можно ли положить предмет wid в ячейку cell."""
    if cell[0] == "h": return allowed_in_hand(pl, wid, cell[1])
    if cell[0] == "e": return allowed_in_slot(pl, wid, cell[1])
    return True, ""

def check_move(pl, src, dst):
    """(можно, ключ текста отказа, предмет, из-за которого отказ): допустим ли перенос из src в dst."""
    with use_char(pl.char_id):
        if not (valid_cell(pl, src) and valid_cell(pl, dst)) or src == dst: return False, "", None
        a, b = get(pl, src), get(pl, dst)
        if a is None: return False, "", None
        ok, key = fits(pl, a, dst)
        if not ok: return False, key, a
        if b is not None:   # предмет из целевой ячейки встанет в освободившуюся: ему она тоже должна подходить
            ok, key = fits(pl, b, src)
            if not ok: return False, key, b
        return True, "", None

# ---------------- действия (одиночная игра и хост) ----------------
def apply(g, pl, name):
    """Выполнить действие игрока pl: "inv:mv:<откуда>:<куда>", "inv:eq:<ячейка рюкзака>", "inv:ue:<ячейка>" или "inv:dr:<ячейка>"."""
    if not cfg().get("enabled", True) or pl.hp <= 0: return
    parts = str(name).split(":")
    if len(parts) < 3: return
    op, cells = parts[1], [parse_cell(p) for p in parts[2:4]]
    with use_char(pl.char_id):
        if op == "mv" and len(cells) == 2 and all(cells): move(g, pl, cells[0], cells[1])
        elif op == "eq" and cells[0] and cells[0][0] == "b": quick_equip(g, pl, cells[0])
        elif op == "ue" and cells[0] and cells[0][0] in ("e", "h"): quick_unequip(g, pl, cells[0])
        elif op == "dr" and cells[0]: drop(g, pl, cells[0])

def _say(g, pl, key, **kw):
    t = cfg()["texts"].get(key, "")
    if t: g.fx.text(t.format(**kw), pl.cx, pl.y - 10)

def _hands_changed(pl, prefer=None):
    """Рука изменилась: сбросить серию ударов и подправить «последнее оружие» (его скин рисуется в руке)."""
    pl.combo = (None, 0, 0)
    have = [w for w in pl.slots if w]
    if pl.last_weapon not in have: pl.last_weapon = prefer if prefer in have else (have[0] if have else None)

def move(g, pl, src, dst):
    ok, key, bad = check_move(pl, src, dst)
    if not ok:
        if key: _say(g, pl, key, name=item_info(bad)["name"])
        return False
    a, b = get(pl, src), get(pl, dst)
    put(pl, src, b); put(pl, dst, a)   # предметы меняются местами (в пустую ячейку — просто переезжает)
    if "h" in (src[0], dst[0]):
        _hands_changed(pl, a if dst[0] == "h" else None)
    if dst[0] in ("h", "e"): _say(g, pl, "equipped", name=item_info(a)["name"])
    if "e" in (src[0], dst[0]): on_equipment_changed(g, pl)
    return True

def quick_equip(g, pl, cell):
    """ПКМ по предмету в рюкзаке: оружие — в руку, вещь — в подходящий слот экипировки (свободный, иначе первый подходящий)."""
    wid = get(pl, cell)
    if wid is None: return
    if wid not in CFG["weapons"]:
        fit = [s["id"] for s in slot_defs() if allowed_in_slot(pl, wid, s["id"])[0]]
        if not fit: _say(g, pl, "cannot_equip", name=item_info(wid)["name"]); return
        move(g, pl, cell, ("e", next((x for x in fit if equipment(pl).get(x) is None), fit[0]))); return
    h = preferred_hand(pl, wid)
    if h is None: _say(g, pl, "hand_locked", name=item_info(wid)["name"]); return
    move(g, pl, cell, ("h", h))

def quick_unequip(g, pl, cell):
    """ПКМ по надетому предмету или оружию в руке: снять в первую свободную ячейку рюкзака."""
    if get(pl, cell) is None: return
    b = bag(pl)
    if None not in b: _say(g, pl, "bag_full"); return
    move(g, pl, cell, ("b", b.index(None)))

def drop(g, pl, cell):
    wid = get(pl, cell)
    if wid is None: return
    from maps import Drop
    put(pl, cell, None)
    if cell[0] == "h": _hands_changed(pl)
    if cell[0] == "e": on_equipment_changed(g, pl)
    g.room.drops.append(Drop(pl.cx + pl.face * 22, pl.y + pl.h - 14, wid))
    _say(g, pl, "dropped", name=item_info(wid)["name"])

def pickup(g, pl, dr):
    """Подбор предмета с пола (E). True — предмет обработан (забрали в руку/рюкзак или рюкзак полон);
    False — оружие нужно подобрать по-старому (обмен с рукой)."""
    c = cfg()
    if not c.get("enabled", True) or not is_item(dr.wid): return False
    is_weapon = dr.wid in CFG["weapons"]; opened = [n for n, ok in enumerate(open_hands(pl)) if ok]
    if is_weapon and c.get("pickup_mode", "bag") != "bag" and opened: return False   # старый режим: обмен с рукой
    b = bag(pl); name = item_info(dr.wid)["name"]
    if is_weapon and any(pl.slots[n] is None for n in opened if n < len(pl.slots)):   # есть свободная открытая рука — оружие сразу в руку
        pl.slots[preferred_hand(pl, dr.wid)] = dr.wid; _hands_changed(pl, dr.wid); _say(g, pl, "equipped", name=name)
    elif None in b: b[b.index(None)] = dr.wid; _say(g, pl, "picked_bag", name=name)
    elif is_weapon: _say(g, pl, "bag_full"); return False
    else: _say(g, pl, "bag_full"); return True
    if dr in g.room.drops: g.room.drops.remove(dr)
    return True

# ---------------- открытие/закрытие, ввод ----------------
def close(g): g.inv_open = False; g.inv_hold = None

def toggle(g):
    if not cfg().get("enabled", True): return
    if g.inv_open: close(g); return
    if g.pl.hp <= 0 or g.level_menu: return
    g.inv_open = True; g.inv_hold = None; g.inv_msg = None

def held(g):
    """(ячейка, предмет), который сейчас несёт игрок, или (None, None). Если ячейку опустошили — перенос отменяется."""
    h = getattr(g, "inv_hold", None)
    if h and valid_cell(g.pl, h) and get(g.pl, h) is not None: return h, get(g.pl, h)
    g.inv_hold = None; return None, None

def _msg(g, key, wid):
    t = cfg()["texts"].get(key, "")
    if t: g.inv_msg = (t.format(name=item_info(wid)["name"]), pg.time.get_ticks() + 2200)

def key(g, k):
    """Клавиши при открытом инвентаре: Tab — закрыть, Esc — отменить перенос / закрыть, drop_key — выбросить предмет."""
    try: toggle_key = pg.key.key_code(str(g.controls().get("inventory", "TAB")))
    except (ValueError, TypeError): toggle_key = pg.K_TAB
    cell, wid = held(g)
    if k == toggle_key: close(g); return
    if k == pg.K_ESCAPE:
        if cell: g.inv_hold = None
        else: close(g)
        return
    try: drop_key = pg.key.key_code(str(cfg().get("drop_key", "X")))
    except (ValueError, TypeError): drop_key = pg.K_x
    if k == drop_key:
        if cell: g.act(f"inv:dr:{cell_str(cell)}"); g.inv_hold = None
        else:
            under = cell_at(g.pl, pg.mouse.get_pos())
            if under and get(g.pl, under) is not None: g.act(f"inv:dr:{cell_str(under)}")

def event(g, e):
    """Мышь при открытом инвентаре: ЛКМ берёт предмет / кладёт его в ячейку, ПКМ — отмена или быстрая экипировка."""
    if e.type != pg.MOUSEBUTTONDOWN or g.level_menu or e.button not in (1, 3): return
    pl, c = g.pl, cfg(); under = cell_at(pl, e.pos); src, wid = held(g)
    if e.button == 3:
        if src: g.inv_hold = None
        elif under and get(pl, under) is not None and c.get("quick_equip_button", "right") == "right":
            g.act(f"inv:eq:{under[1]}" if under[0] == "b" else f"inv:ue:{cell_str(under)}")   # из рюкзака — надеть, из руки / слота — снять в рюкзак
        return
    if src is None:   # ничего не несём: берём предмет под курсором
        if under and get(pl, under) is not None: g.inv_hold = under
        return
    if under is None:
        if not layout(pl)["panel"].collidepoint(e.pos):   # щелчок мимо окна
            if c.get("outside_click", "cancel") == "drop": g.act(f"inv:dr:{cell_str(src)}")
            g.inv_hold = None
        return
    if under == src: g.inv_hold = None; return   # положили туда же
    ok, key_, bad = check_move(pl, src, under)
    if not ok:
        if key_: _msg(g, key_, bad)
        return
    g.act(f"inv:mv:{cell_str(src)}:{cell_str(under)}"); g.inv_hold = None

def floor_icon(v, wid, x, y, box=32):
    """Иконка предмета на полу (для Drop не-оружия). False — картинки нет."""
    img = _icon(wid, box)
    if img: v.blit(img, img.get_rect(center=(int(x), int(y)))); return True
    return False

# ---------------- раскладка и рисование ----------------
def _col(v, default):
    try: return tuple(max(0, min(255, int(x))) for x in v[:3])
    except (TypeError, ValueError, IndexError): return default

def _font(size):
    if size not in _fonts: _fonts[size] = pg.font.SysFont("arial,dejavusans,freesans", int(size), bold=True)
    return _fonts[size]

def _image(path, w, h, fit=False):
    """Картинка из assets, масштабированная до w×h (fit — вписать с сохранением пропорций). Нет файла — None."""
    if not path: return None
    key = (str(path), int(w), int(h), fit)
    if key not in _images:
        try:
            img = pg.image.load(str(ASSETS / str(path))).convert_alpha(); iw, ih = img.get_size()
            if fit: k = min(w / iw, h / ih); w, h = max(1, round(iw * k)), max(1, round(ih * k))
            _images[key] = pg.transform.smoothscale(img, (int(w), int(h)))
        except (OSError, pg.error): _images[key] = None
    return _images[key]

def _icon(wid, size):
    """Картинка предмета, вписанная в size×size: иконка из конфига/weapons.json, иначе скин оружия. Нет ничего — None."""
    img = _image(item_info(wid)["icon"], size, size, True)
    if img: return img
    if wid in CFG["weapons"]:
        path, dw, dh, _ = weapon.info(wid); k = size / max(dw, dh)
        return sprite(path, max(1, round(dw * k)), max(1, round(dh * k)))
    return None

def layout(pl):
    """Прямоугольники инвентаря на экране: панель, ячейки рюкзака, две руки, блок описания, слоты экипировки и «скелет»."""
    c = cfg(); p, b, h, i = c["panel"], c["bag"], c["hand"], c["info"]
    panel = pg.Rect(int(p["x"]), int(p["y"]), int(p["w"]), int(p["h"]))
    cell, gap, cols = int(b["cell"]), int(b["gap"]), max(1, int(b["columns"]))
    cells = [pg.Rect(panel.x + int(b["x"]) + (n % cols) * (cell + gap), panel.y + int(b["y"]) + (n // cols) * (cell + gap), cell, cell) for n in range(len(bag(pl)))]
    hc, hg = int(h["cell"]), int(h["gap"])
    hands = [pg.Rect(panel.x + int(h["x"]) + n * (hc + hg), panel.y + int(h["y"]), hc, hc) for n in range(2)]
    info = pg.Rect(panel.x + int(i["x"]), panel.y + int(i["y"]), int(i["w"]), int(i["h"]))
    eq = c.get("equipment") or {}; m = eq.get("model") or {}
    equip = [(s["id"], pg.Rect(panel.x + int(s.get("x", 0)), panel.y + int(s.get("y", 0)), int(s.get("size", 44)), int(s.get("size", 44)))) for s in slot_defs()]
    model = pg.Rect(panel.x + int(m.get("x", 30)), panel.y + int(m.get("y", 74)), int(m.get("w", 200)), int(m.get("h", 300)))
    return {"panel": panel, "bag": cells, "hand": hands, "info": info, "equip": equip, "model": model}

def cell_at(pl, pos):
    """Ячейка под точкой pos: ("b", номер) / ("h", 0|1) / ("e", id слота) / None."""
    L = layout(pl)
    for kind, tag in (("bag", "b"), ("hand", "h")):
        for n, r in enumerate(L[kind]):
            if r.collidepoint(pos): return (tag, n)
    for sid, r in L["equip"]:
        if r.collidepoint(pos): return ("e", sid)
    return None

def _wrap(text, font, width):
    out = []
    for para in str(text).split("\n"):
        cur = ""
        for word in para.split():
            t = (cur + " " + word).strip()
            if font.size(t)[0] <= width or not cur: cur = t
            else: out.append(cur); cur = word
        out.append(cur)
    return out

def _fit(text, font, width):
    if font.size(text)[0] <= width: return text
    while text and font.size(text + "…")[0] > width: text = text[:-1]
    return text + "…"

def _draw_item(scr, wid, rect, size, small, show_name):
    c = cfg(); inf = item_info(wid); cy = rect.centery - (6 if show_name else 0)
    img = _icon(wid, int(size))
    if img: scr.blit(img, img.get_rect(center=(rect.centerx, cy)))
    else: pg.draw.polygon(scr, inf["color"], [(rect.centerx, cy - 10), (rect.centerx + 10, cy), (rect.centerx, cy + 10), (rect.centerx - 10, cy)])
    if show_name:
        t = small.render(_fit(inf["name"], small, rect.w - 6), True, _col(c.get("name_color"), (225, 225, 240)))
        scr.blit(t, (rect.centerx - t.get_width() // 2, rect.bottom - t.get_height() - 3))

def _draw_slot(scr, rect, img_path, border=None, hover=False, item_color=None):
    """Ячейка: фон, рамка цвета редкости, подсветка под курсором (border — цвет рамки подсветки)."""
    c = cfg(); rad = int(c.get("slot_corner_radius", 6))
    img = _image(img_path, rect.w, rect.h)
    if img: scr.blit(img, rect)
    else:
        pg.draw.rect(scr, _col(c.get("slot_color"), (34, 38, 56)), rect, border_radius=rad)
        pg.draw.rect(scr, _col(c.get("slot_border"), (88, 84, 120)), rect, 2, border_radius=rad)
    if item_color: pg.draw.rect(scr, item_color, rect, 2, border_radius=rad)   # рамка цвета редкости
    if hover: _draw_hover(scr, rect, border)

def _draw_hover(scr, rect, border=None):
    """Подсветка ячейки под курсором (border — цвет рамки; при переносе: зелёный — можно, красный — нельзя)."""
    c = cfg(); rad = int(c.get("slot_corner_radius", 6))
    tint = c.get("slot_hover_tint", [255, 255, 255, 26]); veil = pg.Surface(rect.size, pg.SRCALPHA)
    pg.draw.rect(veil, (*_col(tint, (255, 255, 255)), int(tint[3]) if len(tint) > 3 else 26), veil.get_rect(), border_radius=rad); scr.blit(veil, rect)
    pg.draw.rect(scr, border or _col(c.get("slot_hover_border"), (255, 230, 150)), rect, 2, border_radius=rad)

def _draw_equip_slot(scr, rect, wid, hover=False, border=None, hint=None):
    """Слот экипировки на «скелете»: полупрозрачный, чтобы кости были видны; hint — цвет тонкой рамки «сюда можно положить»."""
    c = cfg(); E = c.get("equipment") or {}; rad = int(c.get("slot_corner_radius", 6))
    img = _image(E.get("slot_image"), rect.w, rect.h)
    if img: scr.blit(img, rect)
    else:
        s = pg.Surface(rect.size, pg.SRCALPHA); pg.draw.rect(s, (*_col(E.get("slot_color"), (16, 18, 30)), int(E.get("slot_alpha", 150))), s.get_rect(), border_radius=rad); scr.blit(s, rect)
        pg.draw.rect(scr, _col(E.get("slot_border"), (150, 140, 190)), rect, 2, border_radius=rad)
    if wid:
        inf = item_info(wid); size = max(8, int(rect.w * float(E.get("icon_scale", 0.78)))); img = _icon(wid, size)
        if img: scr.blit(img, img.get_rect(center=rect.center))
        else: pg.draw.polygon(scr, inf["color"], [(rect.centerx, rect.centery - 9), (rect.centerx + 9, rect.centery), (rect.centerx, rect.centery + 9), (rect.centerx - 9, rect.centery)])
        pg.draw.rect(scr, inf["color"], rect, 2, border_radius=rad)
    if hint: pg.draw.rect(scr, hint, rect.inflate(4, 4), 1, border_radius=rad + 2)
    if hover: _draw_hover(scr, rect, border)

def draw(g):
    """Окно инвентаря поверх игры (вызывается из Game.draw, пока g.inv_open)."""
    c = cfg(); scr, pl = g.scr, g.pl
    with use_char(pl.char_id):
        bg = _image(c.get("background_image"), W, VIEW_H)
        if bg: scr.blit(bg, (0, 0))
        else:
            veil = pg.Surface((W, VIEW_H), pg.SRCALPHA); veil.fill((*_col(c.get("overlay_color"), (5, 5, 14)), max(0, min(255, int(c.get("overlay_alpha", 170)))))); scr.blit(veil, (0, 0))
        L = layout(pl); P = c["panel"]; panel = L["panel"]
        pimg = _image(P.get("image"), panel.w, panel.h)
        if pimg: scr.blit(pimg, panel)
        else:
            s = pg.Surface(panel.size, pg.SRCALPHA); pg.draw.rect(s, (*_col(P.get("color"), (22, 24, 36)), int(P.get("alpha", 238))), s.get_rect(), border_radius=int(P.get("radius", 10))); scr.blit(s, panel)
            pg.draw.rect(scr, _col(P.get("border_color"), (120, 110, 160)), panel, int(P.get("border_width", 2)), border_radius=int(P.get("radius", 10)))
        font, small = g.font, g.small; items = bag(pl); mouse = pg.mouse.get_pos()
        t = _font(c.get("title_size", 28)).render(str(c.get("title", "")), True, _col(c.get("title_color"), (255, 220, 130))); scr.blit(t, (panel.x + int(c.get("title_x", 24)), panel.y + int(c.get("title_y", 14))))
        lc = _col(c.get("label_color"), (190, 190, 215))
        scr.blit(font.render(str(c.get("bag_label", "")).format(used=sum(1 for w in items if w), total=len(items)), True, lc), (panel.x + int(c.get("bag_label_x", 36)), panel.y + int(c.get("bag_label_y", 58))))
        opened = open_hands(pl)
        scr.blit(font.render(str(c.get("hand_label", "")), True, lc), (panel.x + int(c.get("hand_label_x", 630)), panel.y + int(c.get("hand_label_y", 58))))
        E = c.get("equipment") or {}
        for key_, kx, ky in (("label", "label_x", "label_y"), ("multi_label", "multi_label_x", "multi_label_y")):
            if E.get(key_): scr.blit(font.render(str(E[key_]), True, lc), (panel.x + int(E.get(kx, 30)), panel.y + int(E.get(ky, 58))))
        mimg = _image((E.get("model") or {}).get("image"), L["model"].w, L["model"].h, True)   # «скелет»
        if mimg: scr.blit(mimg, mimg.get_rect(center=L["model"].center))
        under = cell_at(pl, mouse); src, hwid = held(g); show_names = bool(c.get("show_names", True))
        verdict = None   # во время переноса: можно ли положить сюда (цвет рамки под курсором)
        if src and under and under != src: verdict = _col(c.get("valid_border") if check_move(pl, src, under)[0] else c.get("invalid_border"), (230, 90, 90))
        def cell_view(cell, rect, slot_img, size):
            wid = get(pl, cell)
            if wid is not None and not is_item(wid): wid = None
            carried = cell == src
            _draw_slot(scr, rect, slot_img, verdict if (cell == under and verdict) else None, cell == under, item_info(wid)["color"] if wid and not carried else None)
            if wid and not carried: _draw_item(scr, wid, rect, size, small, show_names)
        for n, r in enumerate(L["bag"]): cell_view(("b", n), r, c.get("slot_image"), c.get("icon_size", 52))
        names = c.get("hand_names", ["ЛКМ", "ПКМ"])
        for n, r in enumerate(L["hand"]):
            cell_view(("h", n), r, c.get("hand_slot_image") or c.get("slot_image"), c.get("hand_icon_size", 70))
            k = font.render(str(names[n]) if n < len(names) else str(n + 1), True, _col(c.get("hand_key_color"), (255, 230, 150))); scr.blit(k, (r.x + 6, r.y + 4))
            if not opened[n]:   # рука занята способностью героя: затемнить и подписать
                veil = pg.Surface(r.size, pg.SRCALPHA); pg.draw.rect(veil, (8, 8, 16, 165), veil.get_rect(), border_radius=int(c.get("slot_corner_radius", 6))); scr.blit(veil, r)
                lt = font.render(str(c.get("locked_label", "")), True, _col(c.get("locked_color"), (200, 150, 150))); scr.blit(lt, lt.get_rect(center=r.center))
        # слоты экипировки на «скелете» (рисуются поверх него)
        for sid, r in L["equip"]:
            cell = ("e", sid); wid = get(pl, cell); wid = wid if is_item(wid) and cell != src else None
            ok_here = bool(src) and cell != src and check_move(pl, src, cell)[0]   # во время переноса подсвечиваем подходящие слоты
            _draw_equip_slot(scr, r, wid, cell == under, verdict if (cell == under and verdict) else None, _col(c.get("valid_border"), (110, 220, 130)) if ok_here and cell != under else None)
        # описание предмета под курсором (или того, что несём)
        I = c["info"]; ir = L["info"]; sh = pg.Surface(ir.size, pg.SRCALPHA)
        pg.draw.rect(sh, (*_col(I.get("color"), (16, 18, 28)), int(I.get("alpha", 200))), sh.get_rect(), border_radius=6); scr.blit(sh, ir)
        pg.draw.rect(scr, _col(I.get("border_color"), (88, 84, 120)), ir, 1, border_radius=6)
        hw = get(pl, under) if under else None
        if hw is None or not is_item(hw): hw = hwid
        tc, sc = _col(I.get("text_color"), (200, 200, 220)), _col(I.get("stat_color"), (150, 205, 255)); x, y = ir.x + 10, ir.y + 8
        if under and under[0] == "h" and not opened[under[1]]:   # курсор над заблокированной рукой — объясняем почему
            for line in _wrap(lock_reason(pl), small, ir.w - 20): scr.blit(small.render(line, True, _col(c.get("locked_color"), (200, 150, 150))), (x, y)); y += small.get_height() + 2
        elif hw is None and under and under[0] == "e":   # пустой слот экипировки: название и что в него можно положить
            sd = slot_def(under[1]) or {}; types = c.get("types") or {}; acc = sd.get("accepts") or []
            scr.blit(_font(I.get("name_size", 18)).render(str(sd.get("name", under[1])), True, lc), (x, y)); y += 26
            scr.blit(small.render(str(c.get("empty_slot", "")), True, tc), (x, y)); y += small.get_height() + 4
            tn = ", ".join(str(types.get(a, a)) for a in acc if a != "*") or "любые предметы"
            for line in _wrap(str(c.get("slot_accepts", "")).format(types=tn), small, ir.w - 20): scr.blit(small.render(line, True, sc), (x, y)); y += small.get_height() + 2
        elif hw is None: scr.blit(small.render(str(c.get("empty_info", "")), True, tc), (x, y))
        else:
            inf = item_info(hw); w = CFG["weapons"].get(hw)
            nm = _font(I.get("name_size", 18)).render(inf["name"], True, inf["color"]); scr.blit(nm, (x, y)); y += nm.get_height() + 2
            scr.blit(small.render(inf["rarity"], True, inf["color"]), (x, y)); y += small.get_height() + 6
            if w and c.get("show_stats", True):   # характеристики — только у оружия
                step = w["combo"][0] if w.get("combo") else {}
                for tpl, val in ((c.get("stat_damage"), {"damage": step.get("damage", "-")}), (c.get("stat_combo"), {"steps": len(w.get("combo", []))}),
                                 (c.get("stat_mana"), {"mana": weapon.mana_cost(hw, step)})):
                    if tpl: scr.blit(small.render(str(tpl).format(**val), True, sc), (x, y)); y += small.get_height() + 2
                y += 4
            elif not w and c.get("show_stats", True) and c.get("stat_type") and item_type(hw) != "misc":   # у вещей — тип (Шлем, Артефакт ...)
                tn = (c.get("types") or {}).get(item_type(hw), item_type(hw)); scr.blit(small.render(str(c["stat_type"]).format(type=tn), True, sc), (x, y)); y += small.get_height() + 6
            if not w:   # аксессуар: статы, навык и эффект — зелёными строками перед описанием
                for line in bonus_lines(hw):
                    scr.blit(small.render(_fit(line, small, ir.w - 20), True, _col(c.get("bonus_color"), (140, 230, 150))), (x, y)); y += small.get_height() + 1
            for line in _wrap(inf["desc"], small, ir.w - 20):
                if y > ir.bottom - small.get_height() - 4: break
                scr.blit(small.render(line, True, tc), (x, y)); y += small.get_height() + 1
        # подсказка / сообщение об отказе
        msg = getattr(g, "inv_msg", None)
        if msg and pg.time.get_ticks() < msg[1]: scr.blit(small.render(msg[0], True, _col(c.get("msg_color"), (255, 150, 130))), (panel.x + int(c.get("hint_x", 290)), panel.y + int(c.get("hint_y", 466)) - 18))
        hint = c.get("hint_holding") if src else (c.get("hint") if any(opened) else c.get("hint_no_hands"))
        if hint: scr.blit(small.render(str(hint), True, _col(c.get("hint_color"), (160, 220, 175))), (panel.x + int(c.get("hint_x", 290)), panel.y + int(c.get("hint_y", 466))))
        if src:   # предмет «в руке» следует за курсором
            img = _icon(hwid, int(c.get("hold_icon_size", 56)))
            if img: img = img.copy(); img.set_alpha(int(c.get("hold_alpha", 225))); scr.blit(img, img.get_rect(center=mouse))
            else: pg.draw.polygon(scr, item_info(hwid)["color"], [(mouse[0], mouse[1] - 12), (mouse[0] + 12, mouse[1]), (mouse[0], mouse[1] + 12), (mouse[0] - 12, mouse[1])])
