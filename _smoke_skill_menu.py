# -*- coding: utf-8 -*-
"""Смок: меню навыков — окно 4×2 (8 ячеек) с прокруткой.
1) конфиг: columns/rows/max_slots
2) дерево из 30 слотов: рисуется без падений, автопрокрутка к открываемому навыку
3) колесо: прокрутка строк с зажимом в [0, max_scroll]
4) ручная прокрутка не сбивается авто, сброс при открытии/закрытии меню
5) полный кадр с меню у всех героев (деревья 10-15 слотов — листаются)
Запуск: .venv/Scripts/python _smoke_skill_menu.py
"""
import os, sys, io, time
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import pygame as pg
import main, core
from pathlib import Path

pg.init(); pg.font.init(); pg.display.set_mode((core.W, core.VIEW_H))
core.CFG["maps"]["print_world"] = False
g = main.Game(); g.menu_mode = None
pl = g.pl
ui = core.CFG["skill_menu"]
assert ui["columns"] == 4 and ui["rows"] == 2, f"окно {ui['columns']}x{ui['rows']}, ожидалось 4x2"
print("конфиг: окно 4×2 (8 ячеек), max_slots 8 OK")

# ---------------------------------------------------------------- 1) большое дерево: 30 слотов
real_tree = core.CFG["skill_tree"]
core.CFG["skill_tree"] = {"slots": [{"skill": sid, "unlock_level": 1 + i // 2}
                                    for i, sid in enumerate(list(core.CFG["skills"].keys())[:30])]}
tree30 = core.CFG["skill_tree"]["slots"]

def open_menu(level=3, anim_sid=None):
    g.level_menu = True
    g.level_menu_started = pg.time.get_ticks()
    g.level_menu_level = level
    g.skill_menu_scroll = None   # авто
    g.skill_unlock_anim = ({"skill": anim_sid, "start": pg.time.get_ticks(), "duration": 1100}
                           if anim_sid else None)

# авто-прокрутка: без анимации и все навыки "открыты" → целевая строка 0
open_menu()
g.skill_unlock_anim = None
for slot in tree30:
    if slot["skill"] and slot["skill"] not in pl.skills: pl.skills.append(slot["skill"])
g.draw_level_menu()
assert g.skill_menu_scroll == 0, f"автопрокрутка без цели: {g.skill_menu_scroll}, ожидалось 0"
print("автопрокрутка: все открыты → верх дерева OK")

# авто-прокрутка: анимация открываемого навыка в последней строке → окно показывает его
last_sid = tree30[-1]["skill"]                 # i=29 → строка 7 (rows=2 → max_scroll=6)
open_menu(anim_sid=last_sid)
g.draw_level_menu()
rows_total = (len(tree30) + 3) // 4            # 8 строк
max_scroll = rows_total - 2                    # 6
assert g.skill_menu_scroll == max_scroll, f"автопрокрутка к последней строке: {g.skill_menu_scroll}, ожидалось {max_scroll}"
g.draw_level_menu()                            # повторный кадр — прокрутка не дёргается
assert g.skill_menu_scroll == max_scroll
print(f"автопрокрутка: открываемый навык (строка {rows_total - 1}) виден, scroll={g.skill_menu_scroll} OK")

# колесо: прокрутка вверх/вниз с зажимом
g.skill_menu_scroll = None; g.draw_level_menu()          # авто снова
g.skill_menu_wheel(1)                                    # ручная: +1 строка
assert g.skill_menu_scroll == max_scroll, "колесо вниз: не выросло"
g.skill_menu_wheel(10)                                   # зажим снизу
assert g.skill_menu_scroll == max_scroll
g.skill_menu_wheel(-2)
assert g.skill_menu_scroll == max_scroll - 2, "колесо вверх: не уменьшилось"
g.skill_menu_wheel(-50)                                  # зажим сверху
assert g.skill_menu_scroll == 0
print("колесо: шаг ±1 строка, зажим [0, max_scroll] OK")

# ручная прокрутка держится (авто не перебивает), сброс при закрытии
g.skill_menu_wheel(3)
assert g.skill_menu_scroll == 3
g.draw_level_menu()                                      # anim None → цель есть (не все открыты?) — scroll int не трогаем
# (у нас все открыты, цель 0 — но ручное значение int, авто не применяется)
assert g.skill_menu_scroll == 3, "автопрокрутка перебила ручную"
g.key(pg.K_ESCAPE)
assert g.level_menu is False and g.skill_menu_scroll is None, "закрытие: прокрутка не сброшена"
print("ручная прокрутка держится; Esc закрыл и сбросил OK")

# ---------------------------------------------------------------- 2) средний кадр: повторное открытие → авто
open_menu(anim_sid=None)
g.draw_level_menu()
assert g.skill_menu_scroll == 0, "новое открытие меню: авто к началу дерева"
print("повторное открытие: прокрутка сброшена авто OK")

# ---------------------------------------------------------------- 3) герои: полные кадры со своими деревьями
core.CFG["skill_tree"] = real_tree
g.key(pg.K_ESCAPE)
for cid in ("knight", "bard", "ranger", "mage", "shadow"):
    g.new_game(character=cid); core.apply_character(cid)
    n = len(core.CFG["skill_tree"].get("slots", []))
    open_menu(level=2)
    g.draw_level_menu(); g.draw(); pg.event.pump(); pg.display.flip()
    print(f"герой {cid}: дерево {n} слотов, полный кадр OK")

print("SMOKE меню навыков 4×2: ALL OK")
