"""Карты, нарисованные вручную. Ничего не генерируется случайно.

data/maps.json      — порядок карт ("order"), общая легенда символов, общие настройки.
data/maps/<id>.json — одна карта: сетка 30 x 16 символов ("rows"), фон, своя легенда, мобы, награда.
Файлы, имя которых начинается с "_", игра не читает (например, _template.json — заготовка).

Каждый символ сетки — это клетка. Что значит символ, говорит легенда: общая (maps.json) + своя у карты (перекрывает).
Запись легенды — строка-тип ("wall") или словарь:
  type    — физика клетки: empty | wall | platform | ladder | spikes
  exit    — клетка-выход: "next" | "prev" | "back" (откуда пришёл) | id карты
  arrive  — (у выхода) символ, у которого появиться на целевой карте
  player  — true: точка старта игрока
  mob     — id моба из mobs.json или "random"
  item    — id оружия или "random": оружие лежит на полу
  sprite  — картинка клетки из assets (иначе стандартная отрисовка типа), draw [w, h], offset [x, y], color [r, g, b]
  damage  — урон шипов
"""
import math, random
import pygame as pg
from core import CFG, T, COLS, ROWS, W
from anim import sprite, image
import weapon
from mob import Mob

END = "__end__"
PHYS = {"empty": ".", "wall": "#", "platform": "=", "ladder": "H", "spikes": "x"}
VH = ROWS * T   # высота игрового поля в пикселях

def norm(v):
    """Запись легенды -> словарь с полем type."""
    v = {"type": v} if isinstance(v, str) else dict(v)
    v.setdefault("type", "empty")
    return v

def legend_of(md):
    lg = {k: norm(v) for k, v in CFG["maps"].get("legend", {}).items()}
    lg.update({k: norm(v) for k, v in md.get("legend", {}).items()})
    return lg

def opt(md, key, default=None):
    """Настройка карты, если нет — из общих настроек maps.json."""
    return md.get(key, CFG["maps"].get(key, default))

class Drop:
    """Оружие на полу."""
    def __init__(s, x, y, wid): s.x, s.y, s.wid = x, y, wid
    def draw(s, v):
        bob = math.sin(pg.time.get_ticks() / 300) * 3
        if not weapon.icon(v, s.wid, s.x, s.y - 12 + bob, 36, 30):
            pg.draw.polygon(v, (255, 220, 90), [(s.x, s.y - 8), (s.x + 8, s.y), (s.x, s.y + 8), (s.x - 8, s.y)])

def random_weapon(): return random.choice(list(CFG["weapons"]))

class GameMap:
    def __init__(s, mid, scale=1.0):
        s.id = mid; s.d = md = CFG["map_defs"][mid]; s.name = md.get("name", mid)
        s.scale = scale * md.get("difficulty", 1); s.legend = lg = legend_of(md)
        rows = md.get("rows", []); fill = md.get("fill", ".")
        s.chars = [[rows[r][c] if r < len(rows) and c < len(rows[r]) else fill for c in range(COLS)] for r in range(ROWS)]
        s.info = [[lg.get(ch, {"type": "empty"}) for ch in row] for row in s.chars]
        s.visited = s.cleared = s.spawned = s.locked = False
        s.mobs, s.corpses, s.drops = [], [], []
        for c, r, e in s.cells():
            if "item" in e:
                wid = random_weapon() if e["item"] == "random" else e["item"]
                if wid in CFG["weapons"]: s.drops.append(Drop(c * T + T / 2, (r + 1) * T - 14, wid))
        s.exits = s.find_exits()
        s.build()

    def cells(s):
        for r in range(ROWS):
            for c in range(COLS): yield c, r, s.info[r][c]

    def find(s, test):
        return [(c, r) for c, r, e in s.cells() if test(c, r, e)]

    def find_exits(s):
        """Выходы = связные группы одинаковых символов с полем exit."""
        seen, zones = set(), []
        for c, r, e in s.cells():
            if "exit" not in e or (c, r) in seen: continue
            ch = s.chars[r][c]; stack, group = [(c, r)], []
            seen.add((c, r))
            while stack:
                x, y = stack.pop(); group.append((x, y))
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < COLS and 0 <= ny < ROWS and (nx, ny) not in seen and s.chars[ny][nx] == ch:
                        seen.add((nx, ny)); stack.append((nx, ny))
            zones.append(dict(char=ch, entry=e, cells=set(group), rect=box(group), ladder=e["type"] == "ladder"))
        return zones

    def build(s):
        """Физическая сетка (символы # = H x . D, их понимают игрок, мобы и пули) + картинка карты."""
        s.g = [[PHYS.get(e["type"], ".") for e in row] for row in s.info]
        if s.locked:
            for z in s.exits:
                for c, r in z["cells"]: s.g[r][c] = "D"
        s.layer = s.render()

    # ---------- отрисовка ----------
    def render(s):
        surf = pg.Surface((W, VH)); md = s.d
        surf.fill(tuple(opt(md, "bg_color", [20, 18, 30])))
        bg = md.get("background")
        if bg: draw_background(surf, bg, opt(md, "bg_mode", "cover"))
        dim = opt(md, "bg_dim", 0)
        if dim:
            sh = pg.Surface((W, VH), pg.SRCALPHA); sh.fill((0, 0, 0, int(255 * dim))); surf.blit(sh, (0, 0))
        tiles = dict(CFG["maps"].get("tiles", {})); tiles.update(md.get("tiles", {}))
        for c, r, e in s.cells():
            X, Y = c * T, r * T
            if s.g[r][c] == "D": draw_default(surf, "D", X, Y, None); continue
            spr = e.get("sprite") or tiles.get(e["type"])
            if spr:
                dw, dh = e.get("draw", [T, T]); ox, oy = e.get("offset", [0, 0])
                img = sprite(spr, dw, dh, e.get("flip", False))
                if img: surf.blit(img, (X + ox, Y + T - dh + oy)); continue
            draw_default(surf, s.g[r][c], X, Y, e.get("color"))
        return surf

    # ---------- выходы и прибытие ----------
    def exit_at(s, x, y):
        c, r = int(x // T), int(y // T)
        for z in s.exits:
            if (c, r) in z["cells"]: return z
        return None

    def exit_touch(s, rect):
        return any(z["rect"].colliderect(rect) for z in s.exits)

    def exit_near(s, rect):
        for z in s.exits:
            if z["rect"].inflate(T * 2, T * 2).colliderect(rect): return z
        return None

    def arrival(s, came_from, via, camp):
        """Где появиться: (прямоугольник, на лестнице ли)."""
        if via and via.get("arrive"):
            cells = s.find(lambda c, r, e: s.chars[r][c] == via["arrive"])
            if cells: return box(cells), any(s.info[r][c]["type"] == "ladder" for c, r in cells)
        if came_from:
            for z in s.exits:
                if camp.resolve(s.id, z["entry"]["exit"]) == came_from: return z["rect"], z["ladder"]
        cells = s.find(lambda c, r, e: e.get("player"))
        if cells: c, r = cells[0]; return pg.Rect(c * T, r * T, T, T), s.info[r][c]["type"] == "ladder"
        return pg.Rect(W // 2 - T // 2, VH - 2 * T, T, T), False

    # ---------- мобы ----------
    def spawn(s):
        s.spawned = True
        names = list(CFG["mobs"]); pool = s.d.get("mob_pool")
        if isinstance(pool, list): pool = {n: CFG["mobs"].get(n, {}).get("weight", 1) for n in pool}
        if not pool: pool = {n: CFG["mobs"][n].get("weight", 1) for n in names}
        pool = {n: w for n, w in pool.items() if n in CFG["mobs"]}
        for c, r, e in s.cells():
            kind = e.get("mob")
            if not kind: continue
            if kind == "random":
                if not pool: continue
                kind = random.choices(list(pool), list(pool.values()))[0]
            if kind not in CFG["mobs"]: continue
            d = CFG["mobs"][kind]
            s.mobs.append(Mob(kind, c * T + (T - d["w"]) / 2, r * T + T - d["h"], s.scale))
        if not s.mobs: s.cleared = True

    def set_lock(s, on):
        if s.locked != on: s.locked = on; s.build()

    def spike_damage(s, c, r):
        return s.info[r][c].get("damage", 10) if 0 <= c < COLS and 0 <= r < ROWS else 10

def box(cells):
    xs = [c for c, _ in cells]; ys = [r for _, r in cells]
    return pg.Rect(min(xs) * T, min(ys) * T, (max(xs) - min(xs) + 1) * T, (max(ys) - min(ys) + 1) * T)

def draw_background(surf, path, mode):
    """mode: cover — растянуть с сохранением пропорций и обрезать (по умолчанию), stretch — растянуть как есть,
    fit — вписать целиком, center — как есть по центру, tile — замостить."""
    img = image(path)
    if not img: return
    iw, ih = img.get_size()
    if mode == "stretch": surf.blit(sprite(path, W, VH), (0, 0))
    elif mode == "tile":
        for y in range(0, VH, ih):
            for x in range(0, W, iw): surf.blit(img, (x, y))
    elif mode == "center": surf.blit(img, ((W - iw) // 2, (VH - ih) // 2))
    else:
        k = (max if mode != "fit" else min)(W / iw, VH / ih); w, h = max(1, int(iw * k)), max(1, int(ih * k))
        surf.blit(sprite(path, w, h), ((W - w) // 2, (VH - h) // 2))

def draw_default(v, ch, X, Y, color):
    col = tuple(color) if color else None
    if ch == "#": pg.draw.rect(v, col or (62, 56, 84), (X, Y, T, T)); pg.draw.rect(v, (88, 80, 114) if not col else [min(255, k + 26) for k in col], (X, Y, T, 4))
    elif ch == "D": pg.draw.rect(v, (160, 60, 70), (X, Y, T, T)); pg.draw.line(v, (90, 30, 40), (X, Y), (X + T, Y + T), 3)
    elif ch == "=": pg.draw.rect(v, col or (150, 120, 80), (X, Y, T, 8))
    elif ch == "H":
        for lx in (8, 24): pg.draw.line(v, col or (150, 110, 70), (X + lx, Y), (X + lx, Y + T), 3)
        for ly in (6, 22): pg.draw.line(v, col or (150, 110, 70), (X + 8, Y + ly), (X + 24, Y + ly), 2)
    elif ch == "x": pg.draw.polygon(v, col or (200, 200, 215), [(X + 2, Y + T), (X + 16, Y + T - 18), (X + 30, Y + T)])
    elif col: pg.draw.rect(v, col, (X, Y, T, T))

class Campaign:
    """Прохождение: какие карты уже созданы, откуда пришли, круг (после последней карты — заново и сложнее)."""
    def __init__(s, loop=0):
        s.loop = loop; s.maps = {}; s.came_from = {}
    @property
    def order(s): return [m for m in CFG["maps"].get("order", []) if m in CFG["map_defs"]]
    @property
    def first(s):
        st = CFG["maps"].get("start")
        return st if st in CFG["map_defs"] else (s.order[0] if s.order else next(iter(CFG["map_defs"]), None))
    def scale(s): return 1 + CFG["maps"].get("loop_scale", .2) * s.loop
    def get(s, mid):
        if mid not in s.maps: s.maps[mid] = GameMap(mid, s.scale())
        return s.maps[mid]
    def resolve(s, cur, target):
        """Куда ведёт выход: id карты, END (конец) или None (некуда)."""
        o = s.order
        if target == "next":
            if cur not in o: return None
            i = o.index(cur) + 1; return o[i] if i < len(o) else END
        if target == "prev":
            if cur not in o: return None
            i = o.index(cur) - 1; return o[i] if i >= 0 else None
        if target == "back": return s.came_from.get(cur)
        if target == END: return END
        return target if target in CFG["map_defs"] else None
    def reload(s):
        """F5: карты пересобираются из файлов, зачищенные остаются зачищенными."""
        old = s.maps; s.maps = {}
        for mid, m in old.items():
            if mid not in CFG["map_defs"]: continue
            n = s.get(mid); n.visited = m.visited
            if m.cleared: n.cleared = n.spawned = True; n.drops = m.drops if m.spawned else n.drops

def check():
    """Проверка всех карт: список предупреждений (выводятся в консоль и на экран при запуске и F5)."""
    out, defs = list(CFG.get("map_errors", [])), CFG["map_defs"]
    for mid in CFG["maps"].get("order", []):
        if mid not in defs: out.append(f"order: нет файла data/maps/{mid}.json")
    if not CFG["maps"].get("order"): out.append("maps.json: пустой order")
    for mid, md in defs.items():
        rows, lg = md.get("rows", []), legend_of(md)
        if len(rows) != ROWS: out.append(f"{mid}: строк {len(rows)}, нужно {ROWS}")
        for i, row in enumerate(rows):
            if len(row) != COLS: out.append(f"{mid}: строка {i} длиной {len(row)}, нужно {COLS}")
        bad = sorted({ch for row in rows for ch in row if ch not in lg})
        if bad: out.append(f"{mid}: нет в легенде символов {' '.join(bad)} (будут пустотой)")
        for ch, e in lg.items():
            if e["type"] not in PHYS: out.append(f"{mid}: '{ch}' — неизвестный type {e['type']}")
            if e.get("mob") not in (None, "random") and e["mob"] not in CFG["mobs"]: out.append(f"{mid}: '{ch}' — нет моба {e['mob']}")
            if e.get("item") not in (None, "random") and e["item"] not in CFG["weapons"]: out.append(f"{mid}: '{ch}' — нет оружия {e['item']}")
            ex = e.get("exit")
            if ex and ex not in ("next", "prev", "back", END) and ex not in defs: out.append(f"{mid}: '{ch}' ведёт на несуществующую карту {ex}")
        for key in ("background",):
            if md.get(key) and not image(md[key]): out.append(f"{mid}: нет картинки assets/{md[key]}")
    return out
