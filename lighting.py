"""Освещение: блоки света на картах, темнота, мягкие пятна света, мерцание, искры и ореолы.

Блок света — любой символ легенды с полем "light" (физически это пустая клетка, сквозь неё можно ходить):
    "*": {"light": "torch"}                    — заготовка из data/maps.json -> "lights"
    "Q": {"light": {"color": [255, 80, 60], "radius": 200, "flicker": "pulse", "draw": "orb"}}   — свой свет прямо в легенде
    "Z": {"type": "wall", "light": "crystal"}  — светящаяся стена
Готовые символы (общая легенда data/maps.json):  *  факел   o  фонарь   +  кристалл   %  магическая сфера

Поля света: color [r, g, b] или название цвета (см. COLOR_NAMES: "red"/"красный", "green"/"зелёный" ...),
strength 1..5 — сила света (1 — слабый огонёк, 3 — обычный, 5 — очень яркий; меняет радиус и яркость),
preset — от какой заготовки взять остальное ("torch", "lantern", "crystal", "orb", "glow" — невидимый свет),
radius (px), intensity (0..1.5), flicker: "torch" (живое пламя) | "pulse" (дыхание) | "none",
speed (скорость мерцания), offset [x, y] (центр света от центра клетки), draw: "torch" | "lantern" | "crystal" | "orb" | "none"
(как нарисовать сам источник; "none" — только свет, например под свою картинку в "sprite"), embers: true — искры над пламенем.

Карта (data/maps/<id>.json):
    "darkness": 0.6        — насколько темно вне света (0 — светло, 1 — кромешная тьма). Если не задано, а на карте есть
                             блоки света, берётся lighting.default_darkness; если блоков нет — карта не затемняется.
    "ambient": [r, g, b]   — оттенок темноты (по умолчанию тёмно-синий).
Общие настройки — data/maps.json -> "lighting": свет вокруг игрока, свечение снарядов, качество.
Мобы светятся, если в data/mobs.json у моба есть "light": {"color": [...], "radius": 90}.
"""
import math, random
import pygame as pg
from core import CFG, T, W, VIEW_H

PRESETS = {   # если в data/maps.json нет своих "lights"
    "torch":   {"color": [255, 150, 60], "radius": 190, "intensity": 1.0, "flicker": "torch", "speed": 1.0, "offset": [0, -6], "draw": "torch", "embers": True},
    "lantern": {"color": [255, 214, 150], "radius": 230, "intensity": .9, "flicker": "pulse", "speed": .35, "offset": [0, -2], "draw": "lantern"},
    "crystal": {"color": [110, 210, 255], "radius": 170, "intensity": .85, "flicker": "pulse", "speed": .8, "offset": [0, 2], "draw": "crystal"},
    "orb":     {"color": [190, 110, 255], "radius": 200, "intensity": .9, "flicker": "pulse", "speed": 1.4, "offset": [0, 0], "draw": "orb"},
    "glow":    {"color": [255, 230, 190], "radius": 200, "intensity": .85, "flicker": "pulse", "speed": .3, "offset": [0, 0], "draw": "none"},
}
# Цвета света по названию (можно писать по-русски или по-английски).
COLOR_NAMES = {
    "warm": [255, 150, 60], "white": [255, 244, 228], "red": [255, 60, 45], "orange": [255, 120, 30], "yellow": [255, 220, 80],
    "green": [90, 255, 110], "cyan": [90, 225, 255], "blue": [70, 120, 255], "purple": [185, 95, 255], "pink": [255, 110, 200],
    "тёплый": [255, 150, 60], "теплый": [255, 150, 60], "белый": [255, 244, 228], "красный": [255, 60, 45], "оранжевый": [255, 120, 30],
    "жёлтый": [255, 220, 80], "желтый": [255, 220, 80], "зелёный": [90, 255, 110], "зеленый": [90, 255, 110], "голубой": [90, 225, 255],
    "синий": [70, 120, 255], "фиолетовый": [185, 95, 255], "розовый": [255, 110, 200],
}
# Сила 1..5: (множитель радиуса, множитель яркости).
STRENGTH = {1: (.5, .65), 2: (.72, .82), 3: (1.0, 1.0), 4: (1.32, 1.12), 5: (1.7, 1.25)}


def color_of(c, default=(255, 220, 160)):
    """[r, g, b] | "#ff8800" | название -> [r, g, b] или None, если не понять."""
    if isinstance(c, str):
        c = c.strip().lower()
        if c.startswith("#") and len(c) == 7:
            try: return [int(c[i:i + 2], 16) for i in (1, 3, 5)]
            except ValueError: return None
        return list(COLOR_NAMES[c]) if c in COLOR_NAMES else None
    try: return [max(0, min(255, int(v))) for v in c[:3]] if len(c) >= 3 else None
    except (TypeError, ValueError): return None
DEFAULTS = {"default_darkness": .68, "ambient": [14, 14, 30], "resolution": 3,
            "player_light": {"color": [255, 236, 210], "radius": 130, "intensity": .55},
            "projectile_light": True, "halo": True, "glow": .2}

_GRAD, _HALO, _EMBERS, _INV = {}, {}, {}, {}
_last_tick = [0]


def settings():
    return {**DEFAULTS, **CFG["maps"].get("lighting", {})}


def preset(spec):
    """Запись "light" из легенды -> полный словарь параметров (или None)."""
    if not spec: return None
    lights = {**PRESETS, **CFG["maps"].get("lights", {})}
    if isinstance(spec, str):
        base = lights.get(spec)
        return dict(base) if base else None
    if not isinstance(spec, dict): return None
    base = lights.get(spec.get("preset", spec.get("type", "")), {})
    out = {**PRESETS["glow"], **base, **spec}
    out["color"] = color_of(out.get("color")) or list(base.get("color", PRESETS["glow"]["color"]))
    try: lvl = int(spec.get("strength", 0))
    except (TypeError, ValueError): lvl = 0
    if lvl:
        rk, ik = STRENGTH[max(1, min(5, lvl))]
        out["radius"] = float(base.get("radius", out["radius"])) * rk if "radius" not in spec else out["radius"]
        out["intensity"] = float(base.get("intensity", out["intensity"])) * ik if "intensity" not in spec else out["intensity"]
        out["size"] = .75 + .1 * max(1, min(5, lvl))   # сам светильник чуть больше у сильного света
    return out


def find_lights(room):
    """Источники света карты: [(x, y, параметры, фаза)] — центр в пикселях мира."""
    out = []
    for c, r, e in room.cells():
        p = preset(e.get("light"))
        if not p: continue
        ox, oy = p.get("offset", [0, 0])
        out.append((c * T + T / 2 + ox, r * T + T / 2 + oy, p, (c * 12.9898 + r * 78.233) % 6.283))
    return out


def darkness_of(room):
    md = room.d
    if "darkness" in md: return max(0.0, min(1.0, float(md["darkness"])))
    if room.lights: return float(settings()["default_darkness"])
    return max(0.0, min(1.0, float(CFG["maps"].get("darkness", 0))))


# ---------------- мерцание ----------------
def flicker_k(p, t, phase):
    """Плавный множитель яркости ~0.85..1.1: сумма синусов — живое пламя без рывков."""
    sp = float(p.get("speed", 1.0)); kind = p.get("flicker", "none")
    if kind == "torch":
        return 1 + .07 * math.sin(t * 7.3 * sp + phase) + .04 * math.sin(t * 13.7 * sp + phase * 2.1) + .025 * math.sin(t * 23.1 * sp + phase * 3.7)
    if kind == "pulse":
        return 1 + .09 * math.sin(t * 2.4 * sp + phase)
    return 1.0


# ---------------- градиенты ----------------
def gradient(color, r):
    """Мягкое круглое пятно цвета color радиуса r (кэш). Падение яркости — (1 - d²)², без видимой границы."""
    key = (tuple(color), r)
    g = _GRAD.get(key)
    if g is None:
        if len(_GRAD) > 600: _GRAD.clear()
        g = pg.Surface((2 * r + 2, 2 * r + 2)); g.fill((0, 0, 0))
        for i in range(r, 0, -1):
            f = (1 - (i / r) ** 2) ** 2.6
            pg.draw.circle(g, (int(color[0] * f), int(color[1] * f), int(color[2] * f)), (r + 1, r + 1), i)
        _GRAD[key] = g
    return g


def inv_gradient(color, r):
    """То же пятно «наоборот» (255 - свет) — для смешивания света по принципу «экрана»: свет не выжигает картинку в белое."""
    key = (tuple(color), r)
    g = _INV.get(key)
    if g is None:
        if len(_INV) > 600: _INV.clear()
        g = pg.Surface((2 * r + 2, 2 * r + 2)); g.fill((255, 255, 255))
        g.blit(gradient(color, r), (0, 0), special_flags=pg.BLEND_RGB_SUB)
        _INV[key] = g
    return g


def halo(color, r):
    key = (tuple(color), r)
    h = _HALO.get(key)
    if h is None:
        if len(_HALO) > 200: _HALO.clear()
        h = gradient([int(c * .42) for c in color], r).copy(); _HALO[key] = h
    return h


def mix(a, b, k):
    """Цвет между a и b (k = 0 -> a, 1 -> b)."""
    return [int(a[i] + (b[i] - a[i]) * k) for i in range(3)]


def scaled(color, k):
    return [max(0, min(255, int(c * k))) for c in color]


# ---------------- источники на карте (рисуются в мире) ----------------
def draw_sources(v, room, t, dt):
    """Сами светильники: пламя факела, фонарь, кристалл, сфера + искры над огнём."""
    embers = _EMBERS.setdefault(room.id, [])
    for x, y, p, ph in room.lights:
        kind = p.get("draw", "none"); col = p.get("color", [255, 200, 120]); k = flicker_k(p, t, ph)
        X, Y = int(x), int(y); z = float(p.get("size", 1.0))   # сильный свет — светильник чуть крупнее
        if kind == "torch":
            pg.draw.rect(v, (70, 46, 30), (X - 2, Y + 2, 5, 16), border_radius=1)
            pg.draw.rect(v, (120, 88, 56), (X - 5, Y, 11, 4), border_radius=1)
            sway = math.sin(t * 5.1 + ph) * 2.0
            hgt = (15 * k + 2.5 * math.sin(t * 11 + ph)) * z
            for scale, c in ((1.0, scaled(col, 1.0)), (.68, mix(col, (255, 230, 150), .55)), (.36, mix(col, (255, 252, 235), .85))):
                hw, hh = (6 * scale + 1) * z, hgt * scale + 3
                pg.draw.polygon(v, c, [(X - hw, Y + 1), (X + sway * scale, Y - hh), (X + hw, Y + 1), (X, Y + 3)])
        elif kind == "lantern":
            sw = math.sin(t * 1.3 + ph) * 1.2
            pg.draw.line(v, (60, 55, 60), (X, Y - 14), (X + sw, Y - 8), 2)
            body = pg.Rect(0, 0, 12, 14); body.center = (X + sw, Y)
            pg.draw.rect(v, scaled(col, .9 * k), body.inflate(-4, -4), border_radius=3)
            pg.draw.rect(v, (255, 245, 215), body.inflate(-8, -8), border_radius=2)
            pg.draw.rect(v, (55, 48, 46), body, 2, border_radius=3)
            pg.draw.rect(v, (55, 48, 46), (body.x + 2, body.y - 3, 8, 3))
        elif kind == "crystal":
            bob = math.sin(t * 1.6 + ph) * 2
            a, b_, c_ = 11 * z, 6 * z, 10 * z
            pts = [(X, Y - a + bob), (X + b_, Y - 1 + bob), (X, Y + c_ + bob), (X - b_, Y - 1 + bob)]
            pg.draw.polygon(v, scaled(col, .75 + .25 * k), pts)
            pg.draw.polygon(v, mix(col, (255, 255, 255), .35), [(X, Y - a + bob), (X + b_, Y - 1 + bob), (X, Y + 1 + bob)])
            pg.draw.polygon(v, (235, 250, 255), pts, 1)
        elif kind == "orb":
            bob = math.sin(t * 1.9 + ph) * 3
            r0 = (6 + 1.2 * math.sin(t * 2.8 * p.get("speed", 1) + ph)) * z
            pg.draw.circle(v, scaled(col, .7), (X, int(Y + bob)), int(r0 + 2))
            pg.draw.circle(v, mix(col, (255, 255, 255), .2), (X, int(Y + bob)), int(r0))
            pg.draw.circle(v, (250, 240, 255), (X - 2, int(Y + bob - 2)), max(1, int(r0 / 2.6)))
        if p.get("embers") and dt > 0 and random.random() < dt * 7 and len(embers) < 160:
            embers.append([x + random.uniform(-3, 3), y - 10, random.uniform(-8, 8), random.uniform(-45, -25), random.uniform(.7, 1.4), 0.0, col])
    alive = []
    for e in embers:   # искры: поднимаются, покачиваются, гаснут
        e[5] += dt
        if e[5] >= e[4]: continue
        e[0] += (e[2] + math.sin(e[5] * 6 + e[1]) * 10) * dt; e[1] += e[3] * dt
        f = 1 - e[5] / e[4]
        pg.draw.circle(v, mix(e[6], (255, 245, 200), .45 * f), (int(e[0]), int(e[1])), 1 if f < .5 else 2)
        alive.append(e)
    _EMBERS[room.id] = alive


# ---------------- темнота и свет (поверх готового кадра) ----------------
def apply(scr, room, cam, view_size, players, mobs, projs, t):
    """Свет собирается на маленькой карте освещённости, плавно растягивается на экран и умножается на кадр:
    вне света — темнота, в свете — родные цвета с оттенком источника. Потом — лёгкие ореолы вокруг огня."""
    dark = darkness_of(room)
    if dark <= 0: return
    cfg = settings(); res = max(1, int(cfg.get("resolution", 3)))
    cw, ch = view_size
    kx, ky = W / max(1, cw), VIEW_H / max(1, ch)          # мир -> экран
    lw, lh = max(1, W // res), max(1, VIEW_H // res)
    amb_tint = room.d.get("ambient", cfg.get("ambient"))
    amb = [int(255 + (c - 255) * dark) for c in amb_tint]
    # Храним «темноту» D = 255 - свет и для каждого источника умножаем её на (255 - пятно):
    # итог 1 - (1 - a)(1 - b) — источники складываются мягко и никогда не засвечивают кадр целиком.
    dmap = pg.Surface((lw, lh)); dmap.fill([255 - c for c in amb])
    sources = []
    for x, y, p, ph in room.lights:
        sources.append((x, y, p.get("color"), p.get("radius", 180) * flicker_k(p, t, ph), p.get("intensity", 1), p))
    pl_cfg = cfg.get("player_light")
    if pl_cfg:
        for p in players:
            if p.hp > 0: sources.append((p.cx, p.cy - 6, pl_cfg.get("color"), pl_cfg.get("radius", 130), pl_cfg.get("intensity", .55), None))
    for m in mobs:
        ml = m.d.get("light")
        if ml: sources.append((m.cx, m.cy, ml.get("color", m.d.get("color", [200, 200, 255])), ml.get("radius", 90), ml.get("intensity", .7), None))
    if cfg.get("projectile_light", True):
        for q in projs:
            sources.append((q.x, q.y, q.d.get("light_color", q.color), q.d.get("light_radius", max(36, q.r * 9)), .75, None))
    glow = float(cfg.get("glow", .2)); tmap = None   # цветная «аура» источников поверх кадра
    if glow > 0: tmap = pg.Surface((lw, lh)); tmap.fill((0, 0, 0))
    halos = []
    for x, y, col, rad, inten, p in sources:
        sx, sy = (x - cam[0]) * kx, (y - cam[1]) * ky; sr = rad * kx
        if sx < -sr or sy < -sr or sx > W + sr or sy > VIEW_H + sr: continue
        r = max(2, int(sr / res))
        pos = (int(sx / res) - r - 1, int(sy / res) - r - 1)
        dmap.blit(inv_gradient(scaled(col or [255, 255, 255], inten), r), pos, special_flags=pg.BLEND_RGB_MULT)
        if tmap is not None and p is not None:
            tmap.blit(gradient(scaled(col or [255, 255, 255], inten * glow * dark), r), pos, special_flags=pg.BLEND_RGB_ADD)
        if p is not None and cfg.get("halo", True) and p.get("draw", "none") != "none":
            halos.append((sx, sy, col, max(8, int(36 * kx * flicker_k(p, t * 1.3, 0)))))
    lmap = pg.Surface((lw, lh)); lmap.fill((255, 255, 255)); lmap.blit(dmap, (0, 0), special_flags=pg.BLEND_RGB_SUB)
    scr.blit(pg.transform.smoothscale(lmap, (W, VIEW_H)), (0, 0), special_flags=pg.BLEND_RGB_MULT)
    if tmap is not None: scr.blit(pg.transform.smoothscale(tmap, (W, VIEW_H)), (0, 0), special_flags=pg.BLEND_RGB_ADD)
    for sx, sy, col, r in halos:   # мягкое сияние прямо вокруг огня
        h = halo(col, r)
        scr.blit(h, (int(sx) - r - 1, int(sy) - r - 1), special_flags=pg.BLEND_RGB_ADD)


def frame_time():
    """(t, dt) по реальным часам — мерцание идёт плавно и одинаково у всех игроков."""
    now = pg.time.get_ticks()
    dt = 0.0 if not _last_tick[0] else min(.1, (now - _last_tick[0]) / 1000)
    _last_tick[0] = now
    return now / 1000, dt
