"""Дружественные NPC (npc.py): ходят по карте, драться с ними нельзя.

Что умеют:
  • мирные: игрок по ним не попадает (NPC не входят в списки целей ударов и пуль),
    мобы их не атакуют и не касаются — NPC просто гуляют по карте;
  • внешность задаётся ассетами: assets/npcs/<id>/npc.json + папки кадров idle/, move/
    или одиночный скин assets/npcs/<id>.png (нет файлов — рисуется цветная заглушка);
  • NPC с "trader": true — торговец: на E рядом с ним открывается окно торговли (trade.py).

Данные NPC: data/npcs.json -> "npcs": {id: {...}} — имя, описание, trader, скорость,
ассортимент и цены торговца. Расстановка NPC по карте — список "npcs" в JSON карты
([{"type": "trader", "x": 12, "y": 20}]), расставляется в редакторе карт (вкладка «NPC»).
"""
import random
import pygame as pg
from core import CFG, T, Body, read_json, ASSETS, approach, solid, free, floor_below
import anim
import inventory

GRAV = 1400.0            # гравитация NPC (как у мобов)
REACH = 46               # с какого расстояния работает E у торговца (px)
TYPE_PRICES = {"weapon": 80, "resource": 15, "head": 55, "neck": 55, "glove": 50,
               "belt": 40, "boot": 45, "artifact": 90}   # цена предмета без явного "price"
DEFAULT_PRICE = 45       # цена для типов, которых нет в TYPE_PRICES

DEFAULTS = {
    "name": "NPC", "description": "", "trader": False,
    "w": 20, "h": 34, "draw": None, "offset": [0, 0],
    "speed": 36, "walk_pause": [1.0, 2.5], "turn_prob": 0.12, "anim_fps": 6,
    "color": [200, 170, 120], "price_mult": 1.0, "assortment": [],
}


def defs():
    """Регистр NPC из data/npcs.json -> npcs (файл может отсутствовать)."""
    return (CFG.get("npcs") or {}).get("npcs") or {}


def type_def(tid):
    """Словарь NPC: DEFAULTS + assets/npcs/<id>/npc.json + запись из data/npcs.json
    (запись из data сильнее: данные игры правятся там, внешность — в ассетах)."""
    d = dict(DEFAULTS)
    d.update(read_json(ASSETS / "npcs" / tid / "npc.json", {}))
    d.update(defs().get(tid) or {})
    return d


# ================================================================ цены и ассортимент
def base_price(wid):
    """Базовая цена предмета: поле price (weapons.json / assets/inventory.json -> items),
    иначе по типу предмета (TYPE_PRICES, DEFAULT_PRICE)."""
    p = (CFG.get("weapons") or {}).get(wid, {}).get("price")
    if p is None:
        p = ((inventory.cfg().get("items") or {}).get(wid) or {}).get("price")
    if p is None:
        p = TYPE_PRICES.get(inventory.item_type(wid), DEFAULT_PRICE)
    try: p = float(p)
    except (TypeError, ValueError): p = DEFAULT_PRICE
    return max(1.0, p)


def sell_ratio():
    """Сколько монет возвращается при продаже (доля от цены), 0.05..1.0."""
    try: r = float((CFG.get("npcs") or {}).get("sell_ratio", 0.4))
    except (TypeError, ValueError): r = 0.4
    return max(0.05, min(1.0, r))


def price_of(wid, mult=1.0):
    """Цена покупки (у торговца свой множитель price_mult)."""
    return max(1, int(round(base_price(wid) * max(0.1, mult))))


def sell_price_of(wid):
    """Цена продажи: доля базовой цены (data/npcs.json -> sell_ratio)."""
    return max(1, int(round(base_price(wid) * sell_ratio())))


def is_tradable(wid):
    """Товар вообще можно торговать (монеты и другие «кошельковые» предметы — это деньги, не товар)."""
    return inventory.is_item(wid) and inventory.wallet_field(wid) is None


def all_items():
    """Все предметы игры, годные к торговле (для торговца без своего ассортимента)."""
    out, seen = [], set()
    for wid in list((CFG.get("weapons") or {}).keys()) + list((inventory.cfg().get("items") or {}).keys()):
        if wid not in seen and is_tradable(wid):
            seen.add(wid); out.append(wid)
    return sorted(out, key=lambda wid: inventory.item_info(wid)["name"].lower())


def trade_items(d):
    """Что продаёт торговец: свой ассортимент (data/npcs.json -> assortment, список id)
    или все предметы игры, если ассортимент не задан/пуст (сейчас все торговцы так торгуют)."""
    a = d.get("assortment")
    if not isinstance(a, list) or not [i for i in a if isinstance(i, str)]:
        return all_items()
    return [wid for wid in a if isinstance(wid, str) and is_tradable(wid)]


# ================================================================ NPC
class NPC(Body):
    """Мирный NPC. НЕ лежит в room.mobs — поэтому его нельзя ударить/застрелить,
    а мобы его не видят и не трогают: он просто гуляет."""
    def __init__(s, kind, x, y, d=None):
        s.kind = kind
        s.d = d if d is not None else type_def(kind)
        s.w = max(6, int(s.d.get("w", 20))); s.h = max(8, int(s.d.get("h", 34)))
        super().__init__(x, y, s.w, s.h)
        s.dir = -1; s.pause = 0.0; s.t = 0.0
        s.anim = "idle"; s.anim_t = 0.0

    @property
    def is_trader(s): return bool(s.d.get("trader"))

    def hurt(s, dmg, kb, fx):
        """NPC неуязвим: никакая атака/заглушка не может ему навредить (он и не в списках целей)."""
        pass

    # ---------- ходьба: патруль с паузами, разворот у стены и у обрыва
    def wall_ahead(s, g):
        x = s.cx + (s.w / 2 + 4) * (1 if s.dir > 0 else -1)
        return solid(g, int(x // T), int((s.y + s.h - 4) // T))

    def edge_ahead(s, g):
        """Впереди под ногами нет пола — разворот, чтобы не падать."""
        x = s.cx + (s.w / 2 + 2) * (1 if s.dir > 0 else -1)
        return floor_below(g, x, s.y + s.h - 2) is None

    def update(s, dt, room):
        g = room.g; d = s.d
        speed = max(0.0, float(d.get("speed", 36)))
        if s.pause > 0:
            s.pause -= dt
            s.vx = approach(s.vx, 0.0, 600 * dt)
            if s.pause <= 0 and random.random() < 0.5: s.dir = -s.dir
        else:
            s.vx = approach(s.vx, s.dir * speed, 600 * dt)
            if s.wall_ahead(g) or s.edge_ahead(g):
                s.dir = -s.dir; s.vx = 0.0
            elif random.random() < dt * max(0.0, float(d.get("turn_prob", 0.12))):
                p = d.get("walk_pause") or [1.0, 2.5]
                try: s.pause = random.uniform(float(p[0]), float(p[1]))
                except (TypeError, ValueError, IndexError): s.pause = 1.5
        s.vy = min(s.vy + GRAV * dt, 900.0)
        s.move(g, dt)
        s.update_anim(dt)

    def update_anim(s, dt):
        st = "move" if abs(s.vx) > 12 else "idle"
        if st != s.anim: s.anim = st; s.anim_t = 0.0
        else: s.anim_t += dt

    # ---------- отрисовка: скин из ассетов или цветная заглушка
    def draw(s, v):
        d = s.d
        dw, dh = d.get("draw") or [s.w + 6, s.h + 10]
        try: dw, dh = max(4, int(dw)), max(4, int(dh))
        except (TypeError, ValueError): dw, dh = s.w + 6, s.h + 10
        ox, oy = d.get("offset") or [0, 0]
        try: ox, oy = int(ox), int(oy)
        except (TypeError, ValueError): ox = oy = 0
        img = anim.sprite(anim.mob_frame(s.kind, d, [s.anim], s.anim_t, folder=f"npcs/{s.kind}"), dw, dh, s.dir < 0)
        r = s.rect
        if img is not None:
            v.blit(img, (int(r.centerx - dw / 2 + ox), int(r.bottom - dh + oy)))
        else:   # заглушка: цветной человечек с глазами, чтобы отличать NPC от ящиков
            col = tuple(max(0, min(255, int(c))) for c in (d.get("color") or (200, 170, 120))[:3])
            body = pg.Rect(0, 0, s.w, s.h - 8); body.bottomleft = r.bottomleft
            pg.draw.rect(v, col, body, border_radius=4)
            pg.draw.circle(v, col, (r.centerx, r.top + 6), 6)
            ex = r.centerx + (2 if s.dir > 0 else -2)
            pg.draw.circle(v, (34, 26, 22), (ex - 3, r.top + 5), 1)
            pg.draw.circle(v, (34, 26, 22), (ex + 3, r.top + 5), 1)


def update_room(room, dt):
    for n in getattr(room, "npcs", ()):
        n.update(dt, room)


def draw_room(v, room):
    for n in getattr(room, "npcs", ()):
        n.draw(v)


def draw_prompts(v, room, pl, font):
    """Имя над головой NPC, когда герой рядом; у торговца — подсказка [E]."""
    for n in getattr(room, "npcs", ()):
        if not n.rect.inflate(REACH * 2, 26).colliderect(pl.rect): continue
        label = str(n.d.get("name") or n.kind)
        if n.is_trader: label = "[E] " + label + ": торговать"
        img = font.render(label, True, (255, 230, 140) if n.is_trader else (215, 215, 230))
        v.blit(img, (int(n.cx - img.get_width() / 2), int(n.rect.top - 18)))


# ================================================================ расстановка из JSON карты
def create(room):
    """NPC комнаты из room.d["npcs"]: [{"type": id, "x": клетка, "y": клетка}].
    NPC ставится на пол этой клетки; в стену не ставится (запись пропускается)."""
    out = []
    for spec in room.d.get("npcs") or []:
        if not isinstance(spec, dict): continue
        tid = spec.get("type")
        if tid not in defs(): continue
        try: c, r = int(spec["x"]), int(spec["y"])
        except (KeyError, TypeError, ValueError): continue
        d = type_def(tid)
        w, h = max(6, int(d.get("w", 20))), max(8, int(d.get("h", 34)))
        x = c * T + (T - w) / 2
        bottom = (r + 1) * T
        gy = floor_below(room.g, x + w / 2, bottom - 2)
        y = (gy if gy is not None else bottom) - h
        if not free(room.g, pg.Rect(int(x), int(y), w, h)): continue
        out.append(NPC(tid, x, y, d))
    return out


# ================================================================ торговля (E рядом с торговцем)
def trader_near(room, pl):
    """Ближайший торговец рядом с героем (для подсказки и E), иначе None."""
    best = None
    for n in getattr(room, "npcs", ()):
        if not n.is_trader or not n.rect.inflate(REACH * 2, 26).colliderect(pl.rect): continue
        if best is None or abs(n.cx - pl.cx) < abs(best.cx - pl.cx): best = n
    return best


def try_trade(g, pl):
    """E у торговца: открыть окно торговли. False — торговца рядом нет (E сделает своё обычное)."""
    n = trader_near(g.room, pl)
    if n is None: return False
    if g.net:
        if pg.time.get_ticks() > getattr(g, "_npc_warn_t", 0):
            g._npc_warn_t = pg.time.get_ticks() + 1500
            g.fx.text("Торговля недоступна в сетевой игре", pl.cx, pl.y - 30)
        return False
    import trade
    trade.open(g, n)
    return True
