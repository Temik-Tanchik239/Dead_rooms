Готово. Итоговый отчёт:

## Отчёт по задаче [swap]

**Создан единственный файл: `swap.py`** (~270 строк). Никакие другие файлы не тронуты (интеграцию в `main.py` делает главный агент — точки подключения описаны в докстринге модуля).

### Ключевой порядок смены (`swap.switch`, критичная последовательность)
1. **register(g)** — снапшот СТАРОГО героя через `save_io.snapshot_player` **ДО** `apply_character` (иначе CFG перетрёт его поля);
2. запоминается позиция старого героя — **центр по X и ноги по Y** (не из снапшота; при разных хитбоксах герой остаётся стоять на земле);
3. отмена крафта/установки турели (`crafting.cancel` — ресурсы падают на пол), закрытие инвентаря;
4. `apply_character(cid)` → `anim.clear_cache()` → `inventory.clear_cache()` → `SETTINGS["last_character"]=cid` → `g.save_settings()`;
5. **новый `g.Player()`** — его `__init__` сам вызывает `crossbow.init`/`bard.init`/`inventory.init` (свежие подсистемы);
6. `restore_player(новый pl, g.heroes[cid])` — личное состояние героя забега (позицию не трогает);
7. `_reset_transient` — `atk/channel/hold/hold_latch/grab/clones=[]` (атрибут `clones` пересоздаётся), `skill_held/move_input`;
8. `_place` — тот же центр/ноги, x зажат в границы комнаты; если новый хитбокс не влезает — пол под ногами (`core.floor_below`), затем соседние клетки, крайний случай — штатная точка появления комнаты (`g.place`); затем `g.pl = new` и сообщение в fx.

**Делегация в save_io:** `snapshot_player`/`restore_player` импортируют `save_io` лениво внутри функций; пока `save_io.py` нет — встроенный временный фолбэк (level/xp/hp/mana/skills/item_skills/slots/bag/equip/resources/hold_pool/hold_rest/xb_ammo/xb_cd/bd_note + пересчёт бонусов через `inventory.on_equipment_changed`), снапшот JSON-сериализуем.

### Экран
`switch_open` ставит `g.menu_mode = "swap"` (игра на паузе — main сам ставит sim=0); **в сети запрещён** (`g.fx.text("Недоступно в сетевой игре", …)`). `draw_menu` — вуаль `g.menu_veil`, полупрозрачная панель по центру, карточки всех `core.char_ids()`: русское имя из `data/characters.json -> name`, анимированное превью через `characters.preview`, метки «СЕЙЧАС ИГРАЕТЕ»/«В ЗАБЕГЕ»/«НОВЫЙ», уровень, полоски HP/маны (у играемого — живые pl, у отдыхающего — из снапшота, у нового — прочерки). `menu_key`: Esc — отмена, стрелки/W-S/цифры — выбор, Enter/пробел — применить; `menu_event` — клик по карточке.

### Проверено (headless-тесты, SDL dummy — все прошли)
- `init(g)`+`register(g)` → `g.heroes["knight"]` существует; повторный `register` не теряет остальных героев;
- выданы `pl.bag[0]="rusty_sword"`, `level=5`, `xp=123`, `hp=37` → `switch_open` → `menu_mode=="swap"`; `draw_menu` ×5 не падает (наведение, выделение);
- клавиатура: W/S/цифры/Esc/Enter; `K_RIGHT`+`K_RETURN` → `g.pl.char_id=="ranger"` со свежим рюкзаком;
- клик `pg.event.Event(MOUSEBUTTONDOWN)` по карточке мага → `char_id=="mage"`, рюкзак свежий;
- `switch(g,"knight")` обратно: `bag[0]=="rusty_sword"`, `level==5`, `xp==123`, `hp==37`, `atk/channel/hold/clones` сброшены, **позиция совпадает** (центр и ноги ±1 px);
- смена на героя, которого не было в забеге (bard) — путь «нового» героя; сетевой guard; JSON-сериализация `g.heroes`; `py_compile swap.py` — OK.

RESULT_OK