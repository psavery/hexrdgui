from PySide2.QtWidgets import QFileDialog, QInputDialog

from hexrd.ui.async_runner import AsyncRunner
from hexrd.ui.hexrd_config import HexrdConfig
from hexrd.ui.ui_loader import UiLoader


class SaveImagesDialog:

    def __init__(self, parent=None, ):
        loader = UiLoader()
        self.ui = loader.load_file('save_images_dialog.ui', parent)

        self.parent_dir = HexrdConfig().working_dir
        self.async_runner = AsyncRunner(parent)

        self.setup_gui()
        self.setup_connections()

    def setup_gui(self):
        self.ui.detectors.clear()
        self.ui.detectors.addItems(HexrdConfig().detector_names)
        self.ui.pwd.setText(self.parent_dir)
        self.ui.pwd.setToolTip(self.parent_dir)
        if HexrdConfig().unagg_images:
            self.ui.ignore_agg.setEnabled(True)

    def setup_connections(self):
        self.ui.single_detector.toggled.connect(self.ui.detectors.setEnabled)
        self.ui.change_directory.clicked.connect(self.change_directory)

    def change_directory(self):
        caption = HexrdConfig().images_dirtion = 'Select directory for images'
        new_dir = QFileDialog.getExistingDirectory(
            self.ui, caption, dir=self.parent_dir)

        if new_dir:
            HexrdConfig().working_dir = new_dir
            self.parent_dir = new_dir
            self.ui.pwd.setText(self.parent_dir)
            self.ui.pwd.setToolTip(self.parent_dir)

    def save_images(self):
        if self.ui.ignore_agg.isChecked():
            ims_dict = HexrdConfig().unagg_images
        else:
            ims_dict = HexrdConfig().imageseries_dict
        dets = HexrdConfig().detector_names
        if self.ui.single_detector.isChecked():
            dets = [self.ui.detectors.currentText()]
        for det in dets:
            selected_format = self.ui.format.currentText().lower()
            filename = f'{self.ui.file_stem.text()}_{det}.{selected_format}'
            path = f'{self.parent_dir}/{filename}'
            if selected_format.startswith('hdf5'):
                selected_format = 'hdf5'
            elif selected_format.startswith('npz'):
                selected_format = 'frame-cache'

            kwargs = {}
            if selected_format == 'hdf5':
                # A path must be specified. Set it ourselves for now.
                kwargs['path'] = 'imageseries'
            elif selected_format == 'frame-cache':
                # Get the user to pick a threshold
                result, ok = QInputDialog.getDouble(self.ui, 'HEXRD',
                                                    'Choose Threshold',
                                                    10, 0, 1e12, 3)
                if not ok:
                    # User canceled...
                    return

                kwargs['threshold'] = result

                # This needs to be specified, but I think it just needs
                # to be the same as the file name...
                kwargs['cache_file'] = path

            self.async_runner.progress_title = f'Saving {filename}'
            self.async_runner.run(HexrdConfig().save_imageseries,
                                  ims_dict.get(det), det, path,
                                  selected_format, **kwargs)

    def exec_(self):
        if self.ui.exec_():
            self.save_images()
