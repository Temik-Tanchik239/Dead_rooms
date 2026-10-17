"""Оружие в руках: скины, замах, иконки (HUD и предметы на полу).
weapons.json: skin (картинка носом вправо, рукоять слева), draw [w, h] (размер на экране), grip [x, y] (где рука, px от левого верхнего
угла картинки), rest_angle (угол в покое, градусы, + вверх), rotate: false + fixed_angle (не поворачивать, напр. склянка),
style: "slash" | "thrust". В шаге комбо: style, swing [от, до] (градусы) — как идёт взмах.
Нет skin — ищется assets/weapons/<id>.png, нет файла — оружие просто не рисуется."""
import math
import pygame as pg
from core import CFG
from anim import sprite

def info(wid):
    w = CFG["weapons"][wid]; dw, dh = w.get("draw", [40, 12])
    return w.get("skin") or f"weapons/{wid}.png", dw, dh, w.get("grip", [dw * .15, dh / 2])

def ease(k): k = max(0.0, min(1.0, k)); return k * k * (3 - 2 * k)

def held_pose(pl):
    """(id оружия, угол, сдвиг по x, trail) в системе «лицом вправо»; trail — (от, до) для следа взмаха."""
    W = CFG["weapons"]
    def rest(wid):
        w = W[wid]; return w.get("rest_angle", -30) if w.get("rotate", True) else w.get("fixed_angle", 0)
    if pl.state == "attack" and pl.atk:
        a = pl.atk; wid = a["w"]; w = W[wid]; st = a["step"]; t, wu, ac, rec = a["t"], a["wu"], a["ac"], max(a["rec"], 1e-6)
        if "projectile" in st:
            if not w.get("rotate", True): return wid, w.get("fixed_angle", 0), -3 * ease(t / max(wu, 1e-6)) if t < wu else 0, None
            aim = pl.aim_deg(); ang = 0 if aim is None else aim
            push = -4 * ease(t / max(wu, 1e-6)) if t < wu else -4 * (1 - ease((t - wu) / .15))
            return wid, ang, push, None
        if st.get("style", w.get("style", "slash")) == "thrust":
            base = w.get("thrust_angle", 0)
            if t < wu: dx = -8 * ease(t / max(wu, 1e-6))
            elif t < wu + ac: dx = -8 + 18 * (t - wu) / max(ac, 1e-6)
            else: dx = 10 * (1 - ease((t - wu - ac) / rec))
            return wid, base, dx, None
        a0, a1 = st.get("swing") or ((80, -50) if a["n"] % 2 == 0 else (-50, 70)); r0 = rest(wid)
        if t < wu: return wid, r0 + (a0 - r0) * ease(t / max(wu, 1e-6)), 0, None
        if t < wu + ac:
            ang = a0 + (a1 - a0) * (t - wu) / max(ac, 1e-6); return wid, ang, 0, (a0, ang)
        return wid, a1 + (r0 - a1) * ease((t - wu - ac) / rec), 0, None
    wid = pl.slots[0]; return wid, rest(wid), 0, None

def draw_held(v, pl, hand):
    """Рисует оружие в кисти hand (мир. координаты). Вызывается после спрайта игрока."""
    wid, ang, dx, trail = held_pose(pl); path, dw, dh, (gx, gy) = info(wid); f = pl.face
    hx, hy = hand[0] + f * dx, hand[1]
    q = round((ang if f > 0 else -ang) / 5) * 5
    img = sprite(path, dw, dh, f < 0, False, q)
    if not img: return
    th = math.radians(q); vx, vy = (gx if f > 0 else dw - gx) - dw / 2, gy - dh / 2
    rx, ry = vx * math.cos(th) + vy * math.sin(th), -vx * math.sin(th) + vy * math.cos(th)
    v.blit(img, img.get_rect(center=(int(hx - rx), int(hy - ry))))
    if trail:   # белый след взмаха
        R = max(8, dw - gx); lo, hi = sorted(trail)
        if f < 0: lo, hi = 180 - hi, 180 - lo
        pg.draw.arc(v, (235, 240, 255), pg.Rect(int(hx - R), int(hy - R), int(2 * R), int(2 * R)), math.radians(lo), math.radians(hi), 3)

def icon(v, wid, x, y, box=24, angle=0):
    """Иконка оружия по центру (x, y), вписанная в квадрат box x box. False — нет картинки."""
    path, dw, dh, _ = info(wid); k = box / max(dw, dh)
    img = sprite(path, max(1, round(dw * k)), max(1, round(dh * k)), False, False, angle)
    if img: v.blit(img, img.get_rect(center=(int(x), int(y)))); return True
    return False
