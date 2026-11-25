"""Планшет заклинаний мага (герой с "cast_power": true в data/characters.json) — замена прежней
колонки prev/cur/next (hud.book_draw) у левого края экрана.

Квадратный планшет (ассет assets/ui/spell_tablet.png, генератор — make_tablet_textures.py; нет файла —
процедурная заглушка) с ПЯТЬЮ ячейками заклинаний: второй предыдущий · предыдущий · ТЕКУЩЕЕ (крупно) ·
следующий · второй следующий. Список — spells.active_skills(pl), текущее — pl.skill_index; ячейки чуть
мельче прежней книги. Колесо мыши над планшетом листает заклинания (действия next/prev — те же, что
клавиши C/V); клик по планшету ничего не колдует — у мага ЛКМ каст не запускает, заклинание применяет
только клавиша навыка (Q).

Сила каста — ползунок справа от ячейки ВЫБРАННОГО (текущего) заклинания — у соседей ползунка нет: 0 —
минимальная (быстрый, дешёвый и слабый каст), 1 — максимальная (урон, цена маны, перезарядка и время
каста растут пропорционально — множители spells.POWER). Ползунок двигают кликом/перетаскиванием или
колесом мыши над ним; сила хранится по каждому заклинанию в pl.cast_power
(spells.cast_power/set_cast_power) и сохраняется в сейве (save_io). Каст — три шага: выбрал заклинание
-> выставил силу -> применил (Q).

Кнопка-шеврон на левом краю планшета прячет его за левый край экрана (освобождая место); в свёрнутом
состоянии у края остаётся маленькая кнопка (assets/ui/spell_tablet_tab.png), возвращающая планшет.
Состояние — SETTINGS["tablet_open"], положение и размер — ключ раскладки HUD "tablet" ([x, y, сторона],
редактор F2). Мышь планшету раздаёт Game.run -> spell_tablet.event(); в сети смена заклинаний идёт
через s.act("next"/"prev"), сила каста — действием "skpow:<sid>:<сила>" (Game.apply_action)."""
import math
import pygame as pg
from core import CFG, SETTINGS
from anim import sprite
import spells

TABLET_TEX = "ui/spell_tablet.png"    # квадратный планшет (масштабируется под ключ "tablet")
TAB_TEX = "ui/spell_tablet_tab.png"   # кнопка «вернуть планшет» в свёрнутом состоянии
SLOT_SIZES = (0.11, 0.15, 0.20, 0.15, 0.11)   # доли стороны планшета: слоты -2..2 (текущий — 0)
GAP_FRAC = 0.024                      # зазор между соседними ячейками (доля стороны)
S = {"open": bool(SETTINGS.get("tablet_open", True)), "a": 0.0, "b": 0.0, "t0": 0, "drag": None, "drag_sid": None}
S["a"] = S["b"] = 0.0 if S["open"] else 1.0
HITS = {}   # интерактивные зоны последнего кадра (body, hide, tab, bars{sid:Rect}) — их читает event()


def enabled():
    """Планшет у текущего героя: поле "cast_power": true (пока только маг)."""
    return bool(CFG.get("character", {}).get("cast_power"))


def rect():
    """Прямоугольник планшета: ключ раскладки HUD "tablet" ([x, y верха, сторона]; редактор F2)."""
    import hud
    a = hud.layout().get("tablet", [8, 110, 210])
    side = max(120, int(a[2] if len(a) > 2 else 210))
    return pg.Rect(int(a[0]), int(a[1]), side, side)


def _slide():
    """0 (планшет на экране) .. 1 (уехал за левый край) — плавный переход между a и b за ~0.24 с."""
    if S["a"] == S["b"]:
        return S["b"]
    k = min(1.0, (pg.time.get_ticks() - S["t0"]) / 240.0)
    k = k * k * (3.0 - 2.0 * k)
    v = S["a"] + (S["b"] - S["a"]) * k
    if k >= 1.0:
        S["a"] = S["b"] = v
    return v


def _set_open(g, v):
    """Спрятать (False) или вернуть (True) планшет; состояние сохраняется в settings.json."""
    S["a"] = _slide(); S["b"] = 0.0 if v else 1.0; S["t0"] = pg.time.get_ticks()
    S["open"] = bool(v); SETTINGS["tablet_open"] = S["open"]
    if hasattr(g, "save_settings"):
        g.save_settings()


# ---------------- раскладка ----------------

def _geom(r):
    """Раскладка планшета r: (cells, bars, cys, sizes) — ячейки и полосы силы по слотам -2..2.
    Ровный шаг дорожки = текущая ячейка + зазор; слева зарезервировано место под кнопку-шеврон."""
    side = r.w
    sizes = [max(10, int(round(f * side))) for f in SLOT_SIZES]
    gap = max(3, int(round(GAP_FRAC * side)))
    step = sizes[2] + gap
    cys = [r.centery + (i - 2) * step for i in range(5)]
    cell_x = r.x + max(18, int(round(side * 0.085)))    # правее кнопки «спрятать» на левом краю
    bar_x = cell_x + sizes[2] + max(5, int(round(side * 0.03)))
    bar_w = r.right - bar_x - max(8, int(round(side * 0.05)))
    cells, bars = [], []
    for i, sz in enumerate(sizes):
        cells.append(pg.Rect(cell_x, cys[i] - sz // 2, sz, sz))
        bh = max(4, int(round(sz * 0.26)))
        bars.append(pg.Rect(bar_x, cys[i] - bh // 2, bar_w, bh))
    return cells, bars, cys, sizes


def _hide_rect(r):
    """Кнопка-шеврон «спрятать планшет» на его левом краю."""
    return pg.Rect(r.x + 2, r.centery - 9, 13, 18)


def _tab_rect(r):
    """Кнопка «показать планшет» в свёрнутом состоянии — торчит у левого края экрана."""
    return pg.Rect(0, r.centery - 16, 20, 32)


def _track(vals, p):
    """Значение на дробной позиции p дорожки (-2..2): линейная интерполяция якорей vals (за краем — экстраполяция)."""
    p = max(-2.6, min(2.6, float(p)))
    i = max(0, min(3, int(math.floor(p)) + 2))
    return vals[i] + (vals[i + 1] - vals[i]) * (p - (i - 2))


def _window(n):
    """Какие слоты дорожки показывать, чтобы заклинания не дублировались: пять есть — все пять."""
    if n >= 5: return (-2, 2)
    if n == 4: return (-2, 1)
    if n >= 2: return (-1, 1)
    return (0, 0)


# ---------------- отрисовка ----------------

def draw(scr, pl, font):
    """Планшет мага: пять ячеек заклинаний, справа от каждой — ползунок силы каста. Заполняет HITS для event()."""
    HITS.clear()
    if not enabled():
        return
    act = spells.active_skills(pl)
    if not act:
        return
    n, k = len(act), pl.skill_index % len(act)
    r = rect(); slide = _slide()
    if slide < 0.999:
        _draw_body(scr, pl, font, r.move(int(-(r.w + 6) * slide), 0), act, n, k, 1.0 - slide)
    if slide > 0.001:
        _draw_tab(scr, r, slide)


def _draw_body(scr, pl, font, r, act, n, k, vis):
    """Тело планшета: текстура, ячейки на дорожке, ползунки силы, кнопка «спрятать», строка-подпись снизу."""
    import hud
    tex = sprite(TABLET_TEX, r.w, r.h)
    if tex:
        scr.blit(tex, r)
    else:
        _default_body(scr, r)
    HITS["body"] = r.copy()
    hb = _hide_rect(r); HITS["hide"] = hb
    base = pg.Surface(hb.size, pg.SRCALPHA)
    pg.draw.rect(base, (58, 48, 88, int(235 * vis)), base.get_rect(), border_radius=5)
    pg.draw.rect(base, (172, 152, 214, int(235 * vis)), base.get_rect(), 1, border_radius=5)
    scr.blit(base, hb)
    _chevron(scr, hb, left=True, alpha=int(255 * vis))
    cells, bars, cys, sizes = _geom(r)
    off = hud.book_scroll(pl, "mage", n, k)
    lo, hi = _window(n)
    clip = scr.get_clip(); scr.set_clip(r.inflate(-6, -6))
    HITS["bars"] = {}
    for slot in sorted(range(lo, hi + 1), key=lambda s: -abs(s)):    # наружные раньше, текущий поверх всех
        if n == 1 and slot != 0:
            continue
        p = slot + off
        if abs(p) > 2.55:
            continue
        i = slot + 2
        sid = act[(k + slot) % n]
        sk = CFG.get("skills", {}).get(sid, {})
        hold = spells.is_hold(sk); pw = spells.cast_power(pl, sid)
        a2 = abs(p)
        alpha = 1.0 if a2 <= 2.0 else max(0.0, 1.0 - (a2 - 2.0) / 0.55)
        cy, sz = _track(cys, p), _track(sizes, p)
        hud.book_cell(scr, pl, font, sid, cells[i].centerx, cy, sz,
                      alpha * vis, slot == 0, cost=_cost(sk, pw, hold),
                      extra=hud.spell_extra(pl) if slot == 0 else None, per_sec=hold)
        if slot == 0:   # ползунок силы — только у выбранного заклинания, едет вместе с его ячейкой
            bh = max(4, int(round(sz * 0.26)))
            bar = pg.Rect(bars[i].x, int(cy) - bh // 2, bars[i].w, bh)
            _power_bar(scr, bar, pw, tuple(sk.get("color", [150, 130, 220])), alpha * vis)
            HITS["bars"][sid] = bar
    scr.set_clip(clip)
    _draw_info(scr, pl, font, r, act[k], vis)


def _cost(sk, pw, hold):
    """Цена маны для подписи на ячейке (сила каста дорожает ману); None — подписи не будет."""
    mc = float(sk.get("mana_cost", 10.0 if hold else 0.0) or 0.0)
    return mc * spells.power_scale(pw, "mana") if mc else None


def _power_bar(scr, bar, pw, color, alpha):
    """Ползунок силы каста (0..1) у выбранного заклинания: тёмный жёлоб, заполнение цветом заклинания,
    деления четвертей и ручка; рамка выделяет активный ползунок."""
    if alpha <= 0.02:
        return
    col = tuple(min(255, int(c * alpha)) for c in color)
    pg.draw.rect(scr, tuple(int(c * alpha) for c in (18, 16, 30)), bar, border_radius=3)
    w = int(round(bar.w * max(0.0, min(1.0, pw))))
    if w > 0:
        pg.draw.rect(scr, col, (bar.x, bar.y, w, bar.h), border_radius=3)
    for q in range(1, 4):   # деления четвертей
        x = bar.x + int(bar.w * q / 4)
        pg.draw.line(scr, tuple(int(c * alpha) for c in (70, 64, 100)), (x, bar.y + 1), (x, bar.bottom - 1))
    kr = bar.h // 2 + 2
    pg.draw.circle(scr, tuple(int(c * alpha) for c in (240, 236, 255)), (bar.x + w, bar.centery), kr)
    pg.draw.circle(scr, col, (bar.x + w, bar.centery), max(1, kr - 2))
    rim = tuple(min(255, int(c * (0.4 + 0.6 * alpha))) for c in color)
    pg.draw.rect(scr, rim, bar.inflate(2, 2), 1, border_radius=4)


def _draw_info(scr, pl, font, r, sid, vis):
    """Под планшетом: название текущего заклинания, цена маны с этой силой и сама сила в процентах."""
    if vis <= 0.05:
        return
    sk = CFG.get("skills", {}).get(sid, {})
    pw = spells.cast_power(pl, sid)
    hold = spells.is_hold(sk)
    mc = float(sk.get("mana_cost", 0.0) or 0.0) * spells.power_scale(pw, "mana")
    cost_s = f"{mc:g}/с" if hold else (f"{mc:g} маны" if mc else "")
    parts = [str(sk.get("name", sid))]
    if cost_s:
        parts.append(cost_s)
    parts.append(f"сила {int(round(pw * 100))}%")
    col = tuple(sk.get("color", [232, 224, 255])[:3])
    img = font.render(" · ".join(parts), True, tuple(min(255, int(c + (255 - c) * 0.35)) for c in col))
    img.set_alpha(int(255 * vis))
    scr.blit(img, (r.x + 4, r.bottom + 3))


def _default_body(scr, r):
    """Заглушка, если assets/ui/spell_tablet.png нет: тёмная доска с латунной рамкой."""
    pg.draw.rect(scr, (36, 31, 52), r, border_radius=12)
    pg.draw.rect(scr, (128, 108, 172), r, 2, border_radius=12)
    pg.draw.rect(scr, (56, 47, 82), r.inflate(-8, -8), 1, border_radius=9)


def _draw_tab(scr, r, slide):
    """Свёрнутый планшет: маленькая кнопка у левого края экрана, возвращает планшет по клику."""
    tr = _tab_rect(r)
    HITS["tab"] = tr
    a = int(255 * max(0.0, min(1.0, (slide - 0.25) / 0.75)))   # проступает по мере уезда планшета
    if a <= 4:
        return
    tex = sprite(TAB_TEX, tr.w, tr.h)
    if tex:
        tex = tex.copy(); tex.set_alpha(a); scr.blit(tex, tr)
    else:
        s = pg.Surface(tr.size, pg.SRCALPHA)
        pg.draw.rect(s, (44, 38, 66, a), s.get_rect(), border_radius=6)
        pg.draw.rect(s, (150, 130, 190, a), s.get_rect(), 2, border_radius=6)
        scr.blit(s, tr)
        _chevron(scr, tr, left=False, alpha=a)


def _chevron(scr, rect, left=True, color=(228, 222, 252), alpha=255):
    """Треугольник-стрелка (‹ / ›) на кнопках планшета."""
    w, h = rect.w, rect.h
    pts = [(w - 3, 2), (w - 3, h - 2), (3, h / 2)] if left else [(3, 2), (3, h - 2), (w - 3, h / 2)]
    s = pg.Surface(rect.size, pg.SRCALPHA)
    pg.draw.polygon(s, (*color, max(0, alpha)), [(int(x), int(y)) for x, y in pts])
    scr.blit(s, rect)


# ---------------- мышь ----------------

def event(s, e):
    """Мышь планшета. True — событие съедено (не дойдёт до атаки/крафта). Роутинг — Game.run:
    у не-магов и вне игры сразу False; колесо листает заклинания или двигает ползунок силы,
    клик по кнопкам прячет/возвращает планшет, клик/перетаскивание по ползунку задаёт силу.
    Ползунок один — у выбранного (текущего) заклинания: силу меняют только ему."""
    if e.type not in (pg.MOUSEWHEEL, pg.MOUSEBUTTONDOWN, pg.MOUSEBUTTONUP, pg.MOUSEMOTION):
        return False
    if not enabled():
        return False
    pl = getattr(s, "pl", None)
    if pl is None or not spells.active_skills(pl):
        return False
    if e.type == pg.MOUSEWHEEL:
        pos = pg.mouse.get_pos()
        if HITS.get("body") and HITS["body"].collidepoint(pos):
            for sid, br in HITS.get("bars", {}).items():
                if br.inflate(6, 6).collidepoint(pos):
                    _set_power(s, pl, sid, spells.cast_power(pl, sid) + (0.1 if e.y > 0 else -0.1))
                    return True
            if e.y:
                s.act("prev" if e.y > 0 else "next")   # колесо листает заклинания (как V/C)
            return True
        return False
    if e.type == pg.MOUSEBUTTONDOWN and e.button in (4, 5):
        # События колеса старого формата над планшетом гасим (иначе прокрутится рецепт крафта).
        return bool(HITS.get("body") and HITS["body"].collidepoint(e.pos))
    if e.type == pg.MOUSEBUTTONDOWN and e.button == 1:
        if HITS.get("hide") and HITS["hide"].collidepoint(e.pos):
            _set_open(s, False); return True
        if HITS.get("tab") and HITS["tab"].collidepoint(e.pos):
            _set_open(s, True); return True
        for sid, br in HITS.get("bars", {}).items():
            if br.inflate(4, 4).collidepoint(e.pos):
                S["drag"], S["drag_sid"] = "bar", sid
                _set_power(s, pl, sid, _pw_of(br, e.pos))
                return True
        return bool(HITS.get("body") and HITS["body"].collidepoint(e.pos))   # клик по планшету — не каст
    if e.type == pg.MOUSEMOTION:
        if S.get("drag") != "bar":
            return False
        br = HITS.get("bars", {}).get(S.get("drag_sid"))
        if br is None:
            S["drag"] = None; return True
        _set_power(s, pl, S["drag_sid"], _pw_of(br, e.pos)); return True
    if e.type == pg.MOUSEBUTTONUP and e.button == 1 and S.get("drag") == "bar":
        S["drag"] = None; return True
    return False


def _pw_of(bar, pos):
    """Сила каста (0..1) по x курсора на ползунке bar."""
    if bar.w <= 1:
        return 0.0
    return max(0.0, min(1.0, (pos[0] - bar.x) / (bar.w - 1)))


def _set_power(s, pl, sid, pw):
    """Сохранить силу каста; в сети сообщить хосту действием skpow (Game.apply_action)."""
    spells.set_cast_power(pl, sid, pw)
    if getattr(s, "net", None) and s.net.in_game:
        s.net.local_action(f"skpow:{sid}:{spells.cast_power(pl, sid):.2f}")
