"""Заклинания игрока (активные навыки категории "active" из data/skills.json).

Эффект заклинания = функция с декоратором @spell("тип"); "тип" — поле "type" навыка в
data/skills.json. Общая обвязка (проверка маны и кулдауна, анимация применения, списание
маны) живёт в cast(); сам эффект — в зарегистрированной функции fn(pl, a, mobs, projs, fx),
где pl — игрок, a — словарь навыка из JSON. Новое заклинание = запись в skills.json
(+ при необходимости новый @spell(...)). Так же устроены movement.py / attacks.py /
projectiles.py / boss_hands.py.

Окно мага (hud.py) показывает три активных заклинания — предыдущее, текущее и следующее;
порядок — список pl.skills (только "active"), текущее — pl.skill_index. Переключение C/V."""
import math
import pygame as pg
from core import CFG, sign
from projectiles import volley
import status
from anim import frames, ASSETS_EXISTS

SPELLS = {}

# Поля навыка, которые переопределяют вид снаряда заклинания (имя в skills.json -> поле пули в projectiles.json).
# Пример: "projectile": "fire_bolt", "projectile_skin": "projectiles/my_fire.png", "projectile_draw": [40, 24]
PROJECTILE_FIELDS = {
    "projectile_skin": "skin", "projectile_frames": "frames", "projectile_fps": "fps",
    "projectile_draw": "draw", "projectile_rotate": "rotate", "projectile_size": "size",
    "projectile_color": "color", "projectile_speed": "speed",
}


def icon_path(sid, a=None):
    """Путь к иконке заклинания (относительно assets/). Порядок поиска:
    1) поле \"icon\" навыка, если файл существует; 2) icons/skill_<id>.png; 3) icons/<id>.png.
    Ничего не нашлось -> None (HUD нарисует кружок цвета заклинания)."""
    a = a if a is not None else CFG.get("skills", {}).get(sid, {})
    cands = [a.get("icon"), f"icons/skill_{sid}.png", f"icons/{sid}.png"]
    for c in cands:
        if c and ASSETS_EXISTS(c):
            return c
    return None


def cast_frames(sid, a=None):
    """Кадры анимации применения навыка (overlay поверх игрока во время каста). Порядок поиска:
    1) поле \"cast_anim\" навыка (папка с кадрами 1.png, 2.png… либо один PNG / шаблон *.png);
    2) папка assets/skills/<id>/cast/; 3) файл assets/skills/<id>/cast.png.
    Ничего не нашлось -> [] (рисуется запасная процедурная вспышка цвета навыка)."""
    a = a if a is not None else CFG.get("skills", {}).get(sid, {})
    for cand in (a.get("cast_anim"), f"skills/{sid}/cast", f"skills/{sid}/cast.png"):
        if cand:
            fr = frames(cand)
            if fr:
                return fr
    return []


def projectile_spec(a):
    """Описание снаряда заклинания: тип из \"projectile\" + правки из полей projectile_* навыка.
    Если правок нет, но лежит assets/projectiles/<id заклинания>.png (или папка с кадрами
    assets/projectiles/<id заклинания>/) — берётся он. Результат понимает projectiles.resolve()."""
    base = a.get("projectile", "bolt")
    over = {dst: a[src] for src, dst in PROJECTILE_FIELDS.items() if src in a}
    sid = a.get("_sid")
    if sid and not ({"skin", "frames", "sprite"} & set(over)):
        if frames(f"projectiles/{sid}"):
            fr = frames(f"projectiles/{sid}")
            if len(fr) > 1 or not ASSETS_EXISTS(f"projectiles/{sid}.png"):
                over["frames"] = f"projectiles/{sid}"
            else:
                over["skin"] = f"projectiles/{sid}.png"
        elif ASSETS_EXISTS(f"projectiles/{sid}.png"):
            over["skin"] = f"projectiles/{sid}.png"
    if not over:
        return base
    if isinstance(base, dict):
        d = dict(base); d.update(over); return d
    d = {"type": base}; d.update(over); return d


def spell(kind):
    """Регистрирует обработчик заклинания типа kind."""
    def reg(fn):
        SPELLS[kind] = fn
        return fn
    return reg


def active_skills(pl):
    """Список id активных навыков игрока в порядке получения (это и есть «книга заклинаний»)."""
    defs = CFG.get("skills", {})
    return [sid for sid in getattr(pl, "skills", []) if defs.get(sid, {}).get("category", "active") == "active"]


def spellbook(pl):
    """(prev, current, next) — id заклинаний для окна мага. Любое может быть None/повтором, если их < 3."""
    act = active_skills(pl)
    if not act:
        return (None, None, None)
    n = len(act)
    i = pl.skill_index % n
    return (act[(i - 1) % n], act[i], act[(i + 1) % n])


def ready(pl):
    """Готово ли текущее заклинание (нет кулдауна и хватает маны). Для авто-каста мага по зажатой ЛКМ."""
    act = active_skills(pl)
    if not act:
        return False
    sid = act[pl.skill_index % len(act)]
    a = CFG.get("skills", {}).get(sid, {})
    if pl.skill_cooldowns.get(sid, 0) > 0:
        return False
    return pl.mana >= max(0.0, float(a.get("mana_cost", 20.0)))


def aim_point(pl, default_dist=60):
    """Точка прицеливания в мире: курсор или точка перед игроком по направлению взгляда."""
    if pl.aim:
        return pl.aim
    return (pl.cx + pl.face * default_dist, pl.cy)


def cast(pl, mobs, projs, fx):
    """Применить текущее активное заклинание (Q, а у мага ещё и ЛКМ). Тонкий диспетчер поверх @spell."""
    defs = CFG.get("skills", {})
    act = active_skills(pl)
    if not act:
        return
    sid = act[pl.skill_index % len(act)]
    a = defs.get(sid)
    if not a:
        return
    if pl.skill_cooldowns.get(sid, 0) > 0:
        fx.text(f"{a.get('name', sid)}: {pl.skill_cooldowns[sid]:.1f}с", pl.cx, pl.y - 18)
        return
    cost = max(0.0, float(a.get("mana_cost", 20.0)))
    if pl.mana < cost:
        pl.mana_flash = .35
        fx.text("Недостаточно маны", pl.cx, pl.y - 18)
        return
    kind = a.get("type", "nova")
    fn = SPELLS.get(kind)
    if fn is None:
        fx.text(f"неизвестное заклинание: {kind}", pl.cx, pl.y - 18)
        return
    pl.skill_cast = (sid, 0.0, float(a.get("cast_animation", 0.55)))
    fn(pl, dict(a, _sid=sid), mobs, projs, fx)
    pl.mana -= cost
    pl.mana_t = CFG["player"].get("mana", {}).get("regen_delay", .9)
    pl.skill_cooldowns[sid] = max(0.0, float(a.get("cooldown", 5.0)))
    fx.text(f"{a.get('name', sid)} (-{cost:g} маны)", pl.cx, pl.y - 18)


def _near(m, x, y, radius):
    """Задевает ли моба круг (x, y, radius) — с учётом составных хитбоксов босса."""
    if hasattr(m, "collides_circle"):
        return m.collides_circle(x, y, radius)
    return (m.cx - x) ** 2 + (m.cy - y) ** 2 <= radius * radius


# ---------------- базовые навыки (общие для всех героев) ----------------

@spell("dash")
def _dash(pl, a, mobs, projs, fx):
    pl.vx = pl.face * a.get("speed", 620)
    pl.inv = max(pl.inv, a.get("invulnerability", .18))
    fx.ring(pl.cx + pl.face * 20, pl.cy, a.get("radius", 24))


@spell("nova")
def _nova(pl, a, mobs, projs, fx):
    """Круговой взрыв вокруг игрока. Поле "effect" (например {"freeze": 1.6}) накладывает статус."""
    radius, damage = a.get("radius", 100), a.get("damage", 25)
    eff = a.get("effect")
    fx.ring(pl.cx, pl.cy, radius)
    fx.shake = max(fx.shake, .12)
    for m in mobs:
        if _near(m, pl.cx, pl.cy, radius):
            m.hurt(damage * pl.dmg_mult(), pl.face * a.get("knockback", 220), fx)
            if eff:
                status.apply(m, eff, fx)


@spell("heal")
def _heal(pl, a, mobs, projs, fx):
    pl.hp = min(pl.maxhp, pl.hp + a.get("amount", 30))
    fx.ring(pl.cx, pl.cy, a.get("radius", 42))


@spell("shield")
def _shield(pl, a, mobs, projs, fx):
    pl.shield_time = max(0.1, float(a.get("duration", 4.0)))
    pl.shield_hp = max(1.0, float(a.get("capacity", 60)))
    pl.shield_face = pl.face
    fx.ring(pl.cx + pl.shield_face * 26, pl.cy, a.get("radius", 42))


# ---------------- заклинания мага ----------------

@spell("projectile")
def _projectile(pl, a, mobs, projs, fx):
    """Выстрел снарядом в курсор. "projectile" — тип/описание пули; эффект пули (поле "effect"
    у типа в data/projectiles.json, напр. заморозка) применяется при попадании внутри projectiles.py."""
    pr = projectile_spec(a)
    hx, hy = pl.hand("shoot")
    ang = 0 if pl.face > 0 else math.pi
    if pl.aim:
        ang = math.atan2(pl.aim[1] - hy, pl.aim[0] - hx)
    volley(projs, pr, hx + math.cos(ang) * 14, hy + math.sin(ang) * 14, ang,
           a.get("damage", 20) * pl.dmg_mult(), True, a.get("count", 1), a.get("spread", 0))


@spell("chain_lightning")
def _chain_lightning(pl, a, mobs, projs, fx):
    """Молния бьёт по ближайшему к курсору врагу и перескакивает на ближайших соседей
    (в радиусе "chain_range"), "chains" прыжков, урон слабеет на каждом ("falloff")."""
    dmg = a.get("damage", 22) * pl.dmg_mult()
    reach = a.get("range", 340)
    chain_range = a.get("chain_range", 150)
    chains = int(a.get("chains", 3))
    falloff = float(a.get("falloff", 0.8))
    color = list(a.get("color", [150, 200, 255]))
    kb = a.get("knockback", 120)
    hx, hy = pl.hand("shoot")
    ox, oy = aim_point(pl, 50)
    pool = [m for m in mobs if m.hp > 0]
    target, best = None, reach
    for m in pool:
        if math.hypot(m.cx - hx, m.cy - hy) > reach:
            continue
        d_aim = math.hypot(m.cx - ox, m.cy - oy)
        if d_aim < best:
            best, target = d_aim, m
    if target is None:
        fx.beam(hx, hy, ox, oy, color)   # промах — просто разряд в сторону курсора
        return
    fx.shake = max(fx.shake, .1)
    hit = set()
    px, py = hx, hy
    cur, amount = target, dmg
    for _ in range(chains + 1):
        if cur is None:
            break
        fx.beam(px, py, cur.cx, cur.cy, color)
        cur.hurt(amount, (sign(cur.cx - px) or 1) * kb, fx)
        hit.add(id(cur))
        px, py = cur.cx, cur.cy
        amount *= falloff
        nxt, bd = None, chain_range
        for m in pool:
            if id(m) in hit or m.hp <= 0:
                continue
            dd = math.hypot(m.cx - px, m.cy - py)
            if dd < bd:
                bd, nxt = dd, m
        cur = nxt


@spell("strike_area")
def _strike_area(pl, a, mobs, projs, fx):
    """Удар сверху в выбранную область (курсор): урон по радиусу + статус. Для «мощной молнии»
    задайте "stun": 2.0, для метеора — "effect": {"burn": {...}}."""
    ox, oy = aim_point(pl, 80)
    radius = a.get("radius", 80)
    dmg = a.get("damage", 45) * pl.dmg_mult()
    color = list(a.get("color", [200, 180, 255]))
    kb = a.get("knockback", 180)
    eff = dict(a.get("effect", {}))
    if a.get("stun"):
        eff.setdefault("stun", a["stun"])
    fx.bolt(ox, oy, color)
    fx.flash(ox, oy, radius, color)
    fx.ring(ox, oy, radius)
    fx.shake = max(fx.shake, .3)
    for m in mobs:
        if _near(m, ox, oy, radius):
            m.hurt(dmg, (sign(m.cx - ox) or 1) * kb, fx)
            if eff:
                status.apply(m, eff, fx)


# ---------------- телекинез (инженер) ----------------

def _shove(m, vx, vy=-200.0, stun=0.3):
    """Толкнуть/притянуть моба без урона (не ломает броню, но прерывает его атаку)."""
    m.vx = vx
    m.vy = min(getattr(m, "vy", 0.0), vy) if not getattr(m, "flies", False) else vy
    m.stun = max(getattr(m, "stun", 0.0), stun)
    m.act = None
    m.grav = None
    m.aggro = True


@spell("telekinesis")
def _telekinesis(pl, a, mobs, projs, fx):
    """Поле телекинеза по области вокруг точки прицеливания: что дальше \"grip\" от игрока —
    притягивается к нему, что ближе — отталкивается. Действует и на врагов, и на предметы (оружие на полу)."""
    ox, oy = aim_point(pl, 60)
    reach = a.get("range", 280)
    radius = a.get("radius", 72)
    force = a.get("force", 460)
    grip = a.get("grip", 96)
    dmg = a.get("damage", 0) * pl.dmg_mult()
    color = list(a.get("color", [150, 110, 255]))
    fx.beam(pl.cx, pl.cy, ox, oy, color)
    fx.ring(ox, oy, radius)
    for m in mobs:
        if m.hp <= 0 or math.hypot(m.cx - pl.cx, m.cy - pl.cy) > reach or not _near(m, ox, oy, radius):
            continue
        pull = math.hypot(m.cx - pl.cx, m.cy - pl.cy) > grip
        dirx = (sign(m.cx - pl.cx) or pl.face) * (-1 if pull else 1)   # притянуть -> к игроку, оттолкнуть -> от игрока
        if dmg and not pull:
            m.hurt(dmg, dirx * force, fx)
        else:
            _shove(m, dirx * force, -force * (0.2 if pull else 0.35))
    for dr in getattr(pl, "drops", []):
        if math.hypot(dr.x - ox, dr.y - oy) > radius or math.hypot(dr.x - pl.cx, dr.y - pl.cy) > reach:
            continue
        if math.hypot(dr.x - pl.cx, dr.y - pl.cy) > grip:
            dr.x += (pl.cx - dr.x) * 0.6; dr.y += (pl.cy - dr.y) * 0.6     # притянуть предмет к игроку
        else:
            dr.x += (sign(dr.x - pl.cx) or pl.face) * 56                    # оттолкнуть предмет


@spell("telekinesis_cone")
def _telekinesis_cone(pl, a, mobs, projs, fx):
    """Телекинетическая волна: отталкивает всех врагов в конусе перед игроком (по направлению взгляда/курсора)."""
    reach = a.get("range", 230)
    half = math.radians(a.get("angle", 55))
    kb = a.get("knockback", 540)
    dmg = a.get("damage", 0) * pl.dmg_mult()
    color = list(a.get("color", [120, 170, 255]))
    ox, oy = aim_point(pl, 60)
    base = math.atan2(oy - pl.cy, ox - pl.cx)
    fx.ring(pl.cx, pl.cy, 30)
    fx.flash(pl.cx + math.cos(base) * reach * 0.45, pl.cy + math.sin(base) * reach * 0.45, reach * 0.5, color)
    fx.shake = max(fx.shake, .2)
    for m in mobs:
        dx, dy = m.cx - pl.cx, m.cy - pl.cy
        dist = math.hypot(dx, dy)
        if m.hp <= 0 or dist > reach or dist < 1:
            continue
        if abs((math.atan2(dy, dx) - base + math.pi) % math.tau - math.pi) > half:
            continue
        push = (sign(dx) or pl.face) * kb
        if dmg:
            m.hurt(dmg, push, fx)
        else:
            _shove(m, push, -kb * 0.4)


@spell("telekinesis_hold")
def _telekinesis_hold(pl, a, mobs, projs, fx):
    """Телекинетический захват: останавливает ближайшего к курсору врага и держит его в стане \"duration\" секунд."""
    reach = a.get("range", 340)
    dur = float(a.get("duration", 2.5))
    color = list(a.get("color", [200, 120, 255]))
    ox, oy = aim_point(pl, 50)
    target, best = None, reach
    for m in mobs:
        if m.hp <= 0 or math.hypot(m.cx - pl.cx, m.cy - pl.cy) > reach:
            continue
        d_aim = math.hypot(m.cx - ox, m.cy - oy)
        if d_aim < best:
            best, target = d_aim, m
    if target is None:
        fx.text("нет цели для захвата", pl.cx, pl.y - 18)
        return
    fx.beam(pl.cx, pl.cy, target.cx, target.cy, color)
    fx.ring(target.cx, target.cy, 38)
    target.vx = 0.0
    if getattr(target, "flies", False):
        target.vy = 0.0
    status.apply(target, {"stun": dur}, fx)   # боссы (cc_immune) не поддаются — см. status.py
