"""Генератор примеров экранных фильтров и прицела (Pillow). Всё лежит в assets/ и заменяется своими PNG:

  filters/gun/1..4.png + filter.json   — красный фильтр ружейного режима рыцаря (4 кадра, 8 fps)
  filters/vision/1..4.png + filter.json — жёлтый фильтр «зрения» очков инженера (4 кадра, 8 fps)
  ui/crosshair/1..3.png                — анимированный прицел (кадры крутятся, 6 fps)

Свою анимацию сделать просто: положи свои кадры 1.png, 2.png… в ту же папку (или один filter.png —
статичная картинка; один crosshair.png — статичный прицел). fps меняется в filter.json рядом с кадрами.
Кадров нет — фильтр рисуется кодом (дышит по яркости), прицел — процедурный (кружок с рисками).

Без --force существующие файлы не трогаются. Запуск:  uv run --with pillow make_filter_textures.py [--force]
"""
import math
import sys
from pathlib import Path
from PIL import Image, ImageDraw

A = Path(__file__).resolve().parent / "assets"
FORCE = "--force" in sys.argv
FW, FH = 600, 320   # кадры фильтров (масштабируются в окно при отрисовке)


def save(img, rel):
    p = A / rel
    if p.exists() and not FORCE:
        print("есть, пропускаю:", rel); return
    p.parent.mkdir(parents=True, exist_ok=True); img.save(p); print("создан:", rel)


def filter_frame(base, dark, phase, blobs=6):
    """Кадр фильтра: полупрозрачная заливка + тёмные кляксы по краям, медленно плывущие между кадрами."""
    img = Image.new("RGBA", (FW, FH), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    d.rectangle((0, 0, FW - 1, FH - 1), fill=base)
    cx, cy = FW / 2, FH / 2
    clear = min(FW, FH) * 0.34   # центр экрана остаётся прозрачным
    rng = __import__("random").Random(7)
    for j in range(blobs * 4):
        # точки по краям кадра; кляксы плывут: фаза сдвигает их вдоль края
        side = j % 4
        u = (j // 4 + phase / blobs) / blobs
        if side == 0: x, y = u * FW, rng.uniform(0, 26)
        elif side == 1: x, y = u * FW, FH - rng.uniform(0, 26)
        elif side == 2: x, y = rng.uniform(0, 26), u * FH
        else: x, y = FW - rng.uniform(0, 26), u * FH
        if (x - cx) ** 2 + (y - cy) ** 2 < clear * clear: continue
        r = rng.uniform(50, 130)
        d.ellipse((x - r, y - r, x + r, y + r), fill=dark)
    # мягкая «пульсирующая» кромка: кольцо, надувающееся с фазой
    rr = clear * (0.9 + 0.12 * math.sin(phase * math.pi / 2))
    d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=dark, width=3)
    return img


def gun_filters():
    """Красный фильтр ружейного режима: заливка и кляксы дышат, кольцо пульсирует.»"""
    frames = []
    for i in range(4):
        a = (30, 36, 42, 36)[i]           # дыхание яркости заливки
        da = (60, 74, 86, 74)[i]          # дыхание тёмных клякс
        frames.append(filter_frame((255, 42, 30, a), (168, 8, 8, da), i))
    return frames


def vision_filters():
    """Жёлтый фильтр очков: то же, в жёлтом.»"""
    frames = []
    for i in range(4):
        a = (28, 34, 40, 34)[i]
        da = (58, 70, 82, 70)[i]
        frames.append(filter_frame((255, 214, 70, a), (206, 150, 20, da), i))
    return frames


def crosshair_frames():
    """Прицел: кольцо + 4 риски, вращающиеся между кадрами; центр — точка прицеливания.»"""
    out = []
    for i in range(3):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
        col = [(255, 255, 255, 230), (255, 210, 120, 235), (255, 255, 255, 230)][i]
        out_c = (20, 20, 30, 255)
        d.ellipse((17, 17, 47, 47), outline=out_c, width=5)   # тёмная подложка — видно на любом фоне
        d.ellipse((19, 19, 45, 45), outline=col, width=2)
        d.ellipse((30, 30, 34, 34), fill=col)
        for k in range(4):
            th = math.radians(90 * k + 30 * i)
            x1, y1 = 32 + 16 * math.cos(th), 32 + 16 * math.sin(th)
            x2, y2 = 32 + 22 * math.cos(th), 32 + 22 * math.sin(th)
            d.line((x1, y1, x2, y2), fill=out_c, width=5)
            d.line((x1, y1, x2, y2), fill=col, width=2)
        out.append(img)
    return out


if __name__ == "__main__":
    for i, f in enumerate(gun_filters(), 1): save(f, f"filters/gun/{i}.png")
    save(Image.new("RGBA", (1, 1)), "filters/gun/.keep") if False else None
    for p, v in (("filters/gun/filter.json", {"fps": 8}), ("filters/vision/filter.json", {"fps": 8})):
        fp = A / p
        if fp.exists() and not FORCE: print("есть, пропускаю:", p); continue
        fp.parent.mkdir(parents=True, exist_ok=True); fp.write_text('{\n "fps": %d\n}\n' % v["fps"], encoding="utf-8"); print("создан:", p)
    for i, f in enumerate(vision_filters(), 1): save(f, f"filters/vision/{i}.png")
    for i, f in enumerate(crosshair_frames(), 1): save(f, f"ui/crosshair/{i}.png")
    xp = A / "ui/crosshair/filter.json"
    if not xp.exists() or FORCE:
        xp.write_text('{\n "fps": 6\n}\n', encoding="utf-8"); print("создан: ui/crosshair/filter.json")
