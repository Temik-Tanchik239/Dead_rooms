"""Генератор текстур ружейного режима меча рыцаря (Pillow). Всё лежит в assets/ и заменяется своими PNG:

  weapons/sword_gun.png        — меч, превращённый в ружьё (носом вправо, рукоять слева; размер на экране — draw у rusty_sword_gun в data/weapons.json)
  projectiles/pellet.png       — дробина (маленький металлический шарик)
  icons/rusty_sword_gun.png    — иконка оружия в HUD (та же плитка 64x64, что у остальных иконок)

Без --force существующие файлы не трогаются. Запуск:  uv run --with pillow make_sword_gun_textures.py [--force]
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw

A = Path(__file__).resolve().parent / "assets"
FORCE = "--force" in sys.argv
OUT = (24, 18, 26, 255)


def save(img, rel):
    p = A / rel
    if p.exists() and not FORCE:
        print("есть, пропускаю:", rel); return
    p.parent.mkdir(parents=True, exist_ok=True); img.save(p); print("создан:", rel)


def art(rows, pal, scale, margin=1, outline=True):
    """Рисует пиксель-арт из строк-символов; outline — тёмная обводка вокруг фигуры; scale — размер «большого пикселя»."""
    h, w = len(rows), max(len(r) for r in rows)
    g = [[None] * (w + 2 * margin) for _ in range(h + 2 * margin)]
    for y, r in enumerate(rows):
        for x, ch in enumerate(r):
            if ch in pal: g[y + margin][x + margin] = pal[ch]
    if outline:
        add = []
        for y in range(len(g)):
            for x in range(len(g[0])):
                if g[y][x] is None and any(0 <= y + dy < len(g) and 0 <= x + dx < len(g[0]) and g[y + dy][x + dx] is not None
                                           for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))): add.append((x, y))
        for x, y in add: g[y][x] = OUT
    img = Image.new("RGBA", (len(g[0]) * scale, len(g) * scale), (0, 0, 0, 0)); px = img.load()
    for y, row in enumerate(g):
        for x, c in enumerate(row):
            if c is None: continue
            for j in range(scale):
                for i in range(scale): px[x * scale + i, y * scale + j] = c
    return img


# ---------------- меч-ружьё ----------------
# Носом вправо: слева деревянный приклад с пистолетной рукоятью, поверх — короткий клинок (меч не исчез, а «сложился»),
# вдоль — ствол, справа раструб дробовика. Сетка 26x15, масштаб 4 -> 104x60 (draw в data/weapons.json).
GUN_PAL = {"W": (170, 118, 66, 255), "w": (128, 82, 46, 255), "d": (86, 54, 34, 255),
           "m": (170, 178, 196, 255), "M": (104, 112, 134, 255), "k": (40, 42, 58, 255),
           "t": (226, 232, 244, 255), "T": (168, 176, 196, 255), "g": (255, 205, 90, 255)}
def sword_gun():
    rows = [list("." * 26) for _ in range(15)]
    def put(x, y, ch):
        if 0 <= y < 15 and 0 <= x < 26: rows[y][x] = ch
    # клинок поверх ствола: серебристая полоса с остриём справа
    put(21, 1, "t")
    for x in range(6, 22): put(x, 2, "t")
    for x in range(6, 22): put(x, 3, "T")
    put(22, 2, "t")
    # золотая гарда между клинком и стволом
    put(5, 2, "g"); put(5, 3, "g"); put(5, 4, "g")
    # курок позади ствола
    put(7, 3, "M"); put(8, 4, "M")
    # ствол (металл) и раструб дробовика справа — расширяется к дульному срезу
    for x in range(6, 22): put(x, 5, "m")
    for x in range(4, 22): put(x, 6, "M"); put(x, 7, "M")
    for x in range(4, 22): put(x, 8, "m")
    put(24, 4, "m")
    for x in range(22, 25): put(x, 5, "m")
    for x in range(21, 26): put(x, 6, "m")
    for x in range(21, 26): put(x, 7, "k" if x >= 24 else "M")
    for x in range(21, 25): put(x, 8, "m")
    for x in range(22, 25): put(x, 9, "m")
    put(24, 10, "m")
    # приклад и пистолетная рукоять (дерево, три слоя)
    for x in range(0, 7): put(x, 8, "W")
    for x in range(0, 9): put(x, 9, "W"); put(x, 10, "w")
    for x in range(0, 9): put(x, 11, "w"); put(x, 12, "d")
    for y in range(10, 15):
        put(3, y, "w" if y < 13 else "d"); put(4, y, "w" if y < 13 else "d"); put(5, y, "d")
    # спусковая скоба и спуск
    put(11, 10, "M"); put(10, 11, "M"); put(11, 11, "g"); put(12, 11, "M")
    return art(["".join(r) for r in rows], GUN_PAL, 4, margin=1)


# ---------------- дробина ----------------
def pellet():
    pal = {"m": (196, 204, 222, 255), "M": (128, 136, 158, 255), "k": (70, 74, 94, 255)}
    rows = [".mmm...",
            "mmMMm..",
            "mMMMk..",
            ".Mkk...",
            "...k..."]
    return art(rows, pal, 2, margin=1)


# ---------------- иконка (64x64, как у навыков: тёмная плитка + цветная рамка) ----------------
def icon():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    d.rounded_rectangle((1, 1, 62, 62), radius=9, fill=(28, 26, 42, 255), outline=(206, 176, 116, 255), width=3)
    gun = sword_gun()
    k = 52 / gun.width
    gun = gun.resize((52, max(1, round(gun.height * k))), Image.NEAREST)
    img.alpha_composite(gun, ((64 - gun.width) // 2, (64 - gun.height) // 2))
    return img


if __name__ == "__main__":
    save(sword_gun(), "weapons/sword_gun.png")
    save(pellet(), "projectiles/pellet.png")
    save(icon(), "icons/rusty_sword_gun.png")
