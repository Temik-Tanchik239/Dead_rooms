"""Пули и снаряды. Типы лежат в data/projectiles.json, оружие и мобы ссылаются на них по имени:
    "projectile": "bolt"                         — тип как есть
    "projectile": {"type": "bolt", "speed": 400} — тип + переопределённые поля
    "projectile": {"speed": 300, ...}            — описание прямо на месте (как раньше)

Базовые поля: speed, vy (добавка к вертикальной скорости), gravity, life, size, color, knockback, damage (если урон не задан
атакой), aoe (радиус взрыва), pierce (сквозь сколько целей пролетает), bounces + bounce_damp (отскоки от стен),
skin (или sprite) / frames + fps (картинка или серия PNG, носом вправо; без skin ищется assets/projectiles/<имя типа>.png), draw [w, h], rotate (поворачивать по полёту).
Поведения: homing, accel, wave, split — описаны ниже.

Новое поведение = функция с декоратором @behavior("ключ") (каждый кадр) или @on_death("ключ") (при исчезновении).
Срабатывает у любой пули, в описании которой есть этот ключ; значение ключа приходит в функцию как p."""
import math
import pygame as pg
from core import CFG, T, solid, sign, circle_hits_rect
from anim import sprite, frames

BEHAVIORS, DEATH = {}, {}
def behavior(key):
    def reg(fn): BEHAVIORS[key] = fn; return fn
    return reg
def on_death(key):
    def reg(fn): DEATH[key] = fn; return fn
    return reg

def resolve(spec):
    """Имя типа | {"type": имя, ...правки} | полное описание -> словарь параметров пули."""
    if isinstance(spec, str):
        if spec not in CFG["projectiles"]: raise KeyError(f"нет пули '{spec}' в data/projectiles.json")
        d = dict(CFG["projectiles"][spec]); d["_id"] = spec; return d
    if "type" in spec:
        d = resolve(spec["type"]); d.update({k: v for k, v in spec.items() if k != "type"}); return d
    return dict(spec)

def volley(projs, spec, x, y, angle, dmg, friendly, count=1, spread=0):
    """Залп из count пуль веером вокруг angle (радианы); spread — градусы между соседними пулями."""
    d = resolve(spec)
    for i in range(count):
        a = angle + math.radians((i - (count - 1) / 2) * spread)
        projs.append(Proj(x, y, math.cos(a) * d.get("speed", 300), math.sin(a) * d.get("speed", 300) + d.get("vy", 0),
                          d, d.get("damage", 10) if dmg is None else dmg, friendly))

class Proj:
    def __init__(s, x, y, vx, vy, d, dmg, friendly):
        s.x, s.y, s.vx, s.vy, s.d, s.dmg, s.friendly = x, y, vx, vy, d, dmg, friendly
        s.g = d.get("gravity", 0); s.life = d.get("life", 1.5); s.r = d.get("size", 5)
        s.color = d.get("color", [255, 255, 255]); s.kb = d.get("knockback", 120); s.aoe = d.get("aoe", 0)
        s.pierce = d.get("pierce", 0); s.bounces = d.get("bounces", 0); s.t = 0.0; s.hit = set(); s.dead = False
    @property
    def speed(s): return math.hypot(s.vx, s.vy)
    @property
    def angle(s): return math.atan2(s.vy, s.vx)
    def set_dir(s, angle, speed=None):
        sp = s.speed if speed is None else speed; s.vx, s.vy = math.cos(angle) * sp, math.sin(angle) * sp
    def targets(s, w): return w.mobs if s.friendly else (getattr(w, "players", None) or [w.pl])   # мультиплеер: все живые игроки
    def damage(s, target, w, kb_dir):
        if s.friendly: target.hurt(s.dmg, kb_dir * s.kb, w.fx)
        else: target.hit(s.dmg, s.x, w.fx, s.kb)
    def die(s, w):
        if s.dead: return
        s.dead = True
        if s.aoe:
            w.fx.shake = .15; w.fx.ring(s.x, s.y, s.aoe)
            for m in s.targets(w):
                if circle_hits_rect(s.x, s.y, s.aoe, m.rect): s.damage(m, w, sign(m.cx - s.x) or 1)
        for key, fn in DEATH.items():
            if key in s.d: fn(s, s.d[key], w)
    def update(s, dt, w):
        s.t += dt
        for key, fn in BEHAVIORS.items():
            if key in s.d: fn(s, s.d[key], dt, w)
        if s.dead: return
        s.vy += s.g * dt; damp = s.d.get("bounce_damp", .8)
        s.x += s.vx * dt
        if solid(w.g, int(s.x // T), int(s.y // T)):
            s.x -= s.vx * dt
            if s.bounces <= 0: return s.die(w)
            s.vx *= -damp; s.bounces -= 1
        s.y += s.vy * dt
        if solid(w.g, int(s.x // T), int(s.y // T)):
            s.y -= s.vy * dt
            if s.bounces <= 0: return s.die(w)
            s.vy *= -damp; s.bounces -= 1
        s.life -= dt
        if s.life <= 0: return s.die(w)
        box = pg.Rect(int(s.x - s.r), int(s.y - s.r), 2 * s.r, 2 * s.r)
        for m in s.targets(w):
            if id(m) in s.hit or not box.colliderect(m.rect): continue
            if not s.friendly and getattr(m, "state", "") == "roll": continue   # перекат проходит сквозь пули
            s.hit.add(id(m))
            if not s.aoe: s.damage(m, w, sign(s.vx) or 1)
            if s.pierce > 0 and not s.aoe: s.pierce -= 1
            else: return s.die(w)
    def draw(s, v):
        d, path = s.d, None
        if "frames" in d:
            fr = frames(d["frames"])
            if fr: path = fr[int(s.t * d.get("fps", 12)) % len(fr)]
        elif d.get("skin") or d.get("sprite"): path = d.get("skin") or d["sprite"]
        elif "_id" in d: path = f"projectiles/{d['_id']}.png"
        if path:
            dw, dh = d.get("draw", [s.r * 2, s.r * 2])
            ang = round(-math.degrees(s.angle) / 6) * 6 if d.get("rotate", True) else 0   # шаг 6°, чтобы не плодить кэш
            img = sprite(path, dw, dh, angle=ang)
            if img: v.blit(img, img.get_rect(center=(int(s.x), int(s.y)))); return
        pg.draw.circle(v, s.color, (int(s.x), int(s.y)), s.r)

# ---------- поведения пуль ----------

@behavior("homing")
def _homing(s, p, dt, w):
    """"homing": 3  или {"rate": 3, "delay": 0.2, "range": 500} — поворачивает к ближайшей цели, rate — радиан/с."""
    p = p if isinstance(p, dict) else {"rate": p}
    if s.t < p.get("delay", 0): return
    best, bd = None, p.get("range", 99999)
    for m in s.targets(w):
        dd = math.hypot(m.cx - s.x, m.cy - s.y)
        if dd < bd: best, bd = m, dd
    if not best: return
    want = math.atan2(best.cy - s.y, best.cx - s.x)
    diff = (want - s.angle + math.pi) % (2 * math.pi) - math.pi
    step = p.get("rate", 3) * dt
    s.set_dir(s.angle + max(-step, min(step, diff)))

@behavior("accel")
def _accel(s, p, dt, w):
    """"accel": 400 (px/с², можно отрицательное — торможение), "max_speed" / "min_speed" — пределы."""
    sp = max(s.d.get("min_speed", 0), min(s.speed + p * dt, s.d.get("max_speed", 99999)))
    s.set_dir(s.angle, sp)

@behavior("wave")
def _wave(s, p, dt, w):
    """"wave": {"amp": 16, "freq": 3} — синусоида поперёк полёта (amp — px, freq — колебаний в секунду)."""
    om = 2 * math.pi * p.get("freq", 3); a = p.get("amp", 16)
    off = a * (math.sin(om * s.t) - math.sin(om * (s.t - dt)))
    nx, ny = -math.sin(s.angle), math.cos(s.angle)
    s.x += nx * off; s.y += ny * off

@on_death("split")
def _split(s, p, w):
    """"split": {"into": "bolt", "count": 6, "spread": 60, "damage": 5} — при исчезновении распадается на пули.
    spread — градусы между осколками; "ring": true — равномерно по кругу."""
    n = p.get("count", 6); spread = 360 / n if p.get("ring", False) else p.get("spread", 30)
    child = resolve(p.get("into", "bolt")); child.pop("split", None)   # осколки дальше не делятся
    volley(w.projs, child, s.x, s.y, s.angle, p.get("damage", max(1, s.dmg // 2)), s.friendly, n, spread)
