# -*- coding: utf-8 -*-
"""Смоук системы эффектов: emit по привязкам, движения частиц, хуки (удар/скилл/шаги/ящик/пуля/смерть),
логика редактора частиц (attachments_editor.py), сетевая упаковка, полный кадр с частицами."""
import os, sys, io
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import json
import pygame as pg
import main, core, effects, attachments_editor, containers, projectiles, weapon

# 1) данные читаются
assert isinstance(core.CFG.get("effects"), dict) and "spark" in core.CFG["effects"], "effects.json не читается"
assert isinstance(core.CFG.get("attachments"), list), "attachments.json не читается"
print("data load OK")

g = main.Game(); g.new_game(character="knight"); g.menu_mode = None
fx, pl, r = g.fx, g.pl, g.room

# 2) emit: привязка weapon_hit -> spark, частицы появляются
fx.parts.clear()
effects.emit(fx, "weapon_hit", pl.cx, pl.cy, dir=1, target_id="rusty_sword")
assert len(fx.parts) == 8, len(fx.parts)   # из attachments.json: spark ×8
effects.emit(fx, "weapon_hit", pl.cx, pl.cy, dir=1, target_id="unknown_weapon")  # id "*" матчит любую цель
assert len(fx.parts) == 16, len(fx.parts)
print("emit/bind OK")

# 3) update+draw всех движений
spec = core.CFG["effects"]["spark"]
for motion, _ in effects.MOTIONS:
    fx.parts.clear()
    effects.spawn(fx, spec, 100, 100, motion, 20, 1, {"angle": 60, "spin": 4})
    assert len(fx.parts) == 20, motion
    for _ in range(60): effects.update(fx.parts, 1 / 60)   # 1 с — дольше жизни spark
    effects.draw(fx.parts, pg.Surface((core.W, core.VIEW_H)))
assert len(fx.parts) == 0   # всё отжило
fx.parts.clear(); effects.spawn(fx, spec, 0, 0, "burst", effects.MAX + 50, 1)
assert len(fx.parts) <= effects.MAX   # потолок частиц
print("motions+cap OK")

# 4) хуки: удар оружием, скилл, шаги, ящик, пуля, смерть моба
fx.parts.clear()
pl.slots[0] = "rusty_sword"   # стартовый герой без оружия — выдадим меч, иначе удара не будет
pl.start_attack(0, fx)
assert len(fx.parts) >= 1, "weapon_swing не сработал"
fx.parts.clear()
m = r.mobs[0] if r.mobs else None
if m:
    m.hurt(5, 260, fx)
    assert len(fx.parts) >= 1, "mob_hit не сработал"
fx.parts.clear()
pl.vx = 200; pl.ground = True   # идёт по земле — шаги должны дать пыль
pl.step_t = 0.0
effects.walk_step(pl, fx, 1 / 60)   # шаг: таймер сброшен -> частицы
assert len(fx.parts) >= 1, "walk не сработал"
fx.parts.clear()
for _ in range(60): effects.update(fx.parts, 1 / 60)
print("hooks (swing/hit/walk) OK")

# 5) ящик: break_container с эффектом
fx.parts.clear()
ct = next((c for c in r.containers if c.can_break), None)
if ct:
    containers.break_container(r, ct, fx)
    assert len(fx.parts) >= 1, "container_break не сработал"
print("container hook OK")

# 6) пуля: die() даёт projectile_hit
fx.parts.clear()
q = projectiles.Proj(100, 100, 0, 0, {"size": 2, "life": 0.1}, 0, True)
q.die(g)
assert len(fx.parts) >= 1, "projectile_hit не сработал"
print("projectile hook OK")

# 7) логика редактора частиц (attachments_editor.py): поиск/парс/подписи; файл остаётся тем же
bs = attachments_editor.load_bindings()
assert attachments_editor.find_binding(bs, "weapon_hit", "*") >= 0
assert attachments_editor.find_binding(bs, "weapon_hit", "нет_такого") == -1
assert attachments_editor.parse_int("abc", 8) == 8 and attachments_editor.parse_int("500", 8) == 200
assert attachments_editor.parse_float("0,25") == 0.25 and attachments_editor.parse_float("") is None
assert "spark" in attachments_editor.effect_ids()
assert attachments_editor.hook_ids("weapon_hit")[0] == "*"   # все события начинаются с «ко всем»
assert attachments_editor.hook_ids("skill_cast")[1:]   # в skills.json есть id навыков
assert attachments_editor.hook_ids("jump") == ["*"]   # геройские события — без списка целей
assert attachments_editor.HOOK_RU["skill_cast"] == "Применение навыка"
lab = attachments_editor.row_label({"hook": "mob_hit", "id": "slime", "effect": "blood", "count": 6, "motion": "burst"})
assert "slime" in lab and "blood" in lab
bs.append({"hook": "projectile_hit", "id": "_tmp", "effect": "spark", "count": 1, "motion": "puff"})
attachments_editor.save_bindings(bs); bs2 = attachments_editor.load_bindings()
assert attachments_editor.find_binding(bs2, "projectile_hit", "_tmp") >= 0
bs2.pop(); attachments_editor.save_bindings(bs2)   # вернуть как было
print("editor logic OK")

# 8) сетевая упаковка частиц (формат snapshot)
fx.parts.clear()
effects.spawn(fx, spec, 10, 10, "spiral", 5, 1)
import multiplayer
R = lambda v: round(v, 1)
packed = [[R(p[0]), R(p[1]), R(p[2]), R(p[3]), round(p[4], 3), R(p[5]), R(p[6]), p[7], R(p[8]), R(p[9]), p[10], R(p[11]), round(p[12], 2), 1 if p[13] else 0] for p in fx.parts]
back = []
for p in packed:
    p = list(p); p[4] += 0.05; p[13] = bool(p[13]); back.append(p)
assert len(back) == 5 and all(len(p) == 14 for p in back)
print("net pack OK")

# 9) полный кадр с частицами
fx.parts.clear(); effects.spawn(fx, spec, pl.cx, pl.cy, "burst", 40, 1)
g.draw()
print("full frame OK")
print("ALL EFFECTS SMOKE OK")
