"""DEAD ROOMS — механики Dead Cells + карты-экраны, нарисованные вручную (data/maps/*.json, порядок — data/maps.json).
Весь контент (физика, оружие, мобы, карты) лежит в data/*.json. F5 в игре — перезагрузка данных."""
import math, random, sys
from types import SimpleNamespace
import pygame as pg
from core import CFG, SETTINGS, DATA, ASSETS, T, COLS, ROWS, W, H, MW, MH, VIEW_H, reload_data, sign, approach, tile, free, FX, Body
from anim import clear_cache, sprite, mob_frame
import weapon
import hud
from projectiles import volley
from mob import Mob, Corpse
from maps import Campaign, Drop, END, VH, check, random_weapon, pos_of, world_text, world_links, two_way

class Player(Body):
    H0 = 34
    def __init__(s):
        super().__init__(0, 0, 20, s.H0)
        s.hp = s.maxhp = CFG["player"]["hp"]; s.face, s.state = 1, "move"
        s.hp_regen_timer = 0.0
        s.inv = s.coy = s.st = s.lock = s.drop_t = s.stun = 0
        s.atk, s.combo, s.hitbox = None, (None, 0, 0), None
        s.refresh_mana(True)
        s.buf = dict(jump=0, roll=0, a1=0, a2=0, skill=0); s.slots = ["rusty_sword", "short_bow"]
        s.anim, s.anim_t, s.anim_p = "idle", 0.0, None
        s.aim = None   # куда смотрит курсор (координаты комнаты) или None
        s.skills = ["dash", "nova", "heal"]; s.skill_index = 0
        s.skill_cooldowns = {key: 0.0 for key in s.skills}; s.skill_notice = 0.0
    def press(s, what): s.buf[what] = CFG["player"]["buffer"]
    def anim_states(s):
        p = CFG["player"]
        if s.state == "roll": return ["roll"], 1 - max(0, s.st) / p["roll_time"]
        if s.state == "attack" and s.atk:
            a = s.atk; prog = min(1, a["t"] / (a["wu"] + a["ac"] + a["rec"]))
            return (["shoot", "attack"] if "projectile" in a["step"] else ["attack"]), prog
        if s.state == "ladder": return ["ladder"], None
        if s.stun > 0: return ["hurt"], None
        if not s.ground: return ["jump"], None
        return (["move"] if abs(s.vx) > 25 else ["idle"]), None
    def facing(s, d):
        """Куда повернуться при ударе: к курсору (если есть) или по движению."""
        return (sign(s.aim[0] - s.cx) or s.face) if s.aim else (d or s.face)
    def hand(s, state="idle"):
        """Где кисть в мире (по данным player.json: hand / hands)."""
        p = CFG["player"]; hx, hy = p.get("hands", {}).get(state, p.get("hand", [13, -24])); r = s.rect
        return (r.centerx + s.face * hx, r.bottom + hy)
    def aim_deg(s):
        """Угол на курсор в системе «лицом вправо» (+ вверх) или None."""
        if not s.aim: return None
        hx, hy = s.hand("shoot"); a = math.degrees(math.atan2(hy - s.aim[1], s.aim[0] - hx)); a = a if s.face > 0 else 180 - a
        return (a + 180) % 360 - 180
    def update_anim(s, dt):
        st, p = s.anim_states(); key = "|".join(st)
        if key != s.anim: s.anim, s.anim_t = key, 0.0
        else: s.anim_t += dt
        s.anim_p = p
    def draw(s, v):
        p = CFG["player"]; r = s.rect; st = s.anim.split("|")
        dw, dh = p.get("draws", {}).get(st[0], p.get("draw", [s.w, s.H0]))
        img = sprite(mob_frame("player", p, st, s.anim_t, s.anim_p, folder="player"), dw, dh, s.face < 0)
        if img: v.blit(img, (r.centerx - dw // 2, r.bottom - dh))
        else:
            pg.draw.rect(v, (200, 160, 70) if s.state == "roll" else (240, 200, 90), r, border_radius=4)
            ex = r.right - 6 if s.face > 0 else r.left + 3; pg.draw.rect(v, (30, 20, 20), (ex, r.top + 6, 3, 5))
        if st[0] not in ("roll", "ladder"): weapon.draw_held(v, s, s.hand(st[0]))
    def can_stand(s, g): return free(g, pg.Rect(int(s.x), int(s.y) - (s.H0 - s.h), s.w, s.H0))
    def hit(s, dmg, fx_x, fx, kb=260):
        if s.inv > 0: return
        s.hp -= dmg
        s.hp_regen_timer = 0.0  # любой полученный урон заново запускает задержку регенерации
        s.inv = CFG["player"]["hurt_inv"]; s.stun = .18
        s.vx = (sign(s.cx - fx_x) or 1) * kb; s.vy = -260; fx.shake = .2; fx.stop = .06
        if s.state in ("attack", "ladder"): s.state = "move"; s.atk = None
    def refresh_mana(s, full=False):
        """Прочитать настройки маны из player.json (full — заполнить стартовым значением)."""
        m = CFG["player"].get("mana", {}); s.maxmana = m.get("max", 100)
        if full: s.mana, s.mana_t, s.mana_flash = min(m.get("start", s.maxmana), s.maxmana), 0, 0
        else: s.mana = min(s.mana, s.maxmana)
    def start_attack(s, i):
        wid = s.slots[i]; steps = CFG["weapons"][wid]["combo"]; sl, stp, left = s.combo
        n = (stp + 1) % len(steps) if sl == wid and left > 0 else 0; st = steps[n]
        s.buf["a1" if i == 0 else "a2"] = 0; cost = weapon.mana_cost(wid, st)
        if s.mana < cost: s.mana_flash = .35; return   # не хватает маны — удар не начинается, полоска мигает
        s.mana -= cost; s.mana_t = CFG["player"].get("mana", {}).get("regen_delay", .9)
        s.atk = dict(w=wid, n=n, step=st, t=0.0, wu=st["windup"], ac=st["active"], rec=st["recovery"], fired=False, hit=set())
        s.state = "attack"
    def strike(s, mobs, fx):
        a = s.atk; st = a["step"]; rw, rh = st["reach"]
        s.hitbox = pg.Rect(int(s.x + s.w if s.face > 0 else s.x - rw), int(s.cy - rh / 2), rw, rh)
        for m in mobs:
            if id(m) not in a["hit"] and s.hitbox.colliderect(m.rect):
                a["hit"].add(id(m)); m.hurt(st["damage"] * CFG["player"]["dmg_mult"], s.face * st["knockback"], fx)
                s.mana = min(s.maxmana, s.mana + weapon.mana_hit(a["w"], st))   # попадание возвращает ману
    def fire(s, projs, st):
        pr = st["projectile"]; o = pr if isinstance(pr, dict) else {}
        hx, hy = s.hand("shoot"); ang = 0 if s.face > 0 else math.pi
        if s.aim: ang = math.atan2(s.aim[1] - hy, s.aim[0] - hx)   # стреляем в курсор
        volley(projs, pr, hx + math.cos(ang) * 14, hy + math.sin(ang) * 14, ang,
               st["damage"] * CFG["player"]["dmg_mult"], True, o.get("count", 1), o.get("spread", 0))
    def swap_skill(s, direction=1):
        if not s.skills: return
        s.skill_index = (s.skill_index + direction) % len(s.skills)
        s.skill_notice = 1.0
    def use_skill(s, mobs, fx):
        """Использует активный скилл из data/skills.json; новые скиллы добавляются в JSON."""
        defs = CFG.get("skills", {})
        if not s.skills: return
        sid = s.skills[s.skill_index % len(s.skills)]
        a = defs.get(sid)
        if not a: return
        if s.skill_cooldowns.get(sid, 0) > 0:
            fx.text(f"{a.get('name', sid)}: {s.skill_cooldowns[sid]:.1f}с", s.cx, s.y - 18)
            return
        kind = a.get("type", "nova")
        if kind == "dash":
            s.vx = s.face * a.get("speed", 620); s.inv = max(s.inv, a.get("invulnerability", .18))
            fx.ring(s.cx + s.face * 20, s.cy, a.get("radius", 24))
        elif kind == "nova":
            radius, damage = a.get("radius", 100), a.get("damage", 25)
            fx.ring(s.cx, s.cy, radius); fx.shake = max(fx.shake, .12)
            for m in mobs:
                if (m.cx-s.cx)**2 + (m.cy-s.cy)**2 <= radius**2:
                    m.hurt(damage * CFG["player"].get("dmg_mult", 1.0), s.face * a.get("knockback", 220), fx)
        elif kind == "heal":
            amount = a.get("amount", 30); s.hp = min(s.maxhp, s.hp + amount)
            fx.ring(s.cx, s.cy, a.get("radius", 42))
        s.skill_cooldowns[sid] = max(0.0, float(a.get("cooldown", 5.0)))
        fx.text(a.get("name", sid), s.cx, s.y - 18)

    def ledge(s, g):
        c = int((s.x + s.w + 2) // T) if s.wall > 0 else int((s.x - 2) // T); hr = int((s.y + 6) // T)
        if tile(g, c, hr) in "#D" and tile(g, c, hr - 1) not in "#D" and (s.y + 6) - hr * T < 16:
            nx, ny = c * T + (T - s.w) / 2, hr * T - s.h
            if free(g, pg.Rect(int(nx), int(ny), s.w, s.h)):
                s.x, s.y, s.vy, s.vx, s.lock = nx, ny, 0, s.face * 20, .25
    def update(s, dt, k, g, mobs, projs, fx):
        p = CFG["player"]; s.hitbox = None
        for b in s.buf: s.buf[b] = max(0, s.buf[b] - dt)
        s.inv -= dt; s.lock -= dt; s.drop_t -= dt; s.mana_t -= dt; s.mana_flash -= dt
        s.skill_notice = max(0.0, s.skill_notice - dt)
        for skill_id in s.skill_cooldowns: s.skill_cooldowns[skill_id] = max(0.0, s.skill_cooldowns[skill_id] - dt)
        if s.buf.get("skill", 0) > 0:
            s.buf["skill"] = 0
            s.use_skill(mobs, fx)
        # Регенерация здоровья: начинается после hp_regen_delay секунд без полученного урона.
        s.hp_regen_timer += dt
        hp_regen_delay = max(0.0, float(p.get("hp_regen_delay", 5.0)))
        hp_regen_rate = max(0.0, float(p.get("hp_regen", 5.0)))
        if s.hp_regen_timer >= hp_regen_delay and s.hp < s.maxhp and s.hp > 0 and hp_regen_rate > 0:
            s.hp = min(s.maxhp, s.hp + hp_regen_rate * dt)
        if s.mana_t <= 0 and s.mana < s.maxmana: s.mana = min(s.maxmana, s.mana + p.get("mana", {}).get("regen", 14) * dt)   # восстановление маны
        sl, stp, left = s.combo; s.combo = (sl, stp, left - dt)
        s.coy = p["coyote"] if s.ground else s.coy - dt
        d = (k[pg.K_d] or k[pg.K_RIGHT]) - (k[pg.K_a] or k[pg.K_LEFT])
        up, dn = k[pg.K_w] or k[pg.K_UP], k[pg.K_s] or k[pg.K_DOWN]
        held = up or k[pg.K_SPACE]
        c0, r0 = int(s.cx // T), int(s.cy // T); here = tile(g, c0, r0)
        below = tile(g, c0, int((s.y + s.h + 1) // T)); st = s.state
        # ПЕРЕКАТ (отменяет восстановление атаки, неуязвимость, низкий хитбокс)
        if s.buf["roll"] and s.coy > 0 and (st == "move" or (st == "attack" and s.atk["t"] >= s.atk["wu"])):
            s.buf["roll"] = 0; s.state = st = "roll"; s.atk = None; s.st = p["roll_time"]
            s.face = d or s.face; s.inv = max(s.inv, p["roll_inv"]); s.y += s.h - p["roll_h"]; s.h = p["roll_h"]
        if st == "roll":
            s.st -= dt; s.vx = s.face * p["roll_speed"]
            if s.st <= 0 and s.can_stand(g): s.y -= s.H0 - s.h; s.h = s.H0; s.state = "move"
        elif st == "ladder":
            s.vx = 0; s.vy = (dn - up) * p["ladder_speed"]; s.x += (c0 * T + T / 2 - s.cx) * min(1, dt * 20)
            if here != "H" or (s.ground and dn and below != "H"): s.state = "move"
            if s.buf["jump"]: s.buf["jump"] = 0; s.state = "move"; s.vy = -p["jump"] * .6; s.lock = .2; s.vx = d * p["speed"]
        elif st == "attack":
            a = s.atk; a["t"] += dt; step = a["step"]; end = a["wu"] + a["ac"]
            if a["t"] >= a["wu"]:
                if "projectile" in step:
                    if not a["fired"]: a["fired"] = True; s.fire(projs, step)
                elif a["t"] < end: s.strike(mobs, fx)
            s.vx = s.face * step["lunge"] if a["wu"] <= a["t"] < end else approach(s.vx, 0, p["friction"] * dt)
            if a["t"] >= end + a["rec"] or (a["t"] >= end and s.buf["jump"] and s.coy > 0):
                s.combo = (a["w"], a["n"], p["combo_window"]); s.state = "move"; s.atk = None
        else:
            if s.stun > 0: s.stun -= dt
            else:
                acc = (p["accel"] if d else p["friction"]) if s.ground else (p["air_accel"] if d else p["air_friction"])
                s.vx = approach(s.vx, d * p["speed"], acc * dt)
                if d: s.face = d
            if s.lock <= 0 and ((up and here == "H") or (dn and (here == "H" or below == "H"))):
                s.state = "ladder"; s.vy = 0; s.buf["jump"] = 0
            elif s.buf["jump"] and s.coy > 0:
                if dn and below == "=": s.drop_t = .25; s.y += 2
                else: s.vy = -p["jump"]
                s.buf["jump"] = 0; s.coy = 0
            elif s.buf["a1"]: s.face = s.facing(d); s.start_attack(0)
            elif s.buf["a2"]: s.face = s.facing(d); s.start_attack(1)
            if s.vy < 0 and not held: s.vy = max(s.vy, -p["jump"] * p["jump_cut"])
        if s.state != "ladder":
            s.vy = min(s.vy + p["gravity"] * (p["fall_mult"] if s.vy > 0 else 1) * dt, p["max_fall"])
        s.move(g, dt, drop=s.drop_t > 0)
        if p.get("ledge", True) and s.state == "move" and not s.ground and s.wall and s.wall == d and s.vy > -80 and s.lock <= 0:
            s.ledge(g)

def s_lock(): return CFG["maps"].get("lock", True)

class Game:
    show_world = False   # M: карта мира открыта (игра на паузе)
    def __init__(s):
        pg.init(); pg.display.set_caption("DEAD ROOMS"); s.scr = pg.display.set_mode((W, H), pg.SCALED | (pg.FULLSCREEN if SETTINGS.get("fullscreen", True) else 0)); s.debug = False; s.cam = [0, 0]; s.view = pg.Surface((MW, MH))
        s.font = pg.font.SysFont("arial,dejavusans,freesans", 16, bold=True); s.big = pg.font.SysFont("arial,dejavusans,freesans", 44, bold=True)
        s.small = pg.font.SysFont("arial,dejavusans,freesans", 11, bold=True); s.grid = False
        s.show_world = False; s.controls_open = False; s.waiting_for_bind = None; s.hud_edit = False; s.hud_drag = None; s.hud_selected = "player"; s.veil = pg.Surface((W, VIEW_H), pg.SRCALPHA); s.veil.fill((6, 6, 12, 225))
        s.clock = pg.time.Clock(); s.new_game()
        # Стартовое меню; после Esc игровой мир сохраняется и ставится на паузу.
        s.menu_mode = "start"  # start | pause | None
        s.menu_selection = 0
        # Ресурсы меню загружаются из assets рядом с исходниками/EXE.
        # Для EXE после сборки редактируйте dist/assets/menu/* — внешние ресурсы имеют приоритет.
        menu_assets = ASSETS / "menu"
        def load_menu_image(filename):
            try:
                path = menu_assets / filename
                if path.is_file():
                    return pg.image.load(str(path)).convert_alpha()
            except (pg.error, OSError):
                pass
            return None
        s.menu_background = load_menu_image("background.png")
        s.menu_button = load_menu_image("button.png")
        s.menu_button_selected = load_menu_image("button_selected.png")
        s.menu_cursor = load_menu_image("cursor.png")
        # Отдельная полупрозрачная вуаль: не перекрывает пользовательский фон почти полностью.
        s.menu_veil = pg.Surface((W, VIEW_H), pg.SRCALPHA)
        s.menu_veil.fill((6, 6, 12, 72))
        pg.mouse.set_visible(False if s.menu_cursor is not None or SETTINGS.get("mouse_aim", True) else True)
    def new_game(s, loop=0):
        if loop == 0: s.pl = Player()
        else: s.pl.hp = min(s.pl.maxhp, s.pl.hp + 30); s.pl.refresh_mana(True)
        s.camp = Campaign(loop); s.room = None; s.done = False; s.fx = FX(); s.projs = []; s.warn_t = 0
        s.warn(check())
        if CFG["maps"].get("print_world", True): print(world_text())
        first = s.camp.first
        if first is None: print("нет ни одной карты в data/maps/"); pg.quit(); sys.exit()
        s.go(first, None)
    def warn(s, msgs):
        """Ошибки в картах — в консоль и на экран (держатся 8 секунд)."""
        for m in msgs: print("[карты]", m)
        s.warnings, s.warn_until = msgs[:8], pg.time.get_ticks() + 8000
    def go(s, mid, via):
        """Перейти на карту mid. via — запись легенды выхода, через который ушли (или None)."""
        pl, camp = s.pl, s.camp; frm = s.room.id if s.room else None
        if frm and mid != frm: camp.came_from[mid] = frm
        r = s.room = camp.get(mid); r.visited = True; s.projs = []; r.corpses = []
        rect, ladder = r.arrival(frm, via, camp)
        s.place(rect, ladder); s.respawn = (rect, ladder); s.armed = False
        if not r.spawned: r.spawn()
    def place(s, rect, ladder):
        pl = s.pl
        if pl.h != pl.H0: pl.y -= pl.H0 - pl.h; pl.h = pl.H0
        pl.atk = None; pl.state = "ladder" if ladder else "move"
        pl.x = max(0, min(MW - pl.w, rect.centerx - pl.w / 2)); pl.y = rect.bottom - pl.h; pl.vx = pl.vy = 0
    def take_exit(s, z):
        r = s.room; target = s.camp.resolve(r.id, z["entry"]["exit"])
        if target == END: s.done = True; return
        if target is None:
            if pg.time.get_ticks() > s.warn_t: s.fx.text(f"выход '{z['char']}' никуда не ведёт", s.cam[0] + W / 2, s.cam[1] + 80); s.warn_t = pg.time.get_ticks() + 1500
            return
        s.go(target, z["entry"])
    def clear(s, r):
        r.cleared = True; r.set_lock(False); s.fx.text("Зачищено!", s.cam[0] + W / 2, s.cam[1] + 120)
        rw = r.d.get("reward")   # {"item": "random" | id оружия, "chance": 0.5} — выпадает у игрока
        if rw and random.random() < rw.get("chance", 1):
            wid = random_weapon() if rw.get("item", "random") == "random" else rw["item"]
            if wid in CFG["weapons"]: r.drops.append(Drop(s.pl.cx, s.pl.y + s.pl.h - 14, wid))
    def pickup(s):
        pl = s.pl
        for dr in s.room.drops:
            if abs(dr.x - pl.cx) < 36 and abs(dr.y - pl.cy) < 50:
                i = CFG["weapons"][dr.wid].get("slot", 1) - 1
                pl.slots[i], dr.wid = dr.wid, pl.slots[i]; pl.combo = (None, 0, 0)
                s.fx.text(CFG["weapons"][pl.slots[i]]["name"], pl.cx, pl.y - 10); break
    def step(s, dt):
        fx, pl, r = s.fx, s.pl, s.room; sim = 0 if (fx.stop > 0 or s.show_world or s.controls_open or s.menu_mode is not None) else dt   # меню ставит игру на паузу
        fx.stop = max(0, fx.stop - dt); fx.shake = max(0, fx.shake - dt)
        for it in fx.items: it[4] -= dt
        fx.items = [it for it in fx.items if it[4] > 0]
        if pl.hp <= 0: return
        mp = pg.mouse.get_pos(); pl.aim = (mp[0] + s.cam[0], mp[1] + s.cam[1]) if SETTINGS.get("mouse_aim", True) else None
        mb = pg.mouse.get_pressed()   # зажатая кнопка = непрерывные атаки / комбо
        if mb[0]: pl.press("a1")
        if mb[2]: pl.press("a2")
        pl.update(sim, pg.key.get_pressed(), r.g, r.mobs, s.projs, fx); pl.update_anim(sim)
        w = SimpleNamespace(g=r.g, pl=pl, mobs=r.mobs, projs=s.projs, fx=fx)   # «мир» для мобов и пуль
        for m in r.mobs:
            m.update(sim, w)
            if m.d.get("contact") and pl.rect.colliderect(m.rect): pl.hit(m.d["contact"], m.cx, fx)
        for q in s.projs: q.update(sim, w)
        s.projs = [q for q in s.projs if not q.dead]
        for m in r.mobs:
            if m.hp <= 0:
                fx.ring(m.cx, m.cy, 28); c = Corpse(m)
                if not c.dead: r.corpses.append(c)
        for c in r.corpses: c.update(sim)
        r.corpses = [c for c in r.corpses if not c.dead]
        r.mobs = [m for m in r.mobs if m.hp > 0]
        for m in r.mobs:   # упал за край карты — умер
            if m.y > VH + 200 or m.y < -400 or m.x < -400 or m.x > MW + 400: m.hp = 0
        if r.spawned and not r.cleared and not r.mobs: s.clear(r)
        sc, sr = int(pl.cx // T), int((pl.y + pl.h - 2) // T)
        if tile(r.g, sc, sr) == "x": pl.hit(r.spike_damage(sc, sr), pl.cx, fx)
        # выходы: сработают, когда игрок отошёл от места появления и потом зашёл в клетку выхода
        z = r.exit_at(pl.cx, pl.cy)
        if not s.armed and not r.exit_touch(pl.rect):   # целиком вышел из проёма
            s.armed = True
            if r.mobs and r.d.get("lock", s_lock()): r.set_lock(True)   # двери закрываются, пока есть мобы
        elif s.armed and z is not None: s.take_exit(z); return
        if pl.cx < 0 or pl.cx > MW or pl.cy < 0 or pl.cy > VH:   # за край карты
            z = None if r.locked else (z or r.exit_near(pl.rect))
            if z: s.take_exit(z)
            if s.room is r and not s.done:   # выхода нет — пропасть: урон и назад к месту появления
                pl.hit(r.d.get("fall_damage", CFG["maps"].get("fall_damage", 15)), pl.cx, fx); s.place(*s.respawn)
    CONTROL_DEFAULTS = {"jump": "SPACE", "roll": "LSHIFT", "attack1": "J", "attack2": "L", "pickup": "E", "skill": "Q", "skill_next": "C", "skill_prev": "V"}
    CONTROL_LABELS = {"jump": "Прыжок", "roll": "Уклонение", "attack1": "Атака 1 (клавиша)", "attack2": "Атака 2 (клавиша)", "pickup": "Подобрать предмет", "skill": "Использовать скилл", "skill_next": "Следующий скилл", "skill_prev": "Предыдущий скилл"}
    def controls(s):
        cfg = SETTINGS.setdefault("controls", {})
        for action, keyname in s.CONTROL_DEFAULTS.items(): cfg.setdefault(action, keyname)
        return cfg
    def key_name(s, key):
        try: return pg.key.name(pg.key.key_code(key))
        except (ValueError, TypeError): return str(key).lower()
    def save_settings(s):
        try: (DATA / "settings.json").write_text(__import__("json").dumps(SETTINGS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError as exc: print("Не удалось сохранить настройки:", exc)
    def key(s, k):
        if s.menu_mode is not None:
            if k == pg.K_UP: s.menu_selection = (s.menu_selection - 1) % (3 if s.menu_mode == "pause" else 2); return
            if k == pg.K_DOWN: s.menu_selection = (s.menu_selection + 1) % (3 if s.menu_mode == "pause" else 2); return
            if k in (pg.K_RETURN, pg.K_SPACE):
                options = ["continue", "new", "exit"] if s.menu_mode == "pause" else ["new", "exit"]
                s.menu_action(options[s.menu_selection]); return
            if k == pg.K_ESCAPE and s.menu_mode == "pause": s.menu_mode = None
            return
        if s.hud_edit:
            if k == pg.K_F2 or k == pg.K_ESCAPE: s.hud_edit = False; s.hud_drag = None; return
            if k in (pg.K_EQUALS, pg.K_PLUS, pg.K_KP_PLUS, pg.K_MINUS, pg.K_KP_MINUS):
                cfg = hud.layout(); key = s.hud_selected
                if key in ("hp", "mana"):
                    cfg[key][2] = max(20, min(500, cfg[key][2] + (8 if k in (pg.K_EQUALS, pg.K_PLUS, pg.K_KP_PLUS) else -8)))
                    cfg[key][3] = max(4, min(50, cfg[key][3] + (2 if k in (pg.K_EQUALS, pg.K_PLUS, pg.K_KP_PLUS) else -2)))
                else: cfg[key][2] = max(16, min(128, cfg[key][2] + (4 if k in (pg.K_EQUALS, pg.K_PLUS, pg.K_KP_PLUS) else -4)))
                s.save_settings(); return
            return
        if s.controls_open:
            if s.waiting_for_bind:
                if k == pg.K_ESCAPE: s.waiting_for_bind = None; return
                action = s.waiting_for_bind; s.controls()[action] = pg.key.name(k).upper(); s.waiting_for_bind = None; s.save_settings(); return
            if k in (pg.K_ESCAPE, pg.K_F1): s.controls_open = False
            return
        if k == pg.K_F1: s.controls_open = True; return
        if k == pg.K_F2: s.hud_edit = True; return
        controls = s.controls()
        def pressed(action):
            try: return k == pg.key.key_code(controls[action])
            except (ValueError, TypeError): return False
        # Все основные действия читаются из настроек управления.
        for action, buf in (("jump", "jump"), ("roll", "roll"), ("attack1", "a1"), ("attack2", "a2")):
            if pressed(action): self_press = buf; s.pl.press(self_press); return
        if pressed("pickup"): s.pickup()
        elif pressed("skill"): s.pl.press("skill")
        elif pressed("skill_next"): s.pl.swap_skill(1)
        elif pressed("skill_prev"): s.pl.swap_skill(-1)
        elif k == pg.K_F5: s.reload()
        elif k == pg.K_F4: s.grid = not s.grid
        elif k == pg.K_m: s.show_world = not s.show_world
        elif k == pg.K_F11: pg.display.toggle_fullscreen()
        elif k == pg.K_F3: s.debug = not s.debug
        elif k == pg.K_r: s.new_game()
        elif k == pg.K_RETURN and s.done: s.new_game(s.camp.loop + 1)
        elif k == pg.K_ESCAPE:
            s.menu_mode = "pause"; s.menu_selection = 0
    def menu_action(s, action):
        if action == "continue":
            s.menu_mode = None
            pg.mouse.set_visible(not SETTINGS.get("mouse_aim", True))
        elif action == "new":
            s.new_game()
            s.menu_mode = None
            pg.mouse.set_visible(not SETTINGS.get("mouse_aim", True))
        elif action == "exit":
            pg.quit(); sys.exit()
    def menu_event(s, e):
        if s.menu_mode is None: return
        if e.type == pg.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            options = ["continue", "new", "exit"] if s.menu_mode == "pause" else ["new", "exit"]
            y0 = VIEW_H // 2 + 10
            for i, action in enumerate(options):
                rect = pg.Rect(W // 2 - 150, y0 + i * 58, 300, 44)
                if rect.collidepoint(mx, my):
                    s.menu_action(action); return
    def draw_menu(s):
        if s.menu_mode == "start":
            if s.menu_background:
                s.scr.blit(pg.transform.smoothscale(s.menu_background, (W, VIEW_H)), (0, 0))
            else:
                s.scr.fill((8, 8, 17))
            # Лёгкое затемнение повышает читаемость надписей; само изображение остаётся заменяемым.
            s.scr.blit(s.menu_veil, (0, 0))
        else:
            s.scr.blit(s.menu_veil, (0, 0))
        title = s.big.render("DEAD ROOMS", True, (240, 235, 255))
        s.scr.blit(title, title.get_rect(center=(W // 2, VIEW_H // 2 - 125)))
        subtitle = "ГЛАВНОЕ МЕНЮ" if s.menu_mode == "start" else "ПАУЗА"
        st = s.font.render(subtitle, True, (175, 170, 205))
        s.scr.blit(st, st.get_rect(center=(W // 2, VIEW_H // 2 - 75)))
        options = [("НОВАЯ ИГРА", "new"), ("ВЫХОД", "exit")] if s.menu_mode == "start" else [("ПРОДОЛЖИТЬ", "continue"), ("НОВАЯ ИГРА", "new"), ("ВЫХОД", "exit")]
        y0 = VIEW_H // 2 + 10
        mouse = pg.mouse.get_pos()
        for i, (label, action) in enumerate(options):
            rect = pg.Rect(W // 2 - 150, y0 + i * 58, 300, 44)
            hovered = rect.collidepoint(mouse)
            selected = i == s.menu_selection
            button_img = s.menu_button_selected if (hovered or selected) else s.menu_button
            if button_img:
                s.scr.blit(pg.transform.smoothscale(button_img, rect.size), rect.topleft)
            else:
                col = (92, 76, 130) if hovered or selected else (43, 40, 60)
                pg.draw.rect(s.scr, col, rect, border_radius=8)
                pg.draw.rect(s.scr, (180, 160, 230) if hovered or selected else (95, 88, 120), rect, 2, border_radius=8)
            text = s.font.render(label, True, (250, 248, 255))
            s.scr.blit(text, text.get_rect(center=rect.center))
        s.txt("↑ ↓ — выбор   Enter — подтвердить   Esc — назад", W // 2 - 165, VIEW_H - 28, (175, 170, 195), s.small)
        # Пользовательский курсор рисуется поверх всего меню; заменяется файлом assets/menu/cursor.png.
        if s.menu_cursor is not None:
            mx, my = pg.mouse.get_pos()
            cursor = s.menu_cursor
            max_size = 64
            if cursor.get_width() > max_size or cursor.get_height() > max_size:
                scale = min(max_size / cursor.get_width(), max_size / cursor.get_height())
                cursor = pg.transform.smoothscale(cursor, (max(1, int(cursor.get_width() * scale)), max(1, int(cursor.get_height() * scale))))
            s.scr.blit(cursor, (mx, my))
    def hud_event(s, e):
        if not s.hud_edit: return
        cfg = hud.layout()
        if e.type == pg.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            # Приоритет более мелких/поздних элементов, затем бары.
            for key in ("weapon2", "weapon1", "skill", "player", "mana", "hp"):
                a = cfg[key]; rect = pg.Rect(a[0], a[1], a[2], a[2] if key not in ("hp", "mana") else a[3])
                if rect.collidepoint(mx, my): s.hud_selected = key; s.hud_drag = (key, mx-a[0], my-a[1]); return
        elif e.type == pg.MOUSEBUTTONUP and e.button == 1: s.hud_drag = None
        elif e.type == pg.MOUSEMOTION and s.hud_drag:
            key, dx, dy = s.hud_drag; a = cfg[key]; a[0] = max(0, min(W-a[2], e.pos[0]-dx)); a[1] = max(0, min(VIEW_H-(a[3] if key in ("hp", "mana") else a[2]), e.pos[1]-dy)); s.save_settings()
        elif e.type == pg.MOUSEBUTTONDOWN and e.button in (4, 5):
            key = s.hud_selected; a = cfg[key]; delta = 4 if e.button == 4 else -4
            if key in ("hp", "mana"): a[2] = max(20, min(500, a[2]+delta*2)); a[3] = max(4, min(50, a[3]+delta//2))
            else: a[2] = max(16, min(128, a[2]+delta))
            s.save_settings()
    def draw_hud_editor(s):
        s.txt("РЕДАКТОР HUD — перетаскивай элементы мышью | колесо или +/-: размер | F2/Esc: выход", 12, 10, (255, 230, 140), s.small)
        cfg = hud.layout()
        for key, a in cfg.items():
            rect = pg.Rect(a[0], a[1], a[2], a[2] if key not in ("hp", "mana") else a[3])
            pg.draw.rect(s.scr, (255, 220, 100) if key == s.hud_selected else (120, 180, 255), rect, 2)
            s.txt(key.upper(), rect.x, max(25, rect.y-14), (255, 255, 255), s.small)
    def controls_event(s, e):
        if not s.controls_open or e.type != pg.MOUSEBUTTONDOWN or e.button != 1 or s.waiting_for_bind: return
        mx, my = e.pos; y0 = 86
        actions = list(s.CONTROL_LABELS)
        for i, action in enumerate(actions):
            rect = pg.Rect(W // 2 - 220, y0 + i * 38, 440, 32)
            if rect.collidepoint(mx, my): s.waiting_for_bind = action; return
    def draw_controls(s):
        s.scr.blit(s.veil, (0, 0))
        title = s.big.render("УПРАВЛЕНИЕ", True, (240, 235, 255)); s.scr.blit(title, title.get_rect(center=(W // 2, 42)))
        cfg = s.controls()
        for i, (action, label) in enumerate(s.CONTROL_LABELS.items()):
            rect = pg.Rect(W // 2 - 220, 86 + i * 38, 440, 32)
            pg.draw.rect(s.scr, (58, 52, 78) if s.waiting_for_bind != action else (105, 75, 130), rect, border_radius=5)
            pg.draw.rect(s.scr, (130, 120, 165), rect, 1, border_radius=5)
            s.txt(label, rect.x + 10, rect.y + 7, (235, 235, 245), s.small)
            keytext = "НАЖМИ КЛАВИШУ…" if s.waiting_for_bind == action else str(cfg[action]).upper()
            tw = s.small.render(keytext, True, (255, 220, 130)); s.scr.blit(tw, (rect.right - tw.get_width() - 10, rect.y + 7))
        s.txt("Нажми на действие и затем нужную клавишу. Esc — отмена/выход.", W // 2 - 215, 86 + len(s.CONTROL_LABELS) * 38 + 8, (190, 190, 215), s.small)
        s.txt("Настройки сохраняются в data/settings.json", W // 2 - 150, VIEW_H - 28, (160, 220, 175), s.small)
    def reload(s):
        """F5: перечитать JSON и картинки, пересобрать карты; игрок остаётся на месте."""
        reload_data(); clear_cache(); pl = s.pl; x, y, st = pl.x, pl.y, pl.state; pl.refresh_mana()
        s.camp.reload(); s.warn(check()); s.fx.text("данные перезагружены", s.cam[0] + W / 2, s.cam[1] + 80)
        if CFG["maps"].get("print_world", True): print(world_text())
        if s.room.id not in CFG["map_defs"]: s.room = None; s.go(s.camp.first, None); return
        r = s.room = s.camp.get(s.room.id); r.visited = True
        if not r.spawned: r.spawn()
        pl.x, pl.y, pl.state = x, y, st; s.projs = []
        s.armed = not r.exit_touch(pl.rect)
        if s.armed and r.mobs and r.d.get("lock", s_lock()): r.set_lock(True)
    def txt(s, t, x, y, col=(235, 235, 240), f=None):
        s.scr.blit((f or s.font).render(t, True, col), (x, y))
    def draw(s):
        v, r, pl = s.view, s.room, s.pl; v.blit(r.layer, (0, 0))
        for dr in r.drops:
            dr.draw(v)
            if abs(dr.x - pl.cx) < 36: v.blit(s.font.render("[E] " + CFG["weapons"][dr.wid]["name"], True, (255, 230, 120)), (dr.x - 60, dr.y - 34))
        for c in r.corpses: c.draw(v)
        for m in r.mobs: m.draw(v, s.debug)
        for q in s.projs: q.draw(v)
        if pl.inv <= 0 or int(pg.time.get_ticks() / 60) % 2:
            pl.draw(v)
        if pl.hitbox and s.debug: pg.draw.rect(v, (255, 255, 255), pl.hitbox, 2)
        if s.grid: s.draw_grid(v)
        for kind, x, y, data, t in s.fx.items:
            if kind == "t": v.blit(s.font.render(data, True, (255, 240, 160)), (x - 14, y - (0.7 - t) * 40))
            else: pg.draw.circle(v, (255, 200, 120), (int(x), int(y)), int(data * (1 - t / .25) + 4), 2)
        ox = oy = 0
        if s.fx.shake > 0: ox, oy = random.randint(-4, 4), random.randint(-4, 4)
        cx = int(max(0, min(MW - W, pl.cx - W / 2))); cy = int(max(0, min(MH - VIEW_H, pl.cy - VIEW_H / 2))); s.cam = [cx, cy]   # камера следует за игроком
        s.scr.fill((10, 10, 16)); s.scr.blit(v, (ox, oy), pg.Rect(cx, cy, W, VIEW_H))
        order = s.camp.order   # прогресс: квадратик на каждую карту из order
        for i, mid in enumerate(order):
            rm = s.camp.maps.get(mid); rc = (W - 18 * len(order) - 8 + i * 18, 8, 14, 10)
            col = (55, 55, 70) if not rm or not rm.visited else ((80, 170, 100) if rm.cleared else (190, 80, 80))
            pg.draw.rect(s.scr, col, rc)
            if rm is r: pg.draw.rect(s.scr, (255, 255, 255), rc, 2)
        label = r.name + (f"  [{r.pos[0]}, {r.pos[1]}]" if r.pos else "")   # имя карты и её координата в сетке мира
        s.txt(label, W - 18 * len(order) - 16 - s.font.size(label)[0], 4, (220, 220, 235))
        if pg.time.get_ticks() < s.warn_until:
            for i, m in enumerate(s.warnings): s.txt("! " + m, 10, 8 + i * 20, (255, 140, 120))
        hud.draw(s.scr, pl, s.small)   # иконки персонажа и оружия, под персонажем полоски HP и маны (поверх игры)
        if s.camp.loop: s.txt(f"Круг {s.camp.loop + 1}", W - 90, VIEW_H - 24, (180, 180, 200))
        if pl.hp <= 0: s.txt("ТЫ УМЕР — R: заново", W // 2 - 220, 200, (255, 90, 90), s.big)
        elif s.done: s.txt("ВСЕ КАРТЫ ПРОЙДЕНЫ — Enter: ещё круг", W // 2 - 380, 200, (120, 255, 150), s.big)
        if s.show_world: s.draw_world()
        if s.controls_open: s.draw_controls()
        if s.hud_edit: s.draw_hud_editor()
        if s.menu_mode is not None: s.draw_menu()
        if pl.aim and s.menu_mode is None:   # прицел
            mx, my = pl.aim[0] - s.cam[0], pl.aim[1] - s.cam[1]; col = (255, 255, 255); pg.draw.circle(s.scr, col, (mx, my), 10, 1); pg.draw.circle(s.scr, col, (mx, my), 1)
            for a in ((-17, 0, -7, 0), (7, 0, 17, 0), (0, -17, 0, -7), (0, 7, 0, 17)): pg.draw.line(s.scr, col, (mx + a[0], my + a[1]), (mx + a[2], my + a[3]))
        pg.display.flip()
    def draw_world(s):
        """M: сетка мира. Клетка = карта (её pos в data/maps/<id>.json), линия = переход между картами:
        серая — в обе стороны, оранжевая — только в одну. Красная клетка — карта не зачищена, зелёная — зачищена."""
        s.scr.blit(s.veil, (0, 0)); defs = CFG["map_defs"]; cells = {m: pos_of(m) for m in defs if pos_of(m)}
        s.txt("Карта мира (M — закрыть)     x → вправо, y ↓ вниз     [x, y] — поле pos в data/maps/<id>.json", 12, 8, (220, 220, 235))
        s.txt("белая рамка — вы здесь   красная — не зачищена   зелёная — зачищена   серая линия — переход в обе стороны   оранжевая — только в одну", 12, VIEW_H - 22, (170, 175, 200), s.small)
        if not cells: s.txt('ни у одной карты нет pos — впиши "pos": [x, y] в data/maps/<id>.json', 12, 40, (255, 160, 120)); return
        xs, ys = [p[0] for p in cells.values()], [p[1] for p in cells.values()]; nx, ny = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
        cw, ch = min(190, (W - 60) // nx), min(100, (VIEW_H - 90) // ny); ox, oy = (W - nx * cw) // 2, 40 + (VIEW_H - 40 - ny * ch) // 2
        links = world_links(); reveal = CFG["maps"].get("world", {}).get("reveal", "all")
        def seen(m): rm = s.camp.maps.get(m); return bool(rm and rm.visited)
        show = {m for m in cells if reveal == "all" or seen(m) or any(seen(b) for a, b in links if a == m) or any(seen(a) for a, b in links if b == m)}
        rc = {m: pg.Rect(ox + (cells[m][0] - min(xs)) * cw, oy + (cells[m][1] - min(ys)) * ch, cw - 16, ch - 16) for m in show}
        for a, b in links:
            if a in rc and b in rc and not ((b, a) in links and a > b):
                pg.draw.line(s.scr, (120, 120, 150) if two_way(a, b) else (255, 170, 70), rc[a].center, rc[b].center, 3)
        for m, rect in rc.items():
            rm = s.camp.maps.get(m); col = (45, 45, 62) if not (rm and rm.visited) else ((60, 130, 85) if rm.cleared else (150, 60, 60))
            pg.draw.rect(s.scr, col, rect, border_radius=6); pg.draw.rect(s.scr, (255, 255, 255) if m == s.room.id else (110, 110, 140), rect, 3 if m == s.room.id else 1, border_radius=6)
            s.scr.blit(s.font.render(defs[m].get("name", m), True, (240, 240, 250)), (rect.x + 8, rect.y + 6))
            s.scr.blit(s.small.render(f"{m}   [{cells[m][0]}, {cells[m][1]}]" + "", True, (200, 205, 225)), (rect.x + 8, rect.bottom - 18))
    def draw_grid(s, v):
        """F4: сетка с номерами клеток — удобно рисовать карту. Под курсором — столбец, строка и символ."""
        for c in range(COLS): pg.draw.line(v, (110, 110, 140), (c * T, 0), (c * T, VH))
        for r in range(ROWS): pg.draw.line(v, (110, 110, 140), (0, r * T), (W, r * T))
        for c in range(0, COLS, 2): v.blit(s.small.render(str(c), True, (255, 255, 120)), (c * T + 2, 2))
        for r in range(ROWS): v.blit(s.small.render(str(r), True, (255, 255, 120)), (2, r * T + 2))
        mx, my = pg.mouse.get_pos(); c, r = (mx + s.cam[0]) // T, (my + s.cam[1]) // T
        if 0 <= c < COLS and 0 <= r < ROWS:
            pg.draw.rect(v, (255, 255, 120), (c * T, r * T, T, T), 2)
            v.blit(s.font.render(f"столбец {c}, строка {r}: '{s.room.chars[r][c]}'", True, (255, 255, 120)), (mx + s.cam[0] + 14, my + s.cam[1] + 14))
    def run(s):
        while True:
            dt = min(s.clock.tick(60) / 1000, 1 / 30)
            # В меню используем курсор из assets; в забеге сохраняем обычное управление мышью.
            pg.mouse.set_visible(s.menu_mode is not None and s.menu_cursor is None or s.menu_mode is None and not SETTINGS.get("mouse_aim", True))
            for e in pg.event.get():
                if e.type == pg.QUIT: return
                if e.type == pg.KEYDOWN: s.key(e.key)
                if s.menu_mode is not None:
                    s.menu_event(e)
                elif s.hud_edit: s.hud_event(e)
                elif e.type == pg.MOUSEBUTTONDOWN and s.controls_open: s.controls_event(e)
                elif e.type == pg.MOUSEBUTTONDOWN and e.button in (1, 3): s.pl.press("a1" if e.button == 1 else "a2")
            s.step(dt); s.draw()

if __name__ == "__main__":
    Game().run()
