"""Сохранение и загрузка забега (система сохранений DEAD ROOMS).

Один файл сейва — JSON в папке saves/ рядом с игрой (в сборке PyInstaller — рядом с EXE):
    saves/save_<N>.json

Формат файла (version 1):
{
  "version": 1,
  "created": "2026-11-03T21:15:04",     — время создания (ISO, локальное)
  "name": "Забег от 03.11 21:15",       — человеческое имя (label или авто)
  "loop": 0,                            — круг кампании (Campaign.loop)
  "room": "env_7_0",                    — id комнаты, где стоял герой
  "pos": [612.5, 138.0],                — позиция героя в пикселях комнаты (x — левый край, y — верх)
  "char": "knight",                     — id героя, за которого играли
  "heroes": {"knight": {...}},          — снапшот КАЖДОГО героя забега (snapshot_player; swap.py может
                                           держать g.heroes — dict cid->снапшот, сохраняется как есть)
  "came_from": {"env_8_0": "env_7_0"},  — Campaign.came_from (откуда пришли на каждую карту)
  "maps": {                             — состояние каждой посещённой карты (camp.maps)
    "env_8_0": {
      "visited": true, "cleared": false, "spawned": true,
      "locked": true,                   — заперты ли двери (в сейв пишется только при живых мобах)
      "boss_spawned": false,
      "mobs":  [["rotling", 320.5, 1370.0, 1.0, 41.0, -1], ...],  — [kind, x, y, scale, hp, dir]
      "drops": [["W", 100.0, 200.0, "rusty_sword"], ["R", 64.0, 1500.0, "wood"], ...],
               "W" — предмет (оружие/артефакт из инвентаря), "R" — ресурс инженера
      "ct":    {"0": [18.0, 0, 0]},     — ящики: containers.state() {uid: [прочность, открыт, сдвиг]}
      "mc":    {"3": [1, 0.0]}          — механизмы: mechs.state() {id: [вкл, верх платформы]}
    }, ...
  }
}

ЧТО НЕ СОХРАНЯЕТСЯ (транзиентное, пересоздаётся само):
  • fx (всплывающие тексты/кольца), projs (снаряды), corpses (анимация трупов), turrets (турели
    инженера живут до выхода из комнаты, как и в мультиплеере — их состояние хостом тоже не переносится
    между комнатами), манекены F6 (is_dummy);
  • бой игрока: pl.atk/комбо/хитбокс, анимации (anim/anim_t/state), буферы ввода pl.buf;
  • колдовство: pl.channel, pl.hold (активный поток), pl.hold_latch, гарпуны pl.hooks, отдача/заметки
    арбалетов (xb_kick/xb_notice/xb_held/xb_lock), щит (shield_*), невидимость (invis), клоны (clones);
  • игра барда «прямо сейчас» (bd_play/bd_tick/bd_notice/bd_lock) — нота перестаёт звучать;
  • сетевые поля (pid/name/revive/downed/tp/hitc/kb) — сохранение только в одиночной игре.

ЧТО СОХРАНЯЕТСЯ (всё постоянное):
  hp/maxhp/mana, level/xp/xp_next, skills/item_skills/skill_index/skill_cooldowns, slots/bag/equip,
  resources (склад инженера), last_weapon, goggles, hold_pool/hold_rest (запасы «потоков»),
  выбранный бард-нот bd_note, усилители pl.amps, арбалеты: xb_ammo/xb_cd.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

from core import BASE, CFG, CHAR, FX, T, apply_character, char_ids
from maps import Campaign, Drop
from mob import Mob, normalize
from anim import clear_cache as anim_clear_cache
import inventory
import crafting
import containers
import mechs
import crossbow

VERSION = 1

# Папка сейвов: в сборке — рядом с EXE (core.BASE это уже учитывает), иначе рядом с исходниками.
SAVES_DIR = Path(BASE) / "saves"
try:
    SAVES_DIR.mkdir(parents=True, exist_ok=True)
except OSError as e:   # нет прав/диск переполнен — игра продолжит работать, но save() выдаст ошибку
    print("[сохранения] не удалось создать папку", SAVES_DIR, ":", e)


# ---------------- вспомогательные ----------------

def _resolve_path(save_id):
    """Имя файла сейва по id (id — имя файла без .json). Защита от путей вне saves/."""
    name = str(save_id).strip()
    if name.endswith(".json"):
        name = name[:-5]
    if not name or "/" in name or "\\" in name or name in (".", ".."):
        raise ValueError(f"некорректное имя сохранения: {save_id!r}")
    return SAVES_DIR / f"{name}.json"


def _read(save_id):
    """Прочитать документ сейва (dict) или выбросить понятную ошибку."""
    path = _resolve_path(save_id)
    if not path.is_file():
        raise FileNotFoundError(f"сохранение не найдено: {path.name}")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise ValueError(f"файл сохранения повреждён ({path.name}): {e}") from None
    if not isinstance(doc, dict):
        raise ValueError(f"в файле {path.name} нет данных забега")
    if int(doc.get("version", 0)) != VERSION:
        print(f"[сохранения] версия файла {path.name} — {doc.get('version')}, ожидалась {VERSION}: пробую загрузить как есть")
    return doc


def _num_of(save_id):
    """Числовой суффикс id (save_7 -> 7) для сортировки; без числа — 0."""
    try:
        return int(str(save_id).rsplit("_", 1)[-1])
    except ValueError:
        return 0


def _meta(doc, path):
    """Человеческое описание сейва для меню (тот же вид, что и в list_saves)."""
    created = str(doc.get("created") or "")
    try:
        time = datetime.fromisoformat(created).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        time = created[:16].replace("T", " ") or "—"
    heroes = doc.get("heroes") if isinstance(doc.get("heroes"), dict) else {}
    chars = [str(c) for c in heroes]
    char = str(doc.get("char") or (chars[0] if chars else ""))
    if char and char not in chars:
        chars = [char] + chars
    level = {}
    for cid, snap in heroes.items():
        if isinstance(snap, dict):
            try:
                level[str(cid)] = int(snap.get("level", 1))
            except (TypeError, ValueError):
                level[str(cid)] = 1
    return {"id": path.stem, "name": str(doc.get("name") or "Забег"), "time": time,
            "loop": int(doc.get("loop", 0)), "char": char, "chars": chars,
            "level": level, "file": str(path)}


def _free_id():
    """Первый свободный номер: save_1, save_2, ..."""
    taken = {p.stem for p in SAVES_DIR.glob("save_*.json")}
    n = 1
    while f"save_{n}" in taken:
        n += 1
    return f"save_{n}"


def _live_mobs(mobs):
    """Живые обычные мобы (без манекенов F6) — только они держат двери и зачистку."""
    return [m for m in mobs if getattr(m, "hp", 0) > 0 and not getattr(m, "is_dummy", False)]


# ---------------- снапшоты частей мира ----------------

def _mobs_snapshot(mobs):
    """Мобы комнаты -> [[kind, x, y, scale, hp, dir], ...]. Умирающих (hp <= 0), манекенов и
    неизвестных каталгу мобов пропускаем: scale восстанавливается из maxhp."""
    out = []
    for m in mobs:
        if getattr(m, "is_dummy", False) or getattr(m, "hp", 0) <= 0:
            continue
        kind = str(getattr(m, "kind", ""))
        d = normalize(CFG["mobs"][kind]) if kind in CFG.get("mobs", {}) else None
        if not d:
            continue
        base = float(d.get("hp", 1)) or 1.0
        scale = float(getattr(m, "maxhp", base)) / base
        out.append([kind, round(float(m.x), 1), round(float(m.y), 1), round(scale, 3),
                    round(float(m.hp), 1), 1 if getattr(m, "dir", 1) >= 0 else -1])
    return out


def _drops_snapshot(drops):
    """Предметы и ресурсы на полу -> [["W", x, y, wid] | ["R", x, y, rid], ...]."""
    out = []
    for dr in drops or []:
        rid = getattr(dr, "rid", None)
        if rid is not None:   # ресурс инженера (crafting.ResourceDrop)
            if crafting.is_resource(rid):
                out.append(["R", round(float(dr.x), 1), round(float(dr.y), 1), str(rid)])
            continue
        wid = getattr(dr, "wid", None)
        if wid is not None and inventory.is_item(wid):   # оружие или предмет инвентаря (maps.Drop)
            out.append(["W", round(float(dr.x), 1), round(float(dr.y), 1), str(wid)])
    return out


def _map_snapshot(m):
    """Снимок одной карты: флаги + мобы + дропы + ящики + механизмы."""
    return {
        "visited": bool(getattr(m, "visited", False)),
        "cleared": bool(getattr(m, "cleared", False)),
        "spawned": bool(getattr(m, "spawned", False)),
        # запертые двери сохраняем только если есть живые мобы (иначе при загрузке можно остаться в запертой пустой комнате)
        "locked": bool(getattr(m, "locked", False)) and bool(_live_mobs(getattr(m, "mobs", ()))),
        "boss_spawned": bool(getattr(m, "boss_spawned", False)),
        "mobs": _mobs_snapshot(getattr(m, "mobs", ())),
        "drops": _drops_snapshot(getattr(m, "drops", ())),
        "ct": containers.state(m),
        "mc": mechs.state(m),
    }


def _restore_drops(rows):
    """Список сейва -> объекты Drop/ResourceDrop на полу."""
    out = []
    for row in rows or []:
        if not isinstance(row, (list, tuple)) or len(row) < 4:
            continue
        tag, ident = row[0], row[3]
        try:
            x, y = float(row[1]), float(row[2])
        except (TypeError, ValueError):
            continue
        if tag == "R":
            if crafting.is_resource(ident):
                out.append(crafting.ResourceDrop(x, y, str(ident)))
        elif inventory.is_item(ident):   # "W": оружие или предмет инвентаря
            out.append(Drop(x, y, str(ident)))
    return out


def _restore_mobs(m, rows):
    """Создать мобов карты из сейва (kind, x, y, scale, hp, dir). Неизвестные виды пропускаются."""
    m.mobs = []
    for row in rows or []:
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            continue
        kind = row[0]
        if kind not in CFG.get("mobs", {}):
            continue
        try:
            x, y, scale, hp, d = float(row[1]), float(row[2]), float(row[3]), float(row[4]), int(row[5])
        except (TypeError, ValueError):
            continue
        try:
            mob = Mob(kind, x, y, max(0.1, scale), room=m)   # room нужен Моргарту (руки от раскладки карты)
        except (KeyError, TypeError, ValueError):
            continue
        mob.hp = max(1.0, min(hp, mob.maxhp if mob.maxhp > 0 else hp))
        mob.dir = 1 if d >= 0 else -1
        m.mobs.append(mob)


def _restore_map(camp, mid, msnap):
    """Поднять одну карту из сейва: флаги, мобы, дропы, ящики, механизмы, двери."""
    r = camp.get(mid)   # GameMap создаётся из data/maps/<mid>.json с масштабом текущего круга
    r.visited = bool(msnap.get("visited", True))
    r.cleared = bool(msnap.get("cleared"))
    r.boss_spawned = bool(msnap.get("boss_spawned"))
    r.drops = _restore_drops(msnap.get("drops"))
    rows = msnap.get("mobs") or []
    if r.cleared:            # зачищена: мобов нет, спавнить нечего
        r.spawned = True
        r.mobs = []
    elif rows:               # бой шёл на момент сохранения: восстановить мобов как были
        r.spawned = True
        _restore_mobs(r, rows)
    else:                    # не зачищена, мобов не сохранилось — заспавнятся заново при входе
        r.spawned = False
        r.mobs = []
    # Двери заперты только при живых мобах: иначе игрок останется в запертой пустой комнате навсегда.
    locked = bool(msnap.get("locked")) and not r.cleared and bool(_live_mobs(r.mobs))
    if locked != r.locked:
        r.set_lock(locked)
    containers.apply_state(r, msnap.get("ct"))   # ящики: что сломано/открыто (лишние созданные уберутся)
    mechs.apply_state(r, msnap.get("mc"))        # механизмы: рычаги/двери/лифты/платформы
    return r


def _heroes_snapshots(g, pl):
    """Снапшоты всех героев забега. g.heroes (из swap.py) — dict cid->Player или cid->dict;
    живой герой (g.pl) всегда даёт актуальный снапшот."""
    heroes = {}
    stored = getattr(g, "heroes", None)
    if isinstance(stored, dict):
        for cid, val in stored.items():
            if val is None:
                continue
            heroes[str(cid)] = val if isinstance(val, dict) else snapshot_player(val)
    heroes[str(getattr(pl, "char_id", None) or CHAR.get("id"))] = snapshot_player(pl)
    return heroes


# ---------------- герой ----------------

def snapshot_player(pl):
    """JSON-снапшот героя: только постоянный прогресс (его зовёт и swap.py)."""
    slots = [None if w is None else str(w) for w in (list(getattr(pl, "slots", [])) + [None, None])[:2]]
    return {
        "char": getattr(pl, "char_id", None),
        "hp": round(float(getattr(pl, "hp", 1)), 1),
        "maxhp": round(float(getattr(pl, "maxhp", 1)), 1),
        "mana": round(float(getattr(pl, "mana", 0)), 1),
        "level": int(getattr(pl, "level", 1)),
        "xp": int(getattr(pl, "xp", 0)),
        "xp_next": int(getattr(pl, "xp_next", 100)),
        "skills": [str(s) for s in getattr(pl, "skills", [])],
        "item_skills": [str(s) for s in getattr(pl, "item_skills", [])],
        "skill_index": int(getattr(pl, "skill_index", 0)),
        "skill_cooldowns": {str(k): round(float(v), 2)
                            for k, v in getattr(pl, "skill_cooldowns", {}).items() if v and float(v) > 0},
        "slots": slots,
        "bag": [None if w is None else str(w) for w in getattr(pl, "bag", [])],
        "equip": {str(k): str(v) for k, v in getattr(pl, "equip", {}).items() if v is not None},
        "resources": {str(k): int(v) for k, v in getattr(pl, "resources", {}).items()},
        "last_weapon": None if getattr(pl, "last_weapon", None) is None else str(pl.last_weapon),
        "goggles": bool(getattr(pl, "goggles", False)),
        # запасы «потоков» (hold) и пауза перед восстановлением
        "hold_pool": {str(k): round(float(v), 2) for k, v in getattr(pl, "hold_pool", {}).items()},
        "hold_rest": {str(k): round(float(v), 2) for k, v in getattr(pl, "hold_rest", {}).items()},
        # бард: выбранная нота и усилители (игру «прямо сейчас» не сохраняем)
        "bd_note": int(getattr(pl, "bd_note", 0)),
        "amps": [{"x": round(float(a.get("x", 0.0)), 1), "y": round(float(a.get("y", 0.0)), 1),
                  "t": round(float(a.get("t", 0.0)), 2), "life": round(float(a.get("life", a.get("t", 0.0))), 2),
                  "sid": str(a.get("sid", "amp"))}
                 for a in getattr(pl, "amps", []) if isinstance(a, dict)],
        # арбалеты (Тень): выбранный снаряд и перезарядка каждого
        "xb_ammo": [int(v) for v in getattr(pl, "xb_ammo", [])],
        "xb_cd": [round(max(0.0, float(v)), 2) for v in getattr(pl, "xb_cd", [])],
    }


def restore_player(pl, snap):
    """Восстановить героя ПО СЛОВУ: объект pl уже создан (свежим, с данными своего героя из CFG).
    Порядок важен: сначала навыки/экипировка, затем on_equipment_changed пересчитывает
    maxhp/maxmana от предметов, и только потом hp/mana зажимаются в новые максимумы."""
    if not isinstance(snap, dict):
        return
    # навыки и предметы (sync_skills смотрит и skills, и item_skills, и equip)
    pl.skills = [str(s) for s in (snap.get("skills") or []) if isinstance(s, str)]
    pl.item_skills = [str(s) for s in (snap.get("item_skills") or []) if isinstance(s, str)]
    pl.equip = {str(k): str(v) for k, v in (snap.get("equip") or {}).items() if isinstance(v, str)}
    pl.resources = {str(k): max(0, int(v)) for k, v in (snap.get("resources") or {}).items()}
    pl.bag = [None if w is None else str(w) for w in (snap.get("bag") or [])]
    inventory.bag(pl)   # нормализовать длину под bag_size (None-ячейки обязательны)
    slots = snap.get("slots")
    if isinstance(slots, (list, tuple)):
        slots = [None if w is None else str(w) for w in list(slots)[:2]]
        while len(slots) < 2:
            slots.append(None)
        pl.slots = slots
    if "last_weapon" in snap:
        pl.last_weapon = None if snap.get("last_weapon") is None else str(snap["last_weapon"])
    pl.goggles = bool(snap.get("goggles", False))
    # прогресс
    try: pl.level = max(1, int(snap.get("level", 1)))
    except (TypeError, ValueError): pl.level = 1
    try: pl.xp = max(0, int(snap.get("xp", 0)))
    except (TypeError, ValueError): pl.xp = 0
    try: pl.xp_next = max(1, int(snap.get("xp_next", 100)))
    except (TypeError, ValueError): pl.xp_next = 100
    try: pl.skill_index = max(0, int(snap.get("skill_index", 0)))
    except (TypeError, ValueError): pl.skill_index = 0
    # кулдауны: сброс и накат сохранённых (>0); отсутствующим хватит нуля из init
    pl.skill_cooldowns = {sid: 0.0 for sid in pl.skills}
    for k, v in (snap.get("skill_cooldowns") or {}).items():
        if k in pl.skill_cooldowns:
            try: pl.skill_cooldowns[k] = max(0.0, float(v))
            except (TypeError, ValueError): pass
    # «потоки»: запасы и паузы восстановления
    pl.hold_pool = {}
    for k, v in (snap.get("hold_pool") or {}).items():
        try: pl.hold_pool[str(k)] = max(0.0, float(v))
        except (TypeError, ValueError): pass
    pl.hold_rest = {}
    for k, v in (snap.get("hold_rest") or {}).items():
        try: pl.hold_rest[str(k)] = max(0.0, float(v))
        except (TypeError, ValueError): pass
    # бард: нота и усилители (сбрасываем падение — пусть заново лягут на пол этой комнаты)
    try: pl.bd_note = int(snap.get("bd_note", 0))
    except (TypeError, ValueError): pl.bd_note = 0
    pl.amps = []
    for a in snap.get("amps") or []:
        if not isinstance(a, dict):
            continue
        try:
            pl.amps.append({"x": float(a.get("x", 0.0)), "y": float(a.get("y", 0.0)),
                            "t": float(a.get("t", 0.0)), "life": float(a.get("life", a.get("t", 0.0))),
                            "sid": str(a.get("sid", "amp")), "vy": 0.0, "ground": False})
        except (TypeError, ValueError):
            continue
    # арбалеты (Тень): выбранный снаряд и перезарядка; гарпуны/отдача — транзиент, их не трогаем
    ammo, cds = snap.get("xb_ammo") or [], snap.get("xb_cd") or []
    for i in range(crossbow.SIDES):
        try: pl.xb_ammo[i] = int(ammo[i])
        except (IndexError, TypeError, ValueError): pl.xb_ammo[i] = 0
        try: pl.xb_cd[i] = max(0.0, float(cds[i]))
        except (IndexError, TypeError, ValueError): pl.xb_cd[i] = 0.0
    # пересчёт бонусов экипировки (maxhp/maxmana от аксессуаров) и снап навыков предметов
    if hasattr(pl, "skills"):
        inventory.on_equipment_changed(None, pl)
    # здоровье/мана из сейва, зажатые в пересчитанные максимумы
    try: pl.hp = max(1.0, min(float(snap.get("hp", pl.maxhp)), float(pl.maxhp)))
    except (TypeError, ValueError): pl.hp = pl.maxhp
    try: pl.mana = max(0.0, min(float(snap.get("mana", pl.maxmana)), float(pl.maxmana)))
    except (TypeError, ValueError): pl.mana = pl.maxmana


# ---------------- сохранение / загрузка ----------------

def save(g, label=None):
    """Полный снапшот забега g -> saves/save_<N>.json. Возвращает meta (как в list_saves)."""
    if getattr(g, "net", None) is not None:
        raise RuntimeError("в сетевой игре сохранение недоступно")
    pl = getattr(g, "pl", None)
    room = getattr(g, "room", None)
    camp = getattr(g, "camp", None)
    if pl is None or camp is None or room is None:
        raise RuntimeError("сохранять нечего: забег ещё не начат")
    now = datetime.now()
    doc = {
        "version": VERSION,
        "created": now.isoformat(timespec="seconds"),
        "name": str(label) if label is not None else f"Забег от {now:%d.%m.%Y %H:%M}",
        "loop": int(getattr(camp, "loop", 0)),
        "room": str(room.id),
        "pos": [round(float(pl.x), 1), round(float(pl.y), 1)],
        "char": str(getattr(pl, "char_id", None) or CHAR.get("id")),
        "heroes": _heroes_snapshots(g, pl),
        "came_from": {str(k): str(v) for k, v in getattr(camp, "came_from", {}).items()},
        "maps": {str(mid): _map_snapshot(m) for mid, m in camp.maps.items()},
    }
    path = SAVES_DIR / f"{_free_id()}.json"
    try:
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        raise RuntimeError(f"не удалось записать {path.name}: {e}") from None
    print(f"[сохранения] забег сохранён: {path.name} — {doc['name']}")
    return _meta(doc, path)


def restore(g, save_id):
    """Поднять забег из файла: карты кампании, комната и герой (со всеми своими прогрессами).
    main.py после этого должен вернуть геймплей (g.menu_mode=None — ставим здесь)."""
    if getattr(g, "net", None) is not None:
        raise RuntimeError("в сетевой игре загрузка недоступна")
    doc = _read(save_id)
    # 1) герой из сейва: CFG и кэши картинок/инвентаря — до создания Player (Player читает CFG["character"])
    cid = doc.get("char")
    if cid not in char_ids():
        print(f"[сохранения] героя {cid!r} нет в data/characters.json — беру героя по умолчанию")
        cid = None
    cid = apply_character(cid)
    anim_clear_cache()
    inventory.clear_cache()
    # 2) кампания и карты (кэш героев прошлого забега больше не нужен)
    if hasattr(g, "heroes"):
        g.heroes = {}
    camp = g.camp = Campaign(int(doc.get("loop", 0)) if isinstance(doc.get("loop", 0), (int, float)) else 0)
    came = {}
    for mid, prev in (doc.get("came_from") or {}).items():
        if mid in CFG["map_defs"] and prev in CFG["map_defs"]:
            came[str(mid)] = str(prev)
    camp.came_from = came
    # 3) карты: спавн ящиков без броска шанса — «какие ящики появились, решает сейв» (как у клиента сети),
    #    лишних уберёт containers.apply_state по сохранённому списку ct
    old_roll = containers.ROLL_SPAWN
    containers.ROLL_SPAWN = False
    try:
        for mid, msnap in (doc.get("maps") or {}).items():
            if isinstance(msnap, dict) and mid in CFG["map_defs"]:
                _restore_map(camp, mid, msnap)
    finally:
        containers.ROLL_SPAWN = old_roll
    # 4) свежий герой (с данными героя из сейва), затем переход в сохранённую комнату
    g.pl = g.Player()
    room = doc.get("room")
    if room not in CFG["map_defs"]:
        print(f"[сохранения] комнаты {room!r} нет в data/maps — начинаю с первой карты кампании")
        room = camp.first
        if room is None:
            raise RuntimeError(f"в сейве {save_id} нет ни одной известной карты")
    g.go(room, None)
    # 5) позиция героя из сейва (go()/place() уже поставил точку прибытия — перекрываем)
    pos = doc.get("pos")
    if isinstance(pos, (list, tuple)) and len(pos) == 2:
        try:
            x, y = float(pos[0]), float(pos[1])
        except (TypeError, ValueError):
            x = None
        if x is not None:
            pl = g.pl
            pl.x = max(0.0, min(float(g.room.width_px) - pl.w, x))
            pl.y = max(0.0, min(float(g.room.height_px) - pl.h, y))
            pl.vx = pl.vy = 0.0
    # 6) состояние героя по слову (hp/мана/рюкзак/навыки/...) — после go(): place() сбрасывает
    #    гарпуны и усилители барда, а восстановление должно вернуть сохранённые
    heroes = doc.get("heroes") if isinstance(doc.get("heroes"), dict) else {}
    snap = heroes.get(cid)
    if not isinstance(snap, dict):
        print("[сохранения] в сейве нет снапшота героя — остаётся свежий герой со стартовыми предметами")
        snap = {}
    restore_player(g.pl, snap)
    # 7) герои забега: снимки всех (для swap.py), текущий — из живого объекта
    if heroes:
        g.heroes = {str(c): dict(s) for c, s in heroes.items() if isinstance(s, dict)}
        g.heroes[str(cid)] = snapshot_player(g.pl)
    # 8) хвосты интерфейса и транзиента: из меню загрузки — сразу в игру
    g.menu_mode = None
    g.show_world = False
    g.inv_open = False
    g.inv_hold = None
    g.crafting = None
    g.placing = None
    g.place_lock = 0.0
    g.place_hold = False
    g.craft_sel = 0
    g.level_menu = False
    g.level_choices = []
    g.skill_unlock_anim = None
    g.done = False
    g.projs = []
    g.fx = FX()
    g.warn_t = 0
    print(f"[сохранения] забег загружен: {doc.get('name')} (круг {doc.get('loop', 0)}, комната {room}, герой {cid})")


def list_saves():
    """Все сейвы, новые первыми: [{id, name, time, loop, char, chars, level, file}, ...]."""
    out = []
    for p in SAVES_DIR.glob("save_*.json"):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"[сохранения] файл {p.name} не читается: {e}")
            continue
        if isinstance(doc, dict):
            out.append(_meta(doc, p))
    out.sort(key=lambda m: (m["time"], _num_of(m["id"])), reverse=True)
    return out
