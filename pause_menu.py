"""Меню паузы (Esc) — пять кнопок: ПРОДОЛЖИТЬ, ВЫБОР ПЕРСОНАЖА, СОХРАНИТЬСЯ, ЗАГРУЗИТЬ, ГЛАВНОЕ МЕНЮ.

Координаты кнопок хранятся в data/settings.json (SETTINGS["menu_layout_pause"]) и правятся
встроенным редактором (F3): перетаскивание мышью, колесо или +/- — размер. Пользовательские
координаты не перетираются: новые добавляются только через setdefault.

Роутинг со стороны main.py: key()/event()/draw() вызываются при s.menu_mode == "pause",
действия доставляет Game.menu_action (main.py). Курсор поверх меню рисует main (draw_cursor).
В сетевой игре (g.net) смена героя и работа с сохранениями недоступны — кнопки приглушены,
при попытке выбора всплывает подсказка «Недоступно в сетевой игре»."""
import pygame as pg
from core import SETTINGS, W, VIEW_H

# (подпись, действие) — действия "swap"/"save"/"load"/"menu" разбирает Game.menu_action в main.py.
OPTIONS = [
    ("ПРОДОЛЖИТЬ", "continue"),
    ("ВЫБОР ПЕРСОНАЖА", "swap"),
    ("СОХРАНИТЬСЯ", "save"),
    ("ЗАГРУЗИТЬ", "load"),
    ("ГЛАВНОЕ МЕНЮ", "menu"),
]

# Забег в сети общий: герой и сохранения менять нельзя.
NET_LOCKED = ("swap", "save", "load")

BTN_W, BTN_H, STEP = 300, 44, 58   # размер кнопки и шаг столбца по вертикали

# Быстрый выбор кнопок клавишами 1..5 (верхний ряд и цифровой блок).
DIGIT_SLOTS = {
    pg.K_1: 0, pg.K_2: 1, pg.K_3: 2, pg.K_4: 3, pg.K_5: 4,
    pg.K_KP1: 0, pg.K_KP2: 1, pg.K_KP3: 2, pg.K_KP4: 3, pg.K_KP5: 4,
}


def _defaults():
    """Дефолтный столбец по центру экрана: от VIEW_H//2-150, смиряется под низкие окна."""
    n = len(OPTIONS)
    step, total = STEP, (n - 1) * STEP + BTN_H
    if total > VIEW_H - 16:                     # экран совсем низкий — ужимаем шаг
        step = max(BTN_H, (VIEW_H - 16 - BTN_H) // max(1, n - 1))
        total = (n - 1) * step + BTN_H
    top = VIEW_H // 2 - 150
    if top + total > VIEW_H - 8:                # столбец не влезает вниз — поднимаем целиком
        top = max(4, VIEW_H - 8 - total)
    x = W // 2 - BTN_W // 2
    return {action: [x, top + i * step, BTN_W, BTN_H] for i, (_label, action) in enumerate(OPTIONS)}


def layout(g=None):
    """Координаты кнопок паузы из SETTINGS["menu_layout_pause"] (как main.menu_layout:
    setdefault пользовательских значений, clamp под экран). Возвращаются только кнопки OPTIONS."""
    cfg = SETTINGS.setdefault("menu_layout_pause", {})
    defaults = _defaults()
    if any(name not in cfg for name in defaults):
        # Старый формат трёх кнопок (continue/new/exit) или пустой: сбрасываем на дефолтный
        # столбец из пяти кнопок — набор кнопок другой, старые координаты не подходят.
        cfg = {name: rect[:] for name, rect in defaults.items()}
        SETTINGS["menu_layout_pause"] = cfg
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
    return {action: cfg[action] for _label, action in OPTIONS}   # те же списки, что лежат в SETTINGS


def _resize(cfg, action, delta):
    """Размер кнопки меняется вокруг её центра (как resize_menu_button в main.py)."""
    a = cfg.get(action)
    if not a:
        return
    nw, nh = max(100, min(700, a[2] + delta)), max(28, min(120, a[3] + round(delta * 0.22)))
    cx, cy = a[0] + a[2] // 2, a[1] + a[3] // 2
    a[:] = [cx - nw // 2, cy - nh // 2, nw, nh]


def _unavailable(g, action):
    """True — действие запрещено в сетевой игре (подсказка через g.fx.text, координаты мировые)."""
    if not getattr(g, "net", None) or action not in NET_LOCKED:
        return False
    cam = getattr(g, "cam", None) or [0, 0]
    fx = getattr(g, "fx", None)
    if fx:
        fx.text("Недоступно в сетевой игре", cam[0] + W // 2, cam[1] + VIEW_H // 2 - 60)
    return True


def _choose(g, action):
    if _unavailable(g, action):
        return
    g.menu_action(action)


def key(g, k):
    """Клавиши меню паузы: Esc — вернуться в забег, 1..5 (и KP1..KP5) — нажать кнопку."""
    if k == pg.K_ESCAPE:
        if getattr(g, "menu_edit", False):      # Esc в редакторе кнопок сначала выходит из редактора
            g.menu_edit = False
            g.menu_drag = None
            return
        g.menu_mode = None
        pg.mouse.set_visible(not SETTINGS.get("mouse_aim", True))
        return
    if getattr(g, "menu_edit", False):          # в режиме редактирования цифры не нажимают кнопки
        return
    i = DIGIT_SLOTS.get(k)
    if i is not None and i < len(OPTIONS):
        _choose(g, OPTIONS[i][1])


def event(g, e):
    """Мышь: клик по кнопке; в режиме F3 — перетаскивание кнопок и размер колесом."""
    cfg = layout(g)
    options = [action for _label, action in OPTIONS]
    if getattr(g, "menu_edit", False):
        if e.type == pg.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            for action in reversed(options):
                rect = pg.Rect(cfg[action])
                if rect.collidepoint(mx, my):
                    g.menu_selected = action
                    g.menu_drag = (action, mx - rect.x, my - rect.y)
                    return
        elif e.type == pg.MOUSEMOTION and getattr(g, "menu_drag", None):
            action, dx, dy = g.menu_drag
            cfg[action][0] = max(0, min(W - cfg[action][2], e.pos[0] - dx))
            cfg[action][1] = max(0, min(VIEW_H - cfg[action][3], e.pos[1] - dy))
            g.save_settings()
        elif e.type == pg.MOUSEBUTTONUP and e.button == 1:
            g.menu_drag = None
        elif e.type == pg.MOUSEBUTTONDOWN and e.button in (4, 5):
            mx, my = e.pos
            for action in reversed(options):
                if pg.Rect(cfg[action]).collidepoint(mx, my):
                    g.menu_selected = action; break
            _resize(cfg, g.menu_selected, 8 if e.button == 4 else -8)
            g.save_settings()
        elif e.type == pg.MOUSEWHEEL:
            mx, my = pg.mouse.get_pos()
            for action in reversed(options):
                if pg.Rect(cfg[action]).collidepoint(mx, my):
                    g.menu_selected = action; break
            if e.y:
                _resize(cfg, g.menu_selected, 8 if e.y > 0 else -8)
                g.save_settings()
        return
    if e.type == pg.MOUSEBUTTONDOWN and e.button == 1:
        mx, my = e.pos
        for _label, action in OPTIONS:
            if pg.Rect(cfg[action]).collidepoint(mx, my):
                _choose(g, action); return


def draw(g):
    """Вуаль + пять кнопок с номерами; в сетевой игре часть кнопок приглушена. Курсор рисует main."""
    g.scr.blit(g.menu_veil, (0, 0))
    cfg = layout(g)
    mouse = pg.mouse.get_pos()
    net = getattr(g, "net", None)
    editing = getattr(g, "menu_edit", False)
    for i, (label, action) in enumerate(OPTIONS):
        rect = pg.Rect(cfg[action])
        locked = net is not None and action in NET_LOCKED
        hovered = not locked and rect.collidepoint(mouse)
        selected = editing and getattr(g, "menu_selected", None) == action
        img = g.menu_button_selected if (hovered or selected) else g.menu_button
        if img:
            img = pg.transform.smoothscale(img, rect.size)
            if locked:
                img.set_alpha(105)   # копия от smoothscale — общий ассет не портится
            g.scr.blit(img, rect.topleft)
        else:
            col = (92, 76, 130) if hovered else (43, 40, 60)
            if locked:
                col = tuple(c // 2 for c in col)
            pg.draw.rect(g.scr, col, rect, border_radius=8)
            pg.draw.rect(g.scr, (180, 160, 230) if hovered else (95, 88, 120), rect, 2, border_radius=8)
        text = g.font.render(f"{i + 1}. {label}", True, (250, 248, 255) if not locked else (150, 148, 168))
        g.scr.blit(text, text.get_rect(center=rect.center))
        if editing:
            color = (255, 210, 80) if selected else (110, 220, 255)
            pg.draw.rect(g.scr, color, rect, 2)
            size_label = g.small.render(f"{action}: {rect.w}x{rect.h} ({rect.x},{rect.y})", True, color)
            g.scr.blit(size_label, (rect.x, max(0, rect.y - 16)))
    if editing:
        hint = "РЕДАКТОР КНОПОК: перетаскивай мышью · колесо или +/- — размер · F3/Esc — готово"
        col = (255, 225, 135)
    else:
        hint = "Esc — продолжить · 1–5 — выбор кнопки · F3 — редактировать"
        col = (168, 163, 192)
    ht = g.small.render(hint, True, col)
    g.scr.blit(ht, ht.get_rect(center=(W // 2, VIEW_H - 28)))
