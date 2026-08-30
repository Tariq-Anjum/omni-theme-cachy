#!/usr/bin/env python3
"""Omni Theme Settings GUI for CachyOS KDE Plasma.

A native Qt settings application that provides:
  - Live wallpaper-aware color extraction and theming (core engine)
  - One-click theme application with the omni activation pipeline
  - Per-role palette customization saved as real theme directories
  - Wallpaper watcher for automatic re-theming

Runs on the omni-theme-cachy engine directly (``core.engine``): themes
created here live in the engine's themes root, so the ``omni`` CLI sees
them too. Requires the engine's Python environment (PyQt5).

Usage:
  gui/omni-settings-gui            # launcher (picks the engine venv)
  .venv/bin/python gui/omni-settings-gui.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

# ---------- Qt imports ----------
try:
    from PyQt5.QtCore import (
        QCoreApplication,
        QFileSystemWatcher,
        Qt,
        QThread,
        QTimer,
        pyqtSignal,
    )
    from PyQt5.QtGui import QColor, QDragEnterEvent, QDropEvent, QFont, QPainter, QPixmap
    from PyQt5.QtWidgets import (
        QApplication,
        QCheckBox,
        QColorDialog,
        QComboBox,
        QFileDialog,
        QFormLayout,
        QFrame,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QScrollArea,
        QSpinBox,
        QTabWidget,
        QVBoxLayout,
        QWidget,
    )
except ImportError:
    print(
        "ERROR: PyQt5 is required. Run via the engine venv, e.g.:\n"
        "  ~/.local/share/omni-theme-cachy/.venv/bin/python gui/omni-settings-gui.py",
        file=sys.stderr,
    )
    sys.exit(1)

# ==========================================================================
# Engine wiring — import core.* from the omni installation
# ==========================================================================

SCRIPT_DIR = Path(__file__).resolve().parent
OMNI_INSTALL = Path.home() / ".local" / "share" / "omni-theme-cachy"
GUI_STATE_FILE = Path.home() / ".config" / "omni-theme-settings" / "gui-state.json"
PLASMA_WALLPAPER_CONFIG = Path.home() / ".config" / "plasma-org.kde.plasma.desktop-appletsrc"


def resolve_omni_root() -> Optional[Path]:
    """Find the omni-theme-cachy root that holds ``core/`` and ``themes/``.

    Order: the checkout this script lives in (gui/ sits inside the repo),
    the managed install, then the current working directory.
    """
    for candidate in (SCRIPT_DIR.parent, OMNI_INSTALL, Path.cwd()):
        if (candidate / "core" / "engine.py").is_file():
            return candidate
    return None


OMNI_ROOT = resolve_omni_root()
if OMNI_ROOT is not None:
    sys.path.insert(0, str(OMNI_ROOT))
    try:
        from core.engine import ThemeEngine
        from core.theme_factory import create_theme_dir
        from core.theme_loader import discover_themes, load_theme
        from core.wallpaper_extractor import WallpaperColorExtractor
    except ImportError:
        OMNI_ROOT = None

if OMNI_ROOT is None:
    print(
        "ERROR: omni-theme-cachy engine not found. Run this script from the "
        "repo (gui/ inside the checkout) or install it to ~/.local/share/omni-theme-cachy.",
        file=sys.stderr,
    )
    sys.exit(1)

THEMES_ROOT = OMNI_ROOT / "themes"
TEMPLATES_ROOT = OMNI_ROOT / "templates"


# ==========================================================================
# KDE integration helpers
# ==========================================================================


class KDEIntegration:
    """Small, honest helpers for talking to the running Plasma session."""

    @staticmethod
    def get_current_wallpaper() -> Optional[str]:
        """Read the active Plasma wallpaper path from the appletsrc."""
        if not PLASMA_WALLPAPER_CONFIG.is_file():
            return None
        try:
            candidates: list[str] = []
            for line in PLASMA_WALLPAPER_CONFIG.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines():
                stripped = line.strip()
                if not stripped.startswith("Image="):
                    continue
                raw = stripped.split("=", 1)[1].strip()
                if raw.startswith("file://"):
                    path = unquote(urlparse(raw).path)
                else:
                    path = raw
                if path and Path(path).is_file():
                    candidates.append(path)
            # The last entry wins: plasmashell appends the active
            # containment's wallpaper last.
            return candidates[-1] if candidates else None
        except OSError:
            return None

    @staticmethod
    def reload_plasma():
        """Ask plasmashell/KWin to reconfigure (best effort, qdbus*)."""
        bus = shutil.which("qdbus6") or shutil.which("qdbus")
        if not bus:
            return
        for service, path, call in (
            ("org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell.reconfigure"),
            ("org.kde.KWin", "/KWin", "org.kde.KWin.reconfigure"),
        ):
            try:
                subprocess.run([bus, service, path, call], capture_output=True, timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                continue

    @staticmethod
    def notify(title: str, message: str):
        """Send a desktop notification (best effort)."""
        try:
            subprocess.run(
                ["notify-send", "-i", "preferences-desktop-theme", title, message],
                capture_output=True, timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass


# ==========================================================================
# Engine bridge
# ==========================================================================


class OmniBridge:
    """Typed facade over :class:`core.engine.ThemeEngine` for the GUI."""

    def __init__(self) -> None:
        from adapters import build_default_registry

        self.engine = ThemeEngine(
            themes_root=THEMES_ROOT,
            templates_root=TEMPLATES_ROOT,
            adapters=build_default_registry(),
        )

    def list_themes(self) -> list[dict]:
        themes = []
        for theme_dir in discover_themes(THEMES_ROOT):
            try:
                theme = load_theme(theme_dir)
                themes.append({
                    "id": theme.meta.id,
                    "name": theme.meta.name,
                    "mode": theme.meta.mode,
                    "path": str(theme_dir),
                })
            except Exception:  # noqa: BLE001 — a broken theme must not hide the rest
                themes.append({
                    "id": theme_dir.name, "name": theme_dir.name,
                    "mode": "?", "path": str(theme_dir),
                })
        return themes

    def apply_theme(self, theme_id: str, *, force: bool = False) -> dict:
        try:
            outcome = self.engine.apply(theme_id, force=force)
        except Exception as exc:  # noqa: BLE001 — surfaced in the status bar
            return {"ok": False, "status": "ERROR", "error": str(exc), "theme": theme_id}
        return {
            "ok": outcome.ok,
            "status": outcome.status,
            "theme": outcome.theme_id or theme_id,
            "generation": outcome.generation,
            "warnings": list(outcome.warnings),
            "errors": list(outcome.errors),
        }

    def rollback(self) -> dict:
        try:
            outcome = self.engine.rollback()
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "status": "ERROR", "error": str(exc)}
        return {"ok": outcome.ok, "status": outcome.status,
                "errors": list(outcome.errors), "warnings": list(outcome.warnings)}

    def get_current_status(self) -> dict:
        try:
            return self.engine.status().to_dict()
        except Exception:  # noqa: BLE001
            return {"state_exists": False}

    def create_theme_from_colors(
        self, name: str, colors: dict[str, str], *, mode: str = "dark",
        wallpaper: Optional[str] = None, force: bool = False,
    ) -> str:
        """Persist a palette as a theme directory in the engine's root."""
        theme_dir = create_theme_dir(
            THEMES_ROOT, name=name, colors=colors, mode=mode,
            wallpaper=wallpaper, force=force,
        )
        return theme_dir.name


# ==========================================================================
# Background workers
# ==========================================================================


class WallpaperWatcher(QThread):
    """Poll the Plasma wallpaper config and emit changes."""

    wallpaper_changed = pyqtSignal(str)

    def __init__(self, interval_seconds: int = 2, parent=None):
        super().__init__(parent)
        self._interval = max(1, int(interval_seconds)) * 1000
        self._running = True
        self._last_wallpaper: Optional[str] = None
        self._watcher = QFileSystemWatcher()
        if PLASMA_WALLPAPER_CONFIG.is_file():
            self._watcher.addPath(str(PLASMA_WALLPAPER_CONFIG))
            self._watcher.fileChanged.connect(self._on_config_changed)

    def _on_config_changed(self, _path: str):
        QTimer.singleShot(250, self._check)  # let plasmashell finish writing

    def _check(self):
        wp = KDEIntegration.get_current_wallpaper()
        if wp and wp != self._last_wallpaper:
            self._last_wallpaper = wp
            self.wallpaper_changed.emit(wp)

    def run(self):
        while self._running:
            self.msleep(self._interval)
            self._check()

    def stop(self):
        self._running = False
        self.wait(3000)


class ColorExtractionWorker(QThread):
    """Extract a palette from a wallpaper off the UI thread."""

    extracted = pyqtSignal(dict)

    def __init__(self, image_path: str, n_colors: int, sample_size: int, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.n_colors = n_colors
        self.sample_size = sample_size

    def run(self):
        try:
            colors = WallpaperColorExtractor(
                n_colors=self.n_colors, sample_size=self.sample_size
            ).extract(self.image_path)
            self.extracted.emit(colors)
        except Exception as exc:  # noqa: BLE001 — reported to the user
            self.extracted.emit({"__error__": str(exc)})


# ==========================================================================
# Widgets
# ==========================================================================


class ColorSwatch(QWidget):
    """Clickable color swatch showing one role."""

    color_changed = pyqtSignal(str, str)

    def __init__(self, role: str, hex_color: str, parent=None):
        super().__init__(parent)
        self.role = role
        self._color = hex_color
        self.setFixedSize(36, 36)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"{role}: {hex_color}  (click to change)")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(self._color))
        painter.setPen(QColor(255, 255, 255, 40))
        painter.drawRoundedRect(2, 2, 32, 32, 6, 6)
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            color = QColorDialog.getColor(
                QColor(self._color), self, f"Choose color for {self.role}"
            )
            if color.isValid():
                self.set_color(color.name())
                self.color_changed.emit(self.role, self._color)

    def set_color(self, hex_color: str):
        self._color = hex_color
        self.setToolTip(f"{self.role}: {self._color}  (click to change)")
        self.update()


class PaletteEditor(QWidget):
    """Grid of role swatches grouped by category."""

    colors_changed = pyqtSignal(dict)

    CATEGORIES = {
        "Surfaces": [
            "background", "darker_background", "dark_background", "lighter_background",
        ],
        "Text": [
            "foreground", "bright_foreground", "light_foreground",
            "dark_foreground", "muted",
        ],
        "Interaction": ["accent", "accent_secondary", "selection"],
        "Status": ["success", "warning", "error", "info"],
        "Terminal Base": ["red", "green", "yellow", "blue", "magenta", "cyan"],
        "Terminal Bright": [
            "bright_red", "bright_green", "bright_yellow",
            "bright_blue", "bright_magenta", "bright_cyan",
        ],
        "ANSI Ramp": [f"color{i}" for i in range(16)],
    }

    def __init__(self, colors: dict[str, str], parent=None):
        super().__init__(parent)
        self._colors: dict[str, str] = {}
        self._swatches: dict[str, ColorSwatch] = {}
        self._role_labels: dict[str, QLabel] = {}
        self._build_ui()
        self.set_colors(colors)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setSpacing(12)

        for category, roles in self.CATEGORIES.items():
            group = QGroupBox(category)
            grid = QGridLayout(group)
            grid.setSpacing(6)
            for col, role in enumerate(roles):
                swatch = ColorSwatch(role, "#808080")
                swatch.color_changed.connect(self._on_color_changed)
                self._swatches[role] = swatch
                label = QLabel(role)
                label.setStyleSheet("font-size: 10px;")
                label.setWordWrap(True)
                label.setMaximumWidth(104)
                self._role_labels[role] = label
                grid.addWidget(swatch, 0, col)
                grid.addWidget(label, 1, col)
            inner_layout.addWidget(group)

        inner_layout.addStretch()
        scroll.setWidget(inner)
        layout.addWidget(scroll)

    def _on_color_changed(self, role: str, new_hex: str):
        self._colors[role] = new_hex
        self._refresh_role_label(role)
        self.colors_changed.emit(dict(self._colors))

    def _refresh_role_label(self, role: str):
        label = self._role_labels.get(role)
        if label is not None:
            label.setText(role)
            label.setStyleSheet(f"font-size: 10px; color: {self._colors.get(role, '#888')};")

    def get_colors(self) -> dict[str, str]:
        return dict(self._colors)

    def set_colors(self, colors: dict[str, str]):
        self._colors = dict(colors)
        for role, swatch in self._swatches.items():
            swatch.set_color(self._colors.get(role, "#808080"))
            self._refresh_role_label(role)


class WallpaperDropZone(QWidget):
    """Drag-and-drop / click-to-browse wallpaper selector."""

    wallpaper_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.wallpaper_path: Optional[str] = None
        self._pixmap: Optional[QPixmap] = None
        self.setAcceptDrops(True)
        self.setMinimumHeight(170)
        self.setMaximumHeight(240)
        self.setCursor(Qt.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        self._label = QLabel("Drag && drop a wallpaper here\nor click to browse")
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setStyleSheet("color: #888; font-size: 14px; padding: 20px;")
        layout.addWidget(self._label)
        self._path_label = QLabel("")
        self._path_label.setAlignment(Qt.AlignCenter)
        self._path_label.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(self._path_label)

    def set_wallpaper(self, path: str, *, emit: bool = True):
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return False
        self.wallpaper_path = path
        self._pixmap = pixmap
        self._label.setPixmap(
            pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
        self._label.setStyleSheet("")
        self._path_label.setText(f"{Path(path).name}  ·  {path}")
        if emit:
            self.wallpaper_selected.emit(path)
        return True

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            path, _ = QFileDialog.getOpenFileName(
                self, "Select Wallpaper", "",
                "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tiff);;All Files (*)",
            )
            if path:
                self.set_wallpaper(path)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path and Path(path).is_file():
                self.set_wallpaper(path)
                break

    def resizeEvent(self, event):
        if self._pixmap is not None:
            self._label.setPixmap(
                self._pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        super().resizeEvent(event)


class ExtractedPalettePreview(QWidget):
    """Horizontal bar preview of the key palette roles."""

    KEY_ROLES = (
        "darker_background", "background", "lighter_background", "muted",
        "accent", "accent_secondary", "foreground", "bright_foreground",
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self._colors: list[str] = []
        self.setMinimumHeight(46)
        self.setMaximumHeight(64)

    def set_colors(self, colors: dict[str, str]):
        self._colors = [colors.get(role, "#303030") for role in self.KEY_ROLES]
        self.update()

    def paintEvent(self, event):
        if not self._colors:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        bar_w = self.width() / len(self._colors)
        for i, color in enumerate(self._colors):
            painter.setBrush(QColor(color))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(
                int(i * bar_w) + 1, 5, int(bar_w) - 2, self.height() - 10, 4, 4
            )
        painter.end()


# ==========================================================================
# Main window
# ==========================================================================


class OmniSettingsWindow(QMainWindow):
    """Main settings window for Omni Theme."""

    def __init__(self):
        super().__init__()
        self.bridge = OmniBridge()
        self.kde = KDEIntegration()
        self._current_colors: dict[str, str] = {}
        self._watcher: Optional[WallpaperWatcher] = None
        self._worker: Optional[ColorExtractionWorker] = None
        self._auto_apply_pending = False
        self._last_wallpaper_theme: Optional[str] = None

        self.setWindowTitle("Omni Theme Settings")
        self.setMinimumSize(860, 620)
        self._apply_app_style()
        self._build_ui()
        self._load_initial_state()

    # -- style ---------------------------------------------------------------

    def _apply_app_style(self):
        self.setStyleSheet("""
            QMainWindow, QDialog { background-color: #1a1d25; color: #d6dae2; }
            QGroupBox {
                border: 1px solid #2a2e39; border-radius: 6px;
                margin-top: 12px; padding-top: 14px; font-size: 13px; color: #d6dae2;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; }
            QTabWidget::pane {
                border: 1px solid #2a2e39; border-radius: 4px; background: #1a1d25;
            }
            QTabBar::tab {
                background: #14161c; color: #8a919d; padding: 8px 20px;
                border: 1px solid #2a2e39; border-bottom: none;
                border-top-left-radius: 6px; border-top-right-radius: 6px;
                margin-right: 2px; font-size: 13px;
            }
            QTabBar::tab:selected { background: #1a1d25; color: #4f9eea;
                border-bottom: 2px solid #4f9eea; }
            QPushButton {
                background-color: #2a2e39; color: #d6dae2;
                border: 1px solid #3a4150; border-radius: 4px;
                padding: 6px 16px; font-size: 13px; min-height: 26px;
            }
            QPushButton:hover { background-color: #3a4150; border-color: #4f9eea; }
            QPushButton:pressed { background-color: #4f9eea; color: #14161c; }
            QPushButton:disabled { background-color: #1e222b; color: #565d6d; }
            QComboBox {
                background-color: #2a2e39; color: #d6dae2;
                border: 1px solid #3a4150; border-radius: 4px;
                padding: 4px 10px; min-height: 24px;
            }
            QComboBox QAbstractItemView {
                background-color: #1e222b; color: #d6dae2;
                selection-background-color: #294664; border: 1px solid #3a4150;
            }
            QCheckBox { color: #d6dae2; spacing: 8px; }
            QCheckBox::indicator {
                width: 18px; height: 18px; border: 1px solid #3a4150;
                border-radius: 3px; background: #2a2e39;
            }
            QCheckBox::indicator:checked { background: #4f9eea; border-color: #4f9eea; }
            QLabel { color: #d6dae2; }
            QLineEdit {
                background-color: #2a2e39; color: #d6dae2;
                border: 1px solid #3a4150; border-radius: 4px; padding: 4px 8px;
            }
            QSpinBox {
                background-color: #2a2e39; color: #d6dae2;
                border: 1px solid #3a4150; border-radius: 4px; padding: 2px 6px;
            }
            QProgressBar {
                border: 1px solid #3a4150; border-radius: 4px; background: #2a2e39;
                text-align: center; color: #d6dae2; min-height: 18px;
            }
            QProgressBar::chunk { background: #4f9eea; border-radius: 3px; }
            QStatusBar {
                background: #14161c; color: #7d8593;
                border-top: 1px solid #2a2e39; font-size: 12px;
            }
            QScrollArea { border: none; }
        """)

    # -- UI construction -------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(16, 16, 16, 8)
        main_layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Omni Theme Settings")
        title.setFont(QFont("Sans", 17, QFont.Bold))
        title.setStyleSheet("color: #4f9eea;")
        header.addWidget(title)
        subtitle = QLabel("CachyOS KDE Plasma Theme Engine")
        subtitle.setStyleSheet("color: #7d8593; font-size: 13px; padding-left: 12px;")
        header.addWidget(subtitle)
        header.addStretch()
        engine_note = QLabel(f"engine: {OMNI_ROOT}")
        engine_note.setStyleSheet("color: #565d6d; font-size: 11px;")
        header.addWidget(engine_note)
        main_layout.addLayout(header)

        self._tabs = QTabWidget()
        main_layout.addWidget(self._tabs)
        self._build_quick_tab()
        self._build_wallpaper_tab()
        self._build_editor_tab()
        self._build_settings_tab()
        self.statusBar().showMessage("Ready")

    def _build_quick_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(12)

        selector_group = QGroupBox("Select Theme")
        selector_layout = QHBoxLayout(selector_group)
        self._theme_combo = QComboBox()
        self._theme_combo.setMinimumWidth(280)
        selector_layout.addWidget(self._theme_combo)
        self._apply_btn = QPushButton("Apply Theme")
        self._apply_btn.setStyleSheet(
            "QPushButton { background: #4f9eea; color: #14161c; font-weight: bold; }"
            "QPushButton:hover { background: #6ab4f0; }"
        )
        self._apply_btn.clicked.connect(self._on_apply_theme)
        selector_layout.addWidget(self._apply_btn)
        self._rollback_btn = QPushButton("Rollback")
        self._rollback_btn.clicked.connect(self._on_rollback)
        selector_layout.addWidget(self._rollback_btn)
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self._populate_themes)
        selector_layout.addWidget(self._refresh_btn)
        layout.addWidget(selector_group)
        self._populate_themes()

        status_group = QGroupBox("Current Status")
        status_layout = QVBoxLayout(status_group)
        self._status_label = QLabel("Loading…")
        self._status_label.setWordWrap(True)
        status_layout.addWidget(self._status_label)
        layout.addWidget(status_group)
        layout.addStretch()
        self._tabs.addTab(tab, "Quick Apply")

    def _build_wallpaper_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        auto_group = QGroupBox("Automatic Wallpaper Theming")
        auto_layout = QHBoxLayout(auto_group)
        self._auto_theme_check = QCheckBox(
            "Automatically match theme to wallpaper when it changes"
        )
        self._auto_theme_check.toggled.connect(self._on_auto_theme_toggled)
        auto_layout.addWidget(self._auto_theme_check)
        auto_layout.addStretch()
        layout.addWidget(auto_group)

        drop_group = QGroupBox("Extract Colors from Wallpaper")
        drop_layout = QVBoxLayout(drop_group)
        self._drop_zone = WallpaperDropZone()
        self._drop_zone.wallpaper_selected.connect(self._on_wallpaper_selected)
        drop_layout.addWidget(self._drop_zone)

        self._palette_preview = ExtractedPalettePreview()
        drop_layout.addWidget(self._palette_preview)

        buttons = QHBoxLayout()
        self._extract_btn = QPushButton("Extract Colors && Generate Theme")
        self._extract_btn.setStyleSheet(
            "QPushButton { background: #4f9eea; color: #14161c; font-weight: bold; }"
            "QPushButton:hover { background: #6ab4f0; }"
        )
        self._extract_btn.clicked.connect(self._on_extract_and_apply)
        buttons.addWidget(self._extract_btn)
        self._preview_btn = QPushButton("Preview Palette Only")
        self._preview_btn.clicked.connect(self._on_preview_extracted)
        buttons.addWidget(self._preview_btn)
        buttons.addStretch()
        drop_layout.addLayout(buttons)

        self._extract_progress = QProgressBar()
        self._extract_progress.setRange(0, 0)
        self._extract_progress.setVisible(False)
        drop_layout.addWidget(self._extract_progress)

        self._extract_status = QLabel("")
        self._extract_status.setWordWrap(True)
        self._extract_status.setStyleSheet("color: #7d8593; font-size: 12px;")
        drop_layout.addWidget(self._extract_status)
        layout.addWidget(drop_group)

        use_current = QHBoxLayout()
        self._use_current_btn = QPushButton("Use Current Desktop Wallpaper")
        self._use_current_btn.clicked.connect(self._on_use_current_wallpaper)
        use_current.addWidget(self._use_current_btn)
        use_current.addStretch()
        layout.addLayout(use_current)
        layout.addStretch()
        self._tabs.addTab(tab, "Wallpaper → Theme")

    def _build_editor_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Theme Name:"))
        self._theme_name_input = QLineEdit("My Custom Theme")
        self._theme_name_input.setMaximumWidth(260)
        name_row.addWidget(self._theme_name_input)
        name_row.addWidget(QLabel("Mode:"))
        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["dark", "light"])
        name_row.addWidget(self._mode_combo)
        name_row.addStretch()
        layout.addLayout(name_row)

        self._palette_editor = PaletteEditor(self._current_colors)
        self._palette_editor.colors_changed.connect(self._on_palette_colors_changed)
        layout.addWidget(self._palette_editor)

        save_row = QHBoxLayout()
        self._save_theme_btn = QPushButton("Save as Theme")
        self._save_theme_btn.setStyleSheet(
            "QPushButton { background: #4f9eea; color: #14161c; font-weight: bold; }"
            "QPushButton:hover { background: #6ab4f0; }"
        )
        self._save_theme_btn.clicked.connect(self._on_save_custom_theme)
        save_row.addWidget(self._save_theme_btn)
        self._save_apply_btn = QPushButton("Save && Apply")
        self._save_apply_btn.clicked.connect(self._on_save_and_apply)
        save_row.addWidget(self._save_apply_btn)
        self._reset_colors_btn = QPushButton("Reset to Default Palette")
        self._reset_colors_btn.clicked.connect(self._on_reset_colors)
        save_row.addWidget(self._reset_colors_btn)
        save_row.addStretch()
        layout.addLayout(save_row)
        self._tabs.addTab(tab, "Color Editor")

    def _build_settings_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        daemon_group = QGroupBox("Wallpaper Watcher Daemon")
        daemon_layout = QFormLayout(daemon_group)
        self._daemon_check = QCheckBox("Enable wallpaper change detection (in-app)")
        daemon_layout.addRow(self._daemon_check)
        self._daemon_interval = QSpinBox()
        self._daemon_interval.setRange(1, 30)
        self._daemon_interval.setValue(2)
        self._daemon_interval.setSuffix(" seconds")
        daemon_layout.addRow("Poll interval:", self._daemon_interval)
        self._daemon_interval.valueChanged.connect(self._on_interval_changed)
        self._auto_apply_check = QCheckBox("Auto-apply extracted theme on wallpaper change")
        self._auto_apply_check.setChecked(True)
        daemon_layout.addRow(self._auto_apply_check)
        layout.addWidget(daemon_group)

        extract_group = QGroupBox("Color Extraction Settings")
        extract_layout = QFormLayout(extract_group)
        self._n_colors_spin = QSpinBox()
        self._n_colors_spin.setRange(2, 16)
        self._n_colors_spin.setValue(8)
        extract_layout.addRow("Palette clusters (k-means):", self._n_colors_spin)
        self._sample_size_spin = QSpinBox()
        self._sample_size_spin.setRange(50, 500)
        self._sample_size_spin.setValue(200)
        self._sample_size_spin.setSingleStep(50)
        extract_layout.addRow("Sample resolution:", self._sample_size_spin)
        layout.addWidget(extract_group)

        adv_group = QGroupBox("Advanced")
        adv_layout = QVBoxLayout(adv_group)
        self._force_apply_check = QCheckBox("Force apply (overwrite user-modified targets)")
        adv_layout.addWidget(self._force_apply_check)
        self._reload_plasma_check = QCheckBox("Reconfigure plasmashell/KWin after apply")
        self._reload_plasma_check.setChecked(True)
        adv_layout.addWidget(self._reload_plasma_check)
        chrome_note = QLabel(
            "Chrome (panel opacity, window decoration, tooltips) follows the "
            "theme's [panel]/[kwin]/[tooltips] surfaces when present."
        )
        chrome_note.setWordWrap(True)
        chrome_note.setStyleSheet("color: #565d6d; font-size: 11px;")
        adv_layout.addWidget(chrome_note)
        layout.addWidget(adv_group)
        layout.addStretch()
        self._tabs.addTab(tab, "Settings")

    # -- state ----------------------------------------------------------------

    def _populate_themes(self):
        self._theme_combo.blockSignals(True)
        self._theme_combo.clear()
        themes = self.bridge.list_themes()
        for t in themes:
            self._theme_combo.addItem(f"{t['name']} ({t['mode']})", t["id"])
        if not themes:
            self._theme_combo.addItem("No themes found", None)
        self._theme_combo.blockSignals(False)
        self._apply_btn.setEnabled(bool(themes))

    def _load_initial_state(self):
        status = self.bridge.get_current_status()
        if status.get("state_exists"):
            consistent = bool(status.get("consistent"))
            ok = "#82a55b" if consistent else "#d9564f"
            text = (
                f"Active theme: <b>{status.get('current_theme') or '<none>'}</b>"
                f" &nbsp;·&nbsp; generation: {status.get('current_generation') or '-'}"
                f"<br>State: <span style='color:{ok};'>"
                f"{'consistent' if consistent else 'INCONSISTENT'}</span>"
                f" &nbsp;·&nbsp; managed targets: {status.get('managed_targets', 0)}"
            )
            details = status.get("details") or []
            if details:
                text += "<br><small>" + "; ".join(details) + "</small>"
            self._status_label.setText(text)
        else:
            self._status_label.setText("No theme currently active.")

        GUI_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        if GUI_STATE_FILE.is_file():
            try:
                state = json.loads(GUI_STATE_FILE.read_text())
                self._auto_theme_check.setChecked(bool(state.get("auto_theme", False)))
                self._daemon_check.setChecked(bool(state.get("daemon_enabled", False)))
                self._daemon_interval.setValue(int(state.get("daemon_interval", 2)))
                self._auto_apply_check.setChecked(bool(state.get("auto_apply", True)))
                self._n_colors_spin.setValue(int(state.get("n_colors", 8)))
                self._sample_size_spin.setValue(int(state.get("sample_size", 200)))
                self._force_apply_check.setChecked(bool(state.get("force_apply", False)))
                self._reload_plasma_check.setChecked(bool(state.get("reload_plasma", True)))
            except (OSError, ValueError, KeyError):
                pass
        if self._daemon_check.isChecked():
            self._start_watcher()

        current_wp = KDEIntegration.get_current_wallpaper()
        if current_wp:
            self._drop_zone.set_wallpaper(current_wp, emit=False)

        default_colors = WallpaperColorExtractor(n_colors=8).extract(
            THEMES_ROOT / "default" / "wallpapers" / "default.png"
        ) if (THEMES_ROOT / "default" / "wallpapers" / "default.png").is_file() else {}
        self._palette_editor.set_colors(default_colors)
        self._current_colors = default_colors
        self._palette_preview.set_colors(default_colors)

    def _save_gui_state(self):
        state = {
            "auto_theme": self._auto_theme_check.isChecked(),
            "daemon_enabled": self._daemon_check.isChecked(),
            "daemon_interval": self._daemon_interval.value(),
            "auto_apply": self._auto_apply_check.isChecked(),
            "n_colors": self._n_colors_spin.value(),
            "sample_size": self._sample_size_spin.value(),
            "force_apply": self._force_apply_check.isChecked(),
            "reload_plasma": self._reload_plasma_check.isChecked(),
        }
        try:
            GUI_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            GUI_STATE_FILE.write_text(json.dumps(state, indent=2))
        except OSError:
            pass

    # -- slots ----------------------------------------------------------------

    def _on_apply_theme(self):
        theme_id = self._theme_combo.currentData()
        if not theme_id:
            QMessageBox.warning(self, "No Theme", "No theme selected.")
            return
        self.statusBar().showMessage(f"Applying theme: {theme_id}…")
        QApplication.processEvents()
        outcome = self.bridge.apply_theme(theme_id, force=self._force_apply_check.isChecked())
        if outcome["ok"]:
            self.statusBar().showMessage(f"Theme applied: {theme_id} ({outcome['status']})")
            KDEIntegration.notify("Omni Theme", f"Applied theme: {theme_id}")
            if self._reload_plasma_check.isChecked():
                self.kde.reload_plasma()
        else:
            detail = "; ".join(outcome.get("errors", [])) or outcome.get("error", "unknown")
            self.statusBar().showMessage(f"Apply failed: {detail}", 8000)
        self._load_initial_state()

    def _on_rollback(self):
        self.statusBar().showMessage("Rolling back…")
        QApplication.processEvents()
        outcome = self.bridge.rollback()
        if outcome["ok"]:
            self.statusBar().showMessage(f"Rollback: {outcome['status']}")
        else:
            detail = "; ".join(outcome.get("errors", [])) or outcome.get("error", "unknown")
            self.statusBar().showMessage(f"Rollback failed: {detail}", 8000)
        if self._reload_plasma_check.isChecked():
            self.kde.reload_plasma()
        self._load_initial_state()

    def _on_wallpaper_selected(self, path: str):
        self.statusBar().showMessage(f"Wallpaper selected: {Path(path).name}")
        self._on_preview_extracted()

    def _selected_wallpaper(self) -> Optional[str]:
        return self._drop_zone.wallpaper_path

    def _on_extract_and_apply(self):
        wp = self._selected_wallpaper()
        if not wp:
            QMessageBox.information(
                self, "No Wallpaper",
                "Drop a wallpaper, browse for one, or use "
                "'Use Current Desktop Wallpaper' first."
            )
            return
        self._start_extraction(wp, auto=True)

    def _on_preview_extracted(self):
        wp = self._selected_wallpaper()
        if not wp:
            return
        self._start_extraction(wp, auto=False)

    def _on_use_current_wallpaper(self):
        wp = KDEIntegration.get_current_wallpaper()
        if wp and self._drop_zone.set_wallpaper(wp):
            self.statusBar().showMessage(f"Current wallpaper: {Path(wp).name}")
        else:
            self.statusBar().showMessage("Could not detect the current wallpaper", 6000)
            self._extract_status.setText(
                "Could not detect the current Plasma wallpaper.\n"
                "Drag && drop a wallpaper image instead."
            )

    def _start_extraction(self, image_path: str, *, auto: bool):
        if self._worker is not None and self._worker.isRunning():
            self.statusBar().showMessage("Extraction already running…")
            return
        self._auto_apply_pending = auto
        self._extract_progress.setVisible(True)
        self._extract_status.setText(f"Analyzing {Path(image_path).name} …")
        self._worker = ColorExtractionWorker(
            image_path,
            self._n_colors_spin.value(),
            self._sample_size_spin.value(),
            self,
        )
        self._worker.extracted.connect(self._on_extraction_finished)
        self._worker.start()

    def _on_extraction_finished(self, payload: dict):
        self._extract_progress.setVisible(False)
        error = payload.get("__error__")
        if error:
            self._extract_status.setText(f"Extraction failed: {error}")
            self.statusBar().showMessage("Extraction failed", 6000)
            return
        colors = payload
        image_path = self._worker.image_path if self._worker is not None else ""
        self._current_colors = colors
        self._palette_editor.set_colors(colors)
        self._palette_preview.set_colors(colors)
        if image_path and Path(image_path).is_file():
            self._drop_zone.set_wallpaper(image_path, emit=False)
        semantic = sum(1 for k in colors if not k.startswith("color"))
        self._extract_status.setText(
            f"Extracted {semantic} semantic roles + 16 ANSI terminal colors."
        )
        self.statusBar().showMessage("Color extraction complete")
        if self._auto_apply_pending:
            self._create_and_apply_wallpaper_theme(colors, image_path)

    def _create_and_apply_wallpaper_theme(
        self, colors: dict[str, str], image_path: str = ""
    ):
        stem = Path(image_path).stem if image_path else "wallpaper"
        name = f"Wallpaper {stem.replace('-', ' ').replace('_', ' ').title()}"
        try:
            theme_id = self.bridge.create_theme_from_colors(
                name, colors, mode=self._mode_combo.currentText(),
                wallpaper=image_path or None, force=True,  # deterministic: safe to regenerate
            )
        except Exception as exc:  # noqa: BLE001 — surfaced to the user
            self.statusBar().showMessage(f"Theme creation failed: {exc}", 10000)
            return
        self._last_wallpaper_theme = theme_id
        self.statusBar().showMessage(f"Created theme: {theme_id}, applying…")
        QApplication.processEvents()
        outcome = self.bridge.apply_theme(theme_id, force=self._force_apply_check.isChecked())
        # Refresh bookkeeping first so the final status message survives.
        self._populate_themes()
        self._load_initial_state()
        if outcome["ok"]:
            self.statusBar().showMessage(f"Wallpaper theme applied: {theme_id}", 15000)
            KDEIntegration.notify(
                "Omni Theme", f"Desktop matched to wallpaper: {Path(image_path).name}"
            )
            if self._reload_plasma_check.isChecked():
                self.kde.reload_plasma()
        else:
            detail = "; ".join(outcome.get("errors", [])) or outcome.get("error", "?")
            self.statusBar().showMessage(f"Apply failed: {detail}", 15000)
            QMessageBox.warning(
                self, "Apply Failed",
                f"The wallpaper theme {theme_id!r} was created but could not be "
                f"applied:\n\n{detail}",
            )

    def _on_auto_theme_toggled(self, checked: bool):
        if checked:
            self._daemon_check.setChecked(True)
            self._auto_apply_check.setChecked(True)
            self._start_watcher()
            self.statusBar().showMessage("Auto-theming enabled")
        else:
            self._stop_watcher()
            self.statusBar().showMessage("Auto-theming disabled")
        self._save_gui_state()

    def _on_palette_colors_changed(self, colors: dict[str, str]):
        self._current_colors = colors
        self._palette_preview.set_colors(colors)

    def _on_save_custom_theme(self):
        self._persist_custom_theme(apply=False)

    def _on_save_and_apply(self):
        self._persist_custom_theme(apply=True)

    def _persist_custom_theme(self, *, apply: bool):
        colors = self._palette_editor.get_colors()
        name = self._theme_name_input.text().strip() or "Custom Theme"
        mode = self._mode_combo.currentText()
        try:
            theme_id = self.bridge.create_theme_from_colors(
                name, colors, mode=mode, force=False
            )
        except Exception as exc:  # noqa: BLE001 — e.g. id already exists
            retry = QMessageBox.question(
                self, "Theme Exists",
                f"{exc}\nOverwrite the existing theme of this name?",
            )
            if retry != QMessageBox.Yes:
                return
            try:
                theme_id = self.bridge.create_theme_from_colors(
                    name, colors, mode=mode, force=True
                )
            except Exception as exc2:  # noqa: BLE001
                self.statusBar().showMessage(f"Save failed: {exc2}", 8000)
                return
        if apply:
            self.statusBar().showMessage(f"Applying theme: {theme_id}…")
            QApplication.processEvents()
            outcome = self.bridge.apply_theme(theme_id, force=True)
            if outcome["ok"]:
                self.statusBar().showMessage(f"Custom theme applied: {theme_id}")
                KDEIntegration.notify("Omni Theme", f"Applied custom theme: {theme_id}")
                if self._reload_plasma_check.isChecked():
                    self.kde.reload_plasma()
            else:
                detail = "; ".join(outcome.get("errors", []))
                self.statusBar().showMessage(f"Apply failed: {detail}", 8000)
        else:
            self.statusBar().showMessage(f"Theme saved: {theme_id}")
            KDEIntegration.notify("Omni Theme", f"Theme saved: {theme_id}")
        self._populate_themes()

    def _on_reset_colors(self):
        default_png = THEMES_ROOT / "default" / "wallpapers" / "default.png"
        if default_png.is_file():
            colors = WallpaperColorExtractor().extract(default_png)
        else:
            colors = {}
        self._palette_editor.set_colors(colors)
        self._current_colors = colors
        self._palette_preview.set_colors(colors)
        self.statusBar().showMessage("Colors reset to the default wallpaper palette")

    # -- watcher --------------------------------------------------------------

    def _start_watcher(self):
        if self._watcher is not None:
            return
        self._watcher = WallpaperWatcher(self._daemon_interval.value(), self)
        self._watcher.wallpaper_changed.connect(self._on_wallpaper_changed)
        self._watcher.start()
        self.statusBar().showMessage("Wallpaper watcher started")

    def _stop_watcher(self):
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = None
            self.statusBar().showMessage("Wallpaper watcher stopped")

    def _on_interval_changed(self, value: int):
        if self._watcher is not None:
            self._watcher._interval = max(1, value) * 1000
        self._save_gui_state()

    def _on_wallpaper_changed(self, new_path: str):
        self.statusBar().showMessage(f"Wallpaper changed: {Path(new_path).name}")
        if self._drop_zone.set_wallpaper(new_path, emit=False):
            self._start_extraction(new_path, auto=self._auto_apply_check.isChecked())

    def closeEvent(self, event):
        self._save_gui_state()
        self._stop_watcher()
        if self._worker is not None and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(3000)
        event.accept()


# ==========================================================================
# Entry point
# ==========================================================================


def main():
    QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("omni-theme-settings")
    app.setApplicationDisplayName("Omni Theme Settings")
    app.setOrganizationName("omni-theme-cachy")

    window = OmniSettingsWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
