Ты — pi-агент в проекте DEAD ROOMS (Python/Pygame-ce рогалик, каталог C:/Users/artem/Desktop/DEAD_ROOMS).
ЗАДАЧА: создай НОВЫЙ модуль checkpoint.py — чекпоинты (автосохранение + восстановление HP/маны + точка возрождения после смерти), и добавь их сбор в maps.py.

СНАЧАЛА изучи: maps.py (класс GameMap ~153: __init__, cells(), find(), spawn(); docstring про легенду в начале файла), core.py (CFG, T=32, SETTINGS, read_json, tile), main.py ТОЛЬКО ЧИТАЙ (Game.go ~599, place ~614, step ~723, Player ~73, fx ~ core.FX; main.py РЕДАКТИРОВАТЬ ЗАПРЕЩЕНО), save_io.py (save/restore, SAVES_DIR).

Формат чекпоинта на карте: символ "O" в сетке rows, в ОБЩЕЙ легенде data/maps.json уже добавлено "O": {"type": "empty", "checkpoint": true} (главным агентом). Клетка физически пустая.

ЧАСТЬ 1 — maps.py (небольшая правка):
1. В GameMap.__init__ после s.mechs = mechs.create(s) добавь: s.checkpoints = checkpoint.collect(s) (импорт checkpoint вверху файла; циклического импорта нет: checkpoint.py НЕ должен импортировать maps.py).
2. В docstring модуля maps.py (блок описания легенды, где описаны player/mob/boss/item/light) добавь строку:
   "checkpoint — true: чекпоинт (символ O): автосохранение забега, восстановление HP/маны, точка возрождения".

ЧАСТЬ 2 — НОВЫЙ модуль checkpoint.py. Контракт (строго; его вызовут main.py и multiplayer.py):

```python
def freeze_time() -> float          # SETTINGS.get("checkpoint_freeze_seconds", 10.0), clamp 0..120
def collect(r) -> list[dict]        # по клеткам карты r (r.cells(), запись легенды e.get("checkpoint")):
                                    # [{"rect": pg.Rect(c*T, r*T, T, T), "x": центр X px, "ground": (r+1)*T}]
def activate(g, pl, r, cp) -> None  # активация чекпоинта cp комнаты r:
                                    #   pl.cp = (r.id, int(cp["x"]), int(cp["ground"]))
                                    #   pl.hp = pl.maxhp; pl.refresh_mana(True); pl.mana = pl.maxmana
                                    #   g.fx.text("Чекпоинт: здоровье и мана восстановлены", cp x, ground - 60)
                                    #   если нет сети (getattr(g,"net",None) is None): ленивый import save_io;
                                    #     try: save_io.autosave(g) except Exception as e: print("[чекпоинт] не удалось сохранить:", e)
                                    #   повторная активация не спамит: в cp храни "until" (pg.time.get_ticks()+2000),
                                    #   пока не истёк — activate ничего не делает (кроме случая, когда cp["until"] отсутствует)
def update(g, dt) -> None           # ОДИНОЧНАЯ игра: тик заморозки для g.pl (freeze_tick) + активация:
                                    #   если pl жив (hp>0) и пересекается с rect чекпоинта текущей комнаты g.room — activate
def tick(pl, dt) -> None            # pl.frozen = max(0.0, pl.frozen - dt); pl.inv = max(pl.inv, pl.frozen) (кристалл = неуязвимость)
def freeze(pl, seconds=None) -> None  # pl.frozen = float(seconds or freeze_time()); pl.inv = max(pl.inv, pl.frozen)
def respawn(g) -> None              # СМЕРТЬ в одиночной игре (вызывается из main.step вместо старого «if pl.hp <= 0: return»):
                                    #   pl = g.pl; cp = getattr(pl, "cp", None)
                                    #   если cp и cp[0] в g.camp.map_defs: g.go(cp[0], None); pl.x = cp[1] - pl.w/2; pl.y = cp[2] - pl.h
                                    #     (после go — обнулить pl.vx/pl.vy; h подрезать как в g.place: если pl.h != pl.H0: pl.y -= pl.H0-pl.h; pl.h = pl.H0)
                                    #   иначе (чекпоинта ещё не было): g.place(*g.respawn)
                                    #   pl.hp = pl.maxhp; pl.refresh_mana(True); pl.mana = pl.maxmana; freeze(pl)
                                    #   pl.atk=None; pl.grab=None; pl.channel=None; pl.hold=None; pl.stun=0
                                    #   g.fx.text("Ты погиб — возвращение к чекпоинту", pl.cx, pl.y - 40)
                                    #   если g.net — ничего не делай (в сети смерть считает хост, multiplayer.py)
def draw_room(v, r, t_ms) -> None   # кристалл каждого чекпоинта комнаты: гранёный «кристалл» (pg.draw.polygon, бирюза (110,225,255)),
                                    #   высота ~44px от ground вверх, пульсация яркости по t_ms; если это текущая точка возрождения героя
                                    #   (r.id и координаты совпадают с pl.cp из g — пл возьми из замыкания? НЕТ: сигнатура (v, r, t_ms, pl=None)) —
                                    #   рисуй ярче + мягкое свечение (полупрозрачный круг). Если есть картинка assets/icons/checkpoint.png —
                                    #   используй anim.sprite (как в maps.py) поверх/вместо полигона.
def draw_crystal(v, pl, t_ms) -> None  # замороженный игрок: полупрозрачный (alpha ~120+пульс) бирюзовый кристалл-ромб,
                                    #   охватывающий pl.rect (чуть больше), грань-блик, редкие искры (2-3 точки по t_ms)
```

ТРЕБОВАНИЯ:
- Только data-driven: никаких новых json обязывать; время заморозки берётся из SETTINGS (data/settings.json), ключ "checkpoint_freeze_seconds".
- Держи стиль проекта: компактный код, русские docstring, комментарии по-русски. Модуль ~150-220 строк.
- НЕ редактируй: main.py, multiplayer.py, save_io.py, map_editor.py, core.py.
- save_io.autosave() появится от другого агента — просто вызывай его в try/except (ленивый импорт внутри функции).
- В конце прогони headless-проверку: SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy ./.venv/Scripts/python.exe -c "import checkpoint, maps; print('ok')" и мини-сценарий: создать Game из main (new_game), вручную вставить символ O в текущую карту (data меняет rows в CFG map_defs), F5-перезагрузка не нужна — достаточно core.reload_data() + new_game; проверить collect нашёл чекпоинт, activate лечит и создаёт файл сейва (потом удалить его!), tick уменьшает frozen, respawn телепортирует. Игровые тестовые сейвы из папки saves/ УДАЛИ после проверки.
- Отчёт: multiagent/out/cp_core.md — что сделано, контракт, как протестировано.
