"""Моб = тело + паттерн движения (movement.py) + список атак (attacks.py) + скин и анимации (anim.py).
Всё задаётся в data/mobs.json, код трогать не нужно."""
import math, random
import pygame as pg
from core import CFG, Body, sign, approach, MW, MH, T, circle_hits_rect
from movement import MOVES, look
from attacks import ATTACKS, players_of
from anim import sprite, mob_frame, anim_length
from boss_hands import HandSet, head_point, draw_boss
import status

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
    def __init__(s, kind, x, y, scale, room=None):
        s.kind = kind; s.d = d = normalize(CFG["mobs"][kind]); super().__init__(x, y, d["w"], d["h"])
        s.hp = s.maxhp = d["hp"] * scale; s.dmg_scale = d.get("dmg_scale", 1)
        s.flies = d.get("flies", False); s.dir = random.choice((-1, 1)); s.home = (s.cx, s.cy)
        s.mv = d.get("move", {"type": "chase"}); s.attacks = d.get("attacks", [])
        s.cds = [random.uniform(.3, 1.2) for _ in s.attacks]; s.gap = 0.0
        s.stun = s.flash = 0; s.t = 0.0; s.aggro = False; s.act = None; s.grav = None
        s.loop_t = random.random() * s.mv.get("period", 4); s.wp = 0
        s.anim, s.anim_t, s.anim_p = "idle", 0.0, None
        s.hands = None; s.alone = False; s._parts = None; s._shield_msg = -9.0
        status.init(s)   # статусные таймеры: заморозка / горение (status.py)
        if d.get("boss_visual") == "morgart": s.setup_morgart(room, scale)

    # ---------- Моргарт: голова = сам моб, руки — отдельные части (boss_hands.py) ----------
    def setup_morgart(s, room, scale):
        """Руки строятся от центра головы (центр физического ядра) по настройкам карты morgart_layout."""
        layout = room.d.get("morgart_layout", {}) if room is not None else {}
        world = (room.width_px, room.height_px) if room is not None else (MW, MH)
        s.world = world
        s.hands = HandSet(layout, world, (s.cx, s.cy), scale, s.dmg_scale)
        s.alone = not s.hands.list         # рук на карте нет — сразу «только голова»

    def hands_alive(s): return s.hands.alive_count() if s.hands else 0
    def head_shielded(s):
        """Пока жива хоть одна рука, голова неуязвима (assets/boss/boss.json -> mob.hands_gate_head)."""
        return bool(s.d.get("hands_gate_head", True)) and s.hands_alive() > 0
    def pop_xp(s): return s.hands.pop_xp() if s.hands else 0

    def head_rect(s):
        return pg.Rect(int(s.cx) - 78, int(s.cy) - 72 + int(math.sin(s.t * 11.0) * 2.5 * .35), 156, 144)

    def collision_rects(s):
        """Мировые хитбоксы Моргарта: голова + каждая живая рука (там, где она сейчас находится)."""
        if s.d.get("boss_visual") != "morgart": return [s.rect]
        return [s.head_rect()] + (s.hands.rects() if s.hands else [])

    def parts_where(s, test):
        """Какие части задевает проверка test(rect): None — голова, Hand — рука. Запоминается для hurt()."""
        parts = [None] if test(s.head_rect()) else []
        if s.hands: parts += s.hands.parts_at(test)
        s._parts = parts or None
        return bool(parts)

    def touches_rect(s, rect):
        """Контактный урон: касается только голова; руки бьют своими атаками."""
        if s.d.get("boss_visual") != "morgart": return s.collides_rect(rect)
        return s.head_rect().colliderect(rect)

    def collides_rect(s, rect):
        if s.d.get("boss_visual") != "morgart": return s.rect.colliderect(rect)
        return s.parts_where(rect.colliderect)

    def collides_circle(s, x, y, radius):
        if s.d.get("boss_visual") != "morgart": return circle_hits_rect(x, y, radius, s.rect)
        return s.parts_where(lambda r: circle_hits_rect(x, y, radius, r))

    def hurt_morgart(s, dmg, fx):
        """Урон получают те части, которых коснулась проверка попадания (collides_rect/circle); голова — только без рук."""
        parts, s._parts = s._parts, None
        for part in (parts or [None]):
            if part is not None: part.hurt(dmg, fx); s.aggro = True; continue
            if s.head_shielded():
                if s.t - s._shield_msg > .8:
                    s._shield_msg = s.t; fx.text("Щит! Сначала руки", s.cx, s.cy - 100); fx.ring(s.cx, s.cy, 70)
                continue
            s.hp -= dmg; s.flash = .1; s.aggro = True; fx.stop = .05; fx.text(str(int(dmg)), s.cx, s.cy - 80)

    # ---------- урон ----------
    def hurt(s, dmg, kb, fx):
        if s.d.get("boss_visual") == "morgart": return s.hurt_morgart(dmg, fx)   # голова/руки — раздельно
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
            if a.get("requires") == "alone" and s.hands_alive(): continue    # атаки «когда осталась только голова»
            if s.cds[i] <= 0 and ATTACKS[a["type"]].can_use(s, a, w): return s.start_attack(i, w)

    # ---------- кадр ----------
    def update(s, dt, w):
        d = s.d; s.t += dt; s.flash -= dt; s.gap -= dt
        s.cds = [c - dt for c in s.cds]
        status.tick(s, dt, w)   # заморозка тает, горение наносит урон
        is_morgart = d.get("boss_visual") == "morgart"
        move = MOVES[s.mv.get("type", "chase")]
        if is_morgart:
            # Физическое тело — неподвижное ядро босса. Его rect является
            # стабильным хитбоксом: гравитация, отбрасывание и chase не двигают его.
            s.vx = s.vy = 0.0
            s.stun = 0.0
            s.dir = sign(w.pl.cx - s.cx) or s.dir
            if not s.aggro and any(math.hypot(p.cx - s.cx, p.cy - s.cy) <= s.mv.get("sight", 900) for p in players_of(w)): s.aggro = True
            if s.hands:
                s.hands.update(dt, w, s.aggro)
                if not s.alone and not s.hands.alive_count(): s.on_alone(w)      # уничтожена последняя рука
            if s.act:
                s.tick_attack(dt, w)
            else:
                s.choose_attack(w)
            s.update_anim(dt)
            return
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

    def on_alone(s, w):
        """Все руки уничтожены: щит с головы снят, дальше бой идёт только с ней."""
        s.alone = True; s.aggro = True
        w.fx.ring(s.cx, s.cy, 140); w.fx.shake = max(w.fx.shake, .45)
        w.fx.text("Руки уничтожены! Голова беззащитна", s.cx - 90, s.cy - 130)
        for i in range(len(s.cds)): s.cds[i] = min(s.cds[i], .8)

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
        if d.get("boss_visual") == "morgart":
            draw_boss(v, (s.cx, s.cy), s.hands, s.t, bool(hot), appearing=True, act=s.act)
        else:
            img = sprite(mob_frame(s.kind, d, s.anim.split("|"), s.anim_t, s.anim_p), dw, dh, s.dir < 0, bool(hot))
            if img: v.blit(img, (r.centerx - dw // 2, top))
            else:
                pg.draw.rect(v, (255, 255, 255) if hot else d.get("color", [200, 200, 200]), r, border_radius=5)
                pg.draw.rect(v, (20, 10, 10), (r.centerx + s.dir * 5 - 2, r.top + 6, 4, 4))
        tcol = status.tint(s)   # заморожен — синий, горит — оранжевый
        if tcol and not d.get("boss"):
            glow = pg.Surface((max(1, dw), max(1, dh)), pg.SRCALPHA); glow.fill(tcol)
            v.blit(glow, (r.centerx - dw // 2, top))
        if debug:
            pg.draw.rect(v, (0, 255, 0), r, 1)
            if d.get("boss_visual") == "morgart":
                for hb in s.collision_rects(): pg.draw.rect(v, (255, 70, 210), hb, 2)
                if s.hands:
                    for hd in s.hands.alive_hands(): pg.draw.circle(v, (90, 220, 255), (int(hd.home[0]), int(hd.home[1])), 6, 2)
            if s.act and "box" in s.act: pg.draw.rect(v, (255, 0, 255), s.act["box"], 1)
        if not d.get("boss"):
            pg.draw.rect(v, (60, 20, 20), (r.centerx - 14, top - 8, 28, 3))
            pg.draw.rect(v, (220, 60, 60), (r.centerx - 14, top - 8, 28 * max(0, s.hp) / s.maxhp, 3))

def _draw_front(s, v):
    """Руки, державшие игрока, рисуются поверх него (вызывается после отрисовки игроков)."""
    if s.hands: s.hands.draw_front(v)
Mob.draw_front = _draw_front

def spawn_boss(room, scale=1.0, player_count=1, position=None):
    """Создать Моргарта; вызывается только авторитетным миром/хостом.
    Центр головы (он же центр физического ядра): якорь головы из карты (morgart_layout) > точка маркера C/B
    (position — низ клетки маркера, голова ставится в её центр) > стандартное место. Руки ставятся от головы."""
    cfg = CFG.get("boss", {})
    if "__boss__" not in CFG.get("mobs", {}): return None
    d = normalize(CFG["mobs"]["__boss__"])
    per_player = max(0.0, float(cfg.get("health_per_player", 0.45)))
    hp_scale = scale * (1.0 + per_player * max(0, int(player_count) - 1))
    world = (room.width_px, room.height_px)
    marker = (position[0], position[1] - T / 2) if position is not None else None
    hx, hy = head_point(room.d.get("morgart_layout", {}), world, marker)
    w, h = d.get("w", 56), d.get("h", 72)
    return Mob("__boss__", hx - w / 2, hy - h / 2, hp_scale, room)


def scale_boss_for_players(mob, player_count):
    """Босс, появившийся с маркера карты (B/C), создаётся на одного игрока. В мультиплеере (хост) дорастить здоровье
    головы и рук под число игроков так же, как это делает spawn_boss(). Повторный вызов ничего не меняет."""
    if not mob.d.get("boss") or getattr(mob, "_players_scaled", False): return
    mob._players_scaled = True
    per = max(0.0, float(CFG.get("boss", {}).get("health_per_player", 0.45)))
    k = 1.0 + per * max(0, int(player_count) - 1)
    if k == 1.0: return
    mob.hp *= k; mob.maxhp *= k
    if mob.hands:
        for h in mob.hands.list: h.hp *= k; h.maxhp *= k
        mob.hands.total_max = sum(h.maxhp for h in mob.hands.list)


class Corpse:
    """Проигрывает анимацию death (если она есть) на месте погибшего моба и исчезает."""
    def __init__(s, m):
        s.kind, s.d, s.dir, s.rect, s.flies = m.kind, m.d, m.dir, m.rect, m.flies
        s.hands = getattr(m, "hands", None)      # у Моргарта — оставшиеся руки растворяются вместе с головой
        s.t = 0.0; s.dur = anim_length(m.kind, m.d, "death") + s.d.get("corpse_time", 0)
    @property
    def dead(s): return s.t >= s.dur
    def update(s, dt): s.t += dt
    def draw(s, v):
        dw, dh = s.d.get("draw", [s.rect.w, s.rect.h]); r = s.rect
        top = r.centery - dh // 2 if s.flies else r.bottom - dh
        if s.d.get("boss_visual") == "morgart":
            draw_boss(v, r.center, getattr(s, "hands", None), s.t, fade=max(0.0, 1.0 - s.t / max(s.dur, 0.01)), appearing=False)
            return
        img = sprite(mob_frame(s.kind, s.d, ["death"], s.t), dw, dh, s.dir < 0)
        if img: v.blit(img, (r.centerx - dw // 2, top))
