"""Экран выбора персонажа перед забегом.

Что где лежит:
  data/characters.json                    — список героев: имя, роль, описание, характеристики (stats), оружие,
                                            стартовые навыки, дерево навыков, правки навыков/оружия;
  assets/characters/<id>/character.json   — внешний вид героя: скин, анимации, размеры, руки, иконка HUD, цвет;
  assets/characters/<id>/skill_menu.json  — оформление экрана получения навыков этого героя (поверх assets/skill_menu.json);
  assets/character_select.json            — оформление самого экрана выбора (фон, карточки, панель, кнопки, тексты).

Этот же экран — лобби сетевой игры (g.menu_mode == "lobby", см. multiplayer.py): вместо панели снаряжения
показывается список игроков, на карточках — метки, кто какого героя выбрал; начать забег может только хост.
"""
import pygame as pg
from core import CFG, ASSETS, SETTINGS, W, VIEW_H, CHAR, char_ids, char_def, char_look, char_player_cfg, read_json, reload_data
from anim import sprite, mob_frame, clear_cache
import weapon

_FONTS, _IMG = {}, {}


def ui():
    """Настройки экрана выбора — assets/character_select.json (читается заново по F5)."""
    if "ui" not in _IMG:
        _IMG["ui"] = read_json(ASSETS / "character_select.json", {})
    return _IMG["ui"]


def font(size):
    size = int(size)
    if size not in _FONTS: _FONTS[size] = pg.font.SysFont("arial,dejavusans,freesans", size, bold=True)
    return _FONTS[size]


def col(key, default):
    v = ui().get(key, default)
    try: return tuple(max(0, min(255, int(c))) for c in v[:3])
    except (TypeError, ValueError): return default


def image(path, size):
    if not path: return None
    key = (path, tuple(size))
    if key not in _IMG:
        try: _IMG[key] = pg.transform.smoothscale(pg.image.load(str(ASSETS / path)).convert_alpha(), size)
        except (OSError, pg.error): _IMG[key] = None
    return _IMG[key]


def rect(key, default):
    v = ui().get(key, default)
    try: return pg.Rect(*[int(x) for x in v[:4]])
    except (TypeError, ValueError): return pg.Rect(*default)


def accent(cid):
    try: return tuple(int(c) for c in char_look(cid).get("color", char_def(cid).get("color", [200, 180, 120]))[:3])
    except (TypeError, ValueError): return (200, 180, 120)


def cards():
    """{id: Rect} карточек. card_positions в character_select.json задаёт место конкретной карточки вручную."""
    u, ids = ui(), char_ids()
    cw, ch, gap = int(u.get("card_width", 168)), int(u.get("card_height", 214)), int(u.get("card_gap", 12))
    total = len(ids) * cw + max(0, len(ids) - 1) * gap
    x0 = u.get("cards_x"); x0 = (W - total) // 2 if x0 is None else int(x0)
    y0 = int(u.get("cards_y", 66)); pos = u.get("card_positions", {}) or {}
    out = {}
    for i, cid in enumerate(ids):
        p = pos.get(cid)
        out[cid] = pg.Rect(int(p[0]), int(p[1]), cw, ch) if p else pg.Rect(x0 + i * (cw + gap), y0, cw, ch)
    return out


# ---------------- управление ----------------
def open_select(g):
    """Открыть выбор героя (из главного меню или паузы). Esc вернёт туда, откуда пришли."""
    ids = char_ids()
    if not ids:   # персонажей нет — сразу обычный забег
        g.new_game(); g.menu_mode = None; return
    g.select_back = g.menu_mode if g.menu_mode in ("start", "pause") else "start"
    last = SETTINGS.get("last_character", CHAR["id"])
    g.select_index = ids.index(last) if last in ids else 0
    g.select_t0 = pg.time.get_ticks()
    g.menu_mode = "select"


def open_lobby(g):
    """Лобби мультиплеера: тот же выбор героя, но со списком игроков."""
    ids = char_ids()
    last = SETTINGS.get("last_character", CHAR["id"])
    g.select_index = ids.index(last) if last in ids else 0
    g.select_t0 = pg.time.get_ticks()
    g.menu_mode = "lobby"
    if lobby(g) and ids: lobby(g).set_char(selected(g))   # в списке игроков — тот же герой, что выделен


def lobby(g):
    """Сетевая сессия, если открыт экран лобби, иначе None."""
    return g.net if g.menu_mode == "lobby" and getattr(g, "net", None) else None


def selected(g):
    ids = char_ids()
    return ids[g.select_index % len(ids)] if ids else None


def choose(g, i):
    ids = char_ids()
    if ids and (i % len(ids)) != g.select_index:
        g.select_index = i % len(ids); g.select_t0 = pg.time.get_ticks()
        if lobby(g): lobby(g).set_char(selected(g))   # сообщить остальным игрокам


def start(g):
    if lobby(g): lobby(g).start(); return   # в лобби забег запускает хост
    cid = selected(g)
    SETTINGS["last_character"] = cid; g.save_settings()
    g.new_game(character=cid); g.menu_mode = None
    pg.mouse.set_visible(not SETTINGS.get("mouse_aim", True))


def back(g):
    if lobby(g): g.net_leave(); return   # выйти из лобби (хост закрывает сервер)
    g.menu_mode = getattr(g, "select_back", "start")


def key(g, k):
    n = len(char_ids())
    if k in (pg.K_LEFT, pg.K_a): choose(g, g.select_index - 1)
    elif k in (pg.K_RIGHT, pg.K_d): choose(g, g.select_index + 1)
    elif pg.K_1 <= k <= pg.K_9 and k - pg.K_1 < n: choose(g, k - pg.K_1)
    elif k in (pg.K_RETURN, pg.K_KP_ENTER, pg.K_SPACE): start(g)
    elif k == pg.K_ESCAPE: back(g)
    elif k == pg.K_F5 and not lobby(g):   # перечитать data и assets, не выходя с экрана
        cid = selected(g); _IMG.clear(); reload_data(); clear_cache()
        ids = char_ids(); g.select_index = ids.index(cid) if cid in ids else 0
    elif k == pg.K_F11: pg.display.toggle_fullscreen()


def event(g, e):
    if e.type != pg.MOUSEBUTTONDOWN or e.button != 1: return
    if rect("start_button", [648, 420, 276, 44]).collidepoint(e.pos): start(g); return
    if ui().get("show_back_button", True) and rect("back_button", [20, 16, 120, 32]).collidepoint(e.pos): back(g); return
    for i, (cid, r) in enumerate(cards().items()):
        if r.collidepoint(e.pos):
            if i == g.select_index and ui().get("double_click_start", True) and pg.time.get_ticks() - getattr(g, "select_click", -9999) < 400:
                start(g); return
            choose(g, i); g.select_click = pg.time.get_ticks(); return


# ---------------- отрисовка ----------------
def draw_lobby_players(g, scr, lr, net, mouse):
    """Лобби: список игроков на месте панели снаряжения + кнопки «Начать» (хост) и «Выйти»."""
    u = ui()
    box(scr, lr, "loadout_image", col("panel_color", (20, 20, 32)), col("panel_border", (80, 80, 110)), 2, 8)
    players = net.lobby_players()
    text(scr, f"ИГРОКИ {len(players)}/{net.max_players}", 12, col("stat_label_color", (190, 190, 210)), topleft=(lr.x + 10, lr.y + 8), shadow=False)
    for i, info in enumerate(players[:4]):
        y = lr.y + 28 + i * 22
        pg.draw.circle(scr, net.color_of(info["id"]), (lr.x + 16, y + 7), 5)
        name = (info.get("name") or "?") + (" (хост)" if info["id"] == 0 else "") + (" — вы" if info["id"] == net.my_id else "")
        text(scr, name[:26], 12, (235, 232, 245), topleft=(lr.x + 26, y), shadow=False)
        hero = char_def(info.get("char")).get("name", info.get("char") or "?")
        t = font(12).render(hero, True, accent(info.get("char"))); scr.blit(t, (lr.right - 10 - t.get_width(), y))
    def button(key, default, label, active=True):
        r = rect(key, default); hov = active and r.collidepoint(mouse)
        img = image(u.get("button_selected_image" if hov else "button_image"), r.size)
        if img: scr.blit(img, r)
        else:
            pg.draw.rect(scr, (92, 76, 130) if hov else (43, 40, 60), r, border_radius=8)
            pg.draw.rect(scr, (180, 160, 230) if hov else (95, 88, 120), r, 2, border_radius=8)
        text(scr, label, u.get("button_text_size", 16), col("button_text_color", (250, 248, 255)) if active else (150, 150, 170), center=r.center)
    button("start_button", [648, 420, 276, 44], "НАЧАТЬ ЗАБЕГ" if net.is_host else "ЖДЁМ ХОСТА…", net.is_host)
    if u.get("show_back_button", True): button("back_button", [20, 16, 120, 32], "ВЫЙТИ")
    hint = ("Выберите героя · Enter — начать забег для всех · Esc — закрыть лобби" if net.is_host
            else "Выберите героя · забег начнёт хост · Esc — выйти из лобби")
    text(scr, hint, 11, col("hint_color", (160, 160, 185)), center=(int(u.get("hint_x", W // 2)), int(u.get("hint_y", VIEW_H - 14))), shadow=False)



def text(scr, s, size, color, center=None, topleft=None, shadow=True):
    f = font(size)
    t = f.render(str(s), True, color)
    r = t.get_rect(center=center) if center else t.get_rect(topleft=topleft)
    if shadow: scr.blit(f.render(str(s), True, (0, 0, 0)), r.move(1, 2))
    scr.blit(t, r)
    return r


def wrap(s, size, width):
    f, lines = font(size), []
    for para in str(s).split("\n"):
        line = ""
        for word in para.split():
            test = (line + " " + word).strip()
            if f.size(test)[0] <= width or not line: line = test
            else: lines.append(line); line = word
        lines.append(line)
    return lines


def box(scr, r, img_key, fill, border, bw=2, radius=8):
    img = image(ui().get(img_key), r.size)
    if img: scr.blit(img, r)
    else:
        pg.draw.rect(scr, fill, r, border_radius=radius)
        if bw: pg.draw.rect(scr, border, r, bw, border_radius=radius)


def preview(scr, cid, area, moving):
    """Анимированная фигурка героя (анимации — из assets/characters/<id>/)."""
    u, p, look = ui(), char_player_cfg(cid), char_look(cid)
    sel = look.get("select", {})
    state = sel.get("selected", u.get("preview_anim_selected", "idle")) if moving else sel.get("idle", u.get("preview_anim", "idle"))
    fps = sel.get("fps", u.get("preview_fps", 6))
    d = {**p, "anim_fps": fps}
    path = mob_frame(f"player:{cid}", d, [state], pg.time.get_ticks() / 1000, None, folder=p.get("folder", "player"))
    dw, dh = p.get("draw", [44, 55])
    scale = max(0.1, min(5.0, float(char_def(cid).get("model_scale", 1.0))))
    dw, dh = max(1, int(dw * scale)), max(1, int(dh * scale))
    k = min(area.w / dw, area.h / dh)
    w, h = max(1, int(dw * k)), max(1, int(dh * k))
    img = sprite(path, w, h)
    if img: scr.blit(img, (area.centerx - w // 2, area.bottom - h))
    else: pg.draw.rect(scr, accent(cid), (area.centerx - w // 4, area.bottom - h, w // 2, h), border_radius=6)


def stat_value(cfg, path):
    v = cfg
    for part in str(path).split("."):
        v = v.get(part) if isinstance(v, dict) else None
    return v


def draw(g):
    scr, u, ids = g.scr, ui(), char_ids()
    if not ids: return
    cur = selected(g); now = pg.time.get_ticks()
    # фон
    bg = image(u.get("background_image"), (W, VIEW_H))
    if bg: scr.blit(bg, (0, 0))
    else: scr.fill(col("background_color", (10, 10, 18)))
    veil = pg.Surface((W, VIEW_H), pg.SRCALPHA); veil.fill((*col("overlay_color", (6, 6, 12)), int(u.get("overlay_alpha", 90)))); scr.blit(veil, (0, 0))
    net = lobby(g)
    if u.get("show_title", True) or net:
        text(scr, "ЛОББИ" if net else u.get("title", "ВЫБОР ГЕРОЯ"), u.get("title_size", 36), col("title_color", (255, 220, 130)),
             center=(int(u.get("title_x", W // 2)), int(u.get("title_y", 34)) - (6 if net else 0)))
    if net:
        text(scr, net.address_line(), 13, (190, 225, 255), center=(int(u.get("title_x", W // 2)), int(u.get("title_y", 34)) + 20))
    # карточки
    mouse = pg.mouse.get_pos()
    for i, (cid, r) in enumerate(cards().items()):
        c, sel, hov = char_def(cid), cid == cur, r.collidepoint(mouse)
        key = "card_selected_image" if sel else ("card_hover_image" if hov and u.get("card_hover_image") else "card_image")
        lift = int(u.get("selected_lift", 6)) if sel else 0
        rr = r.move(0, -lift)
        box(scr, rr, key, col("card_color", (26, 26, 40)), accent(cid) if sel else col("card_border", (80, 80, 110)),
            int(u.get("card_border_width", 2)), int(u.get("card_radius", 10)))
        if sel and u.get("selected_border", True):
            pg.draw.rect(scr, accent(cid), rr, int(u.get("selected_border_width", 3)), border_radius=int(u.get("card_radius", 10)))
        pw, ph = int(u.get("preview_width", 92)), int(u.get("preview_height", 115))
        preview(scr, cid, pg.Rect(rr.centerx - pw // 2, rr.y + int(u.get("preview_y", 22)), pw, ph), sel)
        text(scr, c.get("name", cid), u.get("name_size", 18), accent(cid) if sel else col("name_color", (235, 230, 245)),
             center=(rr.centerx, rr.y + int(u.get("name_y", 160))))
        if u.get("show_role", True) and c.get("role"):
            text(scr, c["role"], u.get("role_size", 12), col("role_color", (170, 170, 195)), center=(rr.centerx, rr.y + int(u.get("role_y", 182))))
        if u.get("show_hotkeys", True):
            text(scr, str(i + 1), 12, col("hotkey_color", (150, 150, 175)), topleft=(rr.x + 8, rr.y + 6))
        if net:   # метки игроков, выбравших этого героя
            for j, info in enumerate([p for p in net.lobby_players() if p.get("char") == cid][:4]):
                cx, cy = rr.right - 14 - j * 22, rr.y + 14
                pcol = net.color_of(info["id"])
                pg.draw.circle(scr, (12, 12, 20), (cx, cy), 11); pg.draw.circle(scr, pcol, (cx, cy), 9)
                text(scr, (info.get("name") or "?")[:1].upper(), 12, (20, 20, 30), center=(cx, cy), shadow=False)
    # панель описания и характеристик
    c, pcfg = char_def(cur), char_player_cfg(cur)
    pr = rect("panel", [36, 292, 600, 172])
    box(scr, pr, "panel_image", col("panel_color", (20, 20, 32)), col("panel_border", (80, 80, 110)), 2, 8)
    pad = int(u.get("panel_padding", 14))
    text(scr, c.get("name", cur), u.get("panel_name_size", 22), accent(cur), topleft=(pr.x + pad, pr.y + pad - 4))
    desc_w = int(u.get("description_width", 290)); y = pr.y + pad + 26
    for line in wrap(c.get("description", ""), u.get("description_size", 12), desc_w)[:int(u.get("description_lines", 7))]:
        text(scr, line, u.get("description_size", 12), col("description_color", (210, 210, 225)), topleft=(pr.x + pad, y), shadow=False); y += int(u.get("description_size", 12)) + 5
    sx = pr.x + pad + desc_w + int(u.get("stats_gap", 18)); sy = pr.y + pad
    bw, bh = int(u.get("stat_bar_width", 150)), int(u.get("stat_bar_height", 8))
    for st in u.get("stats", []):
        v = stat_value(pcfg, st.get("key", ""))
        if not isinstance(v, (int, float)): continue
        mx = float(st.get("max", 1)) or 1
        text(scr, st.get("label", st.get("key")), 12, col("stat_label_color", (190, 190, 210)), topleft=(sx, sy), shadow=False)
        shown = f"{v:g}" if not st.get("percent") else f"{v * 100:.0f}%"
        t = font(12).render(shown, True, col("stat_value_color", (255, 235, 180))); scr.blit(t, (sx + bw - t.get_width(), sy))
        br = pg.Rect(sx, sy + 16, bw, bh)
        pg.draw.rect(scr, col("stat_bar_back", (40, 40, 58)), br, border_radius=3)
        pg.draw.rect(scr, accent(cur) if u.get("stat_bar_accent", True) else col("stat_bar_color", (120, 200, 255)),
                     (br.x, br.y, int(br.w * max(0.0, min(1.0, v / mx))), br.h), border_radius=3)
        sy += int(u.get("stat_step", 29))
    # снаряжение: оружие и стартовые навыки (в лобби на этом месте — список игроков)
    lr = rect("loadout_panel", [648, 292, 276, 120])
    if net:
        draw_lobby_players(g, scr, lr, net, mouse)
        return
    box(scr, lr, "loadout_image", col("panel_color", (20, 20, 32)), col("panel_border", (80, 80, 110)), 2, 8)
    isz = int(u.get("loadout_icon_size", 34))
    ws = [wid for wid in c.get("weapons", [])[:2] if wid in CFG["weapons_base"]]
    # У безоружных героев (маг/инженер, weapons: []) блок «Оружие» не рисуем — навыки слева.
    sx = lr.x + 10 if not ws else lr.x + 10 + 2 * (isz + 6) + 8
    if ws:
        text(scr, u.get("weapons_label", "Оружие"), 12, col("stat_label_color", (190, 190, 210)), topleft=(lr.x + 10, lr.y + 8), shadow=False)
    x = lr.x + 10
    for wid in ws:
        ir = pg.Rect(x, lr.y + 26, isz, isz)
        pg.draw.rect(scr, (32, 30, 46), ir, border_radius=6); pg.draw.rect(scr, (90, 86, 120), ir, 1, border_radius=6)
        icon = sprite(CFG["weapons_base"][wid].get("icon", f"icons/{wid}.png"), isz, isz)
        if icon: scr.blit(icon, ir)
        else: weapon.icon(scr, wid, ir.centerx, ir.centery, int(isz * .8))
        x += isz + 6
    text(scr, u.get("skills_label", "Навыки"), 12, col("stat_label_color", (190, 190, 210)), topleft=(sx, lr.y + 8), shadow=False)
    x = sx
    skills = CFG["skills_base"]
    for sid in c.get("base_skills", [])[:4]:
        if sid not in skills: continue
        ir = pg.Rect(x, lr.y + 26, isz, isz)
        icon = sprite(skills[sid].get("icon"), isz, isz) if skills[sid].get("icon") else None
        if icon: scr.blit(icon, ir)
        else: pg.draw.circle(scr, skills[sid].get("color", [150, 130, 220]), ir.center, isz // 3)
        x += isz + 6
    names = [skills[sid].get("name", sid) for sid in c.get("base_skills", []) if sid in skills]
    tree = c.get("skill_tree", []); tree = tree.get("slots", []) if isinstance(tree, dict) else tree
    lines = [", ".join(names)] if names else []
    if u.get("show_tree_size", True) and tree: lines.append(str(u.get("tree_label", "Дерево: {n} навыков")).format(n=len(tree)))
    yy = lr.y + 26 + isz + 6
    for ln in lines:
        for sub in wrap(ln, 11, lr.w - 20)[:2]:
            text(scr, sub, 11, col("description_color", (210, 210, 225)), topleft=(lr.x + 10, yy), shadow=False); yy += 15
    # кнопки
    def button(key, default, label_key, label_default):
        r = rect(key, default); hov = r.collidepoint(mouse)
        img = image(u.get("button_selected_image" if hov else "button_image"), r.size)
        if img: scr.blit(img, r)
        else:
            pg.draw.rect(scr, (92, 76, 130) if hov else (43, 40, 60), r, border_radius=8)
            pg.draw.rect(scr, (180, 160, 230) if hov else (95, 88, 120), r, 2, border_radius=8)
        text(scr, u.get(label_key, label_default), u.get("button_text_size", 16), col("button_text_color", (250, 248, 255)), center=r.center)
    button("start_button", [648, 420, 276, 44], "start_label", "НАЧАТЬ ЗАБЕГ")
    if u.get("show_back_button", True): button("back_button", [20, 16, 120, 32], "back_label", "НАЗАД")
    if u.get("hint"):
        text(scr, u["hint"], 11, col("hint_color", (160, 160, 185)), center=(int(u.get("hint_x", W // 2)), int(u.get("hint_y", VIEW_H - 14))), shadow=False)
