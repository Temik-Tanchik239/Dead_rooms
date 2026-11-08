"""Статусные эффекты мобов: заморозка (freeze), оглушение (stun) и горение (burn).

Эффекты накладываются заклинаниями игрока (spells.py) и пулями (поле "effect" у типа
пули в data/projectiles.json). Эффект задаётся словарём:
    {"freeze": 2.0}                       — обездвижить на 2 секунды (синий оттенок)
    {"stun": 2.0}                         — оглушить на 2 секунды (не может атаковать/двигаться)
    {"burn": {"time": 3, "dps": 10}}      — горение: dps урона в секунду в течение time секунд
    {"invisible": 10}                     — невидимость на 10 секунд (или {"time": 10, "transparency": 80}); см. invisibility.py.
                                            Единственный эффект, который действует и на игрока, и на моба (и на босса).

Моб хранит таймеры s.frozen / s.burn (+ s.burn_dps); заморозка/оглушение переиспользуют
штатный s.stun. Наложение и тик — здесь, чтобы расширять логику в одном месте.
Босс (или моб с "cc_immune": true в data/mobs.json) не поддаётся контролю, но горит."""
import random
import invisibility


def init(mob):
    """Поля статусов на мобе (вызывается из Mob.__init__)."""
    mob.frozen = 0.0
    mob.burn = 0.0
    mob.burn_dps = 0.0


def cc_immune(mob):
    """Иммунитет к контролю (заморозка/оглушение): боссы, иначе их можно залочить насмерть."""
    return bool(mob.d.get("cc_immune", mob.d.get("boss")))


def apply(mob, eff, fx=None):
    """Наложить эффект eff (словарь) на моба. Безопасно для не-мобов (у них нет полей статусов)."""
    if eff and eff.get("invisible"):
        invisibility.apply(mob, eff["invisible"], fx)     # невидимость — общий эффект игрока и мобов
    if not eff or not hasattr(mob, "frozen"):
        return
    freeze = float(eff.get("freeze", 0) or 0)
    stun = float(eff.get("stun", 0) or 0)
    burn = eff.get("burn")
    if (freeze or stun) and not cc_immune(mob):
        dur = max(freeze, stun)
        mob.stun = max(getattr(mob, "stun", 0.0), dur)   # штатный стан держит моба на месте и без атак
        if freeze:
            mob.frozen = max(mob.frozen, freeze)
        mob.act = None
        mob.grav = None
        mob.aggro = True
        if fx is not None:
            fx.text("заморожен" if freeze else "оглушён", mob.cx, mob.cy - 60)
    if burn:
        mob.burn = max(mob.burn, float(burn.get("time", 3)))
        mob.burn_dps = max(mob.burn_dps, float(burn.get("dps", 8)))
        mob.aggro = True


def tick(mob, dt, w=None):
    """Каждый кадр: таймеры тают, горение наносит урон. Вызывается из Mob.update."""
    invisibility.tick(mob, dt, w.fx if w is not None else None)   # время невидимости тает
    if mob.frozen > 0:
        mob.frozen = max(0.0, mob.frozen - dt)
    if mob.burn > 0:
        mob.burn = max(0.0, mob.burn - dt)
        mob.hp -= mob.burn_dps * dt
        if w is not None and random.random() < dt * 10:
            w.fx.ring(mob.cx + random.uniform(-8, 8), mob.cy - random.uniform(0, 14), 5)


def tint(mob):
    """Цвет полупрозрачной заливки поверх моба (RGBA) или None — для Mob.draw."""
    if mob.frozen > 0:
        return (120, 200, 255, 95)
    if mob.burn > 0:
        return (255, 130, 40, 70)
    return None
