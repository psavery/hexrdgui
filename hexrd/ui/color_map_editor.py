import copy

from matplotlib import cm
import matplotlib.colors

import hexrd.ui.constants
from hexrd.ui.ui_loader import UiLoader


class ColorMapEditor:

    def __init__(self, image_tab_widget, parent=None):
        self.image_tab_widget = image_tab_widget

        loader = UiLoader()
        self.ui = loader.load_file('color_map_editor.ui', parent)

        self.load_cmaps()

        self.setup_connections()

    def load_cmaps(self):
        cmaps = sorted(i[:-2] for i in dir(cm) if i.endswith('_r'))
        self.ui.color_map.addItems(cmaps)

        # Set the combobox to be the default
        self.ui.color_map.setCurrentText(hexrd.ui.constants.DEFAULT_CMAP)

    def setup_connections(self):
        self.ui.maximum.valueChanged.connect(self.update_mins_and_maxes)
        self.ui.minimum.valueChanged.connect(self.update_mins_and_maxes)

        self.ui.color_map.currentIndexChanged.connect(self.update_cmap)
        self.ui.reverse.toggled.connect(self.update_cmap)
        self.ui.show_under.toggled.connect(self.update_cmap)
        self.ui.show_over.toggled.connect(self.update_cmap)

        self.ui.maximum.valueChanged.connect(self.update_norm)
        self.ui.minimum.valueChanged.connect(self.update_norm)
        self.ui.log_scale.toggled.connect(self.update_norm)

        self.image_tab_widget.new_images_loaded.connect(self.update_bounds)

    def update_mins_and_maxes(self):
        # We can't do this in PySide2 for some reason:
        # self.ui.maximum.valueChanged.connect(self.ui.minimum.setMaximum)
        # self.ui.minimum.valueChanged.connect(self.ui.maximum.setMinimum)
        self.ui.maximum.setMinimum(self.ui.minimum.value())
        self.ui.minimum.setMaximum(self.ui.maximum.value())

    def update_bounds(self):
        bounds = self.image_tab_widget.value_range()
        self.ui.minimum.setMinimum(bounds[0])
        self.ui.minimum.setToolTip('Min: ' + str(bounds[0]))
        self.ui.maximum.setMaximum(bounds[1])
        self.ui.maximum.setToolTip('Max: ' + str(bounds[1]))

    def update_cmap(self):
        # Get the Colormap object from the name
        cmap = cm.get_cmap(self.ui.color_map.currentText())

        if self.ui.reverse.isChecked():
            cmap = cmap.reversed()

        # For set_under() and set_over(), we don't want to edit the
        # original color map, so make a copy
        cmap = copy.copy(cmap)

        if self.ui.show_under.isChecked():
            cmap.set_under('b')

        if self.ui.show_over.isChecked():
            cmap.set_over('r')

        self.image_tab_widget.set_cmap(cmap)

    def update_norm(self):
        min = self.ui.minimum.value()
        max = self.ui.maximum.value()

        if self.ui.log_scale.isChecked():
            norm = matplotlib.colors.LogNorm(vmin=min, vmax=max)
        else:
            norm = matplotlib.colors.Normalize(vmin=min, vmax=max)

        self.image_tab_widget.set_norm(norm)
