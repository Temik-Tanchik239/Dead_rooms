"""Генератор иконки чекпоинта (assets/icons/checkpoint.png).

Запуск: ./.venv/Scripts/python.exe make_checkpoint_icon.py
Рисует гранёный вытянутый кристалл в бирюзово-голубой гамме на прозрачном фоне
(мягкое свечение позади, светлые/тёмные грани, белый блик) — как у make_clone_icon.py,
но с множителем K и даунскейлом, чтобы края были чёткими.
"""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
from pathlib import Path
import pygame as pg

OUT = Path(__file__).parent / "assets" / "icons" / "checkpoint.png"
SIZE = 32          # конечный размер, как у соседних иконок (skill_clone.png)
K = 8              # рисуем в 8 раз крупнее и уменьшаем — края гладкие, пиксель чёткий

# Палитра (бирюзово-голубой кристалл)
BASE  = (110, 225, 255)   # основная грань
DARK  = (60, 140, 190)    # тёмная (теневая) грань
DARK2 = (45, 105, 155)    # самое тёмное — нижний кончик
LIGHT = (176, 244, 255)   # светлая полоса в центре
WHITE = (242, 255, 255)   # блик
GLOW  = (130, 235, 255)   # свечение по краям


def glow(surf, cx, cy, rad, color, alpha):
    """Мягкое свечение: круг рисуется крупно и уменьшается вдвое — края растекаются."""
    g = pg.Surface((rad * 2 * K, rad * 2 * K), pg.SRCALPHA)
    pg.draw.circle(g, (*color, alpha), (rad * K, rad * K), rad * K)
    g2 = pg.transform.smoothscale(g, (rad * K, rad * K))
    surf.blit(g2, (int((cx - rad / 2) * K), int((cy - rad / 2) * K)))


def poly(surf, pts, color):
    """Многоугольник в координатах иконки (умножаются на K)."""
    pg.draw.polygon(surf, color, [(x * K, y * K) for x, y in pts])


def line(surf, p1, p2, color):
    pg.draw.line(surf, color, (p1[0] * K, p1[1] * K), (p2[0] * K, p2[1] * K), K)


def main():
    pg.init()
    surf = pg.Surface((SIZE * K, SIZE * K), pg.SRCALPHA)

    # --- свечение позади кристалла ---
    glow(surf, 16, 16, 15, GLOW, 60)
    glow(surf, 16, 15, 9, GLOW, 75)

    # --- контур кристалла: вытянутый ромб с «плечами» ---
    T  = (16.0, 2.5)    # верхняя точка
    TR = (22.5, 10.0)   # правое плечо
    BR = (21.0, 20.0)   # правая талия
    B  = (16.0, 29.5)   # нижняя точка
    BL = (11.0, 20.0)   # левая талия
    TL = (9.5, 10.0)    # левое плечо

    poly(surf, [T, TL, BL, B], DARK)     # теневая левая грань
    poly(surf, [T, TR, BR, B], BASE)     # основная правая грань
    poly(surf, [T, (18.4, 10.8), (17.8, 20.6), B], LIGHT)  # светлая полоса по центру

    # --- дополнительные швы граней ---
    line(surf, TL, TR, (*DARK, 110))     # плечевой шов сверху
    line(surf, BL, BR, (*DARK, 90))      # шов талии снизу
    poly(surf, [(14.2, 24.5), (17.8, 24.5), B], DARK2)     # тёмный нижний кончик
    poly(surf, [T, (14.7, 5.2), (17.3, 5.2)], (*LIGHT, 170))  # подсвеченный верхний кончик

    # --- светлый кант по контуру + белый блик ---
    pg.draw.lines(surf, (*LIGHT, 130), True, [(x * K, y * K) for x, y in (T, TR, BR, B, BL, TL)], K // 2)
    poly(surf, [(14.0, 5.2), (12.4, 7.0), (13.5, 7.9), (15.1, 6.1)], WHITE)  # блик-«ластичка»
    pg.draw.circle(surf, (*WHITE, 200), (int(17.6 * K), int(8.2 * K)), K // 2)  # искра

    icon = pg.transform.smoothscale(surf, (SIZE, SIZE))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pg.image.save(icon, OUT)
    print("saved:", OUT, icon.get_size())


if __name__ == "__main__":
    main()
