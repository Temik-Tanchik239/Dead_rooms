"""Нижний левый угол (панель прозрачная, рисуется поверх игры): три квадратные иконки (персонаж, оружие 1 — ЛКМ, оружие 2 — ПКМ) и под иконкой персонажа полоски HP и маны.
Иконки лежат в assets/icons/: player.png и <id оружия>.png; свои пути — поле icon в data/player.json и data/weapons.json.
Нет файла иконки — вместо неё рисуется сам скин. Полоски HP и маны. Всё настраивается в data/player.json: hp_bar и mana.bar.
Поля полоски: x, y (от нижнего края окна, минус — вверх), w, h, color, back, border, flash (цвет рамки, когда не хватило маны),
ticks (деление через каждые N единиц, 0 — без делений), text (числа на полоске),
fill_skin / back_skin / frame_skin — картинки из assets (необязательно; нет файла — рисуются цветные прямоугольники)."""
import pygame as pg
from core import CFG, VIEW_H
from anim import sprite
import weapon

ICON, GAP, ICON_Y = 48, 8, -80  # размер квадрата, отступ между иконками, y иконок от нижнего края окна (минус — вверх)

HP = {"x": 8, "y": -28, "w": 48, "h": 10, "color": [210, 60, 60], "back": [60, 20, 20], "border": [20, 8, 8], "text": False, "ticks": 0}
MP = {"x": 8, "y": -16, "w": 48, "h": 10, "color": [70, 140, 255], "back": [18, 26, 60], "border": [8, 12, 30], "flash": [255, 90, 90], "text": False, "ticks": 20}

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
    P = CFG["player"]; y0 = VIEW_H; icons(scr, pl, font)
    bar(scr, {**HP, **P.get("hp_bar", {})}, max(0, pl.hp), pl.maxhp, y0)
    bar(scr, {**MP, **P.get("mana", {}).get("bar", {})}, pl.mana, pl.maxmana, y0, pl.mana_flash > 0, font)

def label(scr, font, text, x, y, col=(235, 235, 240)):
    scr.blit(font.render(text, True, (0, 0, 0)), (x + 1, y + 1)); scr.blit(font.render(text, True, col), (x, y))

def slot(scr, i, path, fallback, border=(96, 90, 130)):
    """Квадрат ICON x ICON номер i слева направо. path — файл иконки в assets, fallback(rect) — чем заменить, если файла нет."""
    r = pg.Rect(8 + i * (ICON + GAP), VIEW_H + ICON_Y, ICON, ICON); img = sprite(path, ICON, ICON) if path else None
    if img: scr.blit(img, r)
    else:
        pg.draw.rect(scr, (30, 27, 44), r, border_radius=8); fallback(r); pg.draw.rect(scr, border, r, 2, border_radius=8)
    return r

def icons(scr, pl, font):
    P = CFG["player"]; Wp = CFG["weapons"]
    def face(r):
        img = sprite(P.get("skin", "player/idle.png"), 30, 38)
        if img: scr.blit(img, img.get_rect(center=r.center))
    slot(scr, 0, P.get("icon", "icons/player.png"), face)
    # Активный скилл рядом с иконкой героя; затемнение и дуга показывают перезарядку.
    defs = CFG.get("skills", {})
    if getattr(pl, "skills", None):
        sid = pl.skills[pl.skill_index % len(pl.skills)]
        skill = defs.get(sid, {"name": sid, "color": [150, 130, 220], "cooldown": 1})
        r = slot(scr, 1, skill.get("icon"), lambda r: pg.draw.circle(scr, skill.get("color", [150, 130, 220]), r.center, 13), border=tuple(skill.get("color", [150, 130, 220])))
        label(scr, font, "Q", r.x + 4, r.y + 3, (255, 230, 150))
        left = max(0.0, getattr(pl, "skill_cooldowns", {}).get(sid, 0.0))
        if left > 0:
            veil = pg.Surface(r.size, pg.SRCALPHA); pg.draw.rect(veil, (8, 8, 18, 165), veil.get_rect(), border_radius=8); scr.blit(veil, r)
            label(scr, font, str(int(left + .99)), r.centerx - 4, r.centery - 8, (255, 255, 255))
        else:
            pg.draw.circle(scr, (100, 240, 150), (r.right - 7, r.bottom - 7), 4)
        nm = font.render(skill.get("name", sid), True, (225, 220, 245))
        scr.blit(nm, (r.x + (r.w - nm.get_width()) // 2, r.y - nm.get_height() - 2))
    for n, (key, wid) in enumerate(zip(("ЛКМ", "ПКМ"), pl.slots[:2])):
        w = Wp[wid]; r = slot(scr, n + 2, w.get("icon", f"icons/{wid}.png"), lambda r, wid=wid: weapon.icon(scr, wid, r.centerx, r.centery, 36))
        cost = weapon.mana_cost(wid, w["combo"][0])
        if pl.mana < cost:   # не хватает маны — иконка темнеет
            veil = pg.Surface(r.size, pg.SRCALPHA); pg.draw.rect(veil, (10, 10, 20, 130), veil.get_rect(), border_radius=8); scr.blit(veil, r)
        label(scr, font, key, r.x + 4, r.y + 3, (255, 230, 150))
        t = font.render(str(cost), True, (140, 185, 255)); label(scr, font, str(cost), r.right - t.get_width() - 4, r.bottom - t.get_height() - 2, (140, 185, 255))
