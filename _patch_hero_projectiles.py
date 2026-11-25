# -*- coding: utf-8 -*-
"""Добавляет новые записи снарядов для навыков героев в data/projectiles.json.
Все используют существующие поведения (@behavior в projectiles.py): boomerang, orbit, vortex, mine, zone, storm, rain, wave, accel, split.
"""
import json, io, sys
sys.stdout.reconfigure(encoding="utf-8")

P = {
    # РЫЦАРЬ
    "steel_boomerang": {"speed": 430, "size": 8, "color": [205, 218, 238], "life": 2.2, "knockback": 150,
        "pierce": 999, "ghost": True, "boomerang": {"return": 0.42, "return_speed": 560}, "rotate": True,
        "skin": "projectiles/steel_boomerang.png", "draw": [30, 30]},
    "iron_mine": {"speed": 250, "vy": -240, "gravity": 1050, "bounces": 99, "bounce_damp": 0.45, "size": 7,
        "color": [165, 185, 215], "life": 14, "aoe": 80, "knockback": 250, "shake": 0.25,
        "mine": {"radius": 48, "arm": 0.7}, "effect": {"stun": 0.6},
        "skin": "projectiles/iron_mine.png", "draw": [26, 28]},
    "holy_zone": {"speed": 0, "size": 9, "color": [255, 224, 130], "life": 4.0, "ghost": True,
        "zone": {"radius": 88, "interval": 0.5}, "knockback": 0, "draw": [38, 38], "no_touch": True,
        "skin": "projectiles/holy_zone.png"},
    # БАРД
    "sound_wave": {"speed": 250, "size": 5, "color": [255, 205, 120], "life": 2.4, "knockback": 90,
        "wave": {"amp": 22, "freq": 3.0}, "skin": "projectiles/sound_wave.png", "draw": [30, 20]},
    "sonic_boomerang": {"speed": 430, "size": 8, "color": [120, 230, 255], "life": 2.2, "knockback": 130,
        "pierce": 999, "ghost": True, "boomerang": {"return": 0.42, "return_speed": 560}, "rotate": True,
        "skin": "projectiles/sonic_boomerang.png", "draw": [30, 30]},
    "string_blade": {"speed": 0, "size": 7, "color": [255, 214, 130], "life": 4.5, "ghost": True, "pierce": 999,
        "orbit": {"radius": 52, "speed": 3.2, "rehit": 0.6}, "knockback": 50,
        "skin": "projectiles/string_blade.png", "draw": [24, 24]},
    # ИНЖЕНЕР
    "rocket": {"speed": 90, "accel": 540, "max_speed": 460, "size": 7, "color": [255, 120, 60], "life": 2.5,
        "aoe": 70, "knockback": 220, "shake": 0.15, "skin": "projectiles/rocket.png", "draw": [34, 16]},
    "shock_grenade": {"speed": 280, "vy": -220, "gravity": 900, "bounces": 3, "bounce_damp": 0.7, "size": 7,
        "color": [255, 232, 90], "life": 3, "aoe": 75, "knockback": 180, "shake": 0.2,
        "effect": {"stun": 0.8}, "skin": "projectiles/shock_grenade.png", "draw": [24, 24]},
    "magnet_core": {"speed": 0, "size": 10, "color": [120, 220, 255], "life": 2.8, "ghost": True,
        "vortex": {"radius": 140, "force": 220, "damage": 3, "interval": 0.6}, "rotate": True,
        "draw": [42, 42], "no_touch": True},
    "oil_zone": {"speed": 0, "size": 9, "color": [130, 110, 190], "life": 4.5, "ghost": True,
        "zone": {"radius": 82, "interval": 0.8}, "effect": {"freeze": 0.45}, "knockback": 0,
        "draw": [38, 38], "no_touch": True},
    # ЧАРОДЕЙ
    "crystal_boomerang": {"speed": 430, "size": 8, "color": [180, 230, 255], "life": 2.2, "knockback": 140,
        "pierce": 999, "ghost": True, "boomerang": {"return": 0.42, "return_speed": 560}, "rotate": True,
        "skin": "projectiles/crystal_boomerang.png", "draw": [30, 30]},
    "starfall_marker": {"speed": 0, "size": 6, "color": [255, 240, 180], "life": 1.6, "ghost": True,
        "rain": {"into": "prism_shard", "count": 12, "interval": 0.12, "spread": 150, "height": 190},
        "draw": [24, 24], "no_touch": True},
    "tempest_core": {"speed": 0, "size": 8, "color": [150, 190, 255], "life": 3.0, "ghost": True,
        "storm": {"strikes": 9, "interval": 0.3, "radius": 140, "aoe": 46},
        "effect": {"burn": {"time": 2, "dps": 6}}, "draw": [36, 36], "no_touch": True},
    "grav_core": {"speed": 0, "size": 10, "color": [150, 90, 220], "life": 2.8, "ghost": True,
        "vortex": {"radius": 150, "force": 320, "damage": 4, "interval": 0.45}, "rotate": True,
        "draw": [46, 46], "no_touch": True},
    # ТЕНЬ
    "poison_trap": {"speed": 250, "vy": -240, "gravity": 1050, "bounces": 99, "bounce_damp": 0.45, "size": 7,
        "color": [140, 220, 110], "life": 14, "aoe": 70, "knockback": 120, "shake": 0.2,
        "mine": {"radius": 46, "arm": 0.7}, "effect": {"burn": {"time": 3, "dps": 8}},
        "skin": "projectiles/poison_trap.png", "draw": [26, 28]},
    "dark_core": {"speed": 0, "size": 10, "color": [110, 80, 190], "life": 2.8, "ghost": True,
        "vortex": {"radius": 130, "force": 240, "damage": 4, "interval": 0.55}, "rotate": True,
        "draw": [42, 42], "no_touch": True},
    "shadow_rain_marker": {"speed": 0, "size": 6, "color": [130, 120, 160], "life": 1.6, "ghost": True,
        "rain": {"into": "shadow_dagger", "count": 10, "interval": 0.14, "spread": 150, "height": 180},
        "draw": [24, 24], "no_touch": True},
    "night_blade": {"speed": 0, "size": 7, "color": [150, 170, 230], "life": 4.5, "ghost": True, "pierce": 999,
        "orbit": {"radius": 54, "speed": 3.4, "rehit": 0.6}, "knockback": 50,
        "skin": "projectiles/night_blade.png", "draw": [24, 24]},
}

with io.open("data/projectiles.json", encoding="utf-8") as f:
    d = json.load(f)
added = [k for k in P if k not in d]
d.update(P)
with io.open("data/projectiles.json", "w", encoding="utf-8") as f:
    json.dump(d, f, ensure_ascii=False, indent=2)
print(f"снарядов добавлено: {len(added)} (всего: {len(d)}): {', '.join(added)}")
