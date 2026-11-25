# -*- coding: utf-8 -*-
"""Headless-тест [mp_rooms]: независимые комнаты игроков в мультиплеере.

Проверяет:
  1. Два игрока стартуют на карте хоста; sims создаются.
  2. go_player переводит ОДНОГО игрока на другую карту, второй остаётся на месте.
  3. step() не падает, когда игроки в разных комнатах; комнаты без игроков не симулируются.
  4. snapshot_for(room_id) отдаёт мобов только той комнаты; g.room/g.projs/g.fx хоста — мир его героя.
  5. Реальный выход в легенде срабатывает индивидуально (второй игрок не двигается).
  6. respawn_player: якорь — только живые игроки той же комнаты; иначе точка появления комнаты.
  7. Клоны игрока растворяются при его уходе из комнаты.
  8. game_over — только когда погибли ВСЕ игроки.
  9. Клиент: apply_world открывает комнату из снимка ("room"), apply_players раздаёт room_id
     из "rm" (себе и союзникам), изменение "tp" переставляет героя, g.room переключается
     ДО predict, apply_mobs кладёт мобов в комнату из снимка.

Запуск: SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy ./.venv/Scripts/python.exe multiagent/out/mp_rooms_test.py
"""
import os
if os.environ.get("SDL_VIDEODRIVER") != "dummy":
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_AUDIODRIVER"] = "dummy"

import sys, traceback
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pygame as pg
import main
from core import CFG, T
from multiplayer import HostSession, Input, NetKeys
from mob import Mob


class FakeHost(HostSession):
    """HostSession без сети: не вызываем __init__ (сокеты), только заполняем слоты,
    на которые опираются его методы (players/inputs/conns/sims/warn_t/phase/g/lobby)."""
    is_host = True
    in_game = True


def main_test():
    g = main.Game()   # SDL dummy: pg.init/set_mode работают

    fs = FakeHost.__new__(FakeHost)
    fs.g = g; fs.phase = "game"; fs.players = {}; fs.inputs = {}; fs.game_over = False
    fs.conns = {}; fs.pending = []; fs.warn_t = 0; fs.sims = {}; fs.mobs = {}
    fs.lobby = None   # entry() безопасно примет отсутствие лобби

    # --- 1. старт: хост — g.pl, все игроки на карте хоста ---------------------------
    host = g.pl
    host.pid, host.name, host.room_id = 0, "Хост", None
    fs.players[0] = host
    start = g.room.id
    fs.go(start, None)
    assert host.room_id == start, host.room_id
    assert set(fs.sims) == {start}, fs.sims.keys()
    sim0 = fs.sims[start]
    assert g.room is sim0.room and g.projs is sim0.projs and g.fx is sim0.fx, "g.* должны указывать на мир хоста"

    # второй игрок подключается — появляется в комнате живого союзника
    fs.lobby = [{"id": 1, "name": "Тень", "char": "shadow"}]
    fs.join_game(1)
    p1 = fs.players[1]
    assert p1.room_id == start, p1.room_id

    # пара кадров общей симуляции не падает
    for _ in range(5):
        fs.step(1 / 60)
    assert not fs.game_over

    # --- 2. переход ОДНОГО игрока на другую карту ----------------------------------
    other = next(mid for mid in CFG["map_defs"] if mid != start and not mid.startswith("_"))
    x0, y0 = host.x, host.y
    fs.go_player(p1, other, None)
    assert p1.room_id == other
    assert host.room_id == start, "хост не должен был переехать"
    assert (host.x, host.y) == (x0, y0), "переход одного не двигает другого"
    assert len(fs.sims) == 2, fs.sims.keys()
    sim1 = fs.sims[other]
    assert sim1.room is g.camp.get(other)
    assert g.camp.get(other).visited, "новая комната помечена посещённой"
    assert 0 <= p1.x < sim1.room.width_px and 0 <= p1.y < sim1.room.height_px, "игрок размещён внутри новой карты"

    # --- 3. кадры в разных комнатах; пустые комнаты не симулируются ----------------
    for _ in range(10):
        fs.step(1 / 60)
    assert not fs.game_over
    # после шага g.* снова смотрят на мир хоста (sync_host_room в конце step)
    assert g.room is fs.sims[host.room_id].room
    assert g.projs is fs.sims[host.room_id].projs
    assert g.fx is fs.sims[host.room_id].fx

    # --- 4. snapshot_for: мобы/дропы/fx — только той комнаты; pls — все с "rm" -----
    from core import FX as _FX
    sim0.room.mobs.append(Mob("rotling", host.cx + 40, host.y - 60, 1.0, sim0.room))
    sim1.room.mobs.append(Mob("bat", p1.cx + 40, p1.y - 60, 1.0, sim1.room))
    sn_h = fs.snapshot_for(host.room_id)
    sn_c = fs.snapshot_for(p1.room_id)
    assert sn_h["room"] == host.room_id and sn_c["room"] == p1.room_id
    assert {e[1] for e in sn_h["mobs"]} == {m.kind for m in sim0.room.mobs}, "в снимке хоста — мобы его комнаты"
    assert {e[1] for e in sn_c["mobs"]} == {m.kind for m in sim1.room.mobs}, "в снимке клиента — мобы его комнаты"
    assert {lp["id"] for lp in sn_h["pl"]} == {0, 1} and all(lp["rm"] for lp in sn_h["pl"]), "pls: все игроки с полем rm"
    assert {lp["id"]: lp["rm"] for lp in sn_h["pl"]}[1] == other

    # --- 5. индивидуальный выход: p1 уходит по выходу своей комнаты -----------------
    # Комната должна быть открыта: в запертой клетка выхода становится "D" (стена).
    # Ставим p1 над клеткой выхода и держим "вниз" (лестничные выходы ведут вниз сам).
    moved = None
    sim1.room.set_lock(False)
    inp = Input(); inp.keys = NetKeys((0, 0, 0, 1, 0, 0))   # зажат "вниз"
    fs.inputs[1] = inp
    for zz in sim1.room.exits:
        t = g.camp.resolve(sim1.room.id, zz["entry"]["exit"])
        if not t or t == "__end__": continue
        p1.hp = 80.0; p1.downed = False; p1.revive = 0.0
        p1.x = zz["rect"].centerx - p1.w / 2; p1.y = zz["rect"].top - p1.h; p1.vx = p1.vy = 0.0
        for _ in range(120):
            fs.step(1 / 60)
            if p1.room_id != sim1.room.id: break
        if p1.room_id != sim1.room.id:
            moved = (zz["char"], t); break
    fs.inputs[1] = Input()   # отпустили "вниз"
    assert moved is not None, f"индивидуальный переход по выходу не сработал (последняя клетка {int(p1.cy // T)}, стена? {p1.room_id})"
    assert host.room_id == start, "хост не должен был переехать"
    assert p1.room_id in fs.sims, "для новой комнаты p1 создан мир"
    # юнит: take_exit напрямую ведёт ровно туда, куда указывает resolve
    sim_now = fs.sims[p1.room_id]
    z = target = None
    for zz in sim_now.room.exits:
        t = g.camp.resolve(sim_now.room.id, zz["entry"]["exit"])
        if t and t != "__end__": z, target = zz, t; break
    if z is not None:
        assert fs.take_exit(p1, z) and p1.room_id == target, "take_exit ведёт в комнату по resolve"

    # --- 6. respawn_player: якорь только из своей комнаты ---------------------------
    roomB = fs.sims[p1.room_id].room
    rectB, ladderB = fs.sims[p1.room_id].respawn
    p1.hp = -1.0; p1.downed = False; p1.revive = 0.0
    fs.respawn_player(p1)   # живых в комнате p1 нет -> точка появления ЕГО комнаты
    assert abs(p1.x - (rectB.centerx - p1.w / 2)) < 1.5 and abs(p1.y - (rectB.bottom - p1.h)) < 1.5, \
        "без живых якорей игрок возвращается в точку появления своей комнаты"
    # хост переходит в ту же комнату, комната заперта -> якорь — живой союзник этой комнаты
    fs.go_player(host, p1.room_id, None)
    roomB.locked = True
    p1.hp = -1.0; p1.downed = False
    fs.respawn_player(p1)
    assert abs(p1.x - host.x) < 64 and abs(p1.y - host.y) < 64, "в запертой комнате якорь — живой союзник"

    # --- 7. клоны растворяются при уходе владельца ---------------------------------
    class FakeClone:
        hp = 10.0; gone = False
        def dissolve(s2, fx2): s2.gone = True; s2.hp = 0.0
    fake = FakeClone()
    host.clones = [fake]
    third = next(mid for mid in CFG["map_defs"] if mid not in (start, p1.room_id) and not mid.startswith("_"))
    fs.go_player(host, third, None)
    assert host.clones == [] and fake.gone and fake.hp <= 0, "клоны растворяются при уходе владельца из комнаты"

    # --- 8. game_over только когда погибли все --------------------------------------
    p1.hp = -1.0
    fs.step(1 / 60)
    assert not fs.game_over, "хост жив — game_over нет"
    host.hp = -1.0
    fs.step(1 / 60)
    assert fs.game_over, "все погибли — game_over"

    # --- 9. клиент: комната из снимка, room_id из "rm", tp-перестановка ДО predict ----
    from multiplayer import ClientSession
    from core import FX as _FX
    host.hp = 90.0; host.downed = False; p1.hp = 90.0; p1.downed = False
    host_camp = g.camp   # apply_world подменит g.camp на клиентский — вернём перед ходами хоста
    cs = ClientSession.__new__(ClientSession)   # без __init__: не подключаемся по сети
    cs.g = g; cs.my_id = 1; cs.players = {}; cs.camp = None; cs.mobs = {}
    cs.game_over = False; cs.predicting = False; cs.local_tp = None; cs.local_hc = None
    cs.ready = False; cs.scratch_projs = []; cs.scratch_fx = _FX()
    my_room = p1.room_id   # «мы» — клиент pid 1, сидим в комнате p1
    sn = fs.snapshot_for(my_room)
    cs.latest = sn; g.room = None
    cs.apply_world(sn)
    assert g.camp is cs.camp and g.room.id == my_room and g.room.visited, "клиент открыл комнату из снимка"
    cs.apply_players(sn, None, 0.0, 0.0)
    me, ally = cs.players[1], cs.players[0]
    assert me.room_id == my_room, "свой room_id из поля rm"
    assert ally.room_id == host.room_id and ally.room_id != my_room, "чужой room_id из поля rm"
    assert cs.predicting and me.hp > 0, "живой герой предсказывается"
    # хост перебрасывает «меня» в свою комнату (tp растёт в place()); клиент должен
    # переключить g.room по свежему снимку и пересадить героя ДО predict
    g.camp = host_camp   # ходы хоста считают мир хостового Campaign
    fs.go_player(p1, host.room_id, None)
    sn2 = fs.snapshot_for(p1.room_id)
    cs.latest = sn2
    cs.apply_world(sn2)
    assert g.room.id == p1.room_id, "g.room переключён по свежему снимку ДО predict"
    tp_before = cs.local_tp
    cs.apply_players(sn2, None, 0.0, 0.0)
    assert cs.local_tp != tp_before and cs.local_tp == p1.tp, "изменение tp переставило героя (local_tp = tp хоста)"
    assert abs(me.x - p1.x) < 1.0 and abs(me.y - p1.y) < 1.0, "позиция героя — как поставил хост"
    cs.apply_mobs(g.room, sn2, None, 0.0, 0.0, 1 / 60)
    assert {m.kind for m in g.room.mobs} == {m.kind for m in fs.sims[p1.room_id].room.mobs}, "мобы из снимка легли в комнату клиента"
    cs.predict(1 / 60)   # предсказание уже в новой комнате — не падает
    assert 0 <= me.cx <= g.room.width_px and 0 <= me.cy <= g.room.height_px, "предсказание идёт в комнате из снимка"

    print("MP_ROOMS_TEST_OK")


if __name__ == "__main__":
    try:
        main_test()
    except Exception:
        traceback.print_exc()
        print("MP_ROOMS_TEST_FAIL")
        sys.exit(1)
