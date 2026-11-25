# -*- coding: utf-8 -*-
"""Смоук: чекпоинты в одиночной игре (активация, лечение, автосейв, смерть->возрождение, кристалл)."""
import os, sys, io
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import pygame as pg
import main, core, checkpoint, save_io

g = main.Game(); s = g
s.new_game()
rid = s.room.id
# подложить символ O в данные карты (в память): строку 2, клетку в центре
md = core.CFG["map_defs"][rid]
rows = [list(row) for row in md["rows"]]
rows[2][5] = "O"
md["rows"] = ["".join(r) for r in rows]
s.camp.maps.pop(rid, None)  # сбросить кэш комнаты, чтобы Room пересобрался с чекпоинтом
s.room = s.camp.get(rid)
cps = s.room.checkpoints
assert cps, "collect не нашёл чекпоинт"
cp = cps[0]
print("collect OK:", cp["x"], cp["ground"])

# активация: поставить героя в клетку кристалла
s.pl.x = cp["x"] - s.pl.w / 2; s.pl.y = cp["ground"] - s.pl.h
s.pl.hp = s.pl.maxhp * 0.3; s.pl.mana = 5
checkpoint.update(s, 0.016)
assert s.pl.hp == s.pl.maxhp and s.pl.mana == s.pl.maxmana, "лечение не сработало"
assert s.pl.cp == (rid, int(cp["x"]), int(cp["ground"])), f"cp не запомнился: {s.pl.cp}"
assert os.path.exists("saves/autosave.json"), "autosave не создан"
print("activate OK: hp/mana/cp/autosave")

# смерть: hp -> 0, step должен телепортировать и заморозить (после интеграции main.py: step сам зовёт respawn)
s.pl.hp = 0
checkpoint.respawn(s)   # прямой вызов (main.step добавит вызов при интеграции)
assert s.pl.hp > 0, "respawn не восстановил hp"
assert s.pl.frozen > 0 and s.pl.frozen <= 10.0, f"frozen не установлен: {s.pl.frozen}"
assert abs(s.pl.x + s.pl.w / 2 - cp["x"]) < 40, "не вернулся к кристаллу"
print(f"respawn OK: hp={s.pl.hp}, frozen={s.pl.frozen:.1f}, x={s.pl.x:.0f}")

# неуязвимость в кристалле
inv_before = s.pl.inv
s.pl.hit(999, s.pl.cx, s.fx)
assert s.pl.hp > 0, "кристалл не защищает"
print("invulnerable OK")

# заморозка тает
t0 = s.pl.frozen
for _ in range(101): checkpoint.tick(s.pl, 0.1)   # 10.1 с — кристалл растаял
assert s.pl.frozen == 0, "tick не растопил кристалл"
assert s.pl.inv >= 0, "inv сломался"
# в игре inv тает в pl.update: после разморозки уязвимость вернётся (inv не удерживается tick выше frozen)
print("tick OK")

# отрисовка
checkpoint.draw_room(s.view, s.room, pg.time.get_ticks(), s.pl)
checkpoint.draw_crystal(s.view, s.pl, pg.time.get_ticks())
print("draw OK")

# сейв/загрузка с cp
meta = save_io.save(s)
doc = save_io._read(meta["id"])
cid = s.pl.char_id
assert doc["heroes"][cid]["cp"] == [rid, int(cp["x"]), int(cp["ground"])], doc["heroes"][cid].get("cp")
save_io.restore(s, meta["id"])
assert s.pl.cp == (rid, int(cp["x"]), int(cp["ground"])), "cp не восстановился из сейва"
print("save/restore cp OK")

# очистка
for f in os.listdir("saves"): os.remove(os.path.join("saves", f))
print("CP_SMOKE_OK")
