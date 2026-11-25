"""Смоук-тест лута (loot.py): roll/drop_for_mob/update_room, save/restore, mob_data.item_ids/validate.
Запуск: .venv/Scripts/python.exe _smoke_loot.py  (SDL_VIDEODRIVER=dummy)"""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import random
import pygame as pg

random.seed(7)
pg.init()
pg.display.set_mode((320, 240))

import main as game
import loot
import inventory
from core import W, H

print("== 1. roll(): разные мобы ==")
rotling = {"loot": [{"item": "random", "chance": 1.0}], "coins": {"chance": 1.0, "min": 3, "max": 7}}
items, n = loot.roll(rotling)
assert items and n == random.randint(3, 7) or n, "нет выпадений"
print("   random-моб:", items, "монет:", n)
assert all(loot.inventory.is_item(i) for i in items), "неизвестный id предмета"
empty = {"hp": 10}
items2, n2 = loot.roll(empty)
assert items2 == [] and n2 == 0, "у моба без loot/coins должно быть пусто"
print("   пустой моб: без лута OK")

print("== 2. drop_for_mob(): предметы + кучка в r.drops ==")
g = game.Game()
g.new_game()   # new_game(loop=0, character=...) — без аргументов, как в других смоук-тестах
g.menu_mode = None   # new_game открывает меню «start» — убираем, чтобы физика шла
r = g.room
r.mobs = []
import core
core.CFG["mobs"]["__loot_test__"] = {"name": "тест", "hp": 5, "xp": 3, "speed": 0, "w": 16, "h": 16,
                                     "loot": [{"item": "random", "chance": 1.0}],
                                     "coins": {"chance": 1.0, "min": 2, "max": 2}}
m = game.Mob("__loot_test__", 200, 300, 1.0, r)
r.mobs.append(m)
m.hp = 0
ndrops = len(r.drops)
g.step( 0.016)
assert len(r.drops) == ndrops + 2, f"ожидали предмет + кучку монет, а выпало {len(r.drops) - ndrops}"
coins = [d for d in r.drops if isinstance(d, loot.Coin)]
assert len(coins) == 1 and coins[0].n == 2, "кучка монет не выпала или неверный размер"
assert m.xp_paid, "xp_paid не выставлен"
print("   r.drops:", [(type(d).__name__, getattr(d, "n", getattr(d, "wid", None))) for d in r.drops])
g.step( 0.016)   # второй раз — повторных выпадений нет
assert len(r.drops) == ndrops + 2, "лут выпадает повторно!"

print("== 3. update_room(): подбор монет касанием ==")
pl = g.pl
coin = next(d for d in r.drops if isinstance(d, loot.Coin))
pl.x, pl.y = coin.x, coin.y - pl.h; pl.vx, pl.vy = 0, 0   # герой прямо у кучки на полу
g.step(0.016)
assert pl.coins == 2, f"монеты не подобрались касанием (coins={pl.coins})"
assert "coin" in inventory.bag(pl), "в рюкзаке нет ячейки «coin» после подбора"
assert not any(isinstance(d, loot.Coin) for d in r.drops), "кучка не удалена после подбора"
g.draw()
print("   pl.coins:", pl.coins, "— подбор, HUD и отрисовка OK")

print("== 3.5. draw(): монета лежит рядом с героем (раньше падало AttributeError 'wid') ==")
coin = loot.Coin(pl.cx + 10, pl.y + pl.h - 12, 1)   # в радиусе подсказки [E], но draw() подбор не делает
r.drops.append(coin)
g.draw()   # регрессия: 'Coin' object has no attribute 'wid'
r.drops.remove(coin)
print("   draw с монетой рядом OK")

print("== 4. сейв/загрузка: монеты в сейве и кучка в drops ==")
from save_io import snapshot_player, _drops_snapshot, _restore_drops, save, restore
m2 = game.Mob("__loot_test__", 150, 300, 1.0, r)   # новый моб — новая кучка монет для секции сериализации
r.mobs.append(m2); m2.hp = 0; g.step(0.016)
snap = snapshot_player(g.pl)
assert snap.get("coins") == 2, f"в снапшоте героя нет монет: {snap.get('coins')}"
rows = _drops_snapshot(r.drops)
assert any(row and row[0] == "C" for row in rows), "в сериализации дропов нет строки 'C'"
back = _restore_drops(rows)
assert any(isinstance(d, loot.Coin) and d.n == 2 for d in back), "кучка монет не восстановилась из строк 'C'"
meta = save(g, label="Смоук лут")
g2 = game.Game()
restore(g2, meta["id"])
assert g2.pl.coins == 2, f"монеты не восстановились из сейва: {g2.pl.coins}"
restored = [d for d in g2.room.drops if isinstance(d, loot.Coin)]
assert any(d.n == 2 for d in restored), "кучка монет не восстановилась из сейва"
g2.draw()
print("   сейв:", meta["id"], "— монеты и кучка восстановились, draw OK")

print("== 5. mob_data.item_ids() / validate() ==")
from mob_data import item_ids, validate
ids = item_ids()
assert "random" in ids and "rusty_sword" in ids, f"список id неполный: {ids[:5]}..."
warns = validate({"t1": {"hp": 10, "w": 10, "h": 10,
                         "loot": [{"item": "нет_такого", "chance": 0.5}, {"item": "random", "chance": 2.0}],
                         "coins": {"chance": 0.5, "min": 2, "max": 3}}})
assert any("нет предмета" in w for _, w in warns), "validate не поймал незнакомый id"
assert any("шанс" in w for _, w in warns), "validate не поймал шанс > 1"
ok = validate({"t2": {"hp": 10, "w": 10, "h": 10, "loot": [{"item": "random", "chance": 0.5}],
                      "coins": {"chance": 0.5, "min": 2, "max": 3}}})
assert not any("лут" in w or "coins" in w for _, w in ok), "validate ругается на корректный лут"
print("   item_ids:", len(ids), "предметов; validate ловит ошибки лута OK")

print("== 6. монеты — предмет инвентаря: стопка, выброс, миграция, лежание ==")
assert inventory.draw_floor(surf := pg.Surface((120, 120)), "coin", 60, 90, t_ms=123), "draw_floor: нет текстуры монеты (assets/icons/coin.png)"
pl.coins = 7
cell = ("b", inventory.bag(pl).index("coin"))
inventory.drop(g, pl, cell)   # X: выбрасывается ВСЯ стопка кучкой
piles = [d for d in r.drops if isinstance(d, loot.Coin)]
assert any(d.n == 7 for d in piles), "выброс: стопка не упала кучкой на пол"
assert pl.coins == 0 and "coin" not in inventory.bag(pl), "выброс: счётчик/ячейка не обнулены"
pl.x, pl.y = piles[-1].x, piles[-1].y - pl.h; pl.vx = pl.vy = 0
g.step(0.016)   # подобрать кучку обратно касанием
assert pl.coins == 7 and "coin" in inventory.bag(pl), "стопка не подобралась обратно"
inventory.bag(pl)[inventory.bag(pl).index("coin")] = None; pl.coins = 5
inventory.sync_stack(pl)   # миграция старого сейва: монеты есть, ячейки нет
assert "coin" in inventory.bag(pl), "sync_stack: ячейка не восстановлена"
pl.coins = 0; inventory.sync_stack(pl)
assert "coin" not in inventory.bag(pl), "sync_stack: ячейка не убрана при 0"
r.drops.append(loot.Drop(pl.cx + 40, pl.y + pl.h, "rusty_sword"))   # оружие лежит на земле
g.draw()
print("   стопка/выброс/миграция/лежание OK")

print("LOOT_SMOKE_OK")
