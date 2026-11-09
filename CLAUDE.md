# DEAD ROOMS — заметки для работы над кодом

2D-платформер в духе Dead Cells на **pygame-ce**. Карты — экраны, нарисованные вручную символами
в `data/maps/*.json`. Почти весь контент (физика, оружие, мобы, карты, навыки, герои, босс, свет)
вынесен в `data/*.json` и `assets/*.json` — **код трогать не нужно**, чтобы менять контент.
`F5` в игре перезагружает все данные и картинки на лету.

Подробная инструкция по контенту для пользователя — в `README.md` (большой, на русском).
Этот файл — техническая карта кода для меня.

> **ПРАВИЛО: держать этот референс в синхроне.** Когда я меняю код (новый модуль, класс,
> реестр-декоратор, поле в data/*.json, перенос логики, смена управления и т.п.) — сразу
> обновляю соответствующий раздел CLAUDE.md в той же задаче.

## Запуск и сборка
- Из исходников: `uv run main.py` (зависимости в `pyproject.toml` / `uv.lock`, нужна pygame-ce).
- Редактор карт: `python map_editor.py` или `launch_map_editor.bat` (использует только `tkinter`).
- Сборка EXE: `build_exe.bat` (`uv sync` + `uv run pyinstaller DEAD_ROOMS.spec`) → `dist/DEAD_ROOMS.exe`.
  - `make_icon.py` собирает `.ico` из `assets/app/icon.png` для PyInstaller.
  - Рядом с EXE кладутся редактируемые `dist/data` и `dist/assets` — они **приоритетнее** встроенных
    (см. `core.FROZEN` / `BASE` / `RESOURCE_BASE`).

## Раскладка модулей (всего ~6200 строк)

| Файл | Строк | За что отвечает |
|---|---|---|
| `main.py` | ~1130 | Класс `Player` (физика/бой/мана/опыт; `use_skill` делегирует в `spells.cast`; `channel`/`skill_held`/`move_input`/`airborne()` — для удерживаемых заклинаний; `hold`/`hold_pool`/`hold_rest`/`hold_latch`/`hold_view` — для «потоков» (`spells.hold_update` зовётся из `Player.update`, `swap_skill` и хват босса останавливают поток); `Game.skill_held()` — зажата ли клавиша навыка), класс `Game` (главный цикл, состояния, меню, рендер, ввод, хелперы `_draw_beam/_draw_bolt/_draw_flash` для эффектов заклинаний). Точка входа. |
| `core.py` | ~195 | Фундамент: пути (`DATA`/`ASSETS`), глобальный `CFG`, `reload_data()`, система персонажей (`apply_character`/`use_char`), базовое физ-тело `Body`, `FX` (включая `beam`/`bolt`/`flash` для молний), мелкие утилиты (`sign`, `tile`, `solid`...). |
| `spells.py` | ~390 | Заклинания/активные навыки игрока. Реестр `@spell("тип")`: `dash`, `nova`, `heal`, `shield`, `projectile`, `chain_lightning`, `strike_area`, а также телекинез инженера `telekinesis` (притянуть дальних / оттолкнуть ближних врагов и предметы в области), `telekinesis_cone` (оттолкнуть всех в конусе перед собой), `telekinesis_hold` (оглушить и держать ближайшего к курсору; удерживаемый каст — см. ниже). Телекинез дотягивается до предметов через `pl.drops` (ставится в `Game.step`/`HostSession.step`); `_shove()` толкает моба без урона. `cast()` — проверка маны/кулдауна + вызов эффекта (в `a` добавляется `_sid` — id навыка); `spellbook()`/`active_skills()`/`ready()` — для окна мага. `icon_path(sid, a)` — поиск иконки (поле `icon` → `icons/skill_<id>.png` → `icons/<id>.png`). `cast_frames(sid, a)` — кадры анимации применения навыка (поле `cast_anim` → `skills/<id>/cast` → `skills/<id>/cast.png`), рисуются в `Player.draw`; нет кадров — процедурная вспышка. `projectile_spec(a)` — вид снаряда заклинания: тип + поля `projectile_*` (`PROJECTILE_FIELDS`) + автоподхват `assets/projectiles/<id навыка>.png` или папки кадров. **Удерживаемые заклинания (`"channel": true` в skills.json, как ульта Bane в Dota 2):** `cast()` лишь запускает каст (`begin_channel` → `pl.channel = {sid, t, max, ...}`), перезарядка стартует в `channel_stop()`, а не при нажатии; пока герой колдует, `Player.update` зовёт `channel_update()` — она проверяет прерывания (`_channel_break`: отпущена клавиша навыка `pl.skill_held`, A/D, S/↓, прыжок, перекат, атака, падение/лестница/захват) и лимит `duration`, затем хук `tick`. Урон прерывает каст из `Player.hit`. `@spell`-функция удерживаемого заклинания возвращает `False` (не вышло — мана и КД не тратятся) или словарь стартового состояния; хуки регистрируются `channel("тип", tick=..., end=...)` (`CHANNELS`). Старт требует стоять на земле без нажатых A/D/S (`_channel_blocker`). Пока идёт каст, `cast()`/`ready()` игнорируют новые нажатия, а `swap_skill` заблокирован. **Заклинания-«потоки» (`"hold": true`, третий режим):** клавишу держат в любой момент (бег/прыжок/удары/урон не прерывают); у навыка запас `duration` сек (`pl.hold_pool[sid]`, нет записи = полный), пока клавиша зажата — запас тратится, мана по `mana_cost` **в секунду**; отпустил — `hold_update` возвращает запас с того значения, на котором остановились, за `recharge` сек с нуля (по умолчанию = `cooldown`; пауза `recharge_delay`). `cast()` для `is_hold(a)` зовёт `hold_start` (кулдауна нет, нужен запас и мана ≥ `mana_cost × HOLD_MIN_START`), каждый кадр `Player.update` зовёт `hold_update` (отдых всех потоков + ведение активного `pl.hold`), `hold_stop(why)` — конец (release/empty/mana/target/grab/swap; при empty/mana/target и зажатой клавише ставится `pl.hold_latch` — заново только после отпускания). Эффект: хуки `channel(...)` типа, если есть (`tick`/`end` общие с channel), иначе `@spell`-функция повторяется каждые `interval` сек. Сеть: `hold_net(pl)` / `hold_net_apply(pl, hd, hr)` — хост шлёт `"hd": [sid, t]` и `"hr": {sid: запас}`, у клиента `pl.hold_view = True` и поток только «картинка» (`pl.hold["view"]`). |
| `status.py` | ~80 | Статусные эффекты мобов: `freeze`/`stun`/`burn` (+ `invisible` — делегируется в `invisibility.py`, действует и на игрока). `apply(mob, eff, fx)`, `tick(mob, dt, w)`, `tint(mob)`. Эффект = словарь `{"freeze":2.0}` / `{"stun":2.0}` / `{"burn":{"time":3,"dps":10}}`. Боссы иммунны к контролю (`cc_immune`). |
| `invisibility.py` | ~190 | Эффект **невидимости** игрока и мобов (в т.ч. босса). Состояние `e.invis` (`None` или `{t, tr, brk, age}`): `apply(e, spec, fx)` (spec: `True` / секунды / `{time, transparency, break_on_attack}`), `clear`, `on_attack`, `tick`, `is_invisible`; видимость для мобов — `visible_only`/`pick_target`; отрисовка — `alpha(e)` (плавность `fade` + мигание `warn`) и `ghost(v, rect, draw, a)` (рисует `draw()` как обычно и подмешивает результат к фону с альфой — работает с любым кодом рисования); сеть — `net_pack`/`net_apply`. Настройки — `data/invisibility.json` (`CFG["invisibility"]`: `transparency`, `player_transparency`, `mob_transparency`, `fade`, `warn`, `break_on_attack`). |
| `maps.py` | 454 | Загрузка карт, сетка мира (`pos`/`world_links`), класс `GameMap` (сетка, спавн, выходы, фон), `Campaign` (круги/масштаб), `check()` — валидация карт. |
| `mob.py` | 252 | Класс `Mob` (= тело + движение + атаки + анимации), `spawn_boss`, `Corpse`. |
| `movement.py` | 156 | Паттерны движения мобов. Реестр через `@movement("имя")`: `chase`, `keep_distance`, `loop`, `stand`. |
| `attacks.py` | 151 | Атаки мобов. Реестр `@attack("имя")`: `melee`, `circle`, `shoot`, `leap`. Базовый `Attack` с фазами windup→active→recovery. |
| `projectiles.py` | 145 | Класс `Proj`, типы из `projectiles.json`. Реестры `@behavior("ключ")` (каждый кадр) и `@on_death("ключ")`: `homing`, `accel`, `wave`, `split`. `volley()` — веер. |
| `crossbow.py` | ~190 | Мини-арбалеты Тени (поле `crossbows` героя в `characters.json`). ЛКМ — арбалет 0, ПКМ — арбалет 1, перезарядка у каждого своя (`pl.xb_cd[i]`), стрельба на бегу/в прыжке (`Player.update`: блок `crossbow.enabled()`, буфер `pl.buf["a1"/"a2"]`, нажатие ждёт конца перезарядки; нет маны — `mana_flash`). Виды снарядов — навыки `category: "ammo"` в `skills.json` (`projectile`, `damage`, `mana_cost`, `cooldown` = пауза между выстрелами арбалета, `count`/`spread`), список порядка — `crossbows.ammo`; у каждого арбалета своя «книга» `book(pl, i)` (пред./текущий/след.), листается `swap(pl, i, ±1)` (действия `xb0_prev/xb0_next/xb1_prev/xb1_next` в `Game.ACTIONS`, клавиши `ammo1_*`/`ammo2_*` в `CONTROL_DEFAULTS`: 1/2 и 3/4). `fire()` берёт точку вылета из `muzzle()`, цену — из `mana_cost()` (пассивки `mana_cost_reduction` с `mini_crossbow` в `weapons`), зовёт `projectile_spec` и `volley`. Герой в `Player.update` поворачивается к курсору; `draw(v, pl, i)` рисует арбалет в руке (второй — за телом, в `Player.draw`), с отдачей. **Стрела с нитью** (`ammo_harpoon`, поле `hook` у вида снаряда): гарпун — не `Proj`, а своя симуляция в `pl.hooks[i]` (так работает и предсказание клиента): `hooks_update` (полёт шагами по 6 px, зацеп за `solid`-тайл, моб — удар и конец), `rope_step` (перед `Body.move`: подтяжка до `swing_len`, пока зажата кнопка — до `min_len`, раскачивание A/D, ограничение длины верёвки подправкой скорости), `trigger` (один гарпун на арбалет, `xb_lock` — ждём отпускания кнопки), `release_all` (Пробел/перекат/лестница/смена комнаты), `draw_hooks`. «Зажата кнопка» определяется по буферу `pl.buf` (в `Player.update`: `buf > buffer - 1.5*dt`). Сеть: `net_pack`/`net_apply`, ключ `"xb"` в снимке игрока (индекс снаряда, перезарядка, гарпун `[состояние, x, y, длина]`). |
| `weapon.py` | 90 | Отрисовка оружия в руке (`held_pose`/`draw_held`), иконки, цена маны (`mana_cost`/`mana_hit`). |
| `characters.py` | 345 | Экран выбора героя и лобби мультиплеера (UI из `assets/character_select.json`). |
| `hud.py` | ~260 | Нижний HUD: иконки (герой/оружие1/оружие2 + активный навык), полоски HP/маны, индикатор опыта, полоса босса. У мага (`spellcaster`) вместо оружия — окно `spellbook()` из трёх заклинаний (пред./текущее/след.); у арбалетчика (`crossbows`, Тень) — два таких окна `ammo_window()` (ЛКМ слева, ПКМ справа; на текущем снаряде сектор перезарядки, цена выстрела и точка состояния гарпуна) + слот Q правее (`skill_slot(..., pos)`). Положение и размер окон — ключ раскладки `"ammo"` ([x, y верха крупной ячейки, её размер]; `ammo_geom()`), в редакторе HUD (F2) их двигают и масштабируют колесом/+/- (`edit_keys()`/`edit_rect()`; у арбалетчика вместо рамок оружия — рамка окон). `channel_overlay()` рисует на иконке колдуемого удерживаемого заклинания убывающий сектор, оставшиеся секунды и пульсирующую рамку (вместо кулдауна; `hold_overlay()` — то же для «потоков»: сектор запаса, секунды, пульсирующая рамка, цена маны подписана `N/с`). |
| `devtools.py` | ~230 | Инструменты разработчика. `DevMenu` — меню на **F6** (одиночная игра, игра на паузе): выдать опыт/HP/ману, заспавнить/убрать тренировочного манекена, сбросить его счётчики. `Dummy(Mob)` — манекен: стоит на месте, неубиваем (свойство `hp` не даёт здоровью убывать, а само уменьшение пишет в счётчики — ловит и удары, и горение, и пули), не отбрасывается и не сбивается ударами, но подвержен стану/заморозке/горению (`status.py`) и толчкам заклинаний; табличка над ним (`draw_overlay`, рисуется после освещения) показывает последний удар, сумму, DPS за 5 с и эффекты. Описание манекена `DEF` подставляется в `CFG["mobs"]` только на момент создания (иначе `maps.py` выбрал бы его случайным мобом). **Внешность — через ассеты** (по образцу `assets/boss/`): папка `assets/dummy/` — необязательный `dummy.json` (`CFG["dummy"]`, читается в `core.reload_data`, F5 обновляет и уже стоящих манекенов; поля `w`,`h` — хитбокс только для новых, `draw`,`offset`,`skin`,`hurt_time`,`anims`,`anim_fps`; `hp`/`xp`/`move`/`attacks` игнорируются, см. `LOCKED`), одиночный скин `dummy.png` и папки кадров `idle/ hurt/ stun/ frozen/ burn/` (`Dummy.anim_states` + `anim.mob_frame`, запасной порядок: frozen→stun→idle→скин→нарисованное чучело `_draw_default`; `assets/dummy/_template.png` — шаблон-болванка 4×). `hostile(mobs)` — мобы без манекенов: по ним считаются зачистка комнаты и замки дверей. |
| `lighting.py` | 266 | Освещение: источники света на картах, темнота/ambient, мягкие пятна, мерцание, искры, ореолы. Реестр пресетов света. |
| `anim.py` | ~110 | Загрузка PNG и серий-анимаций с кэшем (`_IMG`/`_FRAMES`/`_ANIM`). `sprite()`, `frames()`, `mob_frame()`, `ASSETS_EXISTS()` (есть ли необязательный файл). `clear_cache()` на F5. |
| `boss_hands.py` | 605 | Босс Моргарт: голова + 4 руки (`Hand`/`HandSet`). Реестр атак рук `@hand_attack("имя")`: `thrust`, `slam`, `sweep`, `grab`, `clap`. Отрисовка босса. |
| `multiplayer.py` | 1347 | LAN до 4 игроков. `Server`/`Conn`/`Finder` (сеть), `HostSession` (считает весь мир) / `ClientSession` (шлёт ввод, рисует снимки с интерполяцией), меню мультиплеера. |
| `map_editor.py` | 631 | Отдельное tkinter-приложение. Рисование карт, панель света, панель рук Моргарта. Пишет `data/maps/<id>.json` + `order`. Вкладки: «Карты», «Навыки» (`SkillEditor`; у активного навыка список «Вид каста» — обычный / `channel` / `hold`, `mode_key()`, `CAST_MODES`, поля потока `recharge`/`recharge_delay`/`interval` видны только в режиме потока), «Мобы» (`mob_editor.MobTab`, подключается в `__main__` через `_build_mobs_tab`). |
| `make_icon.py` | 56 | Сборка `.ico` из PNG для EXE. |
| `make_crossbow_textures.py` | ~190 | Генератор временных текстур арбалетов Тени (Pillow): `weapons/mini_crossbow.png`, болты `projectiles/xbow_arrow.png`, `xbow_fire/1..3.png`, `xbow_heavy.png`, иконки `icons/ammo_*.png`. Без `--force` не трогает существующие файлы. |
| `make_spell_textures.py` | ~290 | Генератор временных текстур навыков (Pillow): иконки `icons/skill_<id>.png`, снаряды-анимации `projectiles/<id>/1..4.png` и анимации каста `skills/<id>/cast/1..6.png` (телекинез инженера). Без `--force` не трогает существующие файлы. Запуск: `uv run --with pillow make_spell_textures.py`. |

## Как всё связано (центральные механизмы)

**`core.CFG` — единый словарь конфигов.** `reload_data()` читает все `data/*.json` в `CFG[имя]`,
плюс `boss` (из `assets/boss/boss.json`, моб кладётся в каталог как `__boss__`), `skill_tree`,
`skill_menu`, карты (`map_defs`), персонажей. Босс-моб и размеры мировой сетки (`COLS`/`ROWS`)
вычисляются здесь же. F5 → `reload_data()` + `anim.clear_cache()`.

**Система персонажей (core.py).** У каждого героя свои правки `player`/`weapons`/`skills`/
`skill_tree`/`skill_menu`. `apply_character(cid)` применяет их в `CFG`; `use_char(cid)` —
контекст-менеджер для временного переключения (нужно в мультиплеере, где у игроков разные герои
одновременно — см. `_VIEWS` кэш). `char_def`/`char_look`/`char_player_cfg` достают данные героя.

**Реестры-декораторы — главный паттерн расширения.** Новый тип контента = функция/класс с
декоратором, параметры в JSON. Не надо менять диспетчер:
- `@movement("имя")` в `movement.py`
- `@attack("имя")` в `attacks.py`
- `@behavior("ключ")` / `@on_death("ключ")` в `projectiles.py`
- `@spell("тип")` в `spells.py` (активные навыки/заклинания игрока)
- `@hand_attack("имя")` в `boss_hands.py`
- пресеты света в `lighting.py`

**Невидимость (`invisibility.py`).** Один эффект для `Player` и `Mob`. Наложение: навык `type: "invisibility"` (`spells.py`), статус `{"invisible": ...}` в `status.apply` (любой `effect`), поле `invisible` у моба в `mobs.json` (читает `Mob.__init__`), код `invisibility.apply`. Тик — `Player.update` / `status.tick`. Мобы не замечают невидимого: `movement.look` сбрасывает `m.aggro`, если цель `w.pl` невидима; босс — `seen_players(w)` в `Mob.update` (агр сбрасывается, если видимых нет), цели рук — `Hand.targets`; вражеский `homing` пропускает невидимых; в мультиплеере хост выбирает `w.pl` через `invisibility.pick_target`. Зоны ударов и контакт по-прежнему бьют всех (`players_of`). Сброс при атаке: `Player.start_attack` (после проверки маны), `spells.cast`/`hold_start` (по `invisibility.breaks(a)`: всё, кроме `dash/heal/shield/invisibility`, либо `breaks_invisibility` в навыке), `Mob.start_attack`, атаки рук босса. Рисование: `Player.draw`/`Mob.draw`/`Dummy.draw` заворачивают тело в `invisibility.ghost(...)`. Сеть: снимок игрока `"iv"`, строка моба — последний элемент; клиент принимает в `apply_stats`/`apply_mobs` (`net_apply`, свой предсказываемый герой короткое время доверяет локальному состоянию).

**Фазы атак** везде одинаковы: `windup` (замах) → `active` (удар) → `recovery` (отдых), плюс
`cooldown`. Касается `attacks.Attack`, оружия игрока, `boss_hands.HandAttack`.

**Сетка мира.** У каждой карты `"pos": [x,y]`. Выходы `L/R/U/D` ведут к соседней клетке; `maps.world_links`/
`target_of`/`resolve` считают переходы. `check()` валидирует (две карты в клетке, выход в пустоту,
нет парного выхода) — ошибки красным в игре и в консоли.

**Главный цикл — `Game` (main.py).** Состояния через флаги: `menu_mode` (`start`/`pause`/`None`),
`level_menu` (выбор навыка при лвл-апе), `show_world` (карта мира, пауза), `net` (None=одиночка,
иначе Host/Client сессия). Ключевые методы: `new_game`, `go`/`take_exit` (переходы между картами),
`place`, `clear` (зачистка + спавн босса на последней карте круга), `gain_xp`/`choose_level_skill`, `pickup`.

**Мультиплеер.** Хост считает ВСЁ (мир, мобов, пули, всех игроков). Клиенты шлют только ввод,
получают снимки и интерполируют чужих (свой герой считается локально для отзывчивости).
`content_sig()` сверяет, что у всех одинаковые `data/`. Порты: TCP 5555 (игра), UDP 5556 (поиск). Ввод игрока — `NetKeys` из 6 бит `[влево, вправо, вверх, вниз, пробел, клавиша навыка зажата]`; удерживаемый каст целиком считает хост, в снимке он едет как `"ch": [sid, t, max]`, а у клиента `Player.channel` — только картинка (`"view": True`) для HUD/анимации. Поток (`"hold": true`) так же считает хост; в снимке игрока `"hd": [sid, t]` (активный поток) и `"hr": {sid: запас}` (у неполных).

## Данные (`data/`)
`player.json` (физика, мана, регенерация, полоски) · `weapons.json` (combo, projectile, slot, mana) ·
`mobs.json` (hp, move, attacks, anims, xp, light; `cc_immune` — иммунитет к заморозке/оглушению; `invisible` — моб невидим: `true`/секунды/`{time, transparency, break_on_attack}`) ·
`invisibility.json` (процент прозрачности для всех/игрока/мобов, `fade`, `warn`, `break_on_attack`) ·
`projectiles.json` (у типа пули можно задать `effect`, напр. `{"freeze":2.0}` — накладывается при попадании) ·
`skills.json` (активные: dash/nova/heal/shield/invisibility (мантия невидимости) + заклинания мага chain_lightning/strike_area/projectile
+ телекинез инженера telekinesis/telekinesis_cone/telekinesis_hold; пассивки max_hp/damage/move_speed;
`mana_cost` (у `hold` — мана в секунду), `cooldown`, `effect`, `color`, `icon`; режимы использования: обычный / `"channel": true` (стоя) / `"hold": true` (поток с запасом: `duration`, `recharge`, `recharge_delay`, `interval`; пример — `fire_stream` у мага); у активного навыка можно задать анимацию каста:
`cast_anim` — папка/файл кадров, `cast_size` [ш,в], `cast_offset` [dx,dy], `cast_animation` — длительность, сек) ·
`characters.json` (5 героев: stats/weapons/skills/tree/overrides; `spellcaster: true` — чистый заклинатель:
нет оружия/подбора, ЛКМ или Q кастует текущее заклинание, C/V листают книгу из трёх; у мага и инженера это включено, weapons: [] — оружие им вообще не выпадает; `crossbows: {...}` — арбалетчик (Тень): два мини-арбалета вместо оружия, виды снарядов — навыки `category: "ammo"` в `skills.json`, см. `crossbow.py`) ·
`maps.json` (order, общая legend, настройки, lighting, world) · `maps/<id>.json` (rows, pos, legend,
mob_pool, фон, свет, `morgart_layout`) · `settings.json` (fullscreen, mouse_aim, menu_layout,
last_character, player_name). `maps/_*.json` — заготовки, не читаются.

## Ассеты (`assets/`)
`player/` · `mobs/<id>/<состояние>/*.png` · `projectiles/` · `weapons/` · `icons/` · `environment/`
(wall/platform/ladder/spikes варианты, выбор по координатам клетки) · `backgrounds/` · `menu/` ·
`characters/<id>/` (`character.json` + спрайты + `skill_menu.json`) · `boss/` (`boss.json` + спрайты
головы и рук) · `ui/` · `app/icon.png`. JSON-конфиги оформления: `skill_tree.json`, `skill_menu.json`,
`character_select.json`, `boss/boss.json`.

Все анимации рисуются **лицом вправо** (игра отражает сама). Нет картинки — рисуется цветной
прямоугольник/круг (fallback), игра не падает.

## Управление (для тестов)
A/D бег · Space/W прыжок · S+Space спрыгнуть · ЛКМ оружие1 / ПКМ оружие2 (зажать — комбо) ·
K/Shift перекат (неуязвим) · E подобрать · Q навык (удерживаемые `channel`, напр. захват инженера, работают, пока Q зажата и герой стоит на месте; «потоки» `hold` — пока Q зажата, хоть на бегу, пока есть запас), C/V смена навыка · E подобрать · R рестарт ·
M карта мира · **F5 перезагрузка данных** · **F6 меню разработчика** · F4 сетка клеток · F3 хитбоксы / редактор кнопок меню ·
F11 полный экран. Персонаж целится в курсор (`mouse_aim` в settings.json).

## Git
Проект под git (`.git` есть, `.gitignore` исключает dist/build/кэш). На момент заметок —
активная разработка (многие файлы правлены 2026-11-02).
