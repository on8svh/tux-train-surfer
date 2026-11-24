"""Application shell: display, input mapping and all screens (scenes)."""

from __future__ import annotations

import math
import random

import pygame

from . import __version__, art, i18n
from . import config as C
from .audio import Audio
from .levels import LEVELS, ENDLESS, Level, level_by_number
from .missions import MissionTracker
from .render import Renderer
from .storage import ACTIONS, Save
from .ui import UI, Menu, WHITE, YELLOW
from .world import Bot, World

MENU_KEYS = {
    "up": "m_up", "down": "m_down", "left": "m_left", "right": "m_right",
    "w": "m_up", "s": "m_down", "a": "m_left", "d": "m_right",
    "return": "ok", "enter": "ok", "space": "ok",
    "escape": "back", "backspace": "back",
}

POWERUP_TIMERS = (("magnet", "magnet_t", C.MAGNET_TIME), ("coffee", "coffee_t", C.COFFEE_TIME),
                  ("superjump", "superjump_t", C.SUPERJUMP_TIME), ("jetpack", "jetpack_t", C.JETPACK_TIME))


# =========================================================================== input
class Input:
    def __init__(self, save: Save) -> None:
        self.save = save
        self.joys: dict[int, pygame.joystick.JoystickType] = {}
        self.axis_state: dict = {}
        try:
            pygame.joystick.init()
            for i in range(pygame.joystick.get_count()):
                j = pygame.joystick.Joystick(i)
                self.joys[j.get_instance_id()] = j
        except pygame.error:
            pass

    def actions(self, event) -> set[str]:
        a: set[str] = set()
        t = event.type
        if t == pygame.KEYDOWN:
            name = pygame.key.name(event.key)
            for act in ACTIONS:
                if name in self.save.keys.get(act, []):
                    a.add(act)
            m = MENU_KEYS.get(name)
            if m:
                a.add(m)
        elif t == pygame.JOYBUTTONDOWN:
            for act in ACTIONS:
                if event.button in self.save.pad.get(act, []):
                    a.add(act)
            if event.button == 0:
                a.add("ok")
            elif event.button == 1:
                a.add("back")
            elif event.button in (6, 7):
                a.add("pause")
        elif t == pygame.JOYHATMOTION:
            x, y = event.value
            if x < 0:
                a |= {"left", "m_left"}
            elif x > 0:
                a |= {"right", "m_right"}
            if y > 0:
                a |= {"jump", "m_up"}
            elif y < 0:
                a |= {"duck", "m_down"}
        elif t == pygame.JOYAXISMOTION and event.axis in (0, 1):
            key = (event.instance_id, event.axis)
            old = self.axis_state.get(key, 0)
            v = event.value
            new = 1 if v > 0.6 else -1 if v < -0.6 else (0 if abs(v) < 0.3 else old)
            if new != old:
                self.axis_state[key] = new
                if new:
                    if event.axis == 0:
                        a |= {"left", "m_left"} if new < 0 else {"right", "m_right"}
                    else:
                        a |= {"jump", "m_up"} if new < 0 else {"duck", "m_down"}
        elif t == pygame.JOYDEVICEADDED:
            try:
                j = pygame.joystick.Joystick(event.device_index)
                self.joys[j.get_instance_id()] = j
            except pygame.error:
                pass
        elif t == pygame.JOYDEVICEREMOVED:
            self.joys.pop(event.instance_id, None)
        return a


def key_label(name: str) -> str:
    return name.upper() if len(name) <= 2 else name.capitalize()


# =========================================================================== app
class App:
    def __init__(self, args) -> None:
        self.args = args
        self.save = Save()
        st = self.save.settings
        if args.fullscreen:
            st["fullscreen"] = True
        if args.windowed:
            st["fullscreen"] = False
        lang = args.lang or st["language"]
        self.tr = i18n.Translator(lang)
        pygame.display.set_caption(C.TITLE)
        try:
            self.desktop = pygame.display.get_desktop_sizes()[0]
        except (pygame.error, IndexError, AttributeError):
            self.desktop = (1920, 1080)
        self.resolution = self.pick_resolution()
        self.screen = self.open_display()
        self.ui = UI(*self.resolution, self.tr)
        self.renderer = self.make_renderer()
        self.audio = Audio(st["sfx"], st["music"], enabled=not args.mute)
        self.input = Input(self.save)
        self.missions = MissionTracker(self.save)
        self.clock = pygame.time.Clock()
        self.time = 0.0
        self.running = True
        self.frames = 0
        self._work_ms: list[int] = []
        self._start_ticks = pygame.time.get_ticks()
        self._portraits: dict = {}
        self.backdrop = Backdrop(self)
        self.scene: Scene = self.initial_scene()

    # ------------------------------------------------------------------ display
    def pick_resolution(self) -> tuple[int, int]:
        if self.args.resolution:
            return self.args.resolution
        res = self.save.settings.get("resolution")
        if res and len(res) == 2:
            return int(res[0]), int(res[1])
        dw, dh = self.desktop
        best = C.RESOLUTIONS[0]
        for r in C.RESOLUTIONS[:1]:  # automatic: 1280x720 (HD ready); the GPU scales it to the screen
            if r[0] <= dw and r[1] <= dh:
                best = r
        return best

    def open_display(self) -> pygame.Surface:
        flags = 0 if self.args.headless else pygame.SCALED
        if self.save.settings["fullscreen"] and not self.args.headless:
            flags |= pygame.FULLSCREEN
        try:
            screen = pygame.display.set_mode(self.resolution, flags, vsync=1)
        except pygame.error:
            screen = pygame.display.set_mode(self.resolution, flags)
        try:
            pygame.display.set_icon(art.app_icon(64))
        except pygame.error:
            pass
        pygame.display.set_caption(C.TITLE)
        return screen

    def make_renderer(self) -> Renderer:
        r = Renderer(*self.resolution)
        r.font_func = self.ui.font
        r.skin = self.save.settings.get("skin", "classic")
        r.finish_text = self.tr("safe_house")
        return r

    def toggle_fullscreen(self) -> None:
        st = self.save.settings
        st["fullscreen"] = not st["fullscreen"]
        try:
            pygame.display.toggle_fullscreen()
        except pygame.error:
            self.reopen_display()
        self.save.save()

    def reopen_display(self) -> None:
        pygame.display.quit()
        pygame.display.init()
        self.screen = self.open_display()

    def set_resolution(self, res) -> None:
        self.save.settings["resolution"] = list(res) if res else None
        self.save.save()
        new = self.pick_resolution()
        if new == self.resolution:
            return
        self.resolution = new
        self.reopen_display()
        self.ui = UI(*new, self.tr)
        self.renderer = self.make_renderer()
        self.backdrop.reset_camera()

    def set_language(self, code: str) -> None:
        self.save.settings["language"] = code
        self.save.save()
        self.tr.set_language(code)
        self.ui.refresh_fonts()
        self.renderer.finish_text = self.tr("safe_house")
        self.renderer._glow.clear()

    def portrait(self, kind: str, key: str, size: int) -> pygame.Surface:
        k = (kind, key, size)
        img = self._portraits.get(k)
        if img is None:
            if kind == "chaser":
                img = art.chaser_front(key, size)
            elif kind == "tux":
                img = art.tux_front(size, skin=key)
            elif kind == "powerup":
                img = art.powerup_surface(key, size)
            elif kind == "pickup":
                img = art.pickup_surface(key, size)
            elif kind == "star":
                img = art.star_surface(size, key == "on")
            elif kind == "lock":
                img = art.lock_surface(size)
            else:
                img = art.check_surface(size)
            self._portraits[k] = img
        return img

    def chaser_name(self, kind: str) -> str:
        return self.tr("chaser_" + kind)

    # ------------------------------------------------------------------ scenes
    def initial_scene(self) -> "Scene":
        a = self.args
        if a.level is not None:
            return PlayScene(self, level_by_number(a.level))
        start = a.start or "title"
        table = {"title": TitleScene, "levels": LevelSelectScene, "missions": MissionsScene,
                 "skins": SkinsScene, "settings": SettingsScene, "controls": ControlsScene, "help": HelpScene}
        if start == "play":
            return PlayScene(self, LEVELS[0])
        if start == "endless":
            return PlayScene(self, ENDLESS)
        return table.get(start, TitleScene)(self)

    def _save_screenshot(self) -> None:
        if self.args.screenshot:
            import os
            os.makedirs(os.path.dirname(os.path.abspath(self.args.screenshot)), exist_ok=True)
            pygame.image.save(self.screen, self.args.screenshot)

    def go(self, scene: "Scene") -> None:
        self.scene = scene

    def run(self) -> int:
        while self.running:
            if self.args.headless:
                self.clock.tick()  # no frame cap: smoke tests run as fast as possible
                dt = 1 / C.FPS
            else:
                dt = self.clock.tick(C.FPS) / 1000.0
            dt = min(dt, 1 / 20)
            self.time += dt
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                    break
                if event.type == pygame.WINDOWFOCUSLOST:
                    self.scene.focus_lost()
                if event.type == pygame.KEYDOWN and (event.key == pygame.K_F11 or (
                        event.key == pygame.K_RETURN and event.mod & pygame.KMOD_ALT)):
                    self.toggle_fullscreen()
                    continue
                self.scene.handle(self.input.actions(event), event)
            t0 = pygame.time.get_ticks()
            self.scene.update(dt)
            self.scene.draw(self.screen)
            work = pygame.time.get_ticks() - t0  # CPU work, excluding the wait for vsync
            pygame.display.flip()
            self.frames += 1
            if self.frames > 30:  # skip warm-up frames
                self._work_ms.append(work)
            if self.args.quit_after and self.time >= self.args.quit_after:
                self._save_screenshot()
                self.running = False
            if self.args.smoke_test and self.frames >= self.args.smoke_test:
                self._save_screenshot()
                self.running = False
        self.save.save()
        if self.args.stats:
            w = sorted(self._work_ms) or [0]
            fps = self.frames / max(0.001, (pygame.time.get_ticks() - self._start_ticks) / 1000)
            print(f"resolution={self.resolution} window={pygame.display.get_window_size()} "
                  f"frames={self.frames} fps={fps:.1f} work_ms median={w[len(w) // 2]} "
                  f"p95={w[int(len(w) * 0.95)]} max={w[-1]} audio={self.audio.enabled} "
                  f"music={sorted(self.audio.music)} sfx={len(self.audio.sounds)} lang={self.tr.code} "
                  f"joysticks={len(self.input.joys)}")
        return 0


# =========================================================================== backdrop
class Backdrop:
    """An autopiloted run that plays behind the menus."""

    def __init__(self, app: App) -> None:
        self.app = app
        self.new()

    def new(self) -> None:
        lvl = random.choice(LEVELS)
        self.world = World(lvl, seed=random.randrange(1 << 30))
        self.bot = Bot(self.world)
        self.end = 0.0
        self.reset_camera()

    def reset_camera(self) -> None:
        self.app.renderer.reset_camera(self.world)

    def update(self, dt: float) -> None:
        self.bot.update(dt)
        self.world.update(dt)
        self.world.pop_events()
        self.app.renderer.follow(self.world, dt)
        if self.world.state != "run" or self.world.distance > 900:
            self.end += dt
            if self.end > 2.0:
                self.new()

    def draw(self, surf, dt=0.0) -> None:
        self.app.renderer.draw(surf, self.world, self.app.time, dt)


# =========================================================================== base scene
class Scene:
    def __init__(self, app: App) -> None:
        self.app = app
        self.dt = 0.0

    @property
    def ui(self) -> UI:
        return self.app.ui

    @property
    def tr(self):
        return self.app.tr

    def handle(self, actions: set, event) -> None:
        pass

    def update(self, dt: float) -> None:
        self.dt = dt

    def draw(self, surf) -> None:
        pass

    def focus_lost(self) -> None:
        pass

    def click(self) -> None:
        self.app.audio.play("click")


class MenuScene(Scene):
    """A scene drawn over the autopilot backdrop."""

    title_key = ""

    def __init__(self, app: App) -> None:
        super().__init__(app)
        app.audio.play_music("menu")

    def update(self, dt: float) -> None:
        super().update(dt)
        self.app.backdrop.update(dt)

    def draw_backdrop(self, surf, dim=120) -> None:
        self.app.backdrop.draw(surf, self.dt)
        self.ui.dim(surf, dim)

    def draw_title(self, surf, text) -> None:
        self.ui.text(surf, text, 84, (self.ui.W / 2, self.ui.s(90)), YELLOW)

    def back(self) -> None:
        self.click()
        self.app.go(TitleScene(self.app))


# =========================================================================== title
class TitleScene(MenuScene):
    def __init__(self, app: App) -> None:
        super().__init__(app)
        u = app.ui
        tr = app.tr
        items = [
            {"label": lambda: tr("menu_play"), "action": lambda: self._go(LevelSelectScene)},
            {"label": lambda: tr("menu_endless"), "action": lambda: self._play(ENDLESS)},
            {"label": lambda: tr("menu_missions"), "action": lambda: self._go(MissionsScene)},
            {"label": lambda: tr("menu_skins"), "action": lambda: self._go(SkinsScene)},
            {"label": lambda: tr("menu_settings"), "action": lambda: self._go(SettingsScene)},
            {"label": lambda: tr("menu_controls"), "action": lambda: self._go(ControlsScene)},
            {"label": lambda: tr("menu_help"), "action": lambda: self._go(HelpScene)},
            {"label": lambda: tr("menu_quit"), "action": self._quit},
        ]
        self.menu = Menu(items, u.W // 2, u.s(300), u.s(520), u.s(76), u.s(14))

    def _go(self, cls) -> None:
        self.click()
        self.app.go(cls(self.app))

    def _play(self, level: Level) -> None:
        self.click()
        self.app.go(PlayScene(self.app, level))

    def _quit(self) -> None:
        self.app.running = False

    def handle(self, actions, event) -> None:
        if self.menu.handle(actions, event) and actions:
            self.click()
        if "back" in actions:
            pass

    def draw(self, surf) -> None:
        ui = self.ui
        self.draw_backdrop(surf, 90)
        bob = math.sin(self.app.time * 2) * ui.s(8)
        ui.text(surf, self.tr("title"), 130, (ui.W / 2, ui.s(120) + bob), YELLOW)
        ui.text(surf, self.tr("tagline"), 38, (ui.W / 2, ui.s(215)), WHITE)
        self.menu.draw(surf, ui, 42)
        skin = self.app.save.settings.get("skin", "classic")
        tux = self.app.portrait("tux", skin, ui.s(440))
        surf.blit(tux, tux.get_rect(midbottom=(ui.W * 0.18, ui.H - ui.s(60) + bob)))
        kinds = ("thief", "kernel", "segfault", "lockin")
        for i, k in enumerate(kinds):
            img = self.app.portrait("chaser", k, ui.s(150))
            x = ui.W * 0.8 + (i % 2 - 0.5) * ui.s(190)
            y = ui.s(420) + (i // 2) * ui.s(230) + math.sin(self.app.time * 3 + i) * ui.s(6)
            surf.blit(img, img.get_rect(center=(x, y)))
            ui.text(surf, self.app.chaser_name(k), 26, (x, y + ui.s(95)), WHITE)
        mult = self.app.missions.multiplier
        ui.text(surf, self.tr("multiplier", n=mult), 34, (ui.W * 0.8, ui.s(250)), (120, 255, 160))
        ui.text(surf, f"v{__version__}  -  {self.tr('credits')}", 22, (ui.W / 2, ui.H - ui.s(22)), (200, 215, 235))


# =========================================================================== level select
class LevelSelectScene(MenuScene):
    COLS = 5

    def __init__(self, app: App) -> None:
        super().__init__(app)
        unlocked = app.save.progress["unlocked"]
        self.index = max(0, min(len(LEVELS) - 1, unlocked - 1))

    def rects(self):
        ui = self.ui
        w, h, gap = ui.s(330), ui.s(224), ui.s(22)
        rows = math.ceil(len(LEVELS) / self.COLS)
        total_w = self.COLS * w + (self.COLS - 1) * gap
        x0 = (ui.W - total_w) // 2
        y0 = ui.s(160)
        out = []
        for i in range(len(LEVELS)):
            r, c = divmod(i, self.COLS)
            out.append(pygame.Rect(x0 + c * (w + gap), y0 + r * (h + gap), w, h))
        del rows
        return out

    def unlocked(self, i) -> bool:
        return LEVELS[i].number <= self.app.save.progress["unlocked"] or self.app.args.unlock_all

    def start(self, i) -> None:
        if self.unlocked(i):
            self.click()
            self.app.go(PlayScene(self.app, LEVELS[i]))
        else:
            self.app.audio.play("bonk")

    def handle(self, actions, event) -> None:
        n = len(LEVELS)
        if "back" in actions:
            self.back()
            return
        moved = False
        if "m_left" in actions:
            self.index = (self.index - 1) % n
            moved = True
        if "m_right" in actions:
            self.index = (self.index + 1) % n
            moved = True
        if "m_up" in actions:
            self.index = (self.index - self.COLS) % n
            moved = True
        if "m_down" in actions:
            self.index = (self.index + self.COLS) % n
            moved = True
        if moved:
            self.click()
        if "ok" in actions:
            self.start(self.index)
        if event is not None and event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
            for i, r in enumerate(self.rects()):
                if r.collidepoint(event.pos):
                    self.index = i
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        self.start(i)
            back = self.back_rect()
            if event.type == pygame.MOUSEBUTTONDOWN and back.collidepoint(event.pos):
                self.back()

    def back_rect(self):
        ui = self.ui
        r = pygame.Rect(0, 0, ui.s(300), ui.s(64))
        r.midbottom = (ui.W // 2, ui.H - ui.s(18))
        return r

    def draw(self, surf) -> None:
        ui = self.ui
        self.draw_backdrop(surf, 150)
        self.ui.text(surf, self.tr("select_level"), 72, (ui.W / 2, ui.s(80)), YELLOW)
        prog = self.app.save.progress
        for i, r in enumerate(self.rects()):
            lvl = LEVELS[i]
            sel = i == self.index
            unlocked = self.unlocked(i)
            ui.panel(surf, r, (40, 70, 120, 230) if unlocked else (40, 44, 60, 220),
                     (255, 200, 80) if sel else (120, 180, 240), 20)
            if sel:
                pygame.draw.rect(surf, (255, 200, 80), r.inflate(ui.s(8), ui.s(8)), max(2, ui.s(4)), border_radius=ui.s(24))
            ui.text(surf, self.tr("level_n", n=lvl.number), 34, (r.centerx, r.y + ui.s(30)), YELLOW)
            lines = ui.wrap(self.tr(lvl.name_key), 28, r.w - ui.s(30))
            for k, line in enumerate(lines[:2]):
                ui.text(surf, line, 28, (r.centerx, r.y + ui.s(68) + k * ui.s(28)), WHITE)
            if unlocked:
                img = self.app.portrait("chaser", lvl.chaser, ui.s(70))
                surf.blit(img, img.get_rect(center=(r.x + ui.s(55), r.bottom - ui.s(70))))
                stars = prog["stars"].get(str(lvl.number), [False, False, False])
                for k in range(3):
                    st = self.app.portrait("star", "on" if stars[k] else "off", ui.s(42))
                    surf.blit(st, st.get_rect(center=(r.centerx + ui.s(10) + (k - 1) * ui.s(48), r.bottom - ui.s(88))))
                best = prog["best"].get(str(lvl.number), 0)
                ui.text(surf, self.tr("best", score=best), 24, (r.centerx + ui.s(30), r.bottom - ui.s(40)), (200, 220, 255))
            else:
                img = self.app.portrait("lock", "", ui.s(80))
                surf.blit(img, img.get_rect(center=(r.centerx, r.bottom - ui.s(70))))
        cur = LEVELS[self.index]
        if not self.unlocked(self.index):
            hint = self.tr("unlock_hint")
        else:
            hint = self.tr("chased_by", chaser=self.app.chaser_name(cur.chaser))
        ui.text(surf, hint, 32, (ui.W / 2, ui.H - ui.s(122)), WHITE)
        ui.button(surf, self.back_rect(), self.tr("back"), False, True, 36)


# =========================================================================== missions
class MissionsScene(MenuScene):
    def handle(self, actions, event) -> None:
        if actions & {"back", "ok"} or (event is not None and event.type == pygame.MOUSEBUTTONDOWN):
            self.back()

    def draw(self, surf) -> None:
        ui = self.ui
        self.draw_backdrop(surf, 150)
        self.draw_title(surf, self.tr("missions_title"))
        tracker = self.app.missions
        ui.text(surf, self.tr("multiplier", n=tracker.multiplier), 56, (ui.W / 2, ui.s(190)), (120, 255, 160))
        draw_missions(self.app, surf, tracker.progress(), ui.W // 2, ui.s(270))
        ui.text(surf, self.tr("missions_hint"), 32, (ui.W / 2, ui.s(800)), WHITE)
        r = pygame.Rect(0, 0, ui.s(300), ui.s(70))
        r.midbottom = (ui.W // 2, ui.H - ui.s(40))
        ui.button(surf, r, self.tr("back"), True, True, 36)


def draw_missions(app: App, surf, progress, cx, top, width=None) -> None:
    ui = app.ui
    w = width or ui.s(1100)
    h = ui.s(130)
    for i, (m, value, done) in enumerate(progress):
        r = pygame.Rect(0, 0, w, h)
        r.midtop = (cx, top + i * (h + ui.s(20)))
        ui.panel(surf, r, (30, 60, 40, 220) if done else (20, 40, 70, 220), (120, 240, 160) if done else (120, 180, 240), 18)
        ui.text(surf, app.tr(m.text_key, n=m.target), 36, (r.x + ui.s(110), r.y + ui.s(40)), WHITE, anchor="midleft")
        ui.bar(surf, (r.x + ui.s(110), r.y + ui.s(80), r.w - ui.s(330), ui.s(24)), value / max(1, m.target),
               (90, 220, 120) if done else (90, 200, 255))
        ui.text(surf, f"{value}/{m.target}", 30, (r.right - ui.s(110), r.y + ui.s(92)), WHITE)
        icon = app.portrait("check", "", ui.s(70)) if done else app.portrait("star", "off", ui.s(60))
        surf.blit(icon, icon.get_rect(center=(r.x + ui.s(55), r.centery)))


# =========================================================================== skins
class SkinsScene(MenuScene):
    def __init__(self, app: App) -> None:
        super().__init__(app)
        keys = [k for k, _ in art.SKINS]
        cur = app.save.settings.get("skin", "classic")
        self.index = keys.index(cur) if cur in keys else 0

    def unlocked(self, i) -> bool:
        return self.app.save.progress["total_fish"] >= art.SKINS[i][1] or self.app.args.unlock_all

    def rects(self):
        ui = self.ui
        n = len(art.SKINS)
        w, gap = ui.s(320), ui.s(26)
        x0 = (ui.W - (n * w + (n - 1) * gap)) // 2
        return [pygame.Rect(x0 + i * (w + gap), ui.s(200), w, ui.s(600)) for i in range(n)]

    def choose(self, i) -> None:
        if self.unlocked(i):
            key = art.SKINS[i][0]
            self.app.save.settings["skin"] = key
            self.app.renderer.skin = key
            self.app.save.save()
            self.app.audio.play("powerup")
        else:
            self.app.audio.play("bonk")

    def handle(self, actions, event) -> None:
        n = len(art.SKINS)
        if "back" in actions:
            self.back()
            return
        if "m_left" in actions:
            self.index = (self.index - 1) % n
            self.click()
        if "m_right" in actions:
            self.index = (self.index + 1) % n
            self.click()
        if "ok" in actions:
            self.choose(self.index)
        if event is not None and event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
            for i, r in enumerate(self.rects()):
                if r.collidepoint(event.pos):
                    self.index = i
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        self.choose(i)
            if event.type == pygame.MOUSEBUTTONDOWN and self.back_rect().collidepoint(event.pos):
                self.back()

    def back_rect(self):
        ui = self.ui
        r = pygame.Rect(0, 0, ui.s(300), ui.s(70))
        r.midbottom = (ui.W // 2, ui.H - ui.s(40))
        return r

    def draw(self, surf) -> None:
        ui = self.ui
        self.draw_backdrop(surf, 150)
        self.draw_title(surf, self.tr("skins_title"))
        total = self.app.save.progress["total_fish"]
        ui.text(surf, self.tr("total_fish", n=total), 34, (ui.W / 2, ui.s(160)), WHITE)
        cur = self.app.save.settings.get("skin", "classic")
        for i, r in enumerate(self.rects()):
            key, need = art.SKINS[i]
            sel = i == self.index
            ok = self.unlocked(i)
            ui.panel(surf, r, (40, 70, 120, 230) if ok else (40, 44, 60, 220), (255, 200, 80) if sel else (120, 180, 240))
            img = self.app.portrait("tux", key, ui.s(280))
            if not ok:
                img = img.copy()
                img.fill((60, 60, 70, 255), special_flags=pygame.BLEND_RGBA_MULT)
            bob = math.sin(self.app.time * 4) * ui.s(6) if sel else 0
            surf.blit(img, img.get_rect(midbottom=(r.centerx, r.y + ui.s(330) + bob)))
            lines = ui.wrap(self.tr("skin_" + key), 32, r.w - ui.s(20))
            for k, line in enumerate(lines[:2]):
                ui.text(surf, line, 32, (r.centerx, r.y + ui.s(380) + k * ui.s(34)), YELLOW)
            if not ok:
                lock = self.app.portrait("lock", "", ui.s(70))
                surf.blit(lock, lock.get_rect(center=(r.centerx, r.y + ui.s(180))))
                for k, line in enumerate(ui.wrap(self.tr("skin_unlock", n=need), 24, r.w - ui.s(30))[:3]):
                    ui.text(surf, line, 24, (r.centerx, r.y + ui.s(470) + k * ui.s(28)), (200, 210, 230))
            else:
                label = self.tr("skin_selected") if key == cur else self.tr("skin_select")
                br = pygame.Rect(0, 0, r.w - ui.s(50), ui.s(64))
                br.midbottom = (r.centerx, r.bottom - ui.s(24))
                ui.button(surf, br, label, key == cur, True, 30)
        ui.button(surf, self.back_rect(), self.tr("back"), False, True, 36)


# =========================================================================== settings
class SettingsScene(MenuScene):
    def __init__(self, app: App) -> None:
        super().__init__(app)
        st = app.save.settings
        tr = app.tr
        self.langs = ["auto"] + sorted(i18n.available(), key=lambda c: i18n.available()[c].lower())
        self.res_options = [None] + [r for r in C.RESOLUTIONS if r[0] <= app.desktop[0] and r[1] <= app.desktop[1]]
        if len(self.res_options) == 1:
            self.res_options.append(C.RESOLUTIONS[0])

        def onoff(v):
            return tr("on") if v else tr("off")

        def res_label():
            r = st.get("resolution")
            cur = f"{app.resolution[0]} x {app.resolution[1]}"
            return f"{tr('settings_resolution')}: " + (cur if r else f"{tr('language_auto')} ({cur})")

        def lang_label():
            code = st.get("language", "auto")
            names = i18n.available()
            if code == "auto":
                return f"{tr('settings_language')}: {tr('language_auto')} ({names.get(tr.code, tr.code)})"
            return f"{tr('settings_language')}: {names.get(code, code)}"

        items = [
            {"label": lambda: f"{tr('settings_fullscreen')}: {onoff(st['fullscreen'])}",
             "action": app.toggle_fullscreen},
            {"label": res_label, "left": lambda: self._res(-1), "right": lambda: self._res(1)},
            {"label": lambda: f"{tr('settings_music')}: {int(round(st['music'] * 100))}%",
             "left": lambda: self._vol("music", -0.1), "right": lambda: self._vol("music", 0.1)},
            {"label": lambda: f"{tr('settings_sfx')}: {int(round(st['sfx'] * 100))}%",
             "left": lambda: self._vol("sfx", -0.1), "right": lambda: self._vol("sfx", 0.1)},
            {"label": lang_label, "left": lambda: self._lang(-1), "right": lambda: self._lang(1)},
            {"label": lambda: tr("back"), "action": self.back},
        ]
        u = app.ui
        self.menu = Menu(items, u.W // 2, u.s(240), u.s(1000), u.s(84), u.s(22))

    def _res(self, step) -> None:
        cur = self.app.save.settings.get("resolution")
        cur = tuple(cur) if cur else None
        opts = self.res_options
        i = opts.index(cur) if cur in opts else 0
        new = opts[(i + step) % len(opts)]
        self.app.set_resolution(new)
        u = self.app.ui
        self.menu.cx, self.menu.top, self.menu.w, self.menu.h, self.menu.gap = u.W // 2, u.s(240), u.s(1000), u.s(84), u.s(22)

    def _vol(self, key, delta) -> None:
        st = self.app.save.settings
        st[key] = round(max(0.0, min(1.0, st[key] + delta)), 2)
        self.app.audio.set_volumes(st["sfx"], st["music"])
        self.app.audio.play("fish")
        self.app.save.save()

    def _lang(self, step) -> None:
        cur = self.app.save.settings.get("language", "auto")
        i = self.langs.index(cur) if cur in self.langs else 0
        self.app.set_language(self.langs[(i + step) % len(self.langs)])

    def handle(self, actions, event) -> None:
        if "back" in actions:
            self.back()
            return
        if self.menu.handle(actions, event) and actions:
            self.click()

    def draw(self, surf) -> None:
        self.draw_backdrop(surf, 150)
        self.draw_title(surf, self.tr("menu_settings"))
        self.menu.draw(surf, self.ui, 38)


# =========================================================================== controls
class ControlsScene(MenuScene):
    def __init__(self, app: App) -> None:
        super().__init__(app)
        self.capture: str | None = None
        items = [{"label": (lambda a=a: a), "action": (lambda a=a: self._capture(a))} for a in ACTIONS]
        items.append({"label": lambda: self.tr("reset_defaults"), "action": self._reset})
        items.append({"label": lambda: self.tr("back"), "action": self.back})
        u = app.ui
        self.menu = Menu(items, u.W // 2, u.s(250), u.s(1300), u.s(78), u.s(16))

    def _capture(self, action) -> None:
        self.click()
        self.capture = action

    def _reset(self) -> None:
        self.app.save.reset_controls()
        self.app.save.save()
        self.app.audio.play("powerup")

    def handle(self, actions, event) -> None:
        if self.capture:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.capture = None
                else:
                    self.app.save.bind_key(self.capture, pygame.key.name(event.key))
                    self.app.save.save()
                    self.capture = None
                    self.click()
            elif event.type == pygame.JOYBUTTONDOWN:
                self.app.save.bind_pad(self.capture, event.button)
                self.app.save.save()
                self.capture = None
                self.click()
            return
        if "back" in actions:
            self.back()
            return
        if self.menu.handle(actions, event) and actions:
            self.click()

    def draw(self, surf) -> None:
        ui = self.ui
        self.draw_backdrop(surf, 150)
        self.draw_title(surf, self.tr("menu_controls"))
        rects = self.menu.rects()
        hx = rects[0]
        ui.text(surf, self.tr("keyboard"), 30, (hx.x + hx.w * 0.58, hx.y - ui.s(28)), YELLOW)
        ui.text(surf, self.tr("gamepad"), 30, (hx.x + hx.w * 0.87, hx.y - ui.s(28)), YELLOW)
        for i, (r, item) in enumerate(zip(rects, self.menu.items)):
            sel = i == self.menu.index
            if i < len(ACTIONS):
                act = ACTIONS[i]
                ui.button(surf, r, "", sel, True)
                ui.text(surf, self.tr("action_" + act), 36, (r.x + ui.s(30), r.centery), WHITE, anchor="midleft")
                keys = ", ".join(key_label(k) for k in self.app.save.keys.get(act, [])) or "-"
                pad = ", ".join(f"#{b}" for b in self.app.save.pad.get(act, [])) or "-"
                if self.capture == act:
                    blink = int(self.app.time * 3) % 2 == 0
                    keys = "..." if blink else ""
                ui.text(surf, keys, 32, (r.x + r.w * 0.58, r.centery), YELLOW if self.capture == act else WHITE)
                ui.text(surf, pad, 32, (r.x + r.w * 0.87, r.centery), WHITE)
            else:
                ui.button(surf, r, item["label"](), sel, True, 36)
        if self.capture:
            box = pygame.Rect(0, 0, ui.s(1200), ui.s(120))
            box.center = (ui.W // 2, ui.H - ui.s(100))
            ui.panel(surf, box, (90, 40, 20, 235), (255, 200, 80))
            ui.text(surf, self.tr("press_key"), 36, box.center, WHITE)


# =========================================================================== help
class HelpScene(MenuScene):
    KEYS = ("help_goal", "help_lanes", "help_jump", "help_duck", "help_ice", "help_trains",
            "help_zombies", "help_thief", "help_pickups", "help_powerups")

    def handle(self, actions, event) -> None:
        if actions & {"back", "ok"} or (event is not None and event.type == pygame.MOUSEBUTTONDOWN):
            self.back()

    def draw(self, surf) -> None:
        ui = self.ui
        self.draw_backdrop(surf, 170)
        self.draw_title(surf, self.tr("menu_help"))
        y = ui.s(170)
        x = ui.s(330)
        for key in self.KEYS:
            lines = ui.wrap(self.tr(key), 32, ui.W - x - ui.s(120))
            pygame.draw.circle(surf, (255, 180, 50), (x - ui.s(26), y + ui.s(16)), ui.s(9))
            for line in lines:
                ui.text(surf, line, 32, (x, y), WHITE, anchor="topleft")
                y += ui.s(36)
            y += ui.s(14)
        icons = [("powerup", k) for k in ("magnet", "board", "jetpack", "superjump", "coffee")] + \
                [("pickup", "fish"), ("pickup", "golden"), ("pickup", "key")]
        for i, (kind, key) in enumerate(icons):
            img = self.app.portrait(kind, key, ui.s(80))
            surf.blit(img, img.get_rect(center=(ui.s(140) + (i % 2) * ui.s(95), ui.s(210) + (i // 2) * ui.s(120))))
        skin = self.app.save.settings.get("skin", "classic")
        tux = self.app.portrait("tux", skin, ui.s(240))
        surf.blit(tux, tux.get_rect(bottomright=(ui.W - ui.s(30), ui.H - ui.s(20))))


# =========================================================================== play
class PlayScene(Scene):
    def __init__(self, app: App, level: Level) -> None:
        super().__init__(app)
        self.level = level
        seed = app.args.seed if app.args.seed is not None else random.randrange(1 << 30)
        self.world = World(level, seed=seed, multiplier=app.missions.multiplier)
        self.bot = Bot(self.world) if app.args.autoplay else None
        r = app.renderer
        r.reset_camera(self.world)
        r.particles.clear()
        r.finish_text = app.tr("safe_house")
        self.paused = False
        self.result: dict | None = None
        self.banner = 2.2
        self.toasts: list[list] = []
        self.swipe = None
        self.flash = 0.0
        self.committed = False
        tr = app.tr
        u = app.ui
        self.pause_menu = Menu([
            {"label": lambda: tr("resume"), "action": self.resume},
            {"label": lambda: tr("retry"), "action": self.retry},
            {"label": lambda: tr("main_menu"), "action": self.to_menu},
        ], u.W // 2, u.s(770), u.s(520), u.s(76), u.s(16))
        self.result_menu: Menu | None = None
        app.audio.play_music("game")
        app.audio.play("count")

    # ------------------------------------------------------------------ actions
    def resume(self) -> None:
        self.click()
        self.paused = False

    def retry(self) -> None:
        self.click()
        self.commit()
        self.app.go(PlayScene(self.app, self.level))

    def to_menu(self) -> None:
        self.click()
        self.commit()
        self.app.go(TitleScene(self.app))

    def next_level(self) -> None:
        self.click()
        nxt = self.level.number + 1
        self.app.go(PlayScene(self.app, level_by_number(nxt)))

    def focus_lost(self) -> None:
        if self.world.state == "run" and not self.app.args.headless:
            self.paused = True

    def run_stats(self) -> dict:
        s = dict(self.world.stats)
        s["score"] = self.world.score
        return s

    def commit(self) -> bool:
        if self.committed:
            return False
        self.committed = True
        return self.app.missions.commit(self.run_stats())

    # ------------------------------------------------------------------ input
    def handle(self, actions, event) -> None:
        if self.result is not None:
            if self.result_menu and self.result_menu.handle(actions, event) and actions:
                self.click()
            return
        if self.paused:
            if "back" in actions or "pause" in actions:
                self.resume()
                return
            if self.pause_menu.handle(actions, event) and actions:
                self.click()
            return
        if "pause" in actions or "back" in actions:
            self.paused = True
            self.pause_menu.index = 0
            return
        if self.bot:
            return
        w = self.world
        if "left" in actions:
            w.move(-1)
        if "right" in actions:
            w.move(1)
        if "jump" in actions:
            w.jump()
        if "duck" in actions:
            w.duck()
        # touch / mouse swipes
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.swipe = event.pos
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.swipe:
            dx = event.pos[0] - self.swipe[0]
            dy = event.pos[1] - self.swipe[1]
            self.swipe = None
            if max(abs(dx), abs(dy)) > self.ui.s(50):
                if abs(dx) > abs(dy):
                    w.move(1 if dx > 0 else -1)
                elif dy < 0:
                    w.jump()
                else:
                    w.duck()

    # ------------------------------------------------------------------ update
    def update(self, dt: float) -> None:
        super().update(dt)
        if self.paused:
            return
        w = self.world
        if self.bot:
            self.bot.update(dt)
        w.update(dt)
        self.app.renderer.follow(w, dt)
        self.banner = max(0.0, self.banner - dt)
        self.flash = max(0.0, self.flash - dt)
        for t in self.toasts:
            t[1] -= dt
        self.toasts = [t for t in self.toasts if t[1] > 0]
        self._events(w.pop_events())
        if w.state == "run":
            for m in self.app.missions.check(self.run_stats()):
                self.toasts.append([self.tr("mission_complete") + "  " + self.tr(m.text_key, n=m.target), 3.0])
                self.app.audio.play("powerup")
        if self.result is None and w.state != "run":
            wait = 1.6 if w.state == "caught" else 2.6
            if w.end_time > wait:
                self.finish()

    def _events(self, events) -> None:
        r = self.app.renderer
        audio = self.app.audio
        p = self.world.player
        for name, data in events:
            if name == "pickup":
                x, y, z, kind = data
                audio.play("golden" if kind != "fish" else "fish")
                col = (255, 210, 60) if kind == "golden" else (90, 230, 120) if kind == "key" else (150, 210, 255)
                r.burst(x, y, z, col, n=7, speed=2.5, size=0.06, life=0.4)
            elif name == "slip":
                audio.play("slip")
                r.burst(p.x, 0.1, p.z + 0.5, (230, 245, 255), n=14, speed=3, size=0.08, life=0.6)
            elif name in ("stumble", "crash"):
                audio.play(name)
                r.shake = 0.4 if name == "stumble" else 0.7
                self.flash = 0.3
            elif name == "land":
                audio.play("land")
                if p.y < 0.1:
                    r.burst(p.x, 0.05, p.z, (200, 200, 210), n=5, speed=1.5, size=0.07, life=0.3)
            elif name == "powerup":
                audio.play("powerup")
                r.burst(p.x, p.y + 0.8, p.z, (255, 240, 150), n=18, speed=4, size=0.07, life=0.6)
                self.toasts.append([self.tr("powerup_" + data), 1.6])
            elif name in ("board_break",):
                audio.play("shield_break")
                r.burst(p.x, 0.2, p.z, (160, 220, 255), n=20, speed=4, size=0.09, life=0.6)
                r.shake = 0.3
            elif name == "complete":
                audio.play("complete")
            elif name == "caught":
                audio.play("caught")
            elif name in ("jump", "superjump", "swoosh", "bonk", "duck", "horn"):
                audio.play("jump" if name == "superjump" else name)

    def finish(self) -> None:
        w = self.world
        save = self.app.save
        complete = w.state == "complete"
        res = {"complete": complete, "score": w.score, "fish": w.fish_count, "keys": w.keys,
               "distance": int(w.distance), "record": False, "stars": None, "mult_up": False}
        if self.level.endless:
            res["record"] = save.record_endless(w.score, w.fish_count, w.keys)
        else:
            stars = [complete, complete and w.fish_count >= self.level.fish_target, complete and w.stumbles == 0]
            res["stars"] = stars
            res["record"] = save.record_level(self.level.number, w.score, w.fish_count, stars, w.keys)
        res["mult_up"] = self.commit()
        self.result = res
        tr = self.tr
        u = self.ui
        items = []
        if complete and self.level.number < len(LEVELS) and not self.level.endless:
            items.append({"label": lambda: tr("next_level"), "action": self.next_level})
        items.append({"label": lambda: tr("retry"), "action": self.retry})
        items.append({"label": lambda: tr("main_menu"), "action": self.to_menu})
        self.result_menu = Menu(items, u.W // 2, u.s(700), u.s(520), u.s(70), u.s(14))

    # ------------------------------------------------------------------ draw
    def draw(self, surf) -> None:
        ui = self.ui
        self.app.renderer.draw(surf, self.world, self.app.time, 0 if self.paused else self.dt)
        self._hud(surf)
        if self.flash > 0:
            s = pygame.Surface((ui.W, ui.H), pygame.SRCALPHA)
            s.fill((255, 40, 40, int(120 * self.flash)))
            surf.blit(s, (0, 0))
        if self.paused:
            ui.dim(surf, 160)
            ui.text(surf, self.tr("paused"), 96, (ui.W / 2, ui.s(200)), YELLOW)
            draw_missions(self.app, surf, self.app.missions.progress(self.run_stats()), ui.W // 2, ui.s(270), ui.s(900))
            self.pause_menu.draw(surf, ui, 40)
        if self.result is not None:
            self._result(surf)

    def _hud(self, surf) -> None:
        ui = self.ui
        w = self.world
        tr = self.tr
        # score
        ui.panel(surf, (ui.s(24), ui.s(20), ui.s(400), ui.s(150)), (10, 20, 40, 170), (90, 140, 200), 18)
        ui.text(surf, f"{w.score:,}".replace(",", " "), 64, (ui.s(48), ui.s(70)), WHITE, anchor="midleft")
        mcol = (255, 200, 60) if w.coffee_t > 0 else (120, 255, 160)
        ui.text(surf, f"x{w.multiplier}", 44, (ui.s(400), ui.s(70)), mcol, anchor="midright")
        ui.text(surf, tr("distance", m=int(w.distance)), 36, (ui.s(48), ui.s(135)), (200, 220, 255), anchor="midleft")
        # fish & keys
        ui.panel(surf, (ui.W - ui.s(330), ui.s(20), ui.s(306), ui.s(150)), (10, 20, 40, 170), (90, 140, 200), 18)
        fish = self.app.portrait("pickup", "fish", ui.s(70))
        surf.blit(fish, fish.get_rect(center=(ui.W - ui.s(270), ui.s(65))))
        ui.text(surf, str(w.fish_count), 56, (ui.W - ui.s(50), ui.s(65)), WHITE, anchor="midright")
        key = self.app.portrait("pickup", "key", ui.s(64))
        surf.blit(key, key.get_rect(center=(ui.W - ui.s(270), ui.s(132))))
        ui.text(surf, str(w.keys), 44, (ui.W - ui.s(50), ui.s(132)), (160, 255, 170), anchor="midright")
        # level progress
        if not self.level.endless:
            bw = ui.s(640)
            bx = (ui.W - bw) // 2
            ui.text(surf, tr(self.level.name_key), 34, (ui.W / 2, ui.s(36)), WHITE)
            frac = min(1.0, w.distance / self.level.length)
            ui.bar(surf, (bx, ui.s(66), bw, ui.s(22)), frac, (120, 220, 255))
            tux = self.app.portrait("tux", self.app.save.settings.get("skin", "classic"), ui.s(56))
            surf.blit(tux, tux.get_rect(center=(bx + bw * frac, ui.s(77))))
            cfrac = max(0.0, (w.distance - w.thief_dist * 12) / self.level.length)
            ch = self.app.portrait("chaser", w.chaser, ui.s(46))
            surf.blit(ch, ch.get_rect(center=(bx + bw * min(frac, cfrac), ui.s(77))))
        # power-ups
        y = ui.s(200)
        for kind, attr, total in POWERUP_TIMERS:
            v = getattr(w, attr)
            if v > 0:
                img = self.app.portrait("powerup", kind, ui.s(64))
                surf.blit(img, img.get_rect(center=(ui.s(62), y)))
                ui.bar(surf, (ui.s(102), y - ui.s(10), ui.s(200), ui.s(20)), v / total, (255, 200, 90))
                y += ui.s(76)
        if w.board:
            img = self.app.portrait("powerup", "board", ui.s(64))
            surf.blit(img, img.get_rect(center=(ui.s(62), y)))
        # warnings
        if w.state == "run" and w.stumble_timer > 0:
            pulse = 0.5 + 0.5 * math.sin(self.app.time * 10)
            s = pygame.Surface((ui.W, ui.H), pygame.SRCALPHA)
            pygame.draw.rect(s, (255, 30, 30, int(60 + 80 * pulse)), s.get_rect(), ui.s(18))
            surf.blit(s, (0, 0))
            ui.text(surf, tr("chaser_close", chaser=self.app.chaser_name(w.chaser)), 40,
                    (ui.W / 2, ui.s(150)), (255, 120 + int(100 * pulse), 100))
        if w.player.sliding:
            ui.text(surf, tr("slippery"), 56, (ui.W / 2, ui.s(240)), (190, 235, 255))
        if self.banner > 0:
            a = min(1.0, self.banner)
            sz = 150 + int((2.2 - self.banner) * 30)
            ui.text(surf, tr("run"), sz, (ui.W / 2, ui.H * 0.42), (255, int(200 * a), 60))
            ui.text(surf, tr("chased_by", chaser=self.app.chaser_name(w.chaser)), 40, (ui.W / 2, ui.H * 0.55), WHITE)
        for i, (text, _t) in enumerate(self.toasts[-3:]):
            ui.text(surf, text, 38, (ui.W / 2, ui.s(320) + i * ui.s(52)), (255, 240, 140))

    def _result(self, surf) -> None:
        ui = self.ui
        res = self.result
        tr = self.tr
        ui.dim(surf, 150)
        box = pygame.Rect(0, 0, ui.s(1000), ui.s(920))
        box.center = (ui.W // 2, ui.H // 2)
        ui.panel(surf, box)
        title = tr("level_complete") if res["complete"] else tr("caught", chaser=self.app.chaser_name(self.world.chaser))
        ui.text(surf, title, 64, (box.centerx, box.y + ui.s(70)), YELLOW)
        img = self.app.portrait("tux" if res["complete"] else "chaser",
                                self.app.save.settings.get("skin", "classic") if res["complete"] else self.world.chaser,
                                ui.s(170))
        surf.blit(img, img.get_rect(center=(box.x + ui.s(140), box.y + ui.s(240))))
        x = box.x + ui.s(280)
        y = box.y + ui.s(150)
        for label, value in ((tr("score"), f"{res['score']:,}".replace(",", " ")), (tr("fish"), res["fish"]),
                             (tr("keys"), res["keys"]), ("", tr("distance", m=res["distance"]))):
            ui.text(surf, f"{label}{': ' if label else ''}{value}", 44, (x, y), WHITE, anchor="midleft")
            y += ui.s(54)
        if res["stars"] is not None:
            labels = (tr("star_finish"), tr("star_fish", n=self.level.fish_target), tr("star_clean"))
            for k, (got, lab) in enumerate(zip(res["stars"], labels)):
                st = self.app.portrait("star", "on" if got else "off", ui.s(50))
                sy = box.y + ui.s(400) + k * ui.s(60)
                surf.blit(st, st.get_rect(center=(box.x + ui.s(120), sy)))
                ui.text(surf, lab, 32, (box.x + ui.s(165), sy), WHITE if got else (170, 180, 200), anchor="midleft")
        msgs = []
        if res["record"]:
            msgs.append(tr("new_record"))
        if res["mult_up"]:
            msgs.append(tr("multiplier_up", n=self.app.missions.multiplier))
        for k, m in enumerate(msgs):
            ui.text(surf, m, 40, (box.centerx, box.y + ui.s(600) + k * ui.s(46)), (120, 255, 160))
        if self.result_menu:
            self.result_menu.top = box.y + ui.s(600) + len(msgs) * ui.s(46) + ui.s(10)
            self.result_menu.h = ui.s(62)
            self.result_menu.draw(surf, ui, 34)
