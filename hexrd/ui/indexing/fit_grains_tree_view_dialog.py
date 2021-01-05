from hexrd.ui.hexrd_config import HexrdConfig
from hexrd.ui.tree_views.dict_tree_view import DictTreeViewDialog


class FitGrainsTreeViewDialog(DictTreeViewDialog):
    def __init__(self, parent=None):
        config = HexrdConfig().indexing_config['fit_grains']
        super().__init__(config, parent)
        self.setWindowTitle('Fit Grains Config')
