import os
import yaml
import glob
import numpy as np

from hexrd import imageseries

from PySide2.QtGui import QCursor
from PySide2.QtCore import QObject, Qt, QPersistentModelIndex, QThreadPool, Signal
from PySide2.QtWidgets import QTableWidgetItem, QFileDialog, QMenu, QMessageBox

from hexrd.ui.async_worker import AsyncWorker
from hexrd.ui.cal_progress_dialog import CalProgressDialog
from hexrd.ui.hexrd_config import HexrdConfig
from hexrd.ui.image_file_manager import ImageFileManager
from hexrd.ui.ui_loader import UiLoader

"""
    This panel is in charge of loading file(s) for the experiment. It is built
    up in a few steps, and defines how they should be loaded, transformed, and
    attempts to apply intelligent templates to avoid manual entry of everything.
    The final act is to click load data and bring the data set in.
"""


class LoadPanel(QObject):

    # Emitted when new images are loaded
    new_images_loaded = Signal()

    def __init__(self, parent=None):
        super(LoadPanel, self).__init__(parent)

        loader = UiLoader()
        self.ui = loader.load_file('load_panel.ui', parent)

        self.ims = HexrdConfig().imageseries_dict
        self.parent_dir = HexrdConfig().images_dir

        self.files = []
        self.omega_min = []
        self.omega_max = []
        self.dark_file = None
        self.idx = 0
        self.ext = ''

        self.setup_gui()
        self.setup_connections()

    # Setup GUI

    def setup_gui(self):
        if not HexrdConfig().load_panel_state:
            HexrdConfig().load_panel_state = {'agg': 0, 'trans': 0, 'dark': 0}
        self.state = HexrdConfig().load_panel_state

        self.ui.aggregation.setCurrentIndex(self.state['agg'])
        self.ui.transform.setCurrentIndex(self.state['trans'])
        self.ui.darkMode.setCurrentIndex(self.state['dark'])
        if 'dark_file' in self.state:
            self.dark_file = self.state['dark_file']

        self.dark_mode_changed()
        if not self.parent_dir:
            self.ui.img_directory.setText('No directory set')
        else:
            self.ui.img_directory.setText(os.path.dirname(self.parent_dir))
        self.detectors_changed()
        self.ui.file_options.resizeColumnsToContents()

    def setup_connections(self):
        self.ui.image_folder.clicked.connect(self.select_folder)
        self.ui.image_files.clicked.connect(self.select_images)
        self.ui.selectDark.clicked.connect(self.select_dark_img)
        self.ui.read.clicked.connect(self.read_data)

        self.ui.darkMode.currentIndexChanged.connect(self.dark_mode_changed)
        self.ui.detector.currentIndexChanged.connect(self.create_table)
        self.ui.aggregation.currentIndexChanged.connect(self.agg_changed)
        self.ui.transform.currentIndexChanged.connect(self.trans_changed)

        self.ui.file_options.customContextMenuRequested.connect(
            self.contextMenuEvent)
        self.ui.file_options.cellChanged.connect(self.omega_data_changed)
        HexrdConfig().detectors_changed.connect(self.detectors_changed)

    # Handle GUI changes

    def dark_mode_changed(self):
        self.state['dark'] = self.ui.darkMode.currentIndex()

        if self.state['dark'] == 4:
            self.ui.selectDark.setEnabled(True)
            self.ui.dark_file.setText(
                self.dark_file if self.dark_file else '(No File Selected)')
            self.enable_read()
        else:
            self.ui.selectDark.setEnabled(False)
            self.ui.dark_file.setText(
                '(Using ' + str(self.ui.darkMode.currentText()) + ')')
            self.enable_read()
            if 'dark_file' in self.state:
                del self.state['dark_file']

    def detectors_changed(self):
        self.ui.detector.clear()
        self.ui.detector.addItems(HexrdConfig().get_detector_names())

    def agg_changed(self):
        self.state['agg'] = self.ui.aggregation.currentIndex()

    def trans_changed(self):
        self.state['trans'] = self.ui.transform.currentIndex()

    def dir_changed(self):
        self.ui.img_directory.setText(os.path.dirname(self.parent_dir))

    def select_folder(self, new_dir=None):
        # This expects to define the root image folder.
        if not new_dir:
            caption = HexrdConfig().images_dirtion = 'Select directory for images'
            new_dir = QFileDialog.getExistingDirectory(
                self.ui, caption, dir=self.parent_dir)

        # Only update if a new directory is selected
        if new_dir and new_dir != self.parent_dir:
            self.ui.image_files.setEnabled(True)
            HexrdConfig().set_images_dir(new_dir)
            self.parent_dir = new_dir
            self.dir_changed()

    def select_dark_img(self):
        # This takes one image to use for dark subtraction.
        caption = HexrdConfig().images_dirtion = 'Select image file'
        selected_file, selected_filter = QFileDialog.getOpenFileNames(
            self.ui, caption, dir=self.parent_dir)

        if selected_file:
            self.dark_file = selected_file[0]
            self.state['dark_file'] = self.dark_file
            self.dark_mode_changed()
            self.enable_read()

    def select_images(self):
        # This takes one or more images for a single detector.
        caption = HexrdConfig().images_dirtion = 'Select image file(s)'
        selected_files, selected_filter = QFileDialog.getOpenFileNames(
            self.ui, caption, dir=self.parent_dir)

        if selected_files:
            if self.parent_dir is None:
                self.select_folder(os.path.dirname(selected_files[0]))
            self.reset_data()
            self.load_image_data(selected_files)
            self.create_table()
            self.enable_read()

    def reset_data(self):
        self.directories = []
        self.empty_frames = 0
        self.total_frames = []
        self.omega_min = []
        self.omega_max = []
        self.delta = []
        self.files = []

    def load_image_data(self, selected_files):
        self.ext = os.path.splitext(selected_files[0])[1]
        has_omega = False

        # Select the path if the file(s) are HDF5
        if (ImageFileManager().is_hdf5(self.ext) and not
                ImageFileManager().path_exists(selected_files[0])):
            if ImageFileManager().path_prompt(selected_files[0]) is not None:
                return

        fnames = []
        tmp_ims = []
        for img in selected_files:
            f = os.path.split(img)[1]
            name = os.path.splitext(f)[0]
            if not self.ui.subdirectories.isChecked():
                name = name.rsplit('_', 1)[0]
            if self.ext != '.yml':
                tmp_ims.append(ImageFileManager().open_file(img))

            fnames.append(name)

        self.find_images(fnames)

        if not self.files:
            return

        if self.ext == '.yml':
            for yf in self.yml_files[0]:
                ims = ImageFileManager().open_file(yf)
                self.total_frames.append(len(ims))

            for f in self.files[0]:
                with open(f, 'r') as raw_file:
                    data = yaml.safe_load(raw_file)
                if 'ostart' in data['meta'] or 'omega' in data['meta']:
                    self.get_yaml_omega_data(data)
                else:
                    self.omega_min = [''] * len(self.yml_files[0])
                    self.omega_max = [''] * len(self.yml_files[0])
                    self.delta = [''] * len(self.yml_files[0])
                self.empty_frames = data['options']['empty-frames']
        else:
            for ims in tmp_ims:
                has_omega = 'omega' in ims.metadata
                self.total_frames.append(len(ims))
                if has_omega:
                    self.get_omega_data(ims)
                else:
                    self.omega_min.append('')
                    self.omega_max.append('')
                    self.delta.append('')

    def get_omega_data(self, ims):
        minimum = ims.metadata['omega'][0][0]
        size = len(ims.metadata['omega']) - 1
        maximum = ims.metadata['omega'][size][1]

        self.omega_min.append(minimum)
        self.omega_max.append(maximum)
        self.delta.append((maximum - minimum)/len(ims))

    def get_yaml_omega_data(self, data):
        if 'ostart' in data['meta']:
            self.omega_min.append(data['meta']['ostart'])
            self.omega_max.append(data['meta']['ostop'])
            wedge = (data['meta']['ostop'] - data['meta']['ostart']) / self.total_frames[0]
            self.delta.append(wedge)
        else:
            if isinstance(data['meta']['omega'], str):
                words = data['meta']['omega'].split()
                fname = os.path.join(self.parent_dir, words[2])
                nparray = np.load(fname)
            else:
                nparray = data['meta']['omega']

            for idx, vals in enumerate(nparray):
                self.omega_min.append(vals[0])
                self.omega_max.append(vals[1])
                self.delta.append((vals[1] - vals[0]) / self.total_frames[idx])

    def find_images(self, fnames):
        if (self.ui.subdirectories.isChecked()):
            self.find_directories()
            self.match_dirs_images(fnames)
        else:
            self.match_images(fnames)

        if self.files and self.ext == '.yml':
            self.get_yml_files()

    def find_directories(self):
        # Find all detector directories
        num_det = len(HexrdConfig().get_detector_names())
        dirs = []
        for sub_dir in os.scandir(os.path.dirname(self.parent_dir)):
            if (os.path.isdir(sub_dir)
                    and sub_dir.name in HexrdConfig().get_detector_names()):
                dirs.append(sub_dir.path)
        # Show error if expected detector directories are not found
        if len(dirs) != num_det:
            dir_names = []
            if len(dirs) > 0:
                for path in dirs:
                    dir_names.append(os.path.basename(path))
            diff = list(
                set(HexrdConfig().get_detector_names()) - set(dir_names))
            msg = (
                'ERROR - No directory found for the following detectors: \n'
                + str(diff)[1:-1])
            QMessageBox.warning(None, 'HEXRD', msg)
            return

        self.directories = sorted(dirs)[:num_det]

    def match_images(self, fnames):
        file_list = []
        dets = []
        for item in os.scandir(self.parent_dir):
            file_name = os.path.splitext(item.name)[0]
            instance = file_name.rsplit('_', 1)[0]
            if instance == file_name:
                continue
            det = file_name.rsplit('_', 1)[1]
            if os.path.isfile(item) and instance in fnames:
                file_list.append(item.path)
                if det and det not in dets:
                    dets.append(det)
                    self.files.append([])
        for f in file_list:
            det = f.rsplit('.', 1)[0].rsplit('_', 1)[1]
            if det in dets:
                i = dets.index(det)
                self.files[i].append(f)
        # Display error if equivalent files are not found for ea. detector
        files_per_det = all(len(self.files[0]) == len(elem) for elem in self.files)
        num_det = len(HexrdConfig().get_detector_names())
        if len(self.files) != num_det or not files_per_det:
            msg = ('ERROR - There must be the same number of files for each detector.')
            QMessageBox.warning(None, 'HEXRD', msg)
            self.files = []
            return

        self.files = sorted(self.files)[:len(self.files)]

    def match_dirs_images(self, fnames):
        # Find the images with the same name for the remaining detectors
        for i in range(len(self.directories)):
            self.files.append([])
            for item in os.scandir(self.directories[i]):
                fname = os.path.splitext(item.name)[0]
                if os.path.isfile(item) and fname in fnames:
                    self.files[i].append(item.path)
            # Display error if equivalent files are not found for ea. detector
            if i > 0 and len(self.files[i]) != len(fnames):
                diff = list(set(self.files[i]) - set(self.files[i-1]))
                msg = ('ERROR - No equivalent file(s) found for '
                        + str(diff)[1:-1] + ' in ' + self.directories[i])
                QMessageBox.warning(None, 'HEXRD', msg)
                self.files = []
                break

    def get_yml_files(self):
        self.yml_files = []
        for det in self.files:
            files = []
            for f in det:
                with open(f, 'r') as yml_file:
                    data = yaml.safe_load(yml_file)['image-files']
                raw_images = data['files'].split()
                for raw_image in raw_images:
                    files.extend(glob.glob(
                        os.path.join(data['directory'], raw_image)))
            self.yml_files.append(files)

    def enable_read(self):
        if (self.ext == '.tiff'
                or '' not in self.omega_min and '' not in self.omega_max):
            if self.state['dark'] == 4 and self.dark_file is not None:
                self.ui.read.setEnabled(len(self.files))
                return
            elif self.state['dark'] != 4 and len(self.files):
                self.ui.read.setEnabled(True)
                return
        self.ui.read.setEnabled(False)

    # Handle table setup and changes

    def create_table(self):
        # Create the table if files have successfully been selected
        if not len(self.files):
            return

        if self.ext == '.yml':
            table_files = self.yml_files
        else:
            table_files = self.files

        self.idx = self.ui.detector.currentIndex()
        self.ui.file_options.setRowCount(
            len(table_files[self.idx]))

        # Create the rows
        for row in range(self.ui.file_options.rowCount()):
            for column in range(self.ui.file_options.columnCount()):
                item = QTableWidgetItem()
                item.setTextAlignment(Qt.AlignCenter)
                self.ui.file_options.setItem(row, column, item)

        # Populate the rows
        for i in range(self.ui.file_options.rowCount()):
            curr = table_files[self.idx][i]
            self.ui.file_options.item(i, 0).setText(os.path.split(curr)[1])
            self.ui.file_options.item(i, 1).setText(str(self.empty_frames))
            self.ui.file_options.item(i, 2).setText(str(self.total_frames[i]))
            self.ui.file_options.item(i, 3).setText(str(self.omega_min[i]))
            self.ui.file_options.item(i, 4).setText(str(self.omega_max[i]))
            self.ui.file_options.item(i, 5).setText(str(self.delta[i]))

            # Set tooltips
            self.ui.file_options.item(i, 0).setToolTip(curr)
            self.ui.file_options.item(i, 3).setToolTip('Minimum must be set')
            self.ui.file_options.item(i, 4).setToolTip(
                'Must set either maximum or delta')
            self.ui.file_options.item(i, 5).setToolTip(
                'Must set either maximum or delta')

            # Don't allow editing of file name or total frames
            self.ui.file_options.item(i, 0).setFlags(Qt.ItemIsEnabled)
            self.ui.file_options.item(i, 2).setFlags(Qt.ItemIsEnabled)
            # If raw data offset can only be changed in YAML file
            if self.ext == '.yml':
                self.ui.file_options.item(i, 1).setFlags(Qt.ItemIsEnabled)


        self.ui.file_options.resizeColumnsToContents()

    def contextMenuEvent(self, event):
        # Allow user to delete selected file(s)
        menu = QMenu(self.ui)
        remove = menu.addAction('Remove Selected Files')
        action = menu.exec_(QCursor.pos())

        # Re-selects the current row if context menu is called on disabled cell
        i = self.ui.file_options.indexAt(event)
        self.ui.file_options.selectRow(i.row())

        indices = []
        if action == remove:
            for index in self.ui.file_options.selectedIndexes():
                indices.append(QPersistentModelIndex(index))

            for idx in indices:
                self.ui.file_options.removeRow(idx.row())

            if self.ui.file_options.rowCount():
                for i in range(len(self.files)):
                    self.files[i] = []

                for row in range(self.ui.file_options.rowCount()):
                    f = self.ui.file_options.item(row, 0).text()
                    for i in range(len(self.files)):
                        self.files[i].append(self.directories[i] + f)
            else:
                self.directories = []
                self.files = []
        self.enable_read()

    def omega_data_changed(self, row, column):
        # Update the values for equivalent files when the data is changed
        self.blockSignals(True)

        curr_val = self.ui.file_options.item(row, column).text()
        total_frames = self.total_frames[row] - self.empty_frames
        if curr_val != '':
            if column == 1:
                self.empty_frames = int(curr_val)
                for r in range(self.ui.file_options.rowCount()):
                    self.ui.file_options.item(r, column).setText(str(curr_val))
                self.omega_data_changed(row, 3)
            # Update delta when min or max omega are changed
            elif column == 3:
                self.omega_min[row] = float(curr_val)
                if self.omega_max[row] or self.delta[row]:
                    self.omega_data_changed(row, 4)
            elif column == 4:
                self.omega_max[row] = float(curr_val)
                if self.omega_min[row] != '':
                    diff = abs(self.omega_max[row] - self.omega_min[row])
                    delta = diff / total_frames
                    self.delta[row] = delta
                    self.ui.file_options.item(row, 5).setText(
                        str(round(delta, 2)))
            elif column == 5:
                self.delta[row] = float(curr_val)
                if self.omega_min[row] != '':
                    diff = self.delta[row] * total_frames
                    maximum = self.omega_min[row] + diff
                    self.omega_max[row] = maximum
                    self.ui.file_options.item(row, 4).setText(
                        str(float(maximum)))
            self.enable_read()

        self.blockSignals(False)

    # Process files

    def read_data(self):
        # When this is pressed read in a complete set of data for all detectors.
        # Run the imageseries processing in a background thread and display a
        # loading dialog

        # Create threads and loading dialog
        thread_pool = QThreadPool(self.parent())
        progress_dialog = CalProgressDialog(self.parent())
        progress_dialog.setWindowTitle('Loading Processed Imageseries')

        # Start processing in background
        worker = AsyncWorker(self.process_ims)
        thread_pool.start(worker)

        # On completion load imageseries nd close loading dialog
        worker.signals.result.connect(self.finish_processing_ims)
        worker.signals.finished.connect(progress_dialog.accept)
        progress_dialog.exec_()

    def process_ims(self):
        # Open selected images as imageseries
        det_names = HexrdConfig().get_detector_names()

        if len(self.files[0]) > 1:
            for i, det in enumerate(det_names):
                if self.directories:
                    dirs = self.directories[i]
                else:
                    dirs = self.parent_dir
                ims = ImageFileManager().open_directory(dirs, self.files[i])
                HexrdConfig().imageseries_dict[det] = ims
        else:
            ImageFileManager().load_images(det_names, self.files)

        # Process the imageseries
        self.apply_operations(HexrdConfig().imageseries_dict)
        if self.state['agg']:
            self.display_aggregation(HexrdConfig().imageseries_dict)
        elif '' not in self.omega_min:
            self.add_omega_metadata(HexrdConfig().imageseries_dict)

    def finish_processing_ims(self):
        # Display processed images on completion
        # The setEnabled options will not be needed once the panel
        # is complete - those dialogs will be removed.
        self.parent().action_edit_angles.setEnabled(True)
        self.parent().image_tab_widget.load_images()
        self.new_images_loaded.emit()

    def apply_operations(self, ims_dict):
        # Apply the operations to the imageseries
        for key in ims_dict.keys():
            ops = []
            if self.state['dark'] != 5:
                if not self.empty_frames and self.state['dark'] == 1:
                    msg = ('ERROR: \n No empty frames set. '
                            + 'No dark subtracion will be performed.')
                    QMessageBox.warning(None, 'HEXRD', msg)
                    return
                else:
                    self.get_dark_op(ops, ims_dict[key])

            if self.state['trans']:
                self.get_flip_op(ops)

            frames = self.get_range(ims_dict[key])

            ims_dict[key] = imageseries.process.ProcessedImageSeries(
                ims_dict[key], ops, frame_list=frames)

    def get_dark_op(self, oplist, ims):
        # Create or load the dark image if selected
        if self.state['dark'] != 4:
            frames = len(ims)
            if self.state['dark'] == 0:
                darkimg = imageseries.stats.median(ims, frames)
            elif self.state['dark'] == 1:
                darkimg = imageseries.stats.average(ims, self.empty_frames)
            elif self.state['dark'] == 2:
                darkimg = imageseries.stats.average(ims, frames)
            else:
                darkimg = imageseries.stats.max(ims, frames)
        else:
            darkimg = imageseries.stats.median(
                ImageFileManager().open_file(self.dark_file))

        oplist.append(('dark', darkimg))

    def get_flip_op(self, oplist):
        # Change the image orientation
        if self.state['trans'] == 0:
            return

        if self.state['trans'] == 1:
            key = 'v'
        elif self.state['trans'] == 2:
            key = 'h'
        elif self.state['trans'] == 3:
            key = 't'
        elif self.state['trans'] == 4:
            key = 'r90'
        elif self.state['trans'] == 5:
            key = 'r180'
        else:
            key = 'r270'

        oplist.append(('flip', key))

    def get_range(self, ims):
        if self.ext == '.yml':
            return range(len(ims))
        else:
            return range(self.empty_frames, len(ims))

    def display_aggregation(self, ims_dict):
        # Display aggregated image from imageseries
        for key in ims_dict.keys():
            if self.state['agg'] == 1:
                ims_dict[key] = [imageseries.stats.max(
                    ims_dict[key], len(ims_dict[key]))]
            elif self.state['agg'] == 2:
                ims_dict[key] = [imageseries.stats.median(
                    ims_dict[key], len(ims_dict[key]))]
            else:
                ims_dict[key] = [imageseries.stats.average(
                    ims_dict[key], len(ims_dict[key]))]

    def add_omega_metadata(self, ims_dict):
        # Add on the omega metadata if there is any
        files = self.yml_files if self.ext == '.yml' else self.files
        for key in ims_dict.keys():
            nframes = len(ims_dict[key])
            omw = imageseries.omega.OmegaWedges(nframes)
            for i in range(len(files[0])):
                nsteps = self.total_frames[i] - self.empty_frames
                start = self.omega_min[i]
                stop = self.omega_max[i]

                # Don't add wedges if defaults are unchanged
                if not (start - stop):
                    return

                omw.addwedge(start, stop, nsteps)

            ims_dict[key].metadata['omega'] = omw.omegas
