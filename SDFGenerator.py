from krita import Krita, Extension
from PyQt5.QtWidgets import QInputDialog, QMessageBox
import math, time
from array import array
import ctypes
from ctypes import POINTER, c_float, c_uint32, c_int, c_uint8
import os


def get_ptr(arr, type):
    addr, count = arr.buffer_info()
    return ctypes.cast(addr, POINTER(type))


class SDFGenerator(Extension):
    def __init__(self, parent):
        super().__init__(parent)
        self.c_compute_sdf = None

    def setup(self):
        pass

    def init_c_library(self):
        """Loads the DLL safely."""
        if self.c_compute_sdf:
            return True
        try:
            # Get the directory where THIS script is located
            dir_path = os.path.dirname(os.path.realpath(__file__))
            dll_path = os.path.join(dir_path, "sdf_logic.dll")

            sdf_lib = ctypes.CDLL(dll_path)
            if sdf_lib:
                QMessageBox.information(None, "Lib loaded", "Success, Yay!")
            else:
                QMessageBox.information(
                    None, "Lib not loaded", "Oh, no. How will we live?!?!"
                )
            self.c_compute_sdf = sdf_lib.compute_sdf
            self.c_compute_sdf.argtypes = [
                c_int,  # width
                c_int,  # height
                POINTER(c_uint8),  # pixels
                c_float,  # out_dist
                POINTER(c_uint8),  # out_dist_in
            ]
            return True
        except Exception as e:
            QMessageBox.critical(None, "SDF Error", f"Could not load DLL: {str(e)}")
            return False

    def createActions(self, window):
        action = window.createAction(
            "distance_map", "Generate Distance Map (8SSEDT)", "tools/scripts"
        )
        action.triggered.connect(self.run)

    def run(self):
        if not self.init_c_library():
            return

        app = Krita.instance()
        doc = app.activeDocument()
        if not doc:
            return
        node = doc.activeNode()
        if not node:
            return

        width, height = doc.width(), doc.height()
        max_range, ok = QInputDialog.getInt(
            None, "SDF Range", "Max Range (pixels):", 50, 1, 2000, 1
        )
        if not ok:
            return

        timings = {}

        # ---------------------------------------------------------
        # BLOCK 1: FETCH DATA
        # ---------------------------------------------------------
        t0 = time.perf_counter()
        pixel_data = node.pixelData(0, 0, width, height)
        total_pixels = width * height
        # We use bytearray for fast read access
        pixels = bytearray(pixel_data)
        pixels_ptr = (c_uint8 * len(pixels)).from_buffer(pixels)

        pixels_out = bytearray(total_pixels * 4)
        pixels_out_ptr = (c_uint8 * len(pixels_out)).from_buffer(pixels_out)

        timings["Fetch"] = time.perf_counter() - t0

        # ---------------------------------------------------------
        # BLOCK 3: 8SSEDT PASS SETUP
        # ---------------------------------------------------------
        t0 = time.perf_counter()

        self.c_compute_sdf(
            width,  # width
            height,  # height
            pixels_ptr,  # pixels
            max_range,
            pixels_out_ptr,
        )

        timings["Compute"] = time.perf_counter() - t0

        # Create Layer
        new_node = doc.createNode("SDF_8SSEDT", "paintLayer")
        doc.rootNode().addChildNode(new_node, node)
        new_node.setPixelData(bytes(pixels_out), 0, 0, width, height)
        doc.refreshProjection()

        msg = "\n".join([f"{k}: {v * 1000:.2f}ms" for k, v in timings.items()])
        QMessageBox.information(None, "SDF Result", msg)


def remap_clamped(value, low1, high1, low2, high2):
    # Determine the "clamping" bounds
    out_min, out_max = (low2, high2) if low2 < high2 else (high2, low2)

    # Calculate the remapped value
    res = (value - low1) / (high1 - low1) * (high2 - low2) + low2

    # Clamp the result
    return max(out_min, min(out_max, res))


# Register the extension
# Krita.instance().addExtension(SDFGenerator(Krita.instance()))
