"""Pomodoro Bar timer and review bars for Anki's reviewer."""

from __future__ import annotations

import json
import time
from typing import Any

from aqt import gui_hooks, mw
from aqt.qt import (
    QAction,
    QColor,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


DEFAULTS = {
    "pomodoro_minutes": 25,
    "reviews_per_full_bar": 100,
    "timer_color": "#e76f51",
    "height_px": 3,
    "settings_location": "toolbar",
    "review_menu_position": "none",
}

# These match the familiar Again / Hard / Good / Easy feedback colors.
REVIEW_COLORS = {
    "again": "#e53935",
    "hard": "#fb8c00",
    "good": "#43a047",
    "easy": "#1e88e5",
}
CONTROL_PLAYING_COLOR = "#2e7d32"
CONTROL_RESET_COLOR = "#444"
CONTROL_PAUSED_COLOR = CONTROL_RESET_COLOR

_saved_config = mw.addonManager.getConfig(__name__) or {}
_config = {**DEFAULTS, **_saved_config}
if "review_menu_enabled" in _saved_config:
    if not _saved_config["review_menu_enabled"]:
        _config["review_menu_position"] = "none"
    _config.pop("review_menu_enabled", None)
if _config.get("settings_location") not in ("toolbar", "tools"):
    _config["settings_location"] = DEFAULTS["settings_location"]
if _config.get("review_menu_position") not in (
    "none",
    "top-left",
    "top-right",
    "bottom-left",
    "bottom-right",
):
    _config["review_menu_position"] = DEFAULTS["review_menu_position"]
_timer_started: float | None = None
_elapsed_before_start = 0.0
_review_ratings: list[str] = []
_running = False
_session_active = False
_resume_when_review_returns = False
_tools_action: QAction | None = None


def _timer_color() -> str:
    color = QColor(str(_config.get("timer_color", DEFAULTS["timer_color"])))
    return color.name() if color.isValid() else DEFAULTS["timer_color"]


def _review_goal() -> int:
    return max(1, int(_config.get("reviews_per_full_bar", DEFAULTS["reviews_per_full_bar"])))


def _position_style(position: str) -> str:
    if position == "top-left":
        return "top: 12px; left: 12px;"
    if position == "bottom-left":
        return "bottom: 12px; left: 12px;"
    if position == "bottom-right":
        return "bottom: 12px; right: 12px;"
    return "top: 12px; right: 12px;"


def _menu_html() -> str:
    position = str(_config.get("review_menu_position", "none"))
    toggle_icon = "⏸" if _running else "▶"
    toggle_label = "Pause timer" if _running else "Start timer"
    toggle_color = CONTROL_PLAYING_COLOR if _running else CONTROL_PAUSED_COLOR
    return f"""
<div id="pomodoro-control-menu" style="position:fixed; z-index:2147483647; { _position_style(position) } display:flex; align-items:flex-start; gap:4px; pointer-events:auto;">
  <button type="button" data-pb-toggle title="{toggle_label}" aria-label="{toggle_label}"
          onclick="pycmd('pomodoro-bar:toggle')"
          style="box-sizing:border-box; display:flex; align-items:center; justify-content:center; vertical-align:top; margin:0 !important; width:34px; height:34px; line-height:1; padding:0; border:1px solid rgba(255,255,255,.35); border-radius:5px; background:{toggle_color}; color:#fff; font:16px sans-serif; cursor:pointer;">{toggle_icon}</button>
  <button type="button" title="Reset session" aria-label="Reset session" onclick="pycmd('pomodoro-bar:reset')"
          style="box-sizing:border-box; display:flex; align-items:center; justify-content:center; vertical-align:top; margin:0 !important; width:34px; height:34px; line-height:1; padding:0; border:1px solid rgba(255,255,255,.35); border-radius:5px; background:{CONTROL_RESET_COLOR}; color:#fff; font:18px sans-serif; cursor:pointer;">↻</button>
</div>
"""


def _bar_html() -> str:
    height = max(1, min(12, int(_config.get("height_px", DEFAULTS["height_px"]))))
    return f"""
<div id="pomodoro-review-bars" aria-hidden="true">
  <div class="pb-track"><div id="pb-timer" class="pb-fill"></div></div>
  <div class="pb-track"><div id="pb-reviews" class="pb-fill pb-review-fill"></div></div>
</div>
<style>
  #pomodoro-review-bars {{ position:fixed; z-index:2147483646; left:0; right:0; bottom:0; display:{'block' if _session_active else 'none'}; pointer-events:none; }}
  #pomodoro-review-bars .pb-track {{ width:100%; height:{height}px; background:transparent; overflow:hidden; }}
  #pomodoro-review-bars .pb-fill {{ width:0; height:100%; transition:width 250ms linear; }}
  #pb-timer {{ background:{_timer_color()}; }}
  #pb-reviews {{ display:flex; transition:none !important; }}
  #pb-reviews > span {{ flex:1 1 0; min-width:0; height:100%; }}
</style>
"""


def _inject_review_controls(web_content, context) -> None:
    # The reviewer webview is created once per review session. Keeping the
    # overlays in its body avoids destroying and recreating them with each card.
    if context is not getattr(mw, "reviewer", None):
        return
    web_content.body += _bar_html()
    if _config.get("review_menu_position") != "none":
        web_content.body += _menu_html()


def _elapsed() -> float:
    if _running and _timer_started is not None:
        return _elapsed_before_start + time.monotonic() - _timer_started
    return _elapsed_before_start


def _review_web() -> QWidget | None:
    reviewer = getattr(mw, "reviewer", None)
    return getattr(reviewer, "web", None)


def _update_bars() -> None:
    web = _review_web()
    if web is None:
        return

    duration = max(1, int(_config.get("pomodoro_minutes", DEFAULTS["pomodoro_minutes"]))) * 60
    goal = _review_goal()
    timer_pct = min(100, _elapsed() / duration * 100)
    review_pct = min(100, len(_review_ratings) / goal * 100)
    ratings_json = json.dumps(_review_ratings[:goal])
    colors_json = json.dumps(REVIEW_COLORS)
    session_active_json = json.dumps(_session_active)
    web.eval(f"""(() => {{
      const bars = document.getElementById('pomodoro-review-bars');
      const timer = document.getElementById('pb-timer');
      const reviews = document.getElementById('pb-reviews');
      if (bars) bars.style.display = {session_active_json} ? 'block' : 'none';
      if (timer) timer.style.width = '{timer_pct:.2f}%';
      if (reviews) {{
        reviews.style.width = '{review_pct:.2f}%';
        const ratings = {ratings_json};
        const colors = {colors_json};
        while (reviews.children.length > ratings.length) {{
          reviews.lastElementChild.remove();
        }}
        for (let index = reviews.children.length; index < ratings.length; index++) {{
          const rating = ratings[index];
          const segment = document.createElement('span');
          segment.style.backgroundColor = colors[rating] || colors.good;
          segment.title = rating[0].toUpperCase() + rating.slice(1);
          reviews.appendChild(segment);
        }}
      }}
    }})();""")


def _refresh_menu_state(web: QWidget | None) -> None:
    if web is None:
        return
    running = json.dumps(_running)
    web.eval(f"""(() => {{
      const menu = document.getElementById('pomodoro-control-menu');
      if (!menu) return;
      const toggle = menu.querySelector('[data-pb-toggle]');
      if (toggle) {{
        toggle.textContent = {running} ? '⏸' : '▶';
        toggle.title = {running} ? 'Pause timer' : 'Start timer';
        toggle.style.backgroundColor = {json.dumps(CONTROL_PLAYING_COLOR if _running else CONTROL_PAUSED_COLOR)};
        toggle.setAttribute('aria-label', toggle.title);
      }}
    }})();""")


def _replace_menu(web: QWidget | None, *, show: bool) -> None:
    if web is None:
        return
    fragment = _menu_html() if show else ""
    fragment_json = json.dumps(fragment)
    web.eval(f"""(() => {{
      const oldMenu = document.getElementById('pomodoro-control-menu');
      if (oldMenu) oldMenu.remove();
      const fragment = {fragment_json};
      if (!fragment) return;
      const container = document.createElement('div');
      container.innerHTML = fragment;
      const menu = container.firstElementChild;
      if (menu) document.body.appendChild(menu);
    }})();""")


def _sync_open_menu() -> None:
    if getattr(mw, "state", None) == "review":
        show_menu = _config.get("review_menu_position") != "none"
        _replace_menu(_review_web(), show=show_menu)


def _set_timer_running(running: bool) -> None:
    global _elapsed_before_start, _timer_started, _running, _session_active
    if running:
        _session_active = True
    if running and not _running:
        _timer_started = time.monotonic()
        _running = True
    elif not running and _running:
        if _timer_started is not None:
            _elapsed_before_start += time.monotonic() - _timer_started
        _timer_started = None
        _running = False
    _ensure_ticker()
    _update_bars()
    _refresh_menu_state(_review_web())


def _toggle_timer() -> None:
    global _resume_when_review_returns
    _resume_when_review_returns = False
    _set_timer_running(not _running)


def _reset_timer() -> None:
    global _elapsed_before_start, _timer_started, _session_active, _resume_when_review_returns
    _elapsed_before_start = 0.0
    _timer_started = time.monotonic() if _running else None
    _session_active = _running
    _resume_when_review_returns = False
    _review_ratings.clear()
    _update_bars()
    _refresh_menu_state(_review_web())


def _answer_rating(reviewer, card, ease: int) -> str:
    try:
        button_count = reviewer.mw.col.sched.answerButtons(card)
    except Exception:
        button_count = 4

    if button_count == 2:
        rating_by_ease = {1: "again", 2: "good"}
    elif button_count == 3:
        rating_by_ease = {1: "again", 2: "good", 3: "easy"}
    else:
        rating_by_ease = {1: "again", 2: "hard", 3: "good", 4: "easy"}
    return rating_by_ease.get(ease, "good")


def _on_answer(reviewer, card, ease: int) -> None:
    if _session_active:
        _review_ratings.append(_answer_rating(reviewer, card, ease))
    _update_bars()
    _refresh_menu_state(_review_web())


def _ensure_ticker() -> None:
    if not hasattr(mw, "_pomodoro_bar_ticker"):
        from aqt.qt import QTimer

        ticker = QTimer(mw)
        ticker.setInterval(1000)
        ticker.timeout.connect(_update_bars)
        mw._pomodoro_bar_ticker = ticker
    ticker = mw._pomodoro_bar_ticker
    if _running:
        ticker.start()
    else:
        ticker.stop()


class SettingsDialog(QDialog):
    def __init__(self) -> None:
        super().__init__(mw)
        self.setWindowTitle("Pomodoro Bar")
        outer = QVBoxLayout(self)
        form = QFormLayout()

        self.minutes = QSpinBox()
        self.minutes.setRange(1, 240)
        self.minutes.setValue(int(_config["pomodoro_minutes"]))
        self.review_goal = QSpinBox()
        self.review_goal.setRange(1, 1000)
        self.review_goal.setValue(int(_config["reviews_per_full_bar"]))
        self.height = QSpinBox()
        self.height.setRange(1, 12)
        self.height.setValue(int(_config["height_px"]))

        self.timer_color = _timer_color()
        self.color_button = QPushButton()
        self._refresh_color_button()
        self.color_button.clicked.connect(self._choose_color)

        self.settings_location = QComboBox()
        self.settings_location.addItem("Top toolbar", "toolbar")
        self.settings_location.addItem("Tools menu", "tools")
        self.settings_location.setCurrentIndex(max(0, self.settings_location.findData(_config.get("settings_location", "toolbar"))))

        self.menu_position = QComboBox()
        for label, value in (
            ("None", "none"),
            ("Top-left corner", "top-left"),
            ("Top-right corner", "top-right"),
            ("Bottom-left corner", "bottom-left"),
            ("Bottom-right corner", "bottom-right"),
        ):
            self.menu_position.addItem(label, value)
        self.menu_position.setCurrentIndex(max(0, self.menu_position.findData(_config.get("review_menu_position", "none"))))

        form.addRow("Pomodoro length (minutes)", self.minutes)
        form.addRow("Reviews for full counter bar", self.review_goal)
        form.addRow("Bar thickness (pixels)", self.height)
        form.addRow("Timer bar color", self.color_button)
        form.addRow("Settings entry location", self.settings_location)
        form.addRow("Timer controls location", self.menu_position)
        outer.addLayout(form)

        controls = QHBoxLayout()
        controls.setSpacing(4)
        controls.addStretch(1)
        self.toggle_button = QPushButton()
        self.toggle_button.setFixedSize(34, 34)
        self.toggle_button.clicked.connect(self._toggle)
        controls.addWidget(self.toggle_button)

        self.reset_button = QPushButton("↻")
        self.reset_button.setFixedSize(34, 34)
        self.reset_button.clicked.connect(self._reset)
        controls.addWidget(self.reset_button)
        controls.addStretch(1)
        outer.addLayout(controls)
        self._refresh_status()

        self.dialog_buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.dialog_buttons.accepted.connect(self._save)
        self.dialog_buttons.rejected.connect(self.reject)
        outer.addWidget(self.dialog_buttons)

    def _refresh_color_button(self) -> None:
        red = int(self.timer_color[1:3], 16)
        green = int(self.timer_color[3:5], 16)
        blue = int(self.timer_color[5:7], 16)
        text_color = "#000" if (red * 299 + green * 587 + blue * 114) / 1000 > 150 else "#fff"
        self.color_button.setText(self.timer_color.upper())
        self.color_button.setStyleSheet(f"background-color:{self.timer_color}; color:{text_color};")

    def _choose_color(self) -> None:
        selected = QColorDialog.getColor(QColor(self.timer_color), self, "Choose timer bar color")
        if selected.isValid():
            self.timer_color = selected.name()
            self._refresh_color_button()

    def _refresh_status(self) -> None:
        self.toggle_button.setText("⏸" if _running else "▶")
        toggle_label = "Pause timer" if _running else "Start timer"
        self.toggle_button.setToolTip(toggle_label)
        self.toggle_button.setAccessibleName(toggle_label)
        toggle_color = CONTROL_PLAYING_COLOR if _running else CONTROL_PAUSED_COLOR
        self.toggle_button.setStyleSheet(
            "QPushButton {"
            f"background-color:{toggle_color}; "
            "color:#fff; border:1px solid rgba(255,255,255,.35); "
            "border-radius:5px; padding:0; font-size:16px;"
            "}"
        )
        self.reset_button.setToolTip("Reset session")
        self.reset_button.setAccessibleName("Reset session")
        self.reset_button.setStyleSheet(
            "QPushButton {"
            f"background-color:{CONTROL_RESET_COLOR}; color:#fff; "
            "border:1px solid rgba(255,255,255,.35); border-radius:5px; "
            "padding:0; font-size:18px;"
            "}"
        )

    def _toggle(self) -> None:
        _toggle_timer()
        self._refresh_status()

    def _reset(self) -> None:
        _reset_timer()
        self._refresh_status()

    def _save(self) -> None:
        _config["pomodoro_minutes"] = self.minutes.value()
        _config["reviews_per_full_bar"] = self.review_goal.value()
        _config["height_px"] = self.height.value()
        _config["timer_color"] = self.timer_color
        _config["settings_location"] = self.settings_location.currentData()
        _config["review_menu_position"] = self.menu_position.currentData()
        _config.pop("review_menu_enabled", None)
        mw.addonManager.writeConfig(__name__, _config)
        self.accept()
        _sync_settings_entry()
        _sync_open_menu()
        _update_bars()
        web = _review_web()
        if web is not None:
            height = max(1, min(12, self.height.value()))
            web.eval(f"""(() => {{
              const timer = document.getElementById('pb-timer');
              if (timer) timer.style.backgroundColor = {json.dumps(_timer_color())};
              for (const track of document.querySelectorAll('#pomodoro-review-bars .pb-track')) {{
                track.style.height = '{height}px';
              }}
            }})();""")


def _show_settings() -> None:
    SettingsDialog().exec()


def _toolbar_links(links: list[str], toolbar) -> None:
    if _config.get("settings_location", "toolbar") == "toolbar":
        links.append(
            toolbar.create_link(
                "pomodoro-settings",
                "Pomodoro Bar",
                _show_settings,
                tip="Pomodoro Bar settings and controls",
            )
        )


def _install_tools_action() -> None:
    global _tools_action
    if _tools_action is not None or getattr(mw, "form", None) is None:
        return
    _tools_action = QAction("Pomodoro Bar", mw)
    _tools_action.triggered.connect(_show_settings)
    mw.form.menuTools.addAction(_tools_action)
    _tools_action.setVisible(_config.get("settings_location", "toolbar") == "tools")


def _sync_settings_entry() -> None:
    if _tools_action is not None:
        _tools_action.setVisible(_config.get("settings_location", "toolbar") == "tools")
    toolbar = getattr(mw, "toolbar", None)
    if toolbar is not None:
        toolbar.draw()


def _handle_menu_message(handled: tuple[bool, Any], message: str, _context: Any) -> tuple[bool, Any]:
    if handled[0]:
        return handled
    if message == "pomodoro-bar:toggle":
        _toggle_timer()
        return (True, None)
    if message == "pomodoro-bar:reset":
        _reset_timer()
        return (True, None)
    return handled


def _pause_for_review_exit() -> None:
    global _resume_when_review_returns
    if _running:
        _resume_when_review_returns = True
    _set_timer_running(False)


def _on_state_will_change(new_state: str, old_state: str) -> None:
    if old_state == "review" and new_state != "review":
        _pause_for_review_exit()


def _on_state_did_change(new_state: str, old_state: str) -> None:
    global _resume_when_review_returns
    if new_state == "review" and old_state != "review" and _resume_when_review_returns:
        _resume_when_review_returns = False
        _set_timer_running(True)


def _on_focus_did_change(new: QWidget | None, _old: QWidget | None) -> None:
    global _resume_when_review_returns
    if getattr(mw, "state", None) != "review":
        return

    window = new.window() if new is not None else None
    if window is mw:
        if _resume_when_review_returns:
            _resume_when_review_returns = False
            _set_timer_running(True)
    else:
        current = window
        while current is not None:
            if isinstance(current, SettingsDialog):
                return
            current = current.parentWidget()
        _pause_for_review_exit()


gui_hooks.webview_will_set_content.append(_inject_review_controls)
gui_hooks.reviewer_did_answer_card.append(_on_answer)
gui_hooks.reviewer_did_show_question.append(lambda _card: _update_bars())
gui_hooks.reviewer_did_show_answer.append(lambda _card: _update_bars())
gui_hooks.reviewer_will_end.append(_pause_for_review_exit)
gui_hooks.state_will_change.append(_on_state_will_change)
gui_hooks.state_did_change.append(_on_state_did_change)
gui_hooks.focus_did_change.append(_on_focus_did_change)
gui_hooks.top_toolbar_did_init_links.append(_toolbar_links)
gui_hooks.webview_did_receive_js_message.append(_handle_menu_message)
gui_hooks.main_window_did_init.append(_install_tools_action)
mw.addonManager.setConfigAction(__name__, _show_settings)
