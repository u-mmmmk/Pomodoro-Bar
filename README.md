# Pomodoro Bar

Pomodoro Bar is an Anki add-on for timing study sessions and tracking review
answers as you work through cards. This add on was vibe coded with GPT-6 Luna

## Features

- A Pomodoro progress bar that fills over the configured timer duration.
- A review counter bar that fills toward a configurable card goal. Each answer
  is shown in its own segment: Again in red, Hard in orange, Good in green, and
  Easy in blue.
- Both bars keep a consistent width when a card's front or back introduces a
  scrollbar, reserving the scrollbar space even on short cards. They resize
  with the review window.
- An optional line on the Decks screen showing
  remaining New, Learn, and Review cards and the Pomodoro sessions needed to
  complete them, based on the configured review goal.
- The same option shows "X Cards Remaining - Y Pomodoro Sessions" on the
  selected deck's overview, below its card counts and Study Now button. This
  uses that deck's available New, Learn, and Review counts, including its subdecks.
- Compact play/pause and reset controls in the settings dialog, with optional
  controls in any corner of the review screen.
- The timer automatically pauses at its limit and shows a brief completion
  notice. The play button turns orange until you press Play or Reset; pressing
  Play after completion starts a fresh countdown and clears the review bar.
- Automatic pause when you leave or switch away from review. If the timer was
  running, it resumes when you return.
- Settings for timer duration, review goal, timer bar color, bar thickness, and
  whether the settings shortcut appears in the top toolbar or Tools menu, plus
  an option to show or hide the session count.

## Use

Open **Pomodoro Bar** from the configured top-toolbar or **Tools** menu location.
Use the square play/pause button to start or pause the timer, and the reset
button to clear the timer and review count. The review counter appears during an
active timer session and records answers made during that session.

To add controls to the review screen, choose a corner in **Timer controls
location**. Choose **None** to hide them. The review-screen controls use the
same play/pause and reset actions as the settings dialog.

## Install

Pomodoro Bar requires Anki 23.10 or newer.

1. Download and extract this repository.
2. In Anki, choose **Tools → Add-ons → View Files**.
3. Copy the repository contents into a new folder in the add-ons directory, so
   `__init__.py`, `config.json`, and `manifest.json` are directly inside that
   folder.
4. Restart Anki.

## Defaults

- Timer: 20 minutes
- Review goal: 100 cards
- Session count: shown
- Timer bar color: `#1e88e5`
- Bar thickness: 3 pixels
- Settings shortcut: top toolbar
- Review-screen controls: hidden
