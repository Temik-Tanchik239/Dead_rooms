# -*- coding: utf-8 -*-
"""Смоук планшета заклинаний мага (spell_tablet.py) и силы каста (spells.POWER):
5 ячеек на дорожке, колесо мыши листает, ползунки силы масштабируют урон/ману/кулдаун/время каста,
кнопка прячет планшет и кнопка возвращает, сейв/восстановление силы, сетевое действие skpow,
полный кадр с планшетом. Не-маги (рыцарь) силу каста не имеют — планшет у них не включается."""
import os, sys, io
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import pygame as pg
import main, core, spells, spell_tablet, hud, save_io

pg.init(); pg.font.init(); pg.display.set_mode((core.W, core.VIEW_H))

# 1) флаг cast_power только у мага
g = main.Game(); g.new_game(character="mage"); g.menu_mode = None
pl = g.pl
core.apply_character("mage")
assert spells.has_cast_power("mage"), "у мага нет cast_power"
assert not spells.has_cast_power("knight"), "у рыцаря не должно быть cast_power"
assert not spells.has_cast_power("ranger"), "у инженера не должно быть cast_power"
assert spell_tablet.enabled(), "планшет не включён у мага"
assert pl.cast_power == {}, pl.cast_power
print("cast_power flag OK")

# 2) сила каста: масштабы урона, маны, кулдауна и времени каста
core.apply_character("mage"); pl = g.pl
sid = "fireball"
a = core.CFG["skills"][sid]; base_dmg, base_mana, base_cd = float(a["damage"]), float(a["mana_cost"]), float(a["cooldown"])
assert spells.cast_power(pl, sid) == 0.0
spells.set_cast_power(pl, sid, 0.5)
assert spells.cast_power(pl, sid) == 0.5
assert abs(spells.power_scale(0.5, "damage") - 1.5) < 1e-9
assert abs(spells.power_scale(0.5, "mana") - 1.75) < 1e-9
spells.set_cast_power(pl, sid, 2.0)   # зажим в 0..1
assert spells.cast_power(pl, sid) == 1.0
assert spells.power_skill(pl, sid)["damage"] == base_dmg * 2.0
assert core.CFG["skills"][sid]["damage"] == base_dmg   # общие данные не меняются
# рыцарь: сила всегда 0 (у героя-рыцаря планшет не включён)
g.new_game(character="knight"); g.menu_mode = None
assert not spells.has_cast_power(g.pl.char_id)
spells.set_cast_power(g.pl, sid, 0.8)
assert spells.cast_power(g.pl, sid) == 0.0
g.new_game(character="mage"); pl = g.pl; g.menu_mode = None
print("power scale OK")

# 3) каст с силой: больше урона и цена, больше кулдаун и время каста
core.apply_character("mage"); pl = g.pl
act = spells.active_skills(pl)
pl.skill_index = act.index("fireball")   # выбираем заклинание явно
pl.mana = 160.0
spells.set_cast_power(pl, "fireball", 0.0)
spells.cast(pl, g.room.mobs, g.projs, g.fx)
cd0, sc0 = pl.skill_cooldowns["fireball"], pl.skill_cast
pl.mana = 160.0
spells.set_cast_power(pl, "fireball", 1.0)
pl.skill_cooldowns["fireball"] = 0.0
pl.skill_cast = None
spells.cast(pl, g.room.mobs, g.projs, g.fx)
cd1, sc1 = pl.skill_cooldowns["fireball"], pl.skill_cast
assert abs(cd1 - cd0 * 2.0) < 1e-6, (cd0, cd1)
assert abs(sc1[2] - sc0[2] * 2.0) < 1e-6, (sc0, sc1)
assert sc1[2] > sc0[2]
# авто-каст по ready(): не хватает маны при большой силе
pl.mana = 3.0; pl.skill_cooldowns["fireball"] = 0.0
spells.set_cast_power(pl, "fireball", 1.0)
assert not spells.ready(pl), "ready() должен требовать усиленную цену маны"
spells.set_cast_power(pl, "fireball", 0.0)
pl.mana = 160.0
assert spells.ready(pl)
pl.skill_cooldowns["fireball"] = 0.0; pl.mana = 160.0
print("cast with power OK")

# 3б) ЛКМ у мага больше не кастует: заклинание применяет только клавиша навыка (Q)
core.apply_character("mage"); g.new_game(character="mage"); g.menu_mode = None
pl = g.pl
pl.mana = 160.0
n0 = len(g.projs)
pl.press("a1")   # ЛКМ
pl.buf["a1"] = 1.0
g.step(1/60); g.step(1/60)
assert len(g.projs) == n0, (n0, len(g.projs))   # снаряда нет
assert pl.mana >= 160.0, pl.mana   # мана не потрачена (регенерация только добавляет)
pl.buf["a1"] = 0.0
print("LMB not casting OK")

# 4) поток с силой: мана/сек дорожает (fire_stream)
core.apply_character("mage"); pl = g.pl
pl.skill_index = spells.active_skills(pl).index("fire_stream")
spells.set_cast_power(pl, "fire_stream", 1.0)
hsp = spells.hold_start(pl, "fire_stream", core.CFG["skills"]["fire_stream"], g.room.mobs, g.projs, g.fx)
base_cost = float(core.CFG["skills"]["fire_stream"]["mana_cost"]) * 2.5
assert pl.hold and pl.hold.get("sid") == "fire_stream"
pl.skill_held = True   # клавишу «держат», иначе поток сразу прервётся (release)
mana_a = pl.mana
spells.hold_update(pl, 0.1, g.room.mobs, g.projs, g.fx)
spent = (mana_a - pl.mana)
assert spent > base_cost * 0.1 * 0.9, (spent, base_cost)   # минимум 10% запаса по усиленной цене
spells.hold_stop(pl, None, "swap")
spells.set_cast_power(pl, "fire_stream", 0.0)
print("hold with power OK")

# 5) дорожка из пяти ячеек, окно и интерполяция
core.apply_character("mage"); pl = g.pl
act = spells.active_skills(pl)
assert len(act) >= 5, len(act)
cells, bars, cys, sizes = spell_tablet._geom(spell_tablet.rect())
assert len(cells) == 5 and len(bars) == 5
assert cells[2].w > cells[1].w > cells[0].w, [c.w for c in cells]   # текущий крупнее соседей
assert cys[0] < cys[1] < cys[2] < cys[3] < cys[4]
assert spell_tablet._window(5) == (-2, 2) and spell_tablet._window(3) == (-1, 1) and spell_tablet._window(2) == (-1, 1) and spell_tablet._window(1) == (0, 0)
assert abs(spell_tablet._track([0, 1, 2, 3, 4], 0) - 2) < 1e-9
assert abs(spell_tablet._track([0, 1, 2, 3, 4], 1.5) - 3.5) < 1e-9
print("tablet track OK")

# 6) колесо мыши листает заклинания; клик по планшету — не каст
r = spell_tablet.rect()
spell_tablet._set_open(g, True); spell_tablet.S["t0"] = 0; spell_tablet._slide()   # состояние могло сохраниться закрытым в settings.json
spell_tablet.draw(g.scr, pl, g.small)
assert spell_tablet.HITS.get("body") and spell_tablet.HITS.get("bars"), spell_tablet.HITS.keys()
assert set(spell_tablet.HITS["bars"].keys()) == {act[pl.skill_index % len(act)]}, spell_tablet.HITS["bars"].keys()   # ползунок только у текущего
pg.mouse.set_pos(cells[0].center)   # над верхней ячейкой (не над ползунком) — колесо листает
g.skill_index = pl.skill_index = 0
k0 = pl.skill_index
spell_tablet.event(g, pg.event.Event(pg.MOUSEWHEEL, y=1, x=0))   # колесо вверх — prev
assert pl.skill_index == (k0 - 1) % len(act), (pl.skill_index, k0)
spell_tablet.draw(g.scr, pl, g.small)
sid_cur = act[pl.skill_index % len(act)]
bar = spell_tablet.HITS["bars"][sid_cur]
pw0 = spells.cast_power(pl, sid_cur)
pg.mouse.set_pos(bar.center)   # колесо над ползунком — сила
spell_tablet.event(g, pg.event.Event(pg.MOUSEWHEEL, y=1, x=0))
assert spells.cast_power(pl, sid_cur) == min(1.0, pw0 + 0.1)
pg.mouse.set_pos(bar.left + int(bar.w * 0.7), bar.centery)
spell_tablet.event(g, pg.event.Event(pg.MOUSEBUTTONDOWN, button=1, pos=(bar.left + int(bar.w * 0.7), bar.centery)))
spell_tablet.event(g, pg.event.Event(pg.MOUSEMOTION, buttons=(1, 0, 0), pos=(bar.left, bar.centery), rel=(1, 0)))
spell_tablet.event(g, pg.event.Event(pg.MOUSEBUTTONUP, button=1, pos=(bar.left, bar.centery)))
assert abs(spells.cast_power(pl, sid_cur) - 0.0) < 1e-6, spells.cast_power(pl, sid_cur)
# клик по телу планшета съедается (не кастует), вне планшета — нет
pg.mouse.set_pos(r.centerx, r.centery)
assert spell_tablet.event(g, pg.event.Event(pg.MOUSEBUTTONDOWN, button=1, pos=(r.centerx, r.centery)))
assert not spell_tablet.event(g, pg.event.Event(pg.MOUSEBUTTONDOWN, button=1, pos=(core.W - 50, 50)))
# клик по телу не должен уйти в атаку: run() ветка elif — проверяем, что рисование заполняет HITS
spell_tablet.draw(g.scr, pl, g.small)
assert spell_tablet.HITS["body"].collidepoint((r.centerx, r.centery))
print("tablet mouse OK")

# 7) кнопка «спрятать» и кнопка «показать»
spell_tablet.draw(g.scr, pl, g.small)
hb = spell_tablet.HITS["hide"]
assert spell_tablet.event(g, pg.event.Event(pg.MOUSEBUTTONDOWN, button=1, pos=hb.center)), "кнопка спрятать не сработала"
assert not spell_tablet.S["open"]
spell_tablet._slide()   # мгновенно доезжаем до 1 (заглушка без времени)
spell_tablet.S["t0"] = pg.time.get_ticks() - 1000; spell_tablet._slide()
spell_tablet.draw(g.scr, pl, g.small)
tb = spell_tablet.HITS.get("tab")
assert tb is not None, "свёрнутая кнопка не появилась"
assert not spell_tablet.HITS.get("body") or not spell_tablet.HITS["body"].collidepoint(tb.center)
assert spell_tablet.event(g, pg.event.Event(pg.MOUSEBUTTONDOWN, button=1, pos=tb.center)), "кнопка показать не сработала"
spell_tablet.S["t0"] = pg.time.get_ticks() - 1000; spell_tablet._slide()
assert spell_tablet.S["open"] and spell_tablet.S["b"] == 0.0
spell_tablet._set_open(g, True)
assert core.SETTINGS.get("tablet_open") is True
print("tablet hide/show OK")

# 8) планшет только у мага: у рыцаря event всегда False; у инженера ЛКМ-каст остался
g.new_game(character="knight"); g.menu_mode = None
assert not spell_tablet.enabled()
assert not spell_tablet.event(g, pg.event.Event(pg.MOUSEWHEEL, y=1, x=0))
assert not spells.has_cast_power("engineer")   # инженер — заклинатель без планшета: ЛКМ по-прежнему кастует
print("not for knight OK")

# 9) сетевое действие skpow и сейв силы
core.apply_character("mage"); g.new_game(character="mage"); g.menu_mode = None
pl = g.pl
assert hasattr(g, "apply_action") and hasattr(g, "valid_action")
g.apply_action(pl, "skpow:fireball:0.4")
assert abs(spells.cast_power(pl, "fireball") - 0.4) < 1e-9
g.apply_action(pl, "skpow:fireball:bad")   # мусор не роняет
assert abs(spells.cast_power(pl, "fireball") - 0.4) < 1e-9
assert g.valid_action("skpow:fireball:0.4") and not g.valid_action("skpow:" + "x" * 60 + ":1")
snap = save_io.snapshot_player(pl)
assert snap["cast_power"] == {"fireball": 0.4}, snap.get("cast_power")
pl.cast_power = {}
save_io.restore_player(pl, snap)
assert abs(spells.cast_power(pl, "fireball") - 0.4) < 1e-9
print("net+save power OK")

# 10) полный кадр: draw() с планшетом у мага и у инженера (книга)
core.apply_character("mage"); g.new_game(character="mage"); g.menu_mode = None
g.draw()
core.apply_character("ranger"); g.new_game(character="ranger"); g.menu_mode = None
g.draw()
hud.book_draw(g.scr, g.pl, g.small)   # книга инженера жива
core.apply_character("mage")
print("full frame OK")

print("SMOKE spell_tablet: ALL OK")
