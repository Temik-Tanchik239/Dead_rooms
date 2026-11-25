"""Пули и снаряды. Типы лежат в data/projectiles.json, оружие и мобы ссылаются на них по имени:
    "projectile": "bolt"                         — тип как есть
    "projectile": {"type": "bolt", "speed": 400} — тип + переопределённые поля
    "projectile": {"speed": 300, ...}            — описание прямо на месте (как раньше)

Базовые поля: speed, vy (добавка к вертикальной скорости), gravity, life, size, color, knockback, damage (если урон не задан
атакой), aoe (радиус взрыва), pierce (сквозь сколько целей пролетает), bounces + bounce_damp (отскоки от стен),
skin (или sprite) / frames + fps (картинка или серия PNG, носом вправо; без skin ищется assets/projectiles/<имя типа>.png), draw [w, h], rotate (поворачивать по полёту).
Поведения: homing, accel, wave, split — описаны ниже; призрачные/стационарные пули и касты «в точку курсора» — тоже.

Поле "ghost": true — пуля игнорирует стены (проходит сквозь них): для бумеранга, зон, воронки, клинков на орбите.
Поле "no_touch": true — пуля не наносит контактного урона и не исчезает при касании (весь урон делает её поведение):
для маркеров-зон, воронки, шторма и дождя.

Новое поведение = функция с декоратором @behavior("ключ") (каждый кадр) или @on_death("ключ") (при исчезновении).
Срабатывает у любой пули, в описании которой есть этот ключ; значение ключа приходит в функцию как p.

Готовые паттерны атак (в основном навеяны другими играми): boomerang (Zelda/Hades), orbit (Vampire Survivors),
vortex (Dota 2, чёрная дыра), mine (Terraria), zone (морозное поле), storm (Thundergod's Wrath), rain (дождь снарядов)."""
import math
import random
import pygame as pg
from core import CFG, T, solid, sign, circle_hits_rect
from anim import sprite, frames
import status
import effects   # частицы исчезновения пуль (projectile_hit)
from invisibility import is_invisible

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

def volley(projs, spec, x, y, angle, dmg, friendly, count=1, spread=0, owner=None):
    """Залп из count пуль веером вокруг angle (радианы); spread — градусы между соседними пулями.
    owner — стрелявший (герой/моб): бумеранг возвращается к нему, клинки на орбите кружат вокруг него."""
    d = resolve(spec)
    for i in range(count):
        a = angle + math.radians((i - (count - 1) / 2) * spread)
        b = Proj(x, y, math.cos(a) * d.get("speed", 300), math.sin(a) * d.get("speed", 300) + d.get("vy", 0),
                 d, d.get("damage", 10) if dmg is None else dmg, friendly)
        if owner is not None: b.owner = owner
        projs.append(b)

class Proj:
    def __init__(s, x, y, vx, vy, d, dmg, friendly):
        s.x, s.y, s.vx, s.vy, s.d, s.dmg, s.friendly = x, y, vx, vy, d, dmg, friendly
        s.g = d.get("gravity", 0); s.life = d.get("life", 1.5); s.r = d.get("size", 5)
        s.color = d.get("color", [255, 255, 255]); s.kb = d.get("knockback", 120); s.aoe = d.get("aoe", 0)
        s.pierce = d.get("pierce", 0); s.bounces = d.get("bounces", 0); s.t = 0.0; s.hit = set(); s.dead = False
        # Молния-снаряд: после попадания перескакивает на ближайшего ещё не задетого врага (до chain раз).
        s.chain = int(d.get("chain", 0)); s.chain_range = d.get("chain_range", 220)
    @property
    def speed(s): return math.hypot(s.vx, s.vy)
    @property
    def angle(s): return math.atan2(s.vy, s.vx)
    def set_dir(s, angle, speed=None):
        sp = s.speed if speed is None else speed; s.vx, s.vy = math.cos(angle) * sp, math.sin(angle) * sp
    def next_chain(s, w):
        """Ближайшая ещё не задетая цель в радиусе chain_range (для отскока молнии) или None."""
        best, bd = None, s.chain_range
        for m in s.targets(w):
            if id(m) in s.hit or getattr(m, "hp", 1) <= 0: continue
            dd = math.hypot(m.cx - s.x, m.cy - s.y)
            if dd < bd: bd, best = dd, m
        return best
    def targets(s, w):
        # мультиплеер: все живые игроки + клоны героев (clone.py), за ними же гонятся самонаводящиеся и цепные пули
        base = (getattr(w, "players", None) or [w.pl])
        if s.friendly: return w.mobs
        return base + [c for c in getattr(w, "clones", ()) if getattr(c, "hp", 0) > 0]
    def hit_targets(s, w):
        """Кого пуля может задеть: цели + ящики комнаты (ящики стоят в стороне от targets, чтобы на них не наводились и не перескакивали).
        Вражеские пули могут ранить и турели инженера (crafting.Turret)."""
        t = s.targets(w)
        if s.friendly:
            return t + list(getattr(w, "containers", ()))
        return t + list(getattr(w, "turrets", ()))
    def wall_hit(s, w):
        """Пуля упёрлась в стену: если в этой клетке ящик — бьём ящик (его клетки в сетке считаются стеной)."""
        if not s.friendly: return
        for ct in getattr(w, "containers", ()):
            if id(ct) not in s.hit and ct.rect.collidepoint(s.x, s.y): s.hit.add(id(ct)); s.damage(ct, w, sign(s.vx) or 1); return
    def damage(s, target, w, kb_dir):
        if s.friendly:
            stop = w.fx.stop
            target.hurt(s.dmg, kb_dir * s.kb, w.fx)
            hs = s.d.get("hit_stop")   # стоп-кадр от попадания (сек): по умолчанию как у любого удара (hurt ставит .05); 0 — без заморозки (быстрострелы: иначе игра «лагает»)
            if hs is not None: w.fx.stop = max(stop, float(hs))
            eff = s.d.get("effect")   # напр. {"freeze": 2.0} у ледяной пули — применяется только к мобам
            if eff and hasattr(target, "frozen"): status.apply(target, eff, w.fx)
            for eff in getattr(s, "extra_eff", ()):   # эффекты надетых аксессуаров стрелка (Player.fire)
                if hasattr(target, "frozen"): status.apply(target, eff, w.fx)
        else: target.hit(s.dmg, s.x, w.fx, s.kb)
    def die(s, w):
        if s.dead: return
        s.dead = True
        effects.emit(w.fx, "projectile_hit", s.x, s.y, dir=sign(s.vx) or 1, target_id=s.d.get("_id"))   # частицы гибели пули
        if s.aoe:
            sh = s.d.get("shake", .15)   # тряска экрана от взрыва (сек), 0 — без тряски
            if sh: w.fx.shake = float(sh)
            w.fx.ring(s.x, s.y, s.aoe)
            for m in s.hit_targets(w):
                if (m.collides_circle(s.x, s.y, s.aoe) if hasattr(m, "collides_circle") else circle_hits_rect(s.x, s.y, s.aoe, m.rect)): s.damage(m, w, sign(m.cx - s.x) or 1)
        for key, fn in DEATH.items():
            if key in s.d: fn(s, s.d[key], w)
    def update(s, dt, w):
        s.t += dt
        for key, fn in BEHAVIORS.items():
            if key in s.d: fn(s, s.d[key], dt, w)
        if s.dead: return
        s.vy += s.g * dt; damp = s.d.get("bounce_damp", .8)
        s.x += s.vx * dt
        if not s.d.get("ghost") and solid(w.g, int(s.x // T), int(s.y // T)):   # ghost игнорирует стены
            s.wall_hit(w); s.x -= s.vx * dt
            if s.bounces <= 0: return s.die(w)
            s.vx *= -damp; s.bounces -= 1
        s.y += s.vy * dt
        if not s.d.get("ghost") and solid(w.g, int(s.x // T), int(s.y // T)):
            s.wall_hit(w); s.y -= s.vy * dt
            if s.bounces <= 0: return s.die(w)
            s.vy *= -damp; s.bounces -= 1
        s.life -= dt
        if s.life <= 0: return s.die(w)
        if s.d.get("no_touch"): return   # маркер (зона/воронка/шторм/дождь) не бьёт контактом — весь урон в его поведении
        box = pg.Rect(int(s.x - s.r), int(s.y - s.r), 2 * s.r, 2 * s.r)
        for m in s.hit_targets(w):
            if id(m) in s.hit or not (m.collides_rect(box) if hasattr(m, "collides_rect") else box.colliderect(m.rect)): continue
            if not s.friendly and getattr(m, "state", "") == "roll": continue   # перекат проходит сквозь пули
            s.hit.add(id(m))
            if not s.aoe: s.damage(m, w, sign(s.vx) or 1)
            if s.chain > 0 and not s.aoe:
                nxt = s.next_chain(w)
                if nxt is not None:
                    s.chain -= 1
                    w.fx.beam(s.x, s.y, nxt.cx, nxt.cy, s.color)   # разряд к следующей цели
                    s.set_dir(math.atan2(nxt.cy - s.y, nxt.cx - s.x))
                    s.life = max(s.life, s.d.get("life", 1.5))      # хватит времени долететь до следующего врага
                    return
                return s.die(w)                                     # больше некуда перескакивать
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
        if id(m) in s.hit: continue   # уже задетых не преследуем (пробивающие/цепные пули летят к следующему врагу)
        if not s.friendly and is_invisible(m): continue   # вражеские пули не наводятся на невидимого игрока
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

@behavior("boomerang")
def _boomerang(s, p, dt, w):
    """"boomerang": {"return": 0.42, "return_speed": 560} — бумеранг (Zelda/Hades): заданное время летит вперёд,
    затем летит обратно к стрелявшему (на обратном пути бьёт тех же заново), вернувшись — исчезает.
    Обычно с "pierce": 999 и "ghost": true (возвращается сквозь стены, как в Zelda)."""
    p = p if isinstance(p, dict) else {"return": p}
    ret = float(p.get("return", 0.45))
    if s.t < ret: return
    if not getattr(s, "_bo_back", False):
        s._bo_back = True; s.hit.clear()   # на обратном пути задетых бьём заново
    owner = getattr(s, "owner", None) or getattr(w, "pl", None)
    if owner is None: return
    dx, dy = owner.cx - s.x, owner.cy - s.y
    if math.hypot(dx, dy) < 16: return s.die(w)   # вернулся к хозяину — исчезает
    s.set_dir(math.atan2(dy, dx), float(p.get("return_speed", s.speed + 120)))

@behavior("orbit")
def _orbit(s, p, dt, w):
    """"orbit": {"radius": 46, "speed": 3.2, "rehit": 0.55} — снаряд кружит вокруг стрелявшего (Vampire
    Survivors/Terraria): radius — радиус орбиты (px), speed — обороты/с, rehit — через сколько секунд
    можно снова задеть того же врага. Обычно с "pierce": 999, "ghost": true и залпом count>1/spread>0."""
    p = p if isinstance(p, dict) else {"radius": p}
    owner = getattr(s, "owner", None) or getattr(w, "pl", None)
    if owner is None: return
    rehit = float(p.get("rehit", 0.6))
    if rehit > 0 and s.t - getattr(s, "_orb_clear", 0.0) >= rehit:
        s._orb_clear = s.t; s.hit.clear()
    ph = getattr(s, "_orb_phase", None)
    if ph is None: s._orb_phase = ph = s.angle   # начальная фаза — направление залпа
    rad = float(p.get("radius", 46)); om = float(p.get("speed", 3.2))
    ang = ph + s.t * om
    s.x, s.y = owner.cx + math.cos(ang) * rad, owner.cy + math.sin(ang) * rad
    s.vx, s.vy = -math.sin(ang), math.cos(ang)   # скорость-призрак: только для поворота спрайта по касательной

@behavior("vortex")
def _vortex(s, p, dt, w):
    """"vortex": {"radius": 160, "force": 280, "damage": 4, "interval": 0.5} — воронка/чёрная дыра (Dota 2):
    стягивает врагов к центру пули (сильнее ближе к центру); каждые interval секунд наносит урон пули
    (s.dmg) и её статус ("effect") всем в радиусе. Боссы (cc_immune) притяжению не поддаются, но урон получают."""
    p = p if isinstance(p, dict) else {"force": p}
    rad = float(p.get("radius", 150)); force = float(p.get("force", 240))
    every = float(p.get("interval", 0.5))
    tick = s.t - getattr(s, "_vz_t", -every) >= every
    if tick:
        s._vz_t = s.t
        fx = getattr(w, "fx", None)
        if fx is not None: fx.flash(s.x, s.y, rad * 0.55, list(s.color))
    for m in s.targets(w):
        if getattr(m, "hp", 1) <= 0: continue
        dx, dy = s.x - m.cx, s.y - m.cy
        dist = math.hypot(dx, dy)
        if dist > rad or dist < 1: continue
        if not status.cc_immune(m):
            k = force * min(1.0, 0.35 + 0.65 * (1.0 - dist / rad))   # чем ближе к центру, тем сильнее тянет
            m.vx = dx / dist * k
            if getattr(m, "flies", False): m.vy = dy / dist * k
            elif dy < -6: m.vy = min(getattr(m, "vy", 0.0), -30)     # наземных слегка отрывает от земли
        if tick and (p.get("damage", 0) or s.dmg): s.damage(m, w, 0)

@behavior("mine")
def _mine(s, p, dt, w):
    """"mine": {"radius": 48, "arm": 0.7} — мина (Terraria): после arm секунд, когда пуля легла на пол,
    ждёт врага; когда тот подходит в radius — взрывается (aoe и статус пули, см. die())."""
    p = p if isinstance(p, dict) else {"radius": p}
    if s.t < float(p.get("arm", 0.6)): return
    if not getattr(s, "_mine_arm", False):
        s._mine_arm = True
        fx = getattr(w, "fx", None)
        if fx is not None: fx.ring(s.x, s.y, float(p.get("radius", 46)) * 0.5)   # мина взведена
    rad = float(p.get("radius", 46))
    for m in s.targets(w):
        if getattr(m, "hp", 1) > 0 and (m.collides_circle(s.x, s.y, rad) if hasattr(m, "collides_circle") else circle_hits_rect(s.x, s.y, rad, m.rect)):
            return s.die(w)   # взрыв — урон по aoe уже в die()

@behavior("zone")
def _zone(s, p, dt, w):
    """"zone": {"radius": 82, "interval": 0.6} — постоянная зона (морозное поле, Lich): каждые interval
    секунд наносит урон пули (s.dmg) и её статус ("effect") всем в радиусе. Пулю спавнят в точке курсора
    (у навыка "at_cursor": true) со скоростью 0 и "ghost": true."""
    p = p if isinstance(p, dict) else {"radius": p}
    every = float(p.get("interval", 0.6))
    if s.t - getattr(s, "_zn_t", -every) < every: return
    s._zn_t = s.t
    rad = float(p.get("radius", 70))
    fx = getattr(w, "fx", None)
    if fx is not None: fx.flash(s.x, s.y, rad, list(s.color))
    for m in s.hit_targets(w):
        if getattr(m, "hp", 1) > 0 and (m.collides_circle(s.x, s.y, rad) if hasattr(m, "collides_circle") else circle_hits_rect(s.x, s.y, rad, m.rect)):
            s.damage(m, w, 0)

@behavior("storm")
def _storm(s, p, dt, w):
    """"storm": {"strikes": 7, "interval": 0.32, "radius": 130, "aoe": 48} — шторм ударов молнии (Thundergod's
    Wrath): каждые interval секунд в случайную точку в radius вокруг пули бьёт разряд и взрывается на aoe;
    удар наносит урон пули (s.dmg) и её статус ("effect"). Пулю спавнят в точке курсора со скоростью 0."""
    p = p if isinstance(p, dict) else {"strikes": p}
    every = float(p.get("interval", 0.32)); n = int(p.get("strikes", 6))
    rn = getattr(s, "_st_n", 0)
    if rn >= n or s.t - getattr(s, "_st_t", -every) < every: return
    s._st_t = s.t; s._st_n = rn + 1
    rad = float(p.get("radius", 120))
    ang = random.random() * math.tau; dist = random.random() * rad
    x, y = s.x + math.cos(ang) * dist, s.y + math.sin(ang) * dist * 0.5   # шторм чуть сплюснут по вертикали
    fx = getattr(w, "fx", None)
    if fx is not None:
        fx.bolt(x, y, list(s.color)); fx.flash(x, y, p.get("aoe", 46), list(s.color))
    aoe = float(p.get("aoe", 46))
    for m in s.hit_targets(w):
        if getattr(m, "hp", 1) > 0 and (m.collides_circle(x, y, aoe) if hasattr(m, "collides_circle") else circle_hits_rect(x, y, aoe, m.rect)):
            s.damage(m, w, sign(m.cx - x) or 1)

@behavior("rain")
def _rain(s, p, dt, w):
    """"rain": {"into": "shadow_dagger", "count": 10, "interval": 0.11, "spread": 150, "height": 180} —
    дождь снарядов (Hades): каждые interval секунд сверху (на height выше точки) падает снаряд типа "into"
    в случайной точке в радиусе spread. Пулю-маркер спавнят в точке курсора со скоростью 0."""
    p = p if isinstance(p, dict) else {"count": p}
    every = float(p.get("interval", 0.12)); n = int(p.get("count", 8))
    rn = getattr(s, "_rn_n", 0)
    if rn >= n or s.t - getattr(s, "_rn_t", -every) < every: return
    s._rn_t = s.t; s._rn_n = rn + 1
    rad = float(p.get("spread", 140)); h = float(p.get("height", 170))
    child = resolve(p.get("into", "bolt")); child.pop("split", None); child.pop("rain", None)   # капли дождя не делятся и не продолжают дождь
    x = s.x + random.uniform(-rad, rad)
    volley(w.projs, child, x, s.y - h, math.pi / 2, p.get("damage", s.dmg), s.friendly, 1, 0, owner=getattr(s, "owner", None))

@on_death("split")
def _split(s, p, w):
    """"split": {"into": "bolt", "count": 6, "spread": 60, "damage": 5} — при исчезновении распадается на пули.
    spread — градусы между осколками; "ring": true — равномерно по кругу."""
    n = p.get("count", 6); spread = 360 / n if p.get("ring", False) else p.get("spread", 30)
    child = resolve(p.get("into", "bolt")); child.pop("split", None)   # осколки дальше не делятся
    volley(w.projs, child, s.x, s.y, s.angle, p.get("damage", max(1, s.dmg // 2)), s.friendly, n, spread)
