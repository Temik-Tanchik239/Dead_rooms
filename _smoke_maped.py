"""Смоук редактора карт: скорость на карте 300×300 (отрисовка/правка клетки) + страница «Мир»
(весь мир одним холстом: кисть по картам пишет в их json, перетаскивание — pos). Запуск: python _smoke_maped.py
Ничего не пишет в настоящие данные: для мира подменяет MAP_DIR/MAP_CONFIG на временную папку."""
import json, shutil, sys, tempfile, time
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
from tkinter import messagebox

import map_editor
from map_editor import Editor

root = tk.Tk(); root.withdraw()
messagebox.askyesno = lambda *a, **k: True          # «Применить размер», «Очистить» — без вопросов
messagebox.showinfo = lambda *a, **k: None
messagebox.showerror = lambda *a, **k: print("SHOWERROR:", a)

ed = Editor(root, window=None)
ok = True

# ---------- 1. карта 300×300: полная перерисовка и правка одной клетки ----------
print("== 1. карта 300×300: скорость отрисовки ==")
ed.width_var.set("300"); ed.height_var.set("300"); ed.resize_map()
assert (ed.map_w, ed.map_h) == (300, 300), "размер не применился"
for y in range(0, 300, 3):        # заполняем треть карты стенами, как после генерации
    for x in range(0, 300, 3):
        ed.rows[y][x] = "#"
t0 = time.perf_counter(); ed._draw_all(); t_full = time.perf_counter() - t0
print(f"   полная перерисовка (видимая область): {t_full*1000:.1f} мс, элементов на канвасе: {len(ed.canvas.find_all())}")
ok &= t_full < 1.0

ev = SimpleNamespace(x=200, y=200)
t0 = time.perf_counter()
for i in range(200):              # 200 правок клеток (как при протягивании мышью)
    ev.x, ev.y = 100 + (i % 50), 100 + (i % 50)
    ed.paint(ev)
t_paint = time.perf_counter() - t0
print(f"   200 правок клеток (paint): {t_paint*1000:.1f} мс, элементов: {len(ed.canvas.find_all())}")
ok &= t_paint < 1.0 and ed.rows[6][6] == "#"   # при зуме 1.0 экранные (100, 100) = клетка (6, 6)
ev.x, ev.y = 100, 100; ed.erase(ev)
assert ed.rows[6][6] == ".", "ПКМ-ластик не сработал"
# прокрутка не должна перерисовывать всё без изменения видимой области
n_items = len(ed.canvas.find_all())
ed.canvas.yview_scroll(120, "units"); root.update()
ed.canvas.yview_scroll(-120, "units"); root.update()
print(f"   прокрутка туда-обратно: элементов {n_items} -> {len(ed.canvas.find_all())} (перерисовка только при смещении)")

# ---------- 2. страница «Мир»: карты вплотную по сетке pos, правка кистью ----------
print("== 2. «Мир»: весь мир одним холстом ==")
tmp = Path(tempfile.mkdtemp(prefix="dr_world_"))
maps = tmp / "maps"; maps.mkdir()
(maps / "a_0_0.json").write_text(json.dumps({"name": "Первая", "pos": [0, 0], "rows": ["######", "#....#", "#....#", "######"]}), encoding="utf-8")
(maps / "b_5_0.json").write_text(json.dumps({"name": "Вторая", "pos": [5, 0], "rows": ["#####", "#...#", "#...#", "#####"]}), encoding="utf-8")
(maps / "c_free.json").write_text(json.dumps({"name": "Без pos", "rows": ["##"]}), encoding="utf-8")
(tmp / "maps.json").write_text(json.dumps({"start": "a_0_0"}), encoding="utf-8")
map_editor.MAP_DIR, map_editor.MAP_CONFIG = maps, tmp / "maps.json"

ed.world_mode(True); ed._world_enter()
assert ed.world_on and len(ed.world_maps) == 3, f"скан мира: {len(ed.world_maps)}"
assert ed.world_px > 0, "масштаб мира не подобран"
ids = {m["id"] for m in ed.world_maps}
assert {"a_0_0", "b_5_0", "c_free"} <= ids, ids
pw, ph = ed._world_pitch
assert (pw, ph) == (6, 5), f"слот сетки по максимальной карте: {(pw, ph)}"   # карты дополняются до 5×5
ma = next(m for m in ed.world_maps if m["id"] == "a_0_0")
ra = ed._world_rect(ma)
mb = next(m for m in ed.world_maps if m["id"] == "b_5_0")
rb = ed._world_rect(mb)
# карты стоят по своим pos: слоты разнесены ровно на разницу pos * размер слота
assert abs((rb[0] - ra[0]) - 5 * pw * ed.world_px) < 1, "карты не стоят по координатам pos"
print(f"   карты расставлены по pos; масштаб {ed.world_px:.1f} px/клетку; слот сетки {pw}×{ph} клеток")

# ---- рисование кистью прямо по миру: клетка меняется, при отпускании пишется в json ----
ed.world_move.set(False)
ed.world_px = 10.0; ed._draw_world()   # крупный масштаб: клетки, как в обычном режиме
ed.brush.set("#")
ra = ed._world_rect(ma)
ex = ra[0] + 1.5 * ed.world_px - ed.world_canvas.canvasx(0)   # клетка (1, 1) карты a_0_0
ey = ra[1] + 1.5 * ed.world_px - ed.world_canvas.canvasy(0)
ed.world_press(SimpleNamespace(x=ex, y=ey))
assert ed.world_sel == "a_0_0", "локация под кистью не выбралась"
assert ma["rows"][1][1] == "#", "кисть на странице мира не изменила клетку"
ed.world_motion(SimpleNamespace(x=ex + ed.world_px, y=ey))
assert ma["rows"][1][2] == "#", "протягивание кисти не рисует"
ed.world_release(SimpleNamespace(x=ex + ed.world_px, y=ey))
saved = json.loads((maps / "a_0_0.json").read_text(encoding="utf-8"))
assert saved["rows"][1][1:3] == "##", f"правка мира не записалась в json: {saved['rows']}"
print("   кисть по миру: клетки (1,1..2) -> '#', записаны в json a_0_0 OK")
# ПКМ — стереть
ed.world_erase(SimpleNamespace(x=ex, y=ey))
assert ma["rows"][1][1] == ".", "ПКМ-ластик на странице мира не сработал"
ed.world_release(SimpleNamespace(x=ex, y=ey))
saved = json.loads((maps / "a_0_0.json").read_text(encoding="utf-8"))
assert saved["rows"][1][1] == ".", "ластик мира не записался в json"
print("   ПКМ-ластик по миру OK")

# ---- режим «двигать локации»: перетаскивание пишет pos в json ----
ed.world_move.set(True)
ra = ed._world_rect(ma)
cx = (ra[0] + ra[2]) / 2 - ed.world_canvas.canvasx(0)
cy = (ra[1] + ra[3]) / 2 - ed.world_canvas.canvasy(0)
ed.world_press(SimpleNamespace(x=cx, y=cy))
assert ed.world_drag and ed.world_drag[0] is ma, "режим «двигать» не схватил карту"
ed.world_motion(SimpleNamespace(x=cx + 2 * pw * ed.world_px, y=cy))
ed.world_release(SimpleNamespace(x=cx + 2 * pw * ed.world_px, y=cy))
saved = json.loads((maps / "a_0_0.json").read_text(encoding="utf-8"))
assert saved["pos"] == [2, 0], f"pos не записалась: {saved.get('pos')}"
assert ma["pos"] == [2, 0]
print("   перетаскивание: pos [0, 0] -> [2, 0] записана в json OK")

# карта без pos после перетаскивания получает pos
mc = next(m for m in ed.world_maps if m["id"] == "c_free")
rc = ed._world_rect(mc)
cx, cy = rc[0] + 4 - ed.world_canvas.canvasx(0), rc[1] + 4 - ed.world_canvas.canvasy(0)
ed.world_press(SimpleNamespace(x=cx, y=cy))
ed.world_motion(SimpleNamespace(x=cx + 3 * pw * ed.world_px, y=cy))
ed.world_release(SimpleNamespace(x=cx + 3 * pw * ed.world_px, y=cy))
saved = json.loads((maps / "c_free.json").read_text(encoding="utf-8"))
assert saved["pos"] == [3, 1], f"карта без pos не поставилась на сетку: {saved.get('pos')}"
print("   карта без pos встала на сетку: pos [3, 1] OK")

# двойной клик в режиме «двигать» открывает карту в редакторе
ed.world_sel = "b_5_0"
ed.world_open()
assert not ed.world_on and ed.current_path == maps / "b_5_0.json" and ed.map_id.get() == "b_5_0", "открытие из мира не сработало"
print("   двойной клик открыл b_5_0 в редакторе OK")
# перетаскивание открытой карты не теряется при сохранении
ed.meta["pos"] = [5, 5]
ed.save_map()
saved = json.loads((maps / "b_5_0.json").read_text(encoding="utf-8"))
assert saved["pos"] == [5, 5], "save_map перезатёр pos"
print("   save_map сохраняет pos OK")

shutil.rmtree(tmp, ignore_errors=True)
root.destroy()
print("MAPED_SMOKE_OK" if ok else "MAPED_SMOKE_SLOW")
sys.exit(0 if ok else 1)
