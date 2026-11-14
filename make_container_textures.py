"""Рисует картинки ящиков и сундуков: assets/containers/wooden_crate.png, big_crate.png, chest.png, chest_open.png.
Это стартовые заглушки — можно заменить своими (пути и размеры картинок — в data/containers.json: skin, skin_open, draw).
Запуск: python make_container_textures.py (нужен pygame)."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
from pathlib import Path
import pygame as pg

OUT = Path(__file__).resolve().parent / "assets" / "containers"
K = 4   # рисуем в 4 раза крупнее и уменьшаем — края получаются гладкими
WOOD, WOOD_D, WOOD_L, IRON, IRON_L, GOLD = (160, 112, 64), (92, 62, 34), (196, 148, 92), (86, 92, 104), (150, 158, 172), (230, 196, 86)

def surf(w, h): return pg.Surface((w * K, h * K), pg.SRCALPHA)
def R(x, y, w, h): return pg.Rect(int(x * K), int(y * K), int(w * K), int(h * K))
def done(s, w, h): return pg.transform.smoothscale(s, (w, h))

def crate(size):
    """Ящик size×size px: рамка, доски, диагональные распорки и гвозди."""
    s = surf(size, size); u = size / 32
    pg.draw.rect(s, WOOD, R(1 * u, 1 * u, 30 * u, 30 * u), border_radius=int(2 * K * u))
    for i in range(1, 4): pg.draw.line(s, WOOD_D, (int(2 * u * K), int(i * 8 * u * K)), (int(30 * u * K), int(i * 8 * u * K)), max(1, int(K * u * .7)))
    for rx in (R(1 * u, 1 * u, 30 * u, 5 * u), R(1 * u, 26 * u, 30 * u, 5 * u), R(1 * u, 1 * u, 5 * u, 30 * u), R(26 * u, 1 * u, 5 * u, 30 * u)): pg.draw.rect(s, WOOD_L, rx)
    pg.draw.line(s, WOOD_D, (int(6 * u * K), int(6 * u * K)), (int(26 * u * K), int(26 * u * K)), int(3 * K * u)); pg.draw.line(s, WOOD_D, (int(26 * u * K), int(6 * u * K)), (int(6 * u * K), int(26 * u * K)), int(3 * K * u))
    for cx, cy in ((3.5, 3.5), (28.5, 3.5), (3.5, 28.5), (28.5, 28.5)): pg.draw.circle(s, IRON_L, (int(cx * u * K), int(cy * u * K)), int(1.2 * K * u))
    pg.draw.rect(s, WOOD_D, R(1 * u, 1 * u, 30 * u, 30 * u), max(1, int(1.5 * K * u)), border_radius=int(2 * K * u))
    return done(s, size, size)

def chest(opened):
    """Сундук 64×40: деревянный корпус с железными полосами и замком; открытый — крышка поднята, внутри золотой свет."""
    W, H = 64, 40; s = surf(W, H)
    body = R(2, 20, 60, 19)
    if opened:
        pg.draw.rect(s, (60, 44, 28), R(4, 4, 56, 14), border_radius=int(3 * K))      # откинутая крышка (задняя сторона)
        pg.draw.rect(s, WOOD_D, R(4, 4, 56, 14), int(1.5 * K), border_radius=int(3 * K))
        pg.draw.rect(s, IRON, R(10, 4, 5, 14)); pg.draw.rect(s, IRON, R(49, 4, 5, 14))
        pg.draw.rect(s, WOOD, body, border_radius=int(2 * K)); pg.draw.rect(s, (28, 18, 10), R(5, 20, 54, 7), border_radius=int(2 * K))
        glow = pg.Surface((54 * K, 8 * K), pg.SRCALPHA); pg.draw.ellipse(glow, (255, 215, 110, 200), glow.get_rect()); s.blit(glow, (5 * K, 17 * K))
    else:
        pg.draw.rect(s, WOOD, body, border_radius=int(2 * K))
        lid = pg.Surface((60 * K, 24 * K), pg.SRCALPHA); pg.draw.ellipse(lid, WOOD_L, pg.Rect(0, 0, 60 * K, 40 * K)); pg.draw.ellipse(lid, WOOD_D, pg.Rect(0, 0, 60 * K, 40 * K), int(1.5 * K))
        s.blit(lid, (2 * K, 4 * K), pg.Rect(0, 0, 60 * K, 17 * K))
        pg.draw.line(s, WOOD_D, (int(4 * K), int(21 * K)), (int(60 * K), int(21 * K)), int(1.5 * K))
        pg.draw.rect(s, GOLD, R(28, 19, 8, 9), border_radius=int(1.5 * K)); pg.draw.rect(s, WOOD_D, R(31, 22, 2, 4))
    for x in (10, 47): pg.draw.rect(s, IRON, R(x, 20, 6, 19)); pg.draw.rect(s, IRON_L, R(x, 20, 2, 19))
    pg.draw.rect(s, WOOD_D, body, int(1.5 * K), border_radius=int(2 * K))
    return done(s, W, H)

if __name__ == "__main__":
    pg.init(); pg.display.set_mode((1, 1)); OUT.mkdir(parents=True, exist_ok=True)
    for name, img in (("wooden_crate.png", crate(32)), ("big_crate.png", crate(64)), ("chest.png", chest(False)), ("chest_open.png", chest(True))):
        pg.image.save(img, str(OUT / name)); print("saved", OUT / name)
