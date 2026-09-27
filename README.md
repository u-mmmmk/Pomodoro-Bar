# Pomodoro Bar

Pomodoro Bar is an Anki add-on for timing study sessions and tracking review
answers as you work through cards. This add on was vibe coded with GPT-6 Luna.

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
- At the focus limit, the add-on shows a brief completion notice. With rest
  enabled, the timer bar then shrinks through the rest period; without rest,
  the play button turns orange until you press Play or Reset. Pressing Play
  after completion starts a fresh countdown and clears the review bar.
- An optional rest period starts with a full timer bar and counts down to zero.
  Rest continues while you leave review. By default, when it ends, a new
  Pomodoro starts automatically if review is active; otherwise, it starts when
  you return. You can turn off automatic restart to leave the new Pomodoro
  ready at zero until you press Play. Setting rest to zero keeps the standard
  completed state.
- Optional larger, non-blocking notices apply to Pomodoro completion, rest
  completion, and the review-goal alert. The review-goal alert can be enabled
  separately and appears once when the count first reaches or passes the goal
  in each Pomodoro.
- Automatic pause when you leave or switch away from review. If the timer was
  running, it resumes when you return.
- Settings for timer duration, review goal, rest duration, timer bar color, bar thickness, and
  whether the settings shortcut appears in the top toolbar or Tools menu, plus
  options for notifications and the session count. Timer duration, review goal,
  and bar thickness have no add-on-defined upper limit.

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
- Rest: 0 minutes (disabled)
- Automatically restart after rest: on
- Larger notifications: off
- Review-goal notification: off
- Session count: shown
- Timer bar color: `#1e88e5`
- Bar thickness: 3 pixels
- Settings shortcut: top toolbar
- Review-screen controls: hidden
