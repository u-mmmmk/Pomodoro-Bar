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
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    Qt,
)


DEFAULTS = {
"pomodoro_minutes": 20,
    "reviews_per_full_bar": 100,
    "rest_minutes": 0,
    "auto_restart_after_rest": True,
    "large_notifications": False,
    "notify_review_goal": False,
    "timer_color": "#1e88e5",
    "height_px": 3,
    "settings_location": "toolbar",
    "review_menu_position": "none",
    "show_home_sessions": True,
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
CONTROL_COMPLETE_COLOR = "#fb8c00"
CONTROL_REST_COLOR = "#fb8c00"

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
_completed = False
_resting = False
_rest_elapsed_before_start = 0.0
_rest_started: float | None = None
_review_goal_notified = False
_resume_when_review_returns = False
_review_active = False
_tools_action: QAction | None = None
_notice_label: QLabel | None = None
_notice_timer = None


def _timer_color() -> str:
    color = QColor(str(_config.get("timer_color", DEFAULTS["timer_color"])))
    return color.name() if color.isValid() else DEFAULTS["timer_color"]


def _review_goal() -> int:
    return max(1, int(_config.get("reviews_per_full_bar", DEFAULTS["reviews_per_full_bar"])))


def _rest_duration_seconds() -> int:
    return max(0, int(_config.get("rest_minutes", DEFAULTS["rest_minutes"]))) * 60


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
    toggle_icon = _control_icon()
    toggle_label = _control_label()
    toggle_color = _control_color()
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
    height = max(1, int(_config.get("height_px", DEFAULTS["height_px"])))
    return f"""
<div id="pomodoro-review-bars" aria-hidden="true">
  <div class="pb-track"><div id="pb-timer" class="pb-fill"></div></div>
  <div class="pb-track"><div id="pb-reviews" class="pb-fill"></div></div>
</div>
<style>
  /* Keep card content stable where supported; the bars are sized separately. */
  html {{ scrollbar-gutter:stable; }}
  #pomodoro-review-bars {{ position:fixed; z-index:2147483646; left:0; width:0; bottom:0; display:{'block' if _session_active else 'none'}; pointer-events:none; }}
  #pomodoro-review-bars .pb-track {{ width:100%; height:{height}px; background:transparent; overflow:hidden; }}
  #pomodoro-review-bars .pb-fill {{ width:0; height:100%; transition:width 250ms linear; }}
  #pb-timer {{ background:{_timer_color()}; }}
  #pb-reviews {{ display:flex; transition:none !important; }}
  #pb-reviews > span {{ flex:1 1 0; min-width:0; height:100%; }}
</style>
<script>
(() => {{
  const bars = document.getElementById('pomodoro-review-bars');
  if (!bars) return;

  // Measure a scrollbar even on a short card. This hidden, fixed-size probe
  // does not change the page's scrolling or depend on scrollbar-gutter support.
  const probe = document.createElement('div');
  probe.style.cssText = 'position:fixed; left:0; top:0; width:100px; height:100px; box-sizing:content-box; margin:0; padding:0; border:0; overflow:scroll; visibility:hidden; pointer-events:none;';
  document.body.appendChild(probe);
  const scrollbarWidth = Math.max(0, probe.offsetWidth - probe.clientWidth);
  probe.remove();

  let previousViewportWidth = null;
  function updateWidth() {{
    // innerWidth includes the scrollbar, unlike the page's content width.
    // Ignore scrollbar-only resize events so front/back flips keep one width.
    const viewportWidth = window.innerWidth;
    if (viewportWidth === previousViewportWidth) return;
    previousViewportWidth = viewportWidth;
    bars.style.width = Math.max(0, viewportWidth - scrollbarWidth) + 'px';
  }}
  updateWidth();
  window.addEventListener('resize', updateWidth);
}})();
</script>
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


def _rest_elapsed() -> float:
    if _resting and _running and _rest_started is not None:
        return _rest_elapsed_before_start + time.monotonic() - _rest_started
    return _rest_elapsed_before_start


def _duration_seconds() -> int:
    return max(1, int(_config.get("pomodoro_minutes", DEFAULTS["pomodoro_minutes"]))) * 60


def _deck_browser_due_total(deck_browser: Any) -> int:
    """Return today's available New, Learn, and Review cards across all decks."""
    # Anki 23.10 stores the tree on _dueTree; newer releases expose it through
    # render data. Top-level counts already include their children, so summing
    # only those nodes avoids counting parent/child rows twice.
    tree = getattr(deck_browser, "_dueTree", None)
    if tree is None:
        render_data = getattr(deck_browser, "_render_data", None)
        tree = getattr(render_data, "tree", None)
    if tree is None:
        return 0

    return sum(
        int(node.new_count) + int(node.learn_count) + int(node.review_count)
        for node in tree.children
    )


def _remaining_sessions(cards_remaining: int) -> int:
    goal = _review_goal()
    return (cards_remaining + goal - 1) // goal


def _remaining_sessions_text(cards_remaining: int) -> str:
    sessions = _remaining_sessions(cards_remaining)
    return f"{cards_remaining} Cards Remaining - {sessions} Pomodoro Sessions"


def _append_home_sessions(deck_browser: Any, content: Any) -> None:
    if not _config.get("show_home_sessions", DEFAULTS["show_home_sessions"]):
        return
    cards_remaining = _deck_browser_due_total(deck_browser)
    summary = (
        '<div id="pomodoro-home-sessions" style="margin-bottom:8px;">'
        f"{_remaining_sessions_text(cards_remaining)}"
        "</div>"
    )
    content.stats = summary + content.stats


def _append_overview_sessions(overview: Any, content: Any) -> None:
    if not _config.get("show_home_sessions", DEFAULTS["show_home_sessions"]):
        return
    # Use the same selected-deck New / Learn / Review counts as Study Now.
    cards_remaining = sum(overview.mw.col.sched.counts())
    content.table += (
        '<div id="pomodoro-overview-sessions" style="margin-top:12px; text-align:center;">'
        f"{_remaining_sessions_text(cards_remaining)}"
        "</div>"
    )


def _control_color() -> str:
    if _completed:
        return CONTROL_COMPLETE_COLOR
    if _resting:
        return CONTROL_REST_COLOR
    return CONTROL_PLAYING_COLOR if _running else CONTROL_PAUSED_COLOR


def _control_icon() -> str:
    return "⏸" if _running else "▶"


def _control_label() -> str:
    if _resting:
        return "Pause rest" if _running else "Resume rest"
    return "Pause timer" if _running else "Start timer"


def _review_web() -> QWidget | None:
    reviewer = getattr(mw, "reviewer", None)
    return getattr(reviewer, "web", None)


def _update_bars() -> None:
    web = _review_web()
    if web is None:
        return

    duration = _duration_seconds()
    goal = _review_goal()
    if _resting:
        rest_duration = _rest_duration_seconds()
        timer_pct = max(0, 100 - _rest_elapsed() / rest_duration * 100) if rest_duration else 0
    else:
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
    icon = json.dumps(_control_icon())
    label = json.dumps(_control_label())
    color = json.dumps(_control_color())
    web.eval(f"""(() => {{
      const menu = document.getElementById('pomodoro-control-menu');
      if (!menu) return;
      const toggle = menu.querySelector('[data-pb-toggle]');
      if (toggle) {{
        toggle.textContent = {icon};
        toggle.title = {label};
        toggle.style.backgroundColor = {color};
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
    global _elapsed_before_start, _timer_started, _running, _session_active, _completed
    global _rest_elapsed_before_start, _rest_started, _review_goal_notified
    if running:
        if _completed:
            _elapsed_before_start = 0.0
            _timer_started = None
            _review_ratings.clear()
            _completed = False
            _review_goal_notified = False
        _session_active = True
    if running and not _running:
        if _resting:
            _rest_started = time.monotonic()
        else:
            _timer_started = time.monotonic()
        _running = True
    elif not running and _running:
        if _resting:
            if _rest_started is not None:
                _rest_elapsed_before_start += time.monotonic() - _rest_started
            _rest_started = None
        else:
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
    global _elapsed_before_start, _timer_started, _session_active, _resume_when_review_returns, _completed
    global _resting, _rest_elapsed_before_start, _rest_started, _review_goal_notified
    _elapsed_before_start = 0.0
    _timer_started = time.monotonic() if _running else None
    _session_active = _running
    _completed = False
    _resting = False
    _rest_elapsed_before_start = 0.0
    _rest_started = None
    _review_goal_notified = False
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
    global _review_goal_notified
    if _session_active:
        _review_ratings.append(_answer_rating(reviewer, card, ease))
        if (
            _config.get("notify_review_goal", DEFAULTS["notify_review_goal"])
            and not _review_goal_notified
            and len(_review_ratings) >= _review_goal()
        ):
            _review_goal_notified = True
            _show_notice("Review goal reached!")
    _update_bars()


def _ensure_ticker() -> None:
    if not hasattr(mw, "_pomodoro_bar_ticker"):
        from aqt.qt import QTimer

        ticker = QTimer(mw)
        ticker.setInterval(1000)
        ticker.timeout.connect(_on_tick)
        mw._pomodoro_bar_ticker = ticker
    ticker = mw._pomodoro_bar_ticker
    if _running:
        ticker.start()
    else:
        ticker.stop()


def _show_completion_notice() -> None:
    _show_notice("Pomodoro complete!")


def _show_notice(message: str) -> None:
    global _notice_label, _notice_timer
    if not _config.get("large_notifications", DEFAULTS["large_notifications"]):
        from aqt.utils import tooltip

        tooltip(message, period=3000)
        return

    from aqt.qt import QTimer

    if _notice_label is None:
        _notice_label = _DismissibleNotice(mw)
        _notice_label.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        _notice_label.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        _notice_label.setStyleSheet(
            "QLabel { background:#202124; color:white; border:1px solid #666; "
            "border-radius:8px; padding:14px 22px; font-size:20px; font-weight:600; }"
        )
        _notice_timer = QTimer(_notice_label)
        _notice_timer.setSingleShot(True)
        _notice_timer.timeout.connect(_notice_label.hide)
    _notice_label.setText(message)
    _notice_label.adjustSize()
    review_web = _review_web()
    if review_web is not None and getattr(mw, "state", None) == "review":
        center = review_web.mapToGlobal(review_web.rect().center())
    else:
        center = mw.frameGeometry().center()
    _notice_label.move(
        center.x() - _notice_label.width() // 2,
        center.y() - _notice_label.height() // 2,
    )
    _notice_label.show()
    _notice_label.raise_()
    _notice_timer.start(3000)


def _start_fresh_focus(*, running: bool) -> None:
    global _elapsed_before_start, _timer_started, _session_active, _completed
    global _resting, _rest_elapsed_before_start, _rest_started, _review_goal_notified
    _elapsed_before_start = 0.0
    _timer_started = None
    _resting = False
    _rest_elapsed_before_start = 0.0
    _rest_started = None
    _completed = False
    _review_goal_notified = False
    _review_ratings.clear()
    _session_active = running
    if running:
        _set_timer_running(True)
    else:
        _ensure_ticker()
        _update_bars()
        _refresh_menu_state(_review_web())


def _on_tick() -> None:
    global _completed, _resting, _running, _rest_elapsed_before_start, _rest_started
    global _resume_when_review_returns
    if _resting and _running and _rest_elapsed() >= _rest_duration_seconds():
        _running = False
        _resting = False
        _rest_elapsed_before_start = 0.0
        _rest_started = None
        auto_restart = bool(
            _config.get("auto_restart_after_rest", DEFAULTS["auto_restart_after_rest"])
        )
        restart_in_review = (
            auto_restart
            and _review_active
            and getattr(mw, "state", None) == "review"
        )
        _resume_when_review_returns = auto_restart and not restart_in_review
        _start_fresh_focus(running=restart_in_review)
        _refresh_open_settings_dialogs()
        _show_notice("Rest complete!")
    elif not _resting and _running and _elapsed() >= _duration_seconds():
        _set_timer_running(False)
        if _rest_duration_seconds() > 0:
            _resting = True
            _rest_elapsed_before_start = 0.0
            _rest_started = time.monotonic()
            _running = True
            _ensure_ticker()
            _refresh_menu_state(_review_web())
            _refresh_open_settings_dialogs()
        else:
            _completed = True
            _refresh_menu_state(_review_web())
            _refresh_open_settings_dialogs()
        _show_completion_notice()
    _update_bars()


def _refresh_open_settings_dialogs() -> None:
    for dialog in mw.findChildren(SettingsDialog):
        dialog._refresh_status()


class _DismissibleNotice(QLabel):
    def mousePressEvent(self, event) -> None:
        self.hide()
        event.accept()


class SettingsDialog(QDialog):
    def __init__(self) -> None:
        super().__init__(mw)
        self.setWindowTitle("Pomodoro Bar")
        outer = QVBoxLayout(self)
        form = QFormLayout()

        self.minutes = QSpinBox()
        self.minutes.setRange(1, 2_147_483_647)
        self.minutes.setValue(int(_config["pomodoro_minutes"]))
        self.review_goal = QSpinBox()
        self.review_goal.setRange(1, 2_147_483_647)
        self.review_goal.setValue(int(_config["reviews_per_full_bar"]))
        self.rest_minutes = QSpinBox()
        self.rest_minutes.setRange(0, 2_147_483_647)
        self.rest_minutes.setValue(int(_config["rest_minutes"]))
        self.auto_restart_after_rest = QCheckBox(
            "Pomodoro timer automatically restarts after rest"
        )
        self.auto_restart_after_rest.setChecked(
            bool(_config["auto_restart_after_rest"])
        )
        self.height = QSpinBox()
        self.height.setRange(1, 2_147_483_647)
        self.height.setValue(int(_config["height_px"]))
        self.large_notifications = QCheckBox("Use larger notifications")
        self.large_notifications.setChecked(bool(_config["large_notifications"]))
        self.notify_review_goal = QCheckBox(
            "Notify when the review goal is reached"
        )
        self.notify_review_goal.setChecked(bool(_config["notify_review_goal"]))
        self.show_home_sessions = QCheckBox(
            "Show number of Pomodoro sessions to complete cards"
        )
        self.show_home_sessions.setChecked(bool(_config["show_home_sessions"]))

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
        form.addRow("Reviews goal for pomodoro session", self.review_goal)
        form.addRow("Rest length (minutes)", self.rest_minutes)
        form.addRow("Bar thickness (pixels)", self.height)
        form.addRow("Timer bar color", self.color_button)
        form.addRow("Settings entry location", self.settings_location)
        form.addRow("Timer controls location", self.menu_position)
        form.addRow(self.auto_restart_after_rest)
        form.addRow(self.large_notifications)
        form.addRow(self.notify_review_goal)
        form.addRow(self.show_home_sessions)
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
        self.toggle_button.setText(_control_icon())
        toggle_label = _control_label()
        self.toggle_button.setToolTip(toggle_label)
        self.toggle_button.setAccessibleName(toggle_label)
        toggle_color = _control_color()
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
        _config["rest_minutes"] = self.rest_minutes.value()
        _config["auto_restart_after_rest"] = self.auto_restart_after_rest.isChecked()
        _config["height_px"] = self.height.value()
        _config["large_notifications"] = self.large_notifications.isChecked()
        _config["notify_review_goal"] = self.notify_review_goal.isChecked()
        _config["timer_color"] = self.timer_color
        _config["settings_location"] = self.settings_location.currentData()
        _config["review_menu_position"] = self.menu_position.currentData()
        _config["show_home_sessions"] = self.show_home_sessions.isChecked()
        mw.addonManager.writeConfig(__name__, _config)
        self.accept()
        _sync_settings_entry()
        if getattr(mw, "state", None) == "deckBrowser":
            deck_browser = getattr(mw, "deckBrowser", None)
            if deck_browser is not None:
                deck_browser.refresh()
        elif getattr(mw, "state", None) == "overview":
            overview = getattr(mw, "overview", None)
            if overview is not None:
                overview.refresh()
        _sync_open_menu()
        _update_bars()
        web = _review_web()
        if web is not None:
            height = max(1, self.height.value())
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
    if _resting:
        return
    if _running:
        _resume_when_review_returns = True
    _set_timer_running(False)


def _on_state_will_change(new_state: str, old_state: str) -> None:
    global _review_active
    if old_state == "review" and new_state != "review":
        _review_active = False
        _pause_for_review_exit()


def _on_state_did_change(new_state: str, old_state: str) -> None:
    global _resume_when_review_returns, _review_active
    if new_state == "review":
        _review_active = True
    if new_state == "review" and old_state != "review" and _resume_when_review_returns and not _resting:
        _resume_when_review_returns = False
        _set_timer_running(True)


def _on_focus_did_change(new: QWidget | None, _old: QWidget | None) -> None:
    global _resume_when_review_returns, _review_active
    if getattr(mw, "state", None) != "review":
        return

    window = new.window() if new is not None else None
    if window is mw:
        _review_active = True
        if _resume_when_review_returns and not _resting:
            _resume_when_review_returns = False
            _set_timer_running(True)
    else:
        current = window
        while current is not None:
            if isinstance(current, SettingsDialog):
                return
            current = current.parentWidget()
        _review_active = False
        _pause_for_review_exit()


gui_hooks.webview_will_set_content.append(_inject_review_controls)
gui_hooks.deck_browser_will_render_content.append(_append_home_sessions)
gui_hooks.overview_will_render_content.append(_append_overview_sessions)
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
