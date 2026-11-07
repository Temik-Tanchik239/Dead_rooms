import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import main  # noqa
import core, spells, hud, multiplayer  # noqa
core.reload_data()

sk = core.CFG["skills"]["inferno"]
assert sk.get("sustained") and sk.get("type") == "aura"
assert core.char_def("mage")["base_skills"][-1] == "inferno", "mage must start with inferno"
assert hud.reserve_meter and hud.channel_overlay
assert spells.CHANNELS.get("aura")

# icon_path resolves or falls back without crashing
import os
import anim
path = spells.icon_path("inferno", sk)
print("icon path:", path, "| file exists:", os.path.exists(path))

# HUD draw path for sustained cell + meter (headless SFX-free; needs a dummy surface)
import pygame as pg
pg.init()
scr = pg.Surface((200, 120))

class FP:
    def __init__(self):
        self.skills = ["inferno"]; self.skill_index = 0
        self.skill_reserve = {}; self.skill_cooldowns = {}
        self.channel = None; self.skill_cast = None; self.skill_held = True
        self.state = "move"; self.grab = None; self.move_input = False
        self.buf = {}; self.vx = 0.0; self.x = self.y = 10.0
        self.cx = self.cy = 10.0; self.face = 1
        self.mana = 100.0; self.maxmana = 100.0; self.mana_flash = 0.0
        self.mana_t = 0.0; self.stun = 0.0; self.level = 1
        self.xp = 0; self.xp_next = 100; self.hp = 100; self.maxhp = 100
        self.slots = [None, None]; self.last_weapon = None
    def airborne(self): return False
    def dmg_mult(self): return 1.0

pl = FP()
font = pg.font.Font(None, 18)
# ячейка с полным запасом (не колдуем) — reserve_meter
hud.spell_cell(scr, pl, "inferno", 10, 10, 48, font, active=True)
# ячейка с пустым запасом — ветка «0» (та, что раньше падала в NameError)
pl.skill_reserve["inferno"] = 0.0
hud.spell_cell(scr, pl, "inferno", 70, 10, 48, font, active=True)
# активный sustained-каст — channel_overlay с сектором остатка
res = spells.cast(pl, [], [], type("FX", (), {"text": lambda *a: None, "ring": lambda *a: None})())
assert pl.channel and pl.channel.get("sustained")
hud.spell_cell(scr, pl, "inferno", 130, 10, 48, font, active=True)
spells.channel_stop(pl)
print("HUD_DRAW_OK")
