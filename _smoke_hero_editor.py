# -*- coding: utf-8 -*-
"""Смок: вкладка «Герои» (hero_editor.py) — без ручной правки JSON.
1) построение: герои из characters.json, дерево/базовые навыки текущего героя
2) перестановка слотов ↑/↓, добавление/удаление, форма слота
3) меню навыков: правка → dirty, предпросмотр рисуется, revert
4) сохранение: формат файлов (сравнение с исходным текстом), откат
Запуск: .venv/Scripts/python _smoke_hero_editor.py
"""
import os, sys, io, json
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import tkinter as tk
import tkinter.ttk as ttk
import hero_editor

# не сохранять реальные файлы: читаем, сравниваем, возвращаем как было
CHARS_PATH = Path("data/characters.json"); MENU_PATH = Path("assets/skill_menu.json")
chars_before = CHARS_PATH.read_text(encoding="utf-8"); menu_before = MENU_PATH.read_text(encoding="utf-8")

root = tk.Tk(); root.withdraw()
frame = ttk.Frame(root); frame.pack()
g = hero_editor.HeroTab(frame)
try:
    # ---------------------------------------------------------------- 1) построение
    assert len(g.order) == 5, g.order
    assert g.cur == g.order[0], g.cur
    assert g.tree_lb.size() == len(g.hero.get("skill_tree", [])), "дерево не в списке"
    assert g.bs_lb.size() == len(g.hero.get("base_skills", [])), "базовые не в списке"
    print(f"построение: {len(g.order)} героев, дерево {g.tree_lb.size()} слотов, база {g.bs_lb.size()} OK")

    # ---------------------------------------------------------------- 2) переключение героя
    mage_i = g.order.index("mage")
    g.lb.selection_clear(0, "end"); g.lb.selection_set(mage_i); g._on_list()
    assert g.cur == "mage"
    assert g.tree_lb.size() == 10, g.tree_lb.size()   # у мага 10 слотов дерева
    print("переключение на мага: дерево 10 слотов OK")

    # ---------------------------------------------------------------- 3) перестановка слотов
    g.sel = 0; g.tree_lb.selection_set(0)
    slots = g.hero["skill_tree"]
    a, b = slots[0], slots[1]
    g._tree_move(1)
    assert slots[0] is b and slots[1] is a, "перестановка не сработала"
    assert g.sel == 1 and g.chars_dirty, "выбор/dirty не обновились"
    g._tree_move(-1)
    assert slots[0] is a and slots[1] is b
    print("перестановка ↑/↓ OK")

    # ---------------------------------------------------------------- 4) добавление и удаление слота
    class FakeDlg:
        def __init__(self, parent, skills): self.result = ("heal", 7)
    g.wait_window = lambda w: None
    hero_editor._SlotDialog = FakeDlg
    n = len(slots)
    g._tree_add()
    assert len(slots) == n + 1 and slots[-1] == {"skill": "heal", "unlock_level": 7}, slots[-1]
    g.sel = n; g._tree_del()
    assert len(slots) == n, "удаление не сработало"
    print("добавление слота (навык + уровень) и удаление OK")

    # ---------------------------------------------------------------- 5) форма слота
    g.sel = 0; g.tree_lb.selection_set(0)
    g.slot_form.load()
    orig_skill = slots[0].get("skill")
    cb = g.slot_form.w["skill"]["cb"]
    cb.set("heal"); g.slot_form._commit(g.slot_form.fields[0])
    assert slots[0]["skill"] == "heal", slots[0]
    cb.set("по умолчанию"); g.slot_form._commit(g.slot_form.fields[0])
    assert "skill" not in slots[0], "пустой выбор должен удалять ключ"
    cb.set(orig_skill); g.slot_form._commit(g.slot_form.fields[0])
    assert slots[0]["skill"] == orig_skill, "восстановление слота не сработало"
    print("форма слота: выбор навыка, пустое поле удаляет ключ OK")

    # ---------------------------------------------------------------- 6) меню навыков
    g.menu["columns"] = 6; g.menu["rows"] = 2
    assert g.menu_dirty
    g._refresh_preview()          # предпросмотр с 6 столбцами — не падает
    g.touch_menu()
    assert "меню не сохранено" in g.status.get(), g.status.get()
    g.revert_menu()
    assert g.menu.get("columns") == 4 and not g.menu_dirty
    print("меню навыков: правка → dirty → предпросмотр → revert OK")

    # ---------------------------------------------------------------- 7) revert персонажей
    g.hero["role"] = "тест-роль"; g.touch()
    assert g.chars_dirty
    g.revert()
    assert not g.chars_dirty and g.cur == g.order[0]
    print("revert персонажей OK")

    # ---------------------------------------------------------------- 8) сохранение: формат файлов
    g.lb.selection_clear(0, "end"); g.lb.selection_set(g.order.index("mage")); g._on_list()
    g._tree_add()                 # ещё один слот (heal, ур. 7) магу
    assert g.save()
    saved = CHARS_PATH.read_text(encoding="utf-8")
    assert saved == json.dumps(g.chars, ensure_ascii=False, indent=2) + "\n", "формат characters.json изменился"
    assert len(json.loads(saved)["characters"]["mage"]["skill_tree"]) == 11
    g.menu["scroll_arrow_color"] = [10, 20, 30]
    assert g.save_menu()
    assert MENU_PATH.read_text(encoding="utf-8") == json.dumps(g.menu, ensure_ascii=False, indent=2) + "\n"
    print("сохранение: characters.json и skill_menu.json записаны в своём формате OK")
finally:
    CHARS_PATH.write_text(chars_before, encoding="utf-8")   # вернуть файлы как были
    MENU_PATH.write_text(menu_before, encoding="utf-8")
    root.destroy()

assert CHARS_PATH.read_text(encoding="utf-8") == chars_before
assert MENU_PATH.read_text(encoding="utf-8") == menu_before
# ---------------------------------------------------------------- 9) confirm_close без изменений
root = tk.Tk(); root.withdraw()
frame2 = ttk.Frame(root); frame2.pack()
g2 = hero_editor.HeroTab(frame2)
assert g2.confirm_close() is True
root.destroy()
print("confirm_close без изменений OK")

print("SMOKE вкладки «Герои»: ALL OK")
