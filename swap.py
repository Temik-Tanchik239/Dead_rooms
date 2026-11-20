"""swap.py — смена героя посреди забега (экран «ВЫБОР ПЕРСОНАЖА» поверх паузы).

Забег хранит состояние КАЖДОГО героя, который в нём побывал: g.heroes = {char_id: снапшот}
(JSON-сериализуемый, формат — save_io.snapshot_player). Пример: начали за барда, нашли 3 оружия,
переключились на инженера, нашли шлем — в g.heroes лежат и оружие барда, и шлем инженера.

ПОРЯДОК СМЕНЫ (критичен, см. switch):
  1) снапшот СТАРОГО героя — ДО apply_character (apply_character перетирает CFG["player"]/["skills"]...);
  2) apply_character(новый) + anim.clear_cache() + inventory.clear_cache() + SETTINGS["last_character"];
  3) НОВЫЙ Player() — его __init__ сам зовёт crossbow.init/bard.init/inventory.init (свежие подсистемы);
  4) restore_player(новый pl, g.heroes[cid]) — вернуть личное состояние героя забега (позицию НЕ брать);
  5) поставить героя на место старого: центр по X и ноги по Y, в границах комнаты, на пол.

Интеграция (делает главный агент в main.py):
  new_game:   swap.init(g)   — создать g.heroes и записать стартового героя;
  key():      if s.menu_mode == "swap": swap.menu_key(s, k); return
  event():    if s.menu_mode == "swap": swap.menu_event(s, e); return
  draw_menu():if s.menu_mode == "swap": swap.draw_menu(s); s.draw_cursor(); return
  вызов:      swap.switch_open(g) — кнопка паузы/клавиша (в сети сама откажется).
"""
import pygame as pg
from core import SETTINGS, CHAR, MW, T, W, VIEW_H, apply_character, char_def, char_ids, floor_below, free
from anim import clear_cache
import inventory
import characters as char_menu

MODE = "swap"           # значение g.menu_mode, пока экран открыт (main ставит sim=0 сам)

CARD_W, CARD_H, CARD_GAP, PANEL_PAD = 150, 204, 12, 20
PANEL_H = 54 + CARD_H + 42   # заголовок + карточки + подсказка


# ---------- хранилище героев забега ----------

def init(g):
    """Создать хранилище героев забега: g.heroes = {char_id: снапшот}. Зовёт main.new_game.
    Стартовый герой (его pl уже создан) сразу регистрируется."""
    g.heroes = {}
    g.swap_index = 0
    register(g)


def register(g):
    """Записать снапшот ТЕКУЩЕГО героя в g.heroes (остальные записи не трогаем).
    Безопасно в любой момент забега: ошибка снапшота не роняет игру."""
    heroes = getattr(g, "heroes", None)
    if not isinstance(heroes, dict): heroes = g.heroes = {}
    pl = getattr(g, "pl", None)
    cid = getattr(pl, "char_id", None) or CHAR["id"]
    if pl is None or not cid: return
    try: heroes[cid] = snapshot_player(pl)
    except Exception as e: print("[swap] не удалось записать героя", cid, ":", e)


# ---------- снапшот/восстановление: живёт в save_io.py (его пишет параллельный агент) ----------

def snapshot_player(pl):
    """JSON-сериализуемый снапшот героя. Делегирует в save_io.snapshot_player (ленивый импорт —
    save_io пишет параллельный агент; пока его нет — временный встроенный снапшот ниже)."""
    try: from save_io import snapshot_player as snap
    except ImportError: return _fallback_snapshot(pl)
    return snap(pl)


def restore_player(pl, snap):
    """Вернуть герою его состояние из снапшота (объект pl уже создан). Делегирует в save_io."""
    try: from save_io import restore_player as restore
    except ImportError: _fallback_restore(pl, snap); return
    restore(pl, snap)


def _fallback_snapshot(pl):
    """ВРЕМЕННЫЙ снапшот (только пока save_io.py не написан): базовые поля героя, достаточно для смены."""
    return {
        "char": getattr(pl, "char_id", None),
        "hp": pl.hp, "maxhp": pl.maxhp, "mana": pl.mana, "maxmana": pl.maxmana,
        "level": pl.level, "xp": pl.xp, "xp_next": pl.xp_next,
        "skills": list(getattr(pl, "skills", [])), "item_skills": list(getattr(pl, "item_skills", [])),
        "skill_index": getattr(pl, "skill_index", 0), "skill_cooldowns": dict(getattr(pl, "skill_cooldowns", {}) or {}),
        "slots": list(getattr(pl, "slots", [None, None])), "bag": list(getattr(pl, "bag", []) or []),
        "equip": dict(getattr(pl, "equip", {}) or {}), "resources": dict(getattr(pl, "resources", {}) or {}),
        "last_weapon": getattr(pl, "last_weapon", None), "goggles": bool(getattr(pl, "goggles", False)),
        "hold_pool": dict(getattr(pl, "hold_pool", {}) or {}), "hold_rest": dict(getattr(pl, "hold_rest", {}) or {}),
        "xb_ammo": list(getattr(pl, "xb_ammo", []) or []), "xb_cd": list(getattr(pl, "xb_cd", []) or []),
        "bd_note": getattr(pl, "bd_note", 0),
    }


def _fallback_restore(pl, snap):
    """ВРЕМЕННОЕ восстановление (пока нет save_io.py). Порядок: уровни/навыки -> инвентарь/экипировка ->
    пересчёт бонусов предметов -> hp/мана -> индекс заклинания."""
    if not isinstance(snap, dict): return
    from core import CFG
    pl.level = max(1, int(snap.get("level") or 1))
    pl.xp = max(0.0, float(snap.get("xp") or 0.0)); pl.xp_next = max(1.0, float(snap.get("xp_next") or 100))
    known = CFG.get("skills", {})
    pl.skills = [sid for sid in (snap.get("skills") or []) if sid in known]
    pl.item_skills = [sid for sid in (snap.get("item_skills") or []) if sid in known]
    slots = snap.get("slots")
    if isinstance(slots, list): pl.slots = list(slots)[:2]
    bag = snap.get("bag")
    if isinstance(bag, list): pl.bag = list(bag)
    eq = snap.get("equip"); pl.equip = dict(eq) if isinstance(eq, dict) else {}
    res = snap.get("resources"); pl.resources = dict(res) if isinstance(res, dict) else {}
    if "last_weapon" in snap: pl.last_weapon = snap.get("last_weapon")
    pl.goggles = bool(snap.get("goggles"))
    for key in ("hold_pool", "hold_rest"):
        d = snap.get(key)
        if isinstance(d, dict): setattr(pl, key, dict(d))
    for key in ("xb_ammo", "xb_cd"):
        v = snap.get(key)
        if isinstance(v, list) and len(v) == len(getattr(pl, key, []) or []):
            setattr(pl, key, [float(x) for x in v] if key == "xb_cd" else list(v))
    if hasattr(pl, "bd_note"):
        try: pl.bd_note = int(snap.get("bd_note", pl.bd_note))
        except (TypeError, ValueError): pass
    cds = snap.get("skill_cooldowns")
    if isinstance(cds, dict):
        for sid, v in cds.items():
            try: pl.skill_cooldowns[sid] = float(v)
            except (TypeError, ValueError): pass
    for sid in pl.skills: pl.skill_cooldowns.setdefault(sid, 0.0)
    try: inventory.on_equipment_changed(None, pl)   # навыки предметов + пересчёт max HP/маны от аксессуаров
    except Exception: pass
    # hp/мана — ПОСЛЕ пересчёта максимумов (в снапшоте уже значения с бонусами этого героя)
    hp, maxhp = snap.get("hp"), snap.get("maxhp")
    if isinstance(maxhp, (int, float)) and maxhp > 0: pl.maxhp = maxhp
    if isinstance(hp, (int, float)): pl.hp = max(0.0, min(pl.maxhp, hp))
    mn, mx = snap.get("mana"), snap.get("maxmana")
    if isinstance(mx, (int, float)) and mx > 0: pl.maxmana = mx
    if isinstance(mn, (int, float)): pl.mana = max(0.0, min(pl.maxmana, mn))
    try:   # индекс заклинания — в границах книги этого героя
        from spells import active_skills
        act = active_skills(pl)
        if act and not 0 <= int(getattr(pl, "skill_index", 0)) < len(act): pl.skill_index = 0
    except Exception: pass


# ---------- экран смены героя ----------

def switch_open(g):
    """Открыть экран «ВЫБОР ПЕРСОНАЖА» (g.menu_mode = "swap" — main ставит sim=0 сам)."""
    if getattr(g, "net", None):
        pl = getattr(g, "pl", None)
        if pl is not None: g.fx.text("Недоступно в сетевой игре", pl.cx, pl.y - 40)
        return
    ids = char_ids()
    if not ids: return
    register(g)   # зафиксировать текущее состояние героя, пока экран открыт
    cur = getattr(getattr(g, "pl", None), "char_id", None) or CHAR["id"]
    g.swap_index = ids.index(cur) if cur in ids else 0
    g.menu_mode = MODE


def menu_key(g, k):
    """Esc — отмена; стрелки/W-S и цифры — выбор; Enter/пробел — сменить героя."""
    if k == pg.K_ESCAPE:
        g.menu_mode = "pause"; return   # экран смены открыт из паузы — Esc возвращает в неё
    ids = char_ids()
    if not ids: return
    i = int(getattr(g, "swap_index", 0)) % len(ids)
    if k in (pg.K_LEFT, pg.K_a, pg.K_UP, pg.K_w): g.swap_index = (i - 1) % len(ids)
    elif k in (pg.K_RIGHT, pg.K_d, pg.K_DOWN, pg.K_s): g.swap_index = (i + 1) % len(ids)
    elif pg.K_1 <= k <= pg.K_9 and k - pg.K_1 < len(ids): g.swap_index = k - pg.K_1
    elif k in (pg.K_RETURN, pg.K_KP_ENTER, pg.K_SPACE): switch(g, ids[i])


def menu_event(g, e):
    """Клик по карточке героя — сменить."""
    if e.type != pg.MOUSEBUTTONDOWN or e.button != 1: return
    for cid, r in _card_layout()[1].items():
        if r.collidepoint(e.pos): switch(g, cid); return


# ---------- сама смена ----------

def switch(g, cid):
    """Сменить героя забега на cid. Порядок критичен: снапшот ДО apply_character,
    новый Player ПОСЛЕ (иначе apply_character перетрёт поля героя)."""
    if getattr(g, "net", None):
        pl = getattr(g, "pl", None)
        if pl is not None: g.fx.text("Недоступно в сетевой игре", pl.cx, pl.y - 40)
        return
    if cid not in char_ids(): return
    old = getattr(g, "pl", None)
    old_id = getattr(old, "char_id", None) or CHAR["id"]
    register(g)                  # 1) снапшот СТАРОГО героя — до каких-либо переключений CFG
    g.menu_mode = None           # экран закрыт при любом исходе
    if old is None or cid == old_id: return
    cx, feet = old.cx, old.y + old.h   # 2) позиция старого героя (НЕ из снапшота)
    try:
        import crafting
        crafting.cancel(g)       # крафт/установка турели остаются «прошлой жизни» (ресурсы падают на пол)
    except Exception: pass
    if getattr(g, "inv_open", False): g.inv_open = False; g.inv_hold = None
    apply_character(cid)         # 3) CFG на нового героя
    clear_cache()                #    картинки старого героя больше не нужны
    inventory.clear_cache()
    SETTINGS["last_character"] = cid
    g.save_settings()
    new = g.Player()             # 4) свежий герой: crossbow/bard/inventory init уже внутри __init__
    if cid in (getattr(g, "heroes", None) or {}):
        restore_player(new, g.heroes[cid])   # 5) его личное состояние забега (позицию не трогает)
    _reset_transient(new)        # 6) боевые «хвосты» не переносим
    g.pl = new
    _place(g, new, cx, feet)     # 7) на место старого: центр/ноги, в границах комнаты, на пол
    register(g)                  # 8) новый герой сразу в хранилище забега (иначе сейв его потеряет)
    g.fx.text(f"Вы играете за {char_def(cid).get('name', cid)}", new.cx, new.y - 26)


def _reset_transient(pl):
    """Временное состояние не переходит между героями: атаки, колдуния, клоны, захват."""
    pl.atk = None
    pl.channel = None            # удерживаемое заклинание не переходит
    pl.hold = None               # «поток» не переходит (запас hold_pool — личный, его вернул restore)
    pl.hold_latch = False
    pl.grab = None
    pl.clones = []               # атрибут пересоздаётся заново (Player.__init__ его не создаёт)
    pl.skill_held = False
    pl.move_input = False


def _place(g, pl, cx, feet):
    """Поставить героя: центр по X и ноги по Y — как у старого героя, x зажат в границы комнаты.
    Если новый хитбокс не влезает (стены) — пол под ногами, затем соседние клетки; крайний случай —
    штатная точка появления комнаты (Game.place, как при respawn)."""
    pl.vx = pl.vy = 0.0
    room = getattr(g, "room", None)
    if room is None:
        pl.x, pl.y = cx - pl.w / 2, feet - pl.h; return
    wpx = max(pl.w, room.width_px)
    pl.x = max(0.0, min(wpx - pl.w, cx - pl.w / 2.0)); pl.y = feet - pl.h
    grid = room.g
    if free(grid, pl.rect): return
    fy = floor_below(grid, pl.cx, max(0, pl.y - T))   # пол под ногами в этой же колонке
    if fy is not None:
        pl.y = fy - pl.h
        if free(grid, pl.rect): return
    for dx in (0, -T, T, -2 * T, 2 * T, -3 * T, 3 * T):   # соседние клетки вокруг прежнего места
        x = max(0.0, min(wpx - pl.w, cx - pl.w / 2.0 + dx))
        for dy in (0, -T, T, -2 * T):
            cand = pg.Rect(int(x), int(feet - pl.h) + dy, pl.w, pl.h)
            if free(grid, cand): pl.x, pl.y = float(cand.x), float(cand.y); return
    try:   # крайний случай: штатная точка появления комнаты
        rect, ladder = room.arrival(None, None, g.camp)
        g.place(rect, ladder)
    except Exception: pass


# ---------- отрисовка экрана ----------

def _card_layout():
    """(панель, {cid: Rect карточек}) — одна и та же раскладка для отрисовки и кликов."""
    ids = char_ids()
    n = max(1, len(ids))
    cw, gap = CARD_W, CARD_GAP
    if n * cw + (n - 1) * gap + PANEL_PAD * 2 > W - 24:
        cw = max(112, (W - 24 - PANEL_PAD * 2 - (n - 1) * gap) // n)
    pw = n * cw + (n - 1) * gap + PANEL_PAD * 2
    panel = pg.Rect((W - pw) // 2, max(6, (VIEW_H - PANEL_H) // 2 - 4), pw, PANEL_H)
    x0, y0 = panel.x + PANEL_PAD, panel.y + 54
    cards = {cid: pg.Rect(x0 + i * (cw + gap), y0, cw, CARD_H) for i, cid in enumerate(ids)}
    return panel, cards


def _snap_num(snap, *keys):
    """Число из снапшота по любому из имён ключа (формат снапшота пишет save_io — читаем бережно)."""
    if not isinstance(snap, dict): return None
    for k in keys:
        v = snap.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool): return v
    return None


def _stats(g, cid):
    """(уровень, hp, maxhp, мана, максмана) для карточки: у играемого героя — живые значения pl,
    у отдыхающего — из снапшота, у нового для забега — уровень 1 и прочерки."""
    pl = getattr(g, "pl", None)
    if pl is not None and cid == (getattr(pl, "char_id", None) or CHAR["id"]):
        return (getattr(pl, "level", None), getattr(pl, "hp", None), getattr(pl, "maxhp", None),
                getattr(pl, "mana", None), getattr(pl, "maxmana", None))
    snap = (getattr(g, "heroes", None) or {}).get(cid)
    if not isinstance(snap, dict): return (1, None, None, None, None)
    return (_snap_num(snap, "level"), _snap_num(snap, "hp"), _snap_num(snap, "maxhp"),
            _snap_num(snap, "mana"), _snap_num(snap, "maxmana", "max_mana"))


def _bar(scr, rect, v, mx, back, fill, label):
    """Полоска HP/маны с подписью значения на ней (или прочерк, если в снапшоте нет чисел)."""
    pg.draw.rect(scr, back, rect, border_radius=4)
    if v is not None and mx:
        w = int(rect.w * max(0.0, min(1.0, float(v) / float(mx))))
        if w > 0: pg.draw.rect(scr, fill, (rect.x, rect.y, w, rect.h), border_radius=4)
    txt = f"{label} {v:.0f}/{mx:.0f}" if (v is not None and mx) else f"{label} —"
    char_menu.text(scr, txt, 9, (246, 246, 252), center=rect.center, shadow=False)


def draw_menu(g):
    """Экран «ВЫБОР ПЕРСОНАЖА»: вуаль, панель по центру, карточки героев с превью (как characters.draw)."""
    scr = g.scr
    scr.blit(g.menu_veil, (0, 0))
    ids = char_ids()
    panel, cards = _card_layout()
    g.swap_rects = cards
    ps = pg.Surface(panel.size, pg.SRCALPHA); ps.fill((13, 13, 24, 233))
    scr.blit(ps, panel.topleft)
    pg.draw.rect(scr, (98, 92, 132), panel, 2, border_radius=12)
    char_menu.text(scr, "ВЫБОР ПЕРСОНАЖА", 26, (255, 220, 130), center=(panel.centerx, panel.y + 26))
    char_menu.text(scr, "Смена героя посреди забега — состояние у каждого своё", 11, (168, 168, 192), center=(panel.centerx, panel.y + 46))
    mouse = pg.mouse.get_pos()
    heroes = getattr(g, "heroes", None) or {}
    pl = getattr(g, "pl", None); cur = getattr(pl, "char_id", None) or CHAR["id"]
    sel = int(getattr(g, "swap_index", 0)) % len(ids) if ids else 0
    for i, cid in enumerate(ids):
        r = cards[cid].copy()
        on, hov = i == sel, r.collidepoint(mouse)
        ac = char_menu.accent(cid)
        if on: r.y -= 4
        pg.draw.rect(scr, (38, 36, 62) if on else ((31, 30, 48) if hov else (24, 24, 38)), r, border_radius=10)
        pg.draw.rect(scr, ac if on else ((122, 118, 154) if hov else (80, 78, 110)), r, 3 if on else 2, border_radius=10)
        char_menu.text(scr, str(i + 1), 11, (150, 150, 178), topleft=(r.x + 8, r.y + 6), shadow=False)
        try: char_menu.preview(scr, cid, pg.Rect(r.x + 10, r.y + 24, r.w - 20, 76), on)   # фигурка героя
        except Exception: pass
        char_menu.text(scr, char_def(cid).get("name", cid), 15, ac if on else (236, 233, 246), center=(r.centerx, r.y + 112))
        if cid == cur: tag, tc = "СЕЙЧАС ИГРАЕТЕ", (150, 255, 180)
        elif cid in heroes: tag, tc = "В ЗАБЕГЕ", (255, 226, 140)
        else: tag, tc = "НОВЫЙ", (172, 180, 214)
        char_menu.text(scr, tag, 10, tc, center=(r.centerx, r.y + 130), shadow=False)
        level, hp, maxhp, mana, maxmana = _stats(g, cid)
        char_menu.text(scr, f"Уровень {level:.0f}" if level is not None else "Уровень —", 12, (212, 212, 230), center=(r.centerx, r.y + 149), shadow=False)
        _bar(scr, pg.Rect(r.x + 12, r.y + 162, r.w - 24, 10), hp, maxhp, (58, 24, 30), (206, 64, 64), "Здоровье")
        _bar(scr, pg.Rect(r.x + 12, r.y + 178, r.w - 24, 10), mana, maxmana, (24, 36, 68), (88, 148, 255), "Мана")
    char_menu.text(scr, "Стрелки / W-S или мышь — выбор · Enter или клик — сменить героя · Esc — назад в паузу",
                   11, (170, 170, 195), center=(panel.centerx, panel.bottom - 18), shadow=False)
    g.draw_cursor()
