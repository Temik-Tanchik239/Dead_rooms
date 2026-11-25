"""Лут с мобов: предметы и монеты (data/mobs.json, настраивается во вкладке «Лут» редактора мобов).

На каждом мобе (ключей нет — лута нет, старые мобы не меняются):
  "loot":  [{"item": "fire_flask", "chance": 0.2}, {"item": "random", "chance": 0.05}, ...]
           — записи {item, chance}: при смерти моба каждая бросается ОТДЕЛЬНО (chance 0..1).
             item — id оружия (data/weapons.json), предмета (assets/inventory.json -> items)
             или "random" — случайное оружие из разрешённых герою (maps.random_weapon).
  "coins": {"chance": 0.6, "min": 1, "max": 5}
           — кучка монет: шанс выпадения (0..1) и размер — случайное целое от min до max
             (min/max нет — 1).

Как это работает в игре: в момент смерти моба main.step (одиночка) или кадр комнаты хоста
(multiplayer.py) зовут drop_for_mob — кучки монет (loot.Coin) падают в r.drops комнаты и рисуются
общим циклом дропов (dr.draw(v)). Монета — полноценный предмет инвентаря (assets/inventory.json ->
items.coin): на полу она лежит НА земле и крутится на ребре (floor-анимация "spin" предмета),
при подборе касанием счётчик растёт (pl.coins) и в рюкзаке появляется ячейка «coin» со стопкой
(inventory.ensure_stack; сам счётчик — pl.coins: HUD-бейдж, сейв "coins", сеть "cn"). Выброс
ячейки (X) роняет ВСЮ стопку кучкой (inventory.drop). Предметы (maps.Drop) тоже лежат на земле;
«анимация лежания» задаётся у предмета полем floor (inventory.draw_floor).

Сериализация монет: строки ["C", x, y, n] в _drops_snapshot/_restore_drops (save_io.py).
"""
import math, random
import pygame as pg
from core import CFG
from maps import Drop, ground_y, random_weapon
import inventory

COIN, COIN_D, COIN_L = (255, 205, 80), (168, 120, 32), (255, 244, 190)   # золото: заливка, обод, блик (фолбэк без текстуры)
COIN_ITEM = "coin"                                                       # id предмета-монеты (assets/inventory.json)
PICK_R = 26                                                              # радиус подбора монеты касанием, px


class Coin:
    """Кучка монет на полу (n штук): предмет «coin» лежит на земле и крутится на ребре
    (floor-анимация из inventory.json); при n >= 3 рядом лежат соседние монеты плашмя."""
    def __init__(s, x, y, n):
        s.x, s.y = float(x), float(y); s.n = max(1, int(n))

    def draw(s, v):
        if inventory.draw_floor(v, COIN_ITEM, s.x, s.y):   # крутится на ребре, низ — на земле
            if s.n >= 3:   # кучка: соседние монеты лежат рядом плашмя
                img = inventory._icon(COIN_ITEM, 16)
                if img:
                    v.blit(img, img.get_rect(midbottom=(int(s.x) - 12, int(s.y))))
                    if s.n >= 8: v.blit(img, img.get_rect(midbottom=(int(s.x) + 11, int(s.y) - 2)))
            return
        bob = math.sin(pg.time.get_ticks() / 260 + s.x * 0.07) * 2.5
        x, y = int(s.x), int(s.y - 6 + bob)   # фолбэк без текстуры: золото на земле
        if s.n > 1:   # вторая монета за основной — намёк на кучку
            pg.draw.circle(v, COIN_D, (x - 4, y - 4), 5)
            pg.draw.circle(v, COIN, (x - 4, y - 4), 4)
        pg.draw.circle(v, COIN_D, (x, y), 6)
        pg.draw.circle(v, COIN, (x, y), 5)
        pg.draw.circle(v, COIN_L, (x - 2, y - 2), 1)


def item_ids(data_dir=None):
    """Все id предметов для лута: «random» + оружие (data/weapons.json) + предметы (assets/inventory.json -> items)."""
    from pathlib import Path
    data_dir = Path(data_dir) if data_dir else Path(__file__).resolve().parent / "data"
    out, seen = ["random"], {"random"}
    for path, key in ((data_dir / "weapons.json", None), (data_dir.parent / "assets" / "inventory.json", "items")):
        try:
            import json as _json
            data = _json.loads(path.read_text(encoding="utf-8"))
            ids = list(data) if key is None else list((data.get(key) or {}))
        except Exception:
            continue
        for i in ids:
            if isinstance(i, str) and i and i not in seen:
                seen.add(i); out.append(i)
    return out


def roll(d):
    """Бросок лута по данным моба d -> (список id предметов, монет). Незнакомые id и «random» без пула отсеиваются."""
    items = []
    for e in d.get("loot") or ():
        if not isinstance(e, dict): continue
        try: ch = float(e.get("chance", 1.0))
        except (TypeError, ValueError): ch = 1.0
        if random.random() >= min(1.0, max(0.0, ch)): continue
        iid = e.get("item")
        if iid == "random": iid = random_weapon()
        if iid and inventory.is_item(iid): items.append(iid)
    cd = d.get("coins") if isinstance(d.get("coins"), dict) else None
    n = 0
    if cd:
        try: ch = float(cd.get("chance", 0.0))
        except (TypeError, ValueError): ch = 0.0
        if random.random() < min(1.0, max(0.0, ch)):
            try: lo = max(1, int(cd.get("min", 1)))
            except (TypeError, ValueError): lo = 1
            try: hi = max(lo, int(cd.get("max", lo)))
            except (TypeError, ValueError): hi = lo
            n = random.randint(lo, hi)
    return items, n


def drop_for_mob(r, m, fx=None):
    """Смерть моба m: сыпем его лут на пол комнаты r. Зовётся ОДИН раз на моба (внутри блока xp_paid
    в main.step / кадре комнаты хоста) — повторных выпадений нет. fx не используется, оставлен для симметрии."""
    items, n = roll(m.d)
    x, y = m.cx, ground_y(r, m.cx, m.y + m.h)   # лут ложится на пол под мобом (не в воздухе)
    for i, iid in enumerate(items):   # предметы в ряд, чтобы не сливались в одну точку
        r.drops.append(Drop(x + (i - (len(items) - 1) / 2.0) * 24, y, iid))
    if n: r.drops.append(Coin(x, y - 2, n))   # кучка монет чуть позади предметов


def update_room(r, pl, fx=None):
    """Подбор монет касанием (каждый кадр для игрока в его комнате): pl.coins += n, подсказка fx.text."""
    keep, took = [], 0
    for dr in r.drops:
        if isinstance(dr, Coin) and pg.Rect(int(dr.x) - PICK_R, int(dr.y) - PICK_R, PICK_R * 2, PICK_R * 2).colliderect(pl.rect):
            took += dr.n
            if fx is not None: fx.text(f"+{dr.n}", dr.x, dr.y - 26)
        else:
            keep.append(dr)
    if took:
        r.drops = keep
        pl.coins = int(getattr(pl, "coins", 0)) + took
        inventory.ensure_stack(pl, COIN_ITEM)   # ячейка «монеты» в рюкзаке (счётчик штабеля — pl.coins)
