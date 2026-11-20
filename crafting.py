"""Крафт и ресурсы инженера (данные — data/crafting.json, товары — assets/inventory.json).

Механика:
  • Ресурсы (древесина, металлическая деталь, кристалл, огонь) лежат на полу — класс ResourceDrop,
    живёт в room.drops наравне с оружием/предметами (их телекинез тоже цепляет, container.py стучится сюда).
  • Очки инженера (engineer_goggles, слот «Голова») — клавиша G включает «зрение»: жёлтый фильтр на экране
    и ресурсы светятся с подписями. Видение работает, пока очки надеты и pl.goggles == True.
  • Перчатка (engineer_gauntlet, слот «Перчатка») выдаёт навык-поток telekinesis_drag (spells.py): зажал Q
    рядом с предметом — он тянется за курсором (тратит ману в секунду).
  • Крафт: когда нужные ресурсы лежат рядом с героем, над ними показываются миниатюры доступных рецептов.
    F — начать крафт: герой стоит, ресурсы сливаются в жёлтом круге света, через craft_time секунд готовое
    падает на пол (kind: item) или герой выбирает место установки (kind: building, клик — поставить, Esc — отмена).
    Крафт тратит ману; пошёл/пригнулся или кончилась мана — крафт прерывается, ресурсы остаются на месте.
  • Турель (крафтится по рецепту turret): стоит на месте, имеет запас здоровья и стреляет по ближайшему врагу
    в радиусе (friendly-снаряды, бьют мобов). Вражеские пули могут её повредить.
"""
import math
import random
import pygame as pg
from types import SimpleNamespace
from core import CFG, T, W, VIEW_H, ASSETS, sign, free, floor_below

DEFAULTS = {"resources": {}, "recipes": {}, "scatter": {"per_room": 0, "weights": {}},
            "craft_radius": 170, "drag_speed": 540}

_state = {"raw": object(), "cfg": None}   # object() — сторож, чтобы первый вызов всегда пересчитывал DEFAULTS

def cfg():
    """Настройки крафта = DEFAULTS + data/crafting.json (перечитываются после F5)."""
    raw = CFG.get("crafting")
    if _state["raw"] is not raw:
        _state["raw"] = raw
        _state["cfg"] = dict(DEFAULTS)
        if isinstance(raw, dict):
            for k, v in raw.items(): _state["cfg"][k] = v
    return _state["cfg"]

def resources():
    return cfg().get("resources") or {}

def recipes():
    return cfg().get("recipes") or {}

def def_of(rid):
    return (resources().get(rid) or {})

def is_resource(rid):
    return isinstance(rid, str) and rid in resources()

def is_grab_drop(dr):
    """Что телекинез перчатки может тянуть: любой предмет на полу (ресурс, оружие, артефакт)."""
    return getattr(dr, "rid", None) is not None or getattr(dr, "wid", None) is not None

# ---------------- ресурсы на полу ----------------

_tex_cache = {}
def _tex(rel, w, h=None):
    """Картинка текстуры из assets (поля image ресурса/турели), вписанная в w×h. Нет файла/пути — None."""
    if not rel: return None
    h = h or w
    key = (str(rel), int(w), int(h))
    if key not in _tex_cache:
        try:
            img = pg.image.load(str(ASSETS / str(rel))).convert_alpha()
            _tex_cache[key] = pg.transform.smoothscale(img, (int(w), int(h)))
        except (OSError, pg.error, ValueError, AttributeError):
            _tex_cache[key] = None
    return _tex_cache[key]

class ResourceDrop:
    """Ресурс, лежащий на полу комнаты (появляется в room.drops; его тянет телекинез, он участвует в крафте)."""
    def __init__(s, x, y, rid):
        s.x, s.y, s.rid = x, y, rid

    def draw(s, v, vision=False):
        d = def_of(s.rid)
        col = tuple(int(c) for c in d.get("color", [200, 200, 200]))
        glow = tuple(int(c) for c in d.get("glow", [255, 255, 255]))
        bob = math.sin(pg.time.get_ticks() / 300) * 3
        x, y = s.x, s.y - 12 + bob
        if vision:
            rad = 16 + int(math.sin(pg.time.get_ticks() / 90) * 3)
            surf = pg.Surface((rad * 2 + 8, rad * 2 + 8), pg.SRCALPHA)
            pg.draw.circle(surf, (*glow, 150), (rad + 4, rad + 4), rad)
            v.blit(surf, (x - rad - 4, y - rad - 4))
        img = _tex(d.get("image"), 30)
        if img:   # нарисованная в редакторе текстура (вкладка «Текстуры», assets/resources/<id>.png)
            v.blit(img, img.get_rect(center=(int(x), int(y))))
            return
        pg.draw.polygon(v, col, [(x, y - 7), (x + 7, y), (x, y + 7), (x - 7, y)])
        pg.draw.polygon(v, tuple(int(c * .6) for c in col), [(x, y - 4), (x + 4, y), (x, y + 4), (x - 4, y)])

    def draw_label(s, v, font):
        d = def_of(s.rid)
        col = tuple(int(c) for c in d.get("glow", [255, 255, 255]))
        t = font.render(d.get("name", s.rid), True, col)
        v.blit(t, (s.x - t.get_width() // 2, s.y - 42))

def scatter(room, override=None):
    """Разбросать ресурсы по комнате: по свободным клеткам с полом под ними (не на стенах/выходах/старте).
    override — словарь ресурсов карты из её JSON (data/maps/<id>.json -> "resources"): перекрывает data/crafting.json."""
    sc = {}
    sc.update(cfg().get("scatter") or {})
    if isinstance(override, dict):
        sc.update({k: v for k, v in override.items() if v is not None})
        if isinstance(override.get("weights"), dict):
            w = dict(sc.get("weights") or {}); w.update(override["weights"]); sc["weights"] = w
    n = max(0, int(sc.get("per_room", 0)))
    if n <= 0: return []
    wts = sc.get("weights") or {}
    ids = [rid for rid in resources() if wts.get(rid, 0) > 0]
    total = sum(wts.get(r, 0) for r in ids)
    if not ids or total <= 0: return []
    protected = {(c, r) for c, r, e in room.cells() if e.get("player") or "exit" in e}
    cands = []
    for c in range(room.width):
        for r in range(room.height - 1):
            if room.g[r][c] != "." or room.g[r + 1][c] not in "#=": continue   # пустая клетка с полом под ней
            if (c, r) in protected or (c, r + 1) in protected: continue
            cands.append((c, r))
    random.shuffle(cands)
    out = []
    for c, r in cands[:n]:
        rid = random.choices(ids, weights=[wts[i] for i in ids])[0]
        out.append(ResourceDrop(c * T + T / 2, (r + 1) * T - 10, rid))
    return out

# ---------------- очки (зрение) ----------------

def wearing(pl, wid):
    """Надет ли предмет wid хотя бы в один слот экипировки."""
    import inventory
    return any(w == wid for _, w in inventory.equipped_items(pl))

def vision_on(pl):
    """Включено ли «зрение»: есть очки + они надеты + активированы (pl.goggles)."""
    return bool(getattr(pl, "goggles", False)) and wearing(pl, wid_of("goggles"))

def wid_of(kind):
    g = cfg().get("gadgets") or {}
    return g.get(kind)

def toggle_vision(g):
    """G: вкл/выкл жёлтый фильтр очков (только если очки надеты)."""
    pl = g.pl
    gid = wid_of("goggles")
    if not gid:
        return
    if not wearing(pl, gid):
        g.fx.text("Наденьте очки инженера", pl.cx, pl.y - 18)
        return
    pl.goggles = not getattr(pl, "goggles", False)
    if pl.goggles:
        g.fx.text("Очки: зрение включено", pl.cx, pl.y - 26)
    else:
        g.fx.text("Очки выключены", pl.cx, pl.y - 26)

def on_equipment_changed(g, pl):
    """Сняли очки/перчатку — выключить фильтр, остановить потоки перчатки (остальное делает inventory)."""
    if getattr(pl, "goggles", False) and not wearing(pl, wid_of("goggles")):
        pl.goggles = False

# ---------------- крафт ----------------

def _near_resources(drops, x, y, radius):
    """Сколько каких ресурсов лежит в радиусе от (x, y)."""
    counts = {}
    for dr in drops:
        rid = getattr(dr, "rid", None)
        if not is_resource(rid): continue
        if (dr.x - x) ** 2 + (dr.y - y) ** 2 <= radius * radius:
            counts[rid] = counts.get(rid, 0) + 1
    return counts

def available_recipes(drops, x, y, radius):
    """Рецепты, которые можно скрафтить из ресурсов рядом с (x, y): (rid, recipe)."""
    near = _near_resources(drops, x, y, radius)
    out = []
    for rid, rc in recipes().items():
        cost = rc.get("cost") or {}
        if all(near.get(k, 0) >= int(v) for k, v in cost.items()):
            out.append((rid, rc))
    return out

def _pick_resources(drops, x, y, cost, radius):
    """Выбрать конкретные ресурсы (ближайшие к центру) для крафта по cost. Список ResourceDrop."""
    picked = []
    wanted = {k: int(v) for k, v in cost.items()}
    ranked = [(dr, (dr.x - x) ** 2 + (dr.y - y) ** 2) for dr in drops if getattr(dr, "rid", None) in wanted]
    ranked.sort(key=lambda p: p[1])
    for dr, _ in ranked:
        if wanted.get(dr.rid, 0) <= 0: continue
        picked.append(dr); wanted[dr.rid] -= 1
    return picked

def crafting(g):
    return getattr(g, "crafting", None)

def placing(g):
    return getattr(g, "placing", None)

def try_start(g):
    """F: начать крафт ВЫБРАННОГО рецепта (выбор — колесо мыши, craft.craft_sel; по умолчанию первый доступный)."""
    pl, r = g.pl, g.room
    if crafting(g) or placing(g) or pl.hp <= 0 or getattr(pl, "grab", None) or getattr(g, "inv_open", False): return
    radius = float(cfg().get("craft_radius", 170))
    avail = available_recipes(r.drops, pl.cx, pl.cy, radius)
    if not avail:
        g.fx.text("Рядом нет ресурсов для крафта", pl.cx, pl.y - 26)
        return
    sel = int(getattr(g, "craft_sel", 0)) % len(avail)   # выбранный рецепт (индекс по доступным)
    rid, rc = avail[sel]
    cost = rc.get("cost") or {}
    mana_total = float(rc.get("mana_cost", 20))
    if pl.mana <= 0:
        pl.mana_flash = .35
        g.fx.text("Недостаточно маны для крафта", pl.cx, pl.y - 26)
        return
    inv = _pick_resources(r.drops, pl.cx, pl.cy, cost, radius)
    if len(inv) < sum(cost.values()): return
    cx = sum(dr.x for dr in inv) / len(inv)
    cy = sum(dr.y for dr in inv) / len(inv)
    g.fx.text(f"Крафт: {rc.get('name', rid)}" + (f" ({sel + 1}/{len(avail)})" if len(avail) > 1 else ""), pl.cx, pl.y - 40)
    g.crafting = {"rid": rid, "recipe": rc, "t": 0.0, "max": max(0.2, float(rc.get("craft_time", 3.0))),
                  "mana": mana_total, "cost": cost, "inv": inv, "x": cx, "y": cy, "hp0": pl.hp}

def cycle_recipe(g, dirn):
    """Колесо мыши: выбрать рецепт из доступных (когда их несколько; иначе ничего)."""
    pl, r = g.pl, g.room
    if crafting(g) or placing(g) or pl is None or getattr(g, "inv_open", False) or getattr(pl, "grab", None): return
    radius = float(cfg().get("craft_radius", 170))
    avail = available_recipes(r.drops, pl.cx, pl.cy, radius)
    if len(avail) < 2: return
    g.craft_sel = (int(getattr(g, "craft_sel", 0)) + (1 if dirn > 0 else -1)) % len(avail)
    rid, rc = avail[g.craft_sel]
    g.fx.text(f"Крафт: {rc.get('name', rid)} ({g.craft_sel + 1}/{len(avail)})", pl.cx, pl.y - 40)

def _cancel_craft(g, why=None):
    c = g.crafting
    if c and why: g.fx.text(why, g.pl.cx, g.pl.y - 26)
    g.crafting = None

def update_craft(g, dt):
    """Каждый кадр: ведение крафта (герой стоит, ресурсы сливаются, мана тратится; конец -> предмет/установка)."""
    c = g.crafting
    if not c: return
    pl, r = g.pl, g.room
    # урон прерывает крафт, но только ощутимый (потеря > 20% максимума здоровья с начала крафта):
    # слабые удары мобов не должны делать постройку невозможной — герой и так стоит на месте 3 секунды
    hurt_threshold = pl.maxhp * float(cfg().get("craft_hurt_share", 0.2))
    if pl.hp <= 0 or pl.hp < c.get("hp0", pl.hp + 1) - hurt_threshold:
        _cancel_craft(g, "Крафт прерван")
        return
    k = pg.key.get_pressed()
    d = (k[pg.K_d] or k[pg.K_RIGHT]) - (k[pg.K_a] or k[pg.K_LEFT])
    dn = k[pg.K_s] or k[pg.K_DOWN]
    if d or dn:
        _cancel_craft(g, "Крафт прерван")
        return
    pl.vx = 0.0
    c["t"] += dt
    pl.mana -= c["mana"] / c["max"] * dt
    if pl.mana < 0:
        pl.mana = 0.0; pl.mana_flash = .35
        _cancel_craft(g, "Не хватило маны: крафт прерван")
        return
    # ресурсы плавно стягиваются в центр жёлтого круга
    sp = 3.0 * dt
    alive = 0
    for dr in list(c["inv"]):
        if dr not in r.drops: continue
        alive += 1
        dr.x += (c["x"] - dr.x) * min(1, sp)
        dr.y += (c["y"] - dr.y) * min(1, sp)
    if c["t"] >= c["max"]:
        _finish_craft(g)

def _floor_near(g, x, y, col_span=3):
    """Пол под точкой (x, y), ищем и в соседних столбцах (карта: у лестниц/платформ floor_below может не найти).
    Возвращает Y верхней кромки ближайшего пола (>= y - T) или None."""
    c = int(x // T)
    best = None
    for dc in range(-col_span, col_span + 1):
        gy = floor_below(g, (c + dc) * T + T // 2, y)
        if gy is None: continue
        if best is None or abs(gy - y) < abs(best - y): best = gy
    return best


def _finish_craft(g):
    c = g.crafting
    r = g.room
    rc = c["recipe"]
    fx = g.fx
    for dr in list(c["inv"]):
        if dr in r.drops: r.drops.remove(dr)
    fx.flash(c["x"], c["y"], 44, [255, 220, 90])
    fx.ring(c["x"], c["y"], 46)
    g.crafting = None
    if rc.get("kind") == "item":
        from maps import Drop
        r.drops.append(Drop(c["x"], c["y"], rc.get("result")))
        fx.text(f"Готово: {rc.get('name', '')}", c["x"], c["y"] - 40)
    else:
        gy = _floor_near(r.g, c["x"], c["y"])
        build = rc.get("build") or {}
        h = int(build.get("h", 34))
        g.placing = {"build": build, "x": c["x"], "y": (gy - h if gy is not None else c["y"])}
        fx.text("Турель: выберите место (ЛКМ — поставить, Esc — отмена)", c["x"], c["y"] - 40)

def update_place(g, dt):
    """Режим установки строения: герой стоит, призрак следует за курсором; ЛКМ — поставить, Esc — отмена (см. main.key)."""
    p = g.placing
    if not p: return
    g.pl.vx = 0.0
    g.pl.vy = 0.0
    build = p["build"]; w = int(build.get("w", 30)); h = int(build.get("h", 34))
    ax, ay = g.pl.aim if g.pl.aim else (g.pl.cx + g.pl.face * 60, g.pl.cy)
    # привязка к полу, чтобы призрак стоял на земле (ищем и в соседних столбцах)
    gy = _floor_near(g.room.g, ax, ay)
    p["cursor"] = (int(ax - w / 2), (gy - h if gy is not None else int(ay - h)), w, h)
    if pg.mouse.get_pressed()[0] and not g.inv_open and not g.dev.open:
        confirm_place(g)

def place_rect(p):
    return pg.Rect(p["cursor"])

def place_valid(g, rect):
    """Можно ли поставить строение: не в стене (все клетки свободны), не в других ящиках/турелях/мобах и на земле."""
    room = g.room
    if not free(room.g, rect): return False   # тело строения стоит в открытых клетках (пол снизу, не в стене)
    # под постройкой должен быть пол: верхняя кромка пола под центром — у самого низа призрака (нельзя вешать в воздухе)
    fb = _floor_near(room.g, rect.centerx, rect.bottom)
    if fb is None or abs(fb - rect.bottom) > T * 0.5: return False
    for t in room.turrets:
        if t.rect.colliderect(rect): return False
    for m in room.mobs:
        if m.rect.colliderect(rect): return False
    for ct in room.containers:
        if ct.rect.colliderect(rect): return False
    return True

def confirm_place(g):
    p = g.placing
    if not p: return
    rect = place_rect(p)
    if not place_valid(g, rect):
        g.fx.text("Сюда нельзя поставить", rect.centerx, rect.y - 10)
        return
    g.room.turrets.append(Turret(rect.x, rect.y, p["build"]))
    g.fx.flash(rect.centerx, rect.centery, max(rect.w, rect.h) * .7, [150, 200, 255])
    g.fx.ring(rect.centerx, rect.centery, max(rect.w, rect.h) * .6)
    g.placing = None
    # пауза после установки + блок, пока зажата та же кнопка, которой ставили: она не должна включить скилл мага/инженера
    g.place_lock = 0.25
    g.place_hold = True

def cancel_place(g):
    g.placing = None
    g.place_hold = True
    g.fx.text("Установка отменена", g.pl.cx, g.pl.y - 26)

# ---------------- турель ----------------

class Turret:
    """Постройка инженера: запас здоровья, стреляет по ближайшему врагу friendly-снарядами. Живёт в room.turrets."""
    def __init__(s, x, y, build):
        s.x, s.y = float(x), float(y)
        s.w, s.h = int(build.get("w", 30)), int(build.get("h", 34))
        s.build = build
        s.maxhp = s.hp = float(build.get("hp", 90))
        s.range = float(build.get("range", 270))
        s.fire_rate = float(build.get("fire_rate", 0.85))
        s.dmg = float(build.get("damage", 12))
        s.projectile = build.get("projectile", "turret_bolt")
        s.cd = 0.3; s.t = 0.0; s.hit_t = -10_000; s.flash = 0.0

    @property
    def rect(s): return pg.Rect(int(s.x), int(s.y), s.w, s.h)
    @property
    def cx(s): return s.x + s.w / 2
    @property
    def cy(s): return s.y + s.h / 2

    def hurt(s, dmg, kb, fx):
        s.hp -= dmg; s.hit_t = pg.time.get_ticks()
        fx.text(str(max(1, int(dmg))), s.cx, s.y)

    def hit(s, dmg, fx_x, fx, kb=60):
        s.hurt(dmg, kb, fx)

    def collides_rect(s, box): return s.rect.colliderect(box)

    def _target(s, mobs):
        best, bd = None, s.range
        for m in mobs:
            if m.hp <= 0: continue
            dd = math.hypot(m.cx - s.cx, m.cy - s.cy)
            if dd < bd: bd, best = dd, m
        return best

    def update(s, dt, w):
        s.t += dt; s.cd -= dt; s.flash = max(0.0, s.flash - dt)
        t = s._target(w.mobs)
        s.aim = t
        if t is not None and s.cd <= 0:
            from projectiles import resolve, Proj
            d = resolve(s.projectile)
            dx, dy = t.cx - s.cx, t.cy - s.cy - 6
            dist = math.hypot(dx, dy) or 1
            sp = d.get("speed", 380)
            w.projs.append(Proj(s.cx, s.y + 4, dx / dist * sp, dy / dist * sp, d, s.dmg, True))
            s.cd = s.fire_rate
            w.fx.flash(s.cx, s.y + 4, 10, [150, 210, 255])

    def draw(s, v):
        body = tuple(int(c) for c in s.build.get("body_color", [95, 130, 170]))
        barrel = tuple(int(c) for c in s.build.get("barrel_color", [40, 50, 65]))
        x, y = int(s.cx), int(s.rect.bottom)
        img = _tex(s.build.get("image"), s.w, s.h)   # нарисованная в редакторе текстура (вкладка «Текстуры»)
        if img:
            v.blit(img, (int(s.x), int(s.y)))
        else:
            pg.draw.circle(v, (30, 34, 44), (x, y - 5), max(6, s.w // 2 - 1))
            pg.draw.circle(v, body, (x, y - 5), max(4, s.w // 2 - 3))
        if getattr(s, "aim", None) is not None:
            ang = math.atan2(s.aim.cy - (y - 8), s.aim.cx - x)
        else:
            ang = -math.pi / 2
        ex = x + math.cos(ang) * 14
        ey = (y - 8) + math.sin(ang) * 14
        pg.draw.line(v, barrel, (x, y - 8), (int(ex), int(ey)), 4)
        pg.draw.circle(v, tuple(int(c) for c in s.build.get("muzzle", [120, 210, 255])), (x, y - 8), 5)
        if s.hp < s.maxhp:   # полоска прочности
            bw = s.w - 6; fill = max(0.0, s.hp / s.maxhp)
            pg.draw.rect(v, (20, 16, 18), (int(s.x + 3), int(s.y - 8), bw, 4))
            pg.draw.rect(v, (110, 200, 255), (int(s.x + 3), int(s.y - 8), int(bw * fill), 4))

# ---------------- отрисовка (в мировых координатах, до пересчёта камеры) ----------------

def draw_world(g, v):
    """Рисует в мировом «холсте» v: постройки (турели), ресурсы с их свечением/подписями (в очках), рецепты над 
    кучкой ресурсов, индикатор крафта. Призрак установки рисует draw_place() поверх всех."""
    pl = g.pl
    for t in getattr(g.room, "turrets", ()):   # постройки инженера — до мобов/героя (они ходят перед ними)
        t.draw(v)
    vision = vision_on(pl)
    for dr in g.room.drops:
        if isinstance(dr, ResourceDrop):
            dr.draw(v, vision)
            if vision: dr.draw_label(v, g.font)
    if vision and not g.crafting and not g.placing:
        radius = float(cfg().get("craft_radius", 170))
        avail = available_recipes(g.room.drops, pl.cx, pl.cy, radius)
        if avail:
            sel = int(getattr(g, "craft_sel", 0)) % len(avail)
            cx, cy = pl.cx, pl.y - 52
            for i, (rid, rc) in enumerate(avail):
                _recip_icon(v, rid, rc, cx + (i - (len(avail) - 1) / 2) * 40, cy, selected=(len(avail) > 1 and i == sel))
            if len(avail) > 1:
                name = avail[sel][1].get("name", avail[sel][0])
                t = g.font.render(f"[F] — создать: {name} ({sel + 1}/{len(avail)}) · колесо мыши — выбор", True, (255, 230, 120))
            else:
                t = g.font.render("Рядом ресурсы: [F] — создать", True, (255, 230, 120))
            v.blit(t, (cx - t.get_width() // 2, cy + 34))
    c = g.crafting
    if c:
        prog = max(0.0, min(1.0, c["t"] / c["max"]))
        r = 26 + int(math.sin(g.pl.t * 8 if hasattr(g.pl, "t") else 0) * 2)
        pg.draw.circle(v, (255, 220, 90), (int(c["x"]), int(c["y"])), int(r * (0.4 + 0.6 * (1 - prog))), 3)
        pg.draw.circle(v, (120, 110, 60), (int(c["x"]), int(c["y"])), 6)
        # полупрозрачный жёлтый круг света
        surf = pg.Surface((r * 2 + 12, r * 2 + 12), pg.SRCALPHA)
        pg.draw.circle(surf, (255, 210, 90, 70), (r + 6, r + 6), r + 4)
        v.blit(surf, (int(c["x"]) - r - 6, int(c["y"]) - r - 6))
        pg.draw.arc(v, (255, 240, 150), (int(c["x"]) - r - 8, int(c["y"]) - r - 8, (r + 8) * 2, (r + 8) * 2),
                    -math.pi / 2, -math.pi / 2 + math.tau * prog, 3)
def draw_place(g, v):
    """Призрак постройки поверх всего мира (зелёный — можно ставить, красный — нельзя)."""
    p = g.placing
    if not p: return
    rect = place_rect(p)
    ok = place_valid(g, rect)
    col = (110, 220, 130) if ok else (230, 90, 90)
    surf = pg.Surface((rect.w + 8, rect.h + 8), pg.SRCALPHA)
    pg.draw.rect(surf, (*col, 80), surf.get_rect(), 3, border_radius=4)
    v.blit(surf, (rect.x - 4, rect.y - 4))
    pg.draw.line(v, col, (rect.centerx, rect.bottom), (rect.centerx, rect.bottom + 10), 2)
    name = (p.get("build") or {}).get("name", "Постройка")
    t = g.font.render(name, True, col)
    v.blit(t, (rect.centerx - t.get_width() // 2, rect.y - 24))

def update(g, dt):
    """Каждый кадр (из Game.step): ведение крафта, режима установки и турелей комнаты."""
    if getattr(g, "crafting", None): update_craft(g, dt)
    if getattr(g, "placing", None): update_place(g, dt)
    r = g.room
    if r and getattr(r, "turrets", None):
        w = SimpleNamespace(g=r.g, mobs=r.mobs, containers=getattr(r, "containers", []),
                            turrets=r.turrets, projs=g.projs, fx=g.fx)
        for t in list(r.turrets):
            t.update(dt, w)
            if t.hp <= 0:
                r.turrets.remove(t)
                g.fx.flash(t.cx, t.cy, 26, [150, 200, 255]); g.fx.ring(t.cx, t.cy, 24)

def cancel(g):
    """Отменить текущий крафт (ресурсы остаются на месте) без текста. Esc в Game.key."""
    if getattr(g, "placing", None): cancel_place(g)
    elif getattr(g, "crafting", None): _cancel_craft(g)

_VISION_IMG = None   # статичная виньетка (не мерцает, в отличие от случайных точек каждый кадр)
def draw_vision_filter(scr):
    """Жёлтый фильтр очков инженера поверх кадра (аппроксимация референса с жёлтым свечением)."""
    global _VISION_IMG
    if _VISION_IMG is None or _VISION_IMG.get_size() != (W, VIEW_H):
        vg = pg.Surface((W, VIEW_H), pg.SRCALPHA)
        vg.fill((255, 214, 70, 34))
        r = int(min(W, VIEW_H) * 0.62)
        dark = (206, 150, 20, 70)
        rng = random.Random(7)
        for _ in range(72):
            x, y = rng.randint(0, W - 1), rng.randint(0, VIEW_H - 1)
            if (x - W / 2) ** 2 + (y - VIEW_H / 2) ** 2 < r * r: continue
            edge = rng.choice([(rng.randint(0, 26), rng.randint(0, VIEW_H)), (rng.randint(W - 27, W - 1), rng.randint(0, VIEW_H)),
                               (rng.randint(0, W), rng.randint(0, 26)), (rng.randint(0, W), rng.randint(VIEW_H - 27, VIEW_H - 1))])
            pg.draw.circle(vg, dark, edge, rng.randint(60, 220))
        _VISION_IMG = vg
    scr.blit(_VISION_IMG, (0, 0))

def _recip_icon(v, rid, rc, x, y, selected=False):
    col = tuple(int(c) for c in rc.get("color", [255, 220, 120]))
    pg.draw.circle(v, (25, 25, 38), (int(x), int(y)), 17)
    pg.draw.circle(v, (255, 240, 160) if selected else col, (int(x), int(y)), 17, 3 if selected else 2)
    if selected:   # выбранный рецепт: яркая внешняя обводка
        pg.draw.circle(v, (255, 240, 160), (int(x), int(y)), 20, 2)
    # миниатюра: для огненного меча — клинок, для турели — башенка
    if rid == "fire_sword":
        pg.draw.line(v, (255, 170, 70), (x - 8, y + 8), (x + 8, y - 8), 3)
        pg.draw.line(v, col, (x - 5, y - 11), (x - 2, y - 7), 3)
    elif rid == "turret":
        pg.draw.rect(v, (150, 200, 255), (int(x - 7), int(y - 3), 14, 10), border_radius=2)
        pg.draw.line(v, (255, 255, 255), (int(x), int(y - 4)), (int(x + 7), int(y - 10)), 3)
    else:
        pg.draw.circle(v, (255, 255, 255), (int(x), int(y)), 6, 2)

# ---------------- телекинез-перчатка (хуки вызываются из spells.py) ----------------

def drag_target(pl, drops, radius, aim):
    """Ближайший к прицелу объект на полу (для перчатки)."""
    best, bd = None, radius
    for dr in drops:
        if not is_grab_drop(dr): continue
        dd = (dr.x - aim[0]) ** 2 + (dr.y - aim[1]) ** 2
        if dd < bd * bd:
            bd, best = math.sqrt(dd), dr
    return best

def drag_spell_start(pl, a, mobs, projs, fx):
    """@spell для telekinesis_drag: схватить ближайший к курсору предмет (ресурс/оружие/артефакт)."""
    from spells import aim_point
    drops = getattr(pl, "drops", [])
    reach = float(a.get("range", 360))
    aim = aim_point(pl, 60)
    if (aim[0] - pl.cx) ** 2 + (aim[1] - pl.cy) ** 2 > reach * reach:
        aim = (pl.cx + sign(aim[0] - pl.cx or 1) * reach, pl.cy + sign(aim[1] - pl.cy or 0) * reach * .4)
    t = drag_target(pl, drops, reach * 1.4, aim)
    if t is None:
        fx.text("Нет предметов рядом для телекинеза", pl.cx, pl.y - 18)
        return False
    fx.ring(t.x, t.y, 22)
    return {"target": t}

def drag_spell_tick(pl, ch, a, dt, mobs, projs, fx):
    """Каждый кадр потока: предмет тянется за курсором (и поднимается чуть выше). False — цель пропала."""
    from spells import CHANNELS, aim_point
    t = ch.get("target")
    drops = getattr(pl, "drops", [])
    if t is None or t not in drops:
        return False
    aim = aim_point(pl, 60)
    dx, dy = aim[0] - t.x, aim[1] - t.y - 14
    dist = math.hypot(dx, dy)
    sp = float(a.get("speed", cfg().get("drag_speed", 540))) * dt
    if dist > 6:
        t.x += min(sp, dist) * (dx / (dist or 1))
        t.y += min(sp, dist) * (dy / (dist or 1))
    if int((getattr(pl, "t", 0.0) * 8)) % 4 == 0:
        fx.ring(t.x, t.y, 18)
    per = float(a.get("mana_per_sec", 0))
    if per > 0:
        pl.mana -= per * dt
        if pl.mana <= 0:
            pl.mana = 0.0; pl.mana_flash = .35
            return False
    return True

def drag_spell_end(pl, ch, a, fx):
    pass
