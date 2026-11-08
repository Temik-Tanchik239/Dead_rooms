"""Заклинания игрока (активные навыки категории "active" из data/skills.json).

Эффект заклинания = функция с декоратором @spell("тип"); "тип" — поле "type" навыка в
data/skills.json. Общая обвязка (проверка маны и кулдауна, анимация применения, списание
маны) живёт в cast(); сам эффект — в зарегистрированной функции fn(pl, a, mobs, projs, fx),
где pl — игрок, a — словарь навыка из JSON. Новое заклинание = запись в skills.json
(+ при необходимости новый @spell(...)). Так же устроены movement.py / attacks.py /
projectiles.py / boss_hands.py.

Удерживаемые заклинания (в skills.json "channel": true, напр. телекинетический захват инженера) работают
как ульта Bane в Dota 2: нажатие запускает каст, герой стоит на месте и колдует, пока зажата клавиша навыка,
но не дольше "duration" секунд. Каст прерывается (и навык уходит в перезарядку), если герой двинулся,
пригнулся (S/↓), прыгнул, перекатился, атаковал, получил урон или отпустил клавишу. Состояние хранится в
pl.channel, а на иконке навыка (hud.py) рисуется убывающий индикатор. Свои удерживаемые заклинания —
@spell(...) + channel("тип", tick=..., end=...) (см. ниже).

Заклинания-«потоки» (в skills.json \"hold\": true) — третий режим: клавишу навыка можно держать в любой момент (на бегу,
в прыжке, в бою) — у навыка есть запас в секундах (\"duration\"), пока клавиша зажата, он тратится, а мана уходит по
\"mana_cost\" в секунду. Отпустил — запас сразу начинает восстанавливаться с того места, где остановился (полное
восстановление с нуля за \"recharge\" секунд, по умолчанию = \"cooldown\"). Пока в запасе что-то есть, навык можно снова
использовать. Состояние — pl.hold (активный поток) и pl.hold_pool (запас по навыкам); см. раздел «потоки» ниже.

Окно мага (hud.py) показывает три активных заклинания — предыдущее, текущее и следующее;
порядок — список pl.skills (только "active"), текущее — pl.skill_index. Переключение C/V."""
import math
import pygame as pg
from core import CFG, sign
from projectiles import volley
import status
import invisibility
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


CHANNELS = {}   # тип заклинания -> (tick, end): хуки удерживаемых заклинаний (см. channel())


def channel(kind, tick=None, end=None):
    """Хуки удерживаемого заклинания типа kind (дополнение к @spell(kind), в skills.json нужен "channel": true).
    @spell-функция запускает каст: возвращает False (не вышло — ни маны, ни перезарядки не тратится) или
    словарь/None — стартовое состояние канала (оно лежит в pl.channel вместе с sid/t/max).
    tick(pl, ch, a, dt, mobs, projs, fx) вызывается каждый кадр, пока герой колдует; вернёт False — каст завершится
    (цель погибла и т.п.). end(pl, ch, a, fx) — один раз при любом завершении (отпустил/двинулся/урон/время)."""
    CHANNELS[kind] = (tick, end)


def channeling(pl, sid=None):
    """Колдует ли сейчас игрок удерживаемое заклинание (и именно sid, если указан)."""
    ch = getattr(pl, "channel", None)
    return bool(ch) and (sid is None or ch.get("sid") == sid)


def _channel_blocker(pl):
    """Почему удерживаемое заклинание сейчас не начать (текст для игрока) или None, если можно."""
    if getattr(pl, "grab", None) or pl.state != "move" or pl.stun > 0:
        return "Нужно стоять на месте"
    if pl.airborne():
        return "Нужно стоять на земле"
    if getattr(pl, "move_input", False):
        return "Остановитесь, чтобы колдовать"
    return None


def begin_channel(pl, sid, a, state=None):
    """Начать удержание: герой замирает, очередь прыжка/переката/атак сбрасывается, чтобы не прервать каст сразу."""
    pl.vx = 0.0
    for b in ("jump", "roll", "a1", "a2"):
        pl.buf[b] = 0
    pl.channel = dict(state or {}, sid=sid, t=0.0, max=max(0.1, float(a.get("duration", 2.5))))


def _channel_break(pl, d, dn):
    """Причина прерывания удерживаемого заклинания или None. d — направление бега (-1/0/1), dn — зажато «вниз»."""
    if not getattr(pl, "skill_held", False):
        return "release"                                   # отпустил клавишу навыка
    if d or dn:
        return "move"                                      # пошёл или пригнулся
    if pl.state != "move" or getattr(pl, "grab", None) or pl.airborne():
        return "move"                                      # перекат, лестница, атака, падение, захват
    spellcaster = CFG.get("character", {}).get("spellcaster")   # у мага ЛКМ — это и есть клавиша каста
    buttons = ("jump", "roll") if spellcaster else ("jump", "roll", "a1", "a2")
    if any(pl.buf.get(b, 0) > 0 for b in buttons):
        return "move"                                      # прыжок, перекат или удар
    return None


def channel_update(pl, dt, d, dn, mobs, projs, fx):
    """Каждый кадр удерживаемого каста (зовётся из Player.update): проверка прерываний, лимит времени, tick заклинания."""
    ch = pl.channel
    sid = ch["sid"]; a = CFG.get("skills", {}).get(sid, {})
    ch["t"] += dt
    loop = max(0.1, float(a.get("cast_animation", 0.55)))
    if ch.get("view"):
        # Клиент в сетевой игре: состояние каста прислал хост (он же прерывает), здесь только крутим анимацию и таймер.
        pl.skill_cast = (sid, ch["t"] % loop, loop)
        return
    why = _channel_break(pl, d, dn)
    if why is None and ch["t"] >= ch["max"]:
        why = "time"
    if why is None:
        tick = CHANNELS.get(a.get("type"), (None, None))[0]
        if tick and tick(pl, ch, a, dt, mobs, projs, fx) is False:
            why = "target"
    if why:
        channel_stop(pl, fx, why)
        return
    pl.vx = 0.0                                            # герой стоит на месте (без проскальзывания)
    pl.skill_cast = (sid, ch["t"] % loop, loop)            # анимация каста крутится по кругу, пока колдуем


def channel_stop(pl, fx=None, why="release"):
    """Завершить удерживаемый каст: вызвать end-хук и отправить навык в перезарядку.
    why: release (отпустил) / time (вышло время) / target (цель пропала) / move (двинулся, пригнулся, прыгнул...) / damage / grab."""
    ch = getattr(pl, "channel", None)
    if not ch:
        return
    pl.channel = None
    pl.skill_cast = None
    if ch.get("view"):
        return
    sid = ch["sid"]; a = CFG.get("skills", {}).get(sid, {})
    end = CHANNELS.get(a.get("type"), (None, None))[1]
    if end:
        end(pl, ch, a, fx)
    pl.skill_cooldowns[sid] = max(0.0, float(a.get("cooldown", 5.0)))
    if fx is not None and why in ("move", "damage", "grab"):
        fx.text(f"{a.get('name', sid)}: прервано", pl.cx, pl.y - 18)


# ---------------- заклинания-«потоки» (skills.json: "hold": true) ----------------
#
# Третий режим навыка (первые два: разовый и удерживаемый «стоя» — "channel"). Отличия от "channel":
#   * можно держать на бегу, в прыжке, при атаке и под ударами — ничто, кроме отпущенной клавиши, не прерывает;
#   * у навыка есть ЗАПАС: "duration" секунд, он тратится, пока клавиша зажата, и восстанавливается, когда отпущена —
#     с того значения, на котором остановились (а не с нуля, как кулдаун);
#   * "mana_cost" — мана В СЕКУНДУ, а не за применение;
#   * пока в запасе что-то есть (и хватает маны), навык можно использовать снова в любой момент.
# Поля навыка: hold, duration (запас, сек), mana_cost (мана/сек), recharge (сек полного восстановления с нуля, по умолчанию
# равно cooldown), recharge_delay (пауза перед восстановлением после отпускания, по умолчанию 0), interval (период
# повторения эффекта, сек, по умолчанию 0.35 — для типов без собственных хуков channel(...)).
# Эффект: у типа есть хуки channel(тип, tick=..., end=...) (напр. телекинетический захват) — используются они;
# иначе @spell-функция вызывается заново каждые "interval" секунд (потоки снарядов/молний/ударов по области).

HOLD_MIN_START = 0.1   # столько секунд запаса и маны списывается при старте (чтобы частые тычки не были бесплатными)
HOLD_PULSE = 0.35      # период повторения эффекта по умолчанию


def is_hold(a):
    """Навык-«поток» (skills.json: \"hold\": true). Если заданы и channel, и hold — работает как channel."""
    return bool(a) and bool(a.get("hold")) and not a.get("channel")


def hold_max(a):
    """Полный запас навыка в секундах."""
    return max(0.1, float(a.get("duration", 3.0)))


def hold_cost(a):
    """Расход маны в секунду, пока навык зажат."""
    return max(0.0, float(a.get("mana_cost", 10.0)))


def hold_rate(a):
    """Сколько секунд запаса возвращается за секунду отдыха (полный запас за \"recharge\" секунд)."""
    return hold_max(a) / max(0.1, float(a.get("recharge", a.get("cooldown", 5.0))))


def hold_left(pl, sid, a=None):
    """Сколько секунд запаса осталось у навыка-потока sid."""
    a = a if a is not None else CFG.get("skills", {}).get(sid, {})
    mx = hold_max(a)
    return max(0.0, min(mx, getattr(pl, "hold_pool", {}).get(sid, mx)))


def holding(pl, sid=None):
    """Зажат ли сейчас поток (и именно sid, если указан)."""
    h = getattr(pl, "hold", None)
    return bool(h) and (sid is None or h.get("sid") == sid)


def hold_blocker(pl, sid, a):
    """Почему поток сейчас не начать: None — можно; иначе (текст для игрока или None, «не хватает маны»)."""
    if pl.hp <= 0 or getattr(pl, "grab", None) or getattr(pl, "hold_latch", False):
        return ("", False)                       # молча: схвачен, мёртв или ждём, пока отпустят клавишу
    left = hold_left(pl, sid, a)
    if left <= 0.0:
        return (f"{a.get('name', sid)}: запас исчерпан", False)
    if pl.mana < hold_cost(a) * HOLD_MIN_START:
        return ("Недостаточно маны", True)
    return None


def hold_start(pl, sid, a, mobs, projs, fx):
    """Начать поток. Первое срабатывание эффекта — сразу; дальше его ведёт hold_update()."""
    if getattr(pl, "hold_view", False):          # клиент сетевой игры: поток считает хост, здесь только картинка
        return
    blocked = hold_blocker(pl, sid, a)
    if blocked:
        text, mana = blocked
        if mana:
            pl.mana_flash = .35
        if text:
            fx.text(text, pl.cx, pl.y - 18)
        return
    kind = a.get("type", "nova")
    fn = SPELLS.get(kind)
    if fn is None:
        fx.text(f"неизвестное заклинание: {kind}", pl.cx, pl.y - 18)
        return
    loop = max(0.1, float(a.get("cast_animation", 0.55)))
    pl.skill_cast = (sid, 0.0, loop)
    res = fn(pl, dict(a, _sid=sid), mobs, projs, fx)
    if res is False:                             # не вышло (нет цели и т.п.) — ни маны, ни запаса не тратится
        pl.skill_cast = None
        return
    if invisibility.breaks(a): invisibility.on_attack(pl, fx)   # боевой поток из невидимости сбрасывает эффект
    start = HOLD_MIN_START
    pl.hold_pool[sid] = max(0.0, hold_left(pl, sid, a) - start)
    pl.mana = max(0.0, pl.mana - hold_cost(a) * start)
    pl.mana_t = CFG["player"].get("mana", {}).get("regen_delay", .9)
    pl.hold_rest.pop(sid, None)
    pl.hold = dict(res if isinstance(res, dict) else {}, sid=sid, t=0.0,
                   pulse=max(0.05, float(a.get("interval", HOLD_PULSE))))


def hold_update(pl, dt, mobs, projs, fx):
    """Каждый кадр (зовётся из Player.update): восстановление запаса у всех потоков, которые сейчас не зажаты,
    и ведение зажатого потока — расход запаса и маны, эффект, остановка (отпустил / запас или мана кончились)."""
    defs = CFG.get("skills", {})
    if not getattr(pl, "skill_held", False):
        pl.hold_latch = False                    # клавишу отпустили — можно начинать заново
    h = getattr(pl, "hold", None)
    for sid in getattr(pl, "skills", []):        # отдых: запас растёт с того значения, на котором остановились
        a = defs.get(sid)
        if not is_hold(a) or (h and h.get("sid") == sid):
            continue
        mx = hold_max(a)
        cur = pl.hold_pool.get(sid, mx)
        if cur >= mx:
            pl.hold_pool.pop(sid, None)
            continue
        rest = pl.hold_rest.get(sid, 0.0)
        if rest > 0:
            pl.hold_rest[sid] = rest - dt
            continue
        pl.hold_pool[sid] = min(mx, cur + hold_rate(a) * dt)
    if not h:
        return
    sid = h["sid"]; a = defs.get(sid, {})
    loop = max(0.1, float(a.get("cast_animation", 0.55)))
    h["t"] += dt
    if h.get("view"):
        # Клиент в сетевой игре: поток начал/закончил хост. Здесь только таймер, запас и анимация.
        pl.hold_pool[sid] = max(0.0, hold_left(pl, sid, a) - dt)
        pl.skill_cast = (sid, h["t"] % loop, loop)
        return
    why = None
    if pl.hp <= 0 or getattr(pl, "grab", None):
        why = "grab"
    elif not getattr(pl, "skill_held", False):
        why = "release"
    else:
        left = hold_left(pl, sid, a) - dt
        spend = hold_cost(a) * dt
        if left <= 0.0:
            pl.hold_pool[sid] = 0.0
            why = "empty"
        elif pl.mana < spend:
            pl.mana = 0.0
            why = "mana"
        else:
            pl.hold_pool[sid] = left
            pl.mana -= spend
            pl.mana_t = CFG["player"].get("mana", {}).get("regen_delay", .9)   # пока тратим — мана не восстанавливается
            kind = a.get("type")
            tick = CHANNELS.get(kind, (None, None))[0]
            if tick:
                if tick(pl, h, a, dt, mobs, projs, fx) is False:
                    why = "target"
            else:
                h["pulse"] -= dt
                if h["pulse"] <= 0:
                    h["pulse"] = max(0.0, h["pulse"] + max(0.05, float(a.get("interval", HOLD_PULSE))))
                    fn = SPELLS.get(kind)
                    if fn is not None and fn(pl, dict(a, _sid=sid), mobs, projs, fx) is False:
                        why = "target"
    if why:
        hold_stop(pl, fx, why)
        return
    pl.skill_cast = (sid, h["t"] % loop, loop)   # анимация применения крутится, пока держим


def hold_stop(pl, fx=None, why="release"):
    """Остановить поток: end-хук, запас начинает восстанавливаться.
    why: release (отпустил) / empty (запас кончился) / mana (кончилась мана) / target (цель пропала) / grab / swap."""
    h = getattr(pl, "hold", None)
    if not h:
        return
    pl.hold = None
    pl.skill_cast = None
    if h.get("view"):
        return
    sid = h["sid"]; a = CFG.get("skills", {}).get(sid, {})
    end = CHANNELS.get(a.get("type"), (None, None))[1]
    if end:
        end(pl, h, a, fx)
    pl.hold_rest[sid] = max(0.0, float(a.get("recharge_delay", 0.0)))
    if why in ("empty", "mana", "target") and getattr(pl, "skill_held", False):
        pl.hold_latch = True                     # клавиша всё ещё зажата — заново только после отпускания
    if fx is not None and why == "empty":
        fx.text(f"{a.get('name', sid)}: запас исчерпан", pl.cx, pl.y - 18)
    elif fx is not None and why == "mana":
        pl.mana_flash = .35
        fx.text("Недостаточно маны", pl.cx, pl.y - 18)


def hold_net(pl):
    """Состояние потоков для снимка мультиплеера: ([sid, сколько держим] или None, {sid: запас} только у неполных)."""
    h = getattr(pl, "hold", None)
    defs = CFG.get("skills", {})
    pools = {sid: round(v, 2) for sid, v in getattr(pl, "hold_pool", {}).items()
             if sid in defs and v < hold_max(defs[sid]) - 0.005}
    return ([h["sid"], round(h["t"], 2)] if h else None), pools


def hold_net_apply(pl, hd, hr):
    """Клиент: принять состояние потоков от хоста (потом поток крутится как «картинка», view=True)."""
    pl.hold_view = True
    pl.hold_pool = {k: float(v) for k, v in (hr or {}).items()}
    if hd:
        t, cur = float(hd[1]), pl.hold
        if cur and cur.get("sid") == hd[0] and abs(cur["t"] - t) < .3:
            t = cur["t"]                         # свой плавный отсчёт между снимками
        pl.hold = {"sid": hd[0], "t": t, "view": True}
    else:
        if pl.hold:
            pl.skill_cast = None
        pl.hold = None


# ---------------- заклинания-«потоки» (skills.json: "hold": true) ----------------
#
# Третий режим навыка (первые два: разовый и удерживаемый «стоя» — "channel"). Отличия от "channel":
#   * можно держать на бегу, в прыжке, при атаке и под ударами — ничто, кроме отпущенной клавиши, не прерывает;
#   * у навыка есть ЗАПАС: "duration" секунд, он тратится, пока клавиша зажата, и восстанавливается, когда отпущена —
#     с того значения, на котором остановились (а не с нуля, как кулдаун);
#   * "mana_cost" — мана В СЕКУНДУ, а не за применение;
#   * пока в запасе что-то есть (и хватает маны), навык можно использовать снова в любой момент.
# Поля навыка: hold, duration (запас, сек), mana_cost (мана/сек), recharge (сек полного восстановления с нуля, по умолчанию
# равно cooldown), recharge_delay (пауза перед восстановлением после отпускания, по умолчанию 0), interval (период
# повторения эффекта, сек, по умолчанию 0.35 — для типов без собственных хуков channel(...)).
# Эффект: у типа есть хуки channel(тип, tick=..., end=...) (напр. телекинетический захват) — используются они;
# иначе @spell-функция вызывается заново каждые "interval" секунд (потоки снарядов/молний/ударов по области).

HOLD_MIN_START = 0.1   # столько секунд запаса и маны списывается при старте (чтобы частые тычки не были бесплатными)
HOLD_PULSE = 0.35      # период повторения эффекта по умолчанию


def is_hold(a):
    """Навык-«поток» (skills.json: \"hold\": true). Если заданы и channel, и hold — работает как channel."""
    return bool(a) and bool(a.get("hold")) and not a.get("channel")


def hold_max(a):
    """Полный запас навыка в секундах."""
    return max(0.1, float(a.get("duration", 3.0)))


def hold_cost(a):
    """Расход маны в секунду, пока навык зажат."""
    return max(0.0, float(a.get("mana_cost", 10.0)))


def hold_rate(a):
    """Сколько секунд запаса возвращается за секунду отдыха (полный запас за \"recharge\" секунд)."""
    return hold_max(a) / max(0.1, float(a.get("recharge", a.get("cooldown", 5.0))))


def hold_left(pl, sid, a=None):
    """Сколько секунд запаса осталось у навыка-потока sid."""
    a = a if a is not None else CFG.get("skills", {}).get(sid, {})
    mx = hold_max(a)
    return max(0.0, min(mx, getattr(pl, "hold_pool", {}).get(sid, mx)))


def holding(pl, sid=None):
    """Зажат ли сейчас поток (и именно sid, если указан)."""
    h = getattr(pl, "hold", None)
    return bool(h) and (sid is None or h.get("sid") == sid)


def hold_blocker(pl, sid, a):
    """Почему поток сейчас не начать: None — можно; иначе (текст для игрока или None, «не хватает маны»)."""
    if pl.hp <= 0 or getattr(pl, "grab", None) or getattr(pl, "hold_latch", False):
        return ("", False)                       # молча: схвачен, мёртв или ждём, пока отпустят клавишу
    left = hold_left(pl, sid, a)
    if left <= 0.0:
        return (f"{a.get('name', sid)}: запас исчерпан", False)
    if pl.mana < hold_cost(a) * HOLD_MIN_START:
        return ("Недостаточно маны", True)
    return None


def hold_start(pl, sid, a, mobs, projs, fx):
    """Начать поток. Первое срабатывание эффекта — сразу; дальше его ведёт hold_update()."""
    if getattr(pl, "hold_view", False):          # клиент сетевой игры: поток считает хост, здесь только картинка
        return
    blocked = hold_blocker(pl, sid, a)
    if blocked:
        text, mana = blocked
        if mana:
            pl.mana_flash = .35
        if text:
            fx.text(text, pl.cx, pl.y - 18)
        return
    kind = a.get("type", "nova")
    fn = SPELLS.get(kind)
    if fn is None:
        fx.text(f"неизвестное заклинание: {kind}", pl.cx, pl.y - 18)
        return
    loop = max(0.1, float(a.get("cast_animation", 0.55)))
    pl.skill_cast = (sid, 0.0, loop)
    res = fn(pl, dict(a, _sid=sid), mobs, projs, fx)
    if res is False:                             # не вышло (нет цели и т.п.) — ни маны, ни запаса не тратится
        pl.skill_cast = None
        return
    start = HOLD_MIN_START
    pl.hold_pool[sid] = max(0.0, hold_left(pl, sid, a) - start)
    pl.mana = max(0.0, pl.mana - hold_cost(a) * start)
    pl.mana_t = CFG["player"].get("mana", {}).get("regen_delay", .9)
    pl.hold_rest.pop(sid, None)
    pl.hold = dict(res if isinstance(res, dict) else {}, sid=sid, t=0.0,
                   pulse=max(0.05, float(a.get("interval", HOLD_PULSE))))


def hold_update(pl, dt, mobs, projs, fx):
    """Каждый кадр (зовётся из Player.update): восстановление запаса у всех потоков, которые сейчас не зажаты,
    и ведение зажатого потока — расход запаса и маны, эффект, остановка (отпустил / запас или мана кончились)."""
    defs = CFG.get("skills", {})
    if not getattr(pl, "skill_held", False):
        pl.hold_latch = False                    # клавишу отпустили — можно начинать заново
    h = getattr(pl, "hold", None)
    for sid in getattr(pl, "skills", []):        # отдых: запас растёт с того значения, на котором остановились
        a = defs.get(sid)
        if not is_hold(a) or (h and h.get("sid") == sid):
            continue
        mx = hold_max(a)
        cur = pl.hold_pool.get(sid, mx)
        if cur >= mx:
            pl.hold_pool.pop(sid, None)
            continue
        rest = pl.hold_rest.get(sid, 0.0)
        if rest > 0:
            pl.hold_rest[sid] = rest - dt
            continue
        pl.hold_pool[sid] = min(mx, cur + hold_rate(a) * dt)
    if not h:
        return
    sid = h["sid"]; a = defs.get(sid, {})
    loop = max(0.1, float(a.get("cast_animation", 0.55)))
    h["t"] += dt
    if h.get("view"):
        # Клиент в сетевой игре: поток начал/закончил хост. Здесь только таймер, запас и анимация.
        pl.hold_pool[sid] = max(0.0, hold_left(pl, sid, a) - dt)
        pl.skill_cast = (sid, h["t"] % loop, loop)
        return
    why = None
    if pl.hp <= 0 or getattr(pl, "grab", None):
        why = "grab"
    elif not getattr(pl, "skill_held", False):
        why = "release"
    else:
        left = hold_left(pl, sid, a) - dt
        spend = hold_cost(a) * dt
        if left <= 0.0:
            pl.hold_pool[sid] = 0.0
            why = "empty"
        elif pl.mana < spend:
            pl.mana = 0.0
            why = "mana"
        else:
            pl.hold_pool[sid] = left
            pl.mana -= spend
            pl.mana_t = CFG["player"].get("mana", {}).get("regen_delay", .9)   # пока тратим — мана не восстанавливается
            kind = a.get("type")
            tick = CHANNELS.get(kind, (None, None))[0]
            if tick:
                if tick(pl, h, a, dt, mobs, projs, fx) is False:
                    why = "target"
            else:
                h["pulse"] -= dt
                if h["pulse"] <= 0:
                    h["pulse"] = max(0.0, h["pulse"] + max(0.05, float(a.get("interval", HOLD_PULSE))))
                    fn = SPELLS.get(kind)
                    if fn is not None and fn(pl, dict(a, _sid=sid), mobs, projs, fx) is False:
                        why = "target"
    if why:
        hold_stop(pl, fx, why)
        return
    pl.skill_cast = (sid, h["t"] % loop, loop)   # анимация применения крутится, пока держим


def hold_stop(pl, fx=None, why="release"):
    """Остановить поток: end-хук, запас начинает восстанавливаться.
    why: release (отпустил) / empty (запас кончился) / mana (кончилась мана) / target (цель пропала) / grab / swap."""
    h = getattr(pl, "hold", None)
    if not h:
        return
    pl.hold = None
    pl.skill_cast = None
    if h.get("view"):
        return
    sid = h["sid"]; a = CFG.get("skills", {}).get(sid, {})
    end = CHANNELS.get(a.get("type"), (None, None))[1]
    if end:
        end(pl, h, a, fx)
    pl.hold_rest[sid] = max(0.0, float(a.get("recharge_delay", 0.0)))
    if why in ("empty", "mana", "target") and getattr(pl, "skill_held", False):
        pl.hold_latch = True                     # клавиша всё ещё зажата — заново только после отпускания
    if fx is not None and why == "empty":
        fx.text(f"{a.get('name', sid)}: запас исчерпан", pl.cx, pl.y - 18)
    elif fx is not None and why == "mana":
        pl.mana_flash = .35
        fx.text("Недостаточно маны", pl.cx, pl.y - 18)


def hold_net(pl):
    """Состояние потоков для снимка мультиплеера: ([sid, сколько держим] или None, {sid: запас} только у неполных)."""
    h = getattr(pl, "hold", None)
    defs = CFG.get("skills", {})
    pools = {sid: round(v, 2) for sid, v in getattr(pl, "hold_pool", {}).items()
             if sid in defs and v < hold_max(defs[sid]) - 0.005}
    return ([h["sid"], round(h["t"], 2)] if h else None), pools


def hold_net_apply(pl, hd, hr):
    """Клиент: принять состояние потоков от хоста (потом поток крутится как «картинка», view=True)."""
    pl.hold_view = True
    pl.hold_pool = {k: float(v) for k, v in (hr or {}).items()}
    if hd:
        t, cur = float(hd[1]), pl.hold
        if cur and cur.get("sid") == hd[0] and abs(cur["t"] - t) < .3:
            t = cur["t"]                         # свой плавный отсчёт между снимками
        pl.hold = {"sid": hd[0], "t": t, "view": True}
    else:
        if pl.hold:
            pl.skill_cast = None
        pl.hold = None


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
    if not act or channeling(pl) or holding(pl):
        return False
    sid = act[pl.skill_index % len(act)]
    a = CFG.get("skills", {}).get(sid, {})
    if is_hold(a):                       # поток: нужен запас и немного маны (кулдауна нет)
        return hold_blocker(pl, sid, a) is None and not getattr(pl, "hold_view", False)
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
    if not act or channeling(pl) or holding(pl):    # уже колдуем/держим заклинание — новые нажатия игнорируются
        return
    sid = act[pl.skill_index % len(act)]
    a = defs.get(sid)
    if not a:
        return
    if is_hold(a):                   # поток: свой запас вместо кулдауна, мана — в секунду (см. hold_start)
        hold_start(pl, sid, a, mobs, projs, fx)
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
    hold = bool(a.get("channel"))
    if hold:
        why = _channel_blocker(pl)
        if why:
            fx.text(why, pl.cx, pl.y - 18)
            return
    pl.skill_cast = (sid, 0.0, float(a.get("cast_animation", 0.55)))
    res = fn(pl, dict(a, _sid=sid), mobs, projs, fx)
    if res is False:                 # заклинание не сработало (нет цели и т.п.) — ни маны, ни перезарядки
        pl.skill_cast = None
        return
    if invisibility.breaks(a): invisibility.on_attack(pl, fx)   # боевое заклинание из невидимости сбрасывает эффект
    pl.mana -= cost
    pl.mana_t = CFG["player"].get("mana", {}).get("regen_delay", .9)
    if hold:                         # удерживаемое: перезарядка стартует, когда каст закончится (channel_stop)
        begin_channel(pl, sid, a, res if isinstance(res, dict) else None)
    else:
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


@spell("invisibility")
def _invisibility(pl, a, mobs, projs, fx):
    """Мантия невидимости: накладывает на применившего юнита эффект невидимости (invisibility.py) на "duration" секунд
    (по умолчанию 10; 0 — бессрочно). Мобы его не замечают и не агрятся, пока эффект действует; атака (удар оружием,
    боевое заклинание) эффект сбрасывает. Необязательные поля навыка: "transparency" — свой процент прозрачности вместо
    общего из data/invisibility.json, "break_on_attack": false — не снимать при атаке."""
    spec = {"time": a.get("duration", 10.0)}
    for key in ("transparency", "break_on_attack"):
        if key in a: spec[key] = a[key]
    invisibility.apply(pl, spec, fx)


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


HOLD_REFRESH = 0.2   # на сколько секунд захват обновляет стан цели каждый кадр (после конца каста он быстро спадает)


@spell("telekinesis_hold")
def _telekinesis_hold(pl, a, mobs, projs, fx):
    """Телекинетический захват: останавливает ближайшего к курсору врага и держит его в стане.
    С "channel": true (так в skills.json) — удерживаемое заклинание, как ульта Bane: цель в стане, пока герой
    стоит и держит клавишу навыка, но не дольше "duration" секунд (хуки _hold_tick/_hold_end ниже).
    Без "channel" — разовый стан на "duration" секунд, как раньше."""
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
        return False
    if status.cc_immune(target):   # боссы (cc_immune) не поддаются — см. status.py
        fx.text("иммунитет к контролю", target.cx, target.cy - 60)
        return False
    fx.beam(pl.cx, pl.cy, target.cx, target.cy, color)
    fx.ring(target.cx, target.cy, 38)
    target.vx = 0.0
    if getattr(target, "flies", False):
        target.vy = 0.0
    if a.get("channel") or a.get("hold"):
        status.apply(target, {"stun": HOLD_REFRESH}, fx)
        face = sign(target.cx - pl.cx)
        if face:
            pl.face = face          # герой смотрит на пойманного врага
        return {"target": target, "beam": 0.1, "break_range": float(a.get("break_range", reach * 1.5))}
    status.apply(target, {"stun": dur}, fx)


def _hold_tick(pl, ch, a, dt, mobs, projs, fx):
    """Каждый кадр каста: удерживаем стан цели и обновляем луч. False — цель погибла/пропала/вырвалась за break_range."""
    t = ch.get("target")
    if t is None or t.hp <= 0 or t not in mobs:
        return False
    if math.hypot(t.cx - pl.cx, t.cy - pl.cy) > ch.get("break_range", 500):
        return False
    status.apply(t, {"stun": HOLD_REFRESH})
    t.vx = 0.0
    if getattr(t, "flies", False):
        t.vy = 0.0
    ch["beam"] -= dt
    if ch["beam"] <= 0:                                  # луч «живёт» 0.22 с, обновляем чаще — выглядит сплошным
        ch["beam"] = 0.1
        fx.beam(pl.cx, pl.cy, t.cx, t.cy, list(a.get("color", [200, 120, 255])))


def _hold_end(pl, ch, a, fx):
    """Каст закончился: цель отпускают (её стан спадает за доли секунды)."""
    t = ch.get("target")
    if t is not None and fx is not None:
        fx.ring(t.cx, t.cy, 30)


channel("telekinesis_hold", tick=_hold_tick, end=_hold_end)
