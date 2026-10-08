"""
Wordle in Pygame.

Files that sit next to this script:
  words_bank.txt   words that can be picked as the answer
  words_valid.txt  every word you are allowed to guess
  stats.json       created automatically to save your stats

Bank words are always allowed as guesses too, so you never get a
"Not in word list" on the actual answer.

Controls:
  Type letters, BACKSPACE to delete, ENTER to submit.
  You can also click the on-screen keyboard.
  Top left button restarts, top right button shows your stats.
  ESC closes a popup (or quits if no popup is open).
"""

import json
import math
import os
import random
import sys

import pygame

# ---------------------------------------------------------------- settings
WIDTH, HEIGHT = 500, 800
FPS = 120
WORD_LEN = 5
MAX_GUESSES = 6

# colors
BG_TOP = (24, 24, 27)
BG_BOTTOM = (13, 13, 14)
PANEL = (30, 30, 33)
PANEL_BORDER = (62, 62, 66)
TEXT = (248, 248, 248)
SUBTEXT = (160, 160, 166)
EMPTY_BORDER = (58, 58, 61)
FILLED_BORDER = (112, 112, 116)
GREEN = (83, 141, 78)
YELLOW = (181, 159, 59)
GRAY = (58, 58, 61)
LOSS_RED = (166, 68, 68)
KEY_BG = (129, 131, 132)
BAR_GRAY = (70, 70, 74)
DIVIDER = (48, 48, 52)
TOAST_BG = (248, 248, 248)
TOAST_TEXT = (18, 18, 19)
CONFETTI_COLORS = [GREEN, YELLOW, (240, 240, 240), (110, 170, 240), (235, 120, 170)]

CORRECT, PRESENT, ABSENT = 2, 1, 0
STATE_COLORS = {CORRECT: GREEN, PRESENT: YELLOW, ABSENT: GRAY}

# layout
HEADER_H = 72
TILE = 62
GAP = 6
GRID_TOP = 98
GRID_LEFT = (WIDTH - (WORD_LEN * TILE + (WORD_LEN - 1) * GAP)) // 2
GRID_BOTTOM = GRID_TOP + MAX_GUESSES * TILE + (MAX_GUESSES - 1) * GAP

KEY_W, KEY_H, KEY_GAP, KEY_ROW_GAP, WIDE_KEY_W = 41, 58, 6, 8, 64
KEY_ROWS = ["qwertyuiop", "asdfghjkl", ["ENTER"] + list("zxcvbnm") + ["BACK"]]
KEYBOARD_TOP = HEIGHT - (3 * KEY_H + 2 * KEY_ROW_GAP) - 22

# animation timings (ms)
FLIP_DUR = 460
FLIP_STAGGER = 250
POP_DUR = 120
KEY_PRESS_DUR = 140
SHAKE_DUR = 420
BOUNCE_DUR = 500
BOUNCE_STAGGER = 90
TOAST_DUR = 1600
INTRO_DUR = 280
INTRO_STAGGER = 14
WIN_MODAL_DELAY = 1400
LOSE_MODAL_DELAY = 1100

WIN_WORDS = ["Genius", "Magnificent", "Impressive", "Splendid", "Great", "Phew"]


# ---------------------------------------------------------------- helpers
def clamp01(t):
    return 0.0 if t < 0 else 1.0 if t > 1 else t


def ease_out_cubic(t):
    t = clamp01(t)
    return 1 - (1 - t) ** 3


def ease_in_out(t):
    t = clamp01(t)
    return t * t * (3 - 2 * t)


def ease_out_back(t):
    t = clamp01(t)
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def approach(value, target, step):
    if value < target:
        return min(target, value + step)
    return max(target, value - step)


def lerp_color(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def lighten(color, amount):
    return tuple(min(255, c + amount) for c in color)


def darken(color, amount):
    return tuple(max(0, c - amount) for c in color)


# ---------------------------------------------------------------- data
def load_words(path):
    """Read 5-letter words from a text file. Anything else in the file is skipped."""
    words = set()
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                w = line.strip().lower()
                if len(w) == WORD_LEN and w.isascii() and w.isalpha():
                    words.add(w)
    except FileNotFoundError:
        pass
    return words


def default_stats():
    return {"played": 0, "wins": 0, "streak": 0, "best": 0, "dist": [0] * MAX_GUESSES}


def load_stats(path):
    stats = default_stats()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for key in stats:
            if key in data:
                stats[key] = data[key]
        if not isinstance(stats["dist"], list) or len(stats["dist"]) != MAX_GUESSES:
            stats["dist"] = [0] * MAX_GUESSES
    except (OSError, ValueError):
        pass
    return stats


def save_stats(path, stats):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(stats, f)
    except OSError:
        pass


def score_guess(guess, answer):
    """
    Score a guess the real Wordle way, handling repeated letters.
    Greens are claimed first, then yellows only use up letters that are left.
    """
    result = [ABSENT] * WORD_LEN
    leftover = {}

    for i, (g, a) in enumerate(zip(guess, answer)):
        if g == a:
            result[i] = CORRECT
        else:
            leftover[a] = leftover.get(a, 0) + 1

    for i, g in enumerate(guess):
        if result[i] != CORRECT and leftover.get(g, 0) > 0:
            result[i] = PRESENT
            leftover[g] -= 1

    return result


# ---------------------------------------------------------------- ui bits
class Button:
    def __init__(self, rect, label, action, primary=False, icon=None):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.action = action
        self.primary = primary
        self.icon = icon
        self.hover = 0.0

    def update(self, mouse, dt, enabled=True):
        target = 1.0 if enabled and self.rect.collidepoint(mouse) else 0.0
        self.hover += (target - self.hover) * min(1.0, dt * 14)


# ---------------------------------------------------------------- game
class Wordle:
    def __init__(self, bank, valid, stats_path):
        pygame.init()
        pygame.display.set_caption("Wordle")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()

        names = "helveticaneue,helvetica,arial,dejavusans,freesans"
        sf = pygame.font.SysFont
        self.fonts = {
            "title": sf(names, 36, bold=True),
            "tile": sf(names, 34, bold=True),
            "mini": sf(names, 28, bold=True),
            "key": sf(names, 20, bold=True),
            "key_small": sf(names, 13, bold=True),
            "toast": sf(names, 17, bold=True),
            "modal_title": sf(names, 40, bold=True),
            "panel_title": sf(names, 28, bold=True),
            "h2": sf(names, 14, bold=True),
            "body": sf(names, 17),
            "stat_num": sf(names, 32, bold=True),
            "stat_label": sf(names, 12),
            "button": sf(names, 18, bold=True),
            "bar": sf(names, 14, bold=True),
            "hint": sf(names, 15),
        }

        self.bank = sorted(bank)
        self.valid = set(valid) | set(bank)
        self.stats_path = stats_path
        self.stats = load_stats(stats_path)

        self.background = self._make_background()
        self.keys = self._build_keyboard()
        self.key_colors = {label: list(KEY_BG) for label, _ in self.keys}
        self.key_press = {}
        self.letter_cache = {}

        self.header_buttons = [
            Button((14, 15, 42, 42), "", self.restart, icon="restart"),
            Button((WIDTH - 56, 15, 42, 42), "", lambda: self.open_modal("stats"), icon="stats"),
        ]

        # popup state
        self.modal = None          # None, "end" or "stats"
        self.modal_open = False
        self.modal_t = 0.0         # panel slide/fade progress
        self.overlay_t = 0.0       # dark background progress
        self.modal_opened_at = 0
        self.modal_size = (420, 380)
        self.modal_buttons = []

        self.confetti = []
        self.new_game()

    # ------------------------------------------------------------ setup
    def _make_background(self):
        surf = pygame.Surface((WIDTH, HEIGHT))
        for y in range(HEIGHT):
            pygame.draw.line(surf, lerp_color(BG_TOP, BG_BOTTOM, y / HEIGHT), (0, y), (WIDTH, y))
        return surf

    def _build_keyboard(self):
        keys = []
        for row_i, row in enumerate(KEY_ROWS):
            widths = [WIDE_KEY_W if len(k) > 1 else KEY_W for k in row]
            row_w = sum(widths) + KEY_GAP * (len(row) - 1)
            x = (WIDTH - row_w) // 2
            y = KEYBOARD_TOP + row_i * (KEY_H + KEY_ROW_GAP)
            for label, w in zip(row, widths):
                keys.append((label, pygame.Rect(x, y, w, KEY_H)))
                x += w + KEY_GAP
        return keys

    def new_game(self):
        self.answer = random.choice(self.bank)
        self.guesses = []          # list of (word, result)
        self.current = ""
        self.key_states = {}       # letter -> best state seen
        self.game_over = False
        self.won = False

        self.revealing = False
        self.reveal_start = 0
        self.pops = {}
        self.shake_start = None
        self.bounce_start = None
        self.toast_text = None
        self.toast_start = 0
        self.pending_modal_at = None
        self.intro_start = pygame.time.get_ticks()
        self.confetti = []

    def restart(self):
        if self.revealing:
            return
        # walking away from a game you already started counts as a loss
        if self.guesses and not self.game_over:
            self.record_result(False)
        self.modal = None
        self.modal_open = False
        self.modal_t = 0.0
        self.overlay_t = 0.0
        self.new_game()

    def record_result(self, won):
        s = self.stats
        s["played"] += 1
        if won:
            s["wins"] += 1
            s["streak"] += 1
            s["best"] = max(s["best"], s["streak"])
            s["dist"][len(self.guesses) - 1] += 1
        else:
            s["streak"] = 0
        save_stats(self.stats_path, s)

    # ------------------------------------------------------------ popups
    def open_modal(self, kind):
        if self.revealing:
            return
        self.modal = kind
        self.modal_open = True
        self.modal_t = 0.0
        self.modal_opened_at = pygame.time.get_ticks()
        self.pending_modal_at = None

        if kind == "end":
            self.modal_size = (420, 380)
            w, h = self.modal_size
            self.modal_buttons = [
                Button((22, 262, 180, 52), "Play again", self.restart, primary=True),
                Button((w - 202, 262, 180, 52), "Stats", lambda: self.open_modal("stats")),
            ]
        else:
            self.modal_size = (420, 484)
            w, h = self.modal_size
            label = "Play again" if self.game_over else "Keep playing"
            action = self.restart if self.game_over else self.close_modal
            self.modal_buttons = [
                Button((w - 52, 14, 38, 38), "", self.close_modal, icon="close"),
                Button(((w - 220) // 2, h - 74, 220, 52), label, action, primary=True),
            ]

    def close_modal(self):
        self.modal_open = False

    def modal_rect(self):
        w, h = self.modal_size
        slide = (1 - ease_out_cubic(self.modal_t)) * 40
        return pygame.Rect((WIDTH - w) // 2, (HEIGHT - h) // 2 + int(slide), w, h)

    def to_modal_local(self, pos):
        if self.modal is None:
            return (-9999, -9999)
        r = self.modal_rect()
        return (pos[0] - r.x, pos[1] - r.y)

    # ------------------------------------------------------------ input
    def show_toast(self, text):
        self.toast_text = text
        self.toast_start = pygame.time.get_ticks()

    def press_key(self, label):
        self.key_press[label] = pygame.time.get_ticks()
        self.handle_key(label)

    def handle_key(self, key):
        if self.revealing:
            return
        if self.game_over:
            if key == "ENTER":
                self.restart()
            return

        if key == "ENTER":
            self.submit()
        elif key == "BACK":
            self.current = self.current[:-1]
        elif len(key) == 1 and key.isalpha() and len(self.current) < WORD_LEN:
            self.current += key
            self.pops[len(self.current) - 1] = pygame.time.get_ticks()

    def submit(self):
        now = pygame.time.get_ticks()
        if len(self.current) < WORD_LEN:
            self.show_toast("Not enough letters")
            self.shake_start = now
            return
        if self.current not in self.valid:
            self.show_toast("Not in word list")
            self.shake_start = now
            return

        result = score_guess(self.current, self.answer)
        self.guesses.append((self.current, result))
        self.current = ""
        self.pops.clear()
        self.revealing = True
        self.reveal_start = now

    def finish_reveal(self, now):
        self.revealing = False
        word, result = self.guesses[-1]

        for ch, state in zip(word, result):
            self.key_states[ch] = max(self.key_states.get(ch, -1), state)

        if all(s == CORRECT for s in result):
            self.won = True
            self.game_over = True
            self.record_result(True)
            self.bounce_start = now
            self.show_toast(WIN_WORDS[len(self.guesses) - 1])
            self.spawn_confetti()
            self.pending_modal_at = now + WIN_MODAL_DELAY
        elif len(self.guesses) == MAX_GUESSES:
            self.game_over = True
            self.record_result(False)
            self.show_toast(self.answer.upper())
            self.pending_modal_at = now + LOSE_MODAL_DELAY

    def handle_event(self, event):
        """Returns False when the game should quit."""
        if event.type == pygame.KEYDOWN:
            if self.modal_open:
                if event.key == pygame.K_ESCAPE:
                    self.close_modal()
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    if self.game_over:
                        self.restart()
                    else:
                        self.close_modal()
                return True

            if event.key == pygame.K_ESCAPE:
                return False
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.press_key("ENTER")
            elif event.key == pygame.K_BACKSPACE:
                self.press_key("BACK")
            elif event.unicode and event.unicode.isascii() and event.unicode.isalpha():
                self.press_key(event.unicode.lower())

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.modal_open:
                local = self.to_modal_local(event.pos)
                for b in self.modal_buttons:
                    if b.rect.collidepoint(local):
                        b.action()
                        return True
                if not self.modal_rect().collidepoint(event.pos):
                    self.close_modal()
                return True

            for b in self.header_buttons:
                if b.rect.collidepoint(event.pos):
                    b.action()
                    return True
            for label, rect in self.keys:
                if rect.collidepoint(event.pos):
                    self.press_key(label)
                    return True
        return True

    # ------------------------------------------------------------ update
    def spawn_confetti(self):
        row_y = GRID_TOP + (len(self.guesses) - 1) * (TILE + GAP) + TILE // 2
        for i in range(160):
            burst = i < 70
            self.confetti.append({
                "x": WIDTH / 2 + random.uniform(-150, 150) if burst else random.uniform(0, WIDTH),
                "y": row_y if burst else random.uniform(-HEIGHT * 0.6, -10),
                "vx": random.uniform(-260, 260) if burst else random.uniform(-30, 30),
                "vy": random.uniform(-520, -240) if burst else random.uniform(40, 140),
                "rot": random.uniform(0, math.tau),
                "vr": random.uniform(-7, 7),
                "w": random.uniform(6, 11),
                "h": random.uniform(3, 6),
                "c": random.choice(CONFETTI_COLORS),
                "phase": random.uniform(0, math.tau),
            })

    def update(self, dt):
        now = pygame.time.get_ticks()

        if self.revealing:
            if now - self.reveal_start >= FLIP_STAGGER * (WORD_LEN - 1) + FLIP_DUR:
                self.finish_reveal(now)

        if self.pending_modal_at is not None and now >= self.pending_modal_at:
            self.open_modal("end")

        # keyboard colors fade toward their new state instead of snapping
        k = min(1.0, dt * 9)
        for label, color in self.key_colors.items():
            state = self.key_states.get(label)
            target = STATE_COLORS[state] if state is not None else KEY_BG
            for i in range(3):
                color[i] += (target[i] - color[i]) * k

        target = 1.0 if self.modal_open else 0.0
        self.overlay_t = approach(self.overlay_t, target, dt / 0.25)
        self.modal_t = approach(self.modal_t, target, dt / 0.32)
        if not self.modal_open and self.modal_t <= 0 and self.overlay_t <= 0:
            self.modal = None

        mouse = pygame.mouse.get_pos()
        for b in self.header_buttons:
            b.update(mouse, dt, enabled=not self.modal_open)
        local = self.to_modal_local(mouse)
        for b in self.modal_buttons:
            b.update(local, dt, enabled=self.modal_open)

        t = now / 1000
        for p in self.confetti:
            p["vy"] = min(p["vy"] + 520 * dt, 230)
            p["vx"] *= 1 - 1.6 * dt
            p["x"] += (p["vx"] + math.sin(t * 3 + p["phase"]) * 35) * dt
            p["y"] += p["vy"] * dt
            p["rot"] += p["vr"] * dt
        self.confetti = [p for p in self.confetti if p["y"] < HEIGHT + 30]

    # ------------------------------------------------------------ drawing helpers
    def letter_surface(self, letter, font_key):
        key = (letter, font_key)
        if key not in self.letter_cache:
            self.letter_cache[key] = self.fonts[font_key].render(letter.upper(), True, TEXT)
        return self.letter_cache[key]

    def draw_tile(self, surf, cx, cy, size, letter, fill, border, sx=1.0, sy=1.0, font_key="tile"):
        w = max(1, int(size * sx))
        h = max(1, int(size * sy))
        rect = pygame.Rect(0, 0, w, h)
        rect.center = (cx, cy)
        radius = min(6, w // 2, h // 2)

        if fill:
            pygame.draw.rect(surf, fill, rect, border_radius=radius)
        else:
            pygame.draw.rect(surf, border or EMPTY_BORDER, rect, 2, border_radius=radius)

        if letter:
            img = self.letter_surface(letter, font_key)
            if sx != 1.0 or sy != 1.0:
                iw = max(1, int(img.get_width() * sx))
                ih = max(1, int(img.get_height() * sy))
                img = pygame.transform.smoothscale(img, (iw, ih))
            surf.blit(img, img.get_rect(center=(cx, cy + 1)))

    def draw_text(self, surf, text, font_key, color, center):
        img = self.fonts[font_key].render(text, True, color)
        surf.blit(img, img.get_rect(center=center))

    def draw_icon(self, surf, icon, center, color):
        cx, cy = center
        if icon == "stats":
            for dx, h in ((-8, 9), (-1, 17), (6, 12)):
                pygame.draw.rect(surf, color, (cx + dx - 2, cy + 9 - h, 6, h), border_radius=1)
        elif icon == "restart":
            r = 9
            pts = []
            for i in range(31):
                a = math.radians(70 + 310 * i / 30)
                pts.append((cx + r * math.cos(a), cy - r * math.sin(a)))
            pygame.draw.lines(surf, color, False, pts, 3)
            end = math.radians(20)
            px, py = cx + r * math.cos(end), cy - r * math.sin(end)
            dx, dy = -math.sin(end), -math.cos(end)
            nx, ny = -dy, dx
            tip = (px + dx * 6, py + dy * 6)
            b1 = (px - dx * 2 + nx * 5, py - dy * 2 + ny * 5)
            b2 = (px - dx * 2 - nx * 5, py - dy * 2 - ny * 5)
            pygame.draw.polygon(surf, color, [tip, b1, b2])
        elif icon == "close":
            pygame.draw.line(surf, color, (cx - 7, cy - 7), (cx + 7, cy + 7), 3)
            pygame.draw.line(surf, color, (cx - 7, cy + 7), (cx + 7, cy - 7), 3)

    def draw_button(self, surf, b, bg=PANEL):
        if b.icon:
            if b.hover > 0.02:
                circle = lerp_color(bg, lighten(bg, 30), b.hover)
                pygame.draw.circle(surf, circle, b.rect.center, b.rect.w // 2)
            self.draw_icon(surf, b.icon, b.rect.center, lerp_color(SUBTEXT, TEXT, b.hover))
            return

        base = GREEN if b.primary else (60, 60, 65)
        color = lerp_color(base, lighten(base, 22), b.hover)
        lift = int(round(2 * b.hover))
        rect = b.rect.move(0, -lift)
        pygame.draw.rect(surf, darken(base, 30), b.rect.move(0, 3), border_radius=10)
        pygame.draw.rect(surf, color, rect, border_radius=10)
        self.draw_text(surf, b.label, "button", TEXT, rect.center)

    # ------------------------------------------------------------ drawing
    def draw_header(self):
        self.draw_text(self.screen, "WORDLE", "title", TEXT, (WIDTH // 2, 37))
        pygame.draw.line(self.screen, DIVIDER, (0, HEADER_H), (WIDTH, HEADER_H), 1)
        for b in self.header_buttons:
            self.draw_button(self.screen, b, bg=BG_TOP)

    def draw_grid(self):
        now = pygame.time.get_ticks()
        current_row = len(self.guesses)

        for r in range(MAX_GUESSES):
            row_offset_x = 0
            if r == current_row and self.shake_start is not None:
                t = (now - self.shake_start) / SHAKE_DUR
                if t < 1:
                    row_offset_x = int(math.sin(t * math.pi * 8) * 11 * (1 - t) ** 1.5)
                else:
                    self.shake_start = None

            for c in range(WORD_LEN):
                cx = GRID_LEFT + c * (TILE + GAP) + TILE // 2 + row_offset_x
                cy = GRID_TOP + r * (TILE + GAP) + TILE // 2
                letter, fill, border = "", None, EMPTY_BORDER
                sx = sy = 1.0

                if r < len(self.guesses):
                    word, result = self.guesses[r]
                    letter = word[c]
                    revealed = True

                    if self.revealing and r == len(self.guesses) - 1:
                        p = (now - self.reveal_start - c * FLIP_STAGGER) / FLIP_DUR
                        if p < 0:
                            revealed = False
                        elif p < 1:
                            pe = ease_in_out(p)
                            sy = abs(math.cos(math.pi * pe))
                            revealed = pe >= 0.5

                    if revealed:
                        fill = STATE_COLORS[result[c]]
                    else:
                        border = FILLED_BORDER

                    if self.won and r == len(self.guesses) - 1 and self.bounce_start:
                        t = (now - self.bounce_start - c * BOUNCE_STAGGER) / BOUNCE_DUR
                        if 0 <= t < 1:
                            cy -= int(math.sin(math.pi * t) * 24)

                elif r == current_row and c < len(self.current):
                    letter = self.current[c]
                    border = FILLED_BORDER
                    start = self.pops.get(c)
                    if start is not None:
                        t = (now - start) / POP_DUR
                        if t < 1:
                            sx = sy = 1 + 0.12 * math.sin(math.pi * t)
                        else:
                            del self.pops[c]

                # tiles grow in one by one when a new game starts
                ti = (now - self.intro_start - (r * WORD_LEN + c) * INTRO_STAGGER) / INTRO_DUR
                if ti < 1:
                    s = ease_out_back(ti) if ti > 0 else 0.0
                    if s < 0.03:
                        continue
                    sx *= s
                    sy *= s

                self.draw_tile(self.screen, cx, cy, TILE, letter, fill, border, sx, sy)

    def draw_backspace_icon(self, rect, color):
        cx, cy = rect.center
        w, h = 26, 18
        left, top = cx - w // 2, cy - h // 2
        pts = [(left, cy), (left + 8, top), (left + w, top), (left + w, top + h), (left + 8, top + h)]
        pygame.draw.polygon(self.screen, color, pts, 2)
        xc = left + 16
        pygame.draw.line(self.screen, color, (xc - 4, cy - 4), (xc + 4, cy + 4), 2)
        pygame.draw.line(self.screen, color, (xc - 4, cy + 4), (xc + 4, cy - 4), 2)

    def draw_keyboard(self):
        now = pygame.time.get_ticks()
        mouse = pygame.mouse.get_pos()
        for label, rect in self.keys:
            color = tuple(int(v) for v in self.key_colors[label])
            if rect.collidepoint(mouse) and not self.modal_open and not self.revealing:
                color = lighten(color, 18)

            r = rect
            pressed = self.key_press.get(label)
            if pressed is not None:
                t = (now - pressed) / KEY_PRESS_DUR
                if t < 1:
                    s = 1 - 0.08 * math.sin(math.pi * t)
                    r = rect.inflate(int(rect.w * (s - 1)), int(rect.h * (s - 1)))
                else:
                    del self.key_press[label]

            pygame.draw.rect(self.screen, darken(color, 35), r.move(0, 2), border_radius=6)
            pygame.draw.rect(self.screen, color, r, border_radius=6)

            if label == "BACK":
                self.draw_backspace_icon(r, TEXT)
            else:
                font = "key_small" if len(label) > 1 else "key"
                self.draw_text(self.screen, label.upper(), font, TEXT, r.center)

    def draw_toast(self):
        if not self.toast_text:
            return
        elapsed = pygame.time.get_ticks() - self.toast_start
        if elapsed > TOAST_DUR:
            self.toast_text = None
            return

        alpha = 255
        if elapsed > TOAST_DUR - 300:
            alpha = int(255 * (TOAST_DUR - elapsed) / 300)
        drop = (1 - ease_out_back(elapsed / 220)) * -12

        text = self.fonts["toast"].render(self.toast_text, True, TOAST_TEXT)
        box = text.get_rect().inflate(34, 22)
        surf = pygame.Surface(box.size, pygame.SRCALPHA)
        pygame.draw.rect(surf, TOAST_BG, surf.get_rect(), border_radius=8)
        surf.blit(text, text.get_rect(center=surf.get_rect().center))
        surf.set_alpha(alpha)
        self.screen.blit(surf, surf.get_rect(center=(WIDTH // 2, GRID_TOP + 6 + int(drop))))

    def draw_footer_hint(self):
        if not self.game_over or self.modal is not None or self.pending_modal_at is not None:
            return
        pulse = 0.6 + 0.4 * math.sin(pygame.time.get_ticks() / 400)
        img = self.fonts["hint"].render("Press ENTER for a new word", True, SUBTEXT)
        img.set_alpha(int(255 * pulse))
        y = (GRID_BOTTOM + KEYBOARD_TOP) // 2
        self.screen.blit(img, img.get_rect(center=(WIDTH // 2, y)))

    def draw_stat_row(self, surf, y):
        s = self.stats
        win_pct = round(100 * s["wins"] / s["played"]) if s["played"] else 0
        items = [(s["played"], "Played"), (win_pct, "Win %"), (s["streak"], "Streak"), (s["best"], "Best")]
        col = surf.get_width() / len(items)
        for i, (num, label) in enumerate(items):
            cx = int(col * i + col / 2)
            self.draw_text(surf, str(num), "stat_num", TEXT, (cx, y + 16))
            self.draw_text(surf, label, "stat_label", SUBTEXT, (cx, y + 46))

    def draw_end_panel(self, p):
        w, h = p.get_size()
        now = pygame.time.get_ticks()

        title = "Good job!" if self.won else "Game over"
        self.draw_text(p, title, "modal_title", TEXT, (w // 2, 48))
        if self.won:
            n = len(self.guesses)
            sub = f"{WIN_WORDS[n - 1]}! You got it in {n}/{MAX_GUESSES}."
        else:
            sub = "The word was"
        self.draw_text(p, sub, "body", SUBTEXT, (w // 2, 90))

        size, gap = 50, 6
        x0 = (w - (WORD_LEN * size + (WORD_LEN - 1) * gap)) // 2
        color = GREEN if self.won else LOSS_RED
        for i, ch in enumerate(self.answer):
            t = (now - self.modal_opened_at - 160 - i * 70) / 320
            if t <= 0:
                continue
            s = ease_out_back(t)
            cx = x0 + i * (size + gap) + size // 2
            self.draw_tile(p, cx, 142, size, ch, color, None, s, s, font_key="mini")

        self.draw_stat_row(p, 186)
        self.draw_text(p, "Press ENTER to play again", "hint", SUBTEXT, (w // 2, h - 30))

    def draw_stats_panel(self, p):
        w, h = p.get_size()
        now = pygame.time.get_ticks()

        self.draw_text(p, "Statistics", "panel_title", TEXT, (w // 2, 34))
        self.draw_stat_row(p, 72)
        pygame.draw.line(p, PANEL_BORDER, (30, 150), (w - 30, 150), 1)
        self.draw_text(p, "GUESS DISTRIBUTION", "h2", SUBTEXT, (w // 2, 176))

        dist = self.stats["dist"]
        most = max(max(dist), 1)
        bar_x, bar_max, min_w = 54, w - 54 - 30, 32
        highlight = len(self.guesses) - 1 if self.game_over and self.won else None

        for i, count in enumerate(dist):
            y = 200 + i * 32
            self.draw_text(p, str(i + 1), "bar", TEXT, (34, y + 12))
            grow = ease_out_cubic((now - self.modal_opened_at - 120 - i * 50) / 500)
            full = min_w + (bar_max - min_w) * count / most
            bw = int(min_w + (full - min_w) * grow)
            color = GREEN if i == highlight else BAR_GRAY
            bar = pygame.Rect(bar_x, y, bw, 24)
            pygame.draw.rect(p, color, bar, border_radius=5)
            img = self.fonts["bar"].render(str(count), True, TEXT)
            p.blit(img, img.get_rect(midright=(bar.right - 9, bar.centery)))

    def draw_modal(self):
        if self.modal is None:
            return
        rect = self.modal_rect()
        shown = ease_out_cubic(self.modal_t)

        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, int(165 * ease_out_cubic(self.overlay_t))))
        self.screen.blit(overlay, (0, 0))

        # soft shadow: each layer is blended on top of the last
        area = rect.inflate(48, 48).move(0, 8)
        layer = pygame.Surface(area.size, pygame.SRCALPHA)
        for i in range(6, 0, -1):
            layer.fill((0, 0, 0, 0))
            box = pygame.Rect(0, 0, rect.w + i * 6, rect.h + i * 6)
            box.center = (area.w // 2, area.h // 2)
            pygame.draw.rect(layer, (0, 0, 0, int(22 * shown)), box, border_radius=14 + i * 3)
            self.screen.blit(layer, area)

        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, PANEL, panel.get_rect(), border_radius=14)
        pygame.draw.rect(panel, PANEL_BORDER, panel.get_rect(), 1, border_radius=14)

        if self.modal == "end":
            self.draw_end_panel(panel)
        else:
            self.draw_stats_panel(panel)
        for b in self.modal_buttons:
            self.draw_button(panel, b)

        panel.set_alpha(int(255 * shown))
        self.screen.blit(panel, rect)

    def draw_confetti(self):
        for p in self.confetti:
            c, s = math.cos(p["rot"]), math.sin(p["rot"])
            hw, hh = p["w"] / 2, p["h"] / 2 * abs(math.cos(p["rot"] * 0.7))
            pts = [(p["x"] + dx * c - dy * s, p["y"] + dx * s + dy * c)
                   for dx, dy in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))]
            pygame.draw.polygon(self.screen, p["c"], pts)

    def draw(self):
        self.screen.blit(self.background, (0, 0))
        self.draw_header()
        self.draw_grid()
        self.draw_keyboard()
        self.draw_footer_hint()
        self.draw_toast()
        self.draw_modal()
        self.draw_confetti()
        pygame.display.flip()

    # ------------------------------------------------------------ loop
    def run(self):
        running = True
        while running:
            dt = min(self.clock.tick(FPS) / 1000, 0.05)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif not self.handle_event(event):
                    running = False
            self.update(dt)
            self.draw()


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    bank = load_words(os.path.join(here, "words_bank.txt"))
    valid = load_words(os.path.join(here, "words_valid.txt"))

    if not bank:
        # an old single words.txt still works as the answer list
        bank = load_words(os.path.join(here, "words.txt"))
    if not bank:
        print("Couldn't find any 5-letter words in words_bank.txt.")
        print("Put words_bank.txt (answers) and words_valid.txt (allowed guesses) next to wordle.py.")
        sys.exit(1)
    if not valid:
        print("words_valid.txt not found, so only answer words will be accepted as guesses.")

    Wordle(bank, valid, os.path.join(here, "stats.json")).run()
    pygame.quit()


if __name__ == "__main__":
    main()
