"""DEAD ROOMS — механики Dead Cells + карты-экраны, нарисованные вручную (data/maps/*.json, порядок — data/maps.json).
Весь контент (физика, оружие, мобы, карты) лежит в data/*.json. F5 в игре — перезагрузка данных."""
import functools, math, random, sys
from types import SimpleNamespace
import pygame as pg
from core import CFG, SETTINGS, DATA, ASSETS, T, COLS, ROWS, W, H, MW, MH, VIEW_H, reload_data, sign, approach, tile, free, FX, Body, CHAR, apply_character, char_ids, use_char

CAMERA_ZOOM = 0.92  # меньше 1.0 — камера дальше, видно больше окружения
from anim import clear_cache, sprite, mob_frame
import weapon
import hud
import spells
import crossbow
import invisibility
from projectiles import volley
from mob import Mob, Corpse, spawn_boss
import characters as char_menu
from maps import Campaign, Drop, END, VH, check, random_weapon, pos_of, world_text, world_links, two_way
import multiplayer as mp
import lighting
import devtools
from devtools import hostile

# Навыки по умолчанию, если у персонажа в data/characters.json нет base_skills.
BASE_SKILLS = ["dash"]
DEFAULT_WEAPONS = ["rusty_sword", "short_bow"]
AIR_ANIM_DELAY = 0.10   # сколько секунд герой должен быть в воздухе, чтобы включилась анимация прыжка (падение)
AIR_ANIM_RISE = 40      # скорость взлёта (px/с), с которой прыжок включается сразу

# ---------- отрисовка эффектов заклинаний (молнии, удар сверху, вспышка) ----------
def _beam_points(x1, y1, x2, y2, segs=7, jitter=9):
    """Ломаная «молния» между точками с поперечным дрожанием (пересчитывается каждый кадр — мерцает)."""
    dx, dy = x2 - x1, y2 - y1; L = math.hypot(dx, dy) or 1.0; nx, ny = -dy / L, dx / L
    pts = [(x1, y1)]
    for i in range(1, segs):
        f = i / segs; off = random.uniform(-jitter, jitter)
        pts.append((x1 + dx * f + nx * off, y1 + dy * f + ny * off))
    pts.append((x2, y2))
    return [(int(a), int(b)) for a, b in pts]

def _draw_beam(v, x1, y1, x2, y2, col, k):
    """k — доля оставшейся жизни (1..0): цвет гаснет к чёрному фону (альфа без отдельной поверхности)."""
    c = tuple(int(ch * k) for ch in col[:3]); core = tuple(min(255, int(ch + (255 - ch) * .45)) for ch in c)
    pts = _beam_points(x1, y1, x2, y2)
    pg.draw.lines(v, c, False, pts, 5); pg.draw.lines(v, core, False, pts, 2)

def _draw_bolt(v, x, y, col, k):
    _draw_beam(v, x, y - 300, x, y, col, k)
    c = tuple(int(ch * k) for ch in col[:3]); pg.draw.circle(v, c, (int(x), int(y)), int(12 + 46 * (1 - k)), 3)

def _draw_flash(v, x, y, r, col, k):
    c = tuple(int(ch * k) for ch in col[:3]); pg.draw.circle(v, c, (int(x), int(y)), int(r * (1 - k) + 6), 3)

def in_char(fn):
    """Метод игрока выполняется с данными ЕГО героя (в мультиплеере у игроков разные персонажи)."""
    @functools.wraps(fn)
    def wrap(s, *a, **k):
        if CHAR["id"] == s.char_id: return fn(s, *a, **k)
        with use_char(s.char_id): return fn(s, *a, **k)
    return wrap

class Player(Body):
    H0 = 34
    def __init__(s):
        ch = CFG.get("character", {})
        # Физический хитбокс задаётся отдельно для каждого героя в data/characters.json.
        hitbox = ch.get("hitbox", [20, 34])
        try: hw, hh = max(4, int(hitbox[0])), max(4, int(hitbox[1]))
        except (TypeError, ValueError, IndexError): hw, hh = 20, 34
        super().__init__(0, 0, hw, hh)
        s.H0 = hh
        s.model_scale = max(0.1, min(5.0, float(ch.get("model_scale", 1.0))))
        s.char_id = ch.get("id")
        s.face, s.state = 1, "move"
        s.hp_regen_timer = 0.0
        s.inv = s.coy = s.st = s.lock = s.drop_t = s.stun = 0
        s.grab = None   # схвачен рукой Моргарта: {"hand", "t" (сколько ещё держат), "tick", "struggle", "prev"} — см. boss_hands.py
        s.atk, s.combo, s.hitbox = None, (None, 0, 0), None
        s.buf = dict(jump=0, roll=0, a1=0, a2=0, skill=0)
        # Стартовое оружие персонажа (data/characters.json -> weapons: [оружие ЛКМ, оружие ПКМ]).
        # Чистый заклинатель (spellcaster — маг/инженер) и арбалетчик (crossbows — Тень) не носят оружие вовсе: слоты пусты.
        if ch.get("spellcaster") or ch.get("crossbows"): s.slots = [None, None]
        else: s.slots = [w if w in CFG["weapons"] else DEFAULT_WEAPONS[i] for i, w in enumerate((list(ch.get("weapons", [])) + DEFAULT_WEAPONS[len(ch.get("weapons", [])):])[:2])]
        s.anim, s.anim_t, s.anim_p = "idle", 0.0, None
        s.air_t = 0.0   # сколько секунд подряд герой не касается земли (для анимации прыжка)
        s.aim = None   # куда смотрит курсор (координаты комнаты) или None
        s.level = 1; s.xp = 0; s.xp_next = 100
        # Базовые навыки персонажа выдаются сразу и не требуют повышения уровня.
        s.skills = [sid for sid in ch.get("base_skills", BASE_SKILLS) if sid in CFG.get("skills", {})]
        s.refresh_mana(True); s.hp = s.maxhp
        s.skill_index = 0; s.air_jumps = 0
        s.skill_cooldowns = {key: 0.0 for key in s.skills}; s.skill_notice = 0.0
        s.shield_time = 0.0; s.shield_hp = 0.0; s.shield_face = s.face; s.shield_asset_cache = {}
        s.last_weapon = s.slots[0]; s.skill_cast = None
        crossbow.init(s)   # мини-арбалеты (Тень): виды снарядов, перезарядка и отдача по каждому арбалету — см. crossbow.py
        # Удерживаемое заклинание (skills.json: "channel": true — напр. захват инженера, как ульта Bane): словарь
        # {"sid", "t" (сколько уже колдуем), "max" (лимит, сек), ...} или None. Логика — spells.channel_*.
        s.channel = None
        s.skill_held = False   # зажата ли клавиша навыка (одиночная игра: Game.step; сеть: бит в NetKeys)
        s.move_input = False   # зажато ли движение/«вниз» в этом кадре (удерживаемое заклинание нельзя начать на бегу)
        # Заклинания-«потоки» (skills.json: "hold": true — зажал и держишь, запас тратится, отпустил — восстанавливается).
        # hold — активный поток {"sid", "t", ...} или None; hold_pool — оставшийся запас в секундах по навыкам (нет записи = полный);
        # hold_rest — пауза перед восстановлением; hold_latch — запас/мана кончились при зажатой клавише, ждём отпускания;
        # hold_view — клиент сетевой игры (поток считает хост). Логика — spells.hold_*.
        s.hold = None; s.hold_pool = {}; s.hold_rest = {}; s.hold_latch = False; s.hold_view = False
        # Мультиплеер: номер и имя игрока, прогресс воскрешения, «отошёл от входа» (для выходов).
        s.pid, s.name, s.revive, s.armed, s.downed = 0, "", 0.0, False, False
        # tp — номер «телепорта» (хост переставил игрока), hitc/kb — счётчик попаданий и отброс: клиент повторяет их у себя.
        s.tp, s.hitc, s.kb = 0, 0, (0.0, 0.0)
        # Невидимость (invisibility.py): s.invis — состояние эффекта или None; тик — в update, прозрачность — в draw.
        invisibility.init(s)
    @in_char
    def press(s, what): s.buf[what] = CFG["player"]["buffer"]
    def passive_mult(s, kind):
        """Произведение multiplier всех пассивок типа kind (damage, move_speed, mana_regen)."""
        k = 1.0
        for sid in s.skills:
            d = CFG.get("skills", {}).get(sid, {})
            if d.get("type") == kind: k *= float(d.get("multiplier", 1.0))
        return k
    def dmg_mult(s): return CFG["player"].get("dmg_mult", 1.0) * s.passive_mult("damage")
    def speed(s): return CFG["player"]["speed"] * s.passive_mult("move_speed")
    @in_char
    def can_use(s, wid):
        allowed = CFG.get("character", {}).get("allowed_weapons")
        return not allowed or wid in allowed
    def anim_states(s):
        p = CFG["player"]
        if s.state == "roll": return ["roll"], 1 - max(0, s.st) / p["roll_time"]
        if s.state == "attack" and s.atk:
            a = s.atk; prog = min(1, a["t"] / (a["wu"] + a["ac"] + a["rec"]))
            return (["shoot", "attack"] if "projectile" in a["step"] else ["attack"]), prog
        if s.state == "ladder": return ["ladder"], None
        if s.stun > 0: return ["hurt"], None
        # Флаг ground у стоящего героя «мигает» (физика каждый кадр на долю пикселя проваливается в пол и тут же
        # возвращается), поэтому прыжок показываем только при реальном взлёте или если герой в воздухе дольше AIR_ANIM_DELAY.
        if not s.ground and (s.vy < -AIR_ANIM_RISE or s.air_t > AIR_ANIM_DELAY): return ["jump"], None
        return (["move"] if abs(s.vx) > 25 else ["idle"]), None
    def airborne(s):
        """Герой реально в воздухе. Флаг ground у стоящего «мигает», поэтому эвристика та же, что у анимации прыжка."""
        return not s.ground and (s.vy < -AIR_ANIM_RISE or s.air_t > AIR_ANIM_DELAY)
    def facing(s, d):
        """Куда повернуться при ударе: к курсору (если есть) или по движению."""
        return (sign(s.aim[0] - s.cx) or s.face) if s.aim else (d or s.face)
    def hand(s, state="idle"):
        """Где кисть в мире (по данным player.json: hand / hands)."""
        p = CFG["player"]; hx, hy = p.get("hands", {}).get(state, p.get("hand", [13, -24])); r = s.rect
        return (r.centerx + s.face * hx, r.bottom + hy)
    def aim_deg(s):
        """Угол на курсор в системе «лицом вправо» (+ вверх) или None."""
        if not s.aim: return None
        hx, hy = s.hand("shoot"); a = math.degrees(math.atan2(hy - s.aim[1], s.aim[0] - hx)); a = a if s.face > 0 else 180 - a
        return (a + 180) % 360 - 180
    @in_char
    def update_anim(s, dt):
        s.air_t = 0.0 if s.ground else s.air_t + dt
        st, p = s.anim_states(); key = "|".join(st)
        if key != s.anim: s.anim, s.anim_t = key, 0.0
        else: s.anim_t += dt
        s.anim_p = p
    @in_char
    def draw(s, v):
        p = CFG["player"]; r = s.rect; st = s.anim.split("|")
        dw, dh = p.get("draws", {}).get(st[0], p.get("draw", [s.w, s.H0]))
        dw, dh = max(1, int(dw * s.model_scale)), max(1, int(dh * s.model_scale))
        def body():
            xb = crossbow.enabled() and st[0] not in ("roll", "ladder")   # мини-арбалеты в руках видны всегда, кроме переката и лестницы
            if xb: crossbow.draw(v, s, 1)   # второй арбалет (ПКМ) — в дальней руке, за телом
            img = sprite(mob_frame(f"player:{s.char_id}", p, st, s.anim_t, s.anim_p, folder=p.get("folder", "player")), dw, dh, s.face < 0)
            if img: v.blit(img, (r.centerx - dw // 2, r.bottom - dh))
            else:
                pg.draw.rect(v, (200, 160, 70) if s.state == "roll" else (240, 200, 90), r, border_radius=4)
                ex = r.right - 6 if s.face > 0 else r.left + 3; pg.draw.rect(v, (30, 20, 20), (ex, r.top + 6, 3, 5))
            if st[0] not in ("roll", "ladder"): weapon.draw_held(v, s, s.hand(st[0]))
            if xb: crossbow.draw(v, s, 0)   # первый арбалет (ЛКМ) — в ближней руке, поверх тела
            if crossbow.enabled(): crossbow.draw_hooks(v, s)   # нити гарпунов и их наконечники
        # Невидимость: герой с оружием рисуется прозрачным (процент — data/invisibility.json, у навыка/эффекта может быть свой).
        invisibility.ghost(v, pg.Rect(r.centerx - dw // 2, r.bottom - dh, dw, dh).inflate(200, 80), body, invisibility.alpha(s))
        # Анимация применения навыка: сначала кадры из ассета (skills/<id>/cast — можно заменить
        # своими PNG), иначе — процедурная анимация для встроенных навыков / запасная вспышка.
        cast = s.skill_cast
        if cast:
            sid, elapsed, duration = cast
            t = max(0.0, min(1.0, elapsed / max(duration, 0.001)))
            cx, cy = int(r.centerx + s.face * 20), int(r.centery)
            defs = CFG.get("skills", {}); sk = defs.get(sid, {})
            color = tuple(sk.get("color", [100, 190, 255]))
            cframes = spells.cast_frames(sid, sk)
            if cframes:
                # Кадры из ассета прокручиваются ровно за время каста и отражаются по направлению игрока.
                cw, ch = sk.get("cast_size", [96, 96]); cw, ch = max(1, int(cw)), max(1, int(ch))
                ox, oy = sk.get("cast_offset", [24, 0])
                frame = cframes[min(len(cframes) - 1, int(t * len(cframes)))]
                img = sprite(frame, cw, ch, s.face < 0)
                if img: v.blit(img, (int(r.centerx + s.face * ox - cw / 2), int(r.centery + oy - ch / 2)))
            else:
                overlay = pg.Surface(v.get_size(), pg.SRCALPHA)
                if sid == "dash":
                    # Быстрые следы за персонажем.
                    for i in range(4):
                        alpha = int(110 * (1-t) * (1-i/4))
                        x = int(r.centerx - s.face * (12 + i*9))
                        pg.draw.line(overlay, (*color, alpha), (x, r.top+5+i*3), (x-s.face*15, r.bottom-4-i*2), 3)
                elif sid == "nova":
                    rad = int(10 + 95*t)
                    pg.draw.circle(overlay, (*color, int(180*(1-t))), (int(r.centerx), int(r.centery)), rad, max(2, int(6*(1-t))))
                    for i in range(8):
                        ang = i * math.tau/8 + t*0.8
                        x2, y2 = int(r.centerx + math.cos(ang)*rad), int(r.centery + math.sin(ang)*rad)
                        pg.draw.circle(overlay, (*color, int(210*(1-t))), (x2,y2), max(1, int(4*(1-t))))
                elif sid == "heal":
                    rad = int(12 + 26*t)
                    pg.draw.circle(overlay, (*color, int(190*(1-t))), (int(r.centerx), int(r.centery)), rad, 3)
                    for i in range(5):
                        yy = r.bottom - int((t*38 + i*9) % 45)
                        xx = r.centerx + int(math.sin(t*8+i*1.7)*18)
                        pg.draw.circle(overlay, (*color, int(180*(1-t))), (xx, yy), 2)
                elif sid == "shield":
                    # Короткий всплеск вокруг щита при создании.
                    rad = int(16 + 24*t)
                    pg.draw.circle(overlay, (*color, int(190*(1-t))), (cx,cy), rad, 3)
                else:
                    # Запасная вспышка для навыков без своей анимации (например телекинеза без ассета).
                    rad = int(14 + 70*t)
                    pg.draw.circle(overlay, (*color, int(150*(1-t))), (cx, cy), rad, max(2, int(6*(1-t))))
                    for i in range(6):
                        ang = i * math.tau/6 - t*1.2
                        x2, y2 = int(cx + math.cos(ang)*rad), int(cy + math.sin(ang)*rad)
                        pg.draw.circle(overlay, (*color, int(190*(1-t))), (x2, y2), max(1, int(3*(1-t))))
                v.blit(overlay, (0,0))
        if s.shield_time > 0:
            shield_def = CFG.get("skills", {}).get("shield", {})
            rel = shield_def.get("visual", "skills/shield/shield_effect.png")
            if rel not in s.shield_asset_cache:
                try:
                    s.shield_asset_cache[rel] = pg.image.load(str(ASSETS / rel)).convert_alpha()
                except (OSError, pg.error):
                    s.shield_asset_cache[rel] = None
            shield_img = s.shield_asset_cache.get(rel)
            if shield_img:
                size = shield_def.get("visual_size", [70, 78])
                shield_img = pg.transform.smoothscale(shield_img, (int(size[0]), int(size[1])))
                s.shield_face = s.face  # щит постоянно следует за текущим направлением игрока
                if s.shield_face < 0: shield_img = pg.transform.flip(shield_img, True, False)
                sx = r.centerx + s.shield_face * (r.width // 2 + int(size[0]) * 0.32)
                sy = r.centery + int(shield_def.get("visual_y_offset", 2))
                shield_img.set_alpha(max(90, min(255, int(150 + 55 * math.sin(pg.time.get_ticks() * .012)))))
                v.blit(shield_img, shield_img.get_rect(center=(sx, sy)))
    def can_stand(s, g): return free(g, pg.Rect(int(s.x), int(s.y) - (s.H0 - s.h), s.w, s.H0))
    @in_char
    def hit(s, dmg, fx_x, fx, kb=260):
        if s.inv > 0 or s.hp <= 0: return
        # Щит блокирует атаки, пришедшие со стороны, куда он выставлен.
        if s.shield_time > 0 and abs(fx_x - s.cx) > 2 and s.shield_face * (fx_x - s.cx) > 0 and s.shield_hp > 0:
            absorbed = min(float(dmg), s.shield_hp)
            s.shield_hp -= absorbed
            dmg = max(0.0, float(dmg) - absorbed)
            fx.ring(s.cx + s.shield_face * 24, s.cy, 18)
            if s.shield_hp <= 0:
                s.shield_hp = 0; s.shield_time = 0
                fx.text("Щит разрушен", s.cx, s.y - 18)
            if dmg <= 0: return
        s.hp -= dmg
        if s.channel: spells.channel_stop(s, fx, "damage")   # урон прерывает удерживаемое заклинание
        s.hp_regen_timer = 0.0  # любой полученный урон заново запускает задержку регенерации
        s.inv = CFG["player"]["hurt_inv"]; s.stun = .18
        s.vx = (sign(s.cx - fx_x) or 1) * kb; s.vy = -260; fx.shake = .2; fx.stop = .06
        s.hitc += 1; s.kb = (s.vx, s.vy)
        if s.state in ("attack", "ladder"): s.state = "move"; s.atk = None
    @in_char
    def refresh_mana(s, full=False):
        """Прочитать настройки маны из player.json (full — заполнить стартовым значением)."""
        m = CFG["player"].get("mana", {}); s.maxmana = m.get("max", 100); s.maxhp = CFG["player"]["hp"]
        for sid in getattr(s, "skills", []):
            passive = CFG.get("skills", {}).get(sid, {})
            if passive.get("type") == "max_mana": s.maxmana += float(passive.get("amount", 0))
            if passive.get("type") == "max_hp": s.maxhp += float(passive.get("amount", 0))
        if hasattr(s, "hp"): s.hp = min(s.hp, s.maxhp)
        if full: s.mana, s.mana_t, s.mana_flash = min(m.get("start", s.maxmana), s.maxmana), 0, 0
        else: s.mana = min(s.mana, s.maxmana)
    @in_char
    def start_attack(s, i, fx=None):
        wid = s.slots[i]
        if not wid or wid not in CFG["weapons"]: return   # у героя нет оружия (маг/инженер) — удара не будет
        s.last_weapon = wid; steps = CFG["weapons"][wid]["combo"]; sl, stp, left = s.combo
        n = (stp + 1) % len(steps) if sl == wid and left > 0 else 0; st = steps[n]
        s.buf["a1" if i == 0 else "a2"] = 0; cost = weapon.mana_cost(wid, st)
        for sid in s.skills:
            passive = CFG.get("skills", {}).get(sid, {})
            if passive.get("type") == "mana_cost_reduction" and wid in passive.get("weapons", []):
                cost *= max(0.0, 1.0 - float(passive.get("amount", 0)))
        if s.mana < cost: s.mana_flash = .35; return   # не хватает маны — удар не начинается, полоска мигает
        s.mana -= cost; s.mana_t = CFG["player"].get("mana", {}).get("regen_delay", .9)
        invisibility.on_attack(s, fx)   # атака из невидимости сбрасывает эффект
        s.atk = dict(w=wid, n=n, step=st, t=0.0, wu=st["windup"], ac=st["active"], rec=st["recovery"], fired=False, hit=set())
        s.state = "attack"
    def strike(s, mobs, fx):
        a = s.atk; st = a["step"]; rw, rh = st["reach"]
        s.hitbox = pg.Rect(int(s.x + s.w if s.face > 0 else s.x - rw), int(s.cy - rh / 2), rw, rh)
        for m in mobs:
            if id(m) not in a["hit"] and (m.collides_rect(s.hitbox) if hasattr(m, "collides_rect") else s.hitbox.colliderect(m.rect)):
                a["hit"].add(id(m)); m.hurt(st["damage"] * s.dmg_mult(), s.face * st["knockback"], fx)
                s.mana = min(s.maxmana, s.mana + weapon.mana_hit(a["w"], st))   # попадание возвращает ману
    def fire(s, projs, st):
        pr = st["projectile"]; o = pr if isinstance(pr, dict) else {}
        hx, hy = s.hand("shoot"); ang = 0 if s.face > 0 else math.pi
        if s.aim: ang = math.atan2(s.aim[1] - hy, s.aim[0] - hx)   # стреляем в курсор
        volley(projs, pr, hx + math.cos(ang) * 14, hy + math.sin(ang) * 14, ang,
               st["damage"] * s.dmg_mult(), True, o.get("count", 1), o.get("spread", 0))
    @in_char
    def swap_skill(s, direction=1):
        if s.channel: return   # пока колдуем удерживаемое заклинание, книгу не листаем
        if s.hold: spells.hold_stop(s, None, "swap")   # смена навыка отпускает поток (запас начнёт восстанавливаться)
        active_skills = [sid for sid in s.skills if CFG.get("skills", {}).get(sid, {}).get("category", "active") == "active"]
        if not active_skills: return
        s.skill_index = (s.skill_index + direction) % len(active_skills)
        s.skill_notice = 1.0
    @in_char
    def swap_ammo(s, i, direction=1):
        """Листает вид снаряда арбалета i (0 — ЛКМ, 1 — ПКМ). У героев без арбалетов ничего не делает."""
        crossbow.swap(s, i, direction)
    @in_char
    def use_skill(s, mobs, projs, fx):
        """Использует текущий активный навык/заклинание. Эффекты — реестр @spell в spells.py."""
        spells.cast(s, mobs, projs, fx)

    def ledge(s, g):
        c = int((s.x + s.w + 2) // T) if s.wall > 0 else int((s.x - 2) // T); hr = int((s.y + 6) // T)
        if tile(g, c, hr) in "#D" and tile(g, c, hr - 1) not in "#D" and (s.y + 6) - hr * T < 16:
            nx, ny = c * T + (T - s.w) / 2, hr * T - s.h
            if free(g, pg.Rect(int(nx), int(ny), s.w, s.h)):
                s.x, s.y, s.vy, s.vx, s.lock = nx, ny, 0, s.face * 20, .25
    GRAB_KEYS = (pg.K_a, pg.K_d, pg.K_w, pg.K_s, pg.K_LEFT, pg.K_RIGHT, pg.K_UP, pg.K_DOWN, pg.K_SPACE)
    def update_grab(s, dt, k):
        """Игрок в руке босса: стоит на месте (позицию задаёт рука), ничего не может. Каждое НОВОЕ нажатие
        клавиши движения/прыжка сокращает удержание на grab['struggle'] секунд — можно вырваться."""
        g = s.grab; cur = tuple(bool(k[key]) for key in s.GRAB_KEYS); prev = g.get("prev") or (False,) * len(cur)
        g["t"] -= sum(1 for a, b in zip(cur, prev) if a and not b) * g.get("struggle", .18); g["prev"] = cur
        for b in s.buf: s.buf[b] = 0
        s.vx = s.vy = 0.0; s.atk = None; s.skill_cast = None; s.hitbox = None; s.hp_regen_timer = 0.0
        s.stun = max(s.stun, .1)      # поза «hurt»
        if s.state in ("attack", "ladder", "roll"): s.state = "move"
    @in_char
    def update(s, dt, k, g, mobs, projs, fx):
        p = CFG["player"]; s.hitbox = None
        for b in s.buf: s.buf[b] = max(0, s.buf[b] - dt)
        s.inv -= dt; s.lock -= dt; s.drop_t -= dt; s.mana_t -= dt; s.mana_flash -= dt
        s.skill_notice = max(0.0, s.skill_notice - dt)
        invisibility.tick(s, dt, fx)   # время невидимости тает; кончилось — эффект снимается
        if s.skill_cast:
            sid, elapsed, duration = s.skill_cast
            elapsed += dt
            s.skill_cast = (sid, elapsed, duration) if elapsed < duration else None
        s.shield_time = max(0.0, s.shield_time - dt)
        if s.shield_time <= 0: s.shield_hp = 0.0
        else: s.shield_face = s.face  # ориентация защиты синхронизирована с игроком
        for skill_id in s.skill_cooldowns: s.skill_cooldowns[skill_id] = max(0.0, s.skill_cooldowns[skill_id] - dt)
        if s.grab:
            if s.channel: spells.channel_stop(s, fx, "grab")
            if s.hold: spells.hold_stop(s, fx, "grab")
            s.update_grab(dt, k); return
        # Ввод движения считаем заранее: он нужен и удерживаемым заклинаниям (прерывают каст), и самому движению ниже.
        d = (k[pg.K_d] or k[pg.K_RIGHT]) - (k[pg.K_a] or k[pg.K_LEFT])
        up, dn = k[pg.K_w] or k[pg.K_UP], k[pg.K_s] or k[pg.K_DOWN]
        s.move_input = bool(d or dn)
        if hasattr(k, "skill"): s.skill_held = bool(k.skill)   # сетевой ввод несёт «клавиша навыка зажата»
        if s.channel: spells.channel_update(s, dt, d, dn, mobs, projs, fx)
        spells.hold_update(s, dt, mobs, projs, fx)   # потоки: восстановление запаса, расход запаса/маны, эффект зажатого потока
        if s.ground: s.air_jumps = 0
        if s.buf.get("skill", 0) > 0:
            s.buf["skill"] = 0
            s.use_skill(mobs, projs, fx)
        # Заклинатель (spellcaster — маг/инженер) не использует оружие: ЛКМ кастует текущее умение, ПКМ не нужна.
        # Кастуем только когда заклинание готово — иначе зажатая ЛКМ спамила бы сообщениями.
        if CFG.get("character", {}).get("spellcaster"):
            if s.buf.get("a1", 0) > 0 and spells.ready(s):
                s.buf["a1"] = 0
                s.use_skill(mobs, projs, fx)
            s.buf["a2"] = 0
        # Арбалетчик (crossbows — Тень): ЛКМ стреляет первым арбалетом, ПКМ — вторым, у каждого своя перезарядка; стрелять можно на бегу и в прыжке.
        # Нажатие, пришедшее раньше конца перезарядки, ждёт в буфере; не хватило маны — выстрела нет, полоска маны мигает.
        # «Свежее» нажатие (в этом кадре) или зажатая кнопка — буфер ввода только что обновлён и ещё полный (минус кадр): так отличаем зажатую ЛКМ/ПКМ
        # от одиночного клика, чей буфер постепенно тает. Зажатая кнопка арбалета подтягивает гарпун ближе, Пробел отцепляет гарпуны.
        if crossbow.enabled():
            crossbow.tick(s, dt)
            full = p["buffer"] - 1.5 * dt
            if s.buf.get("jump", 0) > full: crossbow.release_all(s)   # прыжок при этом работает как обычно (скорость на верёвке сохраняется)
            if s.state == "move" and s.stun <= 0:
                for i, key in enumerate(crossbow.KEYS):
                    s.xb_held[i] = s.buf.get(key, 0) > full
                    if s.buf.get(key, 0) > 0:
                        res = crossbow.trigger(s, i, projs, fx)
                        if res != "cd": s.buf[key] = 0
                    else: s.xb_lock[i] = False   # кнопку отпустили — новый гарпун можно выпустить
            else:   # перекат/лестница/оглушение: стрелять нельзя, нажатие не копим
                for key in crossbow.KEYS: s.buf[key] = 0
                s.xb_held = [False] * crossbow.SIDES
                if s.state in ("roll", "ladder"): crossbow.release_all(s)
            crossbow.hooks_update(s, dt, g, mobs, fx)
        # Регенерация здоровья: начинается после hp_regen_delay секунд без полученного урона.
        s.hp_regen_timer += dt
        hp_regen_delay = max(0.0, float(p.get("hp_regen_delay", 5.0)))
        hp_regen_rate = max(0.0, float(p.get("hp_regen", 5.0)))
        if s.hp_regen_timer >= hp_regen_delay and s.hp < s.maxhp and s.hp > 0 and hp_regen_rate > 0:
            s.hp = min(s.maxhp, s.hp + hp_regen_rate * dt)
        if s.mana_t <= 0 and s.mana < s.maxmana:
            regen_mult = s.passive_mult("mana_regen")
            s.mana = min(s.maxmana, s.mana + p.get("mana", {}).get("regen", 14) * regen_mult * dt)   # восстановление маны
        sl, stp, left = s.combo; s.combo = (sl, stp, left - dt)
        s.coy = p["coyote"] if s.ground else s.coy - dt
        held = up or k[pg.K_SPACE]
        c0, r0 = int(s.cx // T), int(s.cy // T); here = tile(g, c0, r0)
        below = tile(g, c0, int((s.y + s.h + 1) // T)); st = s.state
        # ПЕРЕКАТ (отменяет восстановление атаки, неуязвимость, низкий хитбокс)
        if s.buf["roll"] and s.coy > 0 and (st == "move" or (st == "attack" and s.atk["t"] >= s.atk["wu"])):
            s.buf["roll"] = 0; s.state = st = "roll"; s.atk = None; s.st = p["roll_time"]
            s.face = d or s.face; s.inv = max(s.inv, p["roll_inv"]); s.y += s.h - p["roll_h"]; s.h = p["roll_h"]
        if st == "roll":
            s.st -= dt; s.vx = s.face * p["roll_speed"]
            if s.st <= 0 and s.can_stand(g): s.y -= s.H0 - s.h; s.h = s.H0; s.state = "move"
        elif st == "ladder":
            s.vx = 0; s.vy = (dn - up) * p["ladder_speed"]; s.x += (c0 * T + T / 2 - s.cx) * min(1, dt * 20)
            if here != "H" or (s.ground and dn and below != "H"): s.state = "move"
            if s.buf["jump"]: s.buf["jump"] = 0; s.state = "move"; s.vy = -p["jump"] * .6; s.lock = .2; s.vx = d * s.speed()
        elif st == "attack":
            a = s.atk; a["t"] += dt; step = a["step"]; end = a["wu"] + a["ac"]
            if a["t"] >= a["wu"]:
                if "projectile" in step:
                    if not a["fired"]: a["fired"] = True; s.fire(projs, step)
                elif a["t"] < end: s.strike(mobs, fx)
            s.vx = s.face * step["lunge"] if a["wu"] <= a["t"] < end else approach(s.vx, 0, p["friction"] * dt)
            if a["t"] >= end + a["rec"] or (a["t"] >= end and s.buf["jump"] and s.coy > 0):
                s.combo = (a["w"], a["n"], p["combo_window"]); s.state = "move"; s.atk = None
        else:
            if s.stun > 0: s.stun -= dt
            elif crossbow.swinging(s):   # висим на верёвке в воздухе: A/D раскачивают (crossbow.rope_step), обычный разгон/торможение выключены
                if d: s.face = d
            else:
                acc = (p["accel"] if d else p["friction"]) if s.ground else (p["air_accel"] if d else p["air_friction"])
                s.vx = approach(s.vx, d * s.speed(), acc * dt)
                if d: s.face = d
            if s.lock <= 0 and ((up and here == "H") or (dn and (here == "H" or below == "H"))):
                s.state = "ladder"; s.vy = 0; s.buf["jump"] = 0
            elif s.buf["jump"] and (s.coy > 0 or (s.air_jumps < 1 and any(CFG.get("skills", {}).get(sid, {}).get("type") == "double_jump" for sid in s.skills))):
                if dn and below == "=" and s.coy > 0: s.drop_t = .25; s.y += 2
                else:
                    s.vy = -p["jump"]
                    if s.coy <= 0: s.air_jumps += 1
                s.buf["jump"] = 0; s.coy = 0
            elif s.buf["a1"]: s.face = s.facing(d); s.start_attack(0, fx)
            elif s.buf["a2"]: s.face = s.facing(d); s.start_attack(1, fx)
            if s.vy < 0 and not held: s.vy = max(s.vy, -p["jump"] * p["jump_cut"])
        if crossbow.enabled() and s.aim and s.state == "move" and s.stun <= 0:
            s.face = sign(s.aim[0] - s.cx) or s.face   # арбалеты в руках всегда смотрят в курсор — герой поворачивается к нему (бег задом — стрейф)
        if s.state != "ladder":
            s.vy = min(s.vy + p["gravity"] * (p["fall_mult"] if s.vy > 0 else 1) * dt, p["max_fall"])
        if crossbow.enabled(): crossbow.rope_step(s, dt, d)   # гарпуны: подтягивание, раскачивание, ограничение длины верёвки
        s.move(g, dt, drop=s.drop_t > 0)
        if p.get("ledge", True) and s.state == "move" and not s.ground and s.wall and s.wall == d and s.vy > -80 and s.lock <= 0:
            s.ledge(g)

def s_lock(): return CFG["maps"].get("lock", True)

def award_xp(pl, amount, fx):
    """Начислить опыт игроку pl. Возвращает [(новый уровень, id открытого навыка или None), ...].
    Общая функция для одиночной игры и мультиплеера (там опыт получает каждый игрок)."""
    with use_char(pl.char_id):
        amount = max(0, int(amount))
        pl.xp += amount
        fx.text(f"+{amount} опыта", pl.cx, pl.y - 28)
        ups = []
        while pl.xp >= pl.xp_next:
            pl.xp -= pl.xp_next
            pl.level += 1
            pl.xp_next = int(100 * (pl.level ** 1.35))
            defs = CFG.get("skills", {})
            slots = CFG.get("skill_tree", {}).get("slots", [])
            # При повышении уровня автоматически открывается следующий навык по порядку.
            unlocked_slot = next((slot for slot in slots
                                  if slot.get("skill") in defs
                                  and int(slot.get("unlock_level", 999)) <= pl.level
                                  and slot.get("skill") not in pl.skills), None)
            sid = None
            if unlocked_slot:
                sid = unlocked_slot["skill"]
                pl.skills.append(sid)
                pl.skill_cooldowns.setdefault(sid, 0.0)
            ups.append((pl.level, sid))
            pl.refresh_mana()
        return ups

def set_app_icon():
    """Иконка окна и панели задач из assets/app/icon.png (заменили файл, перезапустили игру — пересборка не нужна)."""
    try: pg.display.set_icon(pg.image.load(str(ASSETS / "app" / "icon.png")))
    except Exception as e: print("иконка окна не загружена:", e)

class Game:
    show_world = False   # M: карта мира открыта (игра на паузе)
    Player = Player       # мультиплеер создаёт игроков через этот класс
    zoom = CAMERA_ZOOM
    award_xp = staticmethod(award_xp)
    def __init__(s):
        pg.init(); set_app_icon(); pg.display.set_caption("DEAD ROOMS"); s.scr = pg.display.set_mode((W, H), pg.SCALED | (pg.FULLSCREEN if SETTINGS.get("fullscreen", True) else 0)); s.debug = False; s.cam = [0, 0]; s.view = pg.Surface((MW, MH))
        s.font = pg.font.SysFont("arial,dejavusans,freesans", 16, bold=True); s.big = pg.font.SysFont("arial,dejavusans,freesans", 44, bold=True)
        s.small = pg.font.SysFont("arial,dejavusans,freesans", 11, bold=True); s.grid = False
        s.show_world = False; s.controls_open = False; s.waiting_for_bind = None; s.hud_edit = False; s.hud_drag = None; s.hud_selected = "player"; s.veil = pg.Surface((W, VIEW_H), pg.SRCALPHA); s.veil.fill((6, 6, 12, 225))
        # Мультиплеер (multiplayer.py): s.net — сессия хоста или клиента, None — одиночная игра.
        s.net = None; s.mp_status = ""; s.mp_focus = None; s.mp_finder = None
        s.dev = devtools.DevMenu(s)   # F6: меню разработчика (опыт/здоровье/мана, тренировочный манекен) — devtools.py
        s.mp_name = str(SETTINGS.get("player_name") or mp.default_name())[:16]; s.mp_ip = str(SETTINGS.get("mp_last_ip", ""))
        s.clock = pg.time.Clock(); s.new_game()
        # Стартовое меню; после Esc игровой мир сохраняется и ставится на паузу.
        s.level_menu = False; s.level_choices = []; s.level_menu_level = 1; s.skill_unlock_anim = None
        s.menu_mode = "start"  # start | pause | None
        s.menu_selection = 0
        s.menu_edit = False
        s.menu_drag = None
        s.menu_selected = "new"
        # Ресурсы меню загружаются из assets рядом с исходниками/EXE.
        # Для EXE после сборки редактируйте dist/assets/menu/* — внешние ресурсы имеют приоритет.
        menu_assets = ASSETS / "menu"
        def load_menu_image(filename):
            try:
                path = menu_assets / filename
                if path.is_file():
                    return pg.image.load(str(path)).convert_alpha()
            except (pg.error, OSError):
                pass
            return None
        s.menu_background = load_menu_image("background.png")
        s.menu_button = load_menu_image("button.png")
        s.menu_button_selected = load_menu_image("button_selected.png")
        s.menu_cursor = load_menu_image("cursor.png")
        # Отдельная полупрозрачная вуаль: не перекрывает пользовательский фон почти полностью.
        s.menu_veil = pg.Surface((W, VIEW_H), pg.SRCALPHA)
        s.menu_veil.fill((6, 6, 12, 72))
        pg.mouse.set_visible(False if s.menu_cursor is not None or SETTINGS.get("mouse_aim", True) else True)
    def new_game(s, loop=0, character=None):
        if loop == 0:
            if character is not None or CHAR["id"] is None:
                apply_character(character if character is not None else SETTINGS.get("last_character")); clear_cache()
            s.pl = Player()
        else: s.pl.hp = min(s.pl.maxhp, s.pl.hp + 30); s.pl.refresh_mana(True)
        s.camp = Campaign(loop); s.room = None; s.done = False; s.fx = FX(); s.projs = []; s.warn_t = 0
        s.warn(check())
        if CFG["maps"].get("print_world", True): print(world_text())
        first = s.camp.first
        if first is None: print("нет ни одной карты в data/maps/"); pg.quit(); sys.exit()
        s.go(first, None)
    def warn(s, msgs):
        """Ошибки в картах — в консоль и на экран (держатся 8 секунд)."""
        for m in msgs: print("[карты]", m)
        s.warnings, s.warn_until = msgs[:8], pg.time.get_ticks() + 8000
    def go(s, mid, via):
        """Перейти на карту mid. via — запись легенды выхода, через который ушли (или None)."""
        pl, camp = s.pl, s.camp; frm = s.room.id if s.room else None
        if frm and mid != frm: camp.came_from[mid] = frm
        r = s.room = camp.get(mid); r.visited = True; s.projs = []; r.corpses = []
        rect, ladder = r.arrival(frm, via, camp)
        s.place(rect, ladder); s.respawn = (rect, ladder); s.armed = False
        if not r.spawned:
            r.spawn()
            if r.cleared and s.camp.order and r.id == s.camp.order[-1] and not getattr(r, "boss_spawned", False):
                r.cleared = False; s.clear(r)
    def place(s, rect, ladder):
        pl = s.pl
        if pl.h != pl.H0: pl.y -= pl.H0 - pl.h; pl.h = pl.H0
        pl.atk = None; pl.grab = None; pl.state = "ladder" if ladder else "move"
        crossbow.release_all(pl)   # гарпуны остались в прошлой комнате
        pl.x = max(0, min((s.room.width_px if s.room else MW) - pl.w, rect.centerx - pl.w / 2)); pl.y = rect.bottom - pl.h; pl.vx = pl.vy = 0
    def take_exit(s, z):
        r = s.room; target = s.camp.resolve(r.id, z["entry"]["exit"])
        if target == END: s.done = True; return
        if target is None:
            if pg.time.get_ticks() > s.warn_t: s.fx.text(f"выход '{z['char']}' никуда не ведёт", s.cam[0] + W / 2, s.cam[1] + 80); s.warn_t = pg.time.get_ticks() + 1500
            return
        s.go(target, z["entry"])
    def clear(s, r):
        # На последней карте каждого круга после обычных мобов появляется босс.
        order = s.camp.order
        if order and r.id == order[-1] and not getattr(r, "boss_spawned", False):
            boss = spawn_boss(r, s.camp.scale(), 1)
            if boss:
                r.boss_spawned = True; r.mobs.append(boss); r.set_lock(True)
                s.fx.text("БОСС ПРИБЫЛ!", s.cam[0] + W / 2, s.cam[1] + 120)
                return
        r.cleared = True; r.set_lock(False); s.fx.text("Зачищено!", s.cam[0] + W / 2, s.cam[1] + 120)
        rw = r.d.get("reward")   # {"item": "random" | id оружия, "chance": 0.5} — выпадает у игрока
        if rw and random.random() < rw.get("chance", 1):
            wid = random_weapon() if rw.get("item", "random") == "random" else rw["item"]
            if wid in CFG["weapons"]: r.drops.append(Drop(s.pl.cx, s.pl.y + s.pl.h - 14, wid))
    def gain_xp(s, amount):
        for level, sid in award_xp(s.pl, amount, s.fx):
            s.level_menu = True
            s.level_menu_started = pg.time.get_ticks()
            s.level_menu_level = level
            if sid: s.skill_unlock_anim = {"skill": sid, "start": pg.time.get_ticks(), "duration": 1100}
            s.level_choices = []
        if s.level_menu:
            pg.mouse.set_visible(True)

    def choose_level_skill(s, sid):
        if sid not in CFG.get("skills", {}) or CFG["skills"][sid].get("category", "active") != "active": return
        pl = s.pl
        if sid not in pl.skills: pl.skills.append(sid)
        active_skills = [key for key in pl.skills if CFG.get("skills", {}).get(key, {}).get("category", "active") == "active"]
        pl.skill_index = active_skills.index(sid)
        pl.skill_cooldowns.setdefault(sid, 0.0)
        s.level_menu = False
        pg.mouse.set_visible(not SETTINGS.get("mouse_aim", True))
    def pickup(s, pl=None):
        pl = pl or s.pl
        with use_char(pl.char_id):   # у каждого героя свои правки оружия
            if CFG.get("character", {}).get("spellcaster"):   # маг не подбирает и не носит оружие
                s.fx.text("Маг не использует оружие", pl.cx, pl.y - 10); return
            if CFG.get("character", {}).get("crossbows"):     # у арбалетчика руки заняты арбалетами
                s.fx.text("Руки заняты арбалетами", pl.cx, pl.y - 10); return
            for dr in s.room.drops:
                if abs(dr.x - pl.cx) < 36 and abs(dr.y - pl.cy) < 50:
                    if not pl.can_use(dr.wid):   # оружие не из списка allowed_weapons персонажа
                        s.fx.text(CFG["weapons"][dr.wid]["name"] + ": не для этого героя", pl.cx, pl.y - 10); break
                    i = CFG["weapons"][dr.wid].get("slot", 1) - 1
                    pl.slots[i], dr.wid = dr.wid, pl.slots[i]; pl.combo = (None, 0, 0)
                    s.fx.text(CFG["weapons"][pl.slots[i]]["name"], pl.cx, pl.y - 10); break
    AMMO_ACTIONS = {"xb0_prev": (0, -1), "xb0_next": (0, 1), "xb1_prev": (1, -1), "xb1_next": (1, 1)}   # смена снаряда: (арбалет, направление)
    ACTIONS = ("jump", "roll", "a1", "a2", "skill", "next", "prev", "pickup") + tuple(AMMO_ACTIONS)
    def apply_action(s, pl, name):
        """Действие игрока pl: прыжок, перекат, атаки, навык, смена навыка, подобрать предмет."""
        if name in ("jump", "roll", "a1", "a2", "skill"): pl.press(name)
        elif name == "next": pl.swap_skill(1)
        elif name == "prev": pl.swap_skill(-1)
        elif name == "pickup": s.pickup(pl)
        elif name in s.AMMO_ACTIONS: pl.swap_ammo(*s.AMMO_ACTIONS[name])
    def act(s, name):
        """Действие своего игрока. В сетевой игре клиент отправляет его хосту."""
        if s.net:
            if s.net.in_game: s.net.local_action(name)
            return
        s.apply_action(s.pl, name)
    def overlay_open(s):
        """Открыто меню/карта/настройки — в сетевой игре свой персонаж в это время стоит на месте."""
        return s.menu_mode is not None or s.show_world or s.controls_open or s.level_menu or s.hud_edit or s.dev.open
    def net_leave(s, message="", menu="mp"):
        """Выйти из сетевой игры (или лобби) в меню мультиплеера; одиночный мир создаётся заново."""
        if s.net: s.net.close()
        s.net = None
        s.new_game(character=SETTINGS.get("last_character"))
        s.show_world = s.controls_open = s.level_menu = s.hud_edit = False
        if menu == "connect": mp.open_connect(s)
        else: mp.open_menu(s)
        s.mp_status = message
    def step(s, dt):
        mp.housekeeping(s)
        if s.net:   # сетевая игра: хост считает мир, клиент получает его от хоста
            s.net.update(dt); return
        fx, pl, r = s.fx, s.pl, s.room; sim = 0 if (fx.stop > 0 or s.show_world or s.controls_open or s.menu_mode is not None or s.level_menu or s.dev.open) else dt   # меню ставит игру на паузу
        fx.stop = max(0, fx.stop - dt); fx.shake = max(0, fx.shake - dt)
        for it in fx.items: it[4] -= dt
        fx.items = [it for it in fx.items if it[4] > 0]
        if pl.hp <= 0: return
        mpos = pg.mouse.get_pos(); pl.aim = (mpos[0] / CAMERA_ZOOM + s.cam[0], mpos[1] / CAMERA_ZOOM + s.cam[1]) if SETTINGS.get("mouse_aim", True) else None
        mb = pg.mouse.get_pressed()   # зажатая кнопка = непрерывные атаки / комбо
        if mb[0] and not s.dev.open: pl.press("a1")   # клики по меню разработчика — не атаки
        if mb[2] and not s.dev.open: pl.press("a2")
        pl.drops = r.drops   # телекинез дотягивается до предметов на полу текущей комнаты
        pl.skill_held = s.skill_held()   # удерживаемые заклинания (захват инженера) работают, пока клавиша зажата
        pl.update(sim, pg.key.get_pressed(), r.g, r.mobs, s.projs, fx); pl.update_anim(sim)
        w = SimpleNamespace(g=r.g, pl=pl, mobs=r.mobs, projs=s.projs, fx=fx)   # «мир» для мобов и пуль
        for m in r.mobs:
            m.update(sim, w)
            if m.d.get("contact") and (m.touches_rect(pl.rect) if hasattr(m, "touches_rect") else pl.rect.colliderect(m.rect)): pl.hit(m.d["contact"], m.cx, fx)
            xp = m.pop_xp() if hasattr(m, "pop_xp") else 0
            if xp: s.gain_xp(xp)          # опыт за уничтоженные руки босса
        for q in s.projs: q.update(sim, w)
        s.projs = [q for q in s.projs if not q.dead]
        for m in r.mobs:
            if m.hp <= 0:
                if not getattr(m, "xp_paid", False):
                    m.xp_paid = True
                    s.gain_xp(int(m.d.get("xp", 10)))
                fx.ring(m.cx, m.cy, 28); c = Corpse(m)
                if not c.dead: r.corpses.append(c)
        for c in r.corpses: c.update(sim)
        r.corpses = [c for c in r.corpses if not c.dead]
        r.mobs = [m for m in r.mobs if m.hp > 0]
        for m in r.mobs:   # упал за край карты — умер
            if m.y > r.height_px + 200 or m.y < -400 or m.x < -400 or m.x > r.width_px + 400: m.hp = 0
        if r.spawned and not r.cleared and not hostile(r.mobs): s.clear(r)   # манекен (F6) комнату не держит
        sc, sr = int(pl.cx // T), int((pl.y + pl.h - 2) // T)
        if tile(r.g, sc, sr) == "x": pl.hit(r.spike_damage(sc, sr), pl.cx, fx)
        # выходы: сработают, когда игрок отошёл от места появления и потом зашёл в клетку выхода
        z = r.exit_at(pl.cx, pl.cy)
        if not s.armed and not r.exit_touch(pl.rect):   # целиком вышел из проёма
            s.armed = True
            if hostile(r.mobs) and r.d.get("lock", s_lock()): r.set_lock(True)   # двери закрываются, пока есть мобы
        elif s.armed and z is not None: s.take_exit(z); return
        if pl.cx < 0 or pl.cx > r.width_px or pl.cy < 0 or pl.cy > r.height_px:   # за край текущей карты
            z = None if r.locked else (z or r.exit_near(pl.rect))
            if z: s.take_exit(z)
            if s.room is r and not s.done:   # выхода нет — пропасть: урон и назад к месту появления
                pl.hit(r.d.get("fall_damage", CFG["maps"].get("fall_damage", 15)), pl.cx, fx); s.place(*s.respawn)
    CONTROL_DEFAULTS = {"jump": "SPACE", "roll": "LSHIFT", "attack1": "J", "attack2": "L", "pickup": "E", "skill": "Q", "skill_next": "C", "skill_prev": "V",
                        "ammo1_prev": "1", "ammo1_next": "2", "ammo2_prev": "3", "ammo2_next": "4"}
    CONTROL_LABELS = {"jump": "Прыжок", "roll": "Уклонение", "attack1": "Атака 1 (клавиша)", "attack2": "Атака 2 (клавиша)", "pickup": "Подобрать предмет", "skill": "Использовать скилл", "skill_next": "Следующий скилл", "skill_prev": "Предыдущий скилл",
                      "ammo1_prev": "Арбалет ЛКМ: пред. снаряд", "ammo1_next": "Арбалет ЛКМ: след. снаряд", "ammo2_prev": "Арбалет ПКМ: пред. снаряд", "ammo2_next": "Арбалет ПКМ: след. снаряд"}
    def controls(s):
        cfg = SETTINGS.setdefault("controls", {})
        for action, keyname in s.CONTROL_DEFAULTS.items(): cfg.setdefault(action, keyname)
        return cfg
    def skill_held(s):
        """Зажата ли сейчас клавиша навыка (у мага — ещё и ЛКМ). Нужна удерживаемым заклинаниям (skills.json: "channel")."""
        if s.overlay_open(): return False
        try: down = pg.key.get_pressed()[pg.key.key_code(s.controls()["skill"])]
        except (ValueError, TypeError, KeyError, IndexError): down = False
        if not down and CFG.get("character", {}).get("spellcaster"): down = pg.mouse.get_pressed()[0]
        return bool(down)
    def key_name(s, key):
        try: return pg.key.name(pg.key.key_code(key))
        except (ValueError, TypeError): return str(key).lower()
    def save_settings(s):
        try: (DATA / "settings.json").write_text(__import__("json").dumps(SETTINGS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError as exc: print("Не удалось сохранить настройки:", exc)
    def key(s, k):
        if s.level_menu:
            # Навыки больше не выбираются вручную: уровень автоматически открывает следующий.
            if k in (pg.K_ESCAPE, pg.K_RETURN, pg.K_SPACE):
                s.level_menu = False
                s.skill_unlock_anim = None
                pg.mouse.set_visible(not SETTINGS.get("mouse_aim", True))
            return
        if s.menu_mode in ("select", "lobby"): char_menu.key(s, k); return
        if s.menu_mode in mp.MENU_MODES: mp.menu_key(s, k); return
        if s.menu_mode is not None:
            if k == pg.K_F3:
                s.menu_edit = not s.menu_edit
                s.menu_drag = None
                return
            if s.menu_edit:
                if k in (pg.K_ESCAPE, pg.K_F3):
                    s.menu_edit = False; s.menu_drag = None; return
                if k in (pg.K_EQUALS, pg.K_PLUS, pg.K_KP_PLUS, pg.K_MINUS, pg.K_KP_MINUS):
                    s.resize_menu_button(8 if k in (pg.K_EQUALS, pg.K_PLUS, pg.K_KP_PLUS) else -8)
                    s.save_settings(); return
                return
            # Кнопки главного меню и паузы выбираются только мышью.
            # Esc закрывает меню паузы и возвращает в забег; навигации стрелками/Enter нет.
            if k == pg.K_ESCAPE and s.menu_mode == "pause":
                s.menu_mode = None
                pg.mouse.set_visible(not SETTINGS.get("mouse_aim", True))
            return
        if s.hud_edit:
            if k == pg.K_F2 or k == pg.K_ESCAPE: s.hud_edit = False; s.hud_drag = None; return
            if k in (pg.K_EQUALS, pg.K_PLUS, pg.K_KP_PLUS, pg.K_MINUS, pg.K_KP_MINUS):
                cfg = hud.layout(); key = s.hud_selected
                if key in ("hp", "mana"):
                    cfg[key][2] = max(20, min(500, cfg[key][2] + (8 if k in (pg.K_EQUALS, pg.K_PLUS, pg.K_KP_PLUS) else -8)))
                    cfg[key][3] = max(4, min(50, cfg[key][3] + (2 if k in (pg.K_EQUALS, pg.K_PLUS, pg.K_KP_PLUS) else -2)))
                else: cfg[key][2] = max(16, min(128, cfg[key][2] + (4 if k in (pg.K_EQUALS, pg.K_PLUS, pg.K_KP_PLUS) else -4)))
                s.save_settings(); return
            return
        if s.controls_open:
            if s.waiting_for_bind:
                if k == pg.K_ESCAPE: s.waiting_for_bind = None; return
                action = s.waiting_for_bind; s.controls()[action] = pg.key.name(k).upper(); s.waiting_for_bind = None; s.save_settings(); return
            if k in (pg.K_ESCAPE, pg.K_F1): s.controls_open = False
            return
        if k == pg.K_F1: s.controls_open = True; return
        if k == pg.K_F2: s.hud_edit = True; return
        controls = s.controls()
        def pressed(action):
            try: return k == pg.key.key_code(controls[action])
            except (ValueError, TypeError): return False
        # Все основные действия читаются из настроек управления.
        for action, buf in (("jump", "jump"), ("roll", "roll"), ("attack1", "a1"), ("attack2", "a2")):
            if pressed(action): s.act(buf); return
        for action, ev in (("ammo1_prev", "xb0_prev"), ("ammo1_next", "xb0_next"), ("ammo2_prev", "xb1_prev"), ("ammo2_next", "xb1_next")):
            if pressed(action): s.act(ev); return   # смена снарядов арбалетов (Тень)
        if pressed("pickup"): s.act("pickup")
        elif pressed("skill"): s.act("skill")
        elif pressed("skill_next"): s.act("next")
        elif pressed("skill_prev"): s.act("prev")
        elif k == pg.K_F5:
            if s.net: s.fx.text("F5 не работает в сетевой игре", s.pl.cx, s.pl.y - 40)
            else: s.reload()
        elif k == pg.K_F4: s.grid = not s.grid
        elif k == pg.K_m: s.show_world = not s.show_world
        elif k == pg.K_F11: pg.display.toggle_fullscreen()
        elif k == pg.K_F3: s.debug = not s.debug
        elif k == pg.K_r:
            if s.net: s.net.restart()   # хост: новый забег, когда погибли все
            else: s.new_game()
        elif k == pg.K_RETURN and s.done:
            if s.net: s.net.next_loop()
            else: s.new_game(s.camp.loop + 1)
        elif k == pg.K_ESCAPE:
            s.menu_mode = "pause"; s.menu_selection = 0
    def menu_action(s, action):
        if action == "continue":
            s.menu_mode = None
            pg.mouse.set_visible(not SETTINGS.get("mouse_aim", True))
        elif action == "new":
            if s.net: s.net_leave(); s.menu_mode = "start"   # в сетевой игре кнопка = «покинуть игру»
            else: char_menu.open_select(s)   # перед забегом — выбор персонажа
        elif action == "multiplayer":
            mp.open_menu(s)
        elif action == "exit":
            if s.net: s.net.close()
            pg.quit(); sys.exit()
    MENU_BUTTONS = {"continue": "ПРОДОЛЖИТЬ", "new": "НОВАЯ ИГРА", "multiplayer": "МУЛЬТИПЛЕЕР", "exit": "ВЫХОД"}
    def menu_layout(s):
        """Отдельные координаты для главного меню и паузы; сохраняются в data/settings.json."""
        is_pause = s.menu_mode == "pause"
        setting_key = "menu_layout_pause" if is_pause else "menu_layout"
        cfg = SETTINGS.setdefault(setting_key, {})
        if is_pause:
            defaults = {
                "continue": [W // 2 - 150, VIEW_H // 2 - 70, 300, 44],
                "new": [W // 2 - 150, VIEW_H // 2 - 12, 300, 44],
                "exit": [W // 2 - 150, VIEW_H // 2 + 46, 300, 44],
            }
        else:
            # Запрошенные координаты главного меню: x, y, width, height.
            defaults = {
                "new": [684, 291, 268, 36],
                "multiplayer": [684, 337, 268, 36],
                "exit": [787, 480, 172, 28],
            }
        for name, rect in defaults.items():
            cfg.setdefault(name, rect[:])
            if not isinstance(cfg[name], list) or len(cfg[name]) != 4:
                cfg[name] = rect[:]
            cfg[name] = [int(v) for v in cfg[name]]
            cfg[name][0] = max(0, min(W - 1, cfg[name][0]))
            cfg[name][1] = max(0, min(VIEW_H - 1, cfg[name][1]))
            cfg[name][2] = max(100, min(700, cfg[name][2]))
            cfg[name][3] = max(28, min(120, cfg[name][3]))
            cfg[name][0] = min(cfg[name][0], W - cfg[name][2])
            cfg[name][1] = min(cfg[name][1], VIEW_H - cfg[name][3])
        return cfg
    def resize_menu_button(s, delta):
        cfg = s.menu_layout(); key = s.menu_selected
        if key not in cfg: return
        a = cfg[key]
        nw, nh = max(100, min(700, a[2] + delta)), max(28, min(120, a[3] + round(delta * 0.22)))
        cx, cy = a[0] + a[2] // 2, a[1] + a[3] // 2
        a[:] = [cx - nw // 2, cy - nh // 2, nw, nh]
    def menu_event(s, e):
        if s.menu_mode is None: return
        if s.menu_mode in ("select", "lobby"): char_menu.event(s, e); return
        if s.menu_mode in mp.MENU_MODES: mp.menu_event(s, e); return
        options = ["continue", "new", "exit"] if s.menu_mode == "pause" else ["new", "multiplayer", "exit"]
        cfg = s.menu_layout()
        if s.menu_edit:
            if e.type == pg.MOUSEBUTTONDOWN and e.button == 1:
                mx, my = e.pos
                for action in reversed(options):
                    rect = pg.Rect(cfg[action])
                    if rect.collidepoint(mx, my):
                        s.menu_selected = action
                        s.menu_drag = (action, mx - rect.x, my - rect.y)
                        return
            elif e.type == pg.MOUSEMOTION and s.menu_drag:
                action, dx, dy = s.menu_drag
                cfg[action][0] = max(0, min(W - cfg[action][2], e.pos[0] - dx))
                cfg[action][1] = max(0, min(VIEW_H - cfg[action][3], e.pos[1] - dy))
                s.save_settings()
            elif e.type == pg.MOUSEBUTTONUP and e.button == 1:
                s.menu_drag = None
            elif e.type == pg.MOUSEBUTTONDOWN and e.button in (4, 5):
                mx, my = e.pos
                # Совместимость со старыми событиями колеса мыши.
                for action in reversed(options):
                    if pg.Rect(cfg[action]).collidepoint(mx, my):
                        s.menu_selected = action; break
                s.resize_menu_button(8 if e.button == 4 else -8)
                s.save_settings()
            elif e.type == pg.MOUSEWHEEL:
                mx, my = pg.mouse.get_pos()
                for action in reversed(options):
                    if pg.Rect(cfg[action]).collidepoint(mx, my):
                        s.menu_selected = action; break
                if e.y:
                    s.resize_menu_button(8 if e.y > 0 else -8)
                    s.save_settings()
            return
        if e.type == pg.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            for action in options:
                if pg.Rect(cfg[action]).collidepoint(mx, my):
                    s.menu_action(action); return
    def draw_menu(s):
        if s.menu_mode in ("select", "lobby"): char_menu.draw(s); s.draw_cursor(); return
        if s.menu_mode in mp.MENU_MODES: mp.draw_menu(s); s.draw_cursor(); return
        if s.menu_mode == "start":
            if s.menu_background:
                s.scr.blit(pg.transform.smoothscale(s.menu_background, (W, VIEW_H)), (0, 0))
            else:
                s.scr.fill((8, 8, 17))
            s.scr.blit(s.menu_veil, (0, 0))
        else:
            s.scr.blit(s.menu_veil, (0, 0))
        # В стартовом меню и меню паузы не рисуем лишние текстовые заголовки.
        # Назначение экрана определяется фоном и набором кнопок.
        options = ([("НОВАЯ ИГРА", "new"), ("МУЛЬТИПЛЕЕР", "multiplayer"), ("ВЫХОД", "exit")] if s.menu_mode == "start"
                   else [("ПРОДОЛЖИТЬ", "continue"), ("ПОКИНУТЬ ИГРУ" if s.net else "НОВАЯ ИГРА", "new"), ("ВЫХОД", "exit")])
        cfg = s.menu_layout()
        mouse = pg.mouse.get_pos()
        for i, (label, action) in enumerate(options):
            rect = pg.Rect(cfg[action])
            hovered = rect.collidepoint(mouse)
            selected = False  # больше нет переключения кнопок с клавиатуры
            button_img = s.menu_button_selected if (hovered or (s.menu_edit and action == s.menu_selected)) else s.menu_button
            if button_img:
                s.scr.blit(pg.transform.smoothscale(button_img, rect.size), rect.topleft)
            else:
                col = (92, 76, 130) if hovered else (43, 40, 60)
                pg.draw.rect(s.scr, col, rect, border_radius=8)
                pg.draw.rect(s.scr, (180, 160, 230) if hovered else (95, 88, 120), rect, 2, border_radius=8)
            text = s.font.render(label, True, (250, 248, 255))
            s.scr.blit(text, text.get_rect(center=rect.center))
            if s.menu_edit:
                color = (255, 210, 80) if action == s.menu_selected else (110, 220, 255)
                pg.draw.rect(s.scr, color, rect, 2)
                size_label = s.small.render(f"{action}: {rect.w}x{rect.h} ({rect.x},{rect.y})", True, color)
                s.scr.blit(size_label, (rect.x, max(0, rect.y - 16)))
        if s.menu_edit:
            hint = "РЕДАКТОР КНОПОК: перетаскивай мышью · колесо или +/- — размер · F3/Esc — готово"
            ht = s.small.render(hint, True, (255, 225, 135))
            s.scr.blit(ht, ht.get_rect(center=(W // 2, VIEW_H - 28)))
        s.draw_cursor()
    def draw_cursor(s):
        if s.menu_cursor is not None:
            mx, my = pg.mouse.get_pos()
            cursor = s.menu_cursor
            max_size = 64
            if cursor.get_width() > max_size or cursor.get_height() > max_size:
                scale = min(max_size / cursor.get_width(), max_size / cursor.get_height())
                cursor = pg.transform.smoothscale(cursor, (max(1, int(cursor.get_width() * scale)), max(1, int(cursor.get_height() * scale))))
            s.scr.blit(cursor, (mx, my))
    def hud_event(s, e):
        if not s.hud_edit: return
        cfg = hud.layout()
        if e.type == pg.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            # Приоритет более мелких/поздних элементов, затем бары.
            for key in hud.edit_keys():
                a = cfg[key]; rect = hud.edit_rect(key, a)
                if rect.collidepoint(mx, my): s.hud_selected = key; s.hud_drag = (key, mx-rect.x, my-rect.y); return
        elif e.type == pg.MOUSEBUTTONUP and e.button == 1: s.hud_drag = None
        elif e.type == pg.MOUSEMOTION and s.hud_drag:
            key, dx, dy = s.hud_drag; a = cfg[key]; r = hud.edit_rect(key, a); sx = r.x - a[0]   # sx: показ сдвинут относительно записи (слот Q арбалетчика)
            a[0] = max(0, min(W-r.w, e.pos[0]-dx)) - sx; a[1] = max(0, min(VIEW_H-r.h, e.pos[1]-dy)); s.save_settings()
        elif e.type == pg.MOUSEBUTTONDOWN and e.button in (4, 5):
            key = s.hud_selected; a = cfg[key]; delta = 4 if e.button == 4 else -4
            if key in ("hp", "mana"): a[2] = max(20, min(500, a[2]+delta*2)); a[3] = max(4, min(50, a[3]+delta//2))
            else: a[2] = max(16, min(128, a[2]+delta))
            s.save_settings()
    def draw_hud_editor(s):
        s.txt("РЕДАКТОР HUD — перетаскивай элементы мышью | колесо или +/-: размер | F2/Esc: выход", 12, 10, (255, 230, 140), s.small)
        cfg = hud.layout()
        for key in hud.edit_keys():
            a = cfg[key]; rect = hud.edit_rect(key, a)
            pg.draw.rect(s.scr, (255, 220, 100) if key == s.hud_selected else (120, 180, 255), rect, 2)
            s.txt(key.upper(), rect.x, max(25, rect.y-14), (255, 255, 255), s.small)
    def controls_event(s, e):
        if not s.controls_open or e.type != pg.MOUSEBUTTONDOWN or e.button != 1 or s.waiting_for_bind: return
        mx, my = e.pos; y0 = 86
        actions = list(s.CONTROL_LABELS)
        for i, action in enumerate(actions):
            rect = pg.Rect(W // 2 - 220, y0 + i * 38, 440, 32)
            if rect.collidepoint(mx, my): s.waiting_for_bind = action; return
    def draw_controls(s):
        s.scr.blit(s.veil, (0, 0))
        title = s.big.render("УПРАВЛЕНИЕ", True, (240, 235, 255)); s.scr.blit(title, title.get_rect(center=(W // 2, 42)))
        cfg = s.controls()
        for i, (action, label) in enumerate(s.CONTROL_LABELS.items()):
            rect = pg.Rect(W // 2 - 220, 86 + i * 38, 440, 32)
            pg.draw.rect(s.scr, (58, 52, 78) if s.waiting_for_bind != action else (105, 75, 130), rect, border_radius=5)
            pg.draw.rect(s.scr, (130, 120, 165), rect, 1, border_radius=5)
            s.txt(label, rect.x + 10, rect.y + 7, (235, 235, 245), s.small)
            keytext = "НАЖМИ КЛАВИШУ…" if s.waiting_for_bind == action else str(cfg[action]).upper()
            tw = s.small.render(keytext, True, (255, 220, 130)); s.scr.blit(tw, (rect.right - tw.get_width() - 10, rect.y + 7))
        s.txt("Нажми на действие и затем нужную клавишу. Esc — отмена/выход.", W // 2 - 215, 86 + len(s.CONTROL_LABELS) * 38 + 8, (190, 190, 215), s.small)
        s.txt("Настройки сохраняются в data/settings.json", W // 2 - 150, VIEW_H - 28, (160, 220, 175), s.small)
    def reload(s):
        """F5: перечитать JSON и картинки, пересобрать карты; игрок остаётся на месте."""
        reload_data(); clear_cache(); pl = s.pl; x, y, st = pl.x, pl.y, pl.state; pl.refresh_mana()
        s.camp.reload(); s.warn(check()); s.fx.text("данные перезагружены", s.cam[0] + W / 2, s.cam[1] + 80)
        if CFG["maps"].get("print_world", True): print(world_text())
        if s.room.id not in CFG["map_defs"]: s.room = None; s.go(s.camp.first, None); return
        r = s.room = s.camp.get(s.room.id); r.visited = True
        if not r.spawned: r.spawn()
        pl.x, pl.y, pl.state = x, y, st; s.projs = []
        s.armed = not r.exit_touch(pl.rect)
        if s.armed and hostile(r.mobs) and r.d.get("lock", s_lock()): r.set_lock(True)
    def txt(s, t, x, y, col=(235, 235, 240), f=None):
        s.scr.blit((f or s.font).render(t, True, col), (x, y))
    def draw(s):
        v, r, pl = s.view, s.room, s.pl; v.blit(r.layer, (0, 0))
        light_t, light_dt = lighting.frame_time()
        lighting.draw_sources(v, r, light_t, light_dt)   # факелы, фонари, кристаллы — с живым пламенем и искрами
        for dr in r.drops:
            dr.draw(v)
            if abs(dr.x - pl.cx) < 36: v.blit(s.font.render("[E] " + CFG["weapons"][dr.wid]["name"], True, (255, 230, 120)), (dr.x - 60, dr.y - 34))
        for c in r.corpses: c.draw(v)
        for m in r.mobs: m.draw(v, s.debug)
        for q in s.projs: q.draw(v)
        if s.net and s.net.in_game: mp.draw_players(s, v)   # все игроки, имена, павшие союзники
        elif pl.inv <= 0 or int(pg.time.get_ticks() / 60) % 2:
            pl.draw(v)
        for m in r.mobs:
            if hasattr(m, "draw_front"): m.draw_front(v)      # рука, держащая игрока, поверх него
        if s.debug:
            # Зелёный — физический хитбокс персонажа, белый — активная атакующая зона.
            pg.draw.rect(v, (0, 255, 120), pl.rect, 2)
            if pl.hitbox: pg.draw.rect(v, (255, 255, 255), pl.hitbox, 2)
        if s.grid: s.draw_grid(v)
        for kind, x, y, data, t in s.fx.items:
            if kind == "t": v.blit(s.font.render(data, True, (255, 240, 160)), (x - 14, y - (0.7 - t) * 40))
            elif kind == "r": pg.draw.circle(v, (255, 200, 120), (int(x), int(y)), int(data * (1 - t / .25) + 4), 2)
            elif kind == "beam": _draw_beam(v, x, y, data[0], data[1], data[2], max(0.0, min(1.0, t / .22)))
            elif kind == "bolt": _draw_bolt(v, x, y, data, max(0.0, min(1.0, t / .3)))
            elif kind == "flash": _draw_flash(v, x, y, data[0], data[1], max(0.0, min(1.0, t / .25)))
        # Не сдвигаем готовый кадр относительно экрана: при таком shake
        # по краям появлялись чёрные полосы. Камера ограничивается картой ниже.
        # Небольшой отдалённый зум: видно больше уровня вокруг персонажа.
        src_w, src_h = int(W / CAMERA_ZOOM), int(VIEW_H / CAMERA_ZOOM)
        # Ограничиваем камеру границами ИМЕННО текущей карты, а не общей
        # служебной поверхности v (MW x MH). У края карты камера перестаёт
        # следовать за игроком, чтобы за границами локации не появлялась пустота.
        room_w, room_h = r.width_px, r.height_px
        cx = int(max(0, min(max(0, room_w - src_w), pl.cx - src_w / 2)))
        cy = int(max(0, min(max(0, room_h - src_h), pl.cy - src_h / 2)))
        s.cam = [cx, cy]
        s.scr.fill((10, 10, 16))
        crop_w, crop_h = min(src_w, room_w - cx), min(src_h, room_h - cy)
        viewport = v.subsurface(pg.Rect(cx, cy, max(1, crop_w), max(1, crop_h)))
        scaled_view = pg.transform.scale(viewport, (W, VIEW_H))
        s.scr.blit(scaled_view, (0, 0))
        # Темнота и мягкие пятна света поверх кадра (только на картах с темнотой или блоками света).
        lit = s.net.player_list() if s.net and s.net.in_game else [pl]
        lighting.apply(s.scr, r, s.cam, (max(1, crop_w), max(1, crop_h)), lit, r.mobs, s.projs, light_t)
        for m in r.mobs:
            if hasattr(m, "draw_overlay"): m.draw_overlay(s.scr, s.cam, CAMERA_ZOOM)   # таблички манекена поверх темноты
        order = s.camp.order   # прогресс: квадратик на каждую карту из order
        for i, mid in enumerate(order):
            rm = s.camp.maps.get(mid); rc = (W - 18 * len(order) - 8 + i * 18, 8, 14, 10)
            col = (55, 55, 70) if not rm or not rm.visited else ((80, 170, 100) if rm.cleared else (190, 80, 80))
            pg.draw.rect(s.scr, col, rc)
            if rm is r: pg.draw.rect(s.scr, (255, 255, 255), rc, 2)
        label = r.name + (f"  [{r.pos[0]}, {r.pos[1]}]" if r.pos else "")   # имя карты и её координата в сетке мира
        s.txt(label, W - 18 * len(order) - 16 - s.font.size(label)[0], 4, (220, 220, 235))
        if pg.time.get_ticks() < s.warn_until:
            for i, m in enumerate(s.warnings): s.txt("! " + m, 10, 8 + i * 20, (255, 140, 120))
        with use_char(pl.char_id):
            hud.draw(s.scr, pl, s.small)   # иконки персонажа и оружия, под персонажем полоски HP и маны (поверх игры)
        hud.draw_boss_bar(s.scr, r.mobs, s.font)
        if s.camp.loop: s.txt(f"Круг {s.camp.loop + 1}", W - 90, VIEW_H - 24, (180, 180, 200))
        if s.net and s.net.in_game: mp.draw_overlay(s)   # союзники, сообщения о смерти/конце круга, уровень
        elif pl.hp <= 0: s.txt("ТЫ УМЕР — R: заново", W // 2 - 220, 200, (255, 90, 90), s.big)
        elif s.done: s.txt("ВСЕ КАРТЫ ПРОЙДЕНЫ — Enter: ещё круг", W // 2 - 380, 200, (120, 255, 150), s.big)
        if s.level_menu: s.draw_level_menu()
        if s.show_world: s.draw_world()
        if s.controls_open: s.draw_controls()
        if s.hud_edit: s.draw_hud_editor()
        if s.dev.open: s.dev.draw(s.scr)
        if s.menu_mode is not None: s.draw_menu()
        if pl.aim and s.menu_mode is None and not s.dev.open:   # прицел
            mx, my = int((pl.aim[0] - s.cam[0]) * CAMERA_ZOOM), int((pl.aim[1] - s.cam[1]) * CAMERA_ZOOM); col = (255, 255, 255); pg.draw.circle(s.scr, col, (mx, my), 10, 1); pg.draw.circle(s.scr, col, (mx, my), 1)
            for a in ((-17, 0, -7, 0), (7, 0, 17, 0), (0, -17, 0, -7), (0, 7, 0, 17)): pg.draw.line(s.scr, col, (mx + a[0], my + a[1]), (mx + a[2], my + a[3]))
        pg.display.flip()
    def draw_level_menu(s):
        # Меню повышения уровня автоматически закрывается через 4 секунды.
        if pg.time.get_ticks() - getattr(s, "level_menu_started", pg.time.get_ticks()) >= 4000:
            s.level_menu = False
            s.skill_unlock_anim = None
            pg.mouse.set_visible(not SETTINGS.get("mouse_aim", True))
            return
        # Визуальное оформление меню навыков полностью настраивается через assets/skill_menu.json.
        ui = CFG.get("skill_menu", {})
        def color(key, default):
            value = ui.get(key, default)
            try:
                return tuple(max(0, min(255, int(c))) for c in value[:3])
            except (TypeError, ValueError):
                return default
        def image(path_value, size=None):
            if not path_value:
                return None
            if not hasattr(s, "skill_menu_asset_cache"):
                s.skill_menu_asset_cache = {}
            path = ASSETS / str(path_value)
            cache_key = (str(path), tuple(size) if size else None)
            if cache_key not in s.skill_menu_asset_cache:
                try:
                    surf = pg.image.load(str(path)).convert_alpha()
                    if size:
                        surf = pg.transform.smoothscale(surf, size)
                    s.skill_menu_asset_cache[cache_key] = surf
                except (OSError, pg.error):
                    s.skill_menu_asset_cache[cache_key] = None
            return s.skill_menu_asset_cache[cache_key]
        bg_path = ui.get("background_image")
        bg = image(bg_path, (W, VIEW_H)) if bg_path else None
        if bg:
            s.scr.blit(bg, (0, 0))
        else:
            veil = pg.Surface((W, VIEW_H), pg.SRCALPHA)
            veil.fill((*color("overlay_color", (5, 5, 14)), max(0, min(255, int(ui.get("overlay_alpha", 242))))))
            s.scr.blit(veil, (0, 0))

        title_text = str(ui.get("title", "НОВЫЙ УРОВЕНЬ: {level}")).format(level=s.level_menu_level)
        title = s.big.render(title_text, True, color("title_color", (255, 220, 130)))
        s.scr.blit(title, title.get_rect(center=(int(ui.get("title_x", W // 2)), int(ui.get("title_y", 48)))))
        subtitle_text = str(ui.get("subtitle", "Дерево навыков — открываются по порядку. Выберите открытый навык."))
        if ui.get("show_subtitle", True) and subtitle_text:
            sub = s.font.render(subtitle_text, True, color("subtitle_color", (215, 215, 235)))
            s.scr.blit(sub, sub.get_rect(center=(int(ui.get("subtitle_x", W // 2)), int(ui.get("subtitle_y", 88)))))

        defs = CFG.get("skills", {})
        tree = CFG.get("skill_tree", {})
        slots = list(tree.get("slots", []))[:int(ui.get("max_slots", 8))]
        max_slots = max(1, int(ui.get("max_slots", 8)))
        while len(slots) < max_slots:
            slots.append({"skill": None, "unlock_level": 999})
        cols = max(1, int(ui.get("columns", tree.get("grid_columns", 4))))
        rows = max(1, int(ui.get("rows", tree.get("grid_rows", 2))))
        gap_x, gap_y = int(ui.get("gap_x", 14)), int(ui.get("gap_y", 16))
        cell_w = int(ui.get("cell_width", min(180, (W - 70 - gap_x * (cols - 1)) // cols)))
        cell_h = int(ui.get("cell_height", 150))
        total_w = cols * cell_w + (cols - 1) * gap_x
        ox = int(ui.get("grid_x", (W - total_w) // 2))
        oy = int(ui.get("grid_y", 125))
        radius = max(0, int(ui.get("corner_radius", 10)))
        border_width = max(0, int(ui.get("border_width", 3)))
        icon_size = max(1, int(ui.get("icon_size", 52)))
        icon_y = int(ui.get("icon_y", 42))
        name_y = int(ui.get("name_y", 82))
        status_y = int(ui.get("status_y", 106))
        show_names = bool(ui.get("show_skill_names", True))
        show_status = bool(ui.get("show_status", True))
        show_slot_numbers = bool(ui.get("show_slot_numbers", True))
        unlocked_bg = color("unlocked_bg", (35, 55, 50))
        locked_bg = color("locked_bg", (29, 29, 42))
        locked_border = color("locked_border", (95, 95, 115))
        name_unlocked = color("name_unlocked_color", (255, 240, 190))
        name_locked = color("name_locked_color", (145, 145, 165))
        status_unlocked = color("status_unlocked_color", (175, 220, 190))
        status_locked = color("status_locked_color", (125, 125, 145))
        slot_base = ui.get("slot_image")
        slot_unlocked = ui.get("slot_unlocked_image", slot_base)
        slot_locked = ui.get("slot_locked_image", slot_base)
        for i, slot in enumerate(slots):
            sid = slot.get("skill")
            d = defs.get(sid, {}) if sid else {}
            # Навык открыт только если он действительно добавлен персонажу.
            # Уровень сам по себе не снимает замки со всех предыдущих/будущих ячеек.
            # Анимация принадлежит только одному конкретному ID навыка,
            # который открывается прямо сейчас. Остальные ячейки не получают
            # ни fade, ни кадры/вспышку, даже если они уже разблокированы.
            anim = getattr(s, "skill_unlock_anim", None)
            is_animating_unlock = bool(sid and anim and anim.get("skill") == sid)
            unlocked = bool(sid and sid in defs and (sid in s.pl.skills or is_animating_unlock))
            col, row = i % cols, i // cols
            rect = pg.Rect(ox + col * (cell_w + gap_x), oy + row * (cell_h + gap_y), cell_w, cell_h)
            bg_col = unlocked_bg if unlocked else locked_bg
            border_col = tuple(d.get("color", [100, 210, 150])) if unlocked else locked_border
            texture = image(slot_unlocked if unlocked else slot_locked, (cell_w, cell_h))
            if texture:
                s.scr.blit(texture, rect)
                if ui.get("tint_slot_images", False):
                    tint = pg.Surface((cell_w, cell_h), pg.SRCALPHA)
                    tint.fill((*bg_col, 90))
                    s.scr.blit(tint, rect)
                if border_width:
                    pg.draw.rect(s.scr, border_col, rect, border_width, border_radius=radius)
            else:
                pg.draw.rect(s.scr, bg_col, rect, border_radius=radius)
                if border_width:
                    pg.draw.rect(s.scr, border_col, rect, border_width, border_radius=radius)

            icon_rel = (spells.icon_path(sid, d) if sid else d.get("icon")) if unlocked else slot.get("lock_icon", f"icons/locks/{sid}_lock.png" if sid else tree.get("lock_icon", "icons/skill_locked.png"))
            icon = image(icon_rel, (icon_size, icon_size))
            if icon:
                icon_rect = icon.get_rect(center=(rect.centerx, rect.y + icon_y))
                s.scr.blit(icon, icon_rect)
                if is_animating_unlock and anim is not None:
                    # Рисуем эффект строго внутри текущей ячейки открываемого навыка.
                    elapsed = pg.time.get_ticks() - anim["start"]
                    duration = max(1, int(anim.get("duration", tree.get("unlock_animation_duration", 1100))))
                    progress = min(1.0, max(0.0, elapsed / duration))
                    # Не открываем все навыки по уровню: только у открываемого сейчас
                    # поверх его иконки постепенно исчезает замок.
                    frame_paths = tree.get("unlock_animation_frames", [])
                    if frame_paths:
                        frame_index = min(len(frame_paths) - 1, int(progress * len(frame_paths)))
                        frame = image(frame_paths[frame_index], (icon_size, icon_size))
                        if frame:
                            s.scr.blit(frame, icon_rect)
                    else:
                        lock_path = slot.get("lock_icon", f"icons/locks/{sid}_lock.png" if sid else tree.get("lock_icon", "icons/skill_locked.png"))
                        lock_icon = image(lock_path, (icon_size, icon_size))
                        if lock_icon and progress < 1.0:
                            lock_icon.set_alpha(max(0, int(255 * (1 - progress))))
                            s.scr.blit(lock_icon, icon_rect)
                        # Вспышка открытия также настраивается ассетом.
                        flash_path = tree.get("unlock_flash_image")
                        if flash_path and progress < 1.0:
                            flash_img = image(flash_path, (icon_size, icon_size))
                            if flash_img:
                                flash_img.set_alpha(int(220 * (1 - progress)))
                                s.scr.blit(flash_img, icon_rect)
                    if progress >= 1.0:
                        s.skill_unlock_anim = None
            elif not unlocked and ui.get("fallback_lock_draw", True):
                pg.draw.arc(s.scr, (190, 190, 210), (rect.centerx-10, rect.y+15, 20, 22), 0, 3.14, 3)
                pg.draw.rect(s.scr, (190, 190, 210), (rect.centerx-13, rect.y+28, 26, 20), 2, border_radius=3)

            if show_names:
                name = (d.get("name", "Навык не задан" if not sid else sid) if unlocked
                        else str(ui.get("locked_name", "ЗАБЛОКИРОВАНО")))
                if unlocked and d.get("category") == "passive" and ui.get("mark_passive", True):
                    name = str(ui.get("passive_prefix", "[ПАССИВ] ")) + name
                txt = s.small.render(str(name), True, name_unlocked if unlocked else name_locked)
                s.scr.blit(txt, txt.get_rect(center=(rect.centerx, rect.y + name_y)))
            if show_status:
                level = int(slot.get("unlock_level", 999))
                status = (str(ui.get("unlocked_passive_status", "Пассив активен"))
                          if d.get("category") == "passive" and sid in s.pl.skills
                          else str(ui.get("unlocked_status", "Открыт" if sid in s.pl.skills else "Доступен"))) if unlocked else str(ui.get("locked_status_format", "Уровень {level}")).format(level=level)
                t2 = s.small.render(status, True, status_unlocked if unlocked else status_locked)
                s.scr.blit(t2, t2.get_rect(center=(rect.centerx, rect.y + status_y)))
            if unlocked and show_slot_numbers:
                s.txt(f"[{i+1}]", rect.x + 8, rect.bottom - int(ui.get("slot_number_bottom_offset", 23)),
                      color("slot_number_color", (225, 225, 240)), s.small)

        footer_text = str(ui.get("footer", "Активные навыки: Q — использовать, C/V — смена. Пассивные навыки включаются автоматически. Игра на паузе."))
        if ui.get("show_footer", True) and footer_text:
            footer = s.small.render(footer_text, True, color("footer_color", (210, 210, 225)))
            s.scr.blit(footer, footer.get_rect(center=(int(ui.get("footer_x", W // 2)), int(ui.get("footer_y", VIEW_H - 20)))))
    def draw_world(s):
        """M: сетка мира. Клетка = карта (её pos в data/maps/<id>.json), линия = переход между картами:
        серая — в обе стороны, оранжевая — только в одну. Красная клетка — карта не зачищена, зелёная — зачищена."""
        s.scr.blit(s.veil, (0, 0)); defs = CFG["map_defs"]; cells = {m: pos_of(m) for m in defs if pos_of(m)}
        s.txt("Карта мира (M — закрыть)     x → вправо, y ↓ вниз     [x, y] — поле pos в data/maps/<id>.json", 12, 8, (220, 220, 235))
        s.txt("белая рамка — вы здесь   красная — не зачищена   зелёная — зачищена   серая линия — переход в обе стороны   оранжевая — только в одну", 12, VIEW_H - 22, (170, 175, 200), s.small)
        if not cells: s.txt('ни у одной карты нет pos — впиши "pos": [x, y] в data/maps/<id>.json', 12, 40, (255, 160, 120)); return
        xs, ys = [p[0] for p in cells.values()], [p[1] for p in cells.values()]; nx, ny = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
        cw, ch = min(190, (W - 60) // nx), min(100, (VIEW_H - 90) // ny); ox, oy = (W - nx * cw) // 2, 40 + (VIEW_H - 40 - ny * ch) // 2
        links = world_links(); reveal = CFG["maps"].get("world", {}).get("reveal", "all")
        def seen(m): rm = s.camp.maps.get(m); return bool(rm and rm.visited)
        show = {m for m in cells if reveal == "all" or seen(m) or any(seen(b) for a, b in links if a == m) or any(seen(a) for a, b in links if b == m)}
        rc = {m: pg.Rect(ox + (cells[m][0] - min(xs)) * cw, oy + (cells[m][1] - min(ys)) * ch, cw - 16, ch - 16) for m in show}
        for a, b in links:
            if a in rc and b in rc and not ((b, a) in links and a > b):
                pg.draw.line(s.scr, (120, 120, 150) if two_way(a, b) else (255, 170, 70), rc[a].center, rc[b].center, 3)
        for m, rect in rc.items():
            rm = s.camp.maps.get(m); col = (45, 45, 62) if not (rm and rm.visited) else ((60, 130, 85) if rm.cleared else (150, 60, 60))
            pg.draw.rect(s.scr, col, rect, border_radius=6); pg.draw.rect(s.scr, (255, 255, 255) if m == s.room.id else (110, 110, 140), rect, 3 if m == s.room.id else 1, border_radius=6)
            s.scr.blit(s.font.render(defs[m].get("name", m), True, (240, 240, 250)), (rect.x + 8, rect.y + 6))
            s.scr.blit(s.small.render(f"{m}   [{cells[m][0]}, {cells[m][1]}]" + "", True, (200, 205, 225)), (rect.x + 8, rect.bottom - 18))
    def draw_grid(s, v):
        """F4: сетка с номерами клеток — удобно рисовать карту. Под курсором — столбец, строка и символ."""
        for c in range(COLS): pg.draw.line(v, (110, 110, 140), (c * T, 0), (c * T, VH))
        for r in range(ROWS): pg.draw.line(v, (110, 110, 140), (0, r * T), (W, r * T))
        for c in range(0, COLS, 2): v.blit(s.small.render(str(c), True, (255, 255, 120)), (c * T + 2, 2))
        for r in range(ROWS): v.blit(s.small.render(str(r), True, (255, 255, 120)), (2, r * T + 2))
        mx, my = pg.mouse.get_pos(); c, r = int(mx / CAMERA_ZOOM + s.cam[0]) // T, int(my / CAMERA_ZOOM + s.cam[1]) // T
        if 0 <= c < COLS and 0 <= r < ROWS:
            pg.draw.rect(v, (255, 255, 120), (c * T, r * T, T, T), 2)
            v.blit(s.font.render(f"столбец {c}, строка {r}: '{s.room.chars[r][c]}'", True, (255, 255, 120)), (int(mx / CAMERA_ZOOM + s.cam[0]) + 14, int(my / CAMERA_ZOOM + s.cam[1]) + 14))
    def run(s):
        while True:
            dt = min(s.clock.tick(60) / 1000, 1 / 30)
            # В меню используем курсор из assets; в забеге сохраняем обычное управление мышью.
            pg.mouse.set_visible(s.menu_mode is not None and s.menu_cursor is None or s.menu_mode is None and not SETTINGS.get("mouse_aim", True) or s.dev.open)
            for e in pg.event.get():
                if e.type == pg.QUIT:
                    if s.net: s.net.close()
                    return
                if e.type == pg.KEYDOWN and e.key == pg.K_F6 and not s.dev.open: s.dev.toggle(); continue   # F6: меню разработчика
                if s.dev.event(e): continue   # открытое меню разработчика забирает весь ввод
                if e.type == pg.KEYDOWN: s.key(e.key)
                if s.menu_mode is not None:
                    s.menu_event(e)
                elif s.hud_edit: s.hud_event(e)
                elif e.type == pg.MOUSEBUTTONDOWN and s.controls_open: s.controls_event(e)
                elif e.type == pg.MOUSEBUTTONDOWN and e.button in (1, 3): s.act("a1" if e.button == 1 else "a2")
            s.step(dt); s.draw()

if __name__ == "__main__":
    Game().run()
