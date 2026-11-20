Ты — pi-агент в проекте DEAD ROOMS (Python/Pygame-ce рогалик, каталог C:/Users/artem/Desktop/DEAD_ROOMS).
ЗАДАЧА: создай НОВЫЙ модуль saves_menu.py — экран «Сохранения» в главном меню (список сохранений + выбор персонажа для продолжения).

СНАЧАЛА прочитай отчёт аудитора: multiagent/audit_own.md (разделы 3, 4). Также изучи:
- main.py: draw_menu (~983) и menu_event (~940), menu_action (~886) — стиль и порядок вызовов меню; Game.__init__ (~547): ассеты s.menu_background, s.menu_veil, s.menu_button, s.menu_button_selected, s.menu_edit; mp.MENU_MODES — как главный агент роутит режимы (в main.py: key() ~816 `if s.menu_mode in mp.MENU_MODES: mp.menu_key(s, k)`, event() ~942, draw_menu() ~985).
- characters.py (CharMenu: open_select ~75, key ~127, event ~140, draw ~235) — образец экрана с сеткой персонажей.
- core.py: char_ids(), char_def(cid), char_look(cid), char_folder(cid).

Контракт модуля (строго; главный агент роутит из main.py):

```python
MODES = ("saves", "saves_char")
def open_saves(g)             # g.menu_mode="saves"; перечитать список через save_io.list_saves(); s.menu_selected=saves[0].id
def menu_key(g, k)            # W/S/Up/Down — выбор, Enter — открыть, Esc — назад (saves_char -> saves, saves -> старт-меню или None)
def menu_event(g, e)          # мышь: клик по пункту; наведение
def draw_menu(g)              # список сохранений ИЛИ список героев выбранного сохранения
```

Сценарий пользователя:
1. Главное меню -> кнопка «СОХРАНЕНИЯ» (её добавит главный агент) -> open_saves(g): вертикальный список сохранений (имя, время, круг loop, герои забега и их уровни) + пункт «НАЗАД». Если сохранений нет — надпись «Нет сохранений» и пункт «НАЗАД».
2. Выбор сохранения (Enter/клик) -> menu_mode="saves_char": список героев ЭТОГО забега (id из meta["chars"], имена героев по-русски — возьми из data/characters.json -> "name" или char_def(cid).get("name")), у каждого: имя, уровень (meta["level"][cid]), пометка «играл последним» (cid == meta["char"]).
3. Выбор героя -> save_io.restore(g, save_id) (герой уже выставлен сохранением внутри restore) — потом g.menu_mode=None. Перед restore выставить g.menu_mode=None.
4. Esc на «saves_char» — назад к списку сохранений; Esc на «saves» — закрыть (g.menu_mode="start", если открыли из главного меню; помни, откуда открыли — поле модуля, задаваемое open_saves(g, back=...)).

ВАЖНЫЕ ПРАВИЛА:
1. НЕ редактируй и не создавай никаких файлов кроме saves_menu.py. Точки вызова в main.py добавит главный агент.
2. Модуль save_io.py пишет ПАРАЛЛЕЛЬНЫЙ агент — контракт: list_saves() (см. выше), save_io.restore(g, save_id). Импорт ленивый внутри функций: `from save_io import ...` (если файла ещё нет на момент твоего теста, UI-тесты делай на подставном списке — monkeypatch или заглушка).
3. Стилизация как главное меню: фон g.menu_background (smoothscale на весь экран) если есть, поверх g.menu_veil; кнопки рисуй шрифтом g.font/g.big — можно прямоугольники с рамкой в стиле s.menu_button (посмотри как main.draw_menu рисует кнопки и повтори упрощённо). Наведение мыши подсвечивает.
4. Не вызывай g.draw_cursor() — это делает главный агент в draw_menu.
5. Русские подписи. Прокрутка списка, если сохранений много (колесо мыши + стрелки), ~8 видимых пунктов.
6. overlay: рисуй панель с полупрозрачным тёмным фоном по центру (pg.Surface с SRCALPHA).
7. Тесты (SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy ./.venv/Scripts/python.exe): создать Game, open_saves(g) с заглушкой списка (3 сохранения), draw_menu(g) не падает; menu_key: W/S двигают выбор, Enter переходит в saves_char, Esc назад; menu_event: синтетический pg.event.MOUSEBUTTONDOWN с pos на пункте выбирает сохранение; draw_menu в saves_char показывает героев. py_compile saves_menu.py.
Финальный ответ: краткий отчёт (сценарий, стилизация, результаты тестов) + строка RESULT_OK.
