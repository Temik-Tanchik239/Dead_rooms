"""Нижний левый угол (панель прозрачная, рисуется поверх игры): три квадратные иконки (персонаж, оружие 1 — ЛКМ, оружие 2 — ПКМ) и под иконкой персонажа полоски HP и маны.
Иконки лежат в assets/icons/: player.png и <id оружия>.png; свои пути — поле icon в data/player.json и data/weapons.json.
Нет файла иконки — вместо неё рисуется сам скин. Полоски HP и маны. Всё настраивается в data/player.json: hp_bar и mana.bar.
Поля полоски: x, y (от нижнего края окна, минус — вверх), w, h, color, back, border, flash (цвет рамки, когда не хватило маны),
ticks (деление через каждые N единиц, 0 — без делений), text (числа на полоске),
fill_skin / back_skin / frame_skin — картинки из assets (необязательно; нет файла — рисуются цветные прямоугольники)."""
import pygame as pg
import math
from core import CFG, VIEW_H
from anim import sprite
import weapon
from core import SETTINGS, W

ICON, GAP, ICON_Y = 48, 8, -80  # размер квадрата, отступ между иконками, y иконок от нижнего края окна (минус — вверх)

HP = {"x": 8, "y": -28, "w": 48, "h": 10, "color": [210, 60, 60], "back": [60, 20, 20], "border": [20, 8, 8], "text": False, "ticks": 0}
MP = {"x": 8, "y": -16, "w": 48, "h": 10, "color": [70, 140, 255], "back": [18, 26, 60], "border": [8, 12, 30], "flash": [255, 90, 90], "text": False, "ticks": 20}

def layout():
    """Пользовательская раскладка HUD: координаты от левого верхнего угла."""
    cfg = SETTINGS.setdefault("hud_layout", {})
    defaults = {
        "player": [8, VIEW_H - 80, 48],
        # Оружие и активный навык расположены ниже портрета, в одной нижней линии.
        # Порядок слева направо: оружие ЛКМ, оружие ПКМ, активный навык Q.
        "weapon1": [64, VIEW_H - 56, 48], "weapon2": [120, VIEW_H - 56, 48],
        "skill": [176, VIEW_H - 56, 48],
        "hp": [8, VIEW_H - 28, 48, 10], "mana": [8, VIEW_H - 16, 48, 10],
    }
    for k, v in defaults.items(): cfg.setdefault(k, v.copy())
    return cfg

def bar(scr, c, value, maxv, y0, flash=False, font=None):
    x, y, w, h = c["x"], y0 + c["y"], c["w"], c["h"];
    key = "hp" if c.get("_layout_key") == "hp" else "mana" if c.get("_layout_key") == "mana" else None
    if key:
        x, y, w, h = layout()[key]
    k = max(0.0, min(1.0, value / maxv)) if maxv else 0.0; fw = round(w * k)
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
    bar(scr, {**HP, **P.get("hp_bar", {}), "_layout_key": "hp"}, max(0, pl.hp), pl.maxhp, y0)
    bar(scr, {**MP, **P.get("mana", {}).get("bar", {}), "_layout_key": "mana"}, pl.mana, pl.maxmana, y0, pl.mana_flash > 0, font)
    xp_indicator(scr, pl, font)

def xp_indicator(scr, pl, font):
    """Небольшое кольцо опыта, наполовину наложенное на верхний правый угол иконки персонажа."""
    scale = 4  # supersampling для гладкого края кольца
    radius = 13
    ring_w = 2

    # Привязываем индикатор к реальному положению и размеру иконки персонажа,
    # включая пользовательскую раскладку HUD.
    player_rect = layout().get("player", [8, VIEW_H - 80, 48])
    px, py, psize = player_rect[:3]
    cx, cy = int(px + psize), int(py)

    size = (radius * 2 + 8) * scale
    center = size // 2
    outer_r = radius * scale
    inner_r = (radius - ring_w) * scale
    ratio = max(0.0, min(1.0, float(getattr(pl, "xp", 0)) / max(1, float(getattr(pl, "xp_next", 1)))))

    layer = pg.Surface((size, size), pg.SRCALPHA)
    pg.draw.circle(layer, (7, 8, 13, 235), (center, center), outer_r + 3 * scale)
    pg.draw.circle(layer, (64, 48, 26, 255), (center, center), outer_r + scale)
    pg.draw.circle(layer, (201, 157, 72, 255), (center, center), outer_r)
    pg.draw.circle(layer, (19, 18, 22, 255), (center, center), inner_r + scale)

    track_r = radius - 1
    track_rect = pg.Rect(center - track_r * scale, center - track_r * scale,
                         track_r * 2 * scale, track_r * 2 * scale)
    pg.draw.arc(layer, (74, 61, 43, 255), track_rect, 0, math.tau, 2 * scale)
    if ratio > 0:
        pg.draw.arc(layer, (255, 220, 133, 255), track_rect,
                    -math.pi / 2, -math.pi / 2 + ratio * math.tau, 2 * scale)
        pg.draw.arc(layer, (255, 241, 190, 235),
                    pg.Rect(track_rect.x + scale, track_rect.y + scale,
                            track_rect.w - 2 * scale, track_rect.h - 2 * scale),
                    -math.pi / 2, -math.pi / 2 + ratio * math.tau, scale)

    final_size = size // scale
    layer = pg.transform.smoothscale(layer, (final_size, final_size))
    # Центр кольца стоит ровно на углу иконки: половина снаружи, половина поверх портрета.
    scr.blit(layer, (int(cx - final_size / 2), int(cy - final_size / 2)))

    level = str(int(getattr(pl, "level", 1)))
    level_font = pg.font.Font(None, 17 if len(level) < 3 else 13)
    txt = level_font.render(level, True, (255, 239, 190))
    shadow = level_font.render(level, True, (12, 10, 8))
    rect = txt.get_rect(center=(cx, cy))
    scr.blit(shadow, rect.move(1, 1))
    scr.blit(txt, rect)

def label(scr, font, text, x, y, col=(235, 235, 240)):
    scr.blit(font.render(text, True, (0, 0, 0)), (x + 1, y + 1)); scr.blit(font.render(text, True, col), (x, y))

def slot(scr, i, path, fallback, border=(96, 90, 130), layout_key=None):
    """Квадрат ICON x ICON номер i слева направо. path — файл иконки в assets, fallback(rect) — чем заменить, если файла нет."""
    cfg = layout()
    pos = cfg.get(layout_key) if layout_key else None
    x, y, size = pos if pos else [8 + i * (ICON + GAP), VIEW_H + ICON_Y, ICON]
    r = pg.Rect(int(x), int(y), int(size), int(size)); img = sprite(path, r.w, r.h) if path else None
    if img: scr.blit(img, r)
    else:
        pg.draw.rect(scr, (30, 27, 44), r, border_radius=8); fallback(r); pg.draw.rect(scr, border, r, 2, border_radius=8)
    return r

def icons(scr, pl, font):
    P = CFG["player"]; Wp = CFG["weapons"]
    def face(r):
        img = sprite(P.get("skin", "player/idle.png"), 30, 38)
        if img: scr.blit(img, img.get_rect(center=r.center))
    slot(scr, 0, P.get("icon", "icons/player.png"), face, layout_key="player")

    # Сначала оружие (ЛКМ, ПКМ), затем активный навык Q. Пассивные навыки
    # не отображаются в панели и не участвуют в переключении заклинаний.

    for n, (key, wid) in enumerate(zip(("ЛКМ", "ПКМ"), pl.slots[:2])):
        w = Wp[wid]; r = slot(scr, n + 1, w.get("icon", f"icons/{wid}.png"), lambda r, wid=wid: weapon.icon(scr, wid, r.centerx, r.centery, int(r.w * .75)), layout_key="weapon1" if n == 0 else "weapon2")
        cost = weapon.mana_cost(wid, w["combo"][0])
        if pl.mana < cost:   # не хватает маны — иконка темнеет
            veil = pg.Surface(r.size, pg.SRCALPHA); pg.draw.rect(veil, (10, 10, 20, 130), veil.get_rect(), border_radius=8); scr.blit(veil, r)
        label(scr, font, key, r.x + 4, r.y + 3, (255, 230, 150))
        t = font.render(str(cost), True, (140, 185, 255)); label(scr, font, str(cost), r.right - t.get_width() - 4, r.bottom - t.get_height() - 2, (140, 185, 255))

    # Активный навык рисуется последним, справа от двух оружий.
    defs = CFG.get("skills", {})
    active_skills = [sid for sid in getattr(pl, "skills", []) if defs.get(sid, {}).get("category", "active") == "active"]
    if active_skills:
        pl.skill_index %= len(active_skills)
        sid = active_skills[pl.skill_index]
        skill = defs.get(sid, {"name": sid, "color": [150, 130, 220], "cooldown": 1})
        r = slot(scr, 3, skill.get("icon"), lambda r: pg.draw.circle(scr, skill.get("color", [150, 130, 220]), r.center, 13), border=tuple(skill.get("color", [150, 130, 220])), layout_key="skill")
        label(scr, font, "Q", r.x + 4, r.y + 3, (255, 230, 150))
        left = max(0.0, getattr(pl, "skill_cooldowns", {}).get(sid, 0.0))
        if left > 0:
            veil = pg.Surface(r.size, pg.SRCALPHA); pg.draw.rect(veil, (8, 8, 18, 165), veil.get_rect(), border_radius=8); scr.blit(veil, r)
            label(scr, font, str(int(left + .99)), r.centerx - 4, r.centery - 8, (255, 255, 255))
        else:
            pg.draw.circle(scr, (100, 240, 150), (r.right - 7, r.bottom - 7), 4)
        nm = font.render(skill.get("name", sid), True, (225, 220, 245))
        scr.blit(nm, (r.x + (r.w - nm.get_width()) // 2, r.y - nm.get_height() - 2))
