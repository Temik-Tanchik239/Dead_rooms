"""Генератор текстуры моба «Пепельный призрак» (Pillow): assets/mobs/wraith/wraith.png.

Без --force существующий файл не трогается. Запуск:  uv run --with pillow make_wraith_texture.py [--force]
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


def outline(img, color=OUT):
    """Тёмная обводка в 1 пиксель вокруг фигуры (как в make_bard_textures.py)."""
    w, h = img.size; big = Image.new("RGBA", (w + 2, h + 2), (0, 0, 0, 0)); big.alpha_composite(img, (1, 1)); px = big.load(); add = []
    for y in range(h + 2):
        for x in range(w + 2):
            if px[x, y][3] == 0 and any(0 <= x + dx < w + 2 and 0 <= y + dy < h + 2 and px[x + dx, y + dy][3] > 0 for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                add.append((x, y))
    for x, y in add: px[x, y] = color
    return big


def upscale(img, k):
    return img.resize((img.width * k, img.height * k), Image.NEAREST)


def wraith():
    """Призрак в капюшоне: тёмный плащ с рваным подолом, бледное лицо, светящиеся голубые глаза,
    светлая кромка капюшона и летающие пепельные искры. Канвас 22×26, апскейл ×6."""
    im = Image.new("RGBA", (22, 26), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    dark, mid, light = (54, 60, 84, 255), (88, 96, 124, 255), (138, 150, 182, 255)
    face, eye, core = (206, 226, 250, 255), (120, 236, 255, 255), (242, 255, 255, 255)
    d.polygon([(3, 10), (18, 10), (19, 16), (17, 19), (15, 17), (13, 22), (11, 18), (9, 23), (7, 19), (5, 21), (3, 17)], fill=dark)  # плащ
    d.polygon([(6, 11), (15, 11), (16, 15), (13, 14), (11, 17), (9, 14), (7, 16)], fill=mid)                                        # складки
    d.ellipse((4, 0, 17, 12), fill=dark)                                                                                            # капюшон
    d.ellipse((6, 2, 15, 11), fill=mid)
    d.ellipse((6, 4, 15, 11), fill=face)                                                                                            # лицо
    d.rectangle((8, 7, 9, 8), fill=eye); d.rectangle((12, 7, 13, 8), fill=eye)                                                      # глаза
    d.point((8, 7), fill=core); d.point((13, 7), fill=core)
    for x, y in ((5, 2), (4, 4), (4, 6), (5, 8), (6, 10), (16, 3), (17, 5), (17, 8)):                                               # кромка капюшона
        d.point((x, y), fill=light)
    for x, y, a in ((1, 5, 200), (19, 3, 170), (20, 13, 190), (1, 15, 160), (10, 25, 150)):                                         # пепельные искры
        d.point((x, y), fill=(170, 215, 255, a))
    return upscale(outline(im), 6)


if __name__ == "__main__":
    save(wraith(), "mobs/wraith/wraith.png")
