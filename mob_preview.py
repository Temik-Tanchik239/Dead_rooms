"""Окно с мобом для редактора мобов (mob_editor.py): показывает любую анимацию моба и зоны его атак.

Кадры выбираются теми же функциями, что и в игре (anim.mob_frame / anim.find_anim), поэтому в окне всё выглядит так же,
как будет в игре: запасные анимации, растягивание кадров на фазу атаки, fps, зацикливание. Картинка рисуется через pygame
в память (без окна) и отдаётся в tkinter как PPM-данные — Pillow не нужен.

Preview.render(mob_id, mob, entry, t, opts) -> (ppm-байты, строка-описание). entry — запись из mob_data.preview_entries()
или {"kind": "frame", "path": "..."} (один кадр). t — секунды с начала показа. opts: zoom, hitbox, box, zone (индекс атаки
или None), player, flip.
"""
import os, math
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import pygame as pg
import anim
import mob_data as md

BG, GRID, GROUND = (28, 28, 38), (38, 38, 52), (110, 96, 80)
HOLD = 0.35          # сколько секунд показывать последний кадр, прежде чем начать заново
PLAYER_BOX = (20, 34)  # хитбокс героя по умолчанию (data/characters.json -> hitbox)


def _sign(x): return (x > 0) - (x < 0)


class Preview:
    def __init__(self, assets=None, size=(344, 300)):
        pg.display.init()
        if pg.display.get_surface() is None: pg.display.set_mode((1, 1))
        pg.font.init()
        self.size = size; self.frame_dt = 0.1; self.cycle = 1.0
        if assets is not None: anim.ASSETS = type(anim.ASSETS)(assets)     # те же картинки, что видит редактор
        self.invalidate()

    def invalidate(self):
        """Данные моба или файлы поменялись — сбросить кэши картинок/анимаций игры."""
        anim.clear_cache()

    # ---------------------------------------------------------------- какие кадры и когда
    @staticmethod
    def _chain(states):
        chain = list(states)
        while chain[-1] in anim.FALLBACK: chain.append(anim.FALLBACK[chain[-1]])
        return chain

    def _match(self, mob_id, mob, states):
        """Какая анимация реально сработает: (имя, кадры, настройки) или None — так же, как перебирает anim.mob_frame."""
        for st in self._chain(states):
            a = anim.find_anim(mob_id, mob, st)
            if a: return st, a[0], a[1]
        return None

    def _sample(self, mob_id, mob, entry, t):
        """Что показывать в момент t: состояния, доля фазы, фаза атаки, режим зоны (None / faint / solid), атака."""
        kind = entry.get("kind"); a = None; zone = None; phase = None; progress = None
        if kind == "state":
            states = [entry["state"]]; m = self._match(mob_id, mob, states)
            if m:
                n = len(m[1]); fps = m[2].get("fps", mob.get("anim_fps", 10)) or 10
                cyc = max(n / fps, .4) + HOLD
            else: cyc = 1.0
            self.cycle = cyc; return dict(states=states, progress=None, t=t % cyc, phase=None, a=None, zone=None)
        a = (mob.get("attacks") or [{}])[entry.get("i", 0)] if mob.get("attacks") else {}
        if kind == "phase":
            phase = entry["phase"]; dur = max(.01, md.phase_duration(a, phase)); cyc = dur + HOLD
            tt = t % cyc; self.cycle = cyc; progress = min(1, tt / dur)
            zone = "faint" if phase == "windup" else "solid" if phase == "active" else None
        else:   # kind == "attack": замах -> удар -> отдых -> пауза, как в Mob.tick_attack
            w, al, r = md.phase_duration(a, "windup"), md.active_length(a), md.phase_duration(a, "recovery")
            cyc = w + al + r + HOLD; tt = t % cyc; self.cycle = cyc
            if tt < w: phase, tt = "windup", tt; dur = w; zone = "faint"
            elif tt < w + al: phase, tt = "active", tt - w; dur = max(.01, md.phase_duration(a, "active")); zone = "solid"
            elif tt < w + al + r: phase, tt = "recovery", tt - w - al; dur = max(.01, r)
            else: phase, tt = None, 0.0; dur = 1
            progress = min(1, tt / max(dur, .01)) if phase else None
        if phase is None: return dict(states=["idle"], progress=None, t=tt, phase=None, a=a, zone=None)
        gen = md.phase_gen(a, phase); own = (a.get("anims") or {}).get(gen)
        states = [own, gen] if own else [gen]
        return dict(states=states, progress=progress, t=tt, phase=phase, a=a, zone=zone)

    # ---------------------------------------------------------------- рисование
    def render(self, mob_id, mob, entry, t, opts):
        zoom = max(1, int(opts.get("zoom", 2))); W, H = self.size
        wv, hv = W // zoom, H // zoom
        world = pg.Surface((wv, hv)); world.fill(BG)
        for x in range(0, wv, 16): pg.draw.line(world, GRID, (x, 0), (x, hv))
        for y in range(0, hv, 16): pg.draw.line(world, GRID, (0, y), (wv, y))
        gy = int(hv * .78); pg.draw.line(world, GROUND, (0, gy), (wv, gy), 1)

        w, h = int(mob.get("w", 24)), int(mob.get("h", 32)); flies = bool(mob.get("flies"))
        dw, dh = (int(v) for v in mob.get("draw", [w, h])); d = -1 if opts.get("flip") else 1
        cx = int(wv * (.7 if d < 0 else .3)); dist = min(120, int(wv * .5))     # игрок стоит перед мобом, но в кадре
        rect = pg.Rect(0, 0, w, h); rect.centerx = cx
        if flies: rect.centery = max(h // 2 + 4, dh // 2 + 4, gy - min(70, int(hv * .4)))
        else: rect.bottom = gy
        top = rect.centery - dh // 2 if flies else rect.bottom - dh

        if entry.get("kind") == "frame":
            path, info, sm = entry["path"], f"кадр: {entry['path']}", dict(zone=None, a=None, phase=None)
        else:
            sm = self._sample(mob_id, mob, entry, t); m = self._match(mob_id, mob, sm["states"])
            path = anim.mob_frame(mob_id, mob, sm["states"], sm["t"], sm["progress"])
            info = self._describe(mob_id, mob, sm, m, path)
        img = anim.sprite(path, max(1, dw), max(1, dh), d < 0, False) if anim.ASSETS_EXISTS(path) else None
        if img: world.blit(img, (rect.centerx - dw // 2, top))
        else:
            pg.draw.rect(world, mob.get("color", [200, 200, 200]), rect, border_radius=5)
            pg.draw.rect(world, (20, 10, 10), (rect.centerx + d * 5 - 2, rect.top + 6, 4, 4))

        pl = None
        if opts.get("player", True):                     # «призрак» игрока для масштаба: стоит перед мобом
            pw, ph = PLAYER_BOX; pr = pg.Rect(0, 0, pw, ph); pr.bottom = gy; pr.centerx = rect.centerx + d * dist
            pl = pr; ghost = pg.Surface(pr.size, pg.SRCALPHA); ghost.fill((150, 190, 255, 55)); world.blit(ghost, pr)
            pg.draw.rect(world, (120, 160, 230), pr, 1)

        a_zone = sm.get("a") if sm.get("zone") else None
        zi = opts.get("zone")
        if a_zone is None and zi is not None and 0 <= zi < len(mob.get("attacks", [])): a_zone, mode = mob["attacks"][zi], "faint"
        else: mode = sm.get("zone") or "faint"
        if a_zone is not None: self._zone(world, mob, a_zone, rect, d, pl, gy, mode)
        if opts.get("box"): pg.draw.rect(world, (90, 150, 255), (rect.centerx - dw // 2, top, dw, dh), 1)
        if opts.get("hitbox", True): pg.draw.rect(world, (0, 255, 0), rect, 1)

        out = pg.Surface(self.size); out.fill(BG); out.blit(pg.transform.scale(world, (wv * zoom, hv * zoom)), (0, 0))
        return b"P6\n%d %d\n255\n" % self.size + pg.image.tostring(out, "RGB"), info

    def _describe(self, mob_id, mob, sm, m, path):
        """Строка под окном: какая анимация играет, кадр, fps."""
        want = sm["states"][0]
        if not m:
            return "кадров анимации нет — рисуется скин" if anim.ASSETS_EXISTS(path) else "нет ни анимации, ни скина — цветной прямоугольник"
        st, frames, spec = m; n = len(frames); idx = frames.index(path) + 1 if path in frames else 0
        base = sm["states"][-1] if st in sm["states"] else st            # «slam_windup» ведёт себя как windup (так же в anim.mob_frame)
        stretched = "fps" not in spec and sm["progress"] is not None and base in anim.PHASES
        fps = f"{spec['fps']:g} к/с" if "fps" in spec else "растянута на фазу" if stretched else f"{mob.get('anim_fps', 10):g} к/с"
        extra = "" if st == want else f" (вместо «{want}» — запасная «{st}»)"
        if "fps" in spec: self.frame_dt = 1 / spec["fps"]
        elif stretched and sm.get("a") and sm.get("phase"): self.frame_dt = md.phase_duration(sm["a"], sm["phase"]) / n
        else: self.frame_dt = 1 / mob.get("anim_fps", 10)
        return f"«{st}»{extra}: кадр {idx}/{n}, {fps}"

    # ---------------------------------------------------------------- зоны атак
    def _zone(self, world, mob, a, rect, d, pl, gy, mode):
        """Контуры зоны поражения выбранной атаки (в фазе удара — залитые). Формулы те же, что в attacks.py."""
        kind = a.get("type"); solid = mode == "solid"
        line, fill = ((255, 130, 95), (255, 90, 70, 95)) if solid else ((190, 80, 80), (190, 80, 80, 28))
        lay = pg.Surface(world.get_size(), pg.SRCALPHA)
        rng = a.get("range"); mx, my = rect.centerx, rect.centery
        plc = pl.center if pl else (mx + d * 120, gy - 17)
        if kind == "melee":
            rw, rh = a.get("reach", [44, 30]); box = pg.Rect(rect.right if d > 0 else rect.left - rw, int(my - rh / 2), int(rw), int(rh))
            pg.draw.rect(lay, fill, box); pg.draw.rect(lay, line + (255,), box, 1)
            if rng is None: rng = rw + rect.w / 2 + 6
        elif kind == "circle":
            r = int(a.get("radius", 80)); c = (mx, my) if a.get("center", "self") == "self" else plc
            pg.draw.circle(lay, fill, c, r); pg.draw.circle(lay, line + (255,), c, r, 1)
            if rng is None: rng = r * .9 if a.get("center", "self") == "self" else 320
        elif kind == "shoot":
            ox, oy = a.get("offset", [8, -4]); o = (mx + ox * d, my + oy); n = max(1, int(a.get("count", 1))); spread = a.get("spread", 0)
            aim = a.get("aim", "player")
            if aim == "forward": base = 0 if d > 0 else math.pi
            elif aim == "angle": base = math.radians(a.get("angle", 0)); base = base if d > 0 else math.pi - base
            elif aim == "ring": base = math.radians(a.get("angle", 0)); spread = 360 / n
            else: base = math.atan2(plc[1] - o[1], plc[0] - o[0])
            for i in range(n):
                ang = base + math.radians((i - (n - 1) / 2) * spread if aim != "ring" else i * spread)
                e = (o[0] + math.cos(ang) * 70, o[1] + math.sin(ang) * 70)
                pg.draw.line(lay, line + (255,), o, e, 1); pg.draw.circle(lay, line + (255,), (int(e[0]), int(e[1])), 2)
            pg.draw.circle(lay, fill, (int(o[0]), int(o[1])), 5); pg.draw.circle(lay, line + (255,), (int(o[0]), int(o[1])), 5, 1)
            if rng is None: rng = 420
        elif kind == "leap":
            r = int(a.get("radius", 60)); side = -d; tx = plc[0] + side * a.get("land_offset", 40); ty = gy - 2
            pg.draw.ellipse(lay, fill, (int(tx - r), ty - 8, 2 * r, 16)); pg.draw.ellipse(lay, line + (255,), (int(tx - r), ty - 8, 2 * r, 16), 1)
            peak = 18 + 60 * float(a.get("air_time", .6)); prev = (mx, rect.bottom)
            for i in range(1, 17):
                u = i / 16; p = (mx + (tx - mx) * u, rect.bottom + (ty - rect.bottom) * u - 4 * peak * u * (1 - u))
                pg.draw.line(lay, line + (255,), prev, p, 1); prev = p
            if rng is None: rng = 300
        if rng and not solid:                              # дальность применения: тонкая окружность (вокруг моба)
            pg.draw.circle(lay, (120, 120, 140, 160), (mx, my), int(rng), 1)
            mr = a.get("min_range", 60 if kind == "leap" else 0)
            if mr: pg.draw.circle(lay, (120, 120, 140, 160), (mx, my), int(mr), 1)
        world.blit(lay, (0, 0))
