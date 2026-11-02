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
| `main.py` | ~1130 | Класс `Player` (физика/бой/мана/опыт; `use_skill` делегирует в `spells.cast`), класс `Game` (главный цикл, состояния, меню, рендер, ввод, хелперы `_draw_beam/_draw_bolt/_draw_flash` для эффектов заклинаний). Точка входа. |
| `core.py` | ~195 | Фундамент: пути (`DATA`/`ASSETS`), глобальный `CFG`, `reload_data()`, система персонажей (`apply_character`/`use_char`), базовое физ-тело `Body`, `FX` (включая `beam`/`bolt`/`flash` для молний), мелкие утилиты (`sign`, `tile`, `solid`...). |
| `spells.py` | ~230 | Заклинания/активные навыки игрока. Реестр `@spell("тип")`: `dash`, `nova`, `heal`, `shield`, `projectile`, `chain_lightning`, `strike_area`. `cast()` — проверка маны/кулдауна + вызов эффекта; `spellbook()`/`active_skills()`/`ready()` — для окна мага. |
| `status.py` | ~75 | Статусные эффекты мобов: `freeze`/`stun`/`burn`. `apply(mob, eff, fx)`, `tick(mob, dt, w)`, `tint(mob)`. Эффект = словарь `{"freeze":2.0}` / `{"stun":2.0}` / `{"burn":{"time":3,"dps":10}}`. Боссы иммунны к контролю (`cc_immune`). |
| `maps.py` | 454 | Загрузка карт, сетка мира (`pos`/`world_links`), класс `GameMap` (сетка, спавн, выходы, фон), `Campaign` (круги/масштаб), `check()` — валидация карт. |
| `mob.py` | 252 | Класс `Mob` (= тело + движение + атаки + анимации), `spawn_boss`, `Corpse`. |
| `movement.py` | 156 | Паттерны движения мобов. Реестр через `@movement("имя")`: `chase`, `keep_distance`, `loop`, `stand`. |
| `attacks.py` | 151 | Атаки мобов. Реестр `@attack("имя")`: `melee`, `circle`, `shoot`, `leap`. Базовый `Attack` с фазами windup→active→recovery. |
| `projectiles.py` | 145 | Класс `Proj`, типы из `projectiles.json`. Реестры `@behavior("ключ")` (каждый кадр) и `@on_death("ключ")`: `homing`, `accel`, `wave`, `split`. `volley()` — веер. |
| `weapon.py` | 90 | Отрисовка оружия в руке (`held_pose`/`draw_held`), иконки, цена маны (`mana_cost`/`mana_hit`). |
| `characters.py` | 345 | Экран выбора героя и лобби мультиплеера (UI из `assets/character_select.json`). |
| `hud.py` | ~260 | Нижний HUD: иконки (герой/оружие1/оружие2 + активный навык), полоски HP/маны, индикатор опыта, полоса босса. У мага (`spellcaster`) вместо оружия — окно `spellbook()` из трёх заклинаний (пред./текущее/след.). |
| `lighting.py` | 266 | Освещение: источники света на картах, темнота/ambient, мягкие пятна, мерцание, искры, ореолы. Реестр пресетов света. |
| `anim.py` | 105 | Загрузка PNG и серий-анимаций с кэшем (`_IMG`/`_FRAMES`/`_ANIM`). `sprite()`, `frames()`, `mob_frame()`. `clear_cache()` на F5. |
| `boss_hands.py` | 605 | Босс Моргарт: голова + 4 руки (`Hand`/`HandSet`). Реестр атак рук `@hand_attack("имя")`: `thrust`, `slam`, `sweep`, `grab`, `clap`. Отрисовка босса. |
| `multiplayer.py` | 1347 | LAN до 4 игроков. `Server`/`Conn`/`Finder` (сеть), `HostSession` (считает весь мир) / `ClientSession` (шлёт ввод, рисует снимки с интерполяцией), меню мультиплеера. |
| `map_editor.py` | 631 | Отдельное tkinter-приложение. Рисование карт, панель света, панель рук Моргарта. Пишет `data/maps/<id>.json` + `order`. |
| `make_icon.py` | 56 | Сборка `.ico` из PNG для EXE. |

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
`content_sig()` сверяет, что у всех одинаковые `data/`. Порты: TCP 5555 (игра), UDP 5556 (поиск).

## Данные (`data/`)
`player.json` (физика, мана, регенерация, полоски) · `weapons.json` (combo, projectile, slot, mana) ·
`mobs.json` (hp, move, attacks, anims, xp, light; `cc_immune` — иммунитет к заморозке/оглушению) ·
`projectiles.json` (у типа пули можно задать `effect`, напр. `{"freeze":2.0}` — накладывается при попадании) ·
`skills.json` (активные: dash/nova/heal/shield + заклинания мага chain_lightning/strike_area/projectile;
пассивки max_hp/damage/move_speed; `mana_cost`, `cooldown`, `effect`, `color`, `icon`) ·
`characters.json` (5 героев: stats/weapons/skills/tree/overrides; `spellcaster: true` — чистый заклинатель:
нет оружия/подбора, ЛКМ или Q кастует текущее заклинание, C/V листают книгу из трёх; у мага это включено) ·
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
K/Shift перекат (неуязвим) · E подобрать · Q навык, C/V смена навыка · E подобрать · R рестарт ·
M карта мира · **F5 перезагрузка данных** · F4 сетка клеток · F3 хитбоксы / редактор кнопок меню ·
F11 полный экран. Персонаж целится в курсор (`mouse_aim` в settings.json).

## Git
Проект под git (`.git` есть, `.gitignore` исключает dist/build/кэш). На момент заметок —
активная разработка (многие файлы правлены 2026-11-02).
