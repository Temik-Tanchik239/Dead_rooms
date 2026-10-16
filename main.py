"""DEAD ROOMS — механики Dead Cells + комнаты-экраны как в Isaac.
Весь контент (физика, оружие, мобы, комнаты) лежит в data/*.json. F5 в игре — перезагрузка данных."""
import math, random, sys
from types import SimpleNamespace
import pygame as pg
from core import CFG, SETTINGS, T, COLS, ROWS, W, H, reload_data, sign, approach, tile, free, FX, Body
from anim import clear_cache
from projectiles import volley
from mob import Mob, Corpse

class Player(Body):
    H0 = 34
    def __init__(s):
        super().__init__(0, 0, 20, s.H0)
        s.hp = s.maxhp = CFG["player"]["hp"]; s.face, s.state = 1, "move"
        s.inv = s.coy = s.st = s.lock = s.drop_t = s.stun = 0
        s.atk, s.combo, s.hitbox = None, (None, 0, 0), None
        s.buf = dict(jump=0, roll=0, a1=0, a2=0); s.slots = ["rusty_sword", "short_bow"]
    def press(s, what): s.buf[what] = CFG["player"]["buffer"]
    def can_stand(s, g): return free(g, pg.Rect(int(s.x), int(s.y) - (s.H0 - s.h), s.w, s.H0))
    def hit(s, dmg, fx_x, fx, kb=260):
        if s.inv > 0: return
        s.hp -= dmg; s.inv = CFG["player"]["hurt_inv"]; s.stun = .18
        s.vx = (sign(s.cx - fx_x) or 1) * kb; s.vy = -260; fx.shake = .2; fx.stop = .06
        if s.state in ("attack", "ladder"): s.state = "move"; s.atk = None
    def start_attack(s, i):
        wid = s.slots[i]; steps = CFG["weapons"][wid]["combo"]; sl, stp, left = s.combo
        n = (stp + 1) % len(steps) if sl == wid and left > 0 else 0; st = steps[n]
        s.atk = dict(w=wid, n=n, step=st, t=0.0, wu=st["windup"], ac=st["active"], rec=st["recovery"], fired=False, hit=set())
        s.state = "attack"; s.buf["a1" if i == 0 else "a2"] = 0
    def strike(s, mobs, fx):
        a = s.atk; st = a["step"]; rw, rh = st["reach"]
        s.hitbox = pg.Rect(int(s.x + s.w if s.face > 0 else s.x - rw), int(s.cy - rh / 2), rw, rh)
        for m in mobs:
            if id(m) not in a["hit"] and s.hitbox.colliderect(m.rect):
                a["hit"].add(id(m)); m.hurt(st["damage"] * CFG["player"]["dmg_mult"], s.face * st["knockback"], fx)
    def fire(s, projs, st):
        pr = st["projectile"]; o = pr if isinstance(pr, dict) else {}
        volley(projs, pr, s.cx + s.face * 10, s.cy - 4, 0 if s.face > 0 else math.pi,
               st["damage"] * CFG["player"]["dmg_mult"], True, o.get("count", 1), o.get("spread", 0))
    def ledge(s, g):
        c = int((s.x + s.w + 2) // T) if s.wall > 0 else int((s.x - 2) // T); hr = int((s.y + 6) // T)
        if tile(g, c, hr) in "#D" and tile(g, c, hr - 1) not in "#D" and (s.y + 6) - hr * T < 16:
            nx, ny = c * T + (T - s.w) / 2, hr * T - s.h
            if free(g, pg.Rect(int(nx), int(ny), s.w, s.h)):
                s.x, s.y, s.vy, s.vx, s.lock = nx, ny, 0, s.face * 20, .25
    def update(s, dt, k, g, mobs, projs, fx):
        p = CFG["player"]; s.hitbox = None
        for b in s.buf: s.buf[b] = max(0, s.buf[b] - dt)
        s.inv -= dt; s.lock -= dt; s.drop_t -= dt
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
            elif s.buf["a1"]: s.face = d or s.face; s.start_attack(0)
            elif s.buf["a2"]: s.face = d or s.face; s.start_attack(1)
            if s.vy < 0 and not held: s.vy = max(s.vy, -p["jump"] * p["jump_cut"])
        if s.state != "ladder":
            s.vy = min(s.vy + p["gravity"] * (p["fall_mult"] if s.vy > 0 else 1) * dt, p["max_fall"])
        s.move(g, dt, drop=s.drop_t > 0)
        if p.get("ledge", True) and s.state == "move" and not s.ground and s.wall and s.wall == d and s.vy > -80 and s.lock <= 0:
            s.ledge(g)

class Drop:
    def __init__(s, x, y, wid): s.x, s.y, s.wid = x, y, wid

class Room:
    def __init__(s, pos, doors, tpl, scale, start=False):
        s.pos, s.doors, s.tpl, s.scale = pos, doors, tpl, scale
        s.visited = s.cleared = start; s.spawned = start; s.locked = False; s.mobs = []; s.corpses = []
        s.spawns = [(ci + 1, ri + 1) for ri, row in enumerate(tpl) for ci, ch in enumerate(row) if ch == "S"]
        s.drops = [Drop(W / 2, 15 * T - 14, random.choice(list(CFG["weapons"])))] if start else []
        s.build()
    def build(s):
        g = [list("#" * COLS)] + [list("#" + r.replace("S", ".").ljust(COLS - 2, ".")[:COLS - 2] + "#") for r in s.tpl] + [list("#" * COLS)]
        ch = "D" if s.locked else "."; lad = "D" if s.locked else "H"
        if "L" in s.doors: g[13][0] = g[14][0] = ch
        if "R" in s.doors: g[13][COLS - 1] = g[14][COLS - 1] = ch
        if "U" in s.doors or "D" in s.doors:
            for r in range(1, ROWS - 1):
                if g[r][14] != "#": g[r][14] = "H"
        if "U" in s.doors: g[0][14], g[0][15] = lad, ch
        if "D" in s.doors: g[ROWS - 1][14], g[ROWS - 1][15] = lad, ch
        s.g = g
    def spawn(s):
        s.spawned = True
        if not s.spawns: s.cleared = True; return
        s.locked = True; s.build(); names = list(CFG["mobs"]); wts = [CFG["mobs"][n].get("weight", 1) for n in names]
        for c, r in s.spawns:
            kind = random.choices(names, wts)[0]; d = CFG["mobs"][kind]
            s.mobs.append(Mob(kind, c * T + (T - d["w"]) / 2, r * T + T - d["h"], s.scale))

def gen_level(level):
    dirs = {"L": (-1, 0), "R": (1, 0), "U": (0, -1), "D": (0, 1)}
    cells, cur = [(0, 0)], (0, 0)
    while len(cells) < min(6 + level, 12):
        dx, dy = random.choice(list(dirs.values())); n = (cur[0] + dx, cur[1] + dy)
        if abs(n[0]) <= 3 and abs(n[1]) <= 2:
            cur = n
            if cur not in cells: cells.append(cur)
    scale = 1 + .2 * (level - 1); rooms = {}
    for c in cells:
        doors = {k for k, (dx, dy) in dirs.items() if (c[0] + dx, c[1] + dy) in cells}
        tpl = CFG["rooms"]["start"] if c == (0, 0) else random.choice(CFG["rooms"]["rooms"])["rows"]
        rooms[c] = Room(c, doors, tpl, scale, start=c == (0, 0))
    return rooms

class Game:
    def __init__(s):
        pg.init(); pg.display.set_caption("DEAD ROOMS"); s.scr = pg.display.set_mode((W, H), pg.SCALED | (pg.FULLSCREEN if SETTINGS.get("fullscreen", True) else 0)); s.debug = False; s.view = pg.Surface((W, ROWS * T))
        s.font = pg.font.SysFont("arial,dejavusans,freesans", 16, bold=True); s.big = pg.font.SysFont("arial,dejavusans,freesans", 44, bold=True)
        s.clock = pg.time.Clock(); s.new_game()
    def new_game(s): s.level = 1; s.pl = Player(); s.next_level()
    def next_level(s):
        s.rooms = gen_level(s.level); s.done = False; s.fx = FX(); s.projs = []
        if s.level > 1: s.pl.hp = min(s.pl.maxhp, s.pl.hp + 30)
        s.enter((0, 0), None)
    def enter(s, pos, via):
        pl = s.pl; r = s.room = s.rooms[pos]; r.visited = True; s.projs = []
        if pl.state == "attack": pl.state = "move"; pl.atk = None
        cx = 14 * T + (T - pl.w) / 2
        if via == "R": pl.x, pl.y = W - T - pl.w - 6, 15 * T - pl.h
        elif via == "L": pl.x, pl.y = T + 6, 15 * T - pl.h
        elif via == "D": pl.x, pl.y, pl.state = cx, 14 * T - pl.h, "ladder"
        elif via == "U": pl.x, pl.y = cx, T + 2
        else: pl.x, pl.y = W / 2 - pl.w / 2, 15 * T - pl.h
        pl.vx = pl.vy = 0; r.corpses = []
        if not r.spawned: r.spawn()
    def clear(s, r):
        r.cleared = True; r.locked = False; r.build(); s.fx.text("Зачищено!", W / 2, 120)
        if random.random() < .5: r.drops.append(Drop(W / 2, 15 * T - 14, random.choice(list(CFG["weapons"]))))
        if all(x.cleared for x in s.rooms.values()): s.done = True
    def pickup(s):
        pl = s.pl
        for dr in s.room.drops:
            if abs(dr.x - pl.cx) < 36 and abs(dr.y - pl.cy) < 50:
                i = CFG["weapons"][dr.wid].get("slot", 1) - 1
                pl.slots[i], dr.wid = dr.wid, pl.slots[i]; pl.combo = (None, 0, 0)
                s.fx.text(CFG["weapons"][pl.slots[i]]["name"], pl.cx, pl.y - 10); break
    def step(s, dt):
        fx, pl, r = s.fx, s.pl, s.room; sim = 0 if fx.stop > 0 else dt
        fx.stop = max(0, fx.stop - dt); fx.shake = max(0, fx.shake - dt)
        for it in fx.items: it[4] -= dt
        fx.items = [it for it in fx.items if it[4] > 0]
        if pl.hp <= 0: return
        pl.update(sim, pg.key.get_pressed(), r.g, r.mobs, s.projs, fx)
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
        if r.spawned and not r.cleared and not r.mobs: s.clear(r)
        if tile(r.g, int(pl.cx // T), int((pl.y + pl.h - 2) // T)) == "x": pl.hit(10, pl.cx, fx)
        x, y = r.pos
        if pl.cx < 0: s.enter((x - 1, y), "R")
        elif pl.cx > W: s.enter((x + 1, y), "L")
        elif pl.cy < 0: s.enter((x, y - 1), "D")
        elif pl.cy > ROWS * T: s.enter((x, y + 1), "U")
    def key(s, k):
        m = {pg.K_SPACE: "jump", pg.K_w: "jump", pg.K_UP: "jump", pg.K_k: "roll", pg.K_LSHIFT: "roll", pg.K_j: "a1", pg.K_l: "a2"}
        if k in m: s.pl.press(m[k])
        elif k == pg.K_e: s.pickup()
        elif k == pg.K_F5: reload_data(); clear_cache(); s.fx.text("данные перезагружены", W / 2, 80)
        elif k == pg.K_F11: pg.display.toggle_fullscreen()
        elif k == pg.K_F3: s.debug = not s.debug
        elif k == pg.K_r: s.new_game()
        elif k == pg.K_RETURN and s.done: s.level += 1; s.next_level()
        elif k == pg.K_ESCAPE: pg.quit(); sys.exit()
    def txt(s, t, x, y, col=(235, 235, 240), f=None):
        s.scr.blit((f or s.font).render(t, True, col), (x, y))
    def draw(s):
        v, r, pl = s.view, s.room, s.pl; v.fill((20, 18, 30))
        for y, row in enumerate(r.g):
            for x, ch in enumerate(row):
                X, Y = x * T, y * T
                if ch == "#": pg.draw.rect(v, (62, 56, 84), (X, Y, T, T)); pg.draw.rect(v, (88, 80, 114), (X, Y, T, 4))
                elif ch == "D": pg.draw.rect(v, (160, 60, 70), (X, Y, T, T)); pg.draw.line(v, (90, 30, 40), (X, Y), (X + T, Y + T), 3)
                elif ch == "=": pg.draw.rect(v, (150, 120, 80), (X, Y, T, 8))
                elif ch == "H":
                    for lx in (8, 24): pg.draw.line(v, (150, 110, 70), (X + lx, Y), (X + lx, Y + T), 3)
                    for ly in (6, 22): pg.draw.line(v, (150, 110, 70), (X + 8, Y + ly), (X + 24, Y + ly), 2)
                elif ch == "x": pg.draw.polygon(v, (200, 200, 215), [(X + 2, Y + T), (X + 16, Y + T - 18), (X + 30, Y + T)])
        for dr in r.drops:
            pg.draw.polygon(v, (255, 220, 90), [(dr.x, dr.y - 8), (dr.x + 8, dr.y), (dr.x, dr.y + 8), (dr.x - 8, dr.y)])
            if abs(dr.x - pl.cx) < 36: v.blit(s.font.render("[E] " + CFG["weapons"][dr.wid]["name"], True, (255, 230, 120)), (dr.x - 60, dr.y - 34))
        for c in r.corpses: c.draw(v)
        for m in r.mobs: m.draw(v, s.debug)
        for q in s.projs: q.draw(v)
        if pl.inv <= 0 or int(pg.time.get_ticks() / 60) % 2:
            pg.draw.rect(v, (200, 160, 70) if pl.state == "roll" else (240, 200, 90), pl.rect, border_radius=4)
            ex = pl.rect.right - 6 if pl.face > 0 else pl.rect.left + 3; pg.draw.rect(v, (30, 20, 20), (ex, pl.rect.top + 6, 3, 5))
        if pl.hitbox: pg.draw.rect(v, (255, 255, 255), pl.hitbox, 2)
        for kind, x, y, data, t in s.fx.items:
            if kind == "t": v.blit(s.font.render(data, True, (255, 240, 160)), (x - 14, y - (0.7 - t) * 40))
            else: pg.draw.circle(v, (255, 200, 120), (int(x), int(y)), int(data * (1 - t / .25) + 4), 2)
        ox = oy = 0
        if s.fx.shake > 0: ox, oy = random.randint(-4, 4), random.randint(-4, 4)
        s.scr.fill((10, 10, 16)); s.scr.blit(v, (ox, oy))
        bx = W - 150
        for (x, y), rm in s.rooms.items():
            nb = any(s.rooms.get((x + a, y + b)) and s.rooms[(x + a, y + b)].visited for a, b in ((1, 0), (-1, 0), (0, 1), (0, -1)))
            if not (rm.visited or nb): continue
            col = (70, 70, 90) if not rm.visited else ((80, 170, 100) if rm.cleared else (190, 80, 80))
            rc = (bx + 54 + x * 18, 8 + 24 + y * 12, 16, 10); pg.draw.rect(s.scr, col, rc)
            if rm is r: pg.draw.rect(s.scr, (255, 255, 255), rc, 2)
        pg.draw.rect(s.scr, (60, 20, 20), (10, ROWS * T + 8, 200, 16)); pg.draw.rect(s.scr, (210, 60, 60), (10, ROWS * T + 8, 200 * max(0, pl.hp) / pl.maxhp, 16))
        n = lambda i: CFG["weapons"][pl.slots[i]]["name"]
        s.txt(f"[J] {n(0)}   [L] {n(1)}", 230, ROWS * T + 7)
        s.txt(f"Ур.{s.level}  комнат {sum(x.cleared for x in s.rooms.values())}/{len(s.rooms)}", W - 190, ROWS * T + 7, (180, 180, 200))
        if pl.hp <= 0: s.txt("ТЫ УМЕР — R: заново", W // 2 - 220, 200, (255, 90, 90), s.big)
        elif s.done: s.txt("УРОВЕНЬ ПРОЙДЕН — Enter", W // 2 - 260, 200, (120, 255, 150), s.big)
        pg.display.flip()
    def run(s):
        while True:
            dt = min(s.clock.tick(60) / 1000, 1 / 30)
            for e in pg.event.get():
                if e.type == pg.QUIT: return
                if e.type == pg.KEYDOWN: s.key(e.key)
            s.step(dt); s.draw()

if __name__ == "__main__":
    Game().run()
