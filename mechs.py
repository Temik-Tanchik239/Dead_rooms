"""Механизмы: рычаги, кнопки, двери, лифты, телепорты и подвижные платформы.

Все типы описаны в data/mechs.json (размер, цвет, скорость, подсказки). Расстановка и настройки
каждого механизма — в редакторе карт (панель «Механизмы», mech_panel.py), лежат в JSON карты, поле "mechanisms":
    {"id": 1, "type": "lever",      "x": 4,  "y": 8,  "channel": "d1"}                рычаг: E рядом переключает канал d1;
    {"id": 2, "type": "door",       "x": 10, "y": 5, "w": 1, "h": 4, "channel": "d1"}  дверь открыта, пока канал активен;
    {"id": 3, "type": "button",     "x": 6,  "y": 12, "channel": "d2"}                 кнопка: активна, пока герой стоит на ней;
    {"id": 4, "type": "elevator",   "x": 6,  "y": 12, "w": 3, "h": 1, "channel": "d2", "range": 5, "mode": "control"}
        лифт: активный канал ведёт вверх, неактивный — вниз; "mode": "auto" — ездит сам туда-сюда;
    {"id": 5, "type": "teleporter", "x": 3,  "y": 4,  "channel": "", "pair": 6}        портал: шаг внутрь телепортирует к партнёру 6;
    {"id": 7, "type": "mover",      "x": 15, "y": 9, "w": 2, "channel": "", "speed": 60,
     "path": [[15,9],[15,5],[18,5],[18,9]], "loop": true}
        подвижная платформа: ездит по точкам path (клетки), "loop" — по кругу, иначе качается.

Связь «кнопка/рычаг -> механизм» — по имени канала (channel). Чтобы у каждого механизма была СВОЯ кнопка,
дай паре уникальное имя канала; один канал можно дать сразу нескольким механизмам (группа дверей).
Порталы связываются не каналом, а парой id (pair): работает ТОЛЬКО со своим партнёром.

Жизнь системы:
  • GameMap.__init__ создаёт room.mechs = mechs.create(room); room.mech_by_id(id);
  • GameMap.build вызывает mechs.block(room) — закрытые двери становятся стенами (#) в физической сетке;
  • каждый кадр main.step:
      mechs.presolve(room, pl)    — перед физикой игрока: кнопки/рычаги -> сигналы каналов, двери обновляют клетки;
      mechs.update(room, dt, pl, fx) — после физики: лифты/платформы двигаются и несут героя и мобов, порталы срабатывают.
  • в мультиплеере всё считает хост: state() в снимок, apply_state() на клиентах (как у ящиков).

Геометрия механизма задаётся в клетках: x, y — верхний левый угол (для ящико-механизмов, дверей,
лифтов, порталов). У движущихся платформ (elevator/mover) позиция — пиксельная: s.pl = [px, py].
"""
import math
import pygame as pg
from core import CFG, T
from anim import sprite, ASSETS_EXISTS

DEFAULTS = {"name": "Механизм", "w": 1, "h": 1, "color": [150, 150, 170], "draw": None, "offset": [0, 0],
            "skin": "", "skin_on": "", "active_skin": "", "prompt": "", "reach": 44,
            "speed": 60.0, "range": 4, "press_delay": 0.25, "cooldown": 1.0, "thickness": 12}
CONTROLS = ("lever", "button")      # источники сигнала
MOVERS = ("elevator", "mover")      # движущиеся платформы


def types():
    """Все типы механизмов: id -> описание (data/mechs.json, ключ "mechs")."""
    d = CFG.get("mechs") or {}
    return d.get("mechs", {}) if isinstance(d, dict) else {}


def type_def(tid):
    d = dict(DEFAULTS); d.update(types().get(tid, {})); return d


# ---------------- объект механизма ----------------
class Mech:
    def __init__(s, room, spec):
        s.room = room; s.spec = spec
        s.tid = spec.get("type", ""); s.d = type_def(s.tid)
        s.id = int(spec.get("id", 0))
        s.cx0 = int(spec["x"]); s.cy0 = int(spec["y"])   # клетка верхнего левого угла
        s.w = max(1, int(spec.get("w", s.d["w"])))
        s.h = max(1, int(spec.get("h", s.d["h"])))
        s.wpx, s.hpx = s.w * T, s.h * T
        s.th = int(s.d.get("thickness", 12))
        s.channel = spec.get("channel", "") or ""
        s.on = False; s.last_on = False
        s.t = 0.0; s.cd = 0.0
        s.y0px = s.cy0 * T
        s.range = max(0, int(spec.get("range", s.d.get("range", 4))))
        s.mode = spec.get("mode", "").lower()
        # Движущиеся платформы: пиксельная позиция верха.
        s.pl = [s.cx0 * T, s.cy0 * T]   # px, py — верхний левый угол
        s.p0 = (s.cx0 * T, s.cy0 * T)
        s.path = [(int(p[0]) * T, int(p[1]) * T) for p in (spec.get("path") or [])]
        if not s.path: s.path = [s.p0]
        s.wpi = 0; s.forward = 1; s.auto_target = None
        s.pair = spec.get("pair")
        s.prev = (s.pl[0], s.pl[1])

    # ---------- прямоугольники ----------
    @property
    def rect(s):
        """Физический прямоугольник механизма (для захвата/портала/кнопки)."""
        if s.tid in MOVERS:
            return pg.Rect(int(s.pl[0] + 2), int(s.pl[1]), max(1, s.wpx - 4), s.th)
        return pg.Rect(s.cx0 * T, s.cy0 * T, s.wpx, s.hpx)

    @property
    def cx(s): return s.rect.centerx
    @property
    def cy(s): return s.rect.centery

    def cells(s):
        """Клетки, которые механизм сейчас занимает (для дверей; у платформ — клетка под ней)."""
        if s.tid in MOVERS:
            c, r = int(s.pl[0] // T), int(s.pl[1] // T)
            return [(c + i, r) for i in range(max(1, s.wpx // T))]
        return [(s.cx0 + i, s.cy0 + j) for j in range(s.h) for i in range(s.w)]

    # ---------- канал ----------
    def listen(s, signals):
        """Подчинённый механизм: берёт сигнал своего канала."""
        if s.tid in CONTROLS: return
        if s.channel: s.on = bool(signals.get(s.channel, False))

    # ---------- кадр ----------
    def poll(s, pls):
        """Кнопка: активна, пока кто-то из игроков касается клетки кнопки (стоит на ней)."""
        if s.tid != "button": return
        if not isinstance(pls, (list, tuple)): pls = [pls] if pls else []
        zone = s.rect.inflate(T, int(T * 1.2))
        s.on = any(pl is not None and hasattr(pl, "rect") and zone.colliderect(pl.rect) for pl in pls)

    def step(s, dt):
        """Движение лифта/платформы; сдвиг (dx, dy) в пикселях относительно прошлого кадра."""
        if s.tid not in MOVERS: return 0, 0
        old = (s.pl[0], s.pl[1])
        if s.tid == "elevator": s._elev_step(dt)
        else: s._mover_step(dt)
        return s.pl[0] - old[0], s.pl[1] - old[1]

    def _elev_step(s, dt):
        speed = float(s.d.get("speed", 60)); lo = s.y0px - s.range * T   # лучшее место (вверху)
        hi = s.y0px                                                      # пол/место установки (внизу)
        if s.mode == "auto":
            if s.auto_target is None: s.auto_target = lo
            if s.pl[1] <= lo + 1: s.auto_target = hi
            elif s.pl[1] >= hi - 1: s.auto_target = lo
            target = s.auto_target
        else:   # control: активный канал поднимает лифт вверх (к lo), неактивный — опускает (к hi)
            target = lo if s.on else hi
        diff = target - s.pl[1]
        s.pl[1] += math.copysign(min(abs(diff), speed * dt), diff) if diff else 0.0

    def _mover_step(s, dt):
        if len(s.path) < 2: return
        speed = float(s.d.get("speed", 60))
        tx, ty = s.path[s.wpi]
        while True:
            dx, dy = tx - s.pl[0], ty - s.pl[1]
            dist = math.hypot(dx, dy)
            if dist <= speed * dt:
                if s.spec.get("loop"):
                    s.wpi = (s.wpi + 1) % len(s.path)
                else:
                    if s.wpi + s.forward < 0 or s.wpi + s.forward >= len(s.path): s.forward = -s.forward
                    s.wpi += s.forward
                tx, ty = s.path[s.wpi]
                continue
            s.pl[0] += dx / dist * speed * dt; s.pl[1] += dy / dist * speed * dt
            break

    def carry(s, room, pl, dx, dy):
        """Нести героя и мобов, стоящих на платформе. Захват — ноги в полосе над ней; прыжок (vy<0) освобождает."""
        if s.tid not in MOVERS: return
        band = pg.Rect(int(s.pl[0] + 2), int(s.pl[1]) - 10, max(1, s.wpx - 4), 18)
        ents = [pl] if not getattr(pl, "downed", False) else []
        ents += [m for m in room.mobs if not m.flies]
        for ent in ents:
            if ent.vy < 0: continue
            if not ent.rect.colliderect(band): continue
            ent.x += dx; ent.y = s.pl[1] - ent.h
            ent.vy = 0.0; ent.ground = True
            if ent is pl: pl.air_jumps = 0

    # ---------- телепорт ----------
    def teleport_pass(s, room, pl, fx, dt):
        if s.tid != "teleporter": return
        s.cd = max(0.0, s.cd - dt)
        if s.channel and not s.on: return
        partner = room.mech_by_id(s.pair)
        if partner is None or partner.tid != "teleporter": return
        if s.cd > 0 or partner.cd > 0: return
        zone = s.rect.inflate(-6, -10)
        ents = ([pl] if not getattr(pl, "downed", False) else []) + list(room.mobs)
        for ent in ents:
            if ent.rect.colliderect(zone) and ent.vy >= 0:
                s.cd = partner.cd = float(s.d.get("cooldown", 1.0))
                ent.x, ent.y = partner.rect.centerx - ent.w / 2, partner.rect.bottom - ent.h
                ent.vx = ent.vy = 0.0
                c1 = tuple(s.d.get("color")); c2 = tuple(partner.d.get("color"))
                fx.flash(s.cx, s.cy, 30, c1); fx.flash(partner.cx, partner.cy, 30, c2)
                fx.ring(partner.cx, partner.cy, 26)
                break

    # ---------- рисование ----------
    def draw(s, v):
        d = s.d; r = s.rect; now = pg.time.get_ticks(); s.t = now / 1000
        skin = d.get("skin_on") if s.on and d.get("skin_on") else d.get("skin")
        if skin and ASSETS_EXISTS(skin):
            dw, dh = d.get("draw") or [r.w, r.h]; ox, oy = d.get("offset", [0, 0])
            img = sprite(skin, int(dw), int(dh))
            if img: v.blit(img, (r.centerx - dw // 2 + ox, r.bottom - dh + oy)); return
        col = tuple(int(c) for c in d.get("color"))
        on = tuple(min(255, int(c + 70)) for c in col)
        c = on if s.on else col
        if s.tid == "lever":
            pg.draw.rect(v, (70, 60, 50), (r.centerx - 5, r.y - 4, 10, 16))
            pg.draw.circle(v, c, (r.centerx, r.y + 4), 7)
            if s.on: pg.draw.rect(v, (120, 255, 140), (r.centerx - 10, r.y - 16, 20, 5))
        elif s.tid == "button":
            pg.draw.rect(v, (60, 55, 50), r.inflate(2, 2))
            pg.draw.ellipse(v, c, r.inflate(-6, -10))
            if s.on: pg.draw.ellipse(v, (180, 255, 200), r.inflate(-10, -14))
        elif s.tid == "door":
            pg.draw.rect(v, (45, 38, 42), r.inflate(4, 4))
            if not s.on:
                pg.draw.rect(v, c, r.inflate(-5, -5))
                pg.draw.line(v, (30, 20, 20), (r.x + 4, r.y + 4), (r.right - 4, r.bottom - 4), 4)
                pg.draw.line(v, (30, 20, 20), (r.right - 4, r.y + 4), (r.x + 4, r.bottom - 4), 4)
            else:
                pg.draw.rect(v, (90, 120, 90), r.inflate(-6, -6), 3)
        elif s.tid == "teleporter":
            sh = pg.Surface((r.w, r.h), pg.SRCALPHA); sh.fill((*c, 70 if not s.on else 150)); v.blit(sh, r)
            pg.draw.rect(v, c, r, 3)
            for i in range(4):
                yy = (now // 120 + i * 13) % max(1, r.h)
                pg.draw.line(v, c, (r.x + 6, r.y + yy), (r.right - 6, r.y + yy), 2)
        elif s.tid == "mover":
            pg.draw.rect(v, (40, 50, 60), r.inflate(6, 3))
            pg.draw.rect(v, (95, 215, 155) if s.on else c, r)
        elif s.tid == "elevator":
            pg.draw.rect(v, (40, 50, 60), r.inflate(6, 3))
            pg.draw.rect(v, (120, 200, 255), r)


# ---------------- комната ----------------
def create(room):
    """Механизмы карты из room.d["mechanisms"] (вызывается из GameMap.__init__)."""
    out = []
    for spec in (room.d.get("mechanisms") or []):
        if not isinstance(spec, dict) or spec.get("type") not in types(): continue
        try: out.append(Mech(room, spec))
        except (KeyError, TypeError, ValueError): continue
    room._mech_by_id = {m.id: m for m in out}
    room.mech_signals = {}
    return out


def _door_block(room, m):
    for c, r in m.cells():
        if 0 <= r < len(room.g) and 0 <= c < len(room.g[r]): room.g[r][c] = "#"


def _door_free(room, m):
    for c, r in m.cells():
        if 0 <= r < len(room.g) and 0 <= c < len(room.g[r]):
            room.g[r][c] = room.base_cell(c, r)


def block(room):
    """Закрытые двери — стены (#) в физической сетке; кнопки — одно-сторонние платформы (=), на которых стоит герой.
    Вызывается из GameMap.build (после построения карты)."""
    for m in room.mechs:
        if m.tid == "door" and not m.on: _door_block(room, m)
        elif m.tid == "button":
            # кнопка — платформа: герой встаёт на неё сверху, ходить сквозь/прыгать снизу можно
            for c, r in m.cells():
                if 0 <= r < len(room.g) and 0 <= c < len(room.g[r]) and room.g[r][c] in (".", "="): room.g[r][c] = "="


def presolve(room, pls=None):
    """Перед физикой игрока: кнопки/рычаги -> сигналы каналов; двери обновляют клетки под сигнал.
    pls — одиночный игрок (одиночная игра) или список (хост сети)."""
    signals = {}
    for m in room.mechs:
        if pls is not None: m.poll(pls)
        if m.tid in CONTROLS and m.channel: signals[m.channel] = m.on
    room.mech_signals = signals
    for m in room.mechs:
        m.listen(signals)
        if m.tid == "door" and m.on != m.last_on:
            if m.on: _door_free(room, m)
            else: _door_block(room, m)
            m.last_on = m.on


def update(room, dt, pl=None, fx=None):
    """После физики: лифты/платформы двигаются и несут героя и мобов, порталы срабатывают."""
    if dt <= 0: return   # на паузе ничего не движется и порталы не срабатывают
    for m in room.mechs:
        if m.tid not in MOVERS: continue
        dx, dy = m.step(dt)
        m.carry(room, pl, dx, dy)
    for m in room.mechs:
        if m.tid == "teleporter": m.teleport_pass(room, pl, fx, dt)


def draw(room, v):
    for m in room.mechs: m.draw(v)


def draw_prompts(v, room, pl, font):
    """Подсказка «[E] Рычаг» рядом с героем."""
    for m in room.mechs:
        if m.tid == "lever" and m.rect.inflate(2 * int(m.d.get("reach", 44)), 2 * int(m.d.get("reach", 44))).colliderect(pl.rect):
            t = font.render(str(m.d.get("prompt") or "[E] Рычаг"), True, (255, 230, 120))
            v.blit(t, (m.cx - t.get_width() // 2, m.cy - 36))


def try_toggle(room, pl, fx):
    """E рядом с рычагом: переключить его. True — переключили."""
    for m in room.mechs:
        if m.tid == "lever" and m.rect.inflate(2 * int(m.d.get("reach", 44)), 2 * int(m.d.get("reach", 44))).colliderect(pl.rect):
            m.on = not m.on
            fx.ring(m.cx, m.cy, 24)
            fx.text("Вкл" if m.on else "Выкл", m.cx, m.cy - 24)
            return True
    return False


# ---------------- сеть ----------------
def state(room):
    """Состояние для снимка игры: {id: [on, верх платформы]}."""
    return {str(m.id): [int(m.on), round(m.pl[1], 2) if m.tid in MOVERS else 0] for m in room.mechs}


def apply_state(room, st):
    """Клиент: привести механизмы к состоянию хоста (двери обновляют клетки)."""
    if not isinstance(st, dict): return
    for m in room.mechs:
        v = st.get(str(m.id))
        if v is None: continue
        m.on = bool(v[0])
        if m.tid in MOVERS: m.pl[1] = float(v[1])
        if m.tid == "door" and m.on != m.last_on:
            if m.on: _door_free(room, m)
            else: _door_block(room, m)
            m.last_on = m.on
