# -*- coding: utf-8 -*-
"""Рисует иконки (assets/icons/skill_<id>.png) и спрайты снарядов (assets/projectiles/<id>/1..4.png)
для 50 новых навыков героев. Переиспользует помощники make_spell_textures.

Запуск:   python make_skill_icons.py            — рисует только недостающие файлы
          python make_skill_icons.py --force    — перерисовывает всё
Требуется Pillow.
"""
import math, sys
from PIL import ImageDraw
from make_spell_textures import (new, circle, sparkle, rgba, with_outline, scaled,
                                 finish_icon, save, ASSETS)
from pathlib import Path

cos, sin, rad = math.cos, math.sin, math.radians


# ------------------------------------------------------------------ глифы иконок (32x32)
def crescent(accent):                                   # бумеранг: дуга с навершиями
    g = new(32, 32); d = ImageDraw.Draw(g); C = (16, 17)
    d.arc((C[0] - 9, C[1] - 9, C[0] + 9, C[1] + 9), 25, 155, fill=rgba(accent), width=4)
    for a in (25, 155):
        x, y = C[0] + cos(rad(a)) * 9, C[1] + sin(rad(a)) * 9
        circle(d, (x, y), 3.2, rgba(accent)); circle(d, (x, y), 1.8, (255, 255, 255, 255))
    sparkle(d, 8, 8, (255, 255, 255, 255))
    return finish_icon(accent, g)


def hammer(accent):                                     # молот
    g = new(32, 32); d = ImageDraw.Draw(g)
    d.line([(10, 26), (20, 10)], fill=rgba(mix_((120, 110, 100), accent, .3)), width=4)
    d.rounded_rectangle((16, 4, 28, 14), radius=2, fill=rgba(accent))
    d.rounded_rectangle((17, 5, 27, 13), radius=2, fill=rgba(mix_(accent, (255, 255, 255), .35)))
    return finish_icon(accent, g)


def shield_glyph(accent, cross=False):                  # щит (можно с крестом)
    g = new(32, 32); d = ImageDraw.Draw(g)
    d.polygon([(16, 4), (27, 8), (25, 20), (16, 28), (7, 20), (5, 8)], fill=rgba(accent))
    d.polygon([(16, 6), (25, 9.4), (23.4, 19), (16, 25.4), (8.6, 19), (7, 9.4)], fill=rgba(mix_(accent, (255, 255, 255), .3)))
    if cross:
        d.line([(16, 10), (16, 21)], fill=(255, 255, 255, 255), width=3)
        d.line([(11, 14), (21, 14)], fill=(255, 255, 255, 255), width=3)
    else:
        d.line([(11, 12), (21, 12)], fill=rgba(mix_(accent, (0, 0, 0), .45)), width=2)
        d.line([(16, 12), (16, 22)], fill=rgba(mix_(accent, (0, 0, 0), .45)), width=2)
    return finish_icon(accent, g)


def shout(accent):                                      # боевой клич: расходящиеся дуги
    g = new(32, 32); d = ImageDraw.Draw(g); C = (10, 16)
    circle(d, C, 4.2, rgba(accent)); circle(d, C, 3.0, rgba(mix_(accent, (255, 255, 255), .4)))
    for r, w in ((8, 2), (12, 2), (16, 1)):
        d.arc((C[0] - r, C[1] - r, C[0] + r, C[1] + r), -55, 55, fill=rgba(mix_(accent, (255, 255, 255), r / 20)), width=w)
    return finish_icon(accent, g)


def beam_line(accent, thick=4):                         # луч по линии
    g = new(32, 32); d = ImageDraw.Draw(g)
    d.line([(4, 22), (28, 10)], fill=rgba(accent), width=thick)
    d.line([(4, 22), (28, 10)], fill=(255, 255, 255, 230), width=max(1, thick - 2))
    circle(d, (4, 22), 4.0, rgba(accent)); circle(d, (4, 22), 2.2, (255, 255, 255, 255))
    sparkle(d, 27, 8, (255, 255, 255, 255))
    return finish_icon(accent, g)


def mine_glyph(accent):                                 # мина с усами
    g = new(32, 32); d = ImageDraw.Draw(g); C = (16, 19)
    for a in range(0, 360, 45):
        d.line([C, (C[0] + cos(rad(a)) * 9.5, C[1] + sin(rad(a)) * 9.5)], fill=rgba(accent), width=2)
    circle(d, C, 6.8, rgba(accent)); circle(d, C, 5.2, rgba(mix_(accent, (255, 255, 255), .4)))
    circle(d, C, 2.0, (255, 90, 70, 255))
    return finish_icon(accent, g)


def zone_glyph(accent, cross=False):                    # круг на земле (можно с нимбом-крестом)
    g = new(32, 32); d = ImageDraw.Draw(g)
    d.ellipse((5, 18, 27, 28), outline=rgba(accent), width=2)
    d.ellipse((9, 21, 23, 25), fill=rgba(mix_(accent, (255, 255, 255), .35)))
    if cross:
        d.line([(16, 5), (16, 16)], fill=rgba(accent), width=3)
        d.line([(11, 9), (21, 9)], fill=rgba(accent), width=3)
    else:
        for x, y in ((10, 13), (21, 11), (16, 7)): d.point((x, y), fill=rgba(mix_(accent, (255, 255, 255), .5)))
    return finish_icon(accent, g)


def banner_glyph(accent):                               # знамя
    g = new(32, 32); d = ImageDraw.Draw(g)
    d.line([(10, 28), (10, 4)], fill=rgba(mix_((120, 100, 80), accent, .3)), width=3)
    d.polygon([(11, 5), (26, 7), (24, 12), (26, 17), (11, 15)], fill=rgba(accent))
    d.polygon([(12, 6.5), (24, 8), (22.6, 11), (24, 14.6), (12, 13.2)], fill=rgba(mix_(accent, (255, 255, 255), .3)))
    return finish_icon(accent, g)


def wave_glyph(accent, heavy=False):                    # звуковая волна (можно толстую — бас)
    g = new(32, 32); d = ImageDraw.Draw(g)
    w = 4 if heavy else 2
    for k, x0 in ((0, 5), (1, 12), (2, 19)):
        d.arc((x0, 9, x0 + 12, 23), 200, 340, fill=rgba(mix_(accent, (255, 255, 255), k * .25)), width=w)
    circle(d, (5, 16), 3.4, rgba(accent)); circle(d, (5, 16), 1.8, (255, 255, 255, 255))
    return finish_icon(accent, g)


def heart_plus(accent, plus=True):                      # лечение (крест/сердце)
    g = new(32, 32); d = ImageDraw.Draw(g)
    if plus:
        d.rounded_rectangle((12, 5, 20, 27), radius=3, fill=rgba(accent))
        d.rounded_rectangle((5, 12, 27, 20), radius=3, fill=rgba(accent))
        d.rounded_rectangle((13.5, 7, 18.5, 25), radius=2, fill=(255, 255, 255, 220))
        d.rounded_rectangle((7, 13.5, 25, 18.5), radius=2, fill=(255, 255, 255, 220))
    else:
        d.polygon([(16, 27), (6, 16), (6, 10), (11, 7), (16, 11), (21, 7), (26, 10), (26, 16)], fill=rgba(accent))
        d.polygon([(16, 24), (9, 15.5), (10, 11), (13.5, 10), (16, 13.5)], fill=rgba(mix_(accent, (255, 255, 255), .35)))
    return finish_icon(accent, g)


def metronome_glyph(accent):                            # метроном
    g = new(32, 32); d = ImageDraw.Draw(g)
    d.polygon([(16, 4), (25, 28), (7, 28)], fill=rgba(mix_((90, 80, 70), accent, .25)))
    d.polygon([(16, 7), (23, 26.4), (9, 26.4)], fill=rgba(mix_(accent, (255, 255, 255), .25)))
    d.line([(16, 18), (23, 6)], fill=(255, 120, 80, 255), width=2)
    circle(d, (23, 6), 2.0, (255, 160, 90, 255))
    return finish_icon(accent, g)


def orbit_glyph(accent):                                # орбита с клинками
    g = new(32, 32); d = ImageDraw.Draw(g); C = (16, 16)
    d.ellipse((C[0] - 11, C[1] - 11, C[0] + 11, C[1] + 11), outline=rgba(accent[:3] + (150,)), width=1)
    for k in range(3):
        a = rad(k * 120 - 90); x, y = C[0] + cos(a) * 11, C[1] + sin(a) * 11
        ta = a + rad(90); tx, ty = cos(ta), sin(ta)
        d.line([(x - tx * 4.5, y - ty * 4.5), (x + tx * 4.5, y + ty * 4.5)], fill=rgba(accent), width=2)
        d.point((round(x + tx * 5), round(y + ty * 5)), fill=(255, 255, 255, 255))
    circle(d, C, 3.6, rgba(accent)); circle(d, C, 2.0, (255, 255, 255, 255))
    return finish_icon(accent, g)


def burst_glyph(accent):                                # вспышка/взрыв
    g = new(32, 32); d = ImageDraw.Draw(g); C = (16, 16)
    for k in range(8):
        a = rad(k * 45 + 12); r1, r2 = (6, 13) if k % 2 else (5, 10)
        d.line([(C[0] + cos(a) * r1, C[1] + sin(a) * r1), (C[0] + cos(a) * r2, C[1] + sin(a) * r2)], fill=rgba(accent), width=2)
    circle(d, C, 5.2, rgba(accent)); circle(d, C, 3.2, (255, 255, 255, 240)); d.point((15, 15), fill=(255, 255, 255, 255))
    return finish_icon(accent, g)


def note_glyph(accent):                                 # двойная нота
    g = new(32, 32); d = ImageDraw.Draw(g)
    d.line([(11, 22), (11, 7)], fill=rgba(accent), width=2)
    d.line([(21, 20), (21, 5)], fill=rgba(accent), width=2)
    d.line([(11, 7), (21, 5)], fill=rgba(accent), width=2)
    for x, y in ((11, 22), (21, 20)):
        d.ellipse((x - 4, y - 3, x + 4, y + 3), fill=rgba(accent))
        d.ellipse((x - 3, y - 2.4, x + 3, y + 2.2), fill=rgba(mix_(accent, (255, 255, 255), .4)))
    sparkle(d, 26, 10, (255, 255, 255, 255))
    return finish_icon(accent, g)


def rocket_glyph(accent):                               # ракета по диагонали
    g = new(32, 32); d = ImageDraw.Draw(g)
    d.polygon([(26, 6), (22, 16), (12, 22), (10, 20), (16, 10)], fill=rgba(accent))
    d.polygon([(24, 7), (21, 14), (14, 18)], fill=rgba(mix_(accent, (255, 255, 255), .4)))
    d.polygon([(10, 20), (5, 27), (9, 24), (8, 27), (12, 21)], fill=(255, 180, 60, 255))
    d.polygon([(16, 10), (11, 9), (10, 14)], fill=rgba(mix_(accent, (0, 0, 0), .3)))
    return finish_icon(accent, g)


def gatling_glyph(accent):                              # три ствола
    g = new(32, 32); d = ImageDraw.Draw(g)
    for y in (9, 15, 21):
        d.line([(6, y), (24, y - 3)], fill=rgba(accent), width=3)
        d.point((24, y - 3), fill=(255, 255, 255, 255))
    d.rounded_rectangle((3, 7, 8, 24), radius=2, fill=rgba(mix_(accent, (0, 0, 0), .35)))
    return finish_icon(accent, g)


def grenade_glyph(accent):                              # граната
    g = new(32, 32); d = ImageDraw.Draw(g); C = (15, 19)
    circle(d, C, 8, rgba(accent)); circle(d, C, 6.2, rgba(mix_(accent, (255, 255, 255), .35)))
    d.rounded_rectangle((12, 5, 18, 10), radius=1, fill=rgba(mix_(accent, (0, 0, 0), .35)))
    d.point((13, 17), fill=(255, 255, 255, 255))
    d.line([(19, 4), (24, 2)], fill=(255, 160, 60, 255), width=2)
    circle(d, (24, 2), 1.6, (255, 220, 120, 255))
    return finish_icon(accent, g)


def drone_glyph(accent):                                # рой дронов
    g = new(32, 32); d = ImageDraw.Draw(g)
    for x, y, r in ((10, 12, 5), (22, 9, 4), (18, 22, 4.4)):
        circle(d, (x, y), r, rgba(accent)); circle(d, (x - 1, y - 1), r * .55, rgba(mix_(accent, (255, 255, 255), .5)))
        d.point((x - 1, y - 1), fill=(255, 255, 255, 255))
    return finish_icon(accent, g)


def magnet_glyph(accent):                               # магнит-подкова
    g = new(32, 32); d = ImageDraw.Draw(g)
    d.arc((8, 6, 24, 22), 180, 360, fill=rgba(accent), width=4)
    d.line([(8, 14), (8, 22)], fill=rgba(accent), width=4)
    d.line([(24, 14), (24, 22)], fill=rgba(accent), width=4)
    d.rectangle((6, 22, 10, 26), fill=(255, 120, 120, 255)); d.rectangle((22, 22, 26, 26), fill=(120, 160, 255, 255))
    sparkle(d, 25, 8, (255, 255, 255, 255))
    return finish_icon(accent, g)


def arrows_glyph(accent, ghost=False):                  # рывок/скорость
    g = new(32, 32); d = ImageDraw.Draw(g)
    col = rgba(mix_(accent, (255, 255, 255), .35 if ghost else 0))
    for dx in (0, 8):
        a = 12 + dx
        d.line([(a, 24), (a + 8, 16)], fill=col, width=3)
        d.polygon([(a + 8, 16), (a + 9, 21), (a + 4, 20)], fill=col)
        if ghost: d.point((a + 2, 12), fill=rgba(accent))
    return finish_icon(accent, g)


def drop_glyph(accent):                                 # капля
    g = new(32, 32); d = ImageDraw.Draw(g)
    d.polygon([(16, 4), (24, 17), (16, 27), (8, 17)], fill=rgba(accent))
    d.polygon([(16, 7), (21, 17), (16, 24)], fill=rgba(mix_(accent, (255, 255, 255), .4)))
    d.point((14, 16), fill=(255, 255, 255, 255))
    return finish_icon(accent, g)


def spiral_glyph(accent):                               # воронка/гравитация
    g = new(32, 32); d = ImageDraw.Draw(g); C = (16, 16)
    for k in range(14):
        a = k * 0.62; r = 2.2 + k * 0.82
        x, y = C[0] + cos(a) * r, C[1] + sin(a) * r * .82
        x2, y2 = C[0] + cos(a + .5) * (r + 1.1), C[1] + sin(a + .5) * (r + 1.1) * .82
        d.line([(x, y), (x2, y2)], fill=rgba(mix_(accent, (255, 255, 255), k / 16)), width=2)
    circle(d, C, 2.2, (20, 12, 30, 255))
    return finish_icon(accent, g)


def fan_glyph(accent):                                  # веер кинжалов
    g = new(32, 32); d = ImageDraw.Draw(g); C = (16, 26)
    for a in (-38, 0, 38):
        r = rad(a - 90); ex, ey = C[0] + cos(r) * 19, C[1] + sin(r) * 19
        d.line([C, (ex, ey)], fill=rgba(accent), width=2)
        d.polygon([(ex, ey), (ex - sin(r) * 2.4, ey + cos(r) * 2.4), (ex + sin(r) * 2.4, ey - cos(r) * 2.4)], fill=(255, 255, 255, 220))
    circle(d, C, 3.0, rgba(accent))
    return finish_icon(accent, g)


def cloud_glyph(accent):                                # дымовая бомба
    g = new(32, 32); d = ImageDraw.Draw(g)
    for x, y, r in ((11, 20, 6), (19, 15, 6.4), (24, 21, 5), (15, 24, 4.6)):
        circle(d, (x, y), r, rgba(mix_(accent, (255, 255, 255), (y - 10) / 30)))
    d.line([(24, 8), (20, 12)], fill=(255, 160, 60, 255), width=2)
    circle(d, (25, 7), 1.8, (255, 220, 120, 255))
    return finish_icon(accent, g)


def star_glyph(accent):                                 # звезда/звездопад
    g = new(32, 32); d = ImageDraw.Draw(g); C = (20, 12)
    for k in range(5):
        a = rad(k * 72 - 90); a2 = rad(k * 72 - 90 + 36)
        d.line([C, (C[0] + cos(a) * 8.5, C[1] + sin(a) * 8.5)], fill=rgba(accent), width=2)
        d.line([(C[0] + cos(a) * 8.5, C[1] + sin(a) * 8.5), (C[0] + cos(a2) * 3.6, C[1] + sin(a2) * 3.6)], fill=rgba(accent), width=2)
    circle(d, C, 2.4, (255, 255, 255, 255))
    for x, y, L in ((8, 22, 5), (13, 26, 4)):
        d.line([(x, y), (x + 3, y + L)], fill=rgba(mix_(accent, (255, 255, 255), .4)), width=2)
    return finish_icon(accent, g)


def diamond_glyph(accent):                              # кристалл/мана
    g = new(32, 32); d = ImageDraw.Draw(g)
    d.polygon([(16, 4), (26, 16), (16, 28), (6, 16)], fill=rgba(accent))
    d.polygon([(16, 6), (24, 16), (16, 26)], fill=rgba(mix_(accent, (255, 255, 255), .4)))
    d.line([(16, 4), (16, 28)], fill=rgba(mix_(accent, (255, 255, 255), .6)), width=1)
    sparkle(d, 8, 8, (255, 255, 255, 255)); sparkle(d, 24, 24, (255, 255, 255, 255))
    return finish_icon(accent, g)


def eye_glyph(accent):                                  # разум/взгляд
    g = new(32, 32); d = ImageDraw.Draw(g)
    d.polygon([(5, 16), (16, 8), (27, 16), (16, 24)], fill=rgba(accent))
    circle(d, (16, 16), 4.6, (20, 14, 34, 255)); circle(d, (16, 16), 2.4, (255, 255, 255, 255))
    d.point((15, 15), fill=(255, 255, 255, 255))
    return finish_icon(accent, g)


def footprint_glyph(accent):                            # лёгкая поступь
    g = new(32, 32); d = ImageDraw.Draw(g)
    for x, y in ((11, 12), (20, 20)):
        d.ellipse((x - 3.5, y - 5, x + 3.5, y + 5), fill=rgba(accent))
        for k in range(3):
            d.point((x - 3 + k * 3, y - 7), fill=rgba(accent))
    d.line([(6, 27), (12, 27)], fill=rgba(mix_(accent, (255, 255, 255), .4)), width=1)
    d.line([(16, 9), (22, 9)], fill=rgba(mix_(accent, (255, 255, 255), .4)), width=1)
    return finish_icon(accent, g)


def mix_(c1, c2, k):
    from make_spell_textures import mix
    return mix(c1, c2, k)[:3]


# ------------------------------------------------------------------ карта: навык -> (глиф, акцент)
A_KN = (255, 205, 120)   # рыцарь: золото
A_ST = (205, 218, 238)   # сталь
A_BD = (255, 190, 110)   # бард: тёплое золото
A_EN = (140, 220, 255)   # инженер: циан
A_MG = (190, 130, 255)   # маг: пурпур
A_SH = (150, 150, 210)   # тень: сумеречный

ICONS = {
    # рыцарь
    "hammer_fall": lambda: hammer(A_KN),
    "sword_boomerang": lambda: crescent(A_ST),
    "shield_bash": lambda: shield_glyph(A_ST),
    "holy_ward": lambda: shield_glyph(A_KN, cross=True),
    "warcry": lambda: shout((255, 180, 110)),
    "light_lance": lambda: beam_line((255, 235, 170)),
    "iron_mine": lambda: mine_glyph((165, 185, 215)),
    "consecrated_ground": lambda: zone_glyph((255, 224, 130), cross=True),
    "banner_of_war": lambda: banner_glyph((255, 190, 100)),
    "tempered_armor": lambda: shield_glyph((190, 200, 220)),
    # бард
    "sound_wave": lambda: wave_glyph((255, 205, 120)),
    "sonic_boomerang": lambda: crescent((120, 230, 255)),
    "power_chord": lambda: burst_glyph((255, 170, 90)),
    "healing_verse": lambda: heart_plus((110, 230, 140), plus=False),
    "bass_cannon": lambda: wave_glyph((255, 160, 100), heavy=True),
    "metronome": lambda: metronome_glyph((255, 215, 140)),
    "dance_of_strings": lambda: orbit_glyph((255, 214, 130)),
    "final_chord": lambda: burst_glyph((255, 140, 180)),
    "perfect_pitch": lambda: note_glyph((140, 220, 255)),
    "stage_experience": lambda: note_glyph((150, 180, 255)),
    # инженер
    "rocket": lambda: rocket_glyph((255, 120, 60)),
    "gatling": lambda: gatling_glyph((255, 214, 120)),
    "shock_grenade": lambda: grenade_glyph((255, 232, 90)),
    "drone_swarm": lambda: drone_glyph((120, 220, 255)),
    "laser_cutter": lambda: beam_line((255, 90, 90), thick=3),
    "repair_kit": lambda: heart_plus((120, 235, 200)),
    "magnet_field": lambda: magnet_glyph((120, 220, 255)),
    "oil_slick": lambda: zone_glyph((130, 110, 190)),
    "overdrive": lambda: arrows_glyph((140, 230, 255)),
    "workshop_oil": lambda: drop_glyph((160, 160, 200)),
    # маг
    "arcane_lance": lambda: beam_line(A_MG),
    "void_pulse": lambda: burst_glyph((150, 90, 220)),
    "crystal_boomerang": lambda: crescent((180, 230, 255)),
    "frost_ring": lambda: burst_glyph((150, 230, 255)),
    "arcane_ward": lambda: shield_glyph(A_MG),
    "star_fall": lambda: star_glyph((255, 240, 180)),
    "tempest": lambda: star_glyph((150, 190, 255)),
    "gravity_well": lambda: spiral_glyph((150, 90, 220)),
    "mana_crystal": lambda: diamond_glyph((120, 200, 255)),
    "arcane_mind": lambda: eye_glyph(A_MG),
    # тень
    "shadow_burst": lambda: fan_glyph((170, 150, 220)),
    "blade_fan": lambda: fan_glyph((150, 170, 230)),
    "phantom_step": lambda: arrows_glyph((130, 130, 190), ghost=True),
    "smoke_bomb": lambda: cloud_glyph((120, 110, 140)),
    "poison_trap": lambda: mine_glyph((140, 220, 110)),
    "dark_vortex": lambda: spiral_glyph((110, 80, 190)),
    "shadow_rain": lambda: star_glyph((130, 120, 160)),
    "night_blades": lambda: orbit_glyph((150, 170, 230)),
    "lightfoot": lambda: footprint_glyph((170, 180, 220)),
    "night_vigor": lambda: heart_plus((130, 140, 190), plus=False),
}


# ------------------------------------------------------------------ спрайты снарядов (4 кадра)
def boomerang_frames(c1, c2):
    def f(frame):
        a0 = frame * 90; g = new(30, 30); d = ImageDraw.Draw(g); C = (15, 15)
        d.arc((C[0] - 9, C[1] - 9, C[0] + 9, C[1] + 9), a0 + 30, a0 + 130, fill=rgba(c1), width=3)
        for a in (a0, a0 + 45):
            x, y = C[0] + cos(rad(a)) * 10, C[1] + sin(rad(a)) * 10
            circle(d, (x, y), 3.4, rgba(c1)); circle(d, (x, y), 2.0, rgba(c2))
        return scaled(with_outline(g), 4)
    return f


def blade_frames(c1, c2):
    def f(frame):
        g = new(24, 24); d = ImageDraw.Draw(g); C = (12, 12); a = frame * 90
        d.ellipse((C[0] - 5, C[1] - 5, C[0] + 5, C[1] + 5), outline=rgba(c1, 190), width=1)
        for k in range(2):
            b = a + k * 180; tx, ty = cos(rad(b)), sin(rad(b))
            d.line([(C[0] - tx * 9, C[1] - ty * 9), (C[0] + tx * 9, C[1] + ty * 9)], fill=rgba(c1), width=2)
            d.point((round(C[0] + tx * 9), round(C[1] + ty * 9)), fill=rgba(c2))
        circle(d, C, 3.0, rgba(c1)); circle(d, C, 1.6, rgba(c2))
        return scaled(with_outline(g), 4)
    return f


def mine_frames(c1, c2):
    def f(frame):
        g = new(26, 28); d = ImageDraw.Draw(g); C = (13, 15)
        for a in range(0, 360, 45):
            d.line([C, (C[0] + cos(rad(a)) * 8.5, C[1] + sin(rad(a)) * 8.5)], fill=rgba(c1), width=2)
        circle(d, C, 6.2, rgba(c1)); circle(d, C, 5.0, rgba(c2)); circle(d, (11.5, 13.5), 2.2, (255, 255, 255, 255))
        circle(d, C, 1.8, (255, 90, 70, 255) if frame % 2 else (120, 60, 60, 255))
        return scaled(with_outline(g), 4)
    return f


def rocket_frames(c1, c2):
    def f(frame):
        g = new(34, 16); d = ImageDraw.Draw(g)
        d.polygon([(24, 4), (24, 12), (31, 8)], fill=rgba(c2))
        d.rectangle((8, 4, 24, 12), fill=rgba(c1))
        d.polygon([(8, 4), (3, 1), (8, 8)], fill=rgba(c1)); d.polygon([(8, 12), (3, 15), (8, 8)], fill=rgba(c1))
        L = 5 + (frame % 2) * 3
        d.polygon([(8, 5.5), (8 - L, 8), (8, 10.5)], fill=(255, 180, 60, 255))
        d.polygon([(8, 6.8), (8 - L + 2, 8), (8, 9.2)], fill=(255, 235, 150, 255))
        return scaled(with_outline(g), 4)
    return f


def core_frames(c1, c2):
    def f(frame):
        g = new(36, 36); d = ImageDraw.Draw(g); C = (18, 18)
        r = 8 + (frame % 2)
        d.ellipse((C[0] - r, C[1] - r, C[0] + r, C[1] + r), outline=rgba(c1, 150), width=2)
        circle(d, C, 5.5, rgba(c1)); circle(d, C, 3.6, rgba(c2)); circle(d, (16.5, 16.5), 1.8, (255, 255, 255, 255))
        for k in range(4):
            a = rad(frame * 30 + k * 90)
            d.point((round(C[0] + cos(a) * 11), round(C[1] + sin(a) * 11)), fill=rgba(c2))
        return scaled(with_outline(g), 4)
    return f


def grenade_frames(c1, c2):
    def f(frame):
        g = new(24, 24); d = ImageDraw.Draw(g); C = (12, 14)
        circle(d, C, 7, rgba(c1)); circle(d, C, 5.6, rgba(c2))
        d.rectangle((9, 3, 15, 7), fill=rgba(c2))
        d.point((10, 12), fill=(255, 255, 255, 255))
        if frame % 2: circle(d, (19, 5), 1.6, (255, 160, 60, 255))
        return scaled(with_outline(g), 4)
    return f


def zone_frames(c1, c2):
    def f(frame):
        g = new(38, 38); d = ImageDraw.Draw(g); C = (19, 19)
        for k, rr in ((0, 13), (1, 9)):
            r = rr * (0.9 + 0.12 * math.sin(frame * math.tau / 4 + k))
            d.ellipse((C[0] - r, C[1] - r * .5, C[0] + r, C[1] + r * .5), outline=rgba(c1), width=2)
        circle(d, C, 3.0, rgba(c2))
        return scaled(with_outline(g), 4)
    return f


def wave_frames(c1, c2):
    def f(frame):
        g = new(30, 20); d = ImageDraw.Draw(g)
        off = (frame * 5) % 10
        for k in range(4):
            x0 = -6 + k * 10 + off - 5
            d.arc((x0, 4, x0 + 14, 18), 200, 340, fill=rgba(c1), width=2)
        d.arc((2 + off, 6, 16 + off, 16), 210, 330, fill=rgba(c2), width=1)
        return scaled(with_outline(g), 4)
    return f


def marker_frames(c1, c2):
    def f(frame):
        g = new(24, 24); d = ImageDraw.Draw(g); C = (12, 12)
        r = 6 + (frame % 2) * 2
        d.polygon([(C[0], C[1] + r), (C[0] + r * .7, C[1] - r * .5), (C[0] - r * .7, C[1] - r * .5)], outline=rgba(c1), width=2)
        circle(d, C, 2.2, rgba(c2))
        return scaled(with_outline(g), 4)
    return f


SPRITES = {
    "steel_boomerang": boomerang_frames((205, 218, 238), (255, 255, 255)),
    "sonic_boomerang": boomerang_frames((120, 230, 255), (235, 255, 255)),
    "crystal_boomerang": boomerang_frames((180, 230, 255), (255, 255, 255)),
    "string_blade": blade_frames((255, 214, 130), (255, 240, 200)),
    "night_blade": blade_frames((150, 170, 230), (235, 245, 255)),
    "iron_mine": mine_frames((165, 185, 215), (110, 160, 235)),
    "poison_trap": mine_frames((140, 220, 110), (90, 180, 80)),
    "rocket": rocket_frames((200, 90, 60), (255, 150, 70)),
    "shock_grenade": grenade_frames((255, 232, 90), (255, 250, 190)),
    "magnet_core": core_frames((120, 220, 255), (235, 255, 255)),
    "grav_core": core_frames((150, 90, 220), (240, 200, 255)),
    "dark_core": core_frames((110, 80, 190), (200, 170, 255)),
    "tempest_core": core_frames((150, 190, 255), (255, 255, 255)),
    "starfall_marker": core_frames((255, 240, 180), (255, 255, 255)),
    "holy_zone": zone_frames((255, 224, 130), (255, 255, 230)),
    "oil_zone": zone_frames((130, 110, 190), (190, 170, 240)),
    "sound_wave": wave_frames((255, 205, 120), (255, 240, 200)),
    "shadow_rain_marker": marker_frames((130, 120, 160), (200, 190, 220)),
}


def main(force=False):
    print(f"иконки: {len(ICONS)}, снаряды: {len(SPRITES)}")
    for sid, fn in ICONS.items(): save(fn(), ASSETS / "icons" / f"skill_{sid}.png", force)
    for pid, fn in SPRITES.items():
        for i in range(4): save(fn(i), ASSETS / "projectiles" / pid / f"{i + 1}.png", force)


if __name__ == "__main__":
    main(force="--force" in sys.argv)
