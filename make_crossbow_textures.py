"""Генератор временных текстур мини-арбалетов Тени (Pillow). Всё лежит в assets/ и заменяется своими PNG:

  weapons/mini_crossbow.png              — арбалет в руке (носом вправо, рукоять слева; размер на экране — crossbows.draw в characters.json)
  projectiles/xbow_arrow.png             — обычная стрела
  projectiles/xbow_fire/1..3.png         — огненная стрела (кадры горения)
  projectiles/xbow_heavy.png             — усиленный болт
  projectiles/xbow_hook.png              — наконечник гарпуна («стрела с нитью»)
  projectiles/xbow_thread.png            — нить гарпуна: бесшовная полоска (повторяется вдоль нити, высота = hook.thread_width, по умолчанию 4 px)
  icons/ammo_arrow.png / ammo_fire.png / ammo_heavy.png / ammo_harpoon.png — иконки видов снарядов (окна боеприпасов в HUD)

Без --force существующие файлы не трогаются. Запуск:  uv run --with pillow make_crossbow_textures.py [--force]
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


# ---------------- арбалет ----------------
CB_PAL = {"W": (170, 118, 66, 255), "w": (128, 82, 46, 255), "d": (86, 54, 34, 255), "m": (170, 178, 196, 255), "M": (104, 112, 134, 255),
          "s": (232, 226, 200, 255), "b": (206, 176, 116, 255), "t": (226, 232, 244, 255), "f": (214, 72, 72, 255), "g": (255, 205, 90, 255)}
def crossbow():
    rows = [list("." * 28) for _ in range(15)]
    def put(x, y, ch):
        if 0 <= y < 15 and 0 <= x < 28: rows[y][x] = ch
    # ложе: три слоя дерева
    for x in range(1, 20):
        put(x, 6, "W"); put(x, 7, "w"); put(x, 8, "d")
    put(0, 7, "w"); put(0, 8, "d")
    # рукоять вниз
    for y in range(9, 14):
        put(4, y, "w"); put(5, y, "w"); put(6, y, "d")
    put(3, 13, "w")
    # скоба спуска
    put(9, 9, "M"); put(10, 9, "M"); put(10, 10, "M")
    # головка и плечи (сверху и снизу), ось — строка 7
    for y in range(5, 10): put(17, y, "M"); put(18, y, "M")
    arm = [(19, 4), (20, 3), (21, 2), (22, 1), (23, 0)]
    for k, (x, y) in enumerate(arm):
        put(x, y, "m"); put(x - 1, y, "M")
        put(x, 14 - y, "m"); put(x - 1, 14 - y, "M")
    # тетива: от кончиков плеч к ложу
    for k in range(10):
        xs = 23 - k * 1.2; ys = 0 + k * 0.62
        put(round(xs), round(ys), "s"); put(round(xs), 14 - round(ys), "s")
    # болт на желобе (строка 5): оперение, древко, наконечник
    for x in range(3, 5): put(x, 5, "f")
    for x in range(5, 21): put(x, 5, "b")
    for x in range(21, 25): put(x, 5, "t")
    put(23, 4, "t"); put(23, 6, "t")
    return art(["".join(r) for r in rows], CB_PAL, 4, margin=1)


# ---------------- болты ----------------
def bolt_normal():
    pal = {"b": (206, 176, 116, 255), "B": (150, 118, 70, 255), "t": (226, 232, 244, 255), "T": (168, 176, 196, 255), "f": (222, 222, 210, 255)}
    rows = ["ff.................t....",
            "ffbbbbbbbbbbbbbbbbbttt..",
            "ffBBBBBBBBBBBBBBBBBTTT..",
            "ff.................T...."]
    return art(rows, pal, 2, margin=1)


def bolt_fire(frame):
    pal = {"b": (206, 150, 90, 255), "B": (150, 100, 60, 255), "t": (255, 214, 120, 255), "T": (255, 160, 60, 255),
           "o": (255, 120, 40, 255), "y": (255, 235, 150, 255), "r": (220, 70, 30, 255), "f": (222, 222, 210, 255)}
    flames = [
        ["..............oo.......", "........r.....oyyo.....", ".......rroooooyyyyoo...", "........r.....oyyo.....", "..............oo......."],
        ["...............o.......", ".......r......ooyo.....", "......rrooooooyyyyoo...", ".......r......ooyo.....", "...............o......."],
        ["..............o........", "........r....oyyyo.....", ".......rrooooyyyyyyo...", "........r....oyyyo.....", "..............o........"],
    ][frame % 3]
    shaft = ["ffbbbbbbbbbbbbbbbbbtttt.", "ffBBBBBBBBBBBBBBBBTTTTT."]
    rows = ["." * 24] + shaft + ["." * 24]
    # пламя поверх древка: три кадра с разной формой языков огня; строки 1-3 пламени совпадают со строками древка
    return art(overlay(rows, flames[:4]), pal, 2, margin=1, outline=False)


def overlay(base, top):
    h = max(len(base), len(top)); out = []
    for y in range(h):
        b = base[y] if y < len(base) else ""; t = top[y] if y < len(top) else ""
        w = max(len(b), len(t)); b = b.ljust(w, "."); t = t.ljust(w, ".")
        out.append("".join(tc if tc != "." else bc for bc, tc in zip(b, t)))
    return out


def bolt_heavy():
    pal = {"s": (176, 184, 204, 255), "S": (112, 120, 142, 255), "h": (226, 232, 244, 255), "k": (60, 64, 84, 255),
           "f": (210, 70, 70, 255), "g": (130, 200, 255, 255)}
    rows = ["ff...........................h..",
            "ffssssssssssssssssssssssssshhh..",
            "ffssssssssssssssssssssssssshhhh.",
            "ffSSSSSSSSSSSSSSSSSSSSSSSSShhh..",
            "ff...........................h.."]
    return art(rows, pal, 2, margin=1)


def hook_head():
    """Наконечник гарпуна носом вправо: ушко для нити слева, древко, зазубрины и острие."""
    pal = {"s": (222, 214, 188, 255), "m": (170, 178, 196, 255), "M": (104, 112, 134, 255), "t": (232, 240, 250, 255), "g": (120, 215, 190, 255)}
    rows = ["........mM......",
            "......mmmM......",
            "ssggmmmmmmmmmtt.",
            "......mmmM......",
            "........mM......"]
    return art(rows, pal, 2, margin=1)


# ---------------- иконки боеприпасов (64x64, как у навыков: тёмная плитка + цветная рамка) ----------------
def icon(border, draw_fn):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    d.rounded_rectangle((1, 1, 62, 62), radius=9, fill=(28, 26, 42, 255), outline=border, width=3)
    draw_fn(img)
    return img


def diag_bolt(img, shaft, head, glow=None, thick=3):
    if glow:   # свечение у наконечника — на отдельном слое, обрезанном по плитке (не вылезает на рамку)
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0)); ld = ImageDraw.Draw(layer)
        for r, a in ((18, 40), (13, 70), (9, 100)): ld.ellipse((46 - r, 18 - r, 46 + r, 18 + r), fill=(*glow, a))
        clip = Image.new("L", img.size, 0); ImageDraw.Draw(clip).rounded_rectangle((4, 4, 59, 59), radius=7, fill=255)
        layer.putalpha(Image.composite(layer.getchannel("A"), Image.new("L", img.size, 0), clip)); img.alpha_composite(layer)
    d = ImageDraw.Draw(img)
    d.line((14, 50, 48, 16), fill=OUT, width=thick + 3)
    d.line((14, 50, 48, 16), fill=shaft, width=thick)
    d.polygon([(54, 10), (44, 14), (50, 20)], fill=head, outline=OUT)
    d.polygon([(10, 54), (13, 44), (20, 51)], fill=(214, 72, 72, 255), outline=OUT)


def icon_arrow():
    return icon((200, 186, 132, 255), lambda im: diag_bolt(im, (206, 176, 116, 255), (226, 232, 244, 255)))


def icon_fire():
    def f(im):
        diag_bolt(im, (206, 150, 90, 255), (255, 214, 120, 255), glow=(255, 140, 50))
        d = ImageDraw.Draw(im)
        for (x, y, r, c) in ((50, 14, 7, (255, 120, 40, 255)), (53, 10, 5, (255, 190, 80, 255)), (55, 8, 3, (255, 245, 170, 255)), (44, 20, 3, (255, 150, 50, 255))):
            d.ellipse((x - r, y - r, x + r, y + r), fill=c)
        for (x, y) in ((22, 22), (34, 12), (14, 36)): d.rectangle((x, y, x + 2, y + 2), fill=(255, 205, 90, 255))
    return icon((255, 140, 50, 255), f)


def icon_heavy():
    def f(im):
        diag_bolt(im, (176, 184, 204, 255), (240, 245, 255, 255), glow=(130, 180, 255), thick=6)
        d = ImageDraw.Draw(im)
        d.line((18, 46, 44, 20), fill=(112, 120, 142, 255), width=2)
        for (x, y) in ((22, 14), (12, 24), (50, 44)): d.rectangle((x, y, x + 2, y + 2), fill=(170, 210, 255, 255))
    return icon((140, 170, 230, 255), f)


def thread():
    """Нить гарпуна: бесшовная горизонтальная полоска 16x4 (две тёмные кромки и витая бежевая жила). Любая другая полоска подойдёт — она тайлится вдоль нити."""
    img = Image.new("RGBA", (16, 4), (0, 0, 0, 0)); px = img.load()
    light, dark = (232, 224, 196, 255), (186, 176, 148, 255)
    for x in range(16):
        px[x, 0] = OUT; px[x, 3] = OUT
        px[x, 1] = light if (x // 2) % 2 == 0 else dark
        px[x, 2] = dark if (x // 2) % 2 == 0 else light
    return img


def icon_harpoon():
    def f(im):
        d = ImageDraw.Draw(im)
        pts = [(12, 52), (14, 44), (22, 46), (24, 38), (32, 40), (36, 32), (44, 28)]   # нить с петлями к наконечнику
        d.line(pts, fill=OUT, width=5); d.line(pts, fill=(222, 214, 188, 255), width=3)
        d.polygon([(56, 8), (40, 14), (46, 20), (52, 26), (50, 14)], fill=(170, 178, 196, 255), outline=OUT)   # зазубрины
        d.polygon([(58, 6), (46, 12), (52, 18)], fill=(232, 240, 250, 255), outline=OUT)                         # острие
        d.line((44, 28, 52, 16), fill=OUT, width=5); d.line((44, 28, 52, 16), fill=(120, 215, 190, 255), width=3)
        for (x, y) in ((18, 18), (30, 20), (10, 34)): d.rectangle((x, y, x + 2, y + 2), fill=(170, 235, 215, 255))
    return icon((120, 215, 190, 255), f)


if __name__ == "__main__":
    save(crossbow(), "weapons/mini_crossbow.png")
    save(bolt_normal(), "projectiles/xbow_arrow.png")
    for i in range(3): save(bolt_fire(i), f"projectiles/xbow_fire/{i + 1}.png")
    save(bolt_heavy(), "projectiles/xbow_heavy.png")
    save(icon_arrow(), "icons/ammo_arrow.png")
    save(icon_fire(), "icons/ammo_fire.png")
    save(icon_heavy(), "icons/ammo_heavy.png")
    save(hook_head(), "projectiles/xbow_hook.png")
    save(thread(), "projectiles/xbow_thread.png")
    save(icon_harpoon(), "icons/ammo_harpoon.png")
