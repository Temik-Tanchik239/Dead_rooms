"""Генератор временных текстур барда (Pillow). Всё лежит в assets/ и заменяется своими PNG:

  weapons/guitar.png                              — гитара в руках (носом/грифом вправо; размер и точка хвата — bard.guitar в characters.json)
  icons/note_heal.png / note_mana.png / note_stun.png / note_damage.png — иконки нот (колонка в HUD)
  icons/skill_guitar_pick.png / skill_amp.png     — иконки навыков «Медиатор» и «Усилитель»
  icons/skill_resonance.png / skill_echo.png      — иконки пассивок «Резонанс» и «Эхо»
  projectiles/pick.png                            — летящий медиатор (размер — draw у типа пули pick в projectiles.json)
  skills/amp.png                                  — установленный усилитель (размер — draw у навыка amp в skills.json)

Без --force существующие файлы не трогаются. Запуск:  uv run --with pillow make_bard_textures.py [--force]
"""
import math
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


def outline(img, color=OUT):
    """Тёмная обводка в 1 пиксель вокруг фигуры (картинка получает поле в 1 px со всех сторон)."""
    w, h = img.size; big = Image.new("RGBA", (w + 2, h + 2), (0, 0, 0, 0)); big.alpha_composite(img, (1, 1)); px = big.load(); add = []
    for y in range(h + 2):
        for x in range(w + 2):
            if px[x, y][3] == 0 and any(0 <= x + dx < w + 2 and 0 <= y + dy < h + 2 and px[x + dx, y + dy][3] > 0 for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                add.append((x, y))
    for x, y in add: px[x, y] = color
    return big


def upscale(img, k):
    return img.resize((img.width * k, img.height * k), Image.NEAREST)


# ---------------- гитара ----------------
def guitar():
    """Акустическая гитара, гриф вправо: корпус-«восьмёрка» слева, розетка, подставка, гриф с ладами и головка со колками."""
    im = Image.new("RGBA", (32, 15), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    wood, light, dark, neck = (204, 124, 52, 255), (240, 170, 92, 255), (130, 74, 34, 255), (120, 78, 44, 255)
    d.ellipse((0, 3, 10, 13), fill=wood); d.ellipse((7, 4, 15, 12), fill=wood); d.rectangle((6, 5, 10, 11), fill=wood)   # корпус
    d.line((2, 5, 5, 4), fill=light); d.line((8, 5, 12, 5), fill=light)                                               # блик
    d.line((1, 11, 6, 12), fill=dark); d.line((10, 11, 13, 10), fill=dark)                                            # тень снизу
    d.ellipse((6, 6, 9, 9), fill=(48, 28, 22, 255))                                                                  # розетка
    d.rectangle((2, 7, 3, 9), fill=(70, 44, 30, 255))                                                                # подставка
    d.rectangle((15, 7, 27, 8), fill=neck)                                                                           # гриф
    for x in (18, 20, 22, 24): d.point((x, 7), fill=(220, 214, 190, 255))                                            # лады
    d.line((3, 8, 27, 8), fill=(232, 232, 222, 255))                                                                 # струны
    d.rectangle((27, 6, 30, 9), fill=(88, 56, 34, 255)); d.point((28, 5), fill=(210, 205, 185, 255)); d.point((30, 5), fill=(210, 205, 185, 255))
    return upscale(outline(im), 4)


# ---------------- ноты и иконки ----------------
def note_glyph(d, cx, cy, s, color, ink=OUT):
    """Восьмая нота (♪): головка-эллипс, штиль и хвостик; s — размер."""
    hx, hy = cx - s * 0.30, cy + s * 0.48; rx, ry = s * 0.40, s * 0.29
    top = (cx + s * 0.10, cy - s * 0.62)
    d.line((hx + rx * 0.8, hy, top[0], top[1]), fill=ink, width=max(3, int(s * 0.2)) + 2)
    d.polygon([top, (top[0] + s * 0.50, top[1] + s * 0.35), (top[0] + s * 0.42, top[1] + s * 0.80), (top[0], top[1] + s * 0.42)], fill=ink)
    d.ellipse((hx - rx - 1.5, hy - ry - 1.5, hx + rx + 1.5, hy + ry + 1.5), fill=ink)
    d.line((hx + rx * 0.8, hy, top[0], top[1]), fill=color, width=max(3, int(s * 0.2)))
    d.polygon([top, (top[0] + s * 0.42, top[1] + s * 0.32), (top[0] + s * 0.34, top[1] + s * 0.68), (top[0], top[1] + s * 0.36)], fill=color)
    d.ellipse((hx - rx, hy - ry, hx + rx, hy + ry), fill=color)


def tile(border):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    d.rounded_rectangle((1, 1, 62, 62), radius=9, fill=(28, 26, 42, 255), outline=border, width=3)
    return img


def clipped(img, layer):
    """Накладывает слой на плитку, обрезав по её внутренней рамке (свечение не вылезает на кромку)."""
    clip = Image.new("L", img.size, 0); ImageDraw.Draw(clip).rounded_rectangle((4, 4, 59, 59), radius=7, fill=255)
    layer.putalpha(Image.composite(layer.getchannel("A"), Image.new("L", img.size, 0), clip)); img.alpha_composite(layer)


def waves(img, color, cx=30, cy=34):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0)); ld = ImageDraw.Draw(layer)
    for r, a in ((26, 55), (19, 85), (12, 120)): ld.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(*color, a), width=2)
    clipped(img, layer)


def badge(d, kind):
    """Значок эффекта в правом нижнем углу: плюс (лечение), капля (мана), звезда (оглушение), всплеск (урон)."""
    cx, cy = 48, 48
    d.ellipse((cx - 11, cy - 11, cx + 11, cy + 11), fill=OUT)
    if kind == "heal":
        d.ellipse((cx - 9, cy - 9, cx + 9, cy + 9), fill=(70, 200, 110, 255)); d.rectangle((cx - 2, cy - 6, cx + 2, cy + 6), fill=(255, 255, 255, 255)); d.rectangle((cx - 6, cy - 2, cx + 6, cy + 2), fill=(255, 255, 255, 255))
    elif kind == "mana":
        d.ellipse((cx - 9, cy - 9, cx + 9, cy + 9), fill=(70, 130, 235, 255)); d.polygon([(cx, cy - 7), (cx - 5, cy + 1), (cx + 5, cy + 1)], fill=(210, 230, 255, 255)); d.ellipse((cx - 5, cy - 2, cx + 5, cy + 7), fill=(210, 230, 255, 255))
    elif kind == "stun":
        d.ellipse((cx - 9, cy - 9, cx + 9, cy + 9), fill=(215, 170, 40, 255)); pts = []
        for i in range(10):
            r = 7 if i % 2 == 0 else 3; a = -math.pi / 2 + i * math.pi / 5; pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        d.polygon(pts, fill=(255, 245, 170, 255))
    else:
        d.ellipse((cx - 9, cy - 9, cx + 9, cy + 9), fill=(205, 60, 60, 255)); pts = []
        for i in range(16):
            r = 8 if i % 2 == 0 else 4; a = i * math.pi / 8; pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        d.polygon(pts, fill=(255, 220, 190, 255))


def icon_note(border, kind, wave_color):
    img = tile(border); waves(img, wave_color); d = ImageDraw.Draw(img); note_glyph(d, 27, 28, 25, (246, 240, 222, 255)); badge(d, kind)
    return img


def icon_pick():
    img = tile((255, 210, 120, 255)); d = ImageDraw.Draw(img)
    pts = [(32, 52), (14, 24), (18, 14), (46, 14), (50, 24)]
    d.polygon(pts, fill=OUT, outline=OUT, width=4); d.polygon([(32, 49), (17, 25), (20, 17), (44, 17), (47, 25)], fill=(250, 176, 64, 255))
    d.polygon([(32, 44), (22, 25), (24, 20), (34, 20)], fill=(255, 226, 150, 255))
    return img


def icon_amp():
    img = tile((255, 170, 90, 255)); d = ImageDraw.Draw(img)
    d.rounded_rectangle((12, 14, 52, 52), radius=4, fill=OUT); d.rounded_rectangle((14, 16, 50, 50), radius=3, fill=(52, 52, 64, 255))
    d.rectangle((16, 18, 48, 24), fill=(34, 34, 42, 255))
    for x in (21, 28, 35): d.ellipse((x - 2, 19, x + 2, 23), fill=(255, 190, 90, 255))
    d.ellipse((42, 19, 46, 23), fill=(235, 70, 70, 255))
    d.rectangle((17, 27, 47, 48), fill=(94, 94, 108, 255)); d.ellipse((22, 29, 42, 47), fill=OUT); d.ellipse((24, 31, 40, 45), fill=(66, 66, 78, 255)); d.ellipse((29, 36, 35, 41), fill=(110, 110, 124, 255))
    return img


def icon_resonance():
    img = tile((255, 200, 120, 255)); waves(img, (255, 200, 120), 32, 32); d = ImageDraw.Draw(img); note_glyph(d, 30, 31, 25, (255, 224, 150, 255))
    for r in (27, 20): d.arc((32 - r, 32 - r, 32 + r, 32 + r), -40, 40, fill=(255, 224, 150, 255), width=2)
    return img


def icon_echo():
    img = tile((170, 200, 255, 255)); d = ImageDraw.Draw(img)
    for i, (dx, col) in enumerate(((10, (70, 100, 150, 255)), (5, (110, 150, 210, 255)), (0, (200, 224, 255, 255)))):
        note_glyph(d, 22 + dx + 4, 28, 24, col)
    return img


# ---------------- снаряд и установка ----------------
def pick():
    rows = ["..mmmmmmm..", ".mMMMMMMMm.", "mMMMMMMMMMm", "mMMMMMMMMMm", ".mMMMMMMMm.", ".mMMMMMMMm.", "..mMMMMMm..", "..mMMMMMm..", "...mMMMm...", "...mMMMm...", "....mMm...."]
    pal = {"m": (255, 226, 150, 255), "M": (246, 176, 64, 255)}
    im = Image.new("RGBA", (11, len(rows)), (0, 0, 0, 0)); px = im.load()
    for y, r in enumerate(rows):
        for x, ch in enumerate(r):
            if ch in pal: px[x, y] = pal[ch]
    for y in range(2, 5): px[3, y] = (255, 240, 190, 255)   # блик
    return upscale(outline(im), 2)


def amp():
    """Усилитель-комбик: корпус, ручка сверху, панель с тремя ручками и индикатором, решётка с динамиком."""
    im = Image.new("RGBA", (18, 20), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rectangle((6, 0, 11, 1), fill=(90, 90, 100, 255))                                                              # ручка для переноски
    d.rectangle((0, 2, 17, 19), fill=(56, 56, 68, 255)); d.rectangle((0, 2, 17, 2), fill=(86, 86, 100, 255))
    d.rectangle((1, 3, 16, 6), fill=(30, 30, 38, 255))                                                               # панель управления
    for x in (3, 7, 11): d.rectangle((x, 4, x + 1, 5), fill=(255, 190, 90, 255))
    d.point((15, 4), fill=(235, 70, 70, 255))
    d.rectangle((2, 8, 15, 18), fill=(98, 98, 112, 255))                                                             # решётка
    for y in (9, 11, 13, 15, 17): d.line((2, y, 15, y), fill=(84, 84, 98, 255))
    d.ellipse((4, 9, 13, 18), fill=(40, 40, 50, 255)); d.ellipse((5, 10, 12, 17), fill=(66, 66, 80, 255)); d.ellipse((7, 12, 10, 15), fill=(120, 120, 136, 255))
    return upscale(outline(im), 2)


if __name__ == "__main__":
    save(guitar(), "weapons/guitar.png")
    save(icon_note((110, 230, 140, 255), "heal", (110, 230, 140)), "icons/note_heal.png")
    save(icon_note((110, 170, 255, 255), "mana", (110, 170, 255)), "icons/note_mana.png")
    save(icon_note((255, 220, 90, 255), "stun", (255, 220, 90)), "icons/note_stun.png")
    save(icon_note((255, 100, 100, 255), "damage", (255, 100, 100)), "icons/note_damage.png")
    save(icon_pick(), "icons/skill_guitar_pick.png")
    save(icon_amp(), "icons/skill_amp.png")
    save(icon_resonance(), "icons/skill_resonance.png")
    save(icon_echo(), "icons/skill_echo.png")
    save(pick(), "projectiles/pick.png")
    save(amp(), "skills/amp.png")
