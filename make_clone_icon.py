"""Генератор иконки навыка «Клон» (assets/icons/skill_clone.png).

Запуск: ./.venv/Scripts/python.exe make_clone_icon.py
Рисует фигурку героя-силуэта и его полупрозрачную копию позади (сама суть навыка).
"""
import pygame as pg
from pathlib import Path

OUT = Path(__file__).parent / "assets" / "icons" / "skill_clone.png"
SIZE = 32


def silhouette(surf, ox, oy, color, alpha):
    """Фигурка героя: голова, плечи, плащ к низу."""
    body = pg.Surface((SIZE, SIZE), pg.SRCALPHA)
    c = (*color, alpha)
    pg.draw.circle(body, c, (ox + 16, oy + 9), 5)                                  # голова
    pg.draw.polygon(body, c, [(ox + 12, oy + 15), (ox + 20, oy + 15),              # плечи
                              (ox + 23, oy + 29), (ox + 9, oy + 29)])              # плащ
    pg.draw.rect(body, c, (ox + 9, oy + 28, 14, 2), border_radius=1)               # «ноги»
    surf.blit(body, (0, 0))


def main():
    pg.init()
    surf = pg.Surface((SIZE, SIZE), pg.SRCALPHA)
    # полупрозрачная копия позади-справа — клон
    silhouette(surf, 9, 1, (130, 220, 255), 110)
    # сам герой
    silhouette(surf, 4, 4, (235, 245, 255), 255)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pg.image.save(surf, OUT)
    print("saved:", OUT)


if __name__ == "__main__":
    main()
