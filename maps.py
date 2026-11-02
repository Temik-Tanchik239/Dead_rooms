"""Карты, нарисованные вручную. Ничего не генерируется случайно.

data/maps.json      — порядок карт ("order"), общая легенда символов, общие настройки.
data/maps/<id>.json — одна карта: сетка произвольного размера ("rows"), фон, своя легенда, мобы, награда,
                      "pos": [x, y] — координата карты в СЕТКЕ МИРА (x вправо, y вниз), по ней работают выходы left/right/up/down.
Файлы, имя которых начинается с "_", игра не читает (например, _template.json — заготовка).

Каждый символ сетки — это клетка. Что значит символ, говорит легенда: общая (maps.json) + своя у карты (перекрывает).
Запись легенды — строка-тип ("wall") или словарь:
  type    — физика клетки: empty | wall | platform | ladder | spikes
  exit    — клетка-выход: "next" | "prev" (порядок order) | "back" (откуда пришёл) | id карты |
            "left" | "right" | "up" | "down" (соседняя карта по сетке мира, см. pos) | [x, y] (карта в этой клетке сетки)
  arrive  — (у выхода) символ, у которого появиться на целевой карте
  player  — true: точка старта игрока
  mob     — id моба из mobs.json или "random"\n  boss    — true: точка появления обычного босса (B) или Моргарта (C; boss_type=morgart)
  item    — id оружия или "random": оружие лежит на полу
  sprite  — картинка клетки из assets (иначе стандартная отрисовка типа), draw [w, h], offset [x, y], color [r, g, b]
  damage  — урон шипов
  light   — блок света: "torch" | "lantern" | "crystal" | "orb" или свой словарь (подробно — lighting.py)
"""
import math, random
import pygame as pg
from core import CFG, T, COLS, ROWS, MW
from anim import sprite, image
import weapon
import lighting
from mob import Mob, spawn_boss

END = "__end__"
PHYS = {"empty": ".", "wall": "#", "platform": "=", "ladder": "H", "spikes": "x"}
VH = ROWS * T   # высота игрового поля в пикселях
BACK = "__back__"
DIRS = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}
NAMES = {"left": "влево", "right": "вправо", "up": "вверх", "down": "вниз"}

def order(): return [m for m in CFG["maps"].get("order", []) if m in CFG["map_defs"]]

# ---------- сетка мира ----------
def pos_of(mid):
    """Координата карты в сетке мира (поле pos = [x, y]) или None."""
    p = CFG["map_defs"].get(mid, {}).get("pos")
    ok = isinstance(p, (list, tuple)) and len(p) == 2 and all(isinstance(v, int) and not isinstance(v, bool) for v in p)
    return (p[0], p[1]) if ok else None

def map_at(pos):
    """id карты, стоящей в клетке сетки pos, или None."""
    pos = tuple(pos)
    for mid in CFG["map_defs"]:
        if pos_of(mid) == pos: return mid
    return None

def valid_exit(ex, defs):
    if isinstance(ex, (list, tuple)): return len(ex) == 2
    return isinstance(ex, str) and (ex in ("next", "prev", "back", END) or ex in DIRS or ex in defs)

def target_of(cur, target):
    """Куда ведёт выход карты cur: id карты, END (конец), BACK (туда, откуда пришёл) или None (некуда)."""
    if isinstance(target, (list, tuple)): return map_at(target) if len(target) == 2 else None
    o = order()
    if target == "next":
        if cur not in o: return None
        i = o.index(cur) + 1; return o[i] if i < len(o) else END
    if target == "prev":
        if cur not in o: return None
        i = o.index(cur) - 1; return o[i] if i >= 0 else None
    if target == "back": return BACK
    if target == END: return END
    if isinstance(target, str) and target in DIRS:
        p = pos_of(cur)
        return map_at((p[0] + DIRS[target][0], p[1] + DIRS[target][1])) if p else None
    return target if isinstance(target, str) and target in CFG["map_defs"] else None

def used_exits(mid):
    """[(символ, значение exit)] у карты — только символы, которые реально нарисованы в сетке."""
    md = CFG["map_defs"][mid]; lg = legend_of(md); out = []
    for ch in sorted({c for row in md.get("rows", []) for c in row}):
        ex = lg.get(ch, {}).get("exit")
        if ex is not None: out.append((ch, ex))
    return out

def world_links():
    """Реальные переходы: множество пар (откуда, куда). 'back' зависит от прохождения и не учитывается."""
    out = set()
    for mid in CFG["map_defs"]:
        for ch, ex in used_exits(mid):
            t = target_of(mid, ex) if valid_exit(ex, CFG["map_defs"]) else None
            if t and t not in (END, BACK): out.add((mid, t))
    return out

def two_way(a, b):
    """Переход a→b двусторонний: на b есть выход обратно на a или выход 'back'."""
    return (b, a) in world_links() or any(target_of(b, ex) == BACK for _, ex in used_exits(b))

def world_text():
    """Сетка мира текстом (в консоль при запуске и F5)."""
    cells = {m: pos_of(m) for m in CFG["map_defs"] if pos_of(m)}
    if not cells: return "[сетка мира] ни у одной карты нет pos — впиши \"pos\": [x, y] в data/maps/<id>.json"
    xs, ys = [p[0] for p in cells.values()], [p[1] for p in cells.values()]; w = 15
    lines = ["[сетка мира]  x вправо, y вниз", "      " + "".join(f"x={x}".ljust(w) for x in range(min(xs), max(xs) + 1))]
    for y in range(min(ys), max(ys) + 1):
        row = f"y={y}".ljust(6)
        for x in range(min(xs), max(xs) + 1):
            m = map_at((x, y)); row += (f"[{m}]"[:w - 1] if m else "·").ljust(w)
        lines.append(row.rstrip())
    nop = [m for m in CFG["map_defs"] if m not in cells]
    if nop: lines.append("без pos: " + ", ".join(nop))
    return "\n".join(lines)

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

def random_weapon():
    """Случайное оружие из тех, что разрешены текущему персонажу (allowed_weapons в data/characters.json)."""
    allowed = CFG.get("character", {}).get("allowed_weapons")
    pool = [w for w in CFG["weapons"] if not allowed or w in allowed]
    return random.choice(pool or list(CFG["weapons"]))

class GameMap:
    def __init__(s, mid, scale=1.0):
        s.id = mid; s.d = md = CFG["map_defs"][mid]; s.name = md.get("name", mid); s.pos = pos_of(mid)
        s.scale = scale * md.get("difficulty", 1); s.legend = lg = legend_of(md)
        rows = md.get("rows", []); fill = md.get("fill", ".")
        # Сохраняем реальные границы карты отдельно от общей буферной сетки.
        s.width = max((len(row) for row in rows if isinstance(row, str)), default=COLS)
        s.height = len(rows) if rows else ROWS
        s.width_px, s.height_px = s.width * T, s.height * T
        s.chars = [[rows[r][c] if r < len(rows) and c < len(rows[r]) else fill for c in range(COLS)] for r in range(ROWS)]
        s.info = [[lg.get(ch, {"type": "empty"}) for ch in row] for row in s.chars]
        s.visited = s.cleared = s.spawned = s.locked = False
        s.mobs, s.corpses, s.drops = [], [], []
        s.boss_spawned = False
        for c, r, e in s.cells():
            if "item" in e:
                wid = random_weapon() if e["item"] == "random" else e["item"]
                if wid in CFG["weapons"]: s.drops.append(Drop(c * T + T / 2, (r + 1) * T - 14, wid))
        s.exits = s.find_exits()
        s.lights = lighting.find_lights(s)   # блоки света: факелы, фонари, кристаллы, сферы
        s.build()

    def cells(s):
        # Рисуем только реальные клетки этой карты, а не общую буферную сетку.
        for r in range(s.height):
            for c in range(s.width):
                yield c, r, s.info[r][c]

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
                    if 0 <= nx < s.width and 0 <= ny < s.height and (nx, ny) not in seen and s.chars[ny][nx] == ch:
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
        # Фон и геометрия создаются в фактическом размере карты.
        # Раньше использовался общий размер MW × VH (максимум по всем картам),
        # поэтому фон на карте 60×32 растягивался на высоту 50 клеток и камера
        # показывала неверно обрезанный/размытый участок.
        surf = pg.Surface((s.width_px, s.height_px)); md = s.d
        surf.fill(tuple(opt(md, "bg_color", [20, 18, 30])))
        bg = md.get("background")
        if bg: draw_background(surf, bg, opt(md, "bg_mode", "cover"))
        dim = opt(md, "bg_dim", 0)
        if dim:
            sh = pg.Surface(surf.get_size(), pg.SRCALPHA); sh.fill((0, 0, 0, int(255 * dim))); surf.blit(sh, (0, 0))
        tiles = dict(CFG["maps"].get("tiles", {})); tiles.update(md.get("tiles", {}))
        for c, r, e in s.cells():
            X, Y = c * T, r * T
            if s.g[r][c] == "D": draw_default(surf, "D", X, Y, None); continue
            # Все элементы окружения берутся из assets/environment. Если в легенде
            # задан sprite/tiles, он имеет приоритет; иначе выбираем вариант по координатам.
            spr = e.get("sprite") or tiles.get(e["type"])
            variants = {"wall": 3, "platform": 5, "ladder": 3, "spikes": 3}
            if not spr and e["type"] in variants:
                kind = e["type"]
                variant = (c * 7 + r * 11 + (c // 3) * 5) % variants[kind] + 1
                spr = f"environment/{kind}_{variant}.png" if kind != "spikes" else f"environment/spikes_{variant}.png"
            if spr:
                dw, dh = e.get("draw", [T, T]); ox, oy = e.get("offset", [0, 0])
                # Платформы и шипы занимают нижнюю часть клетки, сохраняя физику клетки.
                if not e.get("draw") and e["type"] == "platform": dw, dh = T, T
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
            # Символ прибытия может встречаться на карте несколько раз.
            # Нельзя объединять все такие клетки в один огромный прямоугольник:
            # выбираем отдельную связную группу, ближайшую к стороне входа.
            ch = via["arrive"]
            candidates, seen = [], set()
            for c, r, e in s.cells():
                if s.chars[r][c] != ch or (c, r) in seen:
                    continue
                stack, group = [(c, r)], []
                seen.add((c, r))
                while stack:
                    x, y = stack.pop(); group.append((x, y))
                    for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                        if (0 <= nx < s.width and 0 <= ny < s.height and
                                (nx, ny) not in seen and s.chars[ny][nx] == ch):
                            seen.add((nx, ny)); stack.append((nx, ny))
                candidates.append(group)
            if candidates:
                src_pos, dst_pos = pos_of(came_from), pos_of(s.id) if came_from else (None, None)
                edge = None
                if src_pos and dst_pos:
                    dx, dy = dst_pos[0] - src_pos[0], dst_pos[1] - src_pos[1]
                    if abs(dx) >= abs(dy) and dx: edge = "left" if dx > 0 else "right"
                    elif dy: edge = "top" if dy > 0 else "bottom"
                def arrival_score(group):
                    if edge == "left": return min(c for c, r in group) * 1000 + sum(r for c, r in group) / len(group)
                    if edge == "right": return (s.width - 1 - max(c for c, r in group)) * 1000 + sum(r for c, r in group) / len(group)
                    if edge == "top": return min(r for c, r in group) * 1000 + sum(c for c, r in group) / len(group)
                    if edge == "bottom": return (s.height - 1 - max(r for c, r in group)) * 1000 + sum(c for c, r in group) / len(group)
                    return min((c - s.width / 2) ** 2 + (r - s.height / 2) ** 2 for c, r in group)
                cells = min(candidates, key=arrival_score)
                return box(cells), any(s.info[r][c]["type"] == "ladder" for c, r in cells)
        if came_from:
            # Сначала используем явный обратный выход, если он задан в легенде.
            for z in s.exits:
                if camp.resolve(s.id, z["entry"]["exit"]) == came_from:
                    return z["rect"], z["ladder"]

            # Если на карте нет явного обратного выхода, определяем точку входа
            # по координатам карт в сетке мира. Это важно для карт с разным
            # размером: иначе игрок попадал в fallback-точку в центре уровня.
            src_pos, dst_pos = pos_of(came_from), pos_of(s.id)
            if src_pos and dst_pos:
                dx, dy = dst_pos[0] - src_pos[0], dst_pos[1] - src_pos[1]
                edge = None
                if abs(dx) >= abs(dy) and dx:
                    edge = "left" if dx > 0 else "right"
                elif dy:
                    edge = "top" if dy > 0 else "bottom"
                if edge:
                    if edge == "left": edge_cells = lambda c, r: c == 0
                    elif edge == "right": edge_cells = lambda c, r: c == s.width - 1
                    elif edge == "top": edge_cells = lambda c, r: r == 0
                    else: edge_cells = lambda c, r: r == s.height - 1
                    # Предпочитаем реальные выходы у нужного края.
                    edge_exits = [z for z in s.exits if any(edge_cells(c, r) for c, r in z["cells"])]
                    if edge_exits:
                        z = min(edge_exits, key=lambda z: min(
                            abs(c) + abs(r) if edge == "left" else
                            abs((s.width - 1) - c) + abs(r) if edge == "right" else
                            abs(r) + abs(c) if edge == "top" else
                            abs((s.height - 1) - r) + abs(c)
                            for c, r in z["cells"] if edge_cells(c, r)))
                        return z["rect"], z["ladder"]
                    # Если на краю нет помеченного выхода, всё равно появляемся
                    # у соответствующего края, а не в центре карты.
                    if edge == "left": c, r = 0, max(0, s.height - 3)
                    elif edge == "right": c, r = s.width - 1, max(0, s.height - 3)
                    elif edge == "top": c, r = max(0, s.width // 2), 0
                    else: c, r = max(0, s.width // 2), s.height - 1
                    return pg.Rect(c * T, r * T, T, T), False
        cells = s.find(lambda c, r, e: e.get("player"))
        if cells: c, r = cells[0]; return pg.Rect(c * T, r * T, T, T), s.info[r][c]["type"] == "ladder"
        return pg.Rect(s.width_px // 2 - T // 2, max(0, s.height_px - 2 * T), T, T), False

    # ---------- мобы ----------
    def spawn(s):
        s.spawned = True
        names = list(CFG["mobs"]); pool = s.d.get("mob_pool")
        if isinstance(pool, list): pool = {n: CFG["mobs"].get(n, {}).get("weight", 1) for n in pool}
        if not pool: pool = {n: CFG["mobs"][n].get("weight", 1) for n in names}
        pool = {n: w for n, w in pool.items() if n in CFG["mobs"]}
        for c, r, e in s.cells():
            if e.get("boss") and not s.boss_spawned:
                # B и C — два варианта маркера появления Моргарта; оба используют assets/boss/boss.json.
                boss = spawn_boss(s, s.scale, 1, (c * T + T / 2, (r + 1) * T))
                if boss:
                    s.mobs.append(boss)
                    s.boss_spawned = True
                continue
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
    sw, sh = surf.get_size()
    if mode == "stretch": surf.blit(sprite(path, sw, sh), (0, 0))
    elif mode == "tile":
        for y in range(0, sh, ih):
            for x in range(0, sw, iw): surf.blit(img, (x, y))
    elif mode == "center": surf.blit(img, ((sw - iw) // 2, (sh - ih) // 2))
    else:
        k = (max if mode != "fit" else min)(sw / iw, sh / ih); w, h = max(1, int(iw * k)), max(1, int(ih * k))
        surf.blit(sprite(path, w, h), ((sw - w) // 2, (sh - h) // 2))

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
    def order(s): return order()
    @property
    def first(s):
        st = CFG["maps"].get("start")
        return st if st in CFG["map_defs"] else (s.order[0] if s.order else next(iter(CFG["map_defs"]), None))
    def scale(s): return 1 + CFG["maps"].get("loop_scale", .2) * s.loop
    def get(s, mid):
        if mid not in s.maps: s.maps[mid] = GameMap(mid, s.scale())
        return s.maps[mid]
    def resolve(s, cur, target):
        """Куда ведёт выход: id карты, END (конец) или None (некуда). Направления left/right/up/down и [x, y] — по сетке мира."""
        t = target_of(cur, target)
        return s.came_from.get(cur) if t == BACK else t
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
    seen = {}   # сетка мира: pos должен быть [x, y], в одной клетке — одна карта
    for mid, md in defs.items():
        if "pos" in md and pos_of(mid) is None: out.append(f"{mid}: pos должен быть [x, y] — два целых числа")
        p = pos_of(mid)
        if p and p in seen: out.append(f"{mid} и {seen[p]} стоят в одной клетке сетки {list(p)}")
        elif p: seen[p] = mid
    for mid in CFG["maps"].get("order", []):
        if mid not in defs: out.append(f"order: нет файла data/maps/{mid}.json")
    if not CFG["maps"].get("order"): out.append("maps.json: пустой order")
    for mid, md in defs.items():
        rows, lg = md.get("rows", []), legend_of(md)
        if not isinstance(rows, list) or not rows:
            out.append(f"{mid}: карта не содержит rows")
            rows = []
        widths = [len(row) for row in rows if isinstance(row, str)]
        if len(widths) != len(rows): out.append(f"{mid}: rows должны содержать только строки")
        if widths and min(widths) != max(widths):
            out.append(f"{mid}: строки карты имеют разную длину (будут дополнены пустыми клетками)")
        bad = sorted({ch for row in rows for ch in row if ch not in lg})
        if bad: out.append(f"{mid}: нет в легенде символов {' '.join(bad)} (будут пустотой)")
        for ch, e in lg.items():
            if e["type"] not in PHYS: out.append(f"{mid}: '{ch}' — неизвестный type {e['type']}")
            if e.get("mob") not in (None, "random") and e["mob"] not in CFG["mobs"]: out.append(f"{mid}: '{ch}' — нет моба {e['mob']}")
            if e.get("boss") and "__boss__" not in CFG.get("mobs", {}): out.append(f"{mid}: '{ch}' — не настроен босс (__boss__ в data/mobs.json)")
            if e.get("item") not in (None, "random") and e["item"] not in CFG["weapons"]: out.append(f"{mid}: '{ch}' — нет оружия {e['item']}")
            ex = e.get("exit")
            if ex is not None and not valid_exit(ex, defs): out.append(f"{mid}: '{ch}' ведёт на несуществующую карту {ex}")
            if e.get("light") is not None and not lighting.preset(e["light"]): out.append(f"{mid}: '{ch}' — нет света {e['light']} (см. lights в data/maps.json)")
            li = e.get("light")
            if isinstance(li, dict) and "color" in li and lighting.color_of(li["color"]) is None:
                out.append(f"{mid}: '{ch}' — непонятный цвет света {li['color']} (пример: \"красный\", \"green\", [255, 80, 40], \"#ff8040\")")
        for key in ("background",):
            if md.get(key) and not image(md[key]): out.append(f"{mid}: нет картинки assets/{md[key]}")
    for mid in defs:   # переходы: ведут ли выходы куда надо и есть ли выход обратно
        for ch, ex in used_exits(mid):
            if not valid_exit(ex, defs): continue
            t = target_of(mid, ex)
            if t is None:
                if isinstance(ex, str) and ex in DIRS:
                    p = pos_of(mid)
                    out.append(f"{mid}: выход '{ch}' ({NAMES[ex]}) — " + ("у карты нет pos" if not p else f"в клетке {[p[0] + DIRS[ex][0], p[1] + DIRS[ex][1]]} нет карты"))
                elif isinstance(ex, (list, tuple)): out.append(f"{mid}: выход '{ch}' — в клетке {list(ex)} нет карты")
            elif t not in (END, BACK) and not any(target_of(t, e2) in (mid, BACK) for _, e2 in used_exits(t) if valid_exit(e2, defs)):
                out.append(f"{mid} → {t}: на карте {t} нет выхода обратно на {mid} (игрок появится у символа P)")
    return out
