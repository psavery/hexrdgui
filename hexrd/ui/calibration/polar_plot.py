import numpy as np

from hexrd import instrument
from .polarview import PolarView

from .display_plane import DisplayPlane

from hexrd.ui.hexrd_config import HexrdConfig
from hexrd.ui.utils import select_merged_rings


def polar_viewer():
    images_dict = HexrdConfig().current_images_dict()
    plane_data = HexrdConfig().active_material.planeData

    # HEDMInstrument expects None Euler angle convention for the
    # config. Let's get it as such.
    iconfig = HexrdConfig().instrument_config_none_euler_convention
    return InstrumentViewer(iconfig, images_dict, plane_data)


def load_instrument(config):
    rme = HexrdConfig().rotation_matrix_euler()
    return instrument.HEDMInstrument(instrument_config=config,
                                     tilt_calibration_mapping=rme)


class InstrumentViewer:

    def __init__(self, config, images_dict, plane_data):
        self.type = 'polar'
        self.plane_data = plane_data
        self.instr = load_instrument(config)
        self.images_dict = images_dict
        self.dplane = DisplayPlane()

        # Resolution settings
        # As far as I can tell, self.pixel_size won't actually change
        # anything for a polar plot, so just hard-code it.
        self.pixel_size = 0.5

        self._make_dpanel()

        self.draw_polar()
        self.add_rings()

    def _make_dpanel(self):
        self.dpanel_sizes = self.dplane.panel_size(self.instr)
        self.dpanel = self.dplane.display_panel(self.dpanel_sizes,
                                                self.pixel_size)

    @property
    def angular_grid(self):
        return self.pv.angular_grid

    def draw_polar(self):
        """show polar view of rings"""
        self.pv = PolarView(self.instr, eta_min=-180., eta_max=180.)
        self.pv.warp_all_images()

        tth_min = HexrdConfig().polar_res_tth_min
        tth_max = HexrdConfig().polar_res_tth_max

        self._extent = [tth_min, tth_max, 180., -180.]   # l, r, b, t
        self.img = self.pv.img
        self.snip1d_background = self.pv.snip1d_background

    def clear_rings(self):
        self.ring_data = []
        self.rbnd_data = []
        self.rbnd_indices = []

    def add_rings(self):
        self.clear_rings()

        selected_rings = HexrdConfig().selected_rings
        if HexrdConfig().show_rings:
            dp = self.dpanel

            if selected_rings:
                # We should only get specific values
                tth_list = self.plane_data.getTTh()
                tth_list = [tth_list[i] for i in selected_rings]
                delta_tth = np.degrees(self.plane_data.tThWidth)

                ring_angs, ring_xys = dp.make_powder_rings(
                    tth_list, delta_tth=delta_tth, delta_eta=1)
            else:
                ring_angs, ring_xys = dp.make_powder_rings(
                    self.plane_data, delta_eta=1)

                tth_list = self.plane_data.getTTh()

            for tth in np.degrees(tth_list):
                self.ring_data.append(np.array([[-180, tth], [180, tth]]))

        if HexrdConfig().show_ring_ranges:
            indices, ranges = self.plane_data.getMergedRanges()

            if selected_rings:
                # This ensures the correct ranges are selected
                indices, ranges = select_merged_rings(selected_rings, indices,
                                                      ranges)

            for ind, r in zip(indices, np.degrees(ranges)):
                self.rbnd_data.append(np.array([[-180, r[0]],
                                                [180, r[0]]]))
                self.rbnd_data.append(np.array([[-180, r[1]],
                                                [180, r[1]]]))
                # Append twice since we append to rbnd_data twice
                self.rbnd_indices.append(ind)
                self.rbnd_indices.append(ind)

        return self.ring_data

    def update_detector(self, det):
        self.pv.update_detector(det)
        self.img = self.pv.img

    def write_image(self, filename='polar_image.npz'):
        np.savez(filename,
                 tth_coordinates=self.angular_grid[1],
                 eta_coordinates=self.angular_grid[0],
                 intensities=self.img,
                 extent=np.radians(self._extent))
