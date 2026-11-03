"""Руки Моргарта — отдельные части босса: своя позиция, своё здоровье, свои атаки.

Как это устроено
  * Голова — это сам моб Моргарт (mob.py). Руки лежат в mob.hands (HandSet) и НЕ являются отдельными мобами:
    уровень проходится только по голове (когда умирает голова, комната считается зачищенной).
  * Позиция каждой руки в карте хранится ОТНОСИТЕЛЬНО головы (в клетках) — ставится в редакторе карт:
        "morgart_layout": {"anchors": {"head": [0.5, 0.2]},
                           "hands": {"upper_left": {"enabled": true, "offset": [-11, -1.5], "hp": 260, "pattern": "grabber"}}}
    Всё остальное (спрайты, HP по умолчанию, паттерны, параметры атак) — в assets/boss/boss.json -> "hands".
  * Пока живы руки, голова неуязвима (mob.hands_gate_head). Когда уничтожена последняя рука, остаётся только голова
    и начинаются её атаки с "requires": "alone".

Атаки рук (assets/boss/boss.json -> hands.attacks, тип задаётся полем type):
  thrust — рука выдвигается по прямой к игроку;
  slam   — рука взлетает над игроком и бьёт сверху (ударная волна по кругу);
  sweep  — рука проносится поперёк арены на высоте игрока (нужно перепрыгнуть или уйти в перекат);
  grab   — рука выдвигается и ХВАТАЕТ игрока: тот оглушён, рука тащит и сжимает его (урон тиками);
           вырваться: быстро жать клавиши движения/прыжка, либо нанести руке break_damage урона (союзники);
  clap   — две руки одного ряда (верхние/нижние) смыкаются в центре арены.
Паттерн руки (hands.patterns) — порядок атак (cycle) или случайный выбор (random) и паузы между ними.

Новая атака = класс-наследник HandAttack с декоратором @hand_attack("тип"); параметры — в boss.json.
"""
import math, random
import pygame as pg
from core import CFG, T, deep_merge, circle_hits_rect, floor_below, free, sign
from anim import sprite
from attacks import players_of

DYING_TIME = 0.7
DEFAULT_HEAD = (0.50, 0.20)
SLOT_ORDER = ("upper_left", "lower_left", "upper_right", "lower_right")
HAND_PATH = "boss/morgart/morgart_hand_%s.png"

# Значения по умолчанию — те же, что записаны в assets/boss/boss.json (если там нет блока "hands", игра работает с ними).
DEFAULT_HANDS = {
    "size": [190, 132],          # размер спрайта руки на экране
    "hurtbox": [150, 104],       # куда попадают атаки игрока (и чем рука бьёт)
    "hp": 260,                   # здоровье руки по умолчанию (умножается на сложность круга и число игроков)
    "xp": 60,                    # опыт за уничтоженную руку
    "margin": 70,                # руки не уходят ближе этого расстояния к краю карты
    "max_active": 2,             # сколько рук могут атаковать одновременно
    "enrage_per_lost_hand": 0.82,  # паузы между атаками умножаются на это число за каждую потерянную руку
    "slots": {
        "upper_left": {"sprite": HAND_PATH % "upper_left", "side": "left", "row": "upper", "offset": [-11.0, -1.5], "hp": 260, "pattern": "grabber"},
        "lower_left": {"sprite": HAND_PATH % "lower_left", "side": "left", "row": "lower", "offset": [-11.0, 2.0], "hp": 220, "pattern": "sweeper"},
        "upper_right": {"sprite": HAND_PATH % "upper_right", "side": "right", "row": "upper", "offset": [11.0, -1.5], "hp": 260, "pattern": "slammer"},
        "lower_right": {"sprite": HAND_PATH % "lower_right", "side": "right", "row": "lower", "offset": [11.0, 2.0], "hp": 220, "pattern": "hunter"},
    },
    "patterns": {
        "grabber": {"mode": "cycle", "attacks": ["thrust", "grab", "slam"], "first": [1.2, 2.0], "gap": [1.2, 2.0]},
        "sweeper": {"mode": "cycle", "attacks": ["sweep", "thrust", "clap"], "first": [2.2, 3.2], "gap": [1.5, 2.4]},
        "slammer": {"mode": "cycle", "attacks": ["slam", "grab", "slam", "clap"], "first": [1.8, 2.6], "gap": [1.3, 2.2]},
        "hunter": {"mode": "random", "attacks": ["thrust", "thrust", "slam", "sweep"], "first": [2.6, 3.4], "gap": [1.1, 1.9]},
    },
    "attacks": {
        "thrust": {"type": "thrust", "windup": 0.55, "active": 0.22, "recovery": 0.75, "damage": 22, "knockback": 380,
                   "reach": 560, "range": 950, "pull": 40, "track": 0.65, "inflate": 10},
        "slam": {"type": "slam", "windup": 0.8, "active": 0.17, "recovery": 1.0, "damage": 28, "knockback": 420,
                 "radius": 120, "rise": 240, "range": 1000, "track": 0.7},
        "sweep": {"type": "sweep", "windup": 0.85, "active": 1.0, "recovery": 0.9, "damage": 20, "knockback": 440,
                  "band": 96, "range": 1200, "track": 0.6},
        "grab": {"type": "grab", "windup": 0.6, "active": 0.32, "recovery": 0.9, "whiff_recovery": 1.3, "reach": 640,
                 "range": 950, "damage": 8, "hold": 2.6, "tick": 0.5, "tick_damage": 6, "release_damage": 10,
                 "throw": 420, "struggle": 0.18, "break_damage": 70, "pull": 0.45, "pull_time": 0.35, "track": 0.6,
                 "pull_back": 40, "inflate": 24},
        "clap": {"type": "clap", "windup": 0.85, "active": 0.26, "recovery": 1.0, "damage": 26, "knockback": 460,
                 "gap": 70, "range": 1500},
    },
}


# ------------------------------------------------------------------ вспомогательное
def clamp(v, lo, hi): return max(lo, min(hi, v))
def lerp(a, b, k): return a + (b - a) * k
def ease_out(k): return 1 - (1 - clamp(k, 0, 1)) ** 3
def ease_in(k): k = clamp(k, 0, 1); return k * k * k


def hands_cfg():
    """Настройки рук: DEFAULT_HANDS + блок hands из assets/boss/boss.json."""
    return deep_merge(DEFAULT_HANDS, (CFG.get("boss") or {}).get("hands") or {})


def head_point(layout, world, marker=None):
    """Центр головы в пикселях мира: якорь из карты > точка маркера C/B > стандартное место."""
    ww, wh = world
    anchors = layout.get("anchors", layout) if isinstance(layout, dict) else {}
    val = anchors.get("head") if isinstance(anchors, dict) else None
    try:
        if val is not None: return clamp(float(val[0]), 0.0, 1.0) * ww, clamp(float(val[1]), 0.0, 1.0) * wh
    except (TypeError, ValueError, IndexError): pass
    if marker is not None: return float(marker[0]), float(marker[1])
    return DEFAULT_HEAD[0] * ww, DEFAULT_HEAD[1] * wh


def hand_home(sid, slot, ov, anchors, head, world, margin):
    """Где рука «живёт»: смещение от головы (клетки) из карты, иначе старые якоря left_hand/right_hand, иначе из boss.json."""
    ww, wh = world
    x = y = None
    off = ov.get("offset") if isinstance(ov, dict) else None
    try:
        if off is not None: x, y = head[0] + float(off[0]) * T, head[1] + float(off[1]) * T
    except (TypeError, ValueError, IndexError): x = y = None
    if x is None and isinstance(anchors, dict):      # карты, сохранённые старым редактором (две руки)
        legacy = anchors.get("left_hand" if slot.get("side", "left") == "left" else "right_hand")
        try:
            if legacy is not None:
                x = clamp(float(legacy[0]), 0, 1) * ww
                y = clamp(float(legacy[1]), 0, 1) * wh + (72 if slot.get("row", sid.rsplit("_", 1)[0]) == "lower" else 0)
        except (TypeError, ValueError, IndexError): x = y = None
    if x is None:
        off = slot.get("offset", [0, 0]); x, y = head[0] + float(off[0]) * T, head[1] + float(off[1]) * T
    return clamp(x, margin, max(margin, ww - margin)), clamp(y, margin, max(margin, wh - margin))


def fill_rect(v, rect, color, alpha):
    if rect.w <= 0 or rect.h <= 0: return
    s = pg.Surface(rect.size, pg.SRCALPHA); s.fill((*color, int(alpha))); v.blit(s, rect.topleft)


def fill_circle(v, c, r, color, alpha):
    r = max(1, int(r)); s = pg.Surface((2 * r, 2 * r), pg.SRCALPHA)
    pg.draw.circle(s, (*color, int(alpha)), (r, r), r); v.blit(s, (int(c[0]) - r, int(c[1]) - r))


# ------------------------------------------------------------------ атаки рук
HAND_ATTACKS = {}
def hand_attack(name):
    def reg(cls): HAND_ATTACKS[name] = cls(); return cls
    return reg


def hit_players(h, a, act, w, touches, from_x=None):
    """Бьёт каждого игрока, которого задевает зона (touches(rect) -> bool), не больше одного раза за атаку."""
    done = act["shared"].setdefault("hit_ids", set())
    for p in players_of(w):
        if id(p) in done or p.hp <= 0 or getattr(p, "grab", None) or not touches(p.rect): continue
        done.add(id(p))
        p.hit(a.get("damage", 15) * h.parent.dmg_scale, h.x if from_x is None else from_x, w.fx, a.get("knockback", 300))


class HandAttack:
    """Фазы как у атак мобов: windup (замах, на экране видна зона) -> active (удар) -> recovery (рука возвращается)."""
    def can_use(s, h, a, w):
        r = a.get("range", 1000)
        return any(math.hypot(p.cx - h.x, p.cy - h.y) <= r for p in h.targets(w))
    def start(s, h, a, act, w): pass
    def windup(s, h, a, act, dt, w): pass
    def begin(s, h, a, act, w): act["from"] = (h.x, h.y)
    def active(s, h, a, act, dt, w): return True      # True — удар закончен
    def hold(s, h, a, act, dt, w): return True        # фаза удержания (только grab); True — закончена
    def draw(s, h, a, act, v): pass                   # подсказка зоны поражения


@hand_attack("thrust")
class Thrust(HandAttack):
    """Рука выдвигается по прямой к тому месту, где игрок был в конце замаха (reach — максимальная длина выпада)."""
    def retarget(s, h, a, act):
        p = act.get("tgt"); hx, hy = h.home
        if p is None or p.hp <= 0:
            if "to" not in act or act["to"] == (h.x, h.y): act["to"] = (hx + h.face * a.get("reach", 500), hy)
            return
        dx, dy = p.cx - hx, p.cy - hy; d = math.hypot(dx, dy) or 1.0; k = min(1.0, a.get("reach", 560) / d)
        act["to"] = (hx + dx * k, hy + dy * k)
    def start(s, h, a, act, w):
        act["tgt"] = h.nearest(w); act["to"] = (h.x, h.y); s.retarget(h, a, act)
    def windup(s, h, a, act, dt, w):
        k = clamp(act["t"] / max(.01, a.get("windup", .5)), 0, 1)
        if k < a.get("track", .65): s.retarget(h, a, act)
        tx, ty = act["to"]; dx, dy = tx - h.home[0], ty - h.home[1]; d = math.hypot(dx, dy) or 1.0
        pull = a.get("pull", 40) * ease_out(k)             # рука подаётся назад — «замах»
        h.x, h.y = h.home[0] - dx / d * pull, h.home[1] - dy / d * pull
    def strike(s, h, a, act, w):
        box = h.rect().inflate(a.get("inflate", 10), a.get("inflate", 10))
        hit_players(h, a, act, w, box.colliderect)
    def active(s, h, a, act, dt, w):
        k = clamp(act["t"] / max(.01, a.get("active", .2)), 0, 1); f, t = act["from"], act["to"]; e = ease_out(k)
        h.x, h.y = lerp(f[0], t[0], e), lerp(f[1], t[1], e)
        s.strike(h, a, act, w)
        return k >= 1
    def draw(s, h, a, act, v):
        if act["phase"] != "windup": return
        k = clamp(act["t"] / max(.01, a.get("windup", .5)), 0, 1); tx, ty = act["to"]; hx, hy = h.home
        dx, dy = tx - hx, ty - hy; d = math.hypot(dx, dy) or 1.0; nx, ny = -dy / d * h.box[1] * .35, dx / d * h.box[1] * .35
        pg.draw.polygon(v, (255, 80, 110), [(hx + nx, hy + ny), (tx + nx, ty + ny), (tx - nx, ty - ny), (hx - nx, hy - ny)], 1)
        fill_circle(v, (tx, ty), 26 + 14 * (1 - k), (255, 70, 100), 50 + 90 * k)
        pg.draw.circle(v, (255, 160, 170), (int(tx), int(ty)), int(30 * (1.25 - k * .6)), 2)


@hand_attack("slam")
class Slam(HandAttack):
    """Рука взлетает над игроком и бьёт вниз; в точке удара — ударная волна радиусом radius."""
    def ground(s, h, p, w):
        ww = h.parent.world[0]; tx = clamp(p.cx, 40, ww - 40)
        gy = floor_below(w.g, tx, p.y + p.h - 6)
        return tx, (gy if gy is not None else p.y + p.h)
    def retarget(s, h, a, act, w):
        p = act.get("tgt")
        if p is None or p.hp <= 0: return
        tx, gy = s.ground(h, p, w); act["g"] = (tx, gy); act["to"] = (tx, gy - h.box[1] / 2)
    def start(s, h, a, act, w):
        act["tgt"] = h.nearest(w); act["to"] = (h.x, h.y); act["g"] = (h.x, h.y); s.retarget(h, a, act, w)
    def windup(s, h, a, act, dt, w):
        k = clamp(act["t"] / max(.01, a.get("windup", .8)), 0, 1)
        if k < a.get("track", .7): s.retarget(h, a, act, w)
        tx, ty = act["to"]; up = (tx, ty - a.get("rise", 240)); e = ease_out(k)
        h.x, h.y = lerp(h.home[0], up[0], e), lerp(h.home[1], up[1], e)
    def active(s, h, a, act, dt, w):
        k = clamp(act["t"] / max(.01, a.get("active", .17)), 0, 1); f, t = act["from"], act["to"]; e = ease_in(k)
        h.x, h.y = lerp(f[0], t[0], e), lerp(f[1], t[1], e)
        if k < 1: return False
        gx, gy = act["g"]; r = a.get("radius", 120)
        w.fx.ring(gx, gy, r); w.fx.shake = max(w.fx.shake, .25)
        hit_players(h, a, act, w, lambda rect: circle_hits_rect(gx, gy, r, rect), gx)
        return True
    def draw(s, h, a, act, v):
        if act["phase"] != "windup": return
        k = clamp(act["t"] / max(.01, a.get("windup", .8)), 0, 1); gx, gy = act["g"]; r = a.get("radius", 120)
        fill_circle(v, (gx, gy), r, (255, 60, 90), 25 + 70 * k)
        pg.draw.circle(v, (255, 90, 110), (int(gx), int(gy)), r, 2)
        pg.draw.circle(v, (255, 200, 200), (int(gx), int(gy)), max(3, int(r * k)), 2)
        pg.draw.line(v, (255, 90, 110), (int(gx), int(gy)), (int(gx), int(gy - 260)), 2)


@hand_attack("sweep")
class Sweep(HandAttack):
    """Рука уходит к краю арены и проносится поперёк на высоте игрока. Полоса видна на замахе: прыгай или катись."""
    def row(s, h, p):
        return clamp(p.cy, h.parent.cfg.get("margin", 70), h.parent.world[1] - h.parent.cfg.get("margin", 70))
    def start(s, h, a, act, w):
        act["tgt"] = h.nearest(w); ww = h.parent.world[0]; m = h.parent.cfg.get("margin", 70)
        p = act["tgt"]; y = s.row(h, p) if p else h.home[1]
        sx, ex = (m, ww - m) if h.face > 0 else (ww - m, m)
        act["sx"] = sx; act["y"] = y; act["to"] = (ex, y)
    def windup(s, h, a, act, dt, w):
        k = clamp(act["t"] / max(.01, a.get("windup", .85)), 0, 1); p = act.get("tgt")
        if k < a.get("track", .6) and p and p.hp > 0:
            act["y"] = s.row(h, p); act["to"] = (act["to"][0], act["y"])
        e = ease_out(k); h.x, h.y = lerp(h.home[0], act["sx"], e), lerp(h.home[1], act["y"], e)
    def active(s, h, a, act, dt, w):
        k = clamp(act["t"] / max(.01, a.get("active", 1.0)), 0, 1); y = act["y"]
        h.x, h.y = lerp(act["sx"], act["to"][0], k), y
        band = a.get("band", 96); box = pg.Rect(int(h.x - h.box[0] / 2), int(y - band / 2), h.box[0], band)
        hit_players(h, a, act, w, box.colliderect)
        return k >= 1
    def draw(s, h, a, act, v):
        if act["phase"] != "windup": return
        k = clamp(act["t"] / max(.01, a.get("windup", .85)), 0, 1); band = a.get("band", 96); y = act["to"][1]
        ww = h.parent.world[0]; rect = pg.Rect(0, int(y - band / 2), int(ww), int(band))
        fill_rect(v, rect, (255, 60, 90), 25 + 80 * k)
        pg.draw.line(v, (255, 120, 130), (0, int(y - band / 2)), (int(ww), int(y - band / 2)), 2)
        pg.draw.line(v, (255, 120, 130), (0, int(y + band / 2)), (int(ww), int(y + band / 2)), 2)


@hand_attack("grab")
class Grab(Thrust):
    """Выпад-захват. Попал по незащищённому игроку — тот оглушён (p.grab), рука тянет его к себе и сжимает.
    Игрок вырывается быстрым нажатием клавиш движения/прыжка (struggle сек. за нажатие) или когда руке нанесено break_damage."""
    def strike(s, h, a, act, w):
        pass
    def active(s, h, a, act, dt, w):
        k = clamp(act["t"] / max(.01, a.get("active", .3)), 0, 1); f, t = act["from"], act["to"]; e = ease_out(k)
        h.x, h.y = lerp(f[0], t[0], e), lerp(f[1], t[1], e)
        box = h.rect().inflate(a.get("inflate", 24), a.get("inflate", 24) // 2)
        for p in h.targets(w):
            if p.inv > 0 or getattr(p, "state", "") == "roll" or not box.colliderect(p.rect): continue
            h.grab_player(p, a, act, w); return True
        if k >= 1: act["rec_time"] = a.get("whiff_recovery", a.get("recovery", 1.0)); return True
        return False
    def hold(s, h, a, act, dt, w):
        p = h.held
        if p is None or p.hp <= 0 or not getattr(p, "grab", None) or p.grab.get("hand") is not h:
            h.release(w.fx, None, False); return True
        g = p.grab; k = clamp(act["t"] / max(.01, a.get("pull_time", .35)), 0, 1); sq = act["squeeze"]
        h.x, h.y = lerp(act["from"][0], sq[0], ease_out(k)), lerp(act["from"][1], sq[1], ease_out(k))
        g["t"] -= dt; g["tick"] -= dt
        if g["tick"] <= 0:
            g["tick"] += a.get("tick", .5); h.damage_held(p, a.get("tick_damage", 6), w)
            if p.hp <= 0: h.release(w.fx, None, False); return True
        h.pin(p, w)
        if g["t"] <= 0 or h.hold_hurt >= a.get("break_damage", 70):
            h.release(w.fx, a, True); return True
        return False
    def draw(s, h, a, act, v):
        if act["phase"] == "windup":
            Thrust.draw(s, h, a, act, v)
        elif act["phase"] == "hold" and h.held is not None:
            g = h.held.grab; left = clamp(g["t"] / max(.01, a.get("hold", 2.6)), 0, 1)
            pg.draw.arc(v, (255, 220, 120), pg.Rect(int(h.x - 38), int(h.y - 38), 76, 76), math.pi / 2, math.pi / 2 + math.tau * left, 4)


@hand_attack("clap")
class Clap(HandAttack):
    """Две руки одного ряда (upper/lower) смыкаются у головы на высоте игрока. Партнёр запускается автоматически."""
    def can_use(s, h, a, w):
        p = h.parent.partner(h)
        return p is not None and p.alive and p.act is None and bool(h.targets(w))
    def setup(s, h, a, act):
        sh = act["shared"]; gap = a.get("gap", 70); bw = h.box[0]
        act["to"] = (sh["mx"] - h.face * (gap / 2 + bw / 2), sh["y"])
        act["ready"] = (h.home[0] - h.face * 40, sh["y"])
    def start(s, h, a, act, w):
        sh = act["shared"]
        if not sh.get("lead"):
            pl = h.nearest(w); m = h.parent.cfg.get("margin", 70)
            sh["lead"] = h.id; sh["mx"] = h.parent.head[0]; sh["y"] = clamp(pl.cy if pl else h.home[1], m, h.parent.world[1] - m)
            p = h.parent.partner(h)
            if p is not None: p.start(act["name"], w, shared=sh)
        s.setup(h, a, act)
    def windup(s, h, a, act, dt, w):
        k = clamp(act["t"] / max(.01, a.get("windup", .85)), 0, 1); e = ease_out(k)
        h.x, h.y = lerp(h.home[0], act["ready"][0], e), lerp(h.home[1], act["ready"][1], e)
    def begin(s, h, a, act, w): act["from"] = (h.x, h.y)
    def active(s, h, a, act, dt, w):
        k = clamp(act["t"] / max(.01, a.get("active", .26)), 0, 1); f, t = act["from"], act["to"]; e = ease_in(k)
        h.x, h.y = lerp(f[0], t[0], e), lerp(f[1], t[1], e)
        hit_players(h, a, act, w, h.rect().inflate(14, 14).colliderect)
        if k >= 1: w.fx.ring(h.x - h.face * h.box[0] / 2, h.y, 70); w.fx.shake = max(w.fx.shake, .2)
        return k >= 1
    def draw(s, h, a, act, v):
        if act["phase"] != "windup": return
        k = clamp(act["t"] / max(.01, a.get("windup", .85)), 0, 1); tx, ty = act["to"]; mx = h.parent.head[0]
        rect = pg.Rect(int(min(tx, mx)), int(ty - h.box[1] / 2), int(abs(tx - mx)), int(h.box[1]))
        fill_rect(v, rect, (255, 60, 90), 20 + 70 * k)
        pg.draw.rect(v, (255, 120, 130), rect, 2)


# ------------------------------------------------------------------ рука
class Hand:
    def __init__(s, hid, slot, home, hp, scale, parent):
        s.id, s.slot, s.parent = hid, slot, parent
        s.face = 1 if slot.get("side", "left") == "left" else -1      # куда «смотрят» пальцы спрайта
        s.row = slot.get("row") or hid.rsplit("_", 1)[0]
        s.sprite = slot.get("sprite") or HAND_PATH % hid
        s.size = tuple(parent.cfg.get("size", [190, 132])); s.box = tuple(parent.cfg.get("hurtbox", [150, 104]))
        s.home = (float(home[0]), float(home[1])); s.x, s.y = s.home
        s.maxhp = s.hp = float(hp) * scale
        s.pname = slot.get("pattern") or "grabber"
        s.pattern = parent.cfg["patterns"].get(s.pname) or next(iter(parent.cfg["patterns"].values()), {"attacks": []})
        s.alive = True; s.dying = -1.0; s.flash = 0.0; s.t = random.random() * 6.0
        s.act = None; s.seq = 0; s.held = None; s.net_hold = False; s.hold_hurt = 0.0
        lo, hi = (s.pattern.get("first") or [1.2, 2.0])[:2]; s.cd = random.uniform(lo, hi)
        s.vis_ang = 0.0; s._ld = None

    # ---------- состояние ----------
    def rect(s):
        bw, bh = s.box; return pg.Rect(int(s.x - bw / 2), int(s.y - bh / 2), bw, bh)
    @property
    def holding(s): return s.held is not None or s.net_hold
    def targets(s, w):
        return [p for p in players_of(w) if p.hp > 0 and not getattr(p, "grab", None) and not getattr(p, "downed", False)]
    def nearest(s, w):
        ts = s.targets(w); return min(ts, key=lambda p: (p.cx - s.x) ** 2 + (p.cy - s.y) ** 2) if ts else None

    # ---------- урон ----------
    def hurt(s, dmg, fx):
        if not s.alive: return
        s.hp -= dmg; s.flash = .1; fx.stop = .05; fx.text(str(int(dmg)), s.x, s.y - s.box[1] / 2 - 6)
        if s.held is not None: s.hold_hurt += dmg
        if s.hp <= 0: s.die(fx)
    def die(s, fx):
        s.hp = 0; s.alive = False; s.dying = 0.0
        s.release(fx, None, False); s.act = None
        fx.ring(s.x, s.y, 60); fx.shake = max(fx.shake, .3)
        s.parent.pending_xp += int(s.parent.cfg.get("xp", 60))

    # ---------- захват ----------
    def grab_player(s, p, a, act, w):
        p.grab = {"hand": s, "t": float(a.get("hold", 2.6)), "tick": float(a.get("tick", .5)),
                  "struggle": float(a.get("struggle", .18)), "prev": ()}
        s.held = p; s.hold_hurt = 0.0
        p.vx = p.vy = 0.0; p.atk = None; p.skill_cast = None
        if getattr(p, "state", "") in ("attack", "ladder"): p.state = "move"
        p.hit(a.get("damage", 8) * s.parent.dmg_scale, s.x, w.fx, 0)
        act["from"] = (s.x, s.y); hx, hy = s.home; k = a.get("pull", .45)
        act["squeeze"] = (lerp(s.x, hx, k), lerp(s.y, hy, k))   # куда рука утащит игрока
        act["hold_player"] = True
    def pin(s, p, w):
        """Игрок «зажат» в руке (не уходит в стены: если точка занята — остаётся на последнем свободном месте)."""
        nx = clamp(s.x - p.w / 2, 0, max(0, s.parent.world[0] - p.w)); ny = s.y - p.h / 2
        for tx, ty in ((nx, ny), (nx, p.y), (p.x, ny)):
            if free(w.g, pg.Rect(int(tx), int(ty), p.w, p.h)): p.x, p.y = tx, ty; break
        p.vx = p.vy = 0.0
    def damage_held(s, p, dmg, w):
        p.inv = 0      # тик урона игнорирует кадры неуязвимости от прошлого тика
        p.hit(dmg * s.parent.dmg_scale, s.x, w.fx, 0); p.vx = p.vy = 0.0
    def release(s, fx, a, throw):
        p, s.held = s.held, None
        if p is None: return
        p.grab = None
        if p.hp <= 0: return
        p.stun = max(p.stun, .25)
        if a is not None and throw:      # выбросить к центру арены (руки висят у краёв)
            p.inv = 0; p.hit(a.get("release_damage", 10) * s.parent.dmg_scale, s.x, fx, a.get("throw", 420))
            p.vy = -380
        else:
            p.inv = max(p.inv, 1.0); p.vy = -220

    # ---------- кадр ----------
    def update(s, dt, w):
        s.t += dt; s.flash -= dt
        if not s.alive:
            if s.dying >= 0: s.dying += dt
            return
        if s.act: s.tick_attack(dt, w)
        else:
            s.cd -= dt
            bob = (math.sin(s.t * 2.1) * 6, math.sin(s.t * 3.0 + 1.0) * 8)
            tx, ty = s.home[0] + bob[0], s.home[1] + bob[1]; k = min(1.0, dt * 8)
            s.x += (tx - s.x) * k; s.y += (ty - s.y) * k

    def start(s, name, w, shared=None):
        a = s.parent.attack_params(name); H = HAND_ATTACKS[a["type"]]
        s.act = {"name": name, "a": a, "h": H, "phase": "windup", "t": 0.0, "from": (s.x, s.y), "to": (s.x, s.y),
                 "shared": shared if shared is not None else {}}
        H.start(s, a, s.act, w)

    def tick_attack(s, dt, w):
        act = s.act; a, H = act["a"], act["h"]; act["t"] += dt; ph = act["phase"]
        if ph == "windup":
            H.windup(s, a, act, dt, w)
            if act["t"] >= a.get("windup", .5): act["phase"], act["t"] = "active", 0.0; H.begin(s, a, act, w)
        elif ph == "active":
            if H.active(s, a, act, dt, w):
                act["phase"], act["t"] = ("hold" if s.held is not None else "recovery"), 0.0
                if act["phase"] == "recovery": act["rec_from"] = (s.x, s.y)
        elif ph == "hold":
            if H.hold(s, a, act, dt, w): act["phase"], act["t"] = "recovery", 0.0; act["rec_from"] = (s.x, s.y)
        else:
            rec = act.get("rec_time", a.get("recovery", .8)); k = clamp(act["t"] / max(.01, rec), 0, 1)
            f = act.get("rec_from", (s.x, s.y)); e = ease_out(k)
            s.x, s.y = lerp(f[0], s.home[0], e), lerp(f[1], s.home[1], e)
            if act["t"] >= rec:
                s.act = None; lo, hi = (s.pattern.get("gap") or [1.2, 2.0])[:2]
                s.cd = random.uniform(lo, hi) * s.parent.gap_scale()

    def pick(s, w):
        """Выбрать следующую атаку по паттерну руки. True — атака началась."""
        names = list(s.pattern.get("attacks") or [])
        if not names: s.cd = 1.0; return False
        if s.pattern.get("mode", "cycle") == "random": order = random.sample(names, len(names))
        else: order = [names[(s.seq + i) % len(names)] for i in range(len(names))]
        for i, name in enumerate(order):
            a = s.parent.attack_params(name); H = HAND_ATTACKS.get(a.get("type"))
            if H and H.can_use(s, a, w):
                if s.pattern.get("mode", "cycle") != "random": s.seq = (s.seq + i + 1) % len(names)
                s.start(name, w); return True
        s.cd = .4; return False

    # ---------- рисование ----------
    def aim_angle(s):
        """(flip, угол поворота спрайта) — рука поворачивается к цели удара."""
        act = s.act; ax, ay = float(s.face), 0.0
        if act and act["phase"] in ("windup", "active") and "to" in act:
            tx, ty = act["to"]; dx, dy = tx - s.x, ty - s.y
            if math.hypot(dx, dy) > 4: ax, ay = dx, dy
            if act["phase"] == "windup" and act["a"].get("type") == "slam": ax, ay = float(s.face), 1.0
        dirx = sign(ax) or s.face
        th = math.degrees(math.atan2(-ay, max(abs(ax), 1e-3)))
        return dirx != s.face, clamp(th if dirx > 0 else -th, -80, 80)

    def draw(s, v, alpha=255, scale=1.0, hot=False, bar=True):
        fade = 1.0
        if not s.alive:
            if s.dying < 0 or s.dying >= DYING_TIME: return
            fade = 1 - s.dying / DYING_TIME
        now = pg.time.get_ticks(); dt = 0.016 if s._ld is None else min(.1, (now - s._ld) / 1000); s._ld = now
        flip, target = s.aim_angle(); s.vis_ang += (target - s.vis_ang) * min(1.0, dt * 14)
        ang = int(round(s.vis_ang / 5.0)) * 5
        dw, dh = s.size
        img = sprite(s.sprite, dw, dh, flip, bool(hot or s.flash > 0), ang)
        if img:
            out = img
            if scale != 1.0 or fade < 1.0:
                k = scale * (0.85 + 0.15 * fade); out = pg.transform.smoothscale(img, (max(1, int(img.get_width() * k)), max(1, int(img.get_height() * k))))
            out = out.copy(); out.set_alpha(int(alpha * fade))
            v.blit(out, out.get_rect(center=(int(s.x), int(s.y))))
        else:
            pg.draw.rect(v, (255, 255, 255) if s.flash > 0 else (80, 40, 140), s.rect(), border_radius=10)
        if bar and s.alive: s.draw_bar(v, alpha)

    def draw_bar(s, v, alpha=255):
        bw = 84; x, y = int(s.x - bw / 2), int(s.y - s.box[1] / 2 - 18)
        k = clamp(s.hp / max(1.0, s.maxhp), 0, 1)
        pg.draw.rect(v, (24, 8, 40), (x - 1, y - 1, bw + 2, 8), border_radius=3)
        pg.draw.rect(v, (255, 170, 60) if s.holding else (190, 70, 235), (x, y, int(bw * k), 6), border_radius=3)
        pg.draw.rect(v, (235, 200, 255), (x - 1, y - 1, bw + 2, 8), 1, border_radius=3)


# ------------------------------------------------------------------ набор рук босса
class HandSet:
    def __init__(s, layout, world, head, scale=1.0, dmg_scale=1.0):
        s.cfg = cfg = hands_cfg(); s.world = world; s.head = head; s.dmg_scale = dmg_scale; s.pending_xp = 0
        layout = layout if isinstance(layout, dict) else {}
        anchors = layout.get("anchors", layout); anchors = anchors if isinstance(anchors, dict) else {}
        ovs = layout.get("hands", {}) if isinstance(layout.get("hands", {}), dict) else {}
        s.list = []
        for sid, slot in cfg["slots"].items():
            ov = ovs.get(sid, {}) if isinstance(ovs.get(sid, {}), dict) else {}
            if ov.get("enabled", slot.get("enabled", True)) is False: continue
            home = hand_home(sid, slot, ov, anchors, head, world, cfg.get("margin", 70))
            try: hp = float(ov.get("hp") or slot.get("hp") or cfg.get("hp", 260))
            except (TypeError, ValueError): hp = float(cfg.get("hp", 260))
            slot = dict(slot)
            if ov.get("pattern") in cfg["patterns"]: slot["pattern"] = ov["pattern"]
            s.list.append(Hand(sid, slot, home, hp, scale, s))
        s.total_max = sum(h.maxhp for h in s.list)

    def attack_params(s, name):
        a = dict(s.cfg["attacks"].get(name) or {}); a.setdefault("type", name); a["name"] = name; return a
    def alive_hands(s): return [h for h in s.list if h.alive]
    def alive_count(s): return len(s.alive_hands())
    def gap_scale(s):
        return float(s.cfg.get("enrage_per_lost_hand", .82)) ** (len(s.list) - s.alive_count())
    def hp_ratio(s):
        return clamp(sum(max(0, h.hp) for h in s.list) / max(1.0, s.total_max), 0, 1) if s.list else 0.0
    def active_count(s): return sum(1 for h in s.alive_hands() if h.act)
    def partner(s, h):
        for o in s.list:
            if o is not h and o.row == h.row and o.face != h.face: return o
        return None
    def rects(s): return [h.rect() for h in s.alive_hands()]
    def parts_at(s, test):
        return [h for h in s.alive_hands() if test(h.rect())]
    def pop_xp(s): xp, s.pending_xp = s.pending_xp, 0; return xp
    def release_all(s, fx):
        for h in s.list: h.release(fx, None, False)

    def update(s, dt, w, aggro):
        for h in s.list: h.update(dt, w)
        if not aggro: return
        limit = int(s.cfg.get("max_active", 2))
        for h in s.alive_hands():
            if h.act or h.cd > 0: continue
            if s.active_count() >= limit: break
            h.pick(w)

    # ---------- сеть ----------
    def net_pack(s):
        R = lambda v: round(v, 1); rows = []
        for h in s.list:
            act = h.act; st = 0 if h.alive else (1 if 0 <= h.dying < DYING_TIME else 2)
            fx_, to_ = (act["from"], act["to"]) if act else ((0, 0), (0, 0))
            rows.append([h.id, R(h.x), R(h.y), R(h.hp), R(h.maxhp), st, act["name"] if act else "", act["phase"] if act else "",
                         round(act["t"], 3) if act else round(max(0.0, h.dying), 3), R(fx_[0]), R(fx_[1]), R(to_[0]), R(to_[1]),
                         round(max(0, h.flash), 2), 1 if h.held is not None else 0])
        return rows
    def net_apply(s, rows, rows_b, k, ahead):
        byid = {h.id: h for h in s.list}; rb = {r[0]: r for r in rows_b} if rows_b else {}
        for r in rows:
            h = byid.get(r[0])
            if h is None: continue
            _, x, y, hp, mhp, st, name, ph, t, fx_, fy_, tx, ty, flash, held = r[:15]
            nb = rb.get(r[0])
            if nb and st == 0 and nb[5] == 0 and abs(nb[1] - x) < 220 and abs(nb[2] - y) < 220:
                x, y = x + (nb[1] - x) * k, y + (nb[2] - y) * k
            h.x, h.y, h.hp, h.maxhp, h.flash = x, y, hp, mhp, flash
            h.alive = st == 0; h.dying = -1.0 if st == 0 else (t + ahead if st == 1 else DYING_TIME + 1)
            h.net_hold = bool(held); h.held = None
            if name and name in s.cfg["attacks"] and st == 0:
                a = s.attack_params(name); H = HAND_ATTACKS.get(a["type"])
                h.act = {"name": name, "a": a, "h": H, "phase": ph, "t": t + ahead, "from": (fx_, fy_), "to": (tx, ty), "shared": {}} if H else None
                # Поля, которые хост держит только у себя и не пересылает, восстанавливаем из переданных:
                # точка удара slam лежит на полу под «to» (to = g - половина высоты руки), её рисует телеграф.
                if h.act and a.get("type") == "slam": h.act["g"] = (tx, ty + h.box[1] / 2)
            else: h.act = None

    # ---------- рисование ----------
    def draw_telegraphs(s, v):
        for h in s.alive_hands():
            if h.act and h.act.get("h"):
                try: h.act["h"].draw(h, h.act["a"], h.act, v)
                except (KeyError, TypeError, ValueError): pass      # телеграф без нужных данных (клиент в сети) — просто пропускаем, а не роняем кадр
    def draw(s, v, alpha=255, scale=1.0, hot=False):
        for h in s.list: h.draw(v, alpha, scale, False, bar=False)   # каждая рука мигает сама (h.flash), не вместе с головой
        for h in s.alive_hands(): h.draw_bar(v, alpha)
    def draw_front(s, v):
        """Рука, которая держит игрока, рисуется поверх него — игрок «в кулаке»."""
        for h in s.alive_hands():
            if h.holding: h.draw(v, 205, 1.0, False, bar=False)


# ------------------------------------------------------------------ рисование всего босса
def draw_boss(v, head, hands, t, hot=False, fade=1.0, appearing=True, act=None):
    """Голова + руки. head — центр головы (мир); hands — HandSet или None; t — время жизни; act — атака головы."""
    cx, cy = int(head[0]), int(head[1])
    appear = min(1.0, max(0.0, t / 0.48)) if appearing else 1.0
    appear = appear * appear * (3.0 - 2.0 * appear)
    scale = 0.76 + 0.24 * appear
    alpha = max(0, min(255, int(255 * fade * appear)))
    if alpha <= 0: return
    pulse = math.sin(t * 11.0) * 2.5 + (4.0 if hot else 0.0)
    top = cy - 94
    aura = pg.Surface((680, 540), pg.SRCALPHA)
    pg.draw.ellipse(aura, (112, 20, 210, int(alpha * 0.22)), aura.get_rect())
    v.blit(aura, (cx - 340, top - 60))
    cloak = [(cx - 88, top + 118), (cx - 58, top + 132), (cx - 78, top + 205), (cx - 40, top + 275), (cx, top + 330),
             (cx + 40, top + 275), (cx + 78, top + 205), (cx + 58, top + 132), (cx + 88, top + 118)]
    pg.draw.polygon(v, (12, 4, 48), cloak)
    if hands is not None:
        hands.draw_telegraphs(v)
        hands.draw(v, alpha, scale, hot)
    hw, hh = 205, 188
    img = sprite("boss/morgart/morgart_head.png", hw, hh, False, bool(hot))
    if img:
        out = img.copy()
        if scale != 1.0: out = pg.transform.smoothscale(out, (max(1, int(hw * scale)), max(1, int(hh * scale))))
        out.set_alpha(alpha)
        v.blit(out, (int(cx - out.get_width() / 2), int(cy - out.get_height() / 2 + pulse * 0.35)))
