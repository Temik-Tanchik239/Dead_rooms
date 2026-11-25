"""Окно торговли с NPC-торговцем (trade.py): открывается на E рядом с торговцем (npc.try_trade).

Слева — торговец: имя в отдельной рамке сверху, под ним краткое описание, ниже его товары
(клик по товару кладёт его в окно покупки; колесо мыши — листать). Посередине — окно ПОКУПКИ,
куда ложатся предметы, которые игрок хочет купить, и под ним окно ПРОДАЖИ — туда игрок кладёт
свои предметы кликом из рюкзака/рук/экипировки или со склада ресурсов. Справа — игрок: имя
сверху, под ним класс и монеты, ниже рюкзак, руки, склад и экипировка.

Кнопка «КУПИТЬ»: суммирует окно покупки, списывает монеты и раскладывает покупки по рюкзаку.
Если монет не хватает (или в рюкзаке нет места) — торговец отказывает и ничего не меняется.
Кнопка «ПРОДАТЬ»: забирает отмеченные предметы и выдаёт монеты — долю от цены
(data/npcs.json -> sell_ratio). Пока предмет стоит в окне продажи, он остаётся в своей ячейке —
окно можно закрыть в любой момент без потерь. Tab / Esc — закрыть.
"""
import pygame as pg
from core import CFG, W, VIEW_H, use_char
import inventory
import npc

BUY_MAX, SELL_MAX = 6, 6          # сколько товаров/предметов влезает в окна покупки и продажи
PAGE_ROWS, PAGE_COLS = 4, 4       # страница товаров торговца (колесо мыши листает)
GOLD, RED, GREEN = (255, 214, 120), (255, 150, 130), (150, 230, 160)
LC = (190, 190, 215)              # цвет подписей-заголовков

# --- фиксированная раскладка (окно игры W x VIEW_H = 960 x 512) ---
NAME_BOX = pg.Rect(28, 16, 280, 34)      # имя торговца в отдельной рамке
GOODS_LABEL = (28, 94)                   # «ТОВАРЫ»
BUY_LABEL = (316, 12)                    # «ПОКУПКА»
BUY_BOX = pg.Rect(316, 30, 310, 126)     # окно покупки
BUY_BTN = pg.Rect(316, 182, 148, 30)
SELL_LABEL = (316, 244)                  # «ПРОДАЖА»
SELL_BOX = pg.Rect(316, 262, 310, 126)   # окно продажи
SELL_BTN = pg.Rect(316, 414, 148, 30)
PL_NAME = pg.Rect(636, 14, 292, 26)      # имя игрока
PL_CLASS_Y = 42                          # класс игрока (под именем)
PL_COINS_Y = 58                          # монеты игрока
PL_BAG_LABEL = (636, 76)                 # «РЮКЗАК …»
PL_HAND_LABEL = (636, 272)               # «В РУКАХ»
PL_RES_LABEL = (636, 348)                # «СКЛАД»
PL_EQ_LABEL = (636, 406)                 # «ЭКИПИРОВКА»
MSG_POS = (316, 452)                     # сообщения/подсказки (2 строки)


# ================================================================ состояние окна
def open(g, npc_obj):
    """Открыть торговлю с NPC (g.trade_open)."""
    g.trade_open = {"npc": npc_obj, "buy": [], "sell": [], "scroll": 0, "msg": None}


def close(g):
    g.trade_open = None


def _say(st, text, col=RED):
    st["msg"] = (str(text), pg.time.get_ticks() + 2800, col)


# ================================================================ раскладка
def _grid(x, y, cols, rows, cell, gap, n=None):
    n = cols * rows if n is None else n
    return [pg.Rect(x + i % cols * (cell + gap), y + i // cols * (cell + gap), cell, cell) for i in range(n)]


def _layout(pl):
    """Все прямоугольники окна на экране (по ним же работает мышь)."""
    bag = inventory.bag(pl)
    return {
        "panel": pg.Rect(16, 6, 928, 500),
        "goods": _grid(28, 114, PAGE_COLS, PAGE_ROWS, 56, 6),
        "buy": _grid(316 + (310 - (3 * 56 + 2 * 6)) // 2, 34, 3, 2, 56, 6),
        "sell": _grid(316 + (310 - (3 * 56 + 2 * 6)) // 2, 266, 3, 2, 56, 6),
        "bag": [pg.Rect(636 + i % 4 * (54 + 5), 96 + i // 4 * (54 + 5), 54, 54) for i in range(len(bag))],
        "hand": [pg.Rect(636 + i * (50 + 8), 294, 50, 50) for i in range(2)],
        "res": [(rid, pg.Rect(636 + i * (32 + 6), 370, 32, 32)) for i, rid in enumerate(inventory.resource_order())],
        "equip": [(s["id"], pg.Rect(636 + i % 5 * (32 + 3), 428 + i // 5 * (32 + 3), 32, 32))
                  for i, s in enumerate(inventory.slot_defs())],
    }


# ================================================================ данные окон
def _goods_item(st, i):
    """Товар торговца на экранном месте i (с учётом прокрутки), None — пусто."""
    d = st["npc"].d
    items = npc.trade_items(d)
    page = max(0, int(st.get("scroll", 0)))
    page = min(page, max(0, (len(items) - 1) // (PAGE_ROWS * PAGE_COLS)))
    st["scroll"] = page
    n = page * PAGE_ROWS * PAGE_COLS + i
    return items[n] if 0 <= n < len(items) else None


def _mult(npc_obj):
    try: return max(0.1, float(npc_obj.d.get("price_mult", 1.0)))
    except (TypeError, ValueError): return 1.0


# ================================================================ логика сделки
def _do_buy(g, pl, st):
    """Купить отмеченное: проверка монет и места в рюкзаке — при отказе ничего не меняется."""
    if not st["buy"]: return
    with use_char(pl.char_id):
        need = [e for e in st["buy"] if not inventory.is_resource_item(e["item"])]
        if len(need) > inventory.bag(pl).count(None):
            _say(st, "Рюкзак полон — покупки не влезут"); return
        total = sum(int(e["price"]) for e in st["buy"])
        coins = max(0, int(getattr(pl, "coins", 0) or 0))
        if coins < total:
            _say(st, f"Не хватает монет: нужно {total}, у тебя {coins}"); return
        for e in st["buy"]:
            wid = e["item"]
            if inventory.is_resource_item(wid): inventory.add_resource(pl, wid)
            else:
                b = inventory.bag(pl); b[b.index(None)] = wid
        pl.coins = coins - total
        inventory.sync_stack(pl)
    st["buy"] = []
    _say(st, f"Куплено за {total} монет", GREEN)


def _do_sell(g, pl, st):
    """Продать отмеченное: предметы уходят из ячеек/склада, монеты — игроку."""
    if not st["sell"]: return
    total = 0
    equip_changed = False
    with use_char(pl.char_id):
        for e in st["sell"]:
            rid = e.get("res")
            if rid:   # ресурс со склада
                if inventory.remove_resource(pl, rid, 1): total += npc.sell_price_of(rid)
                continue
            cell, wid = e.get("cell"), e.get("item")
            if not inventory.valid_cell(pl, cell) or inventory.get(pl, cell) != wid: continue
            inventory.put(pl, cell, None)
            if cell[0] == "h": inventory._hands_changed(pl)
            elif cell[0] == "e": equip_changed = True
            total += npc.sell_price_of(wid)
        if equip_changed: inventory.on_equipment_changed(g, pl)
        if total > 0:
            pl.coins = max(0, int(getattr(pl, "coins", 0) or 0)) + total
            inventory.sync_stack(pl)
    st["sell"] = []
    _say(st, f"Продано: +{total} монет", GOLD) if total else _say(st, "Продавать нечего")


# ================================================================ ввод
def key(g, k):
    """Клавиши при открытом окне: Tab/Esc — закрыть (проверяет Game.key первым делом)."""
    try: toggle_key = pg.key.key_code(str(g.controls().get("inventory", "TAB")))
    except (ValueError, TypeError): toggle_key = pg.K_TAB
    if k in (pg.K_ESCAPE, toggle_key): close(g)


def event(g, e):
    """Мышь при открытом окне: клики по товарам/окнам/кнопкам, колесо — листать товары."""
    st = g.trade_open
    if e.type not in (pg.MOUSEBUTTONDOWN, pg.MOUSEWHEEL): return
    pl = g.pl
    L = _layout(pl)
    if e.type == pg.MOUSEWHEEL or e.button in (4, 5):   # колесо: листать товары торговца
        if L["panel"].collidepoint(pg.mouse.get_pos()):
            step = (getattr(e, "y", 0) or (-1 if getattr(e, "button", 0) == 5 else 1))
            items = npc.trade_items(st["npc"].d)
            pages = max(0, (len(items) - 1) // (PAGE_ROWS * PAGE_COLS))
            st["scroll"] = max(0, min(pages, int(st.get("scroll", 0)) - (1 if step > 0 else -1)))
        return
    if e.button != 1: return
    for i, rect in enumerate(L["goods"]):   # товар -> в окно покупки
        if not rect.collidepoint(e.pos): continue
        wid = _goods_item(st, i)
        if wid is None: return
        if len(st["buy"]) >= BUY_MAX:
            _say(st, "Окно покупки заполнено — сначала нажми «Купить»"); return
        st["buy"].append({"item": wid, "price": npc.price_of(wid, _mult(st["npc"]))})
        return
    for i, rect in enumerate(L["buy"]):     # передумали покупать — убрать из окна
        if rect.collidepoint(e.pos):
            if i < len(st["buy"]): del st["buy"][i]
            return
    for i, rect in enumerate(L["sell"]):    # передумали продавать — вернуть на место
        if rect.collidepoint(e.pos):
            if i < len(st["sell"]): del st["sell"][i]
            return
    for cell, rect in _player_cells(L):     # свой предмет -> в окно продажи
        if not rect.collidepoint(e.pos): continue
        if isinstance(cell, str):           # ресурс со склада
            if inventory.resource_count(pl, cell) <= 0: return
            if len(st["sell"]) >= SELL_MAX:
                _say(st, "Окно продажи заполнено — сначала нажми «Продать»"); return
            st["sell"].append({"res": cell})
            return
        wid = inventory.get(pl, cell)
        if wid is None or not npc.is_tradable(wid):
            if wid: _say(st, "Это деньги — их не продают")
            return
        if len(st["sell"]) >= SELL_MAX:
            _say(st, "Окно продажи заполнено — сначала нажми «Продать»"); return
        st["sell"].append({"cell": cell, "item": wid})
        return
    if L["panel"].collidepoint(e.pos):
        if BUY_BTN.collidepoint(e.pos): _do_buy(g, pl, st)
        elif SELL_BTN.collidepoint(e.pos): _do_sell(g, pl, st)
        return
    close(g)   # клик мимо окна — закрыть


def _player_cells(L):
    """[(ячейка, rect)] всего имущества игрока: рюкзак, руки, ресурсы (id вместо ячейки), экипировка."""
    for i, rect in enumerate(L["bag"]): yield ("b", i), rect
    for i, rect in enumerate(L["hand"]): yield ("h", i), rect
    for rid, rect in L["res"]: yield rid, rect
    for sid, rect in L["equip"]: yield ("e", sid), rect


# ================================================================ отрисовка
def _col(v, default):
    try: return tuple(max(0, min(255, int(x))) for x in v[:3])
    except (TypeError, ValueError, IndexError): return default


def _box(scr, rect, color, border=None, alpha=210):
    s = pg.Surface(rect.size, pg.SRCALPHA)
    pg.draw.rect(s, (*color, alpha), s.get_rect(), border_radius=6); scr.blit(s, rect)
    if border: pg.draw.rect(scr, border, rect, 2, border_radius=6)


def _icon(wid, size):
    """Иконка предмета, вписанная в size (переиспользуем систему иконок инвентаря)."""
    return inventory._icon(wid, size)


def _draw_slot(scr, rect, wid, count=0, hover=False, reserved=False):
    """Ячейка окна: фон, иконка, цена/количество, рамка редкости, подсветка."""
    _box(scr, rect, (26, 29, 44), border=(90, 86, 122), alpha=220)
    if wid:
        inf = inventory.item_info(wid)
        img = _icon(wid, rect.w - 12)
        if img:
            if reserved: img = img.copy(); img.set_alpha(120)
            scr.blit(img, img.get_rect(center=rect.center))
        else:
            pg.draw.polygon(scr, inf["color"], [(rect.centerx, rect.centery - 10), (rect.centerx + 10, rect.centery),
                                                 (rect.centerx, rect.centery + 10), (rect.centerx - 10, rect.centery)])
        pg.draw.rect(scr, inf["color"], rect, 2, border_radius=6)
        if count:
            f = pg.font.SysFont("arial,dejavusans,freesans", 11, bold=True)
            t = f.render("×" + str(count), True, (250, 220, 130))
            scr.blit(t, (rect.right - t.get_width() - 3, rect.bottom - t.get_height() - 2))
    if hover:
        veil = pg.Surface(rect.size, pg.SRCALPHA)
        pg.draw.rect(veil, (255, 255, 255, 26), veil.get_rect(), border_radius=6); scr.blit(veil, rect)
        pg.draw.rect(scr, (255, 230, 150), rect, 2, border_radius=6)


def _button(scr, rect, label, enabled=True):
    col = (46, 78, 52) if enabled else (40, 42, 52)
    brd = (110, 220, 130) if enabled else (80, 80, 95)
    _box(scr, rect, col, border=brd, alpha=235)
    f = pg.font.SysFont("arial,dejavusans,freesans", 15, bold=True)
    t = f.render(label, True, (225, 245, 225) if enabled else (120, 120, 135))
    scr.blit(t, t.get_rect(center=rect.center))


def draw(g):
    """Окно торговли поверх игры (вызывается из Game.draw, пока g.trade_open)."""
    st = g.trade_open; scr = g.scr; pl = g.pl
    with use_char(pl.char_id):
        # затемнение и панель — в стиле окна инвентаря
        veil = pg.Surface((W, VIEW_H), pg.SRCALPHA); veil.fill((5, 5, 14, 170)); scr.blit(veil, (0, 0))
        L = _layout(pl); panel = L["panel"]
        P = inventory.cfg().get("panel") or {}
        pimg = inventory._image(P.get("image"), panel.w, panel.h)
        if pimg: scr.blit(pimg, panel)
        else:
            s = pg.Surface(panel.size, pg.SRCALPHA)
            pg.draw.rect(s, (*_col(P.get("color"), (22, 24, 36)), int(P.get("alpha", 238))), s.get_rect(), border_radius=10); scr.blit(s, panel)
            pg.draw.rect(scr, _col(P.get("border_color"), (120, 110, 160)), panel, 2, border_radius=10)
        font, small = g.font, g.small; mouse = pg.mouse.get_pos()
        n_obj = st["npc"]; d = n_obj.d
        items = npc.trade_items(d)
        pages = max(0, (len(items) - 1) // (PAGE_ROWS * PAGE_COLS))
        st["scroll"] = min(max(0, int(st.get("scroll", 0))), pages)

        # ==== торговец (слева): имя в отдельной рамке, описание, товары
        _box(scr, NAME_BOX, (30, 26, 44), border=(150, 140, 190), alpha=230)
        scr.blit(pg.font.SysFont("arial,dejavusans,freesans", 19, bold=True).render(str(d.get("name") or n_obj.kind), True, (255, 220, 130)),
                 (NAME_BOX.x + 10, NAME_BOX.y + 7))
        desc = inventory._wrap(str(d.get("description") or ""), small, NAME_BOX.w - 4)
        for i, line in enumerate(desc[:3]):
            scr.blit(small.render(line, True, (170, 170, 195)), (NAME_BOX.x, NAME_BOX.bottom + 4 + i * 13))
        scr.blit(font.render("ТОВАРЫ", True, LC), GOODS_LABEL)
        mult = _mult(n_obj)
        hover_info = None
        for i, rect in enumerate(L["goods"]):
            wid = _goods_item(st, i)
            if wid is None: continue
            _draw_slot(scr, rect, wid, hover=rect.collidepoint(mouse))
            f = small.render(str(npc.price_of(wid, mult)), True, GOLD)
            scr.blit(f, (rect.right - f.get_width() - 3, rect.y + 2))
            if rect.collidepoint(mouse):
                inf = inventory.item_info(wid)
                hover_info = f"{inf['name']} — {npc.price_of(wid, mult)} монет (продажа: {npc.sell_price_of(wid)})"
        if pages:
            scr.blit(small.render(f"стр. {st['scroll'] + 1}/{pages + 1}  (колесо — листать)", True, (140, 140, 165)), (28, 362))

        # ==== середина: окно ПОКУПКИ + кнопка, окно ПРОДАЖИ + кнопка
        scr.blit(font.render("ПОКУПКА", True, LC), BUY_LABEL)
        _box(scr, BUY_BOX, (18, 20, 32), border=(96, 92, 130), alpha=190)
        for i, rect in enumerate(L["buy"]):
            e = st["buy"][i] if i < len(st["buy"]) else None
            _draw_slot(scr, rect, e["item"] if e else None, hover=bool(e) and rect.collidepoint(mouse))
            if e:
                f = small.render(str(e["price"]), True, GOLD)
                scr.blit(f, (rect.right - f.get_width() - 3, rect.y + 2))
        total_buy = sum(int(e["price"]) for e in st["buy"])
        scr.blit(small.render(f"Итого: {total_buy} монет", True, GOLD if st["buy"] else (140, 140, 165)), (BUY_BOX.x + 4, BUY_BOX.bottom + 3))
        _button(scr, BUY_BTN, "КУПИТЬ", enabled=bool(st["buy"]))

        scr.blit(font.render("ПРОДАЖА", True, LC), SELL_LABEL)
        _box(scr, SELL_BOX, (18, 20, 32), border=(96, 92, 130), alpha=190)
        for i, rect in enumerate(L["sell"]):
            e = st["sell"][i] if i < len(st["sell"]) else None
            if e and e.get("res"): _draw_slot(scr, rect, e["res"], 1, hover=rect.collidepoint(mouse))
            else: _draw_slot(scr, rect, e["item"] if e else None, hover=bool(e) and rect.collidepoint(mouse))
            if e:
                price = npc.sell_price_of(e["res"] if e.get("res") else e["item"])
                f = small.render("+" + str(price), True, GREEN)
                scr.blit(f, (rect.right - f.get_width() - 3, rect.y + 2))
        total_sell = sum(npc.sell_price_of(e["res"] if e.get("res") else e["item"]) for e in st["sell"])
        scr.blit(small.render(f"Получишь: {total_sell} монет", True, GOLD if st["sell"] else (140, 140, 165)), (SELL_BOX.x + 4, SELL_BOX.bottom + 3))
        _button(scr, SELL_BTN, "ПРОДАТЬ", enabled=bool(st["sell"]))

        # ==== игрок (справа): имя, класс, монеты, рюкзак, руки, склад, экипировка
        _box(scr, PL_NAME, (30, 26, 44), border=(150, 140, 190), alpha=230)
        scr.blit(pg.font.SysFont("arial,dejavusans,freesans", 17, bold=True).render(str(getattr(pl, "name", "") or "Герой"), True, (235, 235, 250)),
                 (PL_NAME.x + 8, PL_NAME.y + 4))
        cls = str((CFG.get("character") or {}).get("name") or "Герой")
        scr.blit(small.render(cls, True, (200, 180, 255)), (PL_NAME.x, PL_CLASS_Y))
        scr.blit(font.render(f"Монеты: {max(0, int(getattr(pl, 'coins', 0) or 0))}", True, GOLD), (PL_NAME.x, PL_COINS_Y))
        used = sum(1 for w in inventory.bag(pl) if w)
        scr.blit(font.render(f"РЮКЗАК  {used}/{len(inventory.bag(pl))}", True, LC), PL_BAG_LABEL)
        for i, rect in enumerate(L["bag"]):
            cell = ("b", i)
            reserved = any(e.get("cell") == cell for e in st["sell"])
            wid = inventory.get(pl, cell)
            _draw_slot(scr, rect, wid, reserved=reserved, hover=bool(wid) and rect.collidepoint(mouse))
            if wid and rect.collidepoint(mouse):
                inf = inventory.item_info(wid)
                hover_info = f"{inf['name']} — продажа: {npc.sell_price_of(wid)} монет" if npc.is_tradable(wid) else f"{inf['name']} — это не товар"
        scr.blit(font.render("В РУКАХ", True, LC), PL_HAND_LABEL)
        for i, rect in enumerate(L["hand"]):
            cell = ("h", i)
            reserved = any(e.get("cell") == cell for e in st["sell"])
            wid = inventory.get(pl, cell)
            _draw_slot(scr, rect, wid, reserved=reserved, hover=bool(wid) and rect.collidepoint(mouse))
            scr.blit(small.render(["ЛКМ", "ПКМ"][i], True, (255, 230, 150)), (rect.x + 4, rect.y + 2))
            if wid and rect.collidepoint(mouse): hover_info = f"{inventory.item_info(wid)['name']} — продажа: {npc.sell_price_of(wid)}"
        scr.blit(font.render("СКЛАД", True, LC), PL_RES_LABEL)
        for rid, rect in L["res"]:
            cnt = inventory.resource_count(pl, rid)
            if cnt <= 0: continue
            reserved = sum(1 for e in st["sell"] if e.get("res") == rid)
            _draw_slot(scr, rect, rid, cnt, hover=True, reserved=reserved)
            if rect.collidepoint(mouse): hover_info = f"{inventory.item_info(rid)['name']} ×{cnt} — клик: продать 1 за {npc.sell_price_of(rid)}"
        scr.blit(font.render("ЭКИПИРОВКА", True, LC), PL_EQ_LABEL)
        for sid, rect in L["equip"]:
            cell = ("e", sid)
            reserved = any(e.get("cell") == cell for e in st["sell"])
            wid = inventory.get(pl, cell)
            _draw_slot(scr, rect, wid, reserved=reserved, hover=bool(wid) and rect.collidepoint(mouse))
            if wid and rect.collidepoint(mouse): hover_info = f"{inventory.item_info(wid)['name']} — продажа: {npc.sell_price_of(wid)}"

        # ==== сообщение / подсказка (2 строки под окнами середины)
        msg = st.get("msg")
        hint = "Клик по товару — купить · клик по своему предмету — продать · Tab/Esc — закрыть"
        if msg and pg.time.get_ticks() < msg[1]:
            for i, line in enumerate(inventory._wrap(msg[0], font, SELL_BOX.w)[:2]):
                scr.blit(font.render(line, True, msg[2]), (MSG_POS[0], MSG_POS[1] + i * 17))
        else:
            for i, line in enumerate(inventory._wrap(hover_info or hint, small, SELL_BOX.w)[:2]):
                scr.blit(small.render(line, True, GOLD if hover_info else (160, 220, 175)), (MSG_POS[0], MSG_POS[1] + 3 + i * 13))
