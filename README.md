# Wordle

A polished, fully playable Wordle clone built with Python and Pygame. Guess the hidden five letter word in six tries, with smooth tile flips, a clickable keyboard, win and game over screens, and stats that stay saved between sessions.

## Features

- **Real Wordle scoring.** Repeated letters are handled exactly like the original. Greens get matched first, and a letter only turns yellow if there's still an unmatched copy of it left in the answer.
- **Smooth animations.** The game runs at 120 fps with eased motion throughout:
  - tiles pop when you type, flip one by one to reveal colours, and grow back in when a new game starts
  - the row shakes when a guess is rejected
  - the winning row does a little hop, followed by a burst of confetti
- **Clickable on-screen keyboard.** Keys fade to green, yellow or gray as you learn more about the word, and they press down when you click them.
- **End screens.** Win and you get a "Good job!" screen. Lose and you get a "Game over" screen that shows you the answer. Both have Play again and Stats buttons.
- **Statistics.** Tracks games played, win percentage, current streak and best streak, plus a guess distribution chart. Everything is saved to `stats.json`, so your stats carry over after you close the game.
- **Separate word lists.** One file for the words that can be the answer and another for every word you're allowed to guess.

## Requirements

- Python 3.8 or newer
- Pygame

```bash
pip install pygame
```

## Getting started

1. Put these files in the same folder:

   ```
   wordle.py
   words_bank.txt
   words_valid.txt
   ```

2. Run the game:

   ```bash
   python wordle.py
   ```

## Word lists

| File | What it's for |
| --- | --- |
| `words_bank.txt` | Words that can be picked as the answer. Keep this to common words people actually know. |
| `words_valid.txt` | Every word the player is allowed to guess. This one can be much bigger. |

Both files use one word per line. Lines that aren't exactly five letters get skipped automatically, as do blank lines and capitalisation, so messy lists are fine.

Every word in `words_bank.txt` is also accepted as a guess, even if you forgot to add it to `words_valid.txt`. That way the actual answer can never be rejected.

If `words_bank.txt` is missing, the game falls back to an older `words.txt` file when one exists. If `words_valid.txt` is missing, the game still runs, but you can only guess words from the bank.

## Controls

| Action | Keyboard | Mouse |
| --- | --- | --- |
| Type a letter | A to Z | Click a key |
| Delete a letter | Backspace | Click the ⌫ key |
| Submit a guess | Enter | Click ENTER |
| New game | Enter (after a game ends) | Restart button (top left) or Play again |
| View stats | | Stats button (top right) |
| Close a popup | Esc or Enter | Click outside it or the ✕ |
| Quit | Esc (when no popup is open) | Close the window |

## How scoring works

| Colour | Meaning |
| --- | --- |
| 🟩 Green | Right letter in the right spot |
| 🟨 Yellow | The letter is in the word, but in a different spot |
| ⬛ Gray | The letter isn't in the word (or every copy of it is already accounted for) |

For example, if the answer is `WORLD` and you guess `HELLO`, the second L turns green and the first L stays gray. `WORLD` only has one L, and the green one has already claimed it.

## Stats

Stats are stored in `stats.json` next to the game:

```json
{"played": 12, "wins": 10, "streak": 4, "best": 6, "dist": [0, 1, 3, 4, 2, 0]}
```

`dist` counts how many games you won in 1, 2, 3, 4, 5 and 6 guesses.

If you restart in the middle of a game after making at least one guess, that game counts as a loss and your streak resets. This stops anyone from skipping hard words to protect a streak. To reset all your stats, just delete `stats.json`.

## Customising

All the main settings are constants at the top of `wordle.py`:

- **Colours:** `GREEN`, `YELLOW`, `GRAY`, `LOSS_RED`, `BG_TOP`, `BG_BOTTOM` and the others
- **Animation speed:** `FLIP_DUR`, `FLIP_STAGGER`, `SHAKE_DUR`, `BOUNCE_DUR` and the other timings, all in milliseconds
- **Win messages:** `WIN_WORDS`, the message shown for winning in 1 through 6 guesses
- **Board size:** `WORD_LEN` and `MAX_GUESSES` (if you change `WORD_LEN`, your word lists need words of that length)

## Project structure

```
wordle.py          the game
words_bank.txt     possible answers
words_valid.txt    allowed guesses
stats.json         your saved stats (created automatically)
screenshots/       images for this README
```
