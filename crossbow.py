"""Мини-арбалеты (герой «Тень»): в каждой руке по арбалету, оружия ближнего боя нет.

ЛКМ стреляет первым арбалетом, ПКМ — вторым; перезарядка у каждого своя, стрелять можно одновременно и на бегу.
Вид снаряда выбирается как навык: у каждого арбалета своя «книга» видов снарядов (предыдущий / текущий / следующий — две вертикальные
колонки у левого края экрана, левая — первый арбалет, правая — второй; смена плавно прокручивает колонку, см. hud.book_draw). Листается клавишами из настроек управления (по умолчанию 1/2 — первый арбалет, 3/4 — второй).

Включается полем "crossbows" героя в data/characters.json (нет поля — модуль ничего не делает):
    "crossbows": {
        "skin": "weapons/mini_crossbow.png", "draw": [36, 20],   # картинка носом вправо и размер на экране
        "grip": [7, 14],            # где рука, px от левого верхнего угла картинки (в размере draw)
        "muzzle": [23, 6],          # откуда вылетает болт: вперёд и вверх от руки, px
        "hands": [[14, -16], [-3, -26]],   # кисти арбалетов (ЛКМ, ПКМ): вперёд по взгляду и вверх от ног героя, px.
                                           # Второй арбалет рисуется ЗА телом (в дальней руке)
        "recoil": 4,                # откат арбалета при выстреле, px
        "ammo": ["ammo_arrow", "ammo_fire", "ammo_heavy"]   # виды снарядов по порядку — навыки category "ammo" из data/skills.json
    }
Вид снаряда — запись в data/skills.json с "category": "ammo": projectile (тип пули из data/projectiles.json), damage, mana_cost,
cooldown (пауза между выстрелами ЭТОГО арбалета, сек), count/spread (залп веером), icon, color, name, description; поля projectile_* — правки
пули (как у заклинаний, см. spells.projectile_spec). Эффекты (горение, заморозка, пробитие) — в самом типе пули в projectiles.json.
Пассивка типа mana_cost_reduction с "mini_crossbow" в списке weapons удешевляет выстрелы.

Стрела с нитью (гарпун): вид снаряда с полем "hook" (см. ammo_harpoon в skills.json). Выстрел выпускает гарпун на нити: он летит ровной дугой с
плавным снижением (gravity) до стены/потолка (в моба — бьёт и пропадает), цепляется и подтягивает героя; из одного арбалета — один гарпун (пока он
в деле, этот арбалет не стреляет), но можно по одному из каждого. Нить держится, пока ЗАЖАТА кнопка арбалета (hold_to_keep): отпустил — гарпун убран
(в полёте — отменён); Пробел (или перекат/лестница) тоже отцепляет, скорость сохраняется. Верёвка — ограничение длины: герой висит и раскачивается
как маятник (в воздухе A/D раскачивают) и сам подтягивается до swing_len.
Поля "hook" (все необязательны, умолчания — HOOK_DEFAULT): speed, gravity (снижение полёта, px/с²), range (дальность полёта), swing_len, min_len,
reel_speed, swing_force, damp, knockback, hit_stop (стоп-кадр от попадания гарпуна в моба, по умолчанию 0), hold_to_keep (false — нить остаётся до Пробела; тогда зажатая кнопка подтягивает до min_len),
skin + draw [w, h] (наконечник — картинка в assets), thread_skin + thread_width (нить — картинка-полоска в assets, тайлится вдоль нити; нет файла —
рисуется линия thread_color с обводкой thread_outline). Состояние: pl.hooks[i] (None или {sid, st: "fly"/"hold", x, y, vx, vy, dist, len}),
pl.xb_held[i] (кнопка зажата), pl.xb_lock[i] (ждём отпускания кнопки).

Состояние игрока: xb_ammo[i] — индекс вида снаряда, xb_cd[i] — осталось до следующего выстрела, xb_kick[i] — отдача (для рисования),
xb_notice[i] — «только что переключили» (подсветка в HUD). Сеть: net_pack / net_apply (хост шлёт в снимке игрока ключ "xb")."""
import math
import pygame as pg
from core import CFG, T, solid, sign
from anim import sprite, image, ASSETS_EXISTS
from projectiles import volley
from spells import projectile_spec
import invisibility

SIDES = 2                   # сколько арбалетов: ЛКМ и ПКМ
KEYS = ("a1", "a2")         # какие кнопки (буфер Player.buf) стреляют каким арбалетом
KICK_TIME = 0.14            # длительность отдачи, сек
PASSIVE_ID = "mini_crossbow"   # так арбалет называется в списке weapons у пассивок mana_cost_reduction


def cfg():
    return CFG.get("character", {}).get("crossbows") or {}


def enabled():
    """Есть ли арбалеты у текущего героя (CFG["character"])."""
    return bool(cfg())


def init(pl):
    """Поля арбалетов на игроке (нужны всем героям — чтобы сетевой снимок и HUD не падали)."""
    pl.xb_ammo = [0] * SIDES; pl.xb_cd = [0.0] * SIDES; pl.xb_kick = [0.0] * SIDES; pl.xb_notice = [0.0] * SIDES
    pl.hooks = [None] * SIDES; pl.xb_held = [False] * SIDES; pl.xb_lock = [False] * SIDES


def ammo_ids():
    """Виды снарядов героя по порядку (только существующие в skills.json)."""
    defs = CFG.get("skills", {})
    return [sid for sid in cfg().get("ammo", []) if sid in defs]


def current(pl, i):
    """id вида снаряда, который сейчас заряжен в арбалет i (или None)."""
    ids = ammo_ids()
    return ids[pl.xb_ammo[i] % len(ids)] if ids else None


def book(pl, i):
    """(предыдущий, текущий, следующий) виды снарядов арбалета i для колонки в HUD. При малом числе видов бывают повторы."""
    ids = ammo_ids()
    if not ids: return (None, None, None)
    n = len(ids); k = pl.xb_ammo[i] % n
    return (ids[(k - 1) % n], ids[k], ids[(k + 1) % n])


def swap(pl, i, direction=1):
    """Листает виды снарядов арбалета i (direction: +1 — следующий, -1 — предыдущий). Перезарядку не сбрасывает."""
    ids = ammo_ids()
    if not enabled() or not ids or not 0 <= i < SIDES: return False
    pl.xb_ammo[i] = (pl.xb_ammo[i] + direction) % len(ids)
    pl.xb_notice[i] = 1.0
    return True


def mana_cost(pl, sid):
    """Цена выстрела выбранным снарядом с учётом пассивок «экономия маны» для арбалетов."""
    cost = max(0.0, float(CFG.get("skills", {}).get(sid, {}).get("mana_cost", 0.0)))
    for pid in getattr(pl, "skills", []):
        p = CFG.get("skills", {}).get(pid, {})
        if p.get("type") == "mana_cost_reduction" and PASSIVE_ID in p.get("weapons", []):
            cost *= max(0.0, 1.0 - float(p.get("amount", 0)))
    return cost


def tick(pl, dt):
    """Каждый кадр: тают перезарядка, отдача и подсветка переключения."""
    for i in range(SIDES):
        pl.xb_cd[i] = max(0.0, pl.xb_cd[i] - dt)
        pl.xb_kick[i] = max(0.0, pl.xb_kick[i] - dt)
        pl.xb_notice[i] = max(0.0, pl.xb_notice[i] - dt)


def cooldown_total(pl, i):
    """Полная пауза выбранного снаряда (для сектора перезарядки в HUD)."""
    sid = current(pl, i)
    return max(0.01, float(CFG.get("skills", {}).get(sid, {}).get("cooldown", 0.3))) if sid else 0.3


def ready(pl, i):
    sid = current(pl, i)
    return bool(sid) and pl.xb_cd[i] <= 0 and pl.mana >= mana_cost(pl, sid)


# ---------------- геометрия ----------------

def hand_pos(pl, i):
    """Где в мире кисть, держащая арбалет i (по взгляду героя)."""
    hands = cfg().get("hands") or [[14, -16], [-3, -26]]
    hx, hy = hands[min(i, len(hands) - 1)]; r = pl.rect
    return (r.centerx + pl.face * hx, r.bottom + hy)


def aim_angle(pl, i):
    """Угол выстрела арбалета i (радианы, как у atan2 в мире): на курсор; без прицела мыши — по взгляду героя."""
    hx, hy = hand_pos(pl, i)
    if pl.aim: return math.atan2(pl.aim[1] - hy, pl.aim[0] - hx)
    return 0.0 if pl.face > 0 else math.pi


def muzzle(pl, i):
    """(x, y, угол) — откуда и куда вылетает болт арбалета i."""
    hx, hy = hand_pos(pl, i); a = aim_angle(pl, i)
    fw, up = cfg().get("muzzle", [23, 6])
    ux, uy = math.cos(a), math.sin(a); side = 1 if pl.face > 0 else -1
    px, py = uy * side, -ux * side            # «верх» арбалета (картинку при взгляде влево зеркалят, верх остаётся верхом)
    return (hx + ux * fw + px * up, hy + uy * fw + py * up, a)


# ---------------- выстрел ----------------

def fire(pl, i, projs, fx):
    """Выстрел арбалета i. Возвращает: "ok" — выстрелил; "cd" — ещё перезаряжается (нажатие можно держать в буфере);
    "mana" — не хватило маны (полоска мигнёт); "none" — нечем стрелять."""
    sid = current(pl, i)
    a = CFG.get("skills", {}).get(sid) if sid else None
    if not a: return "none"
    if pl.xb_cd[i] > 0: return "cd"
    cost = mana_cost(pl, sid)
    if pl.mana < cost:
        pl.mana_flash = .35
        return "mana"
    x, y, ang = muzzle(pl, i)
    if a.get("hook"):                          # стрела с нитью: не снаряд, а гарпун на верёвке
        sp = hook_cfg(sid)["speed"]
        pl.hooks[i] = {"sid": sid, "st": "fly", "x": x, "y": y, "vx": math.cos(ang) * sp, "vy": math.sin(ang) * sp, "dist": 0.0, "len": 0.0}
        pl.mana -= cost; pl.mana_t = CFG["player"].get("mana", {}).get("regen_delay", .9)
        pl.xb_cd[i] = max(0.0, float(a.get("cooldown", 0.3))); pl.xb_kick[i] = KICK_TIME; pl.xb_lock[i] = True
        invisibility.on_attack(pl, fx)
        return "ok"
    volley(projs, projectile_spec(dict(a, _sid=sid)), x, y, ang, a.get("damage", 10) * pl.dmg_mult(), True, a.get("count", 1), a.get("spread", 0))
    pl.mana -= cost
    pl.mana_t = CFG["player"].get("mana", {}).get("regen_delay", .9)
    pl.xb_cd[i] = max(0.0, float(a.get("cooldown", 0.3)))
    pl.xb_kick[i] = KICK_TIME
    invisibility.on_attack(pl, fx)            # выстрел из невидимости снимает эффект
    return "ok"


# ---------------- гарпуны (стрела с нитью) ----------------

HOOK_DEFAULT = {"speed": 1000, "gravity": 320, "range": 560, "swing_len": 160, "min_len": 56, "reel_speed": 560, "swing_force": 1200, "damp": 0.25,
                "max_speed": 1500, "hold_to_keep": True, "knockback": 80, "hit_stop": 0,
                "skin": "projectiles/xbow_hook.png", "draw": [34, 13],
                "thread_skin": "projectiles/xbow_thread.png", "thread_width": 4, "thread_color": [222, 214, 188], "thread_outline": [24, 18, 26]}


def hook_cfg(sid):
    """Параметры гарпуна вида снаряда sid: умолчания + поле "hook" из skills.json."""
    d = dict(HOOK_DEFAULT); d.update(CFG.get("skills", {}).get(sid, {}).get("hook") or {})
    return d


def trigger(pl, i, projs, fx):
    """Нажатие кнопки арбалета i: если у него гарпун в деле или кнопку не отпускали после гарпуна — выстрела нет; иначе fire()."""
    if pl.hooks[i]:
        pl.xb_lock[i] = True; return "busy"
    if pl.xb_lock[i]: return "locked"
    return fire(pl, i, projs, fx)


def end_hook(pl, i):
    """Гарпун i убран (отцепили, промах, попал в моба): арбалет уходит на перезарядку."""
    h = pl.hooks[i]; pl.hooks[i] = None
    if h: pl.xb_cd[i] = max(pl.xb_cd[i], float(CFG.get("skills", {}).get(h.get("sid"), {}).get("cooldown", 0.3)))


def hold_check(pl, i):
    """Нить держится, пока зажата кнопка арбалета (hold_to_keep): кнопку отпустили — гарпун убран (в полёте — отменён)."""
    h = pl.hooks[i]
    if h and not pl.xb_held[i] and hook_cfg(h["sid"])["hold_to_keep"]: end_hook(pl, i)


def release_all(pl):
    """Отцепить все гарпуны (Пробел, перекат, лестница, смена комнаты)."""
    for i in range(SIDES):
        if pl.hooks[i]: end_hook(pl, i)


def roped(pl):
    """Висит ли герой хотя бы на одном зацепившемся гарпуне."""
    return any(h and h.get("st") == "hold" for h in pl.hooks)


def swinging(pl):
    """Раскачивается в воздухе на верёвке: обычное управление в воздухе отключено, A/D раскачивают (rope_step)."""
    return roped(pl) and not pl.ground


def hooks_update(pl, dt, g, mobs, fx):
    """Полёт гарпунов (шагами по 6 px, чтобы не пролетать стены), зацеп за тайлы, попадание в мобов, проверка якоря."""
    for i, h in enumerate(pl.hooks):
        if not h: continue
        a = CFG.get("skills", {}).get(h["sid"])
        if not a or not enabled(): pl.hooks[i] = None; continue
        c = hook_cfg(h["sid"])
        if h["st"] == "hold":
            if not solid(g, int(h["x"] // T), int(h["y"] // T)): end_hook(pl, i)   # якорь пропал (дверь открылась, другая комната)
            continue
        sp = math.hypot(h["vx"], h["vy"]); total = sp * dt; n = max(1, math.ceil(total / 6)); sub = dt / n
        for _ in range(n):
            h["vy"] += c["gravity"] * sub                      # плавное снижение: гарпун летит дугой
            sx, sy = h["vx"] * sub, h["vy"] * sub
            h["x"] += sx; h["y"] += sy; h["dist"] += math.hypot(sx, sy)
            if solid(g, int(h["x"] // T), int(h["y"] // T)):
                h["st"] = "hold"; h["len"] = math.hypot(pl.cx - h["x"], pl.cy - h["y"]); fx.ring(h["x"], h["y"], 12)
                break
            box = pg.Rect(int(h["x"]) - 4, int(h["y"]) - 4, 8, 8); hit = None
            for m in mobs:
                if getattr(m, "hp", 1) > 0 and (m.collides_rect(box) if hasattr(m, "collides_rect") else box.colliderect(m.rect)): hit = m; break
            if hit is not None:   # в моба: ударил и пропал (цепляется только за стены, пол и потолок)
                stop = fx.stop
                hit.hurt(a.get("damage", 5) * pl.dmg_mult(), (sign(h["vx"]) or 1) * float(c["knockback"]), fx)
                fx.stop = max(stop, float(c["hit_stop"]))   # стоп-кадр от попадания гарпуна (по умолчанию без него)
                end_hook(pl, i); break
            if h["dist"] >= c["range"]: end_hook(pl, i); break


def rope_step(pl, dt, d):
    """Верёвка перед Body.move: подтягивание, раскачивание A/D и ограничение длины (скорость подправляется так, чтобы шаг лёг на окружность).
    d — ввод A/D (-1/0/1). Подтягивается до swing_len сама; пока зажата кнопка арбалета — до min_len; длина только укорачивается."""
    live = [(i, h) for i, h in enumerate(pl.hooks) if h and h.get("st") == "hold"]
    if not live or dt <= 0: return
    c0 = hook_cfg(live[0][1]["sid"])
    if not pl.ground:
        if d: pl.vx += d * c0["swing_force"] * dt
        pl.vx *= max(0.0, 1 - c0["damp"] * dt)
    for i, h in live:
        c = hook_cfg(h["sid"]); px, py = pl.cx, pl.cy
        dist = math.hypot(px - h["x"], py - h["y"])
        floor = c["min_len"] if (pl.xb_held[i] and not c["hold_to_keep"]) else max(c["min_len"], c["swing_len"])
        reeling = h["len"] > floor
        if reeling: h["len"] = max(floor, min(h["len"], dist) - c["reel_speed"] * dt)
        if reeling and h["len"] <= floor and dist > 1e-6:   # подтяжка закончилась: гасим скорость «внутрь», чтобы герой не пролетел мимо рабочей длины (боковая скорость — маятник — остаётся)
            rx, ry = (px - h["x"]) / dist, (py - h["y"]) / dist; vr = pl.vx * rx + pl.vy * ry
            if vr < 0: pl.vx -= vr * rx * 0.9; pl.vy -= vr * ry * 0.9
        nx, ny = px + pl.vx * dt, py + pl.vy * dt
        dx, dy = nx - h["x"], ny - h["y"]; dd = math.hypot(dx, dy)
        if dd > h["len"] and dd > 1e-6:
            k = h["len"] / dd
            pl.vx, pl.vy = (h["x"] + dx * k - px) / dt, (h["y"] + dy * k - py) / dt
    sp = math.hypot(pl.vx, pl.vy)
    if sp > c0["max_speed"]: pl.vx, pl.vy = pl.vx * c0["max_speed"] / sp, pl.vy * c0["max_speed"] / sp


def _thread(v, pts, c):
    """Рисует нить по ломаной pts: картинка-полоска thread_skin (тайлится вдоль нити) или, если файла нет, линия цветом thread_color с обводкой."""
    w = max(1, int(c["thread_width"])); path = c.get("thread_skin")
    tex = image(path) if path and ASSETS_EXISTS(path) else None
    if tex is None:
        pg.draw.lines(v, tuple(c["thread_outline"]), False, pts, w + 2); pg.draw.lines(v, tuple(c["thread_color"]), False, pts, max(1, w - 2)); return
    tw = max(1, tex.get_width()); strip = sprite(path, tw, w)
    if strip is None: return
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        ln = math.hypot(x1 - x0, y1 - y0)
        if ln < 1: continue
        seg = pg.Surface((max(1, int(math.ceil(ln))), w), pg.SRCALPHA); x = 0
        while x < ln: seg.blit(strip, (x, 0)); x += tw
        rot = pg.transform.rotate(seg, -math.degrees(math.atan2(y1 - y0, x1 - x0)))
        v.blit(rot, rot.get_rect(center=((x0 + x1) / 2, (y0 + y1) / 2)))


def draw_hooks(v, pl):
    """Нить от арбалета до гарпуна (в полёте — ровная, на зацепе провисает, если ослабла) и наконечник гарпуна; вид нити и наконечника — картинки в assets (hook в skills.json)."""
    for i, h in enumerate(pl.hooks):
        if not h: continue
        x0, y0, _ = muzzle(pl, i); x1, y1 = h["x"], h["y"]
        c = hook_cfg(h.get("sid") or current(pl, i)); dist = math.hypot(x1 - x0, y1 - y0)
        sag = min(36.0, max(0.0, (h.get("len") or 0) - dist) * 0.5) if h.get("st") == "hold" else 0.0
        n = 12 if sag >= 1 else 1   # натянутая нить — один ровный отрезок
        pts = [(x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n + 4 * sag * (k / n) * (1 - k / n)) for k in range(n + 1)]
        _thread(v, pts, c)
        dw, dh = c["draw"]
        a = math.atan2(h["vy"], h["vx"]) if h.get("st") == "fly" and "vx" in h else math.atan2(y1 - y0, x1 - x0)   # в полёте наконечник смотрит по дуге
        img = sprite(c["skin"], dw, dh, angle=round(-math.degrees(a) / 6) * 6)
        if img: v.blit(img, img.get_rect(center=(int(x1), int(y1))))
        else: pg.draw.circle(v, (210, 215, 230), (int(x1), int(y1)), 5)


# ---------------- рисование ----------------

def draw(v, pl, i):
    """Рисует арбалет i в руке героя, повёрнутый на курсор (картинка носом вправо, при взгляде влево зеркалится)."""
    c = cfg(); path = c.get("skin", "weapons/mini_crossbow.png")
    dw, dh = c.get("draw", [36, 20]); gx, gy = c.get("grip", [7, 14]); f = pl.face
    hx, hy = hand_pos(pl, i); a = aim_angle(pl, i)
    kick = float(c.get("recoil", 4)) * max(0.0, pl.xb_kick[i]) / KICK_TIME   # отдача: арбалет откатывается назад по стволу
    hx -= math.cos(a) * kick; hy -= math.sin(a) * kick
    ang = math.degrees(math.atan2(-math.sin(a), math.cos(a)))                # угол вверх-положительный, как у Player.aim_deg
    ang = ang if f > 0 else 180 - ang
    ang = (ang + 180) % 360 - 180
    q = round((ang if f > 0 else -ang) / 5) * 5                               # шаг 5° — меньше вариантов в кэше картинок
    img = sprite(path, dw, dh, f < 0, False, q)
    if not img:                                                               # нет картинки — простая заглушка из линий
        ex, ey = hx + math.cos(a) * 22, hy + math.sin(a) * 22
        pg.draw.line(v, (30, 20, 20), (hx, hy), (ex, ey), 6); pg.draw.line(v, (150, 100, 56), (hx, hy), (ex, ey), 4)
        return
    th = math.radians(q); vx, vy = (gx if f > 0 else dw - gx) - dw / 2, gy - dh / 2
    rx, ry = vx * math.cos(th) + vy * math.sin(th), -vx * math.sin(th) + vy * math.cos(th)
    v.blit(img, img.get_rect(center=(int(hx - rx), int(hy - ry))))


# ---------------- сеть ----------------

def net_pack(pl):
    """В снимок игрока: [[индекс снаряда, перезарядка, гарпун], ...] по арбалетам; гарпун — None или [0 летит / 1 цепляет, x, y, длина верёвки]."""
    out = []
    for i in range(SIDES):
        h = pl.hooks[i] if pl.hp > 0 else None
        out.append([int(pl.xb_ammo[i]), round(max(0.0, pl.xb_cd[i]), 2),
                    None if not h else [0 if h["st"] == "fly" else 1, round(h["x"]), round(h["y"]), round(h.get("len") or 0)]])
    return out


def net_apply(pl, xb, local=False):
    """Применить пришедшее от хоста. local — свой герой с предсказанием: перезарядку и гарпуны считаем у себя (у остальных гарпун — «картинка»)."""
    if not isinstance(xb, list): return
    for i, item in enumerate(xb[:SIDES]):
        try: idx, cd = int(item[0]), float(item[1])
        except (TypeError, ValueError, IndexError): continue
        pl.xb_ammo[i] = idx
        if local: continue
        pl.xb_cd[i] = cd
        hk = item[2] if len(item) > 2 else None
        try: pl.hooks[i] = None if not hk else {"sid": current(pl, i), "st": "fly" if int(hk[0]) == 0 else "hold", "x": float(hk[1]), "y": float(hk[2]), "len": float(hk[3])}
        except (TypeError, ValueError, IndexError): pl.hooks[i] = None
