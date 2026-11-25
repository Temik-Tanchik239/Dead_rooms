# -*- coding: utf-8 -*-
"""Смоук: два режима меча рыцаря — переключение B (меч <-> ружьё), дробь, запрет щита, красный фильтр."""
import os, sys, io
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import pygame as pg
import main, core, weapon, hud, filters

g = main.Game(); s = g
s.new_game(character="knight")
s.menu_mode = None
assert s.pl.char_id == "knight", s.pl.char_id

# старт: в руках рыцаря обычный меч, режимов нет
assert s.pl.slots[0] == "rusty_sword", s.pl.slots
assert not weapon.gun_mode(s.pl), "руежьё не должно быть включено изначально"

# переключение: apply_action (как по клавише B) -> ружьё
g.apply_action(s.pl, "weapon_mode")
assert s.pl.slots[0] == "rusty_sword_gun", s.pl.slots
assert s.pl.last_weapon == "rusty_sword_gun", s.pl.last_weapon
assert weapon.gun_mode(s.pl), "оружие в руках должно быть в ружейном режиме"
print("toggle to gun OK")

# в ружейном режиме щит нельзя: активный щит гаснет, попытка каста блокируется с сообщением
s.pl.shield_time = 4.0; s.pl.shield_hp = 90.0
s.pl.skill_index = 0   # «Щит» — первый активный навык рыцаря
s.pl.toggle_weapon_mode()          # назад к мечу
assert s.pl.slots[0] == "rusty_sword"
g.apply_action(s.pl, "weapon_mode")  # снова ружьё — активный щит должен сложиться
assert s.pl.shield_time == 0.0 and s.pl.shield_hp == 0.0, (s.pl.shield_time, s.pl.shield_hp)
n0 = len(g.fx.items)
s.pl.use_skill(s.room.mobs, s.projs, g.fx)
assert not s.pl.shield_time, "щит нельзя ставить в режиме ружья"
assert any(it[0] == "t" for it in g.fx.items[n0:]), "должно появиться сообщение о запрете щита"
print("shield blocked in gun mode OK")

# со мечом щит ставится как раньше
s.pl.toggle_weapon_mode()
assert s.pl.slots[0] == "rusty_sword"
s.pl.use_skill(s.room.mobs, s.projs, g.fx)
assert s.pl.shield_time > 0, "со мечом щит должен работать"
print("shield works with sword OK")

# выстрел дробью: 6 дробин веером
s.pl.toggle_weapon_mode()
assert s.pl.slots[0] == "rusty_sword_gun"
st = core.CFG["weapons"]["rusty_sword_gun"]["combo"][0]
pr = st["projectile"]
assert pr["type"] == "pellet" and pr["count"] == 6 and pr["spread"] > 0, pr
n0 = len(s.projs)
s.pl.fire(s.projs, st)
assert len(s.projs) - n0 == 6, len(s.projs) - n0
print("pellet volley OK:", len(s.projs) - n0, "дробин")

# выстрел проходит через атаку целиком (windup -> fire); дробь живёт 0.5 с — ловим пик
s.projs.clear()
s.pl.start_attack(0, g.fx)
assert s.pl.state == "attack" and s.pl.atk["w"] == "rusty_sword_gun"
peak = 0
for _ in range(60):
    s.pl.update(0.016, pg.key.get_pressed(), s.room.g, s.room.mobs, s.projs, g.fx)
    peak = max(peak, sum(1 for p in s.projs if p.d.get("_id") == "pellet"))
assert peak == 6, peak
print("full attack shot OK: пик", peak)

# фильтр рисуется: свои кадры из assets/filters/gun/ (фолбэк не нужен)
scr = pg.Surface((core.W, core.VIEW_H))
weapon.draw_gun_filter(scr)   # должно пройти через кадры из assets, не упасть
spec = filters._find(["filters/gun"])
assert spec and spec["frames"], "кадры фильтра не найдены"
weapon._gun_procedural(scr, 0.5, 1.0)   # процедурная анимация-фолбэк тоже живая
assert weapon._GUN_IMG is not None
weapon._GUN_IMG = None
print("red filter OK")

# ружьё не выпадает из случайного лута
core.CFG["character"] = {"allowed_weapons": None}
from maps import random_weapon
pool = [w for w in core.CFG["weapons"] if (not core.CFG["character"]["allowed_weapons"] or w in core.CFG["character"]["allowed_weapons"]) and core.CFG["weapons"][w].get("loot", True)]
assert "rusty_sword_gun" not in pool
wids = {random_weapon() for _ in range(200)}
assert "rusty_sword_gun" not in wids, wids
print("no gun in random loot OK")

# иконки/HUD не падают (в т.ч. слот щита с красной меткой в ружейном режиме)
font = pg.font.SysFont("arial,dejavusans,freesans", 14)
hud.draw(scr, s.pl, font)
print("hud draw OK")
print("ALL SMOKE OK")
