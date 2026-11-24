"""Fonts, text and widget helpers."""

from __future__ import annotations

import pygame

from . import i18n

WHITE = (255, 255, 255)
YELLOW = (255, 214, 60)
OUTLINE = (15, 25, 45)
PANEL = (16, 30, 58, 215)
PANEL_EDGE = (120, 180, 240)
ACCENT = (255, 140, 40)


class UI:
    def __init__(self, width: int, height: int, translator: i18n.Translator) -> None:
        self.W, self.H = width, height
        self.u = height / 1080.0
        self.tr = translator
        self._fonts: dict = {}
        self._text: dict = {}
        self._cjk_path = None
        self.refresh_fonts()

    def refresh_fonts(self) -> None:
        self._fonts.clear()
        self._text.clear()
        self._cjk_path = i18n.find_cjk_font() if self.tr.needs_cjk_font else None

    def font(self, size: int) -> pygame.font.Font:
        size = max(6, int(size))
        f = self._fonts.get(size)
        if f is None:
            if self._cjk_path:
                try:
                    f = pygame.font.Font(self._cjk_path, int(size * 0.78))
                except (OSError, RuntimeError):
                    f = pygame.font.Font(None, size)
            else:
                f = pygame.font.Font(None, size)
            self._fonts[size] = f
        return f

    def s(self, v: float) -> int:
        return int(v * self.u)

    def render(self, text: str, size: int, color=WHITE, outline=OUTLINE, width: int = 0) -> pygame.Surface:
        key = (text, size, color, outline, width)
        img = self._text.get(key)
        if img is not None:
            return img
        f = self.font(size)
        base = f.render(text, True, color)
        if outline:
            o = max(1, size // 16) if not width else width
            out = pygame.Surface((base.get_width() + o * 2, base.get_height() + o * 2), pygame.SRCALPHA)
            edge = f.render(text, True, outline)
            for dx in range(-o, o + 1, max(1, o)):
                for dy in range(-o, o + 1, max(1, o)):
                    if dx or dy:
                        out.blit(edge, (o + dx, o + dy))
            out.blit(base, (o, o))
            img = out
        else:
            img = base
        if len(self._text) > 800:
            self._text.clear()
        self._text[key] = img
        return img

    def text(self, surf, text, size, pos, color=WHITE, anchor="center", outline=OUTLINE) -> pygame.Rect:
        img = self.render(text, self.s(size), color, outline)
        rect = img.get_rect(**{anchor: (int(pos[0]), int(pos[1]))})
        surf.blit(img, rect)
        return rect

    def wrap(self, text: str, size: int, max_width: int) -> list[str]:
        f = self.font(self.s(size))
        if " " not in text:
            # CJK and other scripts without spaces: wrap per character
            lines, cur = [], ""
            for ch in text:
                if f.size(cur + ch)[0] > max_width and cur:
                    lines.append(cur)
                    cur = ch
                else:
                    cur += ch
            return lines + ([cur] if cur else [])
        lines, cur = [], ""
        for word in text.split(" "):
            test = (cur + " " + word).strip()
            if f.size(test)[0] > max_width and cur:
                lines.append(cur)
                cur = word
            else:
                cur = test
        if cur:
            lines.append(cur)
        return lines

    def panel(self, surf, rect, color=PANEL, edge=PANEL_EDGE, radius=24) -> None:
        r = pygame.Rect(rect)
        s = pygame.Surface(r.size, pygame.SRCALPHA)
        pygame.draw.rect(s, color, s.get_rect(), border_radius=self.s(radius))
        pygame.draw.rect(s, (*edge, 200), s.get_rect(), max(2, self.s(3)), border_radius=self.s(radius))
        surf.blit(s, r.topleft)

    def button(self, surf, rect, label, selected=False, enabled=True, size=44) -> None:
        r = pygame.Rect(rect)
        base = (40, 90, 160) if enabled else (60, 65, 80)
        if selected:
            base = (240, 130, 30) if enabled else (110, 90, 80)
        shadow = r.move(0, self.s(6))
        pygame.draw.rect(surf, (10, 20, 40), shadow, border_radius=self.s(18))
        pygame.draw.rect(surf, base, r, border_radius=self.s(18))
        hl = pygame.Rect(r.x + self.s(6), r.y + self.s(5), r.w - self.s(12), r.h // 2 - self.s(4))
        hls = pygame.Surface(hl.size, pygame.SRCALPHA)
        pygame.draw.rect(hls, (255, 255, 255, 45), hls.get_rect(), border_radius=self.s(14))
        surf.blit(hls, hl)
        if selected:
            pygame.draw.rect(surf, (255, 240, 200), r, max(2, self.s(4)), border_radius=self.s(18))
        self.text(surf, label, size, r.center, WHITE if enabled else (170, 170, 180))

    def bar(self, surf, rect, frac, fg=(90, 200, 255), bg=(20, 30, 50, 180)) -> None:
        r = pygame.Rect(rect)
        s = pygame.Surface(r.size, pygame.SRCALPHA)
        pygame.draw.rect(s, bg, s.get_rect(), border_radius=r.h // 2)
        surf.blit(s, r.topleft)
        w = int(r.w * max(0.0, min(1.0, frac)))
        if w > 2:
            pygame.draw.rect(surf, fg, (r.x, r.y, w, r.h), border_radius=r.h // 2)

    def dim(self, surf, alpha=140) -> None:
        s = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        s.fill((5, 10, 25, alpha))
        surf.blit(s, (0, 0))


class Menu:
    """A vertical list of items, navigable by keyboard, gamepad and mouse."""

    def __init__(self, items: list, center_x: int, top: int, width: int, height: int, gap: int):
        # items: list of dicts {label: callable->str, action: callable, left/right: callable, enabled: callable}
        self.items = items
        self.index = 0
        self.cx, self.top, self.w, self.h, self.gap = center_x, top, width, height, gap
        self._skip_disabled(1)

    def rects(self) -> list[pygame.Rect]:
        out = []
        for i in range(len(self.items)):
            r = pygame.Rect(0, 0, self.w, self.h)
            r.midtop = (self.cx, self.top + i * (self.h + self.gap))
            out.append(r)
        return out

    def _enabled(self, i) -> bool:
        fn = self.items[i].get("enabled")
        return fn() if fn else True

    def _skip_disabled(self, step) -> None:
        for _ in range(len(self.items)):
            if self._enabled(self.index):
                return
            self.index = (self.index + step) % len(self.items)

    def move(self, step: int) -> None:
        self.index = (self.index + step) % len(self.items)
        self._skip_disabled(step)

    def handle(self, actions: set, event=None) -> bool:
        """Returns True when something was activated or changed."""
        item = self.items[self.index]
        if "m_up" in actions:
            self.move(-1)
            return True
        if "m_down" in actions:
            self.move(1)
            return True
        if "m_left" in actions and item.get("left"):
            item["left"]()
            return True
        if "m_right" in actions and item.get("right"):
            item["right"]()
            return True
        if "ok" in actions and self._enabled(self.index):
            fn = item.get("action") or item.get("right")
            if fn:
                fn()
            return True
        if event is not None and event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
            for i, r in enumerate(self.rects()):
                if r.collidepoint(event.pos) and self._enabled(i):
                    self.index = i
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        it = self.items[i]
                        if it.get("action"):
                            it["action"]()
                        elif it.get("right"):
                            # click on the left half decreases, right half increases
                            if event.pos[0] < r.centerx and it.get("left"):
                                it["left"]()
                            else:
                                it["right"]()
                        return True
        return False

    def draw(self, surf, ui: UI, size=44) -> None:
        for i, (r, item) in enumerate(zip(self.rects(), self.items)):
            label = item["label"]()
            if item.get("right") and not item.get("action"):
                label = f"<  {label}  >"
            ui.button(surf, r, label, i == self.index, self._enabled(i), size)
