"""Система частиц-эффектов: внешний вид, привязка к событиям и движение — всё в data/*.json.

ЭФФЕКТЫ (как выглядит) — data/effects.json, словарь id -> описание частицы:
  colors  — список цветов [r,g,b]; каждая частица берёт случайный;
  size    — [мин, макс] радиус, px;  life — [мин, макс] время жизни, с;
  speed   — [мин, макс] начальная скорость, px/с;
  gravity — ускорение вниз, px/с² (отрицательное — вверх); drag — торможение 0..1 в секунду;
  glow    — мягкий ореол вокруг частицы.

ПРИВЯЗКИ (к чему цепляется) — data/attachments.json, список записей:
  {"hook": "weapon_hit", "id": "rusty_sword", "effect": "spark", "count": 12, "motion": "spray"}
  hook   — событие (см. HOOKS); id — к какому именно оружию/навыку/мобу/ящику/пуле ("*" — ко всем);
  count  — сила эффекта: сколько частиц появляется за событие;
  motion — тип движения (см. MOTIONS); можно уточнить: "angle" (конус spray, °, 60), "spin" (вихрь, рад/с, 4).

HOOKS: weapon_hit / weapon_swing (id оружия), skill_cast (id навыка), walk (id моба или * — герой),
jump / land / player_hurt (герой), mob_hit / mob_attack / mob_death (id моба),
container_break / container_open (id типа ящика), projectile_hit (id типа пули).

MOTIONS: burst — разлёт во все стороны; spray — конус по направлению удара; puff — пыль, вверх и тормозит;
rise — плавно вверх (дым/огонь); fall — падение вниз; twinkle — мерцает на месте; spiral — вихрь.

Редактор — в редакторе игры (launch_map_editor.bat): вкладка «Эффекты» — все привязки, а на вкладках
«Навыки»/«Мобы»/«Ящики» — панели «Частицы» для выбранного навыка/моба/типа ящика. Правки пишутся в
data/attachments.json сразу; в игре перечитываются по F5. Внешний вид частиц — data/effects.json.
Частицы хранятся на fx.parts (JSON-дружелюбные списки — сериализуются в мультиплеере).
"""
import math
import random
import pygame as pg
from core import CFG

HOOKS = (
    ("weapon_hit", "Попадание оружием", "id оружия из data/weapons.json или *"),
    ("weapon_swing", "Удар оружием", "id оружия или *"),
    ("skill_cast", "Использование навыка", "id навыка из data/skills.json или *"),
    ("walk", "Шаги", "* — герой, иначе id моба"),
    ("jump", "Прыжок", "* — герой"),
    ("land", "Приземление", "* — герой"),
    ("player_hurt", "Герой получил урон", "* — герой"),
    ("mob_hit", "Моб получил урон", "id моба из data/mobs.json или *"),
    ("mob_attack", "Моб начал атаку", "id моба или *"),
    ("mob_death", "Моб умер", "id моба или *"),
    ("container_break", "Ящик сломан", "id типа из data/containers.json или *"),
    ("container_open", "Ящик открыт", "id типа ящика или *"),
    ("projectile_hit", "Пуля исчезла (попала)", "id типа из data/projectiles.json или *"),
)
MOTIONS = (
    ("burst", "Разлёт во все стороны"),
    ("spray", "Конус по направлению"),
    ("puff", "Пыль вверх"),
    ("rise", "Плавно вверх (дым/огонь)"),
    ("fall", "Падение вниз"),
    ("twinkle", "Мерцает на месте"),
    ("spiral", "Вихрь"),
)
# запись частицы: x, y, vx, vy, age, life, size, [r,g,b], gravity, drag, motion, spin, seed, glow
MAX = 900   # максимум частиц на один fx (старые вытесняются)


def _pair(v):
    if isinstance(v, (int, float)): return float(v), float(v)
    if isinstance(v, (list, tuple)) and len(v) == 2: return float(v[0]), float(v[1])
    return 20.0, 140.0


def emit(fx, hook, x, y, dir=1, target_id=None):
    """Пускает частицы всех привязок, у которых hook совпал, а id — совпал с target_id (или "*" / пусто)."""
    parts = getattr(fx, "parts", None)
    if parts is None: return
    for b in CFG.get("attachments", []):
        if not isinstance(b, dict) or b.get("hook") != hook: continue
        tid = str(b.get("id", "*") or "*")
        if tid not in ("", "*") and tid != str(target_id): continue
        spec = CFG.get("effects", {}).get(b.get("effect"))
        if not isinstance(spec, dict): continue
        try: count = max(0, int(b.get("count", 8)))
        except (TypeError, ValueError): count = 8
        spawn(fx, spec, x, y, b.get("motion", "burst"), count, dir, b)


def spawn(fx, spec, x, y, motion, count, dir=1, bind=None):
    """Создать count частиц эффекта spec в точке (x, y) движением motion (dir: 1 вправо, -1 влево)."""
    parts = getattr(fx, "parts", None)
    if parts is None or count <= 0: return
    bind = bind or {}
    colors = spec.get("colors") or [[255, 255, 255]]
    smin, smax = _pair(spec.get("speed", [20, 140]))
    lmin, lmax = _pair(spec.get("life", [0.4, 0.9]))
    rmin, rmax = _pair(spec.get("size", [2, 4]))
    grav = float(spec.get("gravity", 0)); drag = max(0.0, min(0.95, float(spec.get("drag", 0))))
    ang = math.radians(float(bind.get("angle", 60))); spin = float(bind.get("spin", 4.0))
    if motion == "fall" and not spec.get("gravity"): grav = max(grav, 600.0)
    glow = bool(spec.get("glow"))
    for _ in range(count):
        a, sp = random.uniform(0, 2 * math.pi), random.uniform(smin, smax)
        if motion == "spray":
            base = 0.0 if dir >= 0 else math.pi
            a = base + random.uniform(-ang / 2, ang / 2)
        elif motion in ("puff", "rise"): a = -math.pi / 2 + random.uniform(-0.7, 0.7)   # вверх
        elif motion == "fall": a = math.pi / 2 + random.uniform(-0.5, 0.5)              # вниз
        elif motion == "twinkle": sp = 0.0
        parts.append([x + random.uniform(-4, 4), y + random.uniform(-4, 4), math.cos(a) * sp, math.sin(a) * sp,
                      0.0, random.uniform(lmin, lmax), random.uniform(rmin, rmax), list(random.choice(colors)),
                      grav, drag, motion, spin, random.uniform(0, 6.283), glow])
    del parts[:-MAX]


def walk_step(unit, fx, dt, interval=0.3):
    """Пыль от шагов юнита (hook "walk"): пока идёт по земле — раз в interval секунд. Юнит — герой или моб
    (у моба target_id — его вид из data/mobs.json, у героя — "*")."""
    if dt <= 0: return
    if unit.ground and abs(unit.vx) > 30:
        unit.step_t = getattr(unit, "step_t", 0.0) - dt
        if unit.step_t <= 0:
            unit.step_t = interval
            emit(fx, "walk", unit.cx, unit.y + unit.h, dir=getattr(unit, "face", None) or getattr(unit, "dir", 1) or 1,
                 target_id=getattr(unit, "kind", "*"))
    else: unit.step_t = 0.0


def update(parts, dt):
    """Тик частиц: гравитация, торможение, поведение движения."""
    if dt <= 0: return
    for p in parts:
        p[4] += dt
        m = p[10]
        if m == "twinkle": continue                     # стоит на месте, мерцает при отрисовке
        if p[8]: p[3] += p[8] * dt                      # гравитация
        if p[9]: f = max(0.0, 1.0 - p[9] * dt); p[2] *= f; p[3] *= f   # торможение
        if m == "spiral":                               # вихрь: скорость поворачивается
            c, s_ = math.cos(p[11] * dt), math.sin(p[11] * dt)
            p[2], p[3] = p[2] * c - p[3] * s_, p[2] * s_ + p[3] * c
        if m == "rise": p[0] += math.sin(p[4] * 5 + p[12]) * 14 * dt   # дым покачивается
        p[0] += p[2] * dt; p[1] += p[3] * dt
    parts[:] = [p for p in parts if p[4] < p[5]]


def draw(parts, v):
    """Рисует частицы в мировых координатах (на логическом экране, до камеры и освещения)."""
    for p in parts:
        k = max(0.0, 1.0 - p[4] / p[5])                 # остаток жизни 1..0
        col = p[7]; a = k
        if p[10] == "twinkle": a *= 0.45 + 0.55 * (0.5 + 0.5 * math.sin(p[4] * 14 + p[12]))
        c = (int(col[0] * a), int(col[1] * a), int(col[2] * a))
        r = max(1, int(p[6] * (0.35 + 0.65 * k)))
        if p[13]: pg.draw.circle(v, (int(col[0] * a * .3), int(col[1] * a * .3), int(col[2] * a * .3)), (int(p[0]), int(p[1])), int(r * 2.6))
        pg.draw.circle(v, c, (int(p[0]), int(p[1])), r)
