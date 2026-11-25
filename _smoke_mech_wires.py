"""Смоук новых возможностей редактора механизмов: провода между механизмами (только редактор,
в карте поле "wires") + редактирование путей платформ (точки, перетаскивание, стрелки) и
пунктир хода лифта. Запуск: python _smoke_mech_wires.py. Ничего не пишет в настоящие данные."""
import sys
from types import SimpleNamespace
import tkinter as tk
from tkinter import messagebox

import map_editor
from map_editor import Editor
from mech_panel import clean_spec

root = tk.Tk(); root.withdraw()
messagebox.askyesno = lambda *a, **k: True
messagebox.showinfo = lambda *a, **k: None
messagebox.showerror = lambda *a, **k: print("SHOWERROR:", a)

ed = Editor(root, window=None)
mp = ed.mpanel
assert mp is not None, "панель механизмов не создалась"
ok = True

def press(x, y): ed.paint(SimpleNamespace(x=x, y=y, type="4"))
def motion(x, y): ed.paint(SimpleNamespace(x=x, y=y, type="6"))  # B1-Motion
def move(x, y): mp._canvas_motion(SimpleNamespace(x=x, y=y))
def rclick(x, y): ed.erase(SimpleNamespace(x=x, y=y))

def cs_px(): return ed.cell_size()
def px(cx): return cx * cs_px() + cs_px() / 2 - ed.canvas.canvasx(0)
def py(cy): return cy * cs_px() + cs_px() / 2 - ed.canvas.canvasy(0)

# ---------- 1. расстановка механизмов ----------
print("== 1. расстановка механизмов ==")
mp.mode.set(True); mp._mode_changed()
mp.type_var.set(mp.type_label("lever"))
press(px(3), py(3))            # рычаг №1
mp.type_var.set(mp.type_label("button"))
press(px(3), py(5))            # кнопка №2
mp.type_var.set(mp.type_label("door"))
press(px(8), py(3))            # дверь №3
mp.type_var.set(mp.type_label("elevator"))
press(px(12), py(3))           # лифт №4
mp.type_var.set(mp.type_label("teleporter"))
press(px(16), py(3))           # портал №5
press(px(20), py(3))           # портал №6
ids = [s["id"] for s in ed.mechs]
assert ids == [1, 2, 3, 4, 5, 6], ids
# кисть ставит всем один и тот же канал-умолчание — разводим каналы для проверки цвета провода
for k, ch in enumerate(("chA", "chB", "chD", "", "", "")): ed.mechs[k]["channel"] = ch
print("   поставлено 6 механизмов:", ids)

# ---------- 2. провода: соединение, дубликаты, цвет, удаление ----------
print("== 2. провода ==")
mp.wire_mode.set(True); mp._wire_mode_changed()
press(px(3), py(3))            # источник: рычаг №1
assert mp.wire_src is not None and mp.wire_src["id"] == 1
press(px(8), py(3))            # рычаг -> дверь №3
assert len(mp.wires) == 1 and mp.wires[0] == {"a": 1, "b": 3}
assert mp.wire_src["id"] == 1, "источник должен остаться выбранным (цепочка)"
press(px(12), py(3))           # рычаг -> лифт №4
assert len(mp.wires) == 2
press(px(16), py(3))           # рычаг -> портал №5
press(px(20), py(3))           # портал №5... нет, источник №1 -> портал №6
assert len(mp.wires) == 4
st1, why1 = mp._wire_state({"a": 1, "b": 3})
st2, why2 = mp._wire_state({"a": 5, "b": 6})
print(f"   рычаг->дверь: {st1} ({why1}); портал->портал: {st2} ({why2})")
assert st1 == "warn", "разные каналы — связь должна быть warn"
assert st2 == "warn", "пара порталов не настроена — warn"
# настроим каналы и пары: канал chA у рычага и двери; пары 5<->6
ed.mechs[0]["channel"] = "chA"; ed.mechs[2]["channel"] = "chA"
ed.mechs[4]["pair"] = 6; ed.mechs[5]["pair"] = 5
st1, _ = mp._wire_state({"a": 1, "b": 3}); st2, _ = mp._wire_state({"a": 5, "b": 6})
assert st1 == "ok" and st2 == "ok", (st1, st2)
print("   после настройки канала/пары связи стали ok (зелёные)")
# дубликат: рычаг -> дверь повторно
press(px(3), py(3)); press(px(8), py(3))
assert len(mp.wires) == 4, "дубликат провода не должен добавляться"
# ЛКМ по пустому месту — сброс источника
mp.wire_src = ed.mechs[0]
press(px(25), py(10))
assert mp.wire_src is None, "ЛКМ по пустому месту должно сбрасывать источник"
# ЛКМ по линии провода — удалить провод
n = len(mp.wires)
press((px(3) + px(8)) / 2, py(3))   # середина провода 1->3
assert len(mp.wires) == n - 1, "ЛКМ по линии провода должна его удалять"
# ПКМ по механизму в режиме проводов — убрать все его провода
press(px(3), py(3)); press(px(12), py(3))   # снова 1->4 (если ещё нет)
assert any((w["a"], w["b"]) in ((1, 4), (4, 1)) for w in mp.wires), "провод 1->4 должен существовать"
rclick(px(3), py(3))
assert not any(1 in (w["a"], w["b"]) for w in mp.wires), "ПКМ по механизму должен убирать его провода"
# ПКМ в режиме проводов НЕ должен удалять сам механизм
assert any(s["id"] == 1 for s in ed.mechs), "ПКМ в режиме проводов не должен удалять механизм"
print(f"   проводов после правок: {len(mp.wires)}; механизм №1 на месте")
# провод между двумя порталами сам настраивает их «пару» — в игре они ведут друг в друга
ed.mechs[4]["pair"] = None; ed.mechs[5]["pair"] = None   # сбросим ручную настройку — проверяем авто
press(px(16), py(3))           # источник — портал №5
assert mp.wire_src is not None and mp.wire_src["id"] == 5
press(px(20), py(3))           # портал №6 -> провод 5<->6, пара настроена сама
assert any({w["a"], w["b"]} == {5, 6} for w in mp.wires), "провод 5<->6 должен появиться"
assert ed.mechs[4]["pair"] == 6 and ed.mechs[5]["pair"] == 5, (ed.mechs[4].get("pair"), ed.mechs[5].get("pair"))
st, why = mp._wire_state({"a": 5, "b": 6})
assert st == "ok", why
print("   портал->портал: пара настроилась сама (в игре телепортируют друг в друга)")
# удаление провода снимает пару
c5 = mp._center_px(ed.mechs[4]); c6 = mp._center_px(ed.mechs[5])   # точно по центру линии 5<->6
cv = ed.canvas
press((c5[0] + c6[0]) / 2 - cv.canvasx(0), (c5[1] + c6[1]) / 2 - cv.canvasy(0))
assert not any({w["a"], w["b"]} == {5, 6} for w in mp.wires), "провод 5<->6 должен удалиться"
assert ed.mechs[4].get("pair") is None and ed.mechs[5].get("pair") is None, (ed.mechs[4].get("pair"), ed.mechs[5].get("pair"))
print("   провод удалён — пара порталов снялась")

# ---------- 3. сохранение/загрузка проводов ----------
print("== 3. сохранение/загрузка проводов ==")
mp.wire_mode.set(False); mp._wire_mode_changed()
ed.mechs[0]["channel"] = "chA"; ed.mechs[2]["channel"] = "chA"
mp.wires = [{"a": 1, "b": 3}, {"a": 5, "b": 6}, {"a": 99, "b": 1}]
dump_wires = mp.dump_wires()
assert dump_wires == [{"a": 1, "b": 3}, {"a": 5, "b": 6}], dump_wires
data = {"mechanisms": [clean_spec(s) for s in ed.mechs], "wires": dump_wires}
ed.mpanel.load(data["mechanisms"]); ed.mpanel.load_wires(data["wires"])
assert mp.wires == [{"a": 1, "b": 3}, {"a": 5, "b": 6}], mp.wires
assert len(ed.mechs) == 6
print("   dump/load проводов: ок (битые провода отсеиваются)")

# ---------- 4. путь платформы: добавление, перетаскивание, удаление точек ----------
print("== 4. путь платформы ==")
mp.type_var.set(mp.type_label("mover"))
mp.path_mode.set(True); mp._path_mode_changed()
mp.sel = None
press(px(4), py(15))           # создаём платформу №7 с точкой пути [4,15]
assert len(ed.mechs) == 7 and ed.mechs[6]["type"] == "mover"
mv = ed.mechs[6]
assert mv["path"] == [[4, 15]], mv["path"]
press(px(8), py(15)); press(px(8), py(19)); press(px(4), py(19))
assert mv["path"] == [[4, 15], [8, 15], [8, 19], [4, 19]], mv["path"]
print("   путь из 4 точек построен кликами (режим пути остаётся включённым):", mv["path"])
assert mp.path_mode.get(), "режим пути не должен выключаться сам"
# перетаскивание точки: ЛКМ по точке 2 (8,15) и тянуть
press(px(8), py(15))
assert mp._drag_pt == 1, "ЛКМ по точке пути должно начинать перетаскивание"
motion(px(10), py(13))
assert mv["path"][1] == [10, 13], mv["path"]
motion(px(400), py(13))        # за краем карты — точка не меняется
assert mv["path"][1] == [10, 13]
rclick(px(10), py(13))         # ПКМ по точке — удалить
assert mv["path"] == [[4, 15], [8, 19], [4, 19]], mv["path"]
print("   перетаскивание и удаление точек: ок ->", mv["path"])
# развернуть путь
mp.reverse_path()
assert mv["path"] == [[4, 19], [8, 19], [4, 15]], mv["path"]
print("   «Развернуть путь»: ок ->", mv["path"])
# дубликат точки не добавляется
press(px(4), py(19))
assert mv["path"] == [[4, 19], [8, 19], [4, 15]]
# очистка пути
mp.clear_path()
assert mv["path"] == [], mv["path"]
print("   «Очистить путь»: ок")
# отрисовка не падает (линии, стрелки, номера, пунктир хода лифта)
mv["path"] = [[4, 15], [8, 15], [8, 19], [4, 19]]
mv["loop"] = True
ed.mechs[3]["range"] = 5
ed._draw_all()
n_items = len(ed.canvas.find_all())
print(f"   отрисовка пути/лифта/проводов: элементов на канвасе {n_items}")
ok &= n_items > 0

# ---------- 5. удаление механизма убирает его провода ----------
print("== 5. удаление механизма ==")
mp.wire_mode.set(False); mp._wire_mode_changed()
mp.path_mode.set(False); mp._path_mode_changed()
mp.sel = None
ed.mechs.append({"id": 8, "type": "door", "x": 8, "y": 25, "channel": "chA", "w": 1, "h": 2})
mp.wires.append({"a": 1, "b": 8})
mp.sel = None
rclick(px(8), py(25))          # убрать дверь №8
assert not any(s["id"] == 8 for s in ed.mechs)
assert not any(8 in (w["a"], w["b"]) for w in mp.wires), "провода удалённого механизма должны убираться"
print("   механизм и его провода удалены; проводов осталось:", len(mp.wires))

# ---------- 6. лифт: пунктир хода и «выбранный источник» не ломают отрисовку ----------
print("== 6. отрисовка в режиме проводов с источником ==")
mp.wire_mode.set(True); mp._wire_mode_changed()
mp.wire_src = ed.mechs[0]
move(px(10), py(8))
ed._draw_all()
mp.wire_mode.set(False); mp._wire_mode_changed()
ed._draw_all()
print("   ок")

# ---------- 7. сохранение карты в файл: поле wires пишется, игра поле игнорирует ----------
print("== 7. сохранение карты ==")
import tempfile, json as _json
from pathlib import Path
map_editor.MAP_DIR = Path(tempfile.mkdtemp(prefix="dr_wires_"))
mp._portals_pair(ed.mechs[4], ed.mechs[5])   # пара порталам (как это делает провод) — проверим, что дойдёт до игры
ed.map_id.set("wires_test")
ed.name.set("Провода")
ed.save_map()
saved = _json.loads((map_editor.MAP_DIR / "wires_test.json").read_text(encoding="utf-8"))
assert "mechanisms" in saved and "wires" in saved, list(saved.keys())
print("   в файле карты: mechanisms =", len(saved["mechanisms"]), ", wires =", saved["wires"])
# игра: mechs.create читает mechanisms и не падает от wires
sys.path.insert(0, ".")
import maps
from core import CFG
CFG["map_defs"]["wires_test"] = saved
room = maps.GameMap("wires_test")
assert len(room.mechs) == len(saved["mechanisms"]), (len(room.mechs), len(saved["mechanisms"]))
print("   GameMap загрузил карту с полем wires без ошибок: механизмов", len(room.mechs))
# в игре порталы ссылаются друг на друга через «пару» (room.mech_by_id)
tps = [m for m in room.mechs if m.tid == "teleporter"]
assert len(tps) == 2 and all(m.pair is not None for m in tps), [(m.id, m.pair) for m in tps]
assert all(room.mech_by_id(m.pair) is not None and room.mech_by_id(m.pair).tid == "teleporter" for m in tps), [(m.id, m.pair) for m in tps]
print("   в игре порталы ведут друг в друга: pair", [(m.id, m.pair) for m in tps])

print("\nSMOKE", "OK" if ok else "FAILED")
