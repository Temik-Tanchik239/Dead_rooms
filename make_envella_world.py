# -*- coding: utf-8 -*-
"""
Генератор мира «Энвелла» — большая связанная карта из десятков локаций в духе
мультсериала «Герои Энвелла»: таверна → склепы → пещеры → руины → кристальные
гроты → канализация → замок → логово Моргарта (финальный босс).

Каждая сгенерированная карта — валидный data/maps/env_*.json (см. maps.check():
все символы в легенде, парные выходы в обе стороны, правильные pos). Символы —
только из общей легенды maps.json, отдельные легенды не нужны.

Запуск:  .venv/Scripts/python.exe make_envella_world.py
  - пишет карты data/maps/env_*.json (кроме старых — не перезаписывает старые файлы);
  - старые карты (не env_*, не _*) переносит в data/maps/_legacy/ (их игра не читает).
  - правит data/maps.json: start, order, world.reveal.
"""
import json
import random
import shutil
from pathlib import Path

BASE = Path(__file__).resolve().parent
MAPS = BASE / "data" / "maps"
MAPS_JSON = BASE / "data" / "maps.json"
NAME = "env_"  # префикс карт мира Энвеллы

# Прибитая «эталонная» палитра биомов.
BIOMES = {
    "tavern": dict(name="Таверна «Энвелла»", bg="backgrounds/bricks_tile.png", dark=0.45,
                   lights=("o", "*", "o"), decor=("candle", "lantern", "fence"),
                   mobs=("b", "b", "r"), mood=(210, 170, 120)),
    "crypt":  dict(name="Склеп", bg="backgrounds/crypt.png", dark=0.72,
                   lights=("*", "o", "*"), decor=("bone", "skull", "cobweb", "shards"),
                   mobs=("r", "r", "c", "g"), mood=(110, 110, 130)),
    "cave":   dict(name="Пещеры", bg="backgrounds/cave.png", dark=0.68,
                   lights=("%", "o", "%"), decor=("moss", "pebbles", "crack"),
                   mobs=("w", "b", "r"), mood=(95, 110, 90)),
    "ruins":  dict(name="Древние руины", bg="backgrounds/ruins.png", dark=0.62,
                   lights=("o", "*"), decor=("shards", "crack", "bone"),
                   mobs=("g", "h", "c"), mood=(145, 120, 85)),
    "crystal":dict(name="Кристальные гроты", bg="backgrounds/crystal.png", dark=0.58,
                   lights=("+", "%", "+"), decor=("pebbles", "lantern", "crack"),
                   mobs=("w", "a", "h"), mood=(115, 150, 205)),
    "canal":  dict(name="Канализация", bg="backgrounds/canalisacia.png", dark=0.68,
                   lights=("o", "o"), decor=("moss", "chain", "crack"),
                   mobs=("l", "b", "w"), mood=(95, 120, 110)),
    "castle": dict(name="Замок Энвеллы", bg="backgrounds/crypt.png", dark=0.74,
                   lights=("*", "o", "*"), decor=("candle", "chain", "skull"),
                   mobs=("g", "h", "c", "a"), mood=(135, 110, 120)),
    "boss":   dict(name="Логово Моргарта", bg="backgrounds/crystal.png", dark=0.82,
                   lights=("%", "%"), decor=("candle", "chain", "skull"),
                   mobs=("a", "a"), mood=(150, 80, 165)),
}

# Сетка мира: (x, y) -> id биома. Связи — по 4-соседству.
WORLD = {
    # стартовая таверна в центре
    (7, 0): "tavern",
    # ---- юг: склепы, канализация, кристальные гроты, пещеры ----
    (7, 1): "crypt", (6, 1): "crypt", (8, 1): "canal",
    (7, 2): "crystal", (8, 2): "crystal", (9, 2): "crystal",
    (6, 2): "cave",
    # ---- север: замок → логово Моргарта (финал) ----
    (7, -1): "castle", (8, -1): "castle",
    (7, -2): "castle", (8, -2): "castle", (9, -2): "boss",
    # ---- восток: руины → пещеры → канализация ----
    (8, 0): "ruins", (9, 0): "ruins",
    (10, 0): "cave", (11, 0): "cave",
    (12, 0): "canal", (13, 0): "canal",
    (10, 1): "crypt", (11, 1): "canal",
    # ---- запад: склепы, пещеры, кристальные гроты, руины ----
    (6, 0): "crypt", (5, 0): "cave", (4, 0): "crystal",
    (5, 1): "ruins",
}

START = (7, 0)      # точка входа в игру на карте-таверне
BOSS = (9, -2)      # карта с маркером Моргарта (C)

N = 50  # размер карты (50x50, как стандартные)


def _new():
    return [["." for _ in range(N)] for _ in range(N)]


def _set(g, x, y, ch):
    if 0 <= x < N and 0 <= y < N:
        g[y][x] = ch


def gen_biome(bio, rng):
    """Внутренности карты биома: земля, платформы, ямы, шипы, свет, мобы, предметы."""
    g = _new()
    # сплошные стены-границы
    for i in range(N):
        g[0][i] = g[N - 1][i] = "#"
        g[i][0] = g[i][N - 1] = "#"
    # земля: ряды 46-48 (поверхность ходьбы — ряд 45 открыт, под ним сплошь)
    for r in range(N - 4, N - 1):
        for c in range(1, N - 1):
            g[r][c] = "#"
    # неровности земли (небольшие ямы/ступени)
    for c in range(3, N - 3, 9):
        if rng.random() < 0.5:
            g[N - 4][c] = "."
    # яма с шипами
    if rng.random() < 0.7:
        sx = rng.randint(6, N - 10)
        for i in range(rng.randint(4, 6)):
            g[N - 4][sx + i] = "x"
    # платформы наверху
    for _ in range(rng.randint(3, 5)):
        y = rng.randint(10, 36)
        w = rng.randint(4, 8)
        x = rng.randint(2, N - 3 - w)
        for i in range(w):
            g[y][x + i] = "="
    # лёгкие ступеньки
    for _ in range(rng.randint(1, 3)):
        y = rng.randint(5, 16)
        x = rng.randint(2, N - 4)
        g[y][x] = "="
        g[y][x + 1] = "="
    # мобы
    for ch in bio["mobs"]:
        for _ in range(rng.randint(1, 2)):
            for _try in range(20):
                x = rng.randint(2, N - 3)
                y = rng.randint(20, N - 6)
                if g[y][x] == ".":
                    g[y][x] = ch
                    break
    # пара случайных мобов
    for _ in range(rng.randint(1, 2)):
        for _try in range(20):
            x = rng.randint(2, N - 3)
            y = rng.randint(20, N - 6)
            if g[y][x] == ".":
                g[y][x] = "S"
                break
    # оружие на полу
    for _ in range(rng.randint(1, 2)):
        g[N - 4][rng.randint(3, N - 4)] = "?"
    # факелы/светильники на стенах (высокие клетки)
    for i, li in enumerate(bio["lights"]):
        ly = rng.randint(2, 20)
        _set(g, 2 + i, ly, li)
        _set(g, N - 3 - i, N - 1 - (i % 3) - 3, li)
    # старт игрока (запасной, если нет обратного выхода)
    g[N - 5][N // 2 - 1] = "P"
    return g


def place_exits(g, ex):
    """ex: set направлений 'L','R','U','D'. Горизонтальные — на полу (ряд 45),
    вертикальные — лестницы в колонке 25 + проём сверху/снизу."""
    row = N - 5                 # 45 — поверхность ходьбы
    col = N // 2                # 25 — колонка лестниц
    if "L" in ex:
        g[row][0] = "L"; g[row][1] = "."; g[row + 1][1] = "."
        g[row - 1][0] = "#"; g[row + 1][0] = "#"
    if "R" in ex:
        g[row][N - 1] = "R"; g[row][N - 2] = "."; g[row + 1][N - 2] = "."
        g[row - 1][N - 1] = "#"; g[row + 1][N - 1] = "#"
    # лестница (вертикальные переходы)
    has_v = ("U" in ex) or ("D" in ex)
    if has_v:
        for r in range(1, N - 2):
            g[r][col] = "H"
    if "U" in ex:
        for dc in (-1, 0, 1):
            g[0][col + dc] = "U"
    if "D" in ex:
        g[N - 1][col] = "D"
        g[N - 2][col] = "."
        g[N - 3][col] = "H"


def build_world():
    """Главный проход: строим все карты и порядок BFS от таверны."""
    rng = random.Random(20241114)
    seen = {}
    for coord, bio_id in WORLD.items():
        mid = f"{NAME}{coord[0]}_{coord[1]}"
        seen[coord] = (mid, bio_id)

    # порядок прохождения: BFS от таверны (экспансия наружу)
    order = []
    q, visited = [START], {START}
    while q:
        c = q.pop(0)
        order.append(seen[c][0])
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nb = (c[0] + dx, c[1] + dy)
            if nb in seen and nb not in visited:
                visited.add(nb)
                q.append(nb)
    # логово Моргарта — финал: ставим в конец order (после зачистки мира появляется босс)
    boss_id = f"{NAME}{BOSS[0]}_{BOSS[1]}"
    if boss_id in order:
        order.remove(boss_id)
        order.append(boss_id)
    for coord, (mid, bio_id) in seen.items():
        bio = BIOMES[bio_id]
        g = gen_biome(bio, rng)
        ex = set()
        for dx, dy, ch in ((1, 0, "R"), (-1, 0, "L"), (0, -1, "U"), (0, 1, "D")):
            if (coord[0] + dx, coord[1] + dy) in seen:
                ex.add(ch)
        if coord == BOSS:
            # финальная арена: в центре — Моргарт, арена пошире
            g[N // 2][N // 2] = "C"
            for r in range(N // 2 - 2, N // 2 + 3):
                for c in range(N // 2 - 4, N // 2 + 5):
                    if g[r][c] in ".S?": g[r][c] = "."
            g[N - 6][N // 2] = "P"
        place_exits(g, ex)
        rows = ["".join(row) for row in g]

        # --- элементы окружения: детали (декор) и ящики/сундуки (контейнеры) ---
        decor = []
        used = set()
        for _ in range(rng.randint(4, 8)):
            for _try in range(30):
                xc, yc = rng.randint(2, N - 3), rng.randint(38, N - 5)
                if g[yc][xc] != "." or (xc, yc) in used:
                    continue
                used.add((xc, yc))
                spr = rng.choice(bio["decor"])
                decor.append({
                    "sprite": f"decor/{spr}.png",
                    "x": xc * 32 + rng.choice((-6, 0, 6)),
                    "y": yc * 32 + 18, "w": 28, "h": 28,
                    "z": "front", "flip": rng.random() < 0.5,
                })
                break

        containers = []
        if bio_id != "boss" and rng.random() < 0.8:
            placed = []
            for _ in range(rng.randint(1, 3)):
                for _try in range(40):
                    xc = rng.randint(3, N - 5)
                    yc = N - 5
                    if g[yc][xc] != ".": continue
                    if any(abs(xc - p[0]) < 3 for p in placed):
                        continue
                    ctype = rng.choice(("wooden_crate", "big_crate", "chest"))
                    placed.append((xc, yc))
                    containers.append({"type": ctype, "x": xc, "y": yc,
                                       "chance": round(rng.uniform(0.55, 1.0), 2)})
                    break

        d = {
            "name": bio["name"], "pos": [coord[0], coord[1]],
            "background": bio["bg"], "bg_mode": "cover",
            "darkness": bio["dark"], "rows": rows,
            "containers": containers, "decor": decor,
        }
        if coord == BOSS:
            d["lock"] = False
        MAPS.joinpath(mid + ".json").write_text(
            json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    return order


def patch_maps_json(order):
    d = json.loads(MAPS_JSON.read_text(encoding="utf-8"))
    d["start"] = f"{NAME}{START[0]}_{START[1]}"
    # мир Энеллы становится единственной кампанией; старые карты убраны в _legacy
    d["order"] = order
    d["world"] = {"reveal": "visited"}
    MAPS_JSON.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def quarantine_old():
    """Старые карты (не env_, не _*) убираем из data/maps/ в data/maps/_legacy/,
    чтобы игра валидировала только мир Энвеллы (файлы сохранены, вернуть — просто скопировать)."""
    legacy = MAPS / "_legacy"
    legacy.mkdir(exist_ok=True)
    moved = []
    for f in sorted(MAPS.glob("*.json")):
        if f.stem.startswith(NAME) or f.stem.startswith("_"):
            continue
        dest = legacy / f.name
        if not dest.exists():
            shutil.move(str(f), str(dest))
            moved.append(f.name)
    return moved


if __name__ == "__main__":
    moved = quarantine_old()
    print("Убрано в _legacy:", moved or "—")
    order = build_world()
    patch_maps_json(order)
    print(f"Сгенерировано карт мира Энвеллы: {len(order)}")

    # проверка без окна — инициализируем виртуальный дисплей, чтобы грузились картинки
    import pygame as pg
    pg.display.init()
    pg.display.set_mode((64, 64))
    import core, maps
    core.CFG = {}
    core.reload_data()
    errs = maps.check()
    real = [e for e in errs if "не загружена" not in e]
    if real:
        print("ОШИБКИ maps.check():")
        for e in real:
            print(" -", e)
    else:
        print("maps.check(): ошибок нет ✅")
    print(maps.world_text())
