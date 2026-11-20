Ты — pi-агент в проекте DEAD ROOMS (Python/Pygame-ce рогалик, каталог C:/Users/artem/Desktop/DEAD_ROOMS).
ЗАДАЧА: создай НОВЫЙ модуль pause_menu.py — новое меню паузы (Esc) с 5 кнопками:
1. ПРОДОЛЖИТЬ  2. ВЫБОР ПЕРСОНАЖА  3. СОХРАНИТЬСЯ  4. ЗАГРУЗИТЬ  5. ГЛАВНОЕ МЕНЮ

СНАЧАЛА прочитай отчёт аудитора: multiagent/audit_own.md (раздел 4). Также изучи main.py: menu_layout (~903, defaults pause: continue/new/exit, настройка "menu_layout_pause" в SETTINGS, F3-режим редактирования кнопок s.menu_edit), draw_menu (~996: рисование кнопок g.menu_button/g.menu_button_selected), menu_event (~940: клики по кнопкам, drag в режиме menu_edit), menu_action (~886: куда ведут действия), key() (~831: Esc в pause закрывает меню).

Контракт модуля (строго; главный агент роутит из main.py: вместо старых pause-опций):

```python
OPTIONS = [("ПРОДОЛЖИТЬ", "continue"), ("ВЫБОР ПЕРСОНАЖА", "swap"), ("СОХРАНИТЬСЯ", "save"),
           ("ЗАГРУЗИТЬ", "load"), ("ГЛАВНОЕ МЕНЮ", "menu")]
def layout(g) -> dict     # SETTINGS["menu_layout_pause"]: {action: [x, y, w, h]} — дефолты: вертикальный столбец
                          # по центру, кнопка 300x44, шаг ~58, от VIEW_H//2-150; смирение под ограничения W/VIEW_H
                          # (скопируй логику main.menu_layout: setdefault, clamp, возврат cfg)
def key(g, k)             # Esc -> g.menu_mode=None (+ pg.mouse.set_visible(not SETTINGS.get("mouse_aim", True)));
                          # клавиши 1..5 (pg.K_1..K_5 и K_KP1..KP5) -> g.menu_action(OPTIONS[i][1])
def event(g, e)           # ЛКМ по кнопке -> g.menu_action(action); если g.menu_edit — перенос кнопок мышью
                          # и изменение размера колесом (скопируй паттерн main.menu_event ~946-990, s.menu_drag,
                          # s.save_settings(), resize по 4/5 и MOUSEWHEEL); подсказка «F3 — редактировать» в draw
def draw(g)               # g.scr.blit(g.menu_veil); кнопки как в main.draw_menu (~996): rect = pg.Rect(layout[action]),
                          # hovered -> g.menu_button_selected, слева от текста номер кнопки «1. ПРОДОЛЖИТЬ» и т.д.
                          # НЕ рисуй курсор — это делает главный агент
```

ВАЖНЫЕ ПРАВИЛА:
1. НЕ редактируй и не создавай файлы кроме pause_menu.py (main.py правит главный агент: key()/menu_event()/draw_menu() будут вызывать твои key/event/draw при s.menu_mode=="pause", menu_action получит новые действия "swap"/"save"/"load"/"menu").
2. В сетевой игре (g.net — не None) кнопки «ВЫБОР ПЕРСОНАЖА», «СОХРАНИТЬСЯ», «ЗАГРУЗИТЬ» рисуются приглушённо и недоступны: при выборе g.fx.text("Недоступно в сетевой игре", ...) — это можно сделать прямо в key/event модуля (guard), чтобы main не усложнять.
3. Дефолтные координаты добавляй через setdefault — пользовательские настройки в data/settings.json не терять.
4. Русские подписи. Кнопка «ЗАГРУЗИТЬ» ведёт в список сохранений (действие "load" — его разрулит main: g.menu_mode="saves" через saves_menu.open_saves(g, back="pause")).
5. Тесты (SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy ./.venv/Scripts/python.exe): создать Game (import core; core.apply_character("knight"); import main as M; g=M.Game(); g.menu_mode="pause"), layout(g) — 5 ключей, валидные прямоугольники в пределах экрана; key: pg.K_2 даёт вызов g.menu_action("swap") (monkeypatch g.menu_action), Esc закрывает; event: клик по прямоугольнику кнопки 3 вызывает menu_action("save"); draw(g) не падает; повторный layout не меняет пользовательских координат (setdefault). py_compile pause_menu.py.
Финальный ответ: краткий отчёт (кнопки, клавиши, результаты тестов) + строка RESULT_OK.
