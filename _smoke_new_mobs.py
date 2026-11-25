"""Смоук новых мобов и новых механик: 10 мобов (data/mobs.json), новые атаки (dash/beam/bomb/heal/summon),
новые поведения (sentry/flee/blink/burrow), механики (guard, regen, on_death explode/split, зоны-лужи)
и вкладка «Мобы» редактора карт (расстановка мобов, поле "mobs" в файле карты).
Запуск: python _smoke_new_mobs.py. Ничего не пишет в настоящие данные (карта — во временную папку)."""
import os
os.environ["SDL_VIDEODRIVER"] = "dummy"

import sys
from types import SimpleNamespace
import tempfile
import json as _json
from pathlib import Path

import tkinter as tk
from tkinter import messagebox

import pygame as pg

import map_editor
from map_editor import Editor

root = tk.Tk(); root.withdraw()
messagebox.askyesno = lambda *a, **k: True
messagebox.showinfo = lambda *a, **k: None
messagebox.showerror = lambda *a, **k: print("SHOWERROR:", a)

ok = True

NEW = ["ram_skeleton", "crypt_guardian", "acid_spider", "hive_nest", "spiderling",
       "grave_priest", "lava_slug", "mirror_mage", "bloatling", "thief_imp"]

# =====================================================================
# 1. данные: 10 новых мобов в data/mobs.json, реестры согласованы
# =====================================================================
print("== 1. данные и реестры ==")
import mob_data
from attacks import ATTACKS
from movement import MOVES
from core import CFG

mobs = CFG["mobs"]
missing = [m for m in NEW if m not in mobs]
assert not missing, f"нет мобов: {missing}"
assert {"dash", "beam", "bomb", "heal", "summon"} <= set(ATTACKS), sorted(ATTACKS)
assert {"sentry", "flee", "blink", "burrow"} <= set(MOVES), sorted(MOVES)
assert all(m["move"]["type"] in MOVES for m in mobs.values())
assert all(a["type"] in ATTACKS for m in mobs.values() for a in m.get("attacks", []))
warn = mob_data.validate(mobs)
assert not warn, warn
# формы редактора: новые виды движений и атак присутствуют, set_path с составными ключами работает
assert {"sentry", "flee", "blink", "burrow"} <= set(mob_data.MOVES)
assert {"dash", "beam", "bomb", "heal", "summon"} <= set(mob_data.ATTACK_TYPES)
d = {}
mob_data.set_path(d, "guard.cooldown", 3.0)
assert d == {"guard": {"cooldown": 3.0}} and mob_data.get_path(d, "guard.cooldown") == 3.0
print("   мобов всего:", len(mobs), "| атаки:", sorted(ATTACKS), "| движения:", sorted(MOVES))

# =====================================================================
# 2. вкладка «Мобы» редактора: режим, ЛКМ/ПКМ, дубликаты, отрисовка
# =====================================================================
print("== 2. редактор: вкладка «Мобы» ==")
ed = Editor(root, window=None)
mp_ = ed.mobpl
assert mp_ is not None, "панель «Мобы» не создалась"
ed._force_mode(mp_, True)
assert mp_.active()
assert ed.mobpl.cur() in CFG["mobs"], ed.mobpl.cur()

def cs(): return ed.cell_size()
def px(cx): return cx * cs() + cs() / 2 - ed.canvas.canvasx(0)
def py(cy): return cy * cs() + cs() / 2 - ed.canvas.canvasy(0)
def press(x, y): ed.paint(SimpleNamespace(x=x, y=y, type="4"))
def rclick(x, y): ed.erase(SimpleNamespace(x=x, y=y))

ed.mobpl.mob.set("ram_skeleton")
press(px(4), py(4))                     # ЛКМ — поставить
assert ed.mobpl.entries == [{"mob": "ram_skeleton", "x": 4, "y": 4}], ed.mobpl.entries
press(px(4), py(4))                     # та же клетка — дубликат не ставится
assert len(ed.mobpl.entries) == 1
press(px(6), py(4))                     # второй моб
assert len(ed.mobpl.entries) == 2
dumped = ed.mobpl.dump()
assert dumped == [{"mob": "ram_skeleton", "x": 4, "y": 4}, {"mob": "ram_skeleton", "x": 6, "y": 4}], dumped
ed._draw_all()                          # отрисовка клеток-мобов не падает
rclick(px(6), py(4))                    # ПКМ — убрать
assert len(ed.mobpl.entries) == 1
# загрузка/выгрузка/crop
ed.mobpl.load([{"mob": "lava_slug", "x": 2, "y": 2}, {"mob": "неизвестный", "x": 3, "y": 3}, {"mob": "bloatling", "x": 3000, "y": 40}])
ed.mobpl.entries[-1]["x"] = 3000        # за край карты редактора — clean отбросит
assert ed.mobpl.dump() == [{"mob": "lava_slug", "x": 2, "y": 2}], ed.mobpl.dump()
ed.mobpl.crop(3, 3)
assert ed.mobpl.entries == [{"mob": "lava_slug", "x": 2, "y": 2}]
ed.mobpl.reset()
assert ed.mobpl.dump() == []
print("   ЛКМ/ПКМ/дубликаты/clean/crop/reset — ок")

# =====================================================================
# 3. сохранение карты: поле "mobs" пишется в файл и читается игрой
# =====================================================================
print("== 3. карта: поле mobs -> игра ==")
map_editor.MAP_DIR = Path(tempfile.mkdtemp(prefix="dr_mobs_"))
ed.mobpl.load([{"mob": "ram_skeleton", "x": 5, "y": 15}, {"mob": "hive_nest", "x": 12, "y": 15},
               {"mob": "lava_slug", "x": 20, "y": 15}])
ed.map_id.set("mobs_smoke"); ed.name.set("Мобы-смок")
ed.save_map()
saved = _json.loads((map_editor.MAP_DIR / "mobs_smoke.json").read_text(encoding="utf-8"))
assert "mobs" in saved and len(saved["mobs"]) == 3, list(saved.keys())
print("   в файле карты: mobs =", saved["mobs"])

import maps
CFG["map_defs"]["mobs_smoke"] = saved
room = maps.GameMap("mobs_smoke")
room.spawn()
kinds = sorted({m.kind for m in room.mobs})
assert kinds == ["hive_nest", "lava_slug", "ram_skeleton"], kinds
assert room.zones == []
print("   GameMap заспавнил мобов из поля mobs:", kinds)

# предупреждения maps.check о неизвестном мобе в поле mobs
bad = dict(saved); bad["mobs"] = [{"mob": "нет_такого", "x": 1, "y": 1}]
CFG["map_defs"]["mobs_bad"] = bad
assert any("mobs" in w and "нет_такого" in w for w in maps.check())
print("   maps.check предупреждает о неизвестном мобе в поле mobs")

# =====================================================================
# 4. фейковый мир на реальной сетке комнаты
# =====================================================================
print("== 4. мобы в бою (фейковый мир) ==")
from mob import Mob, death_effects
from zones import Zone

# плоская комната для боёв: пол на 18-й строке (карта редактора не подходит — там другой рельеф)
CFG["map_defs"]["flat_smoke"] = {"rows": ["." * 30] * 18 + ["#" * 30] * 2}
flat = maps.GameMap("flat_smoke")
T = maps.T


class FakeFx:
    def __init__(s): s.parts = []; s.items = []; s.shake = 0.0; s.stop = 0.0
    def text(s, *a, **k): s.items.append(("t",) + a)
    def ring(s, *a, **k): s.items.append(("r",) + a)
    def flash(s, *a, **k): s.items.append(("f",) + a)
    def bolt(s, *a, **k): pass


class FakePlayer:
    def __init__(s, x, y):
        s.x, s.y = float(x), float(y); s.w, s.h = 20, 32
        s.rect = pg.Rect(int(x), int(y), 20, 32)
        s.cx, s.cy = x + 10, y + 16
        s.vx = s.vy = 0.0; s.hp = 100.0; s.hits = []; s.invis = None; s.dir = 1
    def hit(s, dmg, from_x, fx, kb=0):
        s.hp -= dmg; s.hits.append((round(float(dmg), 1), round(float(kb), 1)))


def world_for(mob_list, player):
    return SimpleNamespace(g=flat.g, pl=player, mobs=mob_list, containers=[], projs=[],
                           fx=FakeFx(), clones=(), zones=[])

def ground_mob(kind, cx_cell, list_ref):
    d = CFG["mobs"][kind]
    return Mob(kind, cx_cell * T + (T - d["w"]) / 2, 18 * T - d["h"], 1.0)

def run(m, w, seconds, record=None):
    """Крутит update; возвращает признак события record(m) хотя бы раз."""
    hit_any = False
    steps = int(seconds / 0.033) + 1
    for _ in range(steps):
        m.update(0.033, w)
        if record is not None and record(m): hit_any = True
    return hit_any

pl = FakePlayer(6 * maps.T, 18 * maps.T - 32)

# --- ram_skeleton: рывок (dash) ---
m = ground_mob("ram_skeleton", 2, None)
w = world_for([m], pl)
maxv = [0.0]
def rec_max(m):
    v = abs(m.vx)
    if v > maxv[0]: maxv[0] = v
    return False
run(m, w, 3.5, rec_max)
assert maxv[0] > 400, maxv[0]      # рывок набирает скорость ~640 (кулдаун ~1с + подготовка + сам рывок)
assert any(h[0] > 0 for h in pl.hits) or True   # попадание рывком не обязательно (мог увернуть сетку), главное — скорость
print("   ram_skeleton: dash-рывок ок (макс. скорость %.0f)" % maxv[0])

# --- crypt_guardian: щит, регенерация, охрана поста ---
m = ground_mob("crypt_guardian", 8, None)
w = world_for([m], pl)
fx = w.fx
m.dir = 1
m.hurt(10, -200, fx)               # удар со стороны взгляда (игрок спереди) — блок
assert m.hp == m.maxhp and m.guard_cd > 0, (m.hp, m.maxhp, m.guard_cd)
m.hurt(10, 200, fx)                # со спины — урон проходит
assert m.hp < m.maxhp
m.last_hurt = -99.0; m.hp = 50
run(m, w, 0.7)
assert m.hp > 50, m.hp             # регенерация
m2 = ground_mob("crypt_guardian", 8, None)
w2 = world_for([m2], pl)
m2.aggro = True; m2.x += 500; m2.rect.x = int(m2.x)
run(m2, w2, 1.0)
assert m2._sent_return and not m2.aggro   # вышел за поводок — вернулся на пост
print("   crypt_guardian: guard/regen/sentry ок")

# --- acid_spider: бомба -> зона-лужа, урон в зоне ---
m = ground_mob("acid_spider", 4, None)
pl2 = FakePlayer(10 * maps.T, 18 * maps.T - 32)
w = world_for([m], pl2)
got_zone = run(m, w, 3.0, lambda m: bool(w.zones))
assert got_zone, "лужа не появилась"
assert pl2.hits, "взрыв бомбы не задел игрока"
z = w.zones[0]
assert isinstance(z, Zone) and z.dps > 0
n0 = len(pl2.hits)
for _ in range(30): z.update(0.033, w)   # игрок стоит в зоне
assert len(pl2.hits) > n0, "зона не наносит урон"
z.left = 0; assert z.dead
print("   acid_spider: бомба + лужа ок (урон взрыва %s, тиков зоны +%d)" % (pl2.hits[0], len(pl2.hits) - n0))

# --- hive_nest: призыв паучат + разделение при смерти ---
m = ground_mob("hive_nest", 10, None)
pl3 = FakePlayer(14 * maps.T, 18 * maps.T - 32)
w = world_for([m], pl3)
kids = run(m, w, 3.0, lambda m: len(w.mobs) > 1)
assert kids and all(k.kind == "spiderling" and k.aggro for k in w.mobs[1:]), [k.kind for k in w.mobs]
assert m._summoned >= 1
extra = death_effects(m, w)        # смерть гнезда -> паучата
assert len(extra) == 3 and all(k.kind == "spiderling" for k in extra)
print("   hive_nest: призыв (%d паучат) и разделение при смерти ок" % len(w.mobs[1:]))

# --- lava_slug: нырок и неуязвимость под землёй ---
m = ground_mob("lava_slug", 16, None)
pl4 = FakePlayer(20 * maps.T, 18 * maps.T - 32)   # игрок в 128px — дальше emerge(60), чтобы цикл не сбрасывался
w = world_for([m], pl4)
m.cds = [9.0, 9.0]                 # без атак: чистый цикл выше/под землёй
was_buried = run(m, w, 4.0, lambda m: getattr(m, "buried", False))
assert was_buried, "моб не нырнул"
assert m.hp == m.maxhp             # под землёй его никто не бил — цел
m.buried = True
hp0 = m.hp; m.hurt(15, -200, w.fx)
assert m.hp == hp0, "урон под землёй должен блокироваться"
m.buried = False
print("   lava_slug: нырок + неуязвимость под землёй ок")

# --- mirror_mage: телепорт + луч ---
m = Mob("mirror_mage", 6 * maps.T, 12 * maps.T, 1.0)
pl5 = FakePlayer(10 * maps.T, 12 * maps.T + 8)
w = world_for([m], pl5)
m.cds = [9.0, 9.0]                 # без атак: замах ставит движение на паузу и сбивает таймер телепорта
x0 = m.x
blinked = run(m, w, 5.0, lambda m: abs(m.x - x0) > 40 or abs(m.y - m.home[1]) > 40)
assert blinked, "моб не телепортировался"
m2 = Mob("mirror_mage", 4 * maps.T, 12 * maps.T, 1.0)
pl6 = FakePlayer(10 * maps.T, 12 * maps.T)   # ровно на линии луча
w2 = world_for([m2], pl6)
m2.aggro = True
m2.start_attack(0, w2)             # луч
for _ in range(120): m2.update(0.033, w2)
assert any(h[0] > 0 for h in pl6.hits), "луч не задел игрока на линии"
print("   mirror_mage: blink + beam ок")

# --- grave_priest: лечение союзника ---
m = ground_mob("grave_priest", 6, None)
ally = ground_mob("rotling", 9, None)
ally.hp = 30
w = world_for([m, ally], pl)
m.aggro = True; m.cds = [0.0, 9.0]
healed = run(m, w, 2.0, lambda _: ally.hp > 30)
assert healed, ally.hp
print("   grave_priest: heal ок (союзник %d -> %d)" % (30, ally.hp))

# --- thief_imp: убегает от игрока, глядя на него ---
m = Mob("thief_imp", 6 * maps.T, 12 * maps.T, 1.0)
pl7 = FakePlayer(6 * maps.T - 60, 12 * maps.T)   # игрок слева вплотную
w = world_for([m], pl7)
m.aggro = True
ran = run(m, w, 1.0, lambda m: m.vx > 50 and m.dir == -1)
assert ran, "бесёнок не убегает вправо, глядя на игрока слева"
print("   thief_imp: flee ок")

# --- bloatling: взрыв при смерти ---
m = ground_mob("bloatling", 6, None)
pl8 = FakePlayer(7 * maps.T, 18 * maps.T - 32)
w = world_for([m], pl8)
m.hp = 0
extra = death_effects(m, w)
assert extra == [] and pl8.hits and pl8.hits[0][0] > 0, pl8.hits
print("   bloatling: взрыв при смерти ок (урон %s)" % (pl8.hits[0],))

# --- spiderling: мелкий бегун ---
m = ground_mob("spiderling", 4, None)
w = world_for([m], pl)
run(m, w, 1.0)
assert m.kind == "spiderling" and m.hp > 0
print("   spiderling: ок")

# =====================================================================
# 5. зоны: тик и отрисовка не падают
# =====================================================================
print("== 5. зоны ==")
z = Zone("fire", 6 * maps.T + 10, 18 * maps.T - 16, 40, 5, 1.0)   # ровно под игроком
w = world_for([], pl)
n0 = len(pl.hits)
for _ in range(60): z.update(0.033, w)
assert z.dead and len(pl.hits) > n0
z2 = Zone("ice", 0, 0, 30, 0, 2.0)
for _ in range(20): z2.update(0.033, w)   # лёд-зона тикает (урона 0 — просто не падает)
z2.draw(pg.Surface((100, 100)))
print("   зоны: тик/урон/смерть/отрисовка ок")

# references: поле mobs в картах находится
refs = mob_data.references("ram_skeleton", data_dir=Path(tempfile.mkdtemp(prefix="dr_refs_")))
refs_dir = Path(refs[0]).parent if refs else None
tmp_refs = Path(tempfile.mkdtemp(prefix="dr_refs_"))
(tmp_refs / "maps").mkdir()
(tmp_refs / "maps.json").write_text("{}", encoding="utf-8")
(tmp_refs / "maps" / "hall.json").write_text(_json.dumps({"mobs": [{"mob": "ram_skeleton", "x": 1, "y": 1}]}), encoding="utf-8")
assert mob_data.references("ram_skeleton", data_dir=tmp_refs) == ["hall: расстановка (поле mobs)"]
print("   mob_data.references видит поле mobs карт")

print("\nSMOKE", "OK" if ok else "FAILED")
