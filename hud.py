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
import spells
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
    P = CFG["player"]; y0 = VIEW_H
    # Заклинатель (spellcaster в data/characters.json — маг/инженер): портрет + окно из трёх умений вместо иконок оружия.
    if CFG.get("character", {}).get("spellcaster"):
        portrait(scr, pl, font); spellbook(scr, pl, font)
    else:
        icons(scr, pl, font)
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

def portrait(scr, pl, font):
    """Иконка персонажа (слот 0). Кольцо опыта привязано к ней отдельно (xp_indicator)."""
    P = CFG["player"]
    def face(r):
        img = sprite(P.get("skin", "player/idle.png"), 30, 38)
        if img: scr.blit(img, img.get_rect(center=r.center))
    slot(scr, 0, P.get("icon", "icons/player.png"), face, layout_key="player")


def channel_overlay(scr, pl, sid, r, font, color):
    """Индикатор удерживаемого заклинания (skills.json: "channel": true) на иконке навыка sid в прямоугольнике r.
    Пока герой колдует: уже «израсходованное» время затемняет иконку сектором по часовой стрелке (светлая часть = сколько
    ещё можно стоять и колдуть), в центре — оставшиеся секунды, рамка пульсирует цветом заклинания.
    Возвращает True, если индикатор нарисован (тогда кулдаун/«готово» на иконке не рисуем)."""
    ch = getattr(pl, "channel", None)
    if not ch or ch.get("sid") != sid: return False
    total = max(0.1, float(ch.get("max", 1.0)))
    left = max(0.0, total - float(ch.get("t", 0.0)))
    used = max(0.0, min(1.0, 1.0 - left / total))
    if used > 0.004:
        veil = pg.Surface(r.size, pg.SRCALPHA)
        cx, cy, rad, a0 = r.w / 2, r.h / 2, r.w * 1.2, -math.pi / 2
        n = max(2, int(used * 48))
        pts = [(cx, cy)] + [(cx + math.cos(a0 + used * math.tau * i / n) * rad, cy + math.sin(a0 + used * math.tau * i / n) * rad) for i in range(n + 1)]
        pg.draw.polygon(veil, (8, 8, 18, 185), pts)
        scr.blit(veil, r)
    pulse = 0.55 + 0.45 * math.sin(pg.time.get_ticks() * 0.012)
    glow = tuple(min(255, int(c * pulse + 255 * (1 - pulse) * 0.35)) for c in color[:3])
    pg.draw.rect(scr, glow, r.inflate(4, 4), 3, border_radius=10)
    txt = f"{left:.1f}"
    label(scr, font, txt, r.centerx - font.size(txt)[0] // 2, r.centery - font.get_height() // 2, (255, 255, 255))
    return True


def spell_cell(scr, pl, sid, x, y, size, font, active=False):
    """Одна ячейка заклинания: иконка/цвет, рамка, затемнение неактивных, кулдаун и цена маны."""
    sk = CFG.get("skills", {}).get(sid, {})
    color = tuple(sk.get("color", [150, 130, 220]))
    r = pg.Rect(int(x), int(y), int(size), int(size))
    pg.draw.rect(scr, (28, 26, 42) if active else (18, 17, 28), r, border_radius=8)
    ip = spells.icon_path(sid, sk)
    img = sprite(ip, r.w - 6, r.h - 6) if ip else None
    if img: scr.blit(img, img.get_rect(center=r.center))
    else: pg.draw.circle(scr, color, r.center, max(4, size // 2 - 5))
    if not active:   # предыдущее/следующее — приглушены
        veil = pg.Surface(r.size, pg.SRCALPHA); veil.fill((8, 8, 16, 120)); scr.blit(veil, r)
    pg.draw.rect(scr, color if active else (80, 78, 105), r, 3 if active else 2, border_radius=8)
    chan = channel_overlay(scr, pl, sid, r, font, color)   # удерживаемое заклинание: убывающий индикатор вместо кулдауна
    left = max(0.0, getattr(pl, "skill_cooldowns", {}).get(sid, 0.0))
    if left > 0 and not chan:
        veil = pg.Surface(r.size, pg.SRCALPHA); pg.draw.rect(veil, (8, 8, 18, 170), veil.get_rect(), border_radius=8); scr.blit(veil, r)
        label(scr, font, str(int(left + .99)), r.centerx - 4, r.centery - 8, (255, 255, 255))
    cost = int(sk.get("mana_cost", 0))
    if cost:
        enough = pl.mana >= cost
        label(scr, font, str(cost), r.x + 4, r.bottom - font.get_height() - 1, (140, 185, 255) if enough else (255, 120, 120))
    return r


def spellbook(scr, pl, font):
    """Окно мага: предыдущее (мелко) · текущее (крупно, подсвечено) · следующее (мелко). Смена — C/V или Q/ЛКМ."""
    prev, cur, nxt = spells.spellbook(pl)
    if cur is None: return
    defs = CFG.get("skills", {})
    base = layout().get("weapon1", [64, VIEW_H - 56, 48])
    x0 = int(base[0]); small, big, gap = 40, 56, 8
    top_big = int(base[1]) - 8; bottom = top_big + big   # крупная ячейка чуть выше, подписи помещаются
    if prev and prev != cur: spell_cell(scr, pl, prev, x0, bottom - small, small, font)
    cx = x0 + small + gap
    rc = spell_cell(scr, pl, cur, cx, top_big, big, font, active=True)
    nx = cx + big + gap
    has_next = bool(nxt and nxt not in (cur, prev))
    if has_next: spell_cell(scr, pl, nxt, nx, bottom - small, small, font)
    nm = font.render(defs.get(cur, {}).get("name", cur), True, (235, 225, 255))
    scr.blit(nm, (rc.centerx - nm.get_width() // 2, rc.y - nm.get_height() - 2))
    if prev != cur or has_next:
        label(scr, font, "C/V", nx + 2, bottom - small - 13, (170, 170, 195))


def icons(scr, pl, font):
    Wp = CFG["weapons"]
    portrait(scr, pl, font)

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
        r = slot(scr, 3, spells.icon_path(sid, skill), lambda r: pg.draw.circle(scr, skill.get("color", [150, 130, 220]), r.center, 13), border=tuple(skill.get("color", [150, 130, 220])), layout_key="skill")
        label(scr, font, "Q", r.x + 4, r.y + 3, (255, 230, 150))
        chan = channel_overlay(scr, pl, sid, r, font, tuple(skill.get("color", [150, 130, 220])))   # удерживаемое заклинание: убывающий индикатор
        left = max(0.0, getattr(pl, "skill_cooldowns", {}).get(sid, 0.0))
        if chan: pass
        elif left > 0:
            veil = pg.Surface(r.size, pg.SRCALPHA); pg.draw.rect(veil, (8, 8, 18, 165), veil.get_rect(), border_radius=8); scr.blit(veil, r)
            label(scr, font, str(int(left + .99)), r.centerx - 4, r.centery - 8, (255, 255, 255))
        else:
            pg.draw.circle(scr, (100, 240, 150), (r.right - 7, r.bottom - 7), 4)
        nm = font.render(skill.get("name", sid), True, (225, 220, 245))
        scr.blit(nm, (r.x + (r.w - nm.get_width()) // 2, r.y - nm.get_height() - 2))


def draw_boss_bar(scr, mobs, font):
    """Большая настраиваемая полоса здоровья активного босса в верхней части экрана."""
    boss = next((m for m in mobs if m.d.get("boss") and m.hp > 0), None)
    if boss is None: return
    cfg = CFG.get("boss", {}).get("bar", {})
    x = int(cfg.get("x", (W - cfg.get("w", 620)) / 2))
    y = int(cfg.get("y", 34)); w = int(cfg.get("w", 620)); h = int(cfg.get("h", 22))
    ratio = max(0.0, min(1.0, boss.hp / max(1, boss.maxhp)))
    back = sprite(cfg.get("back_skin"), w, h) if cfg.get("back_skin") else None
    fill = sprite(cfg.get("fill_skin"), w, h) if cfg.get("fill_skin") else None
    frame = sprite(cfg.get("frame_skin"), w, h) if cfg.get("frame_skin") else None
    if back: scr.blit(back, (x, y))
    else: pg.draw.rect(scr, tuple(cfg.get("back", [35, 18, 25])), (x, y, w, h), border_radius=int(cfg.get("radius", 6)))
    fw = int(w * ratio)
    if fw:
        if fill:
            scr.blit(fill, (x, y), pg.Rect(0, 0, fw, h))
        else:
            pg.draw.rect(scr, tuple(cfg.get("fill", [190, 38, 55])), (x, y, fw, h), border_radius=int(cfg.get("radius", 6)))
    if frame: scr.blit(frame, (x, y))
    else: pg.draw.rect(scr, tuple(cfg.get("border", [235, 190, 150])), (x, y, w, h), max(1, int(cfg.get("border_width", 2))), border_radius=int(cfg.get("radius", 6)))
    title = str(CFG.get("boss", {}).get("name", boss.d.get("name", "БОСС")))
    title_font = pg.font.SysFont("arial,dejavusans,freesans", int(cfg.get("font_size", 18)), bold=True)
    label = title_font.render(title, True, tuple(cfg.get("text", [255, 235, 220])))
    scr.blit(label, label.get_rect(center=(x + w // 2, y - int(cfg.get("title_gap", 12)) - label.get_height() // 2)))
    if cfg.get("show_numbers", True):
        nums = font.render(f"{max(0, int(boss.hp))} / {int(boss.maxhp)}", True, tuple(cfg.get("number_color", [255, 255, 255])))
        scr.blit(nums, nums.get_rect(center=(x + w // 2, y + h // 2)))
    # Моргарт: пока живы руки, голова под щитом; под её полосой — общая полоса здоровья рук.
    hands = getattr(boss, "hands", None)
    if hands is not None and hands.list:
        left = hands.alive_count()
        if left and boss.head_shielded():
            shade = pg.Surface((w, h), pg.SRCALPHA); shade.fill((90, 90, 110, 150)); scr.blit(shade, (x, y))
        if left:
            hy = y + h + 6; hh = max(8, h // 2)
            pg.draw.rect(scr, tuple(cfg.get("back", [35, 18, 25])), (x, hy, w, hh), border_radius=4)
            pg.draw.rect(scr, (255, 170, 60), (x, hy, int(w * hands.hp_ratio()), hh), border_radius=4)
            pg.draw.rect(scr, tuple(cfg.get("border", [235, 190, 150])), (x, hy, w, hh), 1, border_radius=4)
            txt = font.render(f"РУКИ {left}/{len(hands.list)}" + ("  —  голова под щитом" if boss.head_shielded() else ""), True, (255, 235, 200))
            scr.blit(txt, txt.get_rect(center=(x + w // 2, hy + hh // 2)))
