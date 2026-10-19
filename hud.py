"""Полоски HP и маны внизу экрана. Всё настраивается в data/player.json: hp_bar и mana.bar.
Поля полоски: x, y (от верха нижней панели), w, h, color, back, border, flash (цвет рамки, когда не хватило маны),
ticks (деление через каждые N единиц, 0 — без делений), text (числа на полоске),
fill_skin / back_skin / frame_skin — картинки из assets (необязательно; нет файла — рисуются цветные прямоугольники)."""
import pygame as pg
from core import CFG, VIEW_H
from anim import sprite

HP = {"x": 10, "y": 3, "w": 200, "h": 14, "color": [210, 60, 60], "back": [60, 20, 20], "border": [20, 8, 8], "text": False, "ticks": 0}
MP = {"x": 10, "y": 20, "w": 200, "h": 9, "color": [70, 140, 255], "back": [18, 26, 60], "border": [8, 12, 30], "flash": [255, 90, 90], "text": True, "ticks": 20}

def bar(scr, c, value, maxv, y0, flash=False, font=None):
    x, y, w, h = c["x"], y0 + c["y"], c["w"], c["h"]; k = max(0.0, min(1.0, value / maxv)) if maxv else 0.0; fw = round(w * k)
    back = sprite(c["back_skin"], w, h) if c.get("back_skin") else None
    if back: scr.blit(back, (x, y))
    else: pg.draw.rect(scr, c["back"], (x, y, w, h))
    img = sprite(c["fill_skin"], w, h) if c.get("fill_skin") else None
    if fw > 0:
        if img: scr.blit(img, (x, y), pg.Rect(0, 0, fw, h))
        else: pg.draw.rect(scr, c["color"], (x, y, fw, h))
    if c.get("ticks") and maxv:
        for v in range(int(c["ticks"]), int(maxv), int(c["ticks"])):
            tx = x + round(w * v / maxv); pg.draw.line(scr, c["border"], (tx, y), (tx, y + h - 1))
    fr = sprite(c["frame_skin"], w, h) if c.get("frame_skin") else None
    if fr: scr.blit(fr, (x, y))
    else: pg.draw.rect(scr, c["border"], (x, y, w, h), 1)
    if flash: pg.draw.rect(scr, c.get("flash", [255, 90, 90]), (x - 1, y - 1, w + 2, h + 2), 2)
    if c.get("text") and font:
        t = font.render(f"{int(value)}/{int(maxv)}", True, (235, 240, 255)); scr.blit(t, (x + (w - t.get_width()) // 2, y + (h - t.get_height()) // 2))

def draw(scr, pl, font):
    P = CFG["player"]; y0 = VIEW_H
    bar(scr, {**HP, **P.get("hp_bar", {})}, max(0, pl.hp), pl.maxhp, y0)
    bar(scr, {**MP, **P.get("mana", {}).get("bar", {})}, pl.mana, pl.maxmana, y0, pl.mana_flash > 0, font)
