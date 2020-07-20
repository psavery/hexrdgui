import numpy as np

from PySide2.QtWidgets import QMessageBox

from hexrd import indexer, fitgrains
from hexrd.findorientations import (
    create_clustering_parameters, generate_eta_ome_maps,
    generate_orientation_fibers, run_cluster
)
from hexrd.fitgrains import fit_grains
from hexrd.xrdutil import EtaOmeMaps

from hexrd.ui.hexrd_config import HexrdConfig
from hexrd.ui.indexing.create_config import create_indexing_config
from hexrd.ui.indexing.fit_grains_dialog import FitGrainsDialog
from hexrd.ui.indexing.ome_maps_select_dialog import OmeMapsSelectDialog
from hexrd.ui.indexing.ome_maps_viewer_dialog import OmeMapsViewerDialog


class IndexingRunner:
    def __init__(self, parent=None):
        self.parent = parent
        self.ome_maps_select_dialog = None
        self.ome_maps_viewer_dialog = None
        self.fit_grains_dialog = None

        self.ome_maps = None

    def clear(self):
        self.ome_maps_select_dialog = None
        self.ome_maps_viewer_dialog = None
        self.fit_grains_dialog = None

        self.ome_maps = None

    def run(self):
        # We will go through these steps:
        # 1. Have the user select/generate eta omega maps
        # 2. Have the user view and threshold the eta omega maps
        # 3. Run the indexing
        self.select_ome_maps()

    def select_ome_maps(self):
        dialog = OmeMapsSelectDialog(self.parent)
        dialog.accepted.connect(self.ome_maps_selected)
        dialog.rejected.connect(self.clear)
        dialog.show()
        self.ome_maps_select_dialog = dialog

    def ome_maps_selected(self):
        dialog = self.ome_maps_select_dialog
        if dialog is None:
            return

        if dialog.method_name == 'load':
            self.ome_maps = EtaOmeMaps(dialog.file_name)
        else:
            # Create a full indexing config
            config = create_indexing_config()
            self.ome_maps = generate_eta_ome_maps(config, save=False)

        self.ome_maps_select_dialog = None
        self.view_ome_maps()

    def view_ome_maps(self):
        # Now, show the Ome Map viewer

        dialog = OmeMapsViewerDialog(self.ome_maps, self.parent)
        dialog.accepted.connect(self.ome_maps_viewed)
        dialog.rejected.connect(self.clear)
        dialog.show()

        self.ome_maps_viewer_dialog = dialog

    def ome_maps_viewed(self):
        # The dialog should have automatically updated our internal config
        # Let's go ahead and run the indexing!

        # For now, always use all hkls from eta omega maps
        hkls = list(range(len(self.ome_maps.iHKLList)))
        indexing_config = HexrdConfig().indexing_config
        indexing_config['find_orientations']['seed_search']['hkl_seeds'] = hkls

        # Create a full indexing config
        config = create_indexing_config()

        # Generate the orientation fibers
        self.qfib = generate_orientation_fibers(config, self.ome_maps)

        # Run the indexer
        ncpus = config.multiprocessing
        completeness = indexer.paintGrid(
            self.qfib,
            self.ome_maps,
            etaRange=np.radians(config.find_orientations.eta.range),
            omeTol=np.radians(config.find_orientations.omega.tolerance),
            etaTol=np.radians(config.find_orientations.eta.tolerance),
            omePeriod=np.radians(config.find_orientations.omega.period),
            threshold=config.find_orientations.threshold,
            doMultiProc=ncpus > 1,
            nCPUs=ncpus
        )
        self.completeness = np.array(completeness)
        print('Indexing complete')

        self.run_grain_fitting()

    def run_grain_fitting(self):
        # Run dialog for user options
        dialog = FitGrainsDialog(self.parent)
        dialog.accepted.connect(self.fit_grains_config_accepted)
        dialog.rejected.connect(self.clear)
        self.fit_grains_dialog = dialog
        dialog.show()

    def fit_grains_config_accepted(self):
        print('Running grain fitting...')

        # Create a full indexing config
        config = create_indexing_config()

        min_samples, mean_rpg = create_clustering_parameters(config,
                                                             self.ome_maps)

        kwargs = {
            'compl': self.completeness,
            'qfib': self.qfib,
            'qsym': config.material.plane_data.getQSym(),
            'cfg': config,
            'min_samples': min_samples,
            'compl_thresh': config.find_orientations.clustering.completeness,
            'radius': config.find_orientations.clustering.radius
        }
        qbar, cl = run_cluster(**kwargs)
        print('qbar:', qbar.shape)
        print(qbar)
        print('cl:', cl.shape)
        print(cl)

        self.qbar = qbar
        self.cl = cl
        print('Grain fitting is complete!')
        print(f'{self.qbar.shape[1]} grains were found')

        QMessageBox.information(
            None, 'Grain fitting is complete', f'{self.qbar.shape[1]} grains were found')
