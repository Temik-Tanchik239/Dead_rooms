"""Зоны на полу от атак мобов (attacks.py -> Bomb): кислотные лужи и прочие ловушки.
Зона живёт в комнате: r.zones (maps.py -> GameMap.__init__); тикает и рисуется в main.py рядом с пулями.
Зона наносит урон раз в TICK всем игрокам, кто в ней стоит (мобов она не задевает).
Внимание: attacks.py импортирует отсюда Zone, поэтому players_of отсюда берётся лениво (внутри update)."""
import random

import pygame as pg
from core import circle_hits_rect

TICK = 0.4          # раз в сколько секунд зона наносит урон
COLORS = {"acid": (110, 200, 90), "fire": (255, 140, 60), "ice": (110, 190, 255)}


def update_room(r, dt, w):
    """Тик всех зон комнаты (вызывается из main.py рядом с обновлением пуль)."""
    for z in getattr(r, "zones", ()):
        z.update(dt, w)


class Zone:
    def __init__(s, kind="acid", x=0, y=0, radius=46, dps=10, life=4.0):
        s.kind = kind if kind in COLORS else "acid"
        s.x, s.y = float(x), float(y)
        s.radius = max(6.0, float(radius))
        s.dps = float(dps)
        s.life = s.left = max(0.5, float(life))
        s.tick = TICK
        s.t = 0.0

    @property
    def dead(s): return s.left <= 0

    def update(s, dt, w):
        """Тик зоны: урон стоящим в ней игрокам (раз в TICK) + редкие частицы."""
        from attacks import players_of   # лениво: attacks.py импортирует отсюда Zone (циклический импорт)
        s.t += dt; s.left -= dt; s.tick -= dt
        if s.tick > 0: return
        s.tick = TICK
        dmg = s.dps * TICK
        if dmg > 0:
            for p in players_of(w):
                if circle_hits_rect(s.x, s.y, s.radius, p.rect):
                    p.hit(dmg, s.x, w.fx, 0)
        if int(s.t * 4) != int((s.t - dt) * 4):   # пару раз в секунду — пузырёк-частица
            w.fx.ring(s.x + random.uniform(-s.radius, s.radius) * .7,
                      s.y + random.uniform(-s.radius, s.radius) * .7, 6)

    def draw(s, v):
        """Лужа: полупрозрачный круг (ярче, пока жива) + контур."""
        k = max(0.0, min(1.0, s.left / max(s.life, 0.01)))
        col = COLORS[s.kind]
        r = int(s.radius)
        surf = pg.Surface((r * 2, r * 2), pg.SRCALPHA)
        pg.draw.circle(surf, (col[0], col[1], col[2], int(48 + 44 * k)), (r, r), r)
        v.blit(surf, (s.x - r, s.y - r))
        pg.draw.circle(v, col, (int(s.x), int(s.y)), r, 2)
