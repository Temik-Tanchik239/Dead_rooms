"""Паттерны атак мобов. В mobs.json: "attacks": [{"type": "melee", ...}, {"type": "shoot", ...}] — моб берёт первую
атаку из списка, которая перезарядилась и до игрока подходящее расстояние.

Каждая атака идёт фазами: windup (замах, моб мигает) -> active (удар) -> recovery (отдых).
Общие параметры: windup, active, recovery (секунды), cooldown (перезарядка этой атаки), damage, knockback,
range / min_range (с какого расстояния до игрока атакует), range_y (допустимая разница по высоте),
mobile (true — продолжает двигаться по своему паттерну во время атаки), interrupt (false — удар не сбивает замах),
id + next (после этой атаки сразу начать атаку с таким id — комбо), anims {"windup": "имя", "attack": "имя", ...} —
свои анимации на фазы этой атаки.

Новая атака = класс-наследник Attack с декоратором @attack("имя"); переопредели нужные методы."""
import math
import pygame as pg
from core import T, W, free, sign, floor_below, circle_hits_rect
from projectiles import volley

ATTACKS = {}
def attack(name):
    def reg(cls): ATTACKS[name] = cls(); return cls
    return reg

def hit_player(m, a, w, from_x=None):
    w.pl.hit(a.get("damage", 10) * m.dmg_scale, m.cx if from_x is None else from_x, w.fx, a.get("knockback", 260))

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
        if not act["hit"] and act["box"].colliderect(w.pl.rect): act["hit"] = True; hit_player(m, a, w)
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
        x, y = s.center(m, a, act)
        if not act["hit"] and circle_hits_rect(x, y, a.get("radius", 80), w.pl.rect): act["hit"] = True; hit_player(m, a, w, x)
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
            tx = max(T + m.w / 2 + 2, min(W - T - m.w / 2 - 2, pl.cx + sd * off))
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
        if circle_hits_rect(x, y, r, w.pl.rect): hit_player(m, a, w)
        return True
    def anim(s, m, a, act): return "jump"
    def draw(s, m, a, act, v):
        if act["phase"] != "windup" or "to" not in act: return
        tx, ty = map(int, act["to"]); r = a.get("radius", 60)
        if m.flies: pg.draw.circle(v, (230, 80, 70), (tx, ty), 10, 2); return
        pg.draw.line(v, (230, 80, 70), (tx - r, ty - 1), (tx + r, ty - 1), 2)
        pg.draw.polygon(v, (230, 80, 70), [(tx, ty - 6), (tx - 6, ty - 16), (tx + 6, ty - 16)])
