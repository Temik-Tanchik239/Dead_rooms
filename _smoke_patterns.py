# -*- coding: utf-8 -*-
"""Смоук 10 новых паттернов атак (boomerang/orbit/vortex/mine/zone/storm/rain/beam + ghost/at_cursor):
бумеранг возвращается, рой самонаводится, чёрная дыра стягивает, мина взрывается при подходе,
зона морозит, шторм бьёт молниями, дождь роняет кинжалы, луч пронзает линию, клинки кружат,
призма распадается кольцом осколков. Заодно: мана/кулдаун у всех новых навыков, полный кадр."""
import os, sys, io, random
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import pygame as pg
import main, core, spells, spell_tablet, projectiles, mob as mob_mod

pg.init(); pg.font.init(); pg.display.set_mode((core.W, core.VIEW_H))
core.CFG["maps"]["print_world"] = False   # без отладочного дампа карты мира при старте

g = main.Game(); g.new_game(character="mage"); g.menu_mode = None
pl = g.pl
core.apply_character("mage")

# тестовый моб: стоит на месте, много HP — движение и смерть не мешают проверкам
core.CFG["mobs"]["_smoke_dummy"] = {"name": "тест", "hp": 400, "xp": 1, "speed": 0, "w": 18, "h": 22,
                                    "move": {"type": "stand"}}

def add_mob(x, y):
    m = mob_mod.Mob("_smoke_dummy", float(x), float(y), 1.0, g.room)
    g.room.mobs.append(m)
    return m

def add_mob_free(x, y):
    """Моб-манекен: ищем свободный прямоугольник рядом с (x, y) — спираль по горизонтали."""
    for k in range(60):
        dx = 0 if not k else (k * 9 if k % 2 else -k * 9)
        if core.free(g.room.g, pg.Rect(int(x + dx), int(y), 18, 22)):
            return add_mob(x + dx, y)
    raise AssertionError("нет свободного места для моба")

def clear_mobs():
    g.room.mobs.clear()   # комната пуста от своих мобов — только манекены теста (чтобы самонаводящиеся/воронка не отвлекались)

def place(dx, dy=0.0):
    """Моб-манекен: на dx правее/левее героя, ноги на его уровне (ищем свободное место рядом)."""
    return add_mob_free(pl.x + dx, pl.y + pl.h - 22 + dy)

def clear_line(x, y, ang, L, step=8.0):
    """Нет ли стен вдоль линии из (x, y) под углом ang длиной L (с шагом step)."""
    for t in range(int(L / step) + 1):
        if core.solid(g.room.g, int((x + math.cos(ang) * t * step) // core.T), int((y + math.sin(ang) * t * step) // core.T)):
            return False
    return True

def open_dir(L=230):
    """Первый из 36 направлений, где из позиции героя на L пикселей нет стен; None если таких нет."""
    for i in range(36):
        ang = i * math.tau / 36
        if clear_line(pl.cx, pl.cy, ang, L):
            return ang
    raise AssertionError("вокруг героя стены — нет открытого направления")

def open_point(base_x, base_y, reach=90, step=40.0):
    """Точка (в воздухе, не в стене) рядом с (base_x, base_y): спираль outward; исключение если всё занято."""
    for r in range(0, int(reach) + 1, max(1, int(step // 2))):
        for i in range(12):
            a = i * math.tau / 12
            x, y = base_x + math.cos(a) * r, base_y + math.sin(a) * r
            if not core.solid(g.room.g, int(x // core.T), int(y // core.T)):
                return x, y
    raise AssertionError("нет открытой точки")

def cast_skill(sid, aim=None):
    pl.skill_index = spells.active_skills(pl).index(sid)
    pl.aim = aim
    pl.mana = 200.0
    pl.skill_cooldowns[sid] = 0.0
    pl.skill_cast = None
    n0 = len(g.projs)
    spells.cast(pl, g.room.mobs, g.projs, g.fx)
    return n0

def step(sec):
    for _ in range(max(1, int(sec / 0.016))):
        g.fx.stop = 0.0   # без стоп-кадра от попаданий (иначе мир замирает и время кастов съезжает)
        g.step(0.016)

def dist_to_pl(q): return math.hypot(q.x - pl.cx, q.y - pl.cy)

import math

# 1) данные: 48 типов снарядов, новые навыки у мага (24 активных)
assert len(core.CFG["projectiles"]) >= 48, len(core.CFG["projectiles"])
act = spells.active_skills(pl)
assert len(act) >= 24, len(act)
print(f"данные: {len(core.CFG['projectiles'])} снарядов, {len(act)} навыков у мага OK")
act = spells.active_skills(pl)
new_sk = ["arcane_boomerang", "arcane_swarm", "black_hole", "arcane_mine", "frost_field",
          "fire_storm", "dagger_rain", "arcane_beam", "orbit_blades", "prism_orb"]
for sid in new_sk:
    assert sid in act, f"{sid} не в активных навыках мага"
    sk = core.CFG["skills"][sid]
    assert sid in core.CFG["skills"] and sk, f"{sid} сломан в skills.json"
    pr = sk.get("projectile")
    assert pr is None or pr in core.CFG["projectiles"], f"{sid}: снаряда {pr} нет"
assert core.CFG["skills"]["black_hole"]["type"] == "projectile", "black_hole не починен"

# 2) бумеранг: летит вперёд, возвращается, задевает моба на пути, умирает у ног хозяина
clear_mobs(); g.projs.clear()
ang = open_dir()
aim = (pl.cx + math.cos(ang) * 300, pl.cy + math.sin(ang) * 300)
m = add_mob(pl.cx + math.cos(ang) * 180 - 9, pl.cy + math.sin(ang) * 180 - 11)
cast_skill("arcane_boomerang", aim)
step(0.08)
q = [b for b in g.projs if b.d.get("_id") == "arcane_boomerang"]
assert len(q) == 1, f"бумеранг не создан: {len(q)}"
d0 = dist_to_pl(q[0])
step(0.42)
d1 = dist_to_pl(q[0])
assert d1 > d0 + 40, f"бумеранг не летит вперёд: {d0:.0f} -> {d1:.0f}"
assert m.hp < m.maxhp, "бумеранг не задел моба на пути"
step(0.3)
assert dist_to_pl(q[0]) < d1 - 10, "бумеранг не вернулся"
step(0.6)
assert not any(b is q[0] for b in g.projs), "бумеранг не исчез у ног хозяина"
print("бумеранг OK")

# 3) рой сфер: самонаводящиеся пули находят моба по прицелу, пробивают его и добираются до второго
clear_mobs(); g.projs.clear()
ang = open_dir(280)
m1 = add_mob_free(pl.cx + math.cos(ang) * 110 - 9, pl.cy + math.sin(ang) * 110 - 11)
m2 = add_mob_free(pl.cx + math.cos(ang) * 240 - 9, pl.cy + math.sin(ang) * 240 - 11)
cast_skill("arcane_swarm", (m1.cx, m1.cy))
step(2.2)
assert m1.hp < m1.maxhp, "рой не задел моба по прицелу"
assert m2.hp < m2.maxhp, "рой не задел второго моба (пробитие + самонаведение)"
print("рой сфер OK")

# 4) чёрная дыра: at_cursor — воронка в точке курсора, стягивает моба
clear_mobs(); g.projs.clear()
hole = (pl.x + 170, pl.cy)
m = place(170 + 120)   # моб в 120px от центра воронки (в радиусе 160)
n0 = cast_skill("black_hole", hole)
q = [b for b in g.projs if b.d.get("_id") == "blackhole_core"]
assert len(q) == 1 and abs(q[0].x - hole[0]) < 30 and abs(q[0].y - hole[1]) < 30, "воронка не в точке курсора"
dd0 = math.hypot(m.cx - q[0].x, m.cy - q[0].y)
step(1.2)
dd1 = math.hypot(m.cx - q[0].x, m.cy - q[0].y)
assert dd1 < dd0 - 30, f"воронка не стянула моба: {dd0:.0f} -> {dd1:.0f}"
assert m.hp < m.maxhp, "воронка не нанесла урон тиками"
print("чёрная дыра OK")

# 5) мина: брошена, легла, взвелась, взрыв при подходе моба (урон по площади + стан)
clear_mobs(); g.projs.clear()
ang = open_dir(260)
cast_skill("arcane_mine", (pl.cx + math.cos(ang) * 150, pl.cy + math.sin(ang) * 150))
step(1.2)
mine = [b for b in g.projs if b.d.get("_id") == "mana_mine"]
assert len(mine) == 1, f"мина не на месте: {len(mine)}"
assert getattr(mine[0], "_mine_arm", False), "мина не взвелась"
m = add_mob_free(mine[0].x + 26, mine[0].y - 22)
step(0.5)
assert not any(b.d.get("_id") == "mana_mine" for b in g.projs), "мина не взорвалась при подходе"
assert m.hp < m.maxhp, "взрыв мины не задел моба"
assert m.stun > 0, "взрыв мины не оглушил моба"
print("мина OK")

# 6) морозное поле: зона в курсоре — мгновенный тик: урон + заморозка
clear_mobs(); g.projs.clear()
m = place(150)
cast_skill("frost_field", (m.cx, m.cy))
step(0.3)
q = [b for b in g.projs if b.d.get("_id") == "frost_zone"]
assert len(q) == 1, "зона не создана в курсоре"
assert m.frozen > 0, "зона не заморозила моба"
assert m.hp < m.maxhp, "зона не нанесла урон"
step(1.2)
assert any(b.d.get("_id") == "frost_zone" for b in g.projs), "зона умерла раньше времени"
print("морозное поле OK")

# 7) огненный шторм: серия разрядов вокруг курсора; манекены покрывают область
clear_mobs(); g.projs.clear(); random.seed(11)
cx, cy = open_point(pl.cx + 170, pl.cy)
ms = [add_mob_free(cx + dx, cy + dy - 11) for dx in (-105, -35, 35, 105) for dy in (0, -44)]
cast_skill("fire_storm", (cx, cy))
step(3.0)
assert sum(m.maxhp - m.hp for m in ms) > 0, "шторм не задел ни одного моба"
assert not any(b.d.get("_id") == "storm_core" for b in g.projs), "шторм не кончился"
print("огненный шторм OK")

# 8) дождь клинков: маркер в курсоре роняет кинжалы сверху (вертикальный ствол свободен); они бьют мобов
clear_mobs(); g.projs.clear(); random.seed(5)
ax = ay = None
for r in range(0, 121, 20):
    for i in range(12):
        a = i * math.tau / 12
        x, y = pl.cx + math.cos(a) * r, pl.cy + math.sin(a) * r
        if clear_line(x, y - 180, math.pi / 2, 200):
            ax, ay = x, y; break
    if ax is not None: break
assert ax is not None, "нет точки с чистым вертикальным стволом для дождя"
ms = [add_mob_free(ax + dx, ay - 11) for dx in (-30, 0, 30)]
cast_skill("dagger_rain", (ax, ay))
peak = 0
for _ in range(int(1.8 / 0.016)):
    g.step(0.016)
    peak = max(peak, sum(1 for b in g.projs if b.d.get("_id") == "shadow_dagger"))
assert peak >= 2, f"дочерние кинжалы не появились: {peak}"
assert sum(m.maxhp - m.hp for m in ms) > 0, "дождь не задел мобов"
print("дождь клинков OK")

# 9) чародейский луч: мгновенный урон всем на линии
clear_mobs(); g.projs.clear()
ang = open_dir(290)
m1 = add_mob_free(pl.cx + math.cos(ang) * 150 - 9, pl.cy + math.sin(ang) * 150 - 11)
m2 = add_mob_free(pl.cx + math.cos(ang) * 260 - 9, pl.cy + math.sin(ang) * 260 - 11)
cast_skill("arcane_beam", (m1.cx, m1.cy))
assert m1.hp < m1.maxhp, "луч не задел ближнего моба"
assert m2.hp < m2.maxhp, "луч не задел дальнего моба (не пронзил линию)"
print("чародейский луч OK")

# 10) вихрь клинков: 4 клинка на орбите радиуса ~48 вокруг героя, режут подойдяшего моба
clear_mobs(); g.projs.clear()
n0 = cast_skill("orbit_blades", (pl.x + 200, pl.cy))
blades = [b for b in g.projs if b.d.get("_id") == "orbit_blade"]
assert len(blades) == 4, f"клинков не 4: {len(blades)}"
step(0.25)
assert all(abs(math.hypot(b.x - pl.cx, b.y - pl.cy) - 48) < 8 for b in blades), "клинки не на орбите"
m = place(46)   # вплотную к орбите
step(1.2)
assert m.hp < m.maxhp, "клинки не задели моба у орбиты"
print("вихрь клинков OK")

# 11) призма: сфера распадается кольцом ровно на 8 осколков
clear_mobs(); g.projs.clear(); random.seed(3)
ang = open_dir(340)
cast_skill("prism_orb", (pl.cx + math.cos(ang) * 260, pl.cy + math.sin(ang) * 260))
peak = 0
for _ in range(int(2.2 / 0.016)):
    g.step(0.016)
    peak = max(peak, sum(1 for b in g.projs if b.d.get("_id") == "prism_shard"))
assert peak == 8, f"осколков призмы: {peak}, ожидалось 8"
assert not any(b.d.get("_id") == "prism_orb" for b in g.projs), "сфера не исчезла"
print("призма OK")

# 12) ghost: зона/бумеранг сквозь стены — пуля в стене не умирает
g.projs.clear()
pr = dict(projectiles.resolve("frost_zone"))
wx = wy = None
for c in range(len(g.room.g[0])):
    for r in range(len(g.room.g)):
        if core.solid(g.room.g, c, r) and core.tile(g.room.g, c, r) != "D":
            wx, wy = c * core.T + core.T / 2, r * core.T + core.T / 2
            break
    if wx is not None: break
assert wx is not None, "нет стены для проверки ghost"
b = projectiles.Proj(wx, wy, 0.0, 0.0, pr, 5, True)
g.projs.append(b)
step(0.2)
assert b in g.projs and not b.dead, "ghost-пуля умерла в стене"
b2 = projectiles.Proj(wx, wy, 0.0, 0.0, dict(projectiles.resolve("frost_zone"), ghost=False), 5, True)
g.projs.append(b2)
step(0.05)
assert b2.dead, "обычная пуля не умирает в стене"
g.projs.clear()
print("ghost OK")

# 13) полный кадр: планшет с новым навыком (arcane_beam) — отрисовка не падает
pl.skill_index = spells.active_skills(pl).index("arcane_beam")
spell_tablet._set_open(g, True); spell_tablet.S["t0"] = 0; spell_tablet._slide()
g.draw()
print("полный кадр с планшетом OK")

print("SMOKE новых паттернов: ALL OK")
