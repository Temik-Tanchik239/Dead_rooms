"""Рисует ассеты планшета заклинаний мага (spell_tablet.py): assets/ui/spell_tablet.png (квадратный
планшет с магической рамкой) и assets/ui/spell_tablet_tab.png (маленькая кнопка «вернуть планшет»
в свёрнутом состоянии). Это стартовые заглушки — можно заменить своими PNG (масштабируются под ключ
раскладки HUD "tablet" и размер кнопки). Запуск: python make_tablet_textures.py (нужен pygame)."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
from pathlib import Path
import pygame as pg

OUT = Path(__file__).resolve().parent / "assets" / "ui"
K = 4   # рисуем в 4 раза крупнее и уменьшаем — края получаются гладкими

# Палитра: тёмное дерево/камень планшета, латунная оправа, магические вставки.
WOOD_D, WOOD, WOOD_L = (44, 32, 30), (66, 48, 42), (96, 72, 60)
BRONZE, BRONZE_D, BRONZE_L = (168, 132, 76), (104, 76, 42), (232, 200, 132)
CLOTH, CLOTH_D = (38, 30, 54), (26, 20, 38)
GLOW = (150, 120, 255)


def surf(w, h): return pg.Surface((w * K, h * K), pg.SRCALPHA)
def R(x, y, w, h): return pg.Rect(int(x * K), int(y * K), int(w * K), int(h * K))
def done(s, w, h): return pg.transform.smoothscale(s, (w, h))


def tablet(size=256):
    """Квадратный планшет size×size: деревянная доска с латунной оправой, внутренняя тёмная
    «ткань» под ячейки заклинаний, четыре заклёпки и лёгкое магическое свечение по углам."""
    u = size / 64.0
    s = surf(size, size)
    # доска с лёгким вертикальным градиентом
    for i in range(int(62 * u)):
        t = i / (62 * u)
        c = (int(WOOD[0] + (WOOD_L[0] - WOOD[0]) * t * 0.5),
             int(WOOD[1] + (WOOD_L[1] - WOOD[1]) * t * 0.5),
             int(WOOD[2] + (WOOD_L[2] - WOOD[2]) * t * 0.5))
        pg.draw.rect(s, c, R(2 * u, 2 * u + i, 60 * u, 1))
    # волокна дерева
    for y in (10, 22, 34, 46, 55):
        for x0 in range(4, 58, 9):
            pg.draw.line(s, WOOD_D, (int(x0 * u * K), int((y + (x0 % 3) * 0.4) * u * K)),
                         (int(min(58, x0 + 7) * u * K), int(y * u * K)), max(1, int(0.5 * K)))
    # латунная оправа: внешняя рамка и внутренний кант
    pg.draw.rect(s, BRONZE_D, R(1 * u, 1 * u, 62 * u, 62 * u), border_radius=int(3 * u * K))
    pg.draw.rect(s, BRONZE, R(2 * u, 2 * u, 60 * u, 60 * u), border_radius=int(3 * u * K))
    pg.draw.rect(s, BRONZE_L, R(2 * u, 2 * u, 60 * u, 3 * u), border_radius=int(2 * u * K))   # блик сверху
    pg.draw.rect(s, BRONZE_D, R(5 * u, 5 * u, 54 * u, 54 * u), max(1, int(1.2 * K * u)), border_radius=int(2 * u * K))
    # тёмное полотно внутри — на нём лежат ячейки и ползунки
    pg.draw.rect(s, CLOTH, R(6 * u, 6 * u, 52 * u, 52 * u), border_radius=int(2 * u * K))
    pg.draw.rect(s, CLOTH_D, R(6 * u, 6 * u, 52 * u, 52 * u), max(1, int(1.5 * K * u)), border_radius=int(2 * u * K))
    # мягкое свечение по внутреннему периметру
    glow = surf(52, 52)
    pg.draw.rect(glow, (*GLOW, 34), R(0.5, 0.5, 51, 51), int(2 * K), border_radius=int(2 * u * K))
    s.blit(pg.transform.smoothscale(glow, (int(52 * u * K), int(52 * u * K))), R(6, 6, 52, 52))
    # руны по правому канту (тонкие штрихи) — «колдовская» фактура
    for i in range(6):
        y = 8 * u + i * 8.6 * u
        x = 60.6 * u
        pg.draw.line(s, (*GLOW, 120), (int(x * K), int(y * K)), (int(x * K), int((y + 3.4 * u) * K)), max(1, K // 2))
        pg.draw.line(s, (*GLOW, 120), (int(x * K), int((y + 1.2 * u) * K)), (int((x + 1.6 * u) * K), int((y + 2.2 * u) * K)), max(1, K // 2))
    # заклёпки по углам
    for cx, cy in ((4.6, 4.6), (59.4, 4.6), (4.6, 59.4), (59.4, 59.4)):
        pg.draw.circle(s, BRONZE_D, (int(cx * u * K) + K, int(cy * u * K) + K), int(1.7 * u * K))
        pg.draw.circle(s, BRONZE, (int(cx * u * K), int(cy * u * K)), int(1.7 * u * K))
        pg.draw.circle(s, BRONZE_L, (int((cx - 0.5) * u * K), int((cy - 0.5) * u * K)), int(0.6 * u * K))
    return done(s, size, size)


def tab(w=40, h=56):
    """Кнопка «вернуть планшет» (видна, когда планшет спрятан): латунный язычок со стрелкой вправо."""
    s = surf(w, h); u = w / 20.0
    pg.draw.rect(s, BRONZE_D, R(1 * u, 1 * u, 18 * u, 54 * u), border_radius=int(3 * u * K))
    pg.draw.rect(s, BRONZE, R(2 * u, 2 * u, 16 * u, 52 * u), border_radius=int(3 * u * K))
    pg.draw.rect(s, WOOD, R(4 * u, 4 * u, 12 * u, 48 * u), border_radius=int(2 * u * K))
    pg.draw.rect(s, WOOD_D, R(4 * u, 4 * u, 12 * u, 48 * u), max(1, int(1.2 * K * u)), border_radius=int(2 * u * K))
    # стрелка вправо
    cx, cy = 10 * u, 28 * u
    pg.draw.polygon(s, BRONZE_L, [(int((cx - 2.4 * u) * K), int((cy - 5 * u) * K)),
                                  (int((cx - 2.4 * u) * K), int((cy + 5 * u) * K)),
                                  (int((cx + 3.4 * u) * K), int(cy * K))])
    # магическая точка под стрелкой
    pg.draw.circle(s, (*GLOW, 200), (int(cx * K), int(48 * u * K)), int(1.4 * u * K))
    return done(s, w, h)


if __name__ == "__main__":
    pg.init(); pg.display.set_mode((1, 1)); OUT.mkdir(parents=True, exist_ok=True)
    for name, img in (("spell_tablet.png", tablet(256)), ("spell_tablet_tab.png", tab(40, 56))):
        pg.image.save(img, str(OUT / name)); print("saved", OUT / name)
