"""Рисует иконку монеты — предмет «coin» (assets/inventory.json -> items.coin):
  assets/icons/coin.png — золотая монета анфас (в ячейке рюкзака и на полу;
  на полу крутится на ребре — floor-анимация "spin" из её описания).
Запуск: python make_coin_texture.py (нужен pygame)."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
from pathlib import Path
import pygame as pg

ROOT = Path(__file__).resolve().parent / "assets" / "icons"
K = 4   # рисуем в 4 раза крупнее и уменьшаем — линии получаются гладкими

GOLD, GOLD_D, GOLD_L, RIM = (255, 205, 80), (216, 158, 46), (255, 244, 190), (140, 96, 18)


def coin(size=48):
    s = pg.Surface((size * K, size * K), pg.SRCALPHA)
    cx, cy = s.get_rect().center
    R = size * K // 2 - 2 * K
    pg.draw.circle(s, RIM, (cx, cy), R)                # тёмный обод
    pg.draw.circle(s, GOLD, (cx, cy), R - 3 * K)       # золото
    pg.draw.circle(s, GOLD_D, (cx, cy), R - 6 * K, 2 * K)   # гравировка-кольцо
    r0 = R // 3                                        # рельефный ромб в центре
    pg.draw.polygon(s, (232, 176, 60), [(cx, cy - r0), (cx + r0, cy), (cx, cy + r0), (cx - r0, cy)])
    pg.draw.polygon(s, GOLD_L, [(cx, cy - r0 + 3 * K), (cx + r0 - 3 * K, cy), (cx, cy + r0 - 3 * K), (cx - r0 + 3 * K, cy)])
    pg.draw.circle(s, GOLD_L, (cx - R // 3, cy - R // 3), 3 * K)   # блик
    return pg.transform.smoothscale(s, (size, size))


if __name__ == "__main__":
    pg.init(); pg.display.set_mode((1, 1))
    ROOT.mkdir(parents=True, exist_ok=True)
    pg.image.save(coin(), str(ROOT / "coin.png"))
    print("OK: assets/icons/coin.png")
