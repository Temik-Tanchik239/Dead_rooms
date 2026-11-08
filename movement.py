"""Паттерны движения мобов. В mobs.json: "move": {"type": "chase", ...параметры}.
Общие параметры: speed (по умолчанию — speed моба), accel (как быстро набирает/меняет скорость).

Новый паттерн = функция с декоратором @movement("имя"), сигнатура fn(m, p, dt, w):
    m — моб (m.x, m.y, m.vx, m.vy, m.dir, m.home, m.aggro, m.flies ...), p — словарь "move" из json,
    w — мир (w.pl игрок, w.g сетка комнаты, w.mobs, w.projs, w.fx).
Функция меняет только m.vx / m.vy / m.dir: гравитацию и столкновения моб считает сам."""
import math
from core import T, MW, ROWS, tile, free, sign, approach
from invisibility import is_invisible

MOVES = {}
def movement(name):
    def reg(fn): MOVES[name] = fn; return fn
    return reg

# ---------- помощники ----------
def wall_ahead(m, w, d): return not free(w.g, m.rect.move(d * 4, 0))
def edge_ahead(m, w, d):
    ahead = int((m.cx + d * (m.w / 2 + 4)) // T); foot = int((m.y + m.h + 4) // T)
    return m.ground and tile(w.g, ahead, foot) not in "#=D"

def jump_speed(m, p):
    # Настройка в move.jump имеет приоритет; иначе используем безопасный прыжок,
    # достаточный примерно для преодоления стены/разрыва в 1–2 клетки.
    value = p.get("jump", m.d.get("jump", 0))
    return float(value) if value else float(m.d.get("auto_jump", 470))

def pit_landing(m, w, d, max_gap=3):
    """Ищет пол за пропастью: моб не прыгает в бесконечную пустоту."""
    foot = int((m.y + m.h + 3) // T)
    start = int((m.cx + d * (m.w / 2 + 3)) // T)
    for gap in range(1, max_gap + 2):
        col = start + d * gap
        support = tile(w.g, col, foot)
        if support in "#=D":
            # Проверяем, что корпус помещается в точке приземления.
            landing_x = col * T + (T - m.w) / 2
            landing = m.rect.copy()
            landing.x = int(landing_x)
            landing.y = int(foot * T - m.h)
            if free(w.g, landing):
                return gap
        if support in "#D" and tile(w.g, col, foot - 1) in "#D":
            break
    return 0

def try_ground_jump(m, p, w, d):
    """Прыгает только с пола и только если впереди есть свободная площадка."""
    if not m.ground or m.vy < -20:
        return False
    blocked = wall_ahead(m, w, d)
    gap = pit_landing(m, w, d, int(p.get("jump_gap", 3))) if edge_ahead(m, w, d) else 0
    if not blocked and not gap:
        return False
    # Для стены проверяем свободное пространство над мобом.
    if blocked and not free(w.g, m.rect.move(d * 5, -T - 2)):
        return False
    m.vy = -jump_speed(m, p)
    return True
def speed_of(m, p): return p.get("speed", m.d.get("speed", 80))

def steer(m, tx, ty, speed, accel, dt):
    """Плавно разгоняет летуна в сторону точки (tx, ty), у цели притормаживает."""
    dx, dy = tx - m.cx, ty - m.cy; dist = math.hypot(dx, dy) or 1
    sp = min(speed, dist * 4)
    m.vx = approach(m.vx, dx / dist * sp, accel * dt); m.vy = approach(m.vy, dy / dist * sp, accel * dt)

def patrol(m, p, dt, w):
    """Земной обход: идёт, у стены или края разворачивается."""
    if wall_ahead(m, w, m.dir) or edge_ahead(m, w, m.dir): m.dir *= -1
    m.vx = approach(m.vx, m.dir * speed_of(m, p) * p.get("patrol_speed", .6), p.get("accel", 1500) * dt)

def hover(m, p, dt, w):
    m.vy = math.sin(m.t * 2.5 + m.home[0]) * 30; m.vx = approach(m.vx, 0, 300 * dt)

def look(m, w, p):
    """Видит ли игрока; увидел — m.aggro = True. Невидимого игрока (invisibility.py) моб не замечает, а уже агрившийся
    теряет цель: агр сбрасывается, моб возвращается к обходу/покою."""
    if is_invisible(w.pl):
        m.aggro = False
        return False
    dx, dy = w.pl.cx - m.cx, w.pl.cy - m.cy
    if abs(dx) < p.get("sight", m.d.get("sight", 340)) and abs(dy) < p.get("sight_y", m.d.get("sight_y", 140)): m.aggro = True
    return m.aggro

# ---------- паттерны ----------

@movement("chase")
def chase(m, p, dt, w):
    """Жёсткий агр: увидел — прёт прямо на игрока и больше не отстаёт.
    sight / sight_y — дальность обзора (до агра), jump — скорость прыжка через стенку в 1 блок (0 — не прыгает),
    drop — спрыгивать с края к игроку, если он ниже (по умолчанию да), patrol — бродить до агра (по умолчанию да),
    offset_y — летуны целятся чуть выше/ниже центра игрока."""
    sp, acc = speed_of(m, p), p.get("accel", 2000 if not m.flies else 900)
    if not look(m, w, p):
        return (hover if m.flies else patrol if p.get("patrol", True) else lambda *a: None)(m, p, dt, w)
    dx, dy = w.pl.cx - m.cx, w.pl.cy - m.cy
    m.dir = sign(dx) or m.dir
    if m.flies: return steer(m, w.pl.cx, w.pl.cy + p.get("offset_y", -10), sp, acc, dt)
    if abs(dx) < 6: m.vx = approach(m.vx, 0, acc * dt); return
    d = m.dir; go = True
    obstacle = wall_ahead(m, w, d)
    edge = edge_ahead(m, w, d)
    if obstacle or (edge and not (p.get("drop", True) and dy > 40)):
        if not try_ground_jump(m, p, w, d):
            go = False
    m.vx = approach(m.vx, d * sp if go else 0, acc * dt)

@movement("keep_distance")
def keep_distance(m, p, dt, w):
    """Держит дистанцию: подходит, если далеко, отходит, если близко, всегда смотрит на игрока.
    distance — желаемое расстояние, band — допуск ±, height — летуны держатся на столько выше игрока (минус = выше),
    patrol — бродить до агра. Земные не шагают в пропасть и не упираются в стены."""
    sp, acc = speed_of(m, p), p.get("accel", 1500 if not m.flies else 800)
    if not look(m, w, p):
        return (hover if m.flies else patrol if p.get("patrol", True) else lambda *a: None)(m, p, dt, w)
    dist, band = p.get("distance", 220), p.get("band", 50)
    dx = w.pl.cx - m.cx; side = sign(dx) or m.dir; m.dir = side
    if m.flies:
        tx = w.pl.cx - side * dist; tx = max(T + m.w, min(MW - T - m.w, tx))
        return steer(m, tx, w.pl.cy + p.get("height", -70) + math.sin(m.t * 2) * 12, sp, acc, dt)
    want = side if abs(dx) > dist + band else -side if abs(dx) < dist - band else 0
    if want and (wall_ahead(m, w, want) or edge_ahead(m, w, want)):
        if not try_ground_jump(m, p, w, want): want = 0
    m.vx = approach(m.vx, want * sp, acc * dt)

@movement("loop")
def loop(m, p, dt, w):
    """Летает по циклу вокруг точки спавна (или вокруг игрока: anchor = "player"), на игрока не обращает внимания.
    shape: circle | eight (восьмёрка) | line (туда-обратно по горизонтали) | path (свои точки),
    radius [rx, ry] — размеры, period — секунд на круг, reverse — в обратную сторону,
    points [[dx, dy], ...] — для path, смещения от точки спавна; по ним летит со скоростью speed.
    Земные мобы берут из траектории только горизонталь (ходят туда-обратно)."""
    sp, acc = speed_of(m, p), p.get("accel", 900)
    ax, ay = (w.pl.cx, w.pl.cy) if p.get("anchor") == "player" else m.home
    shape = p.get("shape", "circle"); rx, ry = p.get("radius", [90, 50])
    m.loop_t += dt * (-1 if p.get("reverse") else 1)
    if shape == "path":
        pts = p.get("points") or [[-80, 0], [80, 0]]
        px, py = pts[m.wp % len(pts)]; tx, ty = ax + px, ay + py
        if math.hypot(tx - m.cx, ty - m.cy if m.flies else 0) < 8: m.wp += 1
    else:
        th = m.loop_t / p.get("period", 4) * 2 * math.pi
        if shape == "eight": tx, ty = ax + rx * math.sin(th), ay + ry * math.sin(2 * th)
        elif shape == "line": tx, ty = ax + rx * math.sin(th), ay
        else: tx, ty = ax + rx * math.cos(th), ay + ry * math.sin(th)
    if m.flies: steer(m, tx, ty, sp, acc, dt)
    else:
        dx = tx - m.cx; d = sign(dx) if abs(dx) > 4 else 0
        if d and (wall_ahead(m, w, d) or edge_ahead(m, w, d)):
            if not try_ground_jump(m, p, w, d): d = 0
        m.vx = approach(m.vx, d * min(sp, abs(dx) * 4), acc * dt)
    if abs(m.vx) > 5: m.dir = sign(m.vx)

@movement("stand")
def stand(m, p, dt, w):
    """Стоит на месте (летун — висит), поворачивается к игроку."""
    look(m, w, p); m.dir = sign(w.pl.cx - m.cx) or m.dir
    if m.flies: hover(m, p, dt, w)
    else: m.vx = approach(m.vx, 0, 1500 * dt)
