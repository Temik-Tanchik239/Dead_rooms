Ты — pi-агент в проекте DEAD ROOMS (Python/Pygame-ce рогалик, каталог C:/Users/artem/Desktop/DEAD_ROOMS).
ЗАДАЧА: переделай механику СМЕРТИ в multiplayer.py — нокаута больше нет, тиммейты не поднимают. Умер — возрождение на последнем чекпоинте с 10-секундным кристаллом.

КОНТЕКСТ: другой агент уже сделал per-player комнаты (p.room_id у каждого игрока, HostSession.sims, step_room, go_player, snapshot_for с "rm", draw_players фильтрует по комнате). Ещё один агент сделал модуль checkpoint.py — ПРОЧИТАЙ ЕГО ЦЕЛИКОМ: там есть freeze_time() (SETTINGS["checkpoint_freeze_seconds"], по умолчанию 10), tick(pl, dt) (pl.frozen -= dt; pl.inv = max(pl.inv, pl.frozen)), freeze(pl, seconds=None), activate(g, pl, r, cp, fx=None?) — посмотри фактическую сигнатуру, respawn(g) (одиночная версия, в сети no-op).

ЧТО СДЕЛАТЬ В multiplayer.py:
1. УБРАТЬ нокаут: константы REVIVE_TIME/REVIVE_RADIUS/REVIVE_HP/CLEAR_REVIVE_HP (или оставить неиспользуемыми с комментарием — лучше удалить), методы down()/revive() заменить на die(p):
       def die(s, p):
           # смерть: назад к чекпоинту игрока (или к точке появления его комнаты), полный запас, кристалл на freeze_time()
           cp = getattr(p, "cp", None)
           if cp and cp[0] in CFG["map_defs"]:
               s.go_player(p, cp[0], None)          # переход в комнату чекпоинта (tp поднимется — клиент перевставится)
               p.x = cp[1] - p.w / 2; p.y = cp[2] - p.h; p.vx = p.vy = 0
               if p.h != p.H0: p.y -= p.H0 - p.h; p.h = p.H0
           else:
               s.respawn_player(p)                   # чекпоинта не было — точка появления своей комнаты
           p.hp = p.maxhp
           p.refresh_mana(True)  # посмотри, как у игроков задаётся мана в этом файле (mana = maxmana после refresh)
           p.mana = p.maxmana
           p.atk = None; p.grab = None; p.channel = None; p.hold = None; p.stun = 0
           p.shield_time = 0.0; p.shield_hp = 0.0; p.hitbox = None
           # рука Моргарта, державшая героя, должна отпустить: посмотри boss_hands.py (есть ли метод release/drop у hands) и вызови его для мобов комнаты, державших p (или полагайся на сброс p.grab + то, что руки проверяют p.grab каждый кадр — проверь!)
           checkpoint.freeze(p)
           s.room_fx(p).text(f"{p.name} погиб — возвращение к чекпоинту", p.cx, p.y - 30)
2. В step_room: вместо "if p.hp <= 0 and not p.downed: s.down(p)" — "if p.hp <= 0: s.die(p)". УДАЛИТЬ блок «павшие: падают на землю, союзник рядом поднимает» (цикл с REVIVE_TIME). 
3. Замороженные игроки (p.frozen > 0) в step_room: физику и update ИХ вести (чтобы падали/стояли на земле), но ввод нулевой: вместо inp.keys передавай пустые клавиши (посмотри класс NetKeys — сделай NetKeys(0) или эквивалент; press() не вызывать, pose не принимать). До p.update вызови checkpoint.tick(p, dt) (можно один раз для всех игроков комнаты в начале).
4. game_over: теперь недостижим (каждая смерть возрождает). Убери s.game_over из step (оставь поле False для совместимости draw_overlay); "over" в снимке — False.
5. Снимок: в snapshot_for добавь у каждого игрока "fz": round(max(0, p.frozen), 2). Поле "rv" (revive) удали из снимка И из apply_stats клиента (там p.revive = ps.get("rv", 0); p.downed = ... — замени на p.frozen = float(ps.get("fz", 0.0)); атрибут downed больше не используется — убери его чтение; проверь все места с "downed" в файле, включая lobby-код).
6. Клиент: 
   - apply_self: если p.frozen > 0 — не предсказывать (как для павших раньше): s.predicting = False... НО заморозка тает: чтобы клиент не залип навсегда, разрешай предсказание снова, когда fz из снимка == 0 (каждый снимок сравнивай). Проще: в predict() верни early, если p.frozen > 0; в apply_self не блокируй из-за frozen (hp > 0 у замороженного). Ввод всё равно игнорируется хостом — безопасно.
   - draw_players: вместо draw_downed — если p.frozen > 0: нарисуй героя (обычно) и поверх checkpoint.draw_crystal(v, p, pg.time.get_ticks()). Функцию draw_downed УДАЛИ.
   - draw_overlay: убей ветки «ВСЕ ПОГИБЛИ» и «ТЫ ПАЛ» (заменены чекпоинт-возрождением); список союзников слева: вместо "✅/✝" помечай замороженных "❄ ".
7. Чекпоинты в сети (хост): в step_room для каждого живого игрока комнаты: checkpoint.tick(p, dt) (см. п.3) и активация: for cp in r.checkpoints: if p.rect.colliderect(cp["rect"]): checkpoint.activate(g, p, r, cp). ВАЖНО: checkpoint.activate пишет текст в g.fx.text — для игрока из другой комнаты это чужой fx; посмотри сигнатуру activate: если у неё есть параметр fx — передай s.room_fx(p); если нет — РАЗРЕШЕНО добавить в checkpoint.py опциональный параметр fx=None (последним), внутри использовать fx или g.fx; больше checkpoint.py не меняй.
   Автосохранения в сети не будет: activate сам проверяет g.net (None только в одиночке) — в сети он только лечит и ставит p.cp. pl.cp у хостовых игроков: это атрибут p (Player) — просто работает.
8. join_game/respawn_player: убери упоминания павших (якорь — только живые); «все пали — хотя бы в чью-нибудь комнату» — упростить: якорь любой игрок (мёртвых мгновенных нет).

ПРОВЕРКИ (headless, SDL dummy):
- py_compile multiplayer.py checkpoint.py.
- Расширь/напиши тест multiagent/out/mp_death_test.py (за образец возьми multiagent/out/mp_rooms_test.py): хост + 1 клиент (сокеты в цикле, как в том тесте): (а) игрок умирает (p.hp = 0; s.step_room/step) → он перенёсся в комнату своего чекпоинта (предварительно поставив p.cp вручную), hp полный, p.frozen > 0; (б) у frozen игрока ввод игнорируется (inp с клавишами не двигает его); (в) после тика p.frozen до 0 игрок снова управляем; (г) activate в сети ставит p.cp и ЛЕЧИТ, но НЕ создаёт файлов в saves/; (д) в снимке есть "fz" и нет "rv"; (е) client-side: apply_stats ставит p.frozen из снимка.
- Файлы в saves/ после тестов удали (папка пустая).
- НЕ редактируй: main.py, maps.py, save_io.py, map_editor.py (checkpoint.py — только опциональный параметр fx, см. п.7).
Отчёт: multiagent/out/mp_death.md — что изменено, как протестировано, что нужно главному агенту в main.py (если что-то).
