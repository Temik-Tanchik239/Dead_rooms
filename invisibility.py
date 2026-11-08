"""Эффект невидимости — общий для игрока и мобов (в том числе босса).

Состояние лежит в поле e.invis (None — видим) и устроено так:
    {"t": секунд осталось (None — бессрочно), "tr": прозрачность в % (0 — видим, 100 — не виден совсем),
     "brk": сбрасывать ли эффект при атаке, "age": сколько секунд уже действует}

Что делает эффект:
  · Рисунок юнита становится прозрачным (Player.draw / Mob.draw зовут alpha() и ghost()). Прозрачность плавно
    набирается и спадает за "fade" секунд, а в последние "warn" секунд мигает — это предупреждение, что вот-вот кончится.
  · Мобы не замечают невидимого игрока и не агрятся на него (movement.look, босс и его руки в mob.py / boss_hands.py,
    самонаводящиеся пули в projectiles.py); уже агрившиеся — теряют цель. Физические удары и касания работают как раньше:
    зона атаки, которая уже запущена, всё равно заденет игрока, если он в неё попал.
  · Атака из невидимости (удар оружием, а у заклинателей — боевое заклинание, у моба — любая его атака) сбрасывает эффект,
    если у этого эффекта break_on_attack = true (по умолчанию да). Заклинания «Рывок», «Лечение», «Щит» и сама
    «Мантия невидимости» невидимость не снимают; для остальных можно задать в skills.json "breaks_invisibility": true/false.

Как наложить эффект (во всех случаях можно задать время, прозрачность и break_on_attack):
  · навык «Мантия невидимости» (data/skills.json, тип "invisibility", по умолчанию 10 секунд);
  · из кода:                 invisibility.apply(юнит, {"time": 10, "transparency": 80}, fx)
  · как статус-эффект:       status.apply(моб, {"invisible": 10})  — работает в "effect" заклинаний и пуль;
  · моб, невидимый с рождения: в data/mobs.json поле "invisible": true | секунды | {"time": 8, "transparency": 90, ...}.
Поле время: 0 или не задано — эффект бессрочный.

Общие настройки — data/invisibility.json (процент прозрачности для всех, отдельно для игрока и мобов, скорость
проявления, мигание перед концом, break_on_attack по умолчанию). Свой процент можно задать и в самом эффекте
(поле "transparency" в навыке / в "invisible" у моба) — он важнее общего.
"""
import math, time
from core import CFG

DEFAULT_TRANSPARENCY = 70.0   # %, если в data/invisibility.json ничего не задано
DEFAULT_FADE = 0.25           # сек, за сколько юнит становится прозрачным / снова видимым
DEFAULT_WARN = 1.5            # сек до конца эффекта, когда юнит начинает мигать

# Навыки, которые невидимость НЕ снимают (всё остальное — «атака»). Свой выбор — "breaks_invisibility" в skills.json.
NON_ATTACK_SPELLS = {"dash", "heal", "shield", "invisibility"}


def cfg():
    """Общие настройки (data/invisibility.json, CFG[\"invisibility\"]; перечитываются по F5)."""
    c = CFG.get("invisibility")
    return c if isinstance(c, dict) else {}


def _num(v, default, lo=None, hi=None):
    try: v = float(v)
    except (TypeError, ValueError): v = float(default)
    if lo is not None: v = max(lo, v)
    if hi is not None: v = min(hi, v)
    return v


def is_mob(e):
    return hasattr(e, "kind")   # у Mob есть kind (тип из mobs.json), у Player — нет


def default_transparency(e):
    """Прозрачность по умолчанию в %: mob_transparency / player_transparency, а если их нет — общая transparency."""
    c = cfg()
    own = c.get("mob_transparency" if is_mob(e) else "player_transparency")
    return _num(c.get("transparency", DEFAULT_TRANSPARENCY) if own is None else own, DEFAULT_TRANSPARENCY, 0, 100)


def init(e):
    """Поля невидимости на юните (зовётся из Player.__init__ и Mob.__init__)."""
    e.invis = None
    e.invis_vis = 1.0


def is_invisible(e):
    return bool(getattr(e, "invis", None))


def parse(spec):
    """Описание эффекта -> словарь. True — всё по умолчанию, число — секунды, словарь — как есть."""
    if spec is True: return {}
    if isinstance(spec, dict): return dict(spec)
    if isinstance(spec, (int, float)) and not isinstance(spec, bool): return {"time": spec}
    return {}


def apply(e, spec=True, fx=None):
    """Сделать юнита невидимым. spec: True | секунды | {"time"/"duration", "transparency", "break_on_attack"}.
    Повторное наложение продлевает время (берётся большее) и обновляет прозрачность. Возвращает True, если эффект наложен."""
    if e is None or spec is None or spec is False: return False
    sp = parse(spec)
    t = _num(sp.get("time", sp.get("duration")), 0.0, 0.0) or None          # 0 / не задано — бессрочно
    tr = sp.get("transparency")
    tr = default_transparency(e) if tr is None else _num(tr, default_transparency(e), 0, 100)
    brk = sp.get("break_on_attack")
    brk = bool(cfg().get("break_on_attack", True)) if brk is None else bool(brk)
    st = getattr(e, "invis", None)
    if st:
        if st["t"] is not None: st["t"] = None if t is None else max(st["t"], t)
        st["tr"], st["brk"] = tr, brk
        return True
    e.invis = {"t": t, "tr": tr, "brk": brk, "age": 0.0}
    if fx is not None: fx.ring(e.cx, e.cy, 26)
    return True


def clear(e, fx=None, why="attack"):
    """Снять невидимость. why: attack (атаковал) / expire (время вышло) / любое другое. True, если она была."""
    if not getattr(e, "invis", None): return False
    e.invis = None
    e._invis_off = time.monotonic()
    if fx is not None:
        fx.ring(e.cx, e.cy, 22)
        if not is_mob(e):
            fx.text("Невидимость снята" if why == "attack" else "Невидимость закончилась", e.cx, e.y - 18)
    return True


def on_attack(e, fx=None):
    """Юнит атаковал: если у эффекта break_on_attack — невидимость спадает."""
    st = getattr(e, "invis", None)
    if st and st.get("brk"): clear(e, fx, "attack")


def tick(e, dt, fx=None):
    """Каждый кадр (Player.update / status.tick для мобов): время эффекта тает."""
    st = getattr(e, "invis", None)
    if not st: return
    st["age"] += dt
    if st["t"] is not None:
        st["t"] -= dt
        if st["t"] <= 0: clear(e, fx, "expire")


# ---------------------------------------------------------------- кто кого видит

def visible_only(players):
    """Только те игроки, которых мобы могут заметить."""
    return [p for p in players if not is_invisible(p)]


def pick_target(players, m):
    """Ближайший к мобу ВИДИМЫЙ игрок; если видимых нет — просто ближайший (моб его всё равно не заметит: см. movement.look)."""
    pool = visible_only(players) or list(players)
    return min(pool, key=lambda p: (p.cx - m.cx) ** 2 + (p.cy - m.cy) ** 2)


def breaks(a):
    """Снимает ли применение навыка a (словарь из skills.json) невидимость."""
    if "breaks_invisibility" in a: return bool(a["breaks_invisibility"])
    return a.get("type") not in NON_ATTACK_SPELLS


# ---------------------------------------------------------------- отрисовка

def alpha(e):
    """Текущая непрозрачность юнита 0..255 (255 — рисовать как обычно). Плавно догоняет цель за "fade" секунд;
    перед концом эффекта мигает. Зовётся из draw(): время берёт у часов, поэтому работает и у клиента сетевой игры."""
    now = time.monotonic()
    last = getattr(e, "_invis_clock", None); e._invis_clock = now
    st = getattr(e, "invis", None)
    tgt = 1.0 - st["tr"] / 100.0 if st else 1.0
    cur = getattr(e, "invis_vis", 1.0)
    fade = _num(cfg().get("fade", DEFAULT_FADE), DEFAULT_FADE, 0.0, 5.0)
    if last is None or fade <= 0 or now - last > 1.0:
        cur = tgt                                                   # первый кадр / без плавности — сразу
    else:
        step = min(0.1, now - last) / fade
        cur = min(tgt, cur + step) if cur < tgt else max(tgt, cur - step)
    e.invis_vis = cur
    vis = cur
    warn = _num(cfg().get("warn", DEFAULT_WARN), DEFAULT_WARN, 0.0, 10.0)
    if st and st["t"] is not None and warn > 0 and st["t"] < warn:
        vis += (1.0 - vis) * (0.5 + 0.5 * math.sin(now * 14.0))    # мигание: скоро проявится
    return max(0, min(255, int(round(vis * 255))))


def ghost(v, rect, draw, a):
    """Нарисовать draw() на поверхности v прозрачным (a — 0..255). Рисование идёт как обычно, но результат внутри rect
    подмешивается к тому, что было под юнитом. Всё, что draw рисует за пределами rect, остаётся непрозрачным."""
    if a >= 255:
        draw(); return
    r = rect.clip(v.get_rect())
    if r.w <= 0 or r.h <= 0:
        draw(); return
    under = v.subsurface(r).copy()
    draw()
    if a <= 0:
        v.blit(under, r.topleft); return
    over = v.subsurface(r).copy()
    over.set_alpha(a)
    v.blit(under, r.topleft)
    v.blit(over, r.topleft)


# ---------------------------------------------------------------- сеть (multiplayer.py)

def net_pack(e):
    """Состояние для снимка мира: None или [секунд осталось (-1 — бессрочно), прозрачность %, break_on_attack]."""
    st = getattr(e, "invis", None)
    if not st: return None
    return [-1 if st["t"] is None else round(st["t"], 2), round(st["tr"], 1), 1 if st["brk"] else 0]


def net_apply(e, iv, mine=False):
    """Принять состояние от хоста. mine — это свой, предсказываемый локально герой: он мог только что сам наложить
    или снять эффект, а хост об этом ещё не знает, поэтому свежее локальное состояние короткое время не перезаписываем."""
    st = getattr(e, "invis", None)
    if not iv:
        if mine and st and st["age"] < 0.6: return
        e.invis = None; return
    if mine and not st and time.monotonic() - getattr(e, "_invis_off", -9.0) < 0.6: return
    t, tr, brk = iv[0], iv[1], iv[2]
    e.invis = {"t": None if t < 0 else float(t), "tr": float(tr), "brk": bool(brk), "age": st["age"] if st else 0.0}
