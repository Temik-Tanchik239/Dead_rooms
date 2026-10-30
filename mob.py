"""Моб = тело + паттерн движения (movement.py) + список атак (attacks.py) + скин и анимации (anim.py).
Всё задаётся в data/mobs.json, код трогать не нужно."""
import math, random
import pygame as pg
from core import CFG, Body, sign, approach
from movement import MOVES, look
from attacks import ATTACKS
from anim import sprite, mob_frame, anim_length

def normalize(d):
    """Старый формат ("ai": walker | flyer | shooter) -> новый ("move" + "attacks")."""
    if "move" in d or "ai" not in d: return d
    d = dict(d); ai = d["ai"]
    if ai == "shooter":
        d["move"] = {"type": "keep_distance", "distance": d.get("keep", 240)}
        d["attacks"] = [{"type": "shoot", "projectile": d.get("projectile", "bolt"), "windup": d.get("windup", .5),
                         "cooldown": d.get("cooldown", 2), "damage": d.get("damage", 10), "range": d.get("sight", 340)}]
    else: d["move"] = {"type": "chase"}
    return d

class Mob(Body):
    def __init__(s, kind, x, y, scale):
        s.kind = kind; s.d = d = normalize(CFG["mobs"][kind]); super().__init__(x, y, d["w"], d["h"])
        s.hp = s.maxhp = d["hp"] * scale; s.dmg_scale = d.get("dmg_scale", 1)
        s.flies = d.get("flies", False); s.dir = random.choice((-1, 1)); s.home = (s.cx, s.cy)
        s.mv = d.get("move", {"type": "chase"}); s.attacks = d.get("attacks", [])
        s.cds = [random.uniform(.3, 1.2) for _ in s.attacks]; s.gap = 0.0
        s.stun = s.flash = 0; s.t = 0.0; s.aggro = False; s.act = None; s.grav = None
        s.loop_t = random.random() * s.mv.get("period", 4); s.wp = 0
        s.anim, s.anim_t, s.anim_p = "idle", 0.0, None

    # ---------- урон ----------
    def hurt(s, dmg, kb, fx):
        s.hp -= dmg; s.flash = .1; s.aggro = True
        fx.stop = .05; fx.text(str(int(dmg)), s.cx, s.y)
        act = s.act
        if s.d.get("armor") or (act and act.get("free")): return          # бронированный / в прыжке — не сбивается
        if act and act["phase"] == "windup" and not act["a"].get("interrupt", True): return
        s.vx = kb / s.d.get("mass", 1); s.vy = -140 if not s.flies else -60; s.stun = s.d.get("stun", .25)
        if act: s.act = None; s.grav = None

    # ---------- атаки ----------
    def start_attack(s, i, w):
        a = s.attacks[i]; h = ATTACKS[a["type"]]
        s.act = {"a": a, "h": h, "i": i, "phase": "windup", "t": 0.0, "hit": False}
        s.cds[i] = a.get("cooldown", 1.5); s.dir = sign(w.pl.cx - s.cx) or s.dir
        h.start(s, a, s.act, w)
    def tick_attack(s, dt, w):
        act = s.act; a, h = act["a"], act["h"]; act["t"] += dt; ph = act["phase"]
        if ph == "windup":
            h.windup(s, a, act, dt, w)
            if act["t"] >= a.get("windup", .4): act["phase"], act["t"] = "active", 0.0; h.begin(s, a, act, w)
        elif ph == "active":
            if h.active(s, a, act, dt, w): act["phase"], act["t"] = "recovery", 0.0
        elif act["t"] >= a.get("recovery", .4):
            s.act = None; s.gap = s.d.get("attack_gap", .3)
            nxt = a.get("next")
            for j, b in enumerate(s.attacks):
                if nxt and b.get("id") == nxt: s.start_attack(j, w); break
    def choose_attack(s, w):
        if s.gap > 0 or not s.aggro: return
        for i, a in enumerate(s.attacks):
            if s.cds[i] <= 0 and ATTACKS[a["type"]].can_use(s, a, w): return s.start_attack(i, w)

    # ---------- кадр ----------
    def update(s, dt, w):
        d = s.d; s.t += dt; s.flash -= dt; s.gap -= dt
        s.cds = [c - dt for c in s.cds]
        move = MOVES[s.mv.get("type", "chase")]
        look(s, w, s.mv)
        if s.stun > 0:
            s.stun -= dt; s.vx = approach(s.vx, 0, 900 * dt)
            if s.flies: s.vy = approach(s.vy, 0, 900 * dt)
        elif s.act:
            a = s.act["a"]
            if s.act.get("free"): pass                                  # прыжок/рывок — скорость задала атака
            elif a.get("mobile"): move(s, s.mv, dt, w); s.dir = sign(w.pl.cx - s.cx) or s.dir
            else:
                s.vx = approach(s.vx, 0, 900 * dt)
                if s.flies: s.vy = approach(s.vy, 0, 900 * dt)
            s.tick_attack(dt, w)
        else:
            move(s, s.mv, dt, w); s.choose_attack(w)
        if not s.flies or s.grav: s.vy = min(s.vy + (s.grav or d.get("gravity", 1800)) * dt, 900)
        s.move(w.g, dt)
        s.update_anim(dt)

    # ---------- анимация ----------
    def anim_states(s):
        """Имена анимаций по приоритету + доля пройденной фазы атаки (для подгонки кадров под длительность)."""
        if s.stun > 0: return ["hurt"], None
        if s.act:
            act, a = s.act, s.act["a"]; ph = act["phase"]
            gen = {"windup": "windup", "active": act["h"].anim(s, a, act), "recovery": "recovery"}[ph]
            dur = {"windup": a.get("windup", .4), "active": a.get("air_time", a.get("active", .12)), "recovery": a.get("recovery", .4)}[ph]
            own = a.get("anims", {}).get(gen)
            return ([own, gen] if own else [gen]), min(1, act["t"] / max(dur, .01))
        if not s.flies and not s.ground: return ["jump"], None
        if abs(s.vx) > 12 or (s.flies and abs(s.vy) > 12): return ["move"], None
        return ["idle"], None
    def update_anim(s, dt):
        st, p = s.anim_states(); key = "|".join(st)
        if key != s.anim: s.anim, s.anim_t = key, 0.0
        else: s.anim_t += dt
        s.anim_p = p

    def draw(s, v, debug=False):
        d = s.d; hot = s.flash > 0 or (s.act and s.act["phase"] == "windup" and d.get("blink", True) and int(s.act["t"] * 20) % 2)
        dw, dh = d.get("draw", [s.w, s.h]); r = s.rect
        top = r.centery - dh // 2 if s.flies else r.bottom - dh
        if s.act: s.act["h"].draw(s, s.act["a"], s.act, v)
        img = sprite(mob_frame(s.kind, d, s.anim.split("|"), s.anim_t, s.anim_p), dw, dh, s.dir < 0, bool(hot))
        if img: v.blit(img, (r.centerx - dw // 2, top))
        else:
            pg.draw.rect(v, (255, 255, 255) if hot else d.get("color", [200, 200, 200]), r, border_radius=5)
            pg.draw.rect(v, (20, 10, 10), (r.centerx + s.dir * 5 - 2, r.top + 6, 4, 4))
        if debug:
            pg.draw.rect(v, (0, 255, 0), r, 1)
            if s.act and "box" in s.act: pg.draw.rect(v, (255, 0, 255), s.act["box"], 1)
        if not d.get("boss"):
            pg.draw.rect(v, (60, 20, 20), (r.centerx - 14, top - 8, 28, 3))
            pg.draw.rect(v, (220, 60, 60), (r.centerx - 14, top - 8, 28 * max(0, s.hp) / s.maxhp, 3))

def spawn_boss(room, scale=1.0, player_count=1):
    """Создать босса на ближайшей свободной площадке; вызывается только авторитетным миром/хостом."""
    cfg = CFG.get("boss", {})
    if "__boss__" not in CFG.get("mobs", {}): return None
    d = normalize(CFG["mobs"]["__boss__"])
    # Ищем пол в центральной части комнаты, чтобы босс не появлялся внутри стены.
    candidates = []
    center = room.width_px / 2
    for c in range(room.width):
        x = c * 32 + 16
        floor_y = None
        for rr in range(room.height):
            if room.chars[rr][c] in "#D=":
                floor_y = rr * 32
                break
        if floor_y is None: continue
        rect = pg.Rect(0, floor_y - d.get("h", 72), d.get("w", 56), d.get("h", 72))
        rect.centerx = int(x)
        # Проверяем свободное место под тело; площадка сама остаётся под ногами.
        from core import free
        if free(room.g, rect): candidates.append((abs(x - center), x, floor_y))
    if candidates:
        _, x, floor_y = min(candidates)
        y = floor_y - d.get("h", 72)
    else:
        x = room.width_px / 2 - d.get("w", 56) / 2
        y = max(0, room.height_px - 3 * 32 - d.get("h", 72))
    per_player = max(0.0, float(cfg.get("health_per_player", 0.45)))
    hp_scale = scale * (1.0 + per_player * max(0, int(player_count) - 1))
    return Mob("__boss__", x, y, hp_scale)


class Corpse:
    """Проигрывает анимацию death (если она есть) на месте погибшего моба и исчезает."""
    def __init__(s, m):
        s.kind, s.d, s.dir, s.rect, s.flies = m.kind, m.d, m.dir, m.rect, m.flies
        s.t = 0.0; s.dur = anim_length(m.kind, m.d, "death") + s.d.get("corpse_time", 0)
    @property
    def dead(s): return s.t >= s.dur
    def update(s, dt): s.t += dt
    def draw(s, v):
        dw, dh = s.d.get("draw", [s.rect.w, s.rect.h]); r = s.rect
        top = r.centery - dh // 2 if s.flies else r.bottom - dh
        img = sprite(mob_frame(s.kind, s.d, ["death"], s.t), dw, dh, s.dir < 0)
        if img: v.blit(img, (r.centerx - dw // 2, top))
