# -*- coding: utf-8 -*-
"""Добавляет 50 новых навыков (10 на героя) в data/skills.json и раздаёт их героям в data/characters.json.
Все навыки используют существующие типы заклинаний (@spell в spells.py) и поведения снарядов (@behavior в projectiles.py).
Новые записи снарядов — в data/projectiles.json (это отдельный скрипт-патч _patch_hero_projectiles.py).
"""
import json, io, sys
sys.stdout.reconfigure(encoding="utf-8")

SKILLS = {
    # ------------------------------------------------------------------ РЫЦАРЬ — сталь, щит, молот, свет
    "hammer_fall": {"name": "Падение молота", "category": "active", "type": "strike_area",
        "cooldown": 7.0, "radius": 95, "damage": 38, "stun": 1.2, "knockback": 240, "mana_cost": 22,
        "color": [255, 205, 120], "description": "Молот обрушивается на область перед рыцарем: урон, отброс и оглушение на 1.2 секунды."},
    "sword_boomerang": {"name": "Метательный меч", "category": "active", "type": "projectile", "projectile": "steel_boomerang",
        "cooldown": 4.0, "damage": 16, "mana_cost": 12,
        "color": [200, 215, 235], "description": "Стальной меч летит вперёд и возвращается, задевая врагов на обоих путях — даже сквозь стены."},
    "shield_bash": {"name": "Удар щитом", "category": "active", "type": "nova",
        "cooldown": 5.0, "radius": 90, "damage": 18, "knockback": 340, "mana_cost": 14,
        "color": [200, 210, 230], "description": "Резкий удар щитом вокруг себя: почти не ранит, но сильно отбрасывает всех рядом."},
    "holy_ward": {"name": "Святой оберег", "category": "active", "type": "shield",
        "cooldown": 14.0, "duration": 6, "capacity": 120, "radius": 42, "mana_cost": 26,
        "color": [255, 225, 140], "description": "Святая аура на 6 секунд: щит выдерживает 120 урона."},
    "warcry": {"name": "Боевой клич", "category": "active", "type": "nova",
        "cooldown": 8.0, "radius": 150, "damage": 8, "knockback": 360, "mana_cost": 18,
        "color": [255, 180, 110], "description": "Громкий клич: волна страха отшвыривает толпу вокруг."},
    "light_lance": {"name": "Копьё света", "category": "active", "type": "beam",
        "cooldown": 6.5, "range": 430, "width": 24, "damage": 36, "mana_cost": 28,
        "color": [255, 235, 170], "description": "Мгновенное копьё света пронзает всех врагов на линии перед рыцарем."},
    "iron_mine": {"name": "Железная мина", "category": "active", "type": "projectile", "projectile": "iron_mine",
        "cooldown": 6.0, "damage": 32, "mana_cost": 16,
        "color": [150, 170, 200], "description": "Брошенная мина ложится на пол, взводится и взрывается, когда враг подходит близко."},
    "consecrated_ground": {"name": "Освящённая земля", "category": "active", "type": "projectile", "projectile": "holy_zone",
        "cooldown": 9.0, "damage": 7, "mana_cost": 24,
        "color": [255, 220, 120], "description": "Земля под курсором освящается: 4 секунды жжёт нечисть в круге (урон тиками)."},
    "banner_of_war": {"name": "Знамя войны", "category": "passive", "type": "damage", "multiplier": 1.12,
        "color": [255, 190, 100], "description": "Пассивно: знамя ведёт бойца в бой — весь урон +12%."},
    "tempered_armor": {"name": "Закалённая броня", "category": "passive", "type": "max_hp", "amount": 40,
        "color": [190, 200, 220], "description": "Пассивно: кованая броня — +40 к максимуму здоровья."},

    # ------------------------------------------------------------------ БАРД — музыка, звук, струны
    "sound_wave": {"name": "Звуковая волна", "category": "active", "type": "projectile", "projectile": "sound_wave",
        "cooldown": 1.1, "damage": 14, "mana_cost": 9,
        "color": [255, 200, 120], "description": "Струна пускает волну, которая змейкой летит в курсор и бьёт врагов."},
    "sonic_boomerang": {"name": "Звуковой бумеранг", "category": "active", "type": "projectile", "projectile": "sonic_boomerang",
        "cooldown": 3.5, "damage": 15, "mana_cost": 12,
        "color": [120, 230, 255], "description": "Вибрирующая волна летит вперёд и возвращается, задевая врагов на обоих путях."},
    "power_chord": {"name": "Мощный аккорд", "category": "active", "type": "nova",
        "cooldown": 6.0, "radius": 150, "damage": 24, "knockback": 260, "mana_cost": 20,
        "color": [255, 170, 90], "description": "Грязный аккорд: ударная волна ранит и отбрасывает всех вокруг барда."},
    "healing_verse": {"name": "Лечебный стих", "category": "active", "type": "heal",
        "cooldown": 11.0, "amount": 26, "radius": 80, "mana_cost": 24,
        "color": [110, 230, 140], "description": "Тёплый стих лечит барда и союзников рядом на 26 здоровья."},
    "bass_cannon": {"name": "Бас-пушка", "category": "active", "type": "beam",
        "cooldown": 7.0, "range": 480, "width": 34, "damage": 34, "mana_cost": 30,
        "color": [255, 160, 100], "description": "Низкая частота: мощный звуковой луч пронзает всех на линии."},
    "metronome": {"name": "Метроном", "category": "active", "type": "projectile", "projectile": "sound_wave",
        "cooldown": 0.0, "hold": True, "duration": 3.0, "recharge": 6.0, "interval": 0.3, "damage": 7, "mana_cost": 12,
        "spread": 12, "color": [255, 215, 140], "description": "Поток: зажми клавишу — метроном отбивает волны в курсор, пока есть запас (3 сек)."},
    "dance_of_strings": {"name": "Танец струн", "category": "active", "type": "projectile", "projectile": "string_blade",
        "cooldown": 9.0, "damage": 9, "count": 3, "spread": 120, "mana_cost": 26,
        "color": [255, 210, 130], "description": "Три струны кружат вокруг барда и режут всех рядом."},
    "final_chord": {"name": "Финальный аккорд", "category": "active", "type": "projectile", "projectile": "splitter",
        "cooldown": 5.0, "damage": 16, "mana_cost": 18,
        "color": [255, 140, 180], "description": "Аккорд лопается о первого врага и распадается кольцом искр."},
    "perfect_pitch": {"name": "Абсолютный слух", "category": "passive", "type": "note_radius", "multiplier": 1.15,
        "color": [140, 220, 255], "description": "Пассивно: слух чуткий — радиус всех нот +15%."},
    "stage_experience": {"name": "Сценический опыт", "category": "passive", "type": "max_mana", "amount": 25,
        "color": [150, 180, 255], "description": "Пассивно: годы концертов — +25 к максимуму маны."},

    # ------------------------------------------------------------------ ИНЖЕНЕР — техника, ракеты, лазеры
    "rocket": {"name": "Ракета", "category": "active", "type": "projectile", "projectile": "rocket",
        "cooldown": 3.0, "damage": 30, "mana_cost": 18,
        "color": [255, 120, 60], "description": "Медленно стартует, разгоняется и взрывается при попадании."},
    "gatling": {"name": "Гатлинг", "category": "active", "type": "projectile", "projectile": "pellet",
        "cooldown": 1.8, "damage": 6, "count": 5, "spread": 14, "mana_cost": 16,
        "color": [255, 214, 120], "description": "Очередь из пяти пуль широким веером."},
    "shock_grenade": {"name": "Шоковая граната", "category": "active", "type": "projectile", "projectile": "shock_grenade",
        "cooldown": 5.0, "damage": 24, "mana_cost": 16,
        "color": [255, 230, 90], "description": "Граната скачет по полу и взрывается шоком: урон и оглушение по области."},
    "drone_swarm": {"name": "Рой дронов", "category": "active", "type": "projectile", "projectile": "homing_orb",
        "cooldown": 4.5, "damage": 8, "count": 3, "spread": 20, "mana_cost": 20, "projectile_pierce": 1,
        "color": [120, 220, 255], "description": "Три дрона сами находят врагов, пробивают первого и ищут следующего."},
    "laser_cutter": {"name": "Лазерный резак", "category": "active", "type": "beam",
        "cooldown": 5.5, "range": 380, "width": 18, "damage": 30, "mana_cost": 24,
        "color": [255, 90, 90], "description": "Тонкий луч режет всех на линии и поджигает на 2 секунды."},
    "repair_kit": {"name": "Ремкомплект", "category": "active", "type": "heal",
        "cooldown": 10.0, "amount": 20, "radius": 60, "mana_cost": 20,
        "color": [120, 235, 200], "description": "Полевая аптечка: 20 здоровья себе и соседям."},
    "magnet_field": {"name": "Магнитное поле", "category": "active", "type": "projectile", "projectile": "magnet_core",
        "cooldown": 11.0, "damage": 3, "mana_cost": 36,
        "color": [120, 220, 255], "description": "Электромагнит в курсоре: 2.8 секунды стягивает врагов к центру и жжёт тиками."},
    "oil_slick": {"name": "Масляная лужа", "category": "active", "type": "projectile", "projectile": "oil_zone",
        "cooldown": 8.0, "damage": 4, "mana_cost": 22,
        "color": [130, 110, 190], "description": "Лужа масла в курсоре: враги в ней вязнут (короткое замораживание тиками)."},
    "overdrive": {"name": "Разгон", "category": "passive", "type": "move_speed", "multiplier": 1.1,
        "color": [140, 230, 255], "description": "Пассивно: механизмы разогнаны — скорость передвижения +10%."},
    "workshop_oil": {"name": "Смазка механизмов", "category": "passive", "type": "mana_regen", "multiplier": 1.4,
        "color": [160, 160, 200], "description": "Пассивно: всё смазано — регенерация маны +40%."},

    # ------------------------------------------------------------------ ЧАРОДЕЙ — аркана
    "arcane_lance": {"name": "Копьё магии", "category": "active", "type": "projectile", "projectile": "arcane_bolt",
        "cooldown": 1.6, "damage": 24, "mana_cost": 14, "projectile_speed": 380, "projectile_pierce": 1,
        "color": [190, 130, 255], "description": "Быстрое копьё чистой магии пронзает первую цель и летит дальше."},
    "void_pulse": {"name": "Пульс пустоты", "category": "active", "type": "nova",
        "cooldown": 6.5, "radius": 120, "damage": 22, "knockback": 200, "mana_cost": 22,
        "color": [150, 90, 220], "description": "Импульс пустоты расходится вокруг и отбрасывает врагов."},
    "crystal_boomerang": {"name": "Кристальный бумеранг", "category": "active", "type": "projectile", "projectile": "crystal_boomerang",
        "cooldown": 3.5, "damage": 20, "mana_cost": 15,
        "color": [180, 230, 255], "description": "Кристалл летит вперёд и возвращается, рассекая врагов на обоих путях."},
    "frost_ring": {"name": "Морозное кольцо", "category": "active", "type": "nova",
        "cooldown": 7.0, "radius": 110, "damage": 16, "knockback": 120, "effect": {"freeze": 1.2}, "mana_cost": 20,
        "color": [150, 230, 255], "description": "Кольцо льда: урон и заморозка на 1.2 секунды."},
    "arcane_ward": {"name": "Аркановый щит", "category": "active", "type": "shield",
        "cooldown": 15.0, "duration": 7, "capacity": 90, "radius": 42, "mana_cost": 24,
        "color": [170, 140, 255], "description": "Аркановый купол на 7 секунд: поглощает 90 урона."},
    "star_fall": {"name": "Звездопад", "category": "active", "type": "projectile", "projectile": "starfall_marker",
        "cooldown": 8.0, "damage": 10, "mana_cost": 30,
        "color": [255, 240, 180], "description": "В области курсора с неба падают осколки звёзд."},
    "tempest": {"name": "Гроза", "category": "active", "type": "projectile", "projectile": "tempest_core",
        "cooldown": 10.0, "damage": 11, "mana_cost": 32,
        "color": [150, 190, 255], "description": "Шторм в курсоре: 9 разрядов молнии бьют по площади, поджигая врагов."},
    "gravity_well": {"name": "Гравитационный колодец", "category": "active", "type": "projectile", "projectile": "grav_core",
        "cooldown": 13.0, "damage": 4, "mana_cost": 42,
        "color": [150, 90, 220], "description": "Складка гравитации в курсоре: стягивает врагов сильнее, чем чёрная дыра."},
    "mana_crystal": {"name": "Мана-кристалл", "category": "passive", "type": "max_mana", "amount": 30,
        "color": [120, 200, 255], "description": "Пассивно: кристалл в сумке — +30 к максимуму маны."},
    "arcane_mind": {"name": "Аркановый разум", "category": "passive", "type": "mana_regen", "multiplier": 1.4,
        "color": [190, 130, 255], "description": "Пассивно: разум настроен на поток — регенерация маны +40%."},

    # ------------------------------------------------------------------ ТЕНЬ — тьма, скорость, клинки
    "shadow_burst": {"name": "Теневой залп", "category": "active", "type": "projectile", "projectile": "shadow_dagger",
        "cooldown": 2.0, "damage": 9, "count": 4, "spread": 16, "mana_cost": 12,
        "color": [170, 150, 220], "description": "Веер из четырёх теневых кинжалов."},
    "blade_fan": {"name": "Веер клинков", "category": "active", "type": "nova",
        "cooldown": 4.5, "radius": 95, "damage": 16, "knockback": 160, "mana_cost": 14,
        "color": [150, 170, 230], "description": "Взмах клинками вокруг себя — короткая волнf стали."},
    "phantom_step": {"name": "Шаг сквозь тень", "category": "active", "type": "dash",
        "cooldown": 3.0, "speed": 700, "invulnerability": 0.22, "radius": 24, "mana_cost": 10,
        "color": [130, 130, 190], "description": "Мгновенный рывок сквозь тени: чуть быстрее обычного и с longer неуязвимостью."},
    "smoke_bomb": {"name": "Дымовая бомба", "category": "active", "type": "invisibility",
        "cooldown": 14.0, "duration": 5.0, "mana_cost": 20,
        "color": [120, 110, 140], "description": "Облако дыма скрывает Тень на 5 секунд."},
    "poison_trap": {"name": "Ядовитая ловушка", "category": "active", "type": "projectile", "projectile": "poison_trap",
        "cooldown": 6.0, "damage": 20, "mana_cost": 16,
        "color": [140, 220, 110], "description": "Спрятанная ловушка взводится и взрывается ядом, поджигающим врага на 3 секунды."},
    "dark_vortex": {"name": "Тёмная воронка", "category": "active", "type": "projectile", "projectile": "dark_core",
        "cooldown": 12.0, "damage": 4, "mana_cost": 36,
        "color": [110, 80, 190], "description": "Воронка тьмы в курсоре: стягивает врагов и грызёт их тиками."},
    "shadow_rain": {"name": "Теневой дождь", "category": "active", "type": "projectile", "projectile": "shadow_rain_marker",
        "cooldown": 7.5, "damage": 10, "mana_cost": 28,
        "color": [130, 120, 160], "description": "В области курсора сверху падают теневые кинжалы."},
    "night_blades": {"name": "Ночные клинки", "category": "active", "type": "projectile", "projectile": "night_blade",
        "cooldown": 9.5, "damage": 8, "count": 4, "spread": 90, "mana_cost": 26,
        "color": [150, 170, 230], "description": "Четыре призрачных клинка кружат вокруг Тени и режут всё рядом."},
    "lightfoot": {"name": "Лёгкая поступь", "category": "passive", "type": "move_speed", "multiplier": 1.08,
        "color": [170, 180, 220], "description": "Пассивно: тихие шаги — скорость передвижения +8%."},
    "night_vigor": {"name": "Ночная живучесть", "category": "passive", "type": "max_hp", "amount": 30,
        "color": [130, 140, 190], "description": "Пассивно: ночь закаляет — +30 к максимуму здоровья."},
}

HERO_ADDS = {
    "knight":   {"base": ["hammer_fall", "sword_boomerang", "shield_bash", "holy_ward"],
                 "tree": [("warcry", 9), ("light_lance", 10), ("iron_mine", 11), ("consecrated_ground", 12),
                          ("banner_of_war", 13), ("tempered_armor", 14)]},
    "bard":     {"base": ["sound_wave", "sonic_boomerang", "power_chord", "healing_verse"],
                 "tree": [("bass_cannon", 9), ("metronome", 10), ("dance_of_strings", 11), ("final_chord", 12),
                          ("perfect_pitch", 13), ("stage_experience", 14)]},
    "ranger":   {"base": ["rocket", "gatling", "shock_grenade", "drone_swarm", "laser_cutter", "repair_kit"],
                 "tree": [("magnet_field", 9), ("oil_slick", 10), ("overdrive", 11), ("workshop_oil", 12)]},
    "mage":     {"base": ["arcane_lance", "void_pulse", "crystal_boomerang", "frost_ring", "arcane_ward"],
                 "tree": [("star_fall", 7), ("tempest", 8), ("gravity_well", 9), ("mana_crystal", 10), ("arcane_mind", 11)]},
    "shadow":   {"base": ["shadow_burst", "blade_fan", "phantom_step", "smoke_bomb"],
                 "tree": [("poison_trap", 9), ("dark_vortex", 10), ("shadow_rain", 11), ("night_blades", 12),
                          ("lightfoot", 13), ("night_vigor", 14)]},
}

# ------------------------------------------------------------------ skills.json
with io.open("data/skills.json", encoding="utf-8") as f:
    skills = json.load(f)
new_ids = list(SKILLS)
added = [sid for sid in new_ids if sid not in skills]
skills.update(SKILLS)
with io.open("data/skills.json", "w", encoding="utf-8") as f:
    json.dump(skills, f, ensure_ascii=False, indent=2)

# ------------------------------------------------------------------ characters.json
with io.open("data/characters.json", encoding="utf-8") as f:
    chars = json.load(f)
per_hero = 0
for cid, add in HERO_ADDS.items():
    c = chars["characters"][cid]
    for sid in add["base"]:
        if sid not in c["base_skills"]:
            c["base_skills"].append(sid); per_hero += 1
    tree = c.setdefault("skill_tree", [])
    have = {s.get("skill") for s in tree}
    for sid, lvl in add["tree"]:
        if sid not in have:
            tree.append({"skill": sid, "unlock_level": lvl}); per_hero += 1
with io.open("data/characters.json", "w", encoding="utf-8") as f:
    json.dump(chars, f, ensure_ascii=False, indent=2)

print(f"навыков добавлено: {len(added)} (всего в skills.json: {len(skills)})")
print(f"выдано героям: {per_hero} слотов (база + дерево)")
for cid, add in HERO_ADDS.items():
    c = chars["characters"][cid]
    print(f"  {cid}: база {len(c['base_skills'])}, дерево {len(c['skill_tree'])}")
