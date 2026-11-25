"""Паттерны атак мобов. В mobs.json: "attacks": [{"type": "melee", ...}, {"type": "shoot", ...}] — моб берёт первую
атаку из списка, которая перезарядилась и до игрока подходящее расстояние.

Каждая атака идёт фазами: windup (замах, моб мигает) -> active (удар) -> recovery (отдых).
Общие параметры: windup, active, recovery (секунды), cooldown (перезарядка этой атаки), damage, knockback,
range / min_range (с какого расстояния до игрока атакует), range_y (допустимая разница по высоте),
mobile (true — продолжает двигаться по своему паттерну во время атаки), interrupt (false — удар не сбивает замах),
id + next (после этой атаки сразу начать атаку с таким id — комбо), anims {"windup": "имя", "attack": "имя", ...} —
свои анимации на фазы этой атаки.

Новая атака = класс-наследник Attack с декоратором @attack("имя"); переопредели нужные методы."""
import math, random
import pygame as pg
from core import T, MW, free, sign, floor_below, circle_hits_rect, tile, CFG
from projectiles import volley
from invisibility import visible_only
from zones import Zone

ATTACKS = {}
def attack(name):
    def reg(cls): ATTACKS[name] = cls(); return cls
    return reg

def players_of(w):
    """Все живые игроки (мультиплеер: w.players) или единственный w.pl. Плюс живые клоны героев (clone.py):
    их задевают вражеские melee-зоны (hit_zone / boss_hands), за ними гонятся вражеские снаряды."""
    base = list(getattr(w, "players", None) or [w.pl])
    return base + [c for c in getattr(w, "clones", ()) if getattr(c, "hp", 0) > 0]

def seen_players(w):
    """Игроки, которых мобы могут заметить (без невидимых) — для агра; урон по зоне бьёт всех (players_of)."""
    return visible_only(players_of(w))

def hit_player(m, a, w, from_x=None, target=None):
    (target or w.pl).hit(a.get("damage", 10) * m.dmg_scale, m.cx if from_x is None else from_x, w.fx, a.get("knockback", 260))

def hit_zone(m, a, act, w, touches, from_x=None):
    """Бьёт каждого игрока, которого задевает зона (touches(rect) -> bool), не больше одного раза за атаку."""
    done = act.setdefault("hit_ids", set())
    for p in players_of(w):
        if id(p) in done or not touches(p.rect): continue
        done.add(id(p)); act["hit"] = True; hit_player(m, a, w, from_x, p)

class Attack:
    range = 60; range_y = 60; active_time = .12
    def default_range(s, m, a): return s.range
    def can_use(s, m, a, w):
        dx, dy = w.pl.cx - m.cx, w.pl.cy - m.cy
        return a.get("min_range", 0) <= math.hypot(dx, dy) <= a.get("range", s.default_range(m, a)) and abs(dy) <= a.get("range_y", s.range_y)
    def start(s, m, a, act, w): pass                       # начало замаха
    def windup(s, m, a, act, dt, w): pass                  # каждый кадр замаха
    def begin(s, m, a, act, w): pass                       # замах кончился, удар начался
    def active(s, m, a, act, dt, w):                       # каждый кадр удара; True — удар закончен
        return act["t"] >= a.get("active", s.active_time)
    def anim(s, m, a, act): return "attack"                # имя анимации для фазы active
    def draw(s, m, a, act, v): pass                        # подсказки на экране (зоны поражения)

@attack("melee")
class Melee(Attack):
    """Удар перед собой. reach [w, h] — зона удара перед мобом, lunge — рывок вперёд при ударе."""
    def default_range(s, m, a): return a.get("reach", [44, 30])[0] + m.w / 2 + 6
    def box(s, m, a):
        rw, rh = a.get("reach", [44, 30])
        return pg.Rect(int(m.x + m.w if m.dir > 0 else m.x - rw), int(m.cy - rh / 2), rw, rh)
    def begin(s, m, a, act, w): m.vx = m.dir * a.get("lunge", 0)
    def active(s, m, a, act, dt, w):
        act["box"] = s.box(m, a)
        hit_zone(m, a, act, w, act["box"].colliderect)
        return super().active(m, a, act, dt, w)
    def draw(s, m, a, act, v):
        if act["phase"] == "active": pg.draw.rect(v, (255, 120, 90), s.box(m, a), 2)

@attack("circle")
class Circle(Attack):
    """Удар по кругу. radius — радиус, center: "self" — вокруг себя (по умолчанию), "player" — круг ложится туда,
    где игрок был в начале замаха. На замахе рисуется зона поражения."""
    range_y = 999
    def default_range(s, m, a): return a.get("radius", 80) * .9 if a.get("center", "self") == "self" else 320
    def center(s, m, a, act): return act["c"] if a.get("center", "self") == "player" else (m.cx, m.cy)
    def start(s, m, a, act, w): act["c"] = (w.pl.cx, w.pl.cy)
    def begin(s, m, a, act, w):
        x, y = s.center(m, a, act); w.fx.ring(x, y, a.get("radius", 80)); w.fx.shake = max(w.fx.shake, .12)
    def active(s, m, a, act, dt, w):
        x, y = s.center(m, a, act); rad = a.get("radius", 80)
        hit_zone(m, a, act, w, lambda r: circle_hits_rect(x, y, rad, r), x)
        return super().active(m, a, act, dt, w)
    def draw(s, m, a, act, v):
        x, y = map(int, s.center(m, a, act)); r = a.get("radius", 80)
        if act["phase"] == "windup":
            k = min(1, act["t"] / max(.01, a.get("windup", .5)))
            pg.draw.circle(v, (170, 50, 50), (x, y), r, 1); pg.draw.circle(v, (230, 80, 70), (x, y), max(2, int(r * k)), 2)
        elif act["phase"] == "active": pg.draw.circle(v, (255, 150, 90), (x, y), r, 3)

@attack("shoot")
class Shoot(Attack):
    """Стрельба. projectile — тип пули из data/projectiles.json (или описание на месте), count + spread — веер
    (градусы между пулями), burst + burst_gap — очередь из нескольких залпов, aim: "player" (в игрока),
    "forward" (горизонтально), "ring" (по кругу, spread = 360/count), "angle" (+ "angle": градусы, 0 — вперёд, -90 — вверх),
    offset [x, y] — откуда вылетает пуля относительно центра моба (x — в сторону взгляда)."""
    range = 420; range_y = 260
    def begin(s, m, a, act, w): act["shots"], act["next"] = 0, 0.0
    def fire(s, m, a, w):
        ox, oy = a.get("offset", [8, -4]); x, y = m.cx + ox * m.dir, m.cy + oy
        aim, n = a.get("aim", "player"), a.get("count", 1); spread = a.get("spread", 0)
        if aim == "forward": ang = 0 if m.dir > 0 else math.pi
        elif aim == "ring": ang, spread = math.radians(a.get("angle", 0)), 360 / n
        elif aim == "angle": ang = math.radians(a.get("angle", 0)); ang = ang if m.dir > 0 else math.pi - ang
        else: ang = math.atan2(w.pl.cy - y, w.pl.cx - x)
        volley(w.projs, a.get("projectile", "bolt"), x, y, ang, a.get("damage", 10) * m.dmg_scale, False, n, spread)
    def active(s, m, a, act, dt, w):
        burst = a.get("burst", 1)
        while act["shots"] < burst and act["t"] >= act["next"]:
            m.dir = sign(w.pl.cx - m.cx) or m.dir; s.fire(m, a, w)
            act["shots"] += 1; act["next"] += a.get("burst_gap", .15)
        return act["shots"] >= burst and act["t"] >= a.get("active", .05)

@attack("leap")
class Leap(Attack):
    """Прыжок к игроку с ударом при приземлении. Моб прыгает не на игрока, а на землю рядом с ним — со своей стороны.
    land_offset — на каком расстоянии от игрока приземлиться, air_time — время в полёте (чем больше, тем выше дуга),
    radius — радиус удара при приземлении, gravity — гравитация прыжка, track (true) — пока замах, цель следует за игроком.
    Летающий моб вместо прыжка делает рывок по прямой. Место приземления видно на замахе."""
    range = 300; range_y = 220
    def can_use(s, m, a, w):
        return (m.flies or m.ground) and a.get("min_range", 60) <= abs(w.pl.cx - m.cx) <= a.get("range", s.range) \
            and abs(w.pl.cy - m.cy) <= a.get("range_y", s.range_y)
    def target(s, m, a, w):
        pl, g = w.pl, w.g; off = a.get("land_offset", 40); side = sign(m.cx - pl.cx) or -m.dir
        for sd in (side, -side):
            tx = max(T + m.w / 2 + 2, min(MW - T - m.w / 2 - 2, pl.cx + sd * off))
            if m.flies: return tx, pl.cy
            ty = floor_below(g, tx, pl.y + pl.h - 6) or floor_below(g, tx, pl.cy)
            if ty and free(g, pg.Rect(int(tx - m.w / 2), int(ty - m.h), m.w, m.h)): return tx, ty
        return pl.cx, pl.y + pl.h
    def start(s, m, a, act, w): act["to"] = s.target(m, a, w)
    def windup(s, m, a, act, dt, w):
        if a.get("track", True): act["to"] = s.target(m, a, w)
    def begin(s, m, a, act, w):
        tx, ty = act["to"]; tt = a.get("air_time", .6); act["free"] = True; m.dir = sign(tx - m.cx) or m.dir
        if m.flies: m.vx, m.vy = (tx - m.cx) / tt, (ty - m.cy) / tt; return
        gr = a.get("gravity", 1800); dy = (ty - m.h) - m.y
        m.vx, m.vy = (tx - m.cx) / tt, (dy - .5 * gr * tt * tt) / tt; m.grav = gr; m.ground = False
    def active(s, m, a, act, dt, w):
        tt = a.get("air_time", .6)
        landed = act["t"] >= tt if m.flies else (act["t"] > .08 and m.ground)
        if not (landed or act["t"] > tt * 2.5): return False
        act["free"] = False; m.vx = 0; m.grav = None
        if m.flies: m.vy = 0
        r = a.get("radius", 60); x, y = m.cx, m.y + m.h - 4
        w.fx.ring(x, y, r); w.fx.shake = max(w.fx.shake, .2)
        hit_zone(m, a, act, w, lambda rect: circle_hits_rect(x, y, r, rect))
        return True
    def anim(s, m, a, act): return "jump"
    def draw(s, m, a, act, v):
        if act["phase"] != "windup" or "to" not in act: return
        tx, ty = map(int, act["to"]); r = a.get("radius", 60)
        if m.flies: pg.draw.circle(v, (230, 80, 70), (tx, ty), 10, 2); return
        pg.draw.line(v, (230, 80, 70), (tx - r, ty - 1), (tx + r, ty - 1), 2)
        pg.draw.polygon(v, (230, 80, 70), [(tx, ty - 6), (tx - 6, ty - 16), (tx + 6, ty - 16)])

@attack("dash")
class Dash(Attack):
    """Рывок через комнату: на замахе моб целится, затем летит по горизонтали и сносит игроков.
    speed — скорость рывка, dist — наибольшая длина рывка, stop_on_wall (true) — об стену рывок заканчивается.
    Земной не срывается с края, летун летит по прямой. Урон — всем, кого задел корпус (не больше раза за атаку)."""
    range = 420; range_y = 70
    def start(s, m, a, act, w): act["gone"] = 0.0
    def begin(s, m, a, act, w):
        act["free"] = True; m.dir = sign(w.pl.cx - m.cx) or m.dir
        m.vx = m.dir * a.get("speed", 620)
        if m.flies: m.vy = 0
        w.fx.ring(m.cx, m.cy, 20); w.fx.shake = max(w.fx.shake, .1)
    def active(s, m, a, act, dt, w):
        act["gone"] += abs(m.vx) * dt
        hit_zone(m, a, act, w, m.rect.colliderect)
        stop = False
        d = m.dir
        if not free(w.g, m.rect.move(d * 6, 0)): stop = True        # стена
        elif a.get("stop_on_wall", True) and not m.flies:
            ahead = int((m.cx + d * (m.w / 2 + 6)) // T); foot = int((m.y + m.h + 4) // T)
            if m.ground and tile(w.g, ahead, foot) not in "#=D": stop = True   # край — земной не срывается
        if act["gone"] >= a.get("dist", 380) or act["t"] > 2.0: stop = True
        if stop:
            act["free"] = False
            if not m.flies: m.vy = 0
            return True
        return False
    def draw(s, m, a, act, v):
        if act["phase"] == "windup":
            d = sign(w.pl.cx - m.cx) or m.dir; ln = a.get("dist", 380)
            pg.draw.line(v, (230, 80, 70), (m.cx, m.cy), (m.cx + d * ln, m.cy), 2)
        elif act["phase"] == "active":
            pg.draw.rect(v, (255, 120, 90), m.rect, 2)

@attack("beam")
class Beam(Attack):
    """Луч: на замахе моб наводит линию до стены, затем вся она наносит урон. width — толщина луча,
    track (true) — на замахе линия следует за игроком; если выключить — цель фиксируется в начале замаха."""
    range = 470; range_y = 60
    def cast(s, m, g):
        """Прямая до стены: (x начала, x конца, y) в px."""
        step = m.dir; c0, r0 = int(m.cx // T), int(m.cy // T)
        n = 0
        while n < 60:
            c = c0 + step * (n + 1)
            if not (0 <= c < MW // T) or tile(g, c, r0) in "#=D": break
            n += 1
        x0, x1 = m.cx + step * 8, (c0 + step * (n + 1)) * T + (T if step > 0 else 0)
        if step < 0: x0, x1 = x0, min(x1, c0 * T)
        return x0, x1, m.cy
    def box(s, m, a, g):
        x0, x1, y = s.cast(m, g); hw = a.get("width", 14) / 2
        return pg.Rect(int(min(x0, x1)), int(y - hw), int(abs(x1 - x0)), int(a.get("width", 14)))
    def start(s, m, a, act, w): act["row"] = int(w.pl.cy // T) if a.get("track", True) else int(m.cy // T)
    def windup(s, m, a, act, dt, w):
        if a.get("track", True) and abs(w.pl.cy - m.cy) <= a.get("range_y", s.range_y): pass   # цель следует за игроком по высоте
    def active(s, m, a, act, dt, w):
        box = s.box(m, a, w.g); act["box"] = box
        hit_zone(m, a, act, w, box.colliderect)
        return act["t"] >= a.get("active", .3)
    def draw(s, m, a, act, v):
        if act["phase"] == "windup":
            x0, x1, y = s.cast(m, w.g); pg.draw.line(v, (190, 80, 80), (x0, y), (x1, y), 1)
        elif act["phase"] == "active":
            box = act.get("box") or s.box(m, a, w.g)
            pg.draw.rect(v, (255, 220, 180), box); pg.draw.rect(v, (255, 120, 90), box, 2)

@attack("bomb")
class Bomb(Attack):
    """Бомба: на замахе моб целится в точку игрока (растущий круг), затем бросок — взрыв в точке падения
    и лужа (zones.py): zone_radius, zone_dps — урон в секунду, zone_life — сколько секунд живёт."""
    range = 380; range_y = 260
    def target(s, m, a, w):
        x = max(T, min(MW - T, w.pl.cx)); gy = floor_below(w.g, x, int(w.pl.y + w.pl.h - 6)) or int(w.pl.cy)
        return x, gy
    def start(s, m, a, act, w): act["to"] = s.target(m, a, w)
    def windup(s, m, a, act, dt, w):
        if a.get("track", True): act["to"] = s.target(m, a, w)
    def begin(s, m, a, act, w):
        x, y = act["to"]; r = a.get("radius", 60)
        w.fx.ring(x, y, r); w.fx.shake = max(w.fx.shake, .12)
        hit_zone(m, a, act, w, lambda rect: circle_hits_rect(x, y, r, rect), x)
        zr = a.get("zone_radius", 0)
        if zr and getattr(w, "zones", None) is not None:   # лужа (zones.py) — в реальный список комнаты
            w.zones.append(Zone(a.get("zone", "acid"), x, y, zr,
                                a.get("zone_dps", 10), a.get("zone_life", 4)))
    def draw(s, m, a, act, v):
        if act["phase"] != "windup" or "to" not in act: return
        x, y = map(int, act["to"]); r = a.get("radius", 60)
        k = min(1, act["t"] / max(.01, a.get("windup", .6)))
        pg.draw.circle(v, (170, 50, 50), (x, y), r, 1); pg.draw.circle(v, (230, 80, 70), (x, y), max(2, int(r * k)), 2)
        zr = int(a.get("zone_radius", 0))
        if zr: pg.draw.circle(v, (110, 200, 90), (x, y), zr, 1)

@attack("heal")
class Heal(Attack):
    """Лечение: восстанавливает здоровье раненым соседям (радиус, px). amount — лечение за раз.
    Применяет, только если рядом есть кому лечить."""
    range = 999; range_y = 999
    def can_use(s, m, a, w):
        rad = a.get("radius", 240)
        return any(o is not m and o.hp > 0 and o.hp < o.maxhp and math.hypot(o.cx - m.cx, o.cy - m.cy) <= rad
                   for o in w.mobs)
    def begin(s, m, a, act, w):
        rad, amt = a.get("radius", 240), a.get("amount", 12)
        for o in w.mobs:
            if o is m or o.hp <= 0 or o.hp >= o.maxhp: continue
            if math.hypot(o.cx - m.cx, o.cy - m.cy) > rad: continue
            o.hp = min(o.maxhp, o.hp + amt)
            w.fx.ring(o.cx, o.cy, 22); w.fx.text("+" + str(int(amt)), o.cx, o.y - 6)
        w.fx.ring(m.cx, m.cy, rad)
    def draw(s, m, a, act, v):
        if act["phase"] == "windup":
            pg.draw.circle(v, (90, 220, 130), (int(m.cx), int(m.cy)), int(a.get("radius", 240)), 1)

@attack("summon")
class Summon(Attack):
    """Призыв: рождает count мобов (mob) вокруг себя. cap — не больше живых призванных от этого моба,
    hard_cap — не больше мобов в комнате всего. Призванные сразу агрятся."""
    range = 300; range_y = 999
    def can_use(s, m, a, w):
        if getattr(m, "_summoned", 0) >= a.get("cap", 8): return False
        if len(w.mobs) >= a.get("hard_cap", 26): return False
        return True
    def begin(s, m, a, act, w):
        from mob import Mob   # лениво: mob.py импортирует attacks.py (реестр ATTACKS)
        kind = a.get("mob")
        if kind not in CFG["mobs"]: return
        n = max(1, int(a.get("count", 2))); made = 0
        for i in range(n * 3):
            if made >= n or len(w.mobs) >= a.get("hard_cap", 26): break
            ang = math.pi * 2 * (i % n) / n + i * .5
            px = m.cx + math.cos(ang) * T * 1.2
            py = m.cy + math.sin(ang) * T * .8
            d = CFG["mobs"][kind]
            if free(w.g, pg.Rect(int(px - d["w"] / 2), int(py - d["h"] / 2), d["w"], d["h"])) or i >= n * 2:
                kid = Mob(kind, px - d["w"] / 2, py - d["h"] / 2, 1.0)
                kid.aggro = True; kid.cds = [random.uniform(.1, .5) for _ in kid.attacks]
                w.mobs.append(kid); made += 1
        m._summoned = getattr(m, "_summoned", 0) + made
        if made:
            w.fx.ring(m.cx, m.cy, 60); w.fx.text("Призыв!", m.cx, m.y - 10)
    def draw(s, m, a, act, v):
        if act["phase"] == "windup":
            pg.draw.circle(v, (170, 50, 50), (int(m.cx), int(m.cy)), int(T * 1.8), 1)

@attack("kamikaze")
class Kamikaze(Attack):
    """Камикадзе: моб летит к игроку с большой скоростью и взрывается при столкновении.
    Параметры: speed (px/s, по умолчанию 500), radius (радиус урона, 80), damage (по умолчанию 20)."""
    def start(s, m, a, act, w):
        act["free"] = True
        dx = w.pl.cx - m.cx
        dy = w.pl.cy - m.cy
        dist = math.hypot(dx, dy) or 1
        speed = a.get("speed", 500)
        m.vx = dx / dist * speed
        m.vy = dy / dist * speed

    def active(s, m, a, act, dt, w):
        if m.touches_rect(w.pl.rect) or math.hypot(m.cx - w.pl.cx, m.cy - w.pl.cy) <= 5:
            x, y = m.cx, m.cy
            r = a.get("radius", 80)
            w.fx.ring(x, y, r)
            hit_zone(m, a, act, w, lambda rect: circle_hits_rect(x, y, r, rect))
            m.hp = 0
            return True
        if act.get("t", 0) > 5:
            m.vx = m.vy = 0
            return True
        return False
