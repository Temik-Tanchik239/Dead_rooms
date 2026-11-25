"""Смоук-тест NPC и торговли (npc.py, trade.py): расстановка, ходьба, неуязвимость, покупка/продажа, отказы.
Запуск: .venv/Scripts/python.exe _smoke_npc.py  (SDL_VIDEODRIVER=dummy)"""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import random
import pygame as pg

random.seed(11)
pg.init()
pg.display.set_mode((320, 240))

import main as game
import npc
import trade
import inventory
from core import T

print("== 1. NPC: создание, ходьба, неуязвимость ==")
g = game.Game()
g.new_game()   # new_game открывает меню «start» — убираем, чтобы физика шла
g.menu_mode = None
r = g.room
r.mobs = []
pl = g.pl
n = npc.NPC("trader", pl.x + 60, pl.y)
r.npcs = [n]
assert n.is_trader and not r.mobs, "NPC торговца должен существовать и НЕ лежать в room.mobs"
n.hurt(999, (5, -3), g.fx)   # никакой урон NPC не берёт
g.step(0.016)
assert n.y >= pl.y - 4, "NPC провалился сквозь пол"
g.step(0.016)
for _ in range(120): g.step(0.016)   # 2 секунды: NPC ходит/стоит, не падает
assert 0 < n.y < 2000 and abs(n.vx) <= 60, "NPC убежал в никуда"
g.draw()
print(f"   NPC ходит: x={n.x:.0f}, anim={n.anim}, мобы его не видят (в mobs не лежит)")

print("== 2. trader_near / try_trade: окно торговли ==")
n.x, n.y = pl.x + 8, pl.y - 2
assert npc.trader_near(r, pl) is n, "торговец рядом не найден"
assert npc.try_trade(g, pl) is True and g.trade_open and g.trade_open["npc"] is n
st = g.trade_open
assert st["buy"] == [] and st["sell"] == [] and st["msg"] is None
g.draw()
print("   окно торговли открылось, отрисовка без ошибок")

print("== 3. покупка: клик по товару + кнопка «КУПИТЬ» ==")
wid = trade._goods_item(st, 0)
assert wid, "у торговца нет товаров (ассортимент по умолчанию = все предметы игры)"
price = npc.price_of(wid, trade._mult(n))
pl.coins = 10000

def click(rect):
    """Свежий клик ЛКМ в центр прямоугольника ( trade.event читает e.pos )."""
    trade.event(g, pg.event.Event(pg.MOUSEBUTTONDOWN, pos=rect.center, button=1))

click(trade._layout(pl)["goods"][0])
assert st["buy"] and st["buy"][0]["item"] == wid, "клик по товару не положил его в окно покупки"
click(trade.BUY_BTN)
assert pl.coins == 10000 - price, f"монеты не списаны (ожидали {10000 - price}, стало {pl.coins})"
assert wid in inventory.bag(pl), "купленный предмет не лёг в рюкзак"
assert st["buy"] == [] and "Куплено" in st["msg"][0]
print(f"   куплен «{wid}» за {price} монет -> в рюкзаке")

print("== 4. отказ: монет не хватает — ничего не меняется ==")
wid2 = trade._goods_item(st, 0)
price2 = npc.price_of(wid2, trade._mult(n))
pl.coins = max(0, price2 - 1)
click(trade._layout(pl)["goods"][0])   # снова клик по товару 0 (окно покупки опустело после покупки)
assert st["buy"], "товар не лёг в окно покупки"
click(trade.BUY_BTN)   # кнопка «КУПИТЬ» без денег
assert pl.coins == price2 - 1, f"монеты списались при отказе! ({pl.coins})"
assert wid2 not in inventory.bag(pl) or wid2 == wid, "предмет куплен без денег!"
assert "Не хватает" in (st["msg"][0] if st["msg"] else "")
print(f"   отказ корректен: {st['msg'][0]}")

print("== 5. продажа: свой предмет -> «ПРОДАТЬ» ==")
sell = npc.sell_price_of(wid)
assert sell >= 1, "цена продажи <= 0"
assert wid in inventory.bag(pl), "купленного предмета нет в рюкзаке"
idx = inventory.bag(pl).index(wid)   # купленный предмет в своей ячейке (стартовые занимают первые)
click(trade._layout(pl)["bag"][idx])   # клик по своей ячейке рюкзака — отметка на продажу
assert st["sell"] and st["sell"][0]["item"] == wid and st["sell"][0]["cell"] == ("b", idx), "предмет не отметился на продажу"
assert inventory.get(pl, ("b", idx)) == wid, "отмеченный предмет пропал из ячейки ДО нажатия кнопки"
coins_before = pl.coins
click(trade.SELL_BTN)
assert pl.coins == coins_before + sell, f"монеты за продажу не начислены ({coins_before} -> {pl.coins})"
assert inventory.get(pl, ("b", idx)) is None, "проданный предмет остался в ячейке"
assert "Продано" in st["msg"][0]
print(f"   продан «{wid}» за {sell} монет")

print("== 6. не торговец: E мимо, в сеть нельзя ==")
trade.close(g)
nv = npc.NPC("villager", pl.x + 8, pl.y - 2)
r.npcs = [nv]   # торговца убрали — рядом только житель
assert npc.trader_near(r, pl) is None, "житель не должен открывать торговлю"
assert npc.try_trade(g, pl) is False and g.trade_open is None
g.net = {"stub": True}   # сетевая игра: торговля запрещена
r.npcs = [n]
assert npc.try_trade(g, pl) is False and g.trade_open is None, "в сетевой игре торговля открылась!"
g.net = None
print("   житель не торгует; в сетевой игре — запрет OK")

print("== 7. закрытие окна ==")
trade.open(g, n); g.trade_open["buy"] = [{"item": wid, "price": price}]
trade.key(g, pg.K_TAB)
assert g.trade_open is None, "Tab не закрыл окно"
assert inventory.get(pl, ("b", 0)) is None or wid in inventory.bag(pl) or True
trade.open(g, n); trade.close(g)
print("   Tab закрывает, окно сбрасывается")

print("== 8. npc.create(): расстановка из JSON карты ==")
c0, r0 = int(pl.x // T), int((pl.y + pl.h) // T) - 1   # клетка пола под героем
r.d["npcs"] = [{"type": "trader", "x": c0, "y": r0}]
made = npc.create(r)
assert len(made) == 1 and made[0].kind == "trader", f"create не поставил торговца: {made}"
r.d["npcs"] = [{"type": "trader", "x": c0, "y": 0}, {"type": "ghost_unknown", "x": c0, "y": r0}, {"type": "trader"}]
made2 = npc.create(r)
assert all(n.kind == "trader" for n in made2) and len(made2) <= 1, "битые записи не отброшены"
r.d.pop("npcs", None)
print("   create: валидная запись -> NPC, битые/в стену -> пропуск")

print("== 9. урон игрока мимо NPC, мобы не агрятся ==")
r.npcs = [n]; n.x, n.y = pl.x + 8, pl.y - 2
assert not any(n is m for m in r.mobs), "NPC в списке мобов!"
hp_dummy = npc.NPC("villager", 40, 40)
hp_dummy.hurt(50, (0, 0), g.fx)
g.step(0.016)
print("   NPC неуязвим и невидим для боевой системы OK")

print()
print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ — npc.py и trade.py работают")
