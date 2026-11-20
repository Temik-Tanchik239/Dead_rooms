"""Клон героя — навык type "clone" (@spell в spells.py).

При активации навыка рядом с героем появляется его точная копия:
  * собственный ИИ: ищет ближайшего врага (моба) в радиусе зрения, преследует его
    (с автопрыжком через стенку в клетку и небольшие пропасти — как chase у мобов)
    и атакует; когда врагов нет — следует за хозяином, спрыгивая с уступов к нему;
  * здоровье задаёт навык ("hp", по умолчанию 100): вражеские melee-зоны и вражеские
    снаряды могут убить клона (см. attacks.players_of / projectiles.Proj.targets);
  * оружие — то, что было «в руке» героя в момент призыва (last_weapon): клон использует
    его комбо как игрок — ближние шаги бьют хитбоксом, шаги с projectile стреляют;
    руки были пусты (маг, бард) — простая базовая атака BASIC_ATTACK;
  * живёт duration секунд, растворяется при отставании от хозяина дальше leash
    (переход комнаты, телепорт) и уходит вместе с гибелью героя.
Клон-приманка: моб выбирает между героем и ближайшим заметно более близким клоном
(clone.decoy) — враги переключаются на клона, пока он жив.
Клоны хранятся у своего игрока (pl.clones), тикают из Game.step / HostSession.step —
clone.update_all(). Клоны НЕ считаются мобами: зачистку комнаты не держат, игрок по ним
не попадает. В мультиплеере клоны считает хост, клиент видит их из снимка ("cls", NetClone).
"""
import math
from types import SimpleNamespace
import pygame as pg
from core import CFG, Body, T, MW, MH, sign, approach, free, use_char
from projectiles import volley
from movement import wall_ahead, edge_ahead, try_ground_jump
import weapon
import invisibility
from anim import sprite, mob_frame

# Шаг комбо базовой атаки клона без оружия (формат шага из weapons.json).
BASIC_ATTACK = {"name": "Базовая атака", "windup": .22, "active": .09, "recovery": .24,
                "damage": 10, "reach": [42, 32], "knockback": 180, "lunge": 60}


def alive(owner):
    """Живые клоны владельца (игрока)."""
    return [c for c in getattr(owner, "clones", ()) if getattr(c, "hp", 0) > 0]


def update_all(owner, dt, g, mobs, projs, fx):
    """Каждый кадр (Game.step / HostSession.step): тик клонов игрока и уборка мёртвых.
    Герой погиб — клоны растворяются вместе с ним; dt == 0 (пауза) — только уборка."""
    clones = getattr(owner, "clones", None)
    if clones is None:
        owner.clones = clones = []
    for c in clones:
        if c.hp > 0 and owner.hp > 0 and dt > 0:
            c.update(dt, g, mobs, projs, fx)
        elif c.hp > 0 and owner.hp <= 0:
            c.hp = 0.0   # хозяин погиб — клоны уходят вместе с ним
        if c.hp <= 0 and not c.gone:
            c.gone = True
            c.dissolve(fx)
    owner.clones[:] = [c for c in clones if c.hp > 0]


def _xb_step(owner):
    """Шаг атаки клона по арбалету героя (Тень): снаряд = текущий заряженный вид боеприпаса
    (crossbow.current). None — арбалетов нет или стрелять нечем (гарпун на нити — не даём)."""
    import crossbow
    if not crossbow.enabled():
        return None
    sid = crossbow.current(owner, 0)
    a = CFG.get("skills", {}).get(sid) if sid else None
    if not a or a.get("hook"):
        return None
    from spells import projectile_spec   # лениво: spells.py импортирует clone.py
    spec = projectile_spec(dict(a, _sid=sid))
    return {"name": a.get("name", "Арбалет"), "windup": .18, "active": .05, "recovery": .3,
            "damage": float(a.get("damage", 10)), "knockback": 120, "lunge": 0,
            "projectile": spec, "cooldown": float(a.get("cooldown", .3))}


def spawn(owner, a, mobs, fx):
    """Призвать клона (вызывается из @spell("clone") в spells.py). Свойство a — поля навыка:
    hp, duration, max, damage_mult, basic_damage, sight, speed_mult, follow, leash.
    Оружие клона — то, что было в руке героя (last_weapon); пусто — базовая атака."""
    wid = getattr(owner, "last_weapon", None)
    if wid not in CFG["weapons"]:
        wid = (owner.slots[0] if getattr(owner, "slots", None) else None)
    if wid not in CFG["weapons"]:
        wid = None   # руки пусты (маг, бард, арбалетчик) — базовая атака или арбалет
    xb = None
    if wid is None:
        with use_char(owner.char_id):
            xb = _xb_step(owner)   # арбалетчик: клон стреляет текущим боеприпасом
    x, y = _free_spot(owner)
    if getattr(owner, "clones", None) is None:
        owner.clones = []
    mx = max(1, int(a.get("max", 1)))
    cur = alive(owner)
    while len(cur) >= mx:   # лишние (старейшие) клоны растворяются, освобождая место
        old = cur.pop(0)
        old.hp = 0.0
        old.gone = True
        old.dissolve(fx)
    owner.clones.append(Clone(owner, x, y, wid, a, xb))
    sk = CFG.get("skills", {}).get("clone", {})
    col = tuple(sk.get("color", [130, 220, 255]))
    fx.flash(x + owner.w / 2, y, 26, col)
    fx.ring(x + owner.w / 2, y + owner.h / 2, 30)
    return True


def _free_spot(owner):
    """Свободная точка рядом с героем (клетки перед ним/за ним/под ним); сетка комнаты
    приходит через pl.grid (Game.step/HostSession.step). Не нашли — прямо на героя."""
    g = getattr(owner, "grid", None)
    if g is None:
        return owner.x, owner.y
    for dx in (owner.face * T * 1.5, -owner.face * T * 1.5, 0.0, owner.face * T * 2.5, -owner.face * T * 2.5):
        x = owner.x + dx
        if free(g, pg.Rect(int(x), int(owner.y), owner.w, owner.h)):
            return x, owner.y
    return owner.x, owner.y


def decoy(w, m, fallback=None):
    """Кого моб m считает целью (Game.step / HostSession.step вместо w.pl): герой, а если рядом
    живой клон-приманка, заметно ближе героя, — то клон. После гибели клона враг вернётся к герою."""
    base = fallback if fallback is not None else getattr(w, "pl", None)
    if base is None:
        return None
    best, bd = base, math.hypot(base.cx - m.cx, base.cy - m.cy)
    for c in getattr(w, "clones", ()):
        if getattr(c, "hp", 0) <= 0:
            continue
        d = math.hypot(c.cx - m.cx, c.cy - m.cy)
        if d < bd * .9:   # перетягивает агр только если заметно ближе
            best, bd = c, d
    return best


def view_of(game):
    """Клоны для отрисовки (Game.draw): у хоста — настоящие клоны всех игроков,
    у клиента — «картинки» из снимка хоста (view_clones), в одиночной — клоны героя."""
    net = getattr(game, "net", None)
    if net is not None and getattr(net, "in_game", False):
        if getattr(net, "is_host", False):   # хост: считает клоны сам
            return [c for p in net.players.values() for c in getattr(p, "clones", ()) if c.hp > 0]
        return list(getattr(net, "view_clones", ()) or ())   # клиент: «картинки» из снимка
    return alive(getattr(game, "pl", None))


class Clone(Body):
    """Копия героя с собственным ИИ. Тело — как у моба/игрока (Body): физика, гравитация.
    Интерфейс пересекается с Player настолько, чтобы работали weapon.held_pose и анимация персонажа."""

    is_clone = True

    def __init__(s, owner, x, y, wid, a, xb=None):
        with use_char(owner.char_id):
            ch = CFG.get("character", {})
            hitbox = ch.get("hitbox", [20, 34])
            try:
                hw, hh = max(4, int(hitbox[0])), max(4, int(hitbox[1]))
            except (TypeError, ValueError, IndexError):
                hw, hh = 20, 34
            p = CFG["player"]
            s.speed = float(p["speed"]) * float(a.get("speed_mult", .95))
            s.accel = float(p["accel"])
            s.jump_v = float(p["jump"])
            s.gravity = float(p["gravity"])
            s.max_fall = float(p["max_fall"])
            s.combo_window = float(p["combo_window"])
            s.model_scale = max(.1, min(5.0, float(p.get("model_scale", 1.0))))
        super().__init__(x, y, hw, hh)
        s.H0 = hh
        s.owner = owner
        s.char_id = owner.char_id
        s.wid = wid
        s.slots = [wid, None]           # как Player.slots: [оружие в руке, —]
        s.last_weapon = wid
        s.face = owner.face
        s.state, s.anim, s.anim_t, s.anim_p = "move", "idle", 0.0, None
        s.aim, s.atk, s.hitbox = None, None, None
        s.combo = (None, 0, 0)          # (weapon, номер шага, окно комбо) — как у игрока
        s.maxhp = s.hp = max(1.0, float(a.get("hp", 100)))
        s.life = max(0.0, float(a.get("duration", 0.0)))
        s.dmg_mult = float(a.get("damage_mult", .7)) * owner.dmg_mult()
        # арбалет (Тень) — синтетический шаг с projectile; иначе базовая атака руками
        s.basic = xb or dict(BASIC_ATTACK, damage=float(a.get("basic_damage", BASIC_ATTACK["damage"])))
        s.sight = float(a.get("sight", 400.0))
        s.follow = float(a.get("follow", 90.0))
        s.leash = float(a.get("leash", 1100.0))
        s.t, s.flash, s.inv = 0.0, 0.0, .4
        s.cd = .5                       # полсекунды после призыва не бьёт
        s.gone = False                  # растворён (убран из списка update_all)
        s.d = {"jump": s.jump_v}        # данные как у моба: movement.try_ground_jump читает m.d["jump"]
        s._jmp = {"jump": s.jump_v, "jump_gap": 3}
        s.target = None

    # ---------------- ИИ ----------------

    def update(s, dt, g, mobs, projs, fx):
        s.t += dt
        s.flash = max(0.0, s.flash - dt)
        s.inv -= dt
        s.cd -= dt
        s.life -= dt
        owner = s.owner
        far = math.hypot(owner.cx - s.cx, owner.cy - s.cy) > s.leash   # хозяин ушёл (смена комнаты, телепорт)
        if s.life <= 0 or far or s.y > MH + 300 or s.y < -500 or s.x < -300 or s.x > MW + 300:
            s.hp = 0.0
            return
        tgt = s.pick_target(mobs)
        s.target = tgt
        if s.atk:
            if tgt is not None:
                s.aim = (tgt.cx, tgt.cy)
            s.state = "attack"
            s.tick_attack(dt, mobs, projs, fx)
        elif tgt is not None:
            dx = tgt.cx - s.cx
            dist = math.hypot(dx, tgt.cy - s.cy)
            s.face = sign(dx) or s.face
            s.aim = (tgt.cx, tgt.cy)
            s.state = "move"
            lo, hi = s.attack_band()
            if s.cd <= 0 and lo <= dist <= hi:
                s.start_attack(tgt)
            else:
                d = sign(dx) or s.face
                if dist < lo:
                    d = -d              # стрелок отходит, если цель вплотную
                s.walk(g, dt, d)
        else:
            s.aim = None
            s.state = "move"
            dx, dy = owner.cx - s.cx, owner.cy - s.cy
            if abs(dx) > s.follow:
                s.walk(g, dt, sign(dx), drop=dy > 48)   # за хозяином, спрыгивая с уступа, если он ниже
            else:
                s.vx = approach(s.vx, 0.0, s.accel * dt)
        s.vy = min(s.vy + s.gravity * dt, s.max_fall)
        s.move(g, dt)
        s.update_anim(dt)

    def pick_target(s, mobs):
        """Ближайший живой враг в радиусе зрения (моб; ящики и манекены не в счёт)."""
        best, bd = None, s.sight
        for m in mobs:
            if getattr(m, "is_container", False) or getattr(m, "is_dummy", False):
                continue
            if getattr(m, "hp", 0) <= 0:
                continue
            dd = math.hypot(m.cx - s.cx, m.cy - s.cy)
            if dd < bd:
                bd, best = dd, m
        return best

    def attack_band(s):
        """(ближняя, дальняя) дистанция боя: по первому шагу комбо оружия (melee/ranged), иначе базовая атака."""
        if s.wid and s.wid in CFG["weapons"]:
            steps = CFG["weapons"][s.wid]["combo"]
            if "projectile" in steps[0]:
                return 90.0, 320.0
            return 0.0, float(steps[0].get("reach", [44, 30])[0]) + s.w / 2 + 10
        if "projectile" in s.basic:
            return 90.0, 320.0   # арбалет клона (Тень)
        return 0.0, float(s.basic["reach"][0]) + s.w / 2 + 10

    def walk(s, g, dt, d, drop=False):
        """Шаг в сторону d с автопрыжком через стенку в клетку и небольшие пропасти (как chase у мобов).
        drop — можно спрыгнуть с уступа (хозяин ниже)."""
        go = True
        if s.ground and s.vy >= -20:
            w = SimpleNamespace(g=g)
            if wall_ahead(s, w, d) or (edge_ahead(s, w, d) and not drop):
                if not try_ground_jump(s, s._jmp, w, d):
                    go = False
        s.vx = approach(s.vx, d * s.speed if go else 0.0, s.accel * dt)

    # ---------------- атаки ----------------

    def start_attack(s, tgt):
        """Начать шаг комбо (как Player.start_attack, но без маны)."""
        if s.wid and s.wid in CFG["weapons"]:
            steps = CFG["weapons"][s.wid]["combo"]
            sl, stp, left = s.combo
            n = (stp + 1) % len(steps) if sl == s.wid and left > 0 else 0
            st, w = steps[n], s.wid
        else:
            st, n, w = s.basic, 0, None
        s.face = sign(tgt.cx - s.cx) or s.face
        s.atk = dict(w=w, n=n, step=st, t=0.0, phase="windup", wu=float(st.get("windup", .2)),
                     ac=float(st.get("active", .1)), rec=float(st.get("recovery", .25)), fired=False, hit=set())
        s.state = "attack"

    def tick_attack(s, dt, mobs, projs, fx):
        """Фазы шага комбо: замах -> удар/выстрел -> возврат (как Melee/Shoot у игрока и мобов)."""
        act = s.atk
        st = act["step"]
        act["t"] += dt
        if act["phase"] == "windup":
            if act["t"] >= act["wu"]:
                act["phase"], act["t"] = "active", 0.0
                s.vx = s.face * float(st.get("lunge", 0))   # шаг вперёд, как у игрока/мобов
        elif act["phase"] == "active":
            if "projectile" in st:
                if not act["fired"]:
                    act["fired"] = True
                    s.fire(projs, st)
            else:
                s.strike(mobs, st, act, fx)
            if act["t"] >= max(act["ac"], .05):
                act["phase"], act["t"] = "recovery", 0.0
        elif act["phase"] == "recovery" and act["t"] >= act["rec"]:
            s.atk = None
            s.hitbox = None
            s.combo = (s.wid, act["n"], s.combo_window)
            s.cd = float(st.get("cooldown", 0.0)) or .25    # пауза между атаками

    def strike(s, mobs, st, act, fx):
        """Ближний удар: хитбокс по лицу клона (как Player.strike), каждый враг — один раз за шаг."""
        rw, rh = st.get("reach", [42, 32])
        s.hitbox = pg.Rect(int(s.x + s.w if s.face > 0 else s.x - rw), int(s.cy - rh / 2), rw, rh)
        for m in mobs:
            if id(m) in act["hit"]:
                continue
            hits = m.collides_rect(s.hitbox) if hasattr(m, "collides_rect") else s.hitbox.colliderect(m.rect)
            if hits:
                act["hit"].add(id(m))
                m.hurt(st.get("damage", 10) * s.dmg_mult, s.face * st.get("knockback", 180), fx)

    def fire(s, projs, st):
        """Выстрел шагом комбо с projectile (как Player.fire, только в цель клона)."""
        pr = st["projectile"]
        o = pr if isinstance(pr, dict) else {}
        hx, hy = s.hand("shoot")
        ang = 0.0 if s.face > 0 else math.pi
        if s.aim:
            ang = math.atan2(s.aim[1] - hy, s.aim[0] - hx)
        volley(projs, pr, hx + math.cos(ang) * 14, hy + math.sin(ang) * 14, ang,
               st.get("damage", 10) * s.dmg_mult, True, o.get("count", 1), o.get("spread", 0))

    def hit(s, dmg, fx_x, fx, kb=260):
        """Клон получил урон (вражеская melee-зона или снаряд; сигнатура как Player.hit)."""
        if s.inv > 0 or s.hp <= 0:
            return
        s.hp -= float(dmg)
        s.flash = .15
        fx.stop = max(fx.stop, .03)
        fx.text(str(int(dmg)), s.cx, s.y)
        s.vx = (sign(s.cx - fx_x) or 1) * kb
        s.vy = -180
        s.inv = .2
        if s.atk and s.atk["phase"] == "windup":
            s.atk = None   # замах сбит

    # ---------------- анимация и отрисовка ----------------

    def anim_states(s):
        """Пара (список состояний, прогресс атаки) — как Player.anim_states, для анимации персонажа."""
        if s.flash > 0:
            return ["hurt"], None
        if s.state == "attack" and s.atk:
            a = s.atk
            prog = min(1.0, a["t"] / max(a["wu"] + a["ac"] + a["rec"], .01))
            return (["shoot", "attack"] if "projectile" in a["step"] else ["attack"]), prog
        if not s.ground:
            return ["jump"], None
        return (["move"] if abs(s.vx) > 25 else ["idle"]), None

    def update_anim(s, dt):
        st, p = s.anim_states()
        key = "|".join(st)
        if key != s.anim:
            s.anim, s.anim_t = key, 0.0
        else:
            s.anim_t += dt
        s.anim_p = p

    def aim_deg(s):
        """Угол на цель в системе «лицом вправо» (для позы оружия при выстреле) или None."""
        if not s.aim:
            return None
        hx, hy = s.hand("shoot")
        a = math.degrees(math.atan2(hy - s.aim[1], s.aim[0] - hx))
        return a if s.face > 0 else (180 - a + 180) % 360 - 180

    def hand(s, state="idle"):
        """Точка «руки» (как Player.hand) — старт оружия и выстрелов."""
        with use_char(s.char_id):
            p = CFG["player"]
            hx, hy = p.get("hands", {}).get(state, p.get("hand", [13, -24]))
            r = s.rect
            return (r.centerx + s.face * hx, r.bottom + hy)

    def dissolve(s, fx):
        """Исчезновение клона: вспышка и кольцо цвета навыка."""
        sk = CFG.get("skills", {}).get("clone", {})
        col = tuple(sk.get("color", [130, 220, 255]))
        fx.flash(s.cx, s.cy, 26, col)
        fx.ring(s.cx, s.cy, 30)

    def draw(s, v, debug=False):
        with use_char(s.char_id):
            p = CFG["player"]
            r = s.rect
            st = s.anim.split("|")
            dw, dh = p.get("draws", {}).get(st[0], p.get("draw", [s.w, s.H0]))
            dw, dh = max(1, int(dw * s.model_scale)), max(1, int(dh * s.model_scale))

            def body():
                img = sprite(mob_frame(f"player:{s.char_id}", p, st, s.anim_t, s.anim_p,
                                       folder=p.get("folder", "player")), dw, dh, s.face < 0)
                if img:
                    v.blit(img, (r.centerx - dw // 2, r.bottom - dh))
                else:
                    pg.draw.rect(v, (150, 210, 255), r, border_radius=4)
                    pg.draw.rect(v, (20, 30, 40), (r.centerx + s.face * 5 - 2, r.top + 6, 4, 4))
                if s.state == "attack" and s.atk and st[0] != "roll":
                    weapon.draw_held(v, s, s.hand(st[0]))
                # голубая тонировка — сразу видно, что это клон
                tint = pg.Surface((dw, dh), pg.SRCALPHA)
                tint.fill((110, 200, 255, 55))
                v.blit(tint, (r.centerx - dw // 2, r.bottom - dh))
                # полоска здоровья
                bw = 36
                pg.draw.rect(v, (16, 24, 36), (r.centerx - bw // 2, r.top - 11, bw, 4))
                pg.draw.rect(v, (120, 225, 255), (r.centerx - bw // 2, r.top - 11, int(bw * max(0.0, s.hp) / s.maxhp), 4))

            a = 235 if s.flash > 0 else 175   # полупрозрачный «призрак»; при уроне ярче
            area = pg.Rect(r.centerx - dw // 2, r.bottom - dh, dw, dh).inflate(80, 46)
            invisibility.ghost(v, area, body, a)
            if debug:
                pg.draw.rect(v, (120, 225, 255), r, 1)
                if s.hitbox:
                    pg.draw.rect(v, (255, 120, 120), s.hitbox, 1)


class NetClone(Clone):
    """Клон на клиенте мультиплеера: только картинка из снимка хоста (считает хост)."""

    def __init__(s, char_id, x, y, face, hp, maxhp, state, anim, anim_t, wid):
        with use_char(char_id):
            hitbox = CFG.get("character", {}).get("hitbox", [20, 34])
            try:
                hw, hh = max(4, int(hitbox[0])), max(4, int(hitbox[1]))
            except (TypeError, ValueError, IndexError):
                hw, hh = 20, 34
            p = CFG["player"]
        Body.__init__(s, x, y, hw, hh)
        s.H0 = hh
        s.model_scale = max(.1, min(5.0, float(p.get("model_scale", 1.0))))
        s.char_id = char_id
        s.face = 1 if face >= 0 else -1
        s.wid = wid if wid in CFG["weapons"] else None
        s.slots = [s.wid, None]
        s.last_weapon = s.wid
        s.hp, s.maxhp = float(hp), float(maxhp)
        s.state = state or "move"
        s.anim = anim or "idle"
        s.anim_t = float(anim_t or 0.0)
        s.anim_p = None
        s.aim, s.atk, s.hitbox, s.flash, s.inv = None, None, None, 0.0, 0.0
        s.gone = False
        s.target = None

    def update(s, *a, **k):
        pass   # клиент не считает клона
