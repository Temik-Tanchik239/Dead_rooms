# -*- coding: utf-8 -*-
"""Смоук: интеграция чекпоинтов в main.step (одиночка) — смерть через step возрождает
у кристалла, штраф-заморозка: герой неподвижен, ввод/действия отключены, физика живёт."""
import os, sys, io
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import pygame as pg
import main, core, checkpoint

g = main.Game(); s = g
s.new_game()
s.menu_mode = None   # как «Продолжить» в меню: иначе step стоит на паузе (sim=0) и физика не тикает
rid = s.room.id
md = core.CFG["map_defs"][rid]
rows = [list(row) for row in md["rows"]]
# «O» — на клетку с твёрдым полом под ней (иначе кристалл висит над пустотой и герой падает)
spot = None
for rr in range(len(rows) - 1):
    for cc in range(len(rows[rr])):
        if rows[rr][cc] in ". " and rr + 1 < len(rows) and rows[rr + 1][cc] in "#D":
            spot = (rr, cc); break
    if spot: break
assert spot, "нет подходящей клетки"
rr, cc = spot
rows[rr][cc] = "O"
md["rows"] = ["".join(r) for r in rows]
s.camp.maps.pop(rid, None)
s.room = s.camp.get(rid)
cp = s.room.checkpoints[0]

# активация: герой в клетке кристалла
s.pl.x = cp["x"] - s.pl.w / 2; s.pl.y = cp["ground"] - s.pl.h
checkpoint.update(s, 0.016)
assert s.pl.cp == (rid, int(cp["x"]), int(cp["ground"])), s.pl.cp
print("activate OK")

# смерть через step: игра НЕ кончается — авто-возрождение у кристалла с заморозкой
s.pl.hp = 0
s.step(0.016)
assert s.pl.hp > 0, "step не возродил героя"
assert s.pl.frozen > 0 and s.pl.frozen <= 10.0, f"frozen: {s.pl.frozen}"
assert abs(s.pl.x + s.pl.w / 2 - cp["x"]) < 40, f"не у кристалла: x={s.pl.x:.0f}"
print(f"death->respawn OK: hp={s.pl.hp}, frozen={s.pl.frozen:.1f}")

# штраф: неподвижность — обновляем step, герой не уходит с места и не целится
x0, y0 = s.pl.x, s.pl.y
for _ in range(10):
    s.step(0.016)
assert s.pl.aim is None, "aim должен быть None в кристалле"
assert abs(s.pl.x - x0) < 1 and abs(s.pl.y - y0) < 2, f"герой двигался в кристалле: dx={s.pl.x-x0:.1f} dy={s.pl.y-y0:.1f}"
assert s.pl.atk is None, "замороженный атакует"
print("frozen: стоит неподвижно OK")

# действия заблокированы
s.act("skill"); s.act("a1"); s.act("jump")
assert s.pl.atk is None and not s.pl.skill_cast, "act() пробился сквозь кристалл"
print("act blocked OK")

# физика живёт: герой стоит на земле, заморозка тает по step
assert s.pl.ground, "герой не упал на землю (физика умерла?)"
t0 = s.pl.frozen
s.step(0.25)
assert s.pl.frozen < t0, "заморозка не тает"
print(f"physics/melt OK: frozen {t0:.1f} -> {s.pl.frozen:.1f}")

# отрисовка кадра целиком (кристаллы комнаты + кристалл героя)
s.draw()
print("draw OK")
print("STEP_SMOKE_OK")
