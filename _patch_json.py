import json
p = 'data/skills.json'
d = json.load(open(p, encoding='utf-8'))
d['inferno'] = {
    'name': 'Огненная аура',
    'category': 'active',
    'type': 'aura',
    'sustained': True,
    'mana_cost': 30,
    'reserve': 150,
    'reserve_regen': 45,
    'radius': 100,
    'dps': 26,
    'interval': 0.3,
    'knockback': 30,
    'effect': {'burn': {'time': 1.2, 'dps': 4}},
    'icon': 'icons/skill_inferno.png',
    'color': [255, 130, 40],
    'cast_animation': 0.5,
    'description': ('Удерживаемый навык с запасом: зажмите клавишу и стойте на месте — вокруг героя бушует '
                    'огненная аура, сжигающая врагов рядом. Пока колдуете, расходуется ЗАПАС навыка (30 маны в '
                    'секунду); отпустите — расход прекратится и запас восстановится с этого уровня (45/с). '
                    'Перезарядки нет: включить ауру можно в любой момент, пока есть запас.'),
}
json.dump(d, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('added inferno; keys:', list(d.keys()))
