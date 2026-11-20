Ты — pi-агент в проекте DEAD ROOMS (Python/Pygame-ce рогалик, каталог C:/Users/artem/Desktop/DEAD_ROOMS).
ЗАДАЧА: создай НОВЫЙ модуль swap.py — смена героя посреди забега (пауза, экран «ВЫБОР ПЕРСОНАЖА»), с полным сохранением инвентаря/характеристик КАЖДОГО героя забега.

Смысл фичи (пример пользователя): начал забег за барда, нашёл 3 оружия, переключился на инженера, нашёл шлем — сохранение хранит и оружие барда, и шлем инженера. В одном забеге можно проходить разные моменты за разных героев; всё состояние — индивидуально на героя (hp/мана/уровень/опыт/навыки/оружие/рюкзак/экипировка/ресурсы и пр.).

СНАЧАЛА прочитай отчёт аудитора: multiagent/audit_own.md (разделы 2, 3). Изучи main.py (Player ~69: поля и подсистемы; new_game ~575), core.py (apply_character ~111, _set_char ~126, CHAR ~78, char_ids(), char_def(cid)), characters.py (SETTINGS["last_character"]=cid; g.save_settings() ~117; draw героев ~235 — как рисуют превью), inventory.py (init ~162, bag/equip/resources), crossbow.py, bard.py, clone.py (pl.clones — временное), invisibility.py, anim.py (clear_cache), spells.py (active_skills/skill_index), data/characters.json (имена героев "name").

Контракт модуля (строго):

```python
MODE = "swap"
def init(g)                  # g.heroes = {} — dict char_id -> JSON-сериализуемый снапшот героя; вызовет главный агент в new_game
def register(g)              # g.heroes[CHAR["id"]] = snapshot_player(g.pl) — обновить запись текущего героя (не терять остальных);
                             #  должен быть безопасен в любой момент забега
def switch_open(g)           # экран выбора: g.menu_mode = "swap"; выбрать героя стрелками/W-S или мышью, Enter/клик — switch
def menu_key(g, k)           # Esc — отмена (g.menu_mode=None), навигация, Enter — применить
def menu_event(g, e)         # клики по карточкам героев
def draw_menu(g)             # карточки героев: имя (русское, data/characters.json -> "name"), уровень, HP/мана,
                             #  пометка «сейчас играешь» и «в забеге» (есть в g.heroes) или «новый»
def switch(g, cid) -> None   # register(); если cid == CHAR["id"] — ничего (закрыть экран);
                             #  иначе: g.heroes[старый cid] = snapshot_player(g.pl); apply_character(cid);
                             #  anim.clear_cache(); inventory.clear_cache(); SETTINGS["last_character"]=cid; g.save_settings();
                             #  pos = (g.pl.x, g.pl.y); создаёшь НОВОГО героя через g.Player(); восстановление:
                             #  если cid в g.heroes — restore_player(новый pl, g.heroes[cid]) (позицию НЕ брать из снапшота);
                             #  ставишь на pos (в границах комнаты, на пол — посмотри main.Game.place/respawn);
                             #  g.pl = новый; сбросы перехода: pl.atk=None, pl.channel=None, pl.hold=None, pl.clones=[]
                             #  (пересоздать атрибут, если его нет), crossbow/bard — новые их init уже вызваны в Player.__init__
def snapshot_player(pl) -> dict      # реализация НЕ здесь! (см. ниже)
def restore_player(pl, snap) -> None # реализация НЕ здесь! (см. ниже)
```

ВАЖНЫЕ ПРАВИЛА:
1. snapshot_player/restore_player живёт в save_io.py — его пишет ПАРАЛЛЕЛЬНЫЙ агент. Контракт: snapshot_player(pl)->dict (JSON-safe), restore_player(pl, snap). Импорт ленивый внутри функций: `from save_io import snapshot_player, restore_player`. Если на момент твоего теста save_io.py ещё не существует — протестируй UI-часть с заглушкой (monkeypatch), переключение протестирует главный агент после интеграции.
2. НЕ редактируй и не создавай файлы кроме swap.py. Интеграцию в main.py (menu_mode="swap" роутинг, new_game -> swap.init(g), регистрация героя) делает главный агент.
3. restore_player восстанавливает героя «в деталях» (инвентарь, уровень, навыки, арбалеты барда/Тени и т.д.) — твоя задача: правильный ПОРЯДОК (снапшот ДО apply_character! затем новый Player — иначе apply_character перетрёт поля) и позиция.
4. В сетевой игре (g.net не None) switch_open не открывать: g.fx.text("Недоступно в сетевой игре", g.pl.cx, g.pl.y-40).
5. Персонаж может быть и «новым» для забега (нет в g.heroes) — просто свежий герой; попасть в забег он может через твой экран (список = все core.char_ids()).
6. Русские подписи. Стиль: вуаль g.menu_veil, панель по центру, карточки героев; превью героя рисуй как characters.py draw() (упрощённо достаточно имени/уровня/HP; если есть простой способ нарисовать модель героя — сделай).
7. overlay: экран открыт, когда g.menu_mode == "swap" — игра на паузе (main сам ставит sim=0).
8. Тесты (SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy ./.venv/Scripts/python.exe): import core; core.apply_character("knight"); import main as M; g=M.Game(); g.menu_mode="pause"... — init(g); register(g) -> g.heroes["knight"] существует; выдай pl предметы в bag (inventory: pl.bag[0]="rusty_sword"), level=5, xp=123; switch_open(g) -> menu_mode=="swap"; draw_menu(g) не падает; menu_key/pg.Event клик по карточке мага -> switch: g.pl.char_id=="mage", bag свежий; switch(g,"knight") -> bag с rusty_sword, level==5, hp сохранён; позиции совпадают. py_compile swap.py.
Финальный ответ: краткий отчёт (порядок снапшот/restore, что проверено) + строка RESULT_OK.
