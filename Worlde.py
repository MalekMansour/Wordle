"""
Wordle in Pygame.

Put a words.txt file next to this script (one word per line).
Only 5-letter alphabetic words are used; everything else is skipped.

Controls:
  Type letters, BACKSPACE to delete, ENTER to submit.
  Click the on-screen keyboard if you prefer.
  ENTER after a game ends starts a new word. ESC quits.
"""

import math
import os
import random
import sys

import pygame

# ---------------------------------------------------------------- settings
WIDTH, HEIGHT = 500, 780
FPS = 60
WORD_LEN = 5
MAX_GUESSES = 6

# colors
BG = (18, 18, 19)
TEXT = (248, 248, 248)
SUBTEXT = (150, 150, 155)
EMPTY_BORDER = (58, 58, 60)
FILLED_BORDER = (100, 100, 104)
GREEN = (83, 141, 78)
YELLOW = (181, 159, 59)
GRAY = (58, 58, 60)
KEY_BG = (129, 131, 132)
TOAST_BG = (248, 248, 248)
TOAST_TEXT = (18, 18, 19)
DIVIDER = (58, 58, 60)

CORRECT, PRESENT, ABSENT = 2, 1, 0
STATE_COLORS = {CORRECT: GREEN, PRESENT: YELLOW, ABSENT: GRAY}

# layout
TILE = 62
GAP = 6
GRID_TOP = 100
GRID_LEFT = (WIDTH - (WORD_LEN * TILE + (WORD_LEN - 1) * GAP)) // 2
GRID_BOTTOM = GRID_TOP + MAX_GUESSES * TILE + (MAX_GUESSES - 1) * GAP

KEY_W, KEY_H, KEY_GAP, WIDE_KEY_W = 40, 58, 6, 65
KEY_ROWS = ["qwertyuiop", "asdfghjkl", ["ENTER"] + list("zxcvbnm") + ["BACK"]]
KEYBOARD_TOP = HEIGHT - (3 * KEY_H + 2 * 8) - 24

# animation timings (ms)
FLIP_DUR = 420
FLIP_STAGGER = 260
POP_DUR = 110
SHAKE_DUR = 450
BOUNCE_DUR = 520
BOUNCE_STAGGER = 100
TOAST_DUR = 1500

WIN_WORDS = ["Genius", "Magnificent", "Impressive", "Splendid", "Great", "Phew"]


# ---------------------------------------------------------------- logic
def load_words(path):
    """Read 5-letter words from a text file. Returns a sorted, de-duplicated list."""
    words = set()
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                w = line.strip().lower()
                if len(w) == WORD_LEN and w.isascii() and w.isalpha():
                    words.add(w)
    except FileNotFoundError:
        return []
    return sorted(words)


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


# ---------------------------------------------------------------- game
class Wordle:
    def __init__(self, words):
        pygame.init()
        pygame.display.set_caption("Wordle")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()

        font_names = "helveticaneue,helvetica,arial,dejavusans,freesans"
        self.title_font = pygame.font.SysFont(font_names, 38, bold=True)
        self.tile_font = pygame.font.SysFont(font_names, 34, bold=True)
        self.key_font = pygame.font.SysFont(font_names, 20, bold=True)
        self.small_key_font = pygame.font.SysFont(font_names, 13, bold=True)
        self.toast_font = pygame.font.SysFont(font_names, 18, bold=True)
        self.info_font = pygame.font.SysFont(font_names, 15)

        self.words = words
        self.word_set = set(words)
        self.keys = self._build_keyboard()

        self.played = 0
        self.wins = 0
        self.streak = 0
        self.best_streak = 0

        self.new_game()

    # ------------------------------------------------------------ setup
    def _build_keyboard(self):
        keys = []
        for row_i, row in enumerate(KEY_ROWS):
            widths = [WIDE_KEY_W if len(k) > 1 else KEY_W for k in row]
            row_w = sum(widths) + KEY_GAP * (len(row) - 1)
            x = (WIDTH - row_w) // 2
            y = KEYBOARD_TOP + row_i * (KEY_H + 8)
            for label, w in zip(row, widths):
                keys.append((label, pygame.Rect(x, y, w, KEY_H)))
                x += w + KEY_GAP
        return keys

    def new_game(self):
        self.answer = random.choice(self.words)
        self.guesses = []          # list of (word, result)
        self.current = ""
        self.key_states = {}       # letter -> best state seen
        self.game_over = False
        self.won = False

        self.revealing = False
        self.reveal_start = 0
        self.pops = {}             # column -> start time
        self.shake_start = None
        self.bounce_start = None
        self.toast_text = None
        self.toast_start = 0
        self.toast_sticky = False

    # ------------------------------------------------------------ input
    def show_toast(self, text, sticky=False):
        self.toast_text = text
        self.toast_start = pygame.time.get_ticks()
        self.toast_sticky = sticky

    def handle_key(self, key):
        if self.revealing:
            return

        if self.game_over:
            if key == "ENTER":
                self.new_game()
            return

        now = pygame.time.get_ticks()
        if key == "ENTER":
            self.submit()
        elif key == "BACK":
            if self.current:
                self.current = self.current[:-1]
        elif len(key) == 1 and key.isalpha() and len(self.current) < WORD_LEN:
            self.current += key
            self.pops[len(self.current) - 1] = now

    def submit(self):
        now = pygame.time.get_ticks()
        if len(self.current) < WORD_LEN:
            self.show_toast("Not enough letters")
            self.shake_start = now
            return
        if self.current not in self.word_set:
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
            self.played += 1
            self.wins += 1
            self.streak += 1
            self.best_streak = max(self.best_streak, self.streak)
            self.bounce_start = now
            self.show_toast(WIN_WORDS[len(self.guesses) - 1])
        elif len(self.guesses) == MAX_GUESSES:
            self.game_over = True
            self.played += 1
            self.streak = 0
            self.show_toast(self.answer.upper(), sticky=True)

    # ------------------------------------------------------------ update
    def update(self):
        now = pygame.time.get_ticks()
        if self.revealing:
            total = FLIP_STAGGER * (WORD_LEN - 1) + FLIP_DUR
            if now - self.reveal_start >= total:
                self.finish_reveal(now)

    # ------------------------------------------------------------ drawing
    def draw_tile(self, cx, cy, letter, fill, border, scale_x=1.0, scale_y=1.0):
        w = max(1, int(TILE * scale_x))
        h = max(1, int(TILE * scale_y))
        rect = pygame.Rect(0, 0, w, h)
        rect.center = (cx, cy)

        if fill:
            pygame.draw.rect(self.screen, fill, rect)
        else:
            pygame.draw.rect(self.screen, BG, rect)
            pygame.draw.rect(self.screen, border, rect, 2)

        if letter:
            surf = self.tile_font.render(letter.upper(), True, TEXT)
            if scale_x != 1.0 or scale_y != 1.0:
                sw = max(1, int(surf.get_width() * scale_x))
                sh = max(1, int(surf.get_height() * scale_y))
                surf = pygame.transform.smoothscale(surf, (sw, sh))
            self.screen.blit(surf, surf.get_rect(center=(cx, cy + 1)))

    def draw_header(self):
        title = self.title_font.render("WORDLE", True, TEXT)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 40)))
        pygame.draw.line(self.screen, DIVIDER, (0, 75), (WIDTH, 75), 1)

        streak = self.info_font.render(f"Streak {self.streak}", True, SUBTEXT)
        self.screen.blit(streak, streak.get_rect(midright=(WIDTH - 16, 40)))

        pct = round(100 * self.wins / self.played) if self.played else 0
        wins = self.info_font.render(f"Win {pct}%", True, SUBTEXT)
        self.screen.blit(wins, wins.get_rect(midleft=(16, 40)))

    def draw_grid(self):
        now = pygame.time.get_ticks()
        current_row = len(self.guesses)

        for r in range(MAX_GUESSES):
            row_offset_x = 0
            if r == current_row and self.shake_start is not None:
                t = (now - self.shake_start) / SHAKE_DUR
                if t < 1:
                    row_offset_x = int(math.sin(t * math.pi * 8) * 10 * (1 - t))
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
                            sy = abs(math.cos(math.pi * p))
                            revealed = p >= 0.5

                    if revealed:
                        fill = STATE_COLORS[result[c]]
                    else:
                        border = FILLED_BORDER

                    # little victory hop on the winning row
                    if self.won and r == len(self.guesses) - 1 and self.bounce_start:
                        t = (now - self.bounce_start - c * BOUNCE_STAGGER) / BOUNCE_DUR
                        if 0 <= t < 1:
                            cy -= int(math.sin(math.pi * t) * 22)

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

                self.draw_tile(cx, cy, letter, fill, border, sx, sy)

    def draw_backspace_icon(self, rect, color):
        cx, cy = rect.center
        w, h = 26, 18
        left = cx - w // 2
        top = cy - h // 2
        points = [
            (left, cy),
            (left + 8, top),
            (left + w, top),
            (left + w, top + h),
            (left + 8, top + h),
        ]
        pygame.draw.polygon(self.screen, color, points, 2)
        xc = left + 16
        pygame.draw.line(self.screen, color, (xc - 4, cy - 4), (xc + 4, cy + 4), 2)
        pygame.draw.line(self.screen, color, (xc - 4, cy + 4), (xc + 4, cy - 4), 2)

    def draw_keyboard(self):
        mouse = pygame.mouse.get_pos()
        for label, rect in self.keys:
            state = self.key_states.get(label)
            color = STATE_COLORS[state] if state is not None else KEY_BG

            if rect.collidepoint(mouse) and not self.revealing:
                color = tuple(min(255, ch + 20) for ch in color)

            pygame.draw.rect(self.screen, color, rect, border_radius=5)

            if label == "BACK":
                self.draw_backspace_icon(rect, TEXT)
            else:
                font = self.small_key_font if len(label) > 1 else self.key_font
                surf = font.render(label.upper(), True, TEXT)
                self.screen.blit(surf, surf.get_rect(center=rect.center))

    def draw_toast(self):
        if not self.toast_text:
            return
        now = pygame.time.get_ticks()
        elapsed = now - self.toast_start

        alpha = 255
        if not self.toast_sticky:
            if elapsed > TOAST_DUR:
                self.toast_text = None
                return
            if elapsed > TOAST_DUR - 300:
                alpha = int(255 * (TOAST_DUR - elapsed) / 300)

        text = self.toast_font.render(self.toast_text, True, TOAST_TEXT)
        box = text.get_rect().inflate(32, 22)
        surf = pygame.Surface(box.size, pygame.SRCALPHA)
        pygame.draw.rect(surf, (*TOAST_BG, alpha), surf.get_rect(), border_radius=6)
        text.set_alpha(alpha)
        surf.blit(text, text.get_rect(center=surf.get_rect().center))
        self.screen.blit(surf, surf.get_rect(center=(WIDTH // 2, GRID_TOP - 2)))

    def draw_footer_hint(self):
        if not self.game_over or self.revealing:
            return
        hint = self.info_font.render("Press ENTER for a new word", True, SUBTEXT)
        y = (GRID_BOTTOM + KEYBOARD_TOP) // 2
        self.screen.blit(hint, hint.get_rect(center=(WIDTH // 2, y)))

    def draw(self):
        self.screen.fill(BG)
        self.draw_header()
        self.draw_grid()
        self.draw_keyboard()
        self.draw_footer_hint()
        self.draw_toast()
        pygame.display.flip()

    # ------------------------------------------------------------ loop
    def run(self):
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return
                    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        self.handle_key("ENTER")
                    elif event.key == pygame.K_BACKSPACE:
                        self.handle_key("BACK")
                    elif event.unicode and event.unicode.isascii() and event.unicode.isalpha():
                        self.handle_key(event.unicode.lower())
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    for label, rect in self.keys:
                        if rect.collidepoint(event.pos):
                            self.handle_key(label)
                            break

            self.update()
            self.draw()
            self.clock.tick(FPS)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "words.txt")
    words = load_words(path)
    if not words:
        print(f"Couldn't find any 5-letter words in {path}")
        print("Add a words.txt next to wordle.py with one word per line.")
        sys.exit(1)

    Wordle(words).run()
    pygame.quit()


if __name__ == "__main__":
    main()
