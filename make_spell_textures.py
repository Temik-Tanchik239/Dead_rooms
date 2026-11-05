"""Рисует текстуры заклинаний мага: иконки (assets/icons/skill_<id>.png) и анимированные снаряды
(assets/projectiles/<id заклинания>/1..4.png).

Запуск:   python make_spell_textures.py            — рисует только те файлы, которых ещё нет
          python make_spell_textures.py --force    — перерисовывает всё (затирает свои картинки с теми же именами!)

Это временные «программерские» текстуры в стиле остальных иконок игры. Чтобы поставить свои, просто положи
свой PNG с тем же именем (или папку кадров 1.png, 2.png, …) — игра подхватит его сама (см. README, «Иконка/Снаряд заклинания»).
Требуется Pillow:  pip install pillow
"""
import math, random, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

ASSETS = Path(__file__).resolve().parent / "assets"
OUTLINE = (24, 14, 36, 255)


# ------------------------------------------------------------------ мелкие помощники
def new(w, h): return Image.new("RGBA", (w, h), (0, 0, 0, 0))
def lerp(a, b, k): return a + (b - a) * k
def mix(c1, c2, k): return tuple(int(lerp(c1[i], c2[i], k)) for i in range(3)) + (255,)
def rgba(c, a=255): return (c[0], c[1], c[2], a)


def circle(d, c, r, fill):
    d.ellipse((c[0] - r, c[1] - r, c[0] + r, c[1] + r), fill=fill)


def with_outline(glyph, col=OUTLINE, grow=1):
    """Тёмный контур в 1 пиксель вокруг нарисованного (как у остальных спрайтов игры)."""
    a = glyph.split()[3].point(lambda v: 255 if v > 0 else 0)
    for _ in range(grow): a = a.filter(ImageFilter.MaxFilter(3))
    base = Image.new("RGBA", glyph.size, col); base.putalpha(a)
    base.alpha_composite(glyph); return base


def scaled(img, k): return img.resize((img.width * k, img.height * k), Image.NEAREST)


def comet(d, head, direction, length, radius, layers, rnd, flicker=1.2, step=0.8):
    """Огненный/ледяной хвост: цепочка кругов от головы назад, радиус уменьшается; layers — [(цвет, доля радиуса)] от внешнего к внутреннему."""
    dx, dy = direction; n = max(2, int(length / step)); px, py = -dy, dx
    for col, share in layers:
        for i in range(n, -1, -1):
            t = i / n
            off = (rnd.random() - .5) * 2 * flicker * t
            c = (head[0] + dx * t * length + px * off, head[1] + dy * t * length + py * off)
            r = radius * share * (1 - .85 * t) + 0.3
            circle(d, c, r, col)


def sparkle(d, x, y, col, big=False):
    d.point((x, y), fill=col)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)): d.point((x + dx, y + dy), fill=rgba(col[:3], 150 if big else 0))
    if big:
        for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2)): d.point((x + dx, y + dy), fill=rgba(col[:3], 120))


# ------------------------------------------------------------------ иконки (сетка 32x32 -> 64x64)
def icon_frame(accent):
    """Тёмная плитка с цветной рамкой, как у skill_nova / skill_heal."""
    im = new(32, 32); d = ImageDraw.Draw(im)
    dark = mix((10, 10, 18), accent, .22); light = mix((10, 10, 18), accent, .38)
    for y in range(32): d.line((0, y, 31, y), fill=mix(light, dark, y / 31))
    mask = new(32, 32); ImageDraw.Draw(mask).rounded_rectangle((0, 0, 31, 31), radius=5, fill=255)
    out = new(32, 32); out.paste(im, (0, 0), mask.split()[3])
    d = ImageDraw.Draw(out)
    d.rounded_rectangle((0, 0, 31, 31), radius=5, outline=rgba(accent), width=1)
    d.rounded_rectangle((1, 1, 30, 30), radius=4, outline=mix(accent, (0, 0, 0), .55), width=1)
    return out


def finish_icon(accent, glyph):
    fr = icon_frame(accent); fr.alpha_composite(with_outline(glyph)); return scaled(fr, 2)


def flame_streaks(d, head, back_deg, streaks, layers):
    """Острые языки пламени позади головы. streaks — [(поворот°, длина, ширина у основания)]; layers — [(цвет, доля размера)]."""
    for col, share in layers:
        for off, ln, wd in streaks:
            a = math.radians(back_deg + off); bx, by = math.cos(a), math.sin(a); px, py = -by, bx
            L, W = ln * share, wd * share
            d.polygon([(head[0] + px * W, head[1] + py * W), (head[0] + bx * L, head[1] + by * L), (head[0] - px * W, head[1] - py * W)], fill=col)


def icon_fireball():
    g = new(32, 32); d = ImageDraw.Draw(g); head = (21, 11)
    flame_streaks(d, head, 136, [(-28, 15, 3.6), (0, 20, 4.8), (28, 14, 3.4)],
                  [((205, 55, 30, 255), 1.0), ((255, 125, 40, 255), .76), ((255, 205, 80, 255), .5)])
    circle(d, head, 7, (215, 60, 30, 255)); circle(d, head, 6, (255, 135, 45, 255)); circle(d, (20.5, 10.5), 4.4, (255, 200, 80, 255))
    circle(d, (20, 10), 2.6, (255, 244, 185, 255)); d.point((19, 9), fill=(255, 255, 255, 255))
    for p in ((6, 10), (26, 24), (13, 27)): d.point(p, fill=(255, 200, 90, 255))
    return finish_icon((255, 140, 50), g)


def icon_ice_shard():
    g = new(32, 32); d = ImageDraw.Draw(g)
    A, B = (6, 27), (26, 5); ax, ay = B[0] - A[0], B[1] - A[1]; L = math.hypot(ax, ay); px, py = -ay / L, ax / L
    def pt(t, w): return (A[0] + ax * t + px * w, A[1] + ay * t + py * w)
    P1, P2 = pt(.55, 4.6), pt(.55, -4.6)
    d.polygon([B, P1, A], fill=(200, 245, 255, 255)); d.polygon([B, P2, A], fill=(80, 165, 235, 255))
    d.polygon([B, pt(.55, 1.6), pt(.2, .6)], fill=(255, 255, 255, 255))
    d.line([A, B], fill=(150, 215, 250, 255), width=1)
    for c, r in (((24, 23), 2.2), ((10, 8), 2.0)):
        d.polygon([(c[0], c[1] - r - 1), (c[0] + r, c[1]), (c[0], c[1] + r + 1), (c[0] - r, c[1])], fill=(170, 230, 255, 255))
    sparkle(d, 8, 21, (255, 255, 255, 255)); sparkle(d, 25, 14, (255, 255, 255, 255), True)
    return finish_icon((120, 220, 255), g)


def icon_arcane_orb():
    g = new(32, 32); d = ImageDraw.Draw(g)
    d.arc((4, 11, 28, 21), 180, 360, fill=(225, 175, 255, 255), width=1)
    for r, col in ((8.5, (80, 36, 160)), (7.5, (125, 70, 215)), (5.8, (175, 115, 250)), (3.8, (225, 190, 255))): circle(d, (16, 16), r, rgba(col))
    circle(d, (14, 14), 2.2, (255, 245, 255, 255))
    d.arc((4, 11, 28, 21), 0, 180, fill=(235, 195, 255, 255), width=1)
    d.arc((5, 12, 27, 20), 20, 160, fill=(255, 235, 255, 255), width=1)
    sparkle(d, 6, 6, (240, 210, 255, 255), True); sparkle(d, 26, 25, (240, 210, 255, 255), True); sparkle(d, 25, 6, (200, 150, 255, 255))
    return finish_icon((190, 130, 255), g)


def icon_frost_nova():
    g = new(32, 32); d = ImageDraw.Draw(g); C = (16, 16)
    for a in range(0, 360, 20):
        x, y = C[0] + math.cos(math.radians(a)) * 13.5, C[1] + math.sin(math.radians(a)) * 13.5
        if (a // 20) % 2 == 0: d.point((round(x), round(y)), fill=(110, 200, 245, 255))
    for k in range(6):
        a = math.radians(k * 60 - 90); ca, sa = math.cos(a), math.sin(a)
        end = (C[0] + ca * 11, C[1] + sa * 11); d.line([C, end], fill=(215, 245, 255, 255), width=2)
        for t, ln in ((.5, 4.2), (.78, 3.0)):
            bx, by = C[0] + ca * 11 * t, C[1] + sa * 11 * t
            for s in (-1, 1):
                b = a + s * math.radians(55)
                d.line([(bx, by), (bx + math.cos(b) * ln, by + math.sin(b) * ln)], fill=(170, 230, 255, 255), width=1)
        d.point((round(end[0]), round(end[1])), fill=(255, 255, 255, 255))
    circle(d, C, 2.4, (255, 255, 255, 255))
    return finish_icon((150, 230, 255), g)


def icon_chain_lightning():
    g = new(32, 32); d = ImageDraw.Draw(g)
    blue = (120, 175, 255, 255)
    d.line([(7, 9), (11, 8), (12, 11), (16, 11)], fill=blue, width=1)       # боковые разряды цепи
    d.line([(21, 22), (24, 21), (24, 25), (27, 24)], fill=blue, width=1)
    for c in ((6, 9), (27, 24)): circle(d, c, 2.2, (150, 205, 255, 255)); circle(d, c, 1.0, (255, 255, 255, 255))
    bolt = [(18, 3), (9, 17), (15, 17), (12, 29), (25, 12), (18, 12), (22, 3)]
    d.polygon(bolt, fill=(255, 240, 150, 255))
    d.polygon([(18, 3), (14, 10), (17, 10), (20, 5)], fill=(255, 255, 235, 255))
    d.line([(15, 18), (13, 25)], fill=(255, 205, 90, 255), width=1)
    return finish_icon((140, 200, 255), g)


def icon_thunderstrike():
    g = new(32, 32); d = ImageDraw.Draw(g)
    d.ellipse((6, 4, 26, 15), fill=(105, 95, 150, 255))
    for c, r in (((11, 8), 5), ((17, 6), 6), ((23, 9), 5)): circle(d, c, r, (140, 130, 190, 255))
    d.rectangle((7, 9, 25, 12), fill=(105, 95, 150, 255)); d.line([(9, 8), (14, 4)], fill=(185, 178, 225, 255), width=1)
    bolt = [(17, 11), (12, 20), (16, 20), (13, 28), (22, 17), (18, 17), (21, 11)]
    d.polygon(bolt, fill=(255, 245, 160, 255)); d.line([(17, 12), (14, 18)], fill=(255, 255, 240, 255), width=1)
    d.arc((8, 25, 24, 31), 180, 360, fill=(200, 190, 255, 255), width=1)
    for p in ((8, 26), (24, 26), (11, 23), (21, 24)): d.point(p, fill=(255, 245, 160, 255))
    return finish_icon((180, 170, 255), g)


def icon_meteor():
    g = new(32, 32); d = ImageDraw.Draw(g); rnd = random.Random(3)
    comet(d, (21, 19), (-.72, -.69), 20, 8.0, [((200, 50, 30, 255), 1.0), ((255, 125, 40, 255), .75), ((255, 205, 80, 255), .45)], rnd, 1.8)
    circle(d, (21, 19), 7, (88, 50, 44, 255)); circle(d, (20, 18), 5.8, (120, 70, 52, 255)); circle(d, (19, 17), 3.2, (155, 98, 66, 255))
    d.line([(17, 20), (20, 21), (22, 24)], fill=(255, 165, 60, 255), width=1); d.line([(23, 15), (25, 18)], fill=(255, 140, 50, 255), width=1)
    d.point((21, 22), fill=(255, 220, 110, 255)); d.point((24, 20), fill=(255, 220, 110, 255))
    d.line([(14, 29), (30, 29)], fill=(255, 150, 60, 255), width=1)
    for p in ((15, 27), (28, 27), (22, 26)): d.point(p, fill=(255, 205, 90, 255))
    return finish_icon((255, 120, 50), g)


# ------------------------------------------------------------------ снаряды (смотрят вправо, 4 кадра, ×4)
def fire_bolt(frame):
    rnd = random.Random(100 + frame); g = new(24, 16); d = ImageDraw.Draw(g)
    comet(d, (18, 8), (-1, 0), 15 + frame % 2, 5.6, [((205, 55, 30, 255), 1.0), ((255, 130, 40, 255), .8), ((255, 208, 85, 255), .52)], rnd, 1.9)
    circle(d, (18, 8), 4.6, (255, 128, 40, 255)); circle(d, (18.5, 8), 3.4, (255, 195, 75, 255)); circle(d, (19, 8), 2, (255, 245, 190, 255))
    for i in range(3): d.point((3 + rnd.randint(0, 6), 8 + rnd.choice((-4, -3, 3, 4))), fill=(255, 190, 80, 255))
    return scaled(with_outline(g), 4)


def ice_bolt(frame):
    rnd = random.Random(200 + frame); g = new(28, 16); d = ImageDraw.Draw(g)
    for i in range(14):                                                    # ледяная дымка позади
        x = 2 + int(i * 0.9) + rnd.randint(0, 1); y = 8 + rnd.randint(-3, 3) * (1 - i / 16)
        d.point((x, round(y)), fill=(110, 195, 245, 255 if i > 5 else 150))
    d.polygon([(26, 8), (17, 3), (5, 6), (5, 10), (17, 13)], fill=(95, 170, 238, 255))
    d.polygon([(26, 8), (17, 3), (5, 6), (14, 8)], fill=(200, 245, 255, 255))
    d.line([(8, 8), (24, 8)], fill=(255, 255, 255, 255), width=1)
    d.polygon([(26, 8), (21, 6), (21, 10)], fill=(235, 252, 255, 255))
    sx = (9, 14, 19, 12)[frame % 4]; sparkle(d, sx, 4 + frame % 2, (255, 255, 255, 255), True)
    return scaled(with_outline(g), 4)


def arcane_bolt(frame):
    rnd = random.Random(300 + frame); g = new(28, 24); d = ImageDraw.Draw(g)
    comet(d, (20, 12), (-1, 0), 16, 6.2, [((95, 40, 175, 255), 1.0), ((150, 90, 235, 255), .78), ((205, 160, 255, 255), .5)], rnd, 1.6)
    for r, col in ((6.2, (88, 38, 168)), (5.2, (140, 82, 228)), (3.8, (190, 135, 252)), (2.2, (240, 215, 255))): circle(d, (20, 12), r, rgba(col))
    d.point((19, 11), fill=(255, 255, 255, 255))
    a = math.radians(frame * 90 + 20); sx, sy = 20 + math.cos(a) * 9.5, 12 + math.sin(a) * 6.5   # искра обегает шар
    sparkle(d, round(sx), round(sy), (245, 225, 255, 255), True)
    return scaled(with_outline(g), 4)


# ------------------------------------------------------------------ навыки телекинеза инженера
TK_PURPLE, TK_BLUE, TK_MAG = (150, 110, 255), (120, 170, 255), (200, 120, 255)


def icon_telekinesis():
    g = new(32, 32); d = ImageDraw.Draw(g); c = (16, 16)
    for k, rad in enumerate((11, 7)):
        a0 = k * 60; d.arc((c[0] - rad, c[1] - rad, c[0] + rad, c[1] + rad), a0, a0 + 230, fill=(205, 175, 255, 255), width=2)
    d.polygon([(27, 16), (22, 12), (22, 20)], fill=(235, 215, 255, 255))     # стрелка-отталкивание
    d.polygon([(5, 16), (10, 12), (10, 20)], fill=(235, 215, 255, 255))      # стрелка-притяжение
    circle(d, c, 3, (235, 220, 255, 255)); d.point((15, 15), fill=(255, 255, 255, 255))
    return finish_icon(TK_PURPLE, g)


def icon_telekinesis_cone():
    g = new(32, 32); d = ImageDraw.Draw(g); o = (6, 16)
    for off, ln in ((-18, 20), (0, 25), (18, 20)):
        a = math.radians(off); d.line([o, (o[0] + math.cos(a) * ln, o[1] + math.sin(a) * ln)], fill=(150, 200, 255, 255), width=2)
    for rr in (12, 18, 24): d.arc((o[0] - rr, o[1] - rr, o[0] + rr, o[1] + rr), -46, 46, fill=(205, 228, 255, 255), width=1)
    circle(d, o, 2.6, (235, 245, 255, 255))
    return finish_icon(TK_BLUE, g)


def icon_telekinesis_hold():
    g = new(32, 32); d = ImageDraw.Draw(g); c = (18, 16)
    for rr in (6, 10): d.ellipse((c[0] - rr, c[1] - rr, c[0] + rr, c[1] + rr), outline=(210, 170, 255, 255), width=1)
    for sx in (-1, 1):
        for sy in (-1, 1):
            cx, cy = c[0] + sx * 12, c[1] + sy * 12
            d.line([(cx, cy), (cx - sx * 5, cy)], fill=(240, 215, 255, 255), width=1)
            d.line([(cx, cy), (cx, cy - sy * 5)], fill=(240, 215, 255, 255), width=1)
    d.line([(3, 16), (c[0] - 6, 16)], fill=(200, 140, 255, 255), width=1); circle(d, c, 2, (255, 255, 255, 255))
    return finish_icon(TK_MAG, g)


# Анимации применения (смотрят вправо, 6 кадров). Мягкие эффекты — без тёмного контура.
def cast_telekinesis(frame, n=6):
    S = 72; g = new(S, S); d = ImageDraw.Draw(g); c = (S / 2, S / 2); t = frame / n
    for ring, rad in enumerate((26, 20, 14)):
        pr = rad + math.sin((t + ring * .25) * math.tau) * 4
        col = mix((45, 22, 95), TK_PURPLE, .5 + ring * .18)
        for seg in range(3):
            a0 = math.degrees(t * math.tau * (1 if ring % 2 == 0 else -1)) + seg * 120 + ring * 40
            d.arc((c[0] - pr, c[1] - pr, c[0] + pr, c[1] + pr), a0, a0 + 72, fill=rgba(col), width=2)
    for i in range(8):
        a = i / 8 * math.tau + t * 2; rr = 30 * (1 - t) + 6
        p = (c[0] + math.cos(a) * rr, c[1] + math.sin(a) * rr)
        sparkle(d, round(p[0]), round(p[1]), (230, 210, 255, 255), i % 2 == 0)
    circle(d, c, 5 + math.sin(t * math.tau) * 2, (235, 220, 255, 255)); circle(d, c, 2.5, (255, 255, 255, 255))
    return scaled(g, 2)


def cast_telekinesis_cone(frame, n=6):
    W, H = 90, 72; g = new(W, H); d = ImageDraw.Draw(g); t = frame / n; o = (10, H / 2); reach = 30 + 46 * t
    for off in (-2, -1, 0, 1, 2):
        a = math.radians(off * 22); col = mix((30, 50, 110), TK_BLUE, 1 - abs(off) * .17)
        d.line([o, (o[0] + math.cos(a) * reach, o[1] + math.sin(a) * reach)], fill=rgba(col, int(130 + 125 * (1 - t))), width=max(1, 3 - abs(off)))
    for k in range(3):
        rr = reach - k * 6
        if rr > 5: d.arc((o[0] - rr, o[1] - rr, o[0] + rr, o[1] + rr), -62, 62, fill=rgba(mix(TK_BLUE, (255, 255, 255), .3), int(210 * (1 - t))), width=2)
    circle(d, o, 4, (225, 240, 255, 255))
    return scaled(g, 2)


def cast_telekinesis_hold(frame, n=6):
    S = 72; g = new(S, S); d = ImageDraw.Draw(g); t = frame / n; c = (S * .62, S / 2); rad = 28 - 16 * t
    for k in range(3):
        rr = rad + k * 7
        if rr > 2: d.ellipse((c[0] - rr, c[1] - rr, c[0] + rr, c[1] + rr), outline=rgba(mix((60, 20, 110), TK_MAG, .6 + k * .14), max(60, int(220 - k * 55))), width=2)
    br = rad + 22
    for sx in (-1, 1):
        for sy in (-1, 1):
            cr = (c[0] + sx * br, c[1] + sy * br)
            d.line([cr, (cr[0] - sx * 11, cr[1])], fill=(245, 220, 255, 255), width=2); d.line([cr, (cr[0], cr[1] - sy * 11)], fill=(245, 220, 255, 255), width=2)
    d.line([(4, S / 2), (c[0] - rad, c[1])], fill=rgba(TK_MAG, int(120 + 110 * abs(math.sin(t * math.tau)))), width=2)
    circle(d, c, 3, (255, 255, 255, 255))
    return scaled(g, 2)


# ------------------------------------------------------------------ запись файлов
ICONS = {"fireball": icon_fireball, "ice_shard": icon_ice_shard, "arcane_orb": icon_arcane_orb, "frost_nova": icon_frost_nova,
         "chain_lightning": icon_chain_lightning, "thunderstrike": icon_thunderstrike, "meteor": icon_meteor,
         "telekinesis": icon_telekinesis, "telekinesis_cone": icon_telekinesis_cone, "telekinesis_hold": icon_telekinesis_hold}
PROJECTILES = {"fireball": fire_bolt, "ice_shard": ice_bolt, "arcane_orb": arcane_bolt}
CASTS = {"telekinesis": cast_telekinesis, "telekinesis_cone": cast_telekinesis_cone, "telekinesis_hold": cast_telekinesis_hold}


def save(img, path, force):
    if path.exists() and not force: print(f"  есть, пропускаю: {path.relative_to(ASSETS.parent)}"); return
    path.parent.mkdir(parents=True, exist_ok=True); img.save(path); print(f"  нарисовано: {path.relative_to(ASSETS.parent)}")


def main(force=False):
    for sid, fn in ICONS.items(): save(fn(), ASSETS / "icons" / f"skill_{sid}.png", force)
    for sid, fn in PROJECTILES.items():
        for i in range(4): save(fn(i), ASSETS / "projectiles" / sid / f"{i + 1}.png", force)
    for sid, fn in CASTS.items():
        for i in range(6): save(fn(i), ASSETS / "skills" / sid / "cast" / f"{i + 1}.png", force)


if __name__ == "__main__":
    main("--force" in sys.argv)
