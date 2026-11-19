"""Рисует стартовые мелкие детали окружения: assets/decor/*.png
(трава, мох, цепь, паутина, фонарь, свеча, забор).

Это картинки слоя «Мелкие детали» редактора карт (DecorPanel). Они ни на что
не влияют в физике — только рисуются поверх карты с произвольной точностью.
Запуск: python make_decor_textures.py (нужен pygame)."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
from pathlib import Path
import pygame as pg

OUT = Path(__file__).resolve().parent / "assets" / "decor"
K = 4                       # рисуем в 4 раза крупнее и уменьшаем — края гладкие

# Палитра в духе игры (кости, тёмный, янтарный свет)
DARK      = (42, 36, 32)
INK       = (21, 19, 26)
BONE      = (217, 211, 189)
BONE_D    = (168, 160, 136)
GRASS_D   = (50, 70, 34)
GRASS     = (78, 104, 46)
GRASS_L   = (112, 142, 66)
GRASS_HI  = (150, 176, 92)
MOSS_D    = (40, 58, 36)
MOSS      = (60, 82, 48)
MOSS_L    = (84, 108, 62)
STEEL     = (122, 128, 138)
STEEL_D   = (72, 77, 86)
STEEL_L   = (174, 180, 190)
BRASS     = (190, 152, 84)
BRASS_D   = (128, 96, 52)
BRASS_L   = (226, 192, 130)
GLASS     = (255, 216, 140)
FIRE      = (255, 196, 90)
FIRE_D    = (196, 112, 44)
FIRE_C    = (255, 244, 200)
CANDLE    = (222, 212, 182)
CANDLE_D  = (172, 160, 132)
WOOD_F    = (104, 74, 44)
WOOD_FD   = (72, 52, 30)
WOOD_FL   = (134, 100, 60)


def surf(w, h):
    return pg.Surface((w * K, h * K), pg.SRCALPHA)


def done(s, w, h):
    return pg.transform.smoothscale(s, (w, h))


def glow(s, cx, cy, rad, color, alpha=120):
    """Мягкое свечение вокруг точки (cx, cy) в пикселях картинки."""
    g = pg.Surface((rad * 2 * K, rad * 2 * K), pg.SRCALPHA)
    pg.draw.circle(g, (*color, alpha), (rad * K, rad * K), rad * K)
    g2 = pg.transform.smoothscale(g, (rad * K, rad * K))
    s.blit(g2, (int((cx - rad / 2) * K), int((cy - rad / 2) * K)))


# ---------- трава ----------
def grass():
    s = surf(16, 16)
    blades = [                       # (основание X, высота, цвет, наклон в px)
        (2.5, 7, GRASS_D, 0), (4.5, 10, GRASS, -1), (6.5, 8, GRASS_L, 1),
        (9, 12, GRASS, 0), (11, 7, GRASS_D, -1), (13, 9, GRASS_L, 1),
    ]
    for x, h, col, tilt in blades:
        for i in range(3):           # толщина прядки
            for y in range(16 - h, 16):
                frac = 15 - y        # 0 у корня
                x1 = x + tilt * 0.4 * frac / h * 4
                c = col
                if frac > h - 2 and h >= 8:      # кончик светлее
                    c = GRASS_HI
                s.set_at((int(x1) + i // 2, y), c)
    # арки-перекрещивания у корней
    pg.draw.rect(s, (34, 44, 26, 100), (0, 14 * K, 16 * K, 2 * K))
    return done(s, 16, 16)


# ---------- мох ----------
def moss():
    s = surf(16, 14)
    blobs = [(3, 9, 5), (6, 11, 6), (10, 9, 5), (8, 7, 4), (13, 10, 3), (2, 11, 3), (12, 11, 4)]
    for bx, by, br in blobs:
        pg.draw.circle(s, (*MOSS_D, 150), (bx * K, by * K), br * K)
    for bx, by, br in blobs:
        pg.draw.circle(s, (*MOSS, 235), (bx * K, by * K), int(br * 0.8 * K))
    for bx, by, br in blobs:
        pg.draw.circle(s, (*MOSS_L, 235), (int((bx - br * 0.2) * K), int((by - br * 0.2) * K)), max(2, int(br * 0.45 * K)))
    return done(s, 16, 14)


# ---------- цепь ----------
def chain():
    s = surf(12, 32)
    cx = 6 * K
    pg.draw.circle(s, STEEL_D, (cx, 1 * K), 2 * K)          # кольцо подвеса
    pg.draw.circle(s, STEEL, (cx, 1 * K), int(1.3 * K))
    for i in range(4):
        cy = (6 + i * 8) * K
        if i % 2 == 0:                                      # звено вертикальное
            pg.draw.ellipse(s, STEEL_D, (cx - 3 * K, cy - 3 * K, 6 * K, 6 * K))
            pg.draw.ellipse(s, STEEL, (cx - 2 * K, cy - 2 * K, 4 * K, 4 * K))
            pg.draw.circle(s, (0, 0, 0, 0), (cx, cy), int(1.1 * K))
            pg.draw.arc(s, STEEL_L, (cx - 2 * K, cy - 3 * K, 4 * K, 6 * K), 0.15, 1.3, 2)
        else:                                               # звено горизонтальное
            pg.draw.ellipse(s, STEEL_D, (cx - 3 * K, cy - 3 * K, 6 * K, 6 * K))
            pg.draw.ellipse(s, STEEL, (cx - 2 * K, cy - 2 * K, 4 * K, 4 * K))
            pg.draw.circle(s, (0, 0, 0, 0), (cx, cy), int(1.1 * K))
            pg.draw.arc(s, STEEL_L, (cx - 3 * K, cy - 2 * K, 6 * K, 4 * K), 3.4, 5.0, 2)
    return done(s, 12, 32)


# ---------- паутина ----------
def cobweb():
    s = surf(16, 16)
    cx, cy, rmax = 1.5, 2.0, 14
    WEB = (232, 232, 240)
    for k in range(5):              # радиальные нити из угла
        ang = 0.35 + k * 0.7        # веер ~0.7 rad между нитями
        ex = int((cx + rmax * pg.math.Vector2(1, 0).rotate_rad(ang).x) * K)
        ey = int((cy + rmax * pg.math.Vector2(1, 0).rotate_rad(ang).y) * K)
        pg.draw.line(s, (*WEB, 200), (int(cx * K), int(cy * K)), (ex, ey), 2)
    for r in (5, 9, 13):            # концентрические дуги (пунктиром)
        step = 0.45
        ang = 0.35
        while ang < 0.35 + 2.9:
            p0 = (int((cx + r * pg.math.Vector2(1, 0).rotate_rad(ang).x) * K),
                  int((cy + r * pg.math.Vector2(1, 0).rotate_rad(ang).y) * K))
            p1 = (int((cx + r * pg.math.Vector2(1, 0).rotate_rad(ang + step).x) * K),
                  int((cy + r * pg.math.Vector2(1, 0).rotate_rad(ang + step).y) * K))
            pg.draw.line(s, (*WEB, 170), p0, p1, 2)
            ang += step * 1.6
    return done(s, 16, 16)


# ---------- фонарь с лампой ----------
def lantern():
    W, H = 12, 20
    s = surf(W, H)
    cx = 6
    glow(s, cx, 12, 16, (255, 190, 90), 70)
    # стекло
    pg.draw.rect(s, (*GLASS, 130), (4 * K, 8 * K, 7 * K, 7 * K))
    pg.draw.rect(s, (*GLASS, 110), (3 * K, 8 * K, 1 * K, 7 * K))
    pg.draw.rect(s, (*GLASS, 110), (11 * K, 8 * K, 1 * K, 7 * K))
    # пламя
    pg.draw.circle(s, FIRE_D, (cx * K, 12 * K), 2 * K)
    pg.draw.circle(s, FIRE, (cx * K, 12 * K), 1 * K)
    pg.draw.circle(s, FIRE_C, (cx * K, 12 * K), K - 1)
    # верхняя/нижняя планка каркаса
    pg.draw.rect(s, BRASS_D, (3 * K, 7 * K, 9 * K, 1 * K))
    pg.draw.rect(s, BRASS_D, (3 * K, 15 * K, 9 * K, 1 * K))
    pg.draw.rect(s, BRASS_L, (4 * K, 8 * K, 1 * K, 7 * K))
    pg.draw.rect(s, BRASS_L, (10 * K, 8 * K, 1 * K, 7 * K))
    # купол
    pg.draw.rect(s, BRASS_D, (3 * K, 6 * K, 9 * K, 2 * K))
    pg.draw.rect(s, BRASS_L, (5 * K, 6 * K, 1 * K, 2 * K))
    # дно
    pg.draw.rect(s, BRASS_D, (3 * K, 16 * K, 9 * K, 2 * K))
    pg.draw.rect(s, BRASS_L, (5 * K, 16 * K, 1 * K, 2 * K))
    # ручка-кольцо
    pg.draw.arc(s, BRASS_D, (4 * K, 1 * K, 7 * K, 7 * K), 0, 3.14, K)
    pg.draw.arc(s, BRASS_L, (4 * K, 1 * K, 7 * K, 7 * K), 0, 3.14, 1)
    return done(s, W, H)


# ---------- свеча ----------
def candle():
    W, H = 8, 17
    s = surf(W, H)
    glow(s, 4, 3, 12, (255, 200, 100), 80)
    # пламя
    pg.draw.circle(s, FIRE_D, (4 * K, 3 * K), 2 * K)
    pg.draw.circle(s, FIRE, (4 * K, 3 * K), 1 * K)
    pg.draw.circle(s, FIRE_C, (4 * K, 3 * K), max(1, K // 2))
    # фитиль
    pg.draw.rect(s, INK, (4 * K, 4 * K, 1 * K, 1 * K))
    # тело свечи
    pg.draw.rect(s, CANDLE, (3 * K, 5 * K, 3 * K, 12 * K))
    pg.draw.rect(s, CANDLE_D, (3 * K, 5 * K, 1 * K, 12 * K))
    pg.draw.rect(s, (255, 255, 240), (5 * K, 5 * K, 1 * K, 12 * K))
    # капли воска
    pg.draw.circle(s, CANDLE, (5 * K, 9 * K), K)
    pg.draw.circle(s, CANDLE, (3 * K, 12 * K), K - 1)
    return done(s, W, H)


# ---------- забор ----------
def fence():
    W, H = 32, 16
    s = surf(W, H)
    pg.draw.rect(s, (20, 16, 12, 80), (0, 14 * K, W * K, 2 * K))
    for bx in (3, 24):          # две доски с заострённым верхом
        pg.draw.polygon(s, WOOD_FD, [(bx * K, 7 * K), ((bx + 3) * K, 1 * K), ((bx + 6) * K, 7 * K)])
        pg.draw.rect(s, WOOD_F, (bx * K, 7 * K, 6 * K, 7 * K))
        pg.draw.rect(s, WOOD_FL, ((bx + 1) * K, 7 * K, 1 * K, 7 * K))
        pg.draw.rect(s, WOOD_FD, ((bx + 5) * K, 7 * K, 1 * K, 7 * K))
        pg.draw.rect(s, WOOD_FD, (bx * K, 9 * K, 6 * K, 1 * K))
    # перекладина
    pg.draw.rect(s, WOOD_FD, (0, 9 * K, W * K, 2 * K))
    pg.draw.rect(s, WOOD_F, (0, 9 * K, W * K, 1 * K))
    pg.draw.rect(s, WOOD_FL, (0, 9 * K, W * K, 1 * K))
    for gx in (3, 24):          # гвозди
        pg.draw.circle(s, (30, 26, 20), ((gx + 3) * K, 10 * K), K - 1)
    return done(s, W, H)


if __name__ == "__main__":
    pg.init(); pg.display.set_mode((1, 1)); OUT.mkdir(parents=True, exist_ok=True)
    items = {
        "grass.png": grass(),
        "moss.png": moss(),
        "chain.png": chain(),
        "cobweb.png": cobweb(),
        "lantern.png": lantern(),
        "candle.png": candle(),
        "fence.png": fence(),
    }
    for name, img in items.items():
        pg.image.save(img, str(OUT / name))
        print("saved", OUT / name, img.get_size())
