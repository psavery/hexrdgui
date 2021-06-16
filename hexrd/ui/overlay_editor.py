from hexrd.ui.laue_overlay_editor import LaueOverlayEditor
from hexrd.ui.powder_overlay_editor import PowderOverlayEditor
from hexrd.ui.mono_rotation_series_overlay_editor import (
    MonoRotationSeriesOverlayEditor
)
from hexrd.ui.ui_loader import UiLoader


class OverlayEditor:

    def __init__(self, parent=None):
        loader = UiLoader()
        self.ui = loader.load_file('overlay_editor.ui', parent)

        self.powder_overlay_editor = PowderOverlayEditor(self.ui)
        self.ui.powder_overlay_editor_layout.addWidget(
            self.powder_overlay_editor.ui)

        self.laue_overlay_editor = LaueOverlayEditor(self.ui)
        self.ui.laue_overlay_editor_layout.addWidget(
            self.laue_overlay_editor.ui)

        self.mono_rotation_series_overlay_editor = (
            MonoRotationSeriesOverlayEditor(self.ui)
        )
        self.ui.mono_rotation_series_overlay_editor_layout.addWidget(
            self.mono_rotation_series_overlay_editor.ui)

        self.ui.tab_widget.tabBar().hide()

        self.overlay = None

    @property
    def overlay(self):
        return self._overlay

    @overlay.setter
    def overlay(self, v):
        self._overlay = v
        self.update_type_tab()

    @property
    def type(self):
        return self.overlay['type'] if self.overlay else None

    def update_type_tab(self):
        if self.type is None:
            w = getattr(self.ui, 'blank_tab')
        else:
            # Take advantage of the naming scheme...
            w = getattr(self.ui, self.type.value + '_tab')

        self.ui.tab_widget.setCurrentWidget(w)

        if self.active_widget is not None:
            self.active_widget.overlay = self.overlay

    @property
    def active_widget(self):
        widgets = {
            'powder': self.powder_overlay_editor,
            'laue': self.laue_overlay_editor,
            'mono_rotation_series': self.mono_rotation_series_overlay_editor
        }

        if self.type is None or self.type.value not in widgets:
            return None

        return widgets[self.type.value]

    def update_active_widget_gui(self):
        w = self.active_widget
        if w is None:
            return

        w.update_gui()

    def update_refinement_options(self):
        # Right now, only powder refinement options can vary
        self.powder_overlay_editor.update_refinement_options()
