from krita import Krita, Extension
from PyQt5.QtWidgets import QInputDialog, QMessageBox
import math, time
from array import array


class SDFGenerator(Extension):
    def __init__(self, parent):
        super().__init__(parent)

    def setup(self):
        pass

    def createActions(self, window):
        action = window.createAction(
            "distance_map", "Generate Distance Map (8SSEDT)", "tools/scripts"
        )
        action.triggered.connect(self.run)

    def run(self):
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
        # We use bytearray for fast read access
        pixels = bytearray(pixel_data)
        timings["Fetch"] = time.perf_counter() - t0

        # ---------------------------------------------------------
        # BLOCK 2: INITIALIZE 8SSEDT GRIDS
        # ---------------------------------------------------------
        t0 = time.perf_counter()
        total_pixels = width * height
        infinity = 1000000.0

        # grid_dx and grid_dy store the X and Y distance to the closest edge
        grid_dx = array("f", [infinity] * total_pixels)
        grid_dy = array("f", [infinity] * total_pixels)

        # is_inside stores the binary state (solid or not)
        is_inside = bytearray(total_pixels)

        seed_idx = array(
            "I", [i for i in range(total_pixels)]
        )  # Track the index of the source pixel
        additional_dist = array("f", [0.0] * total_pixels)  # Track pre-squared Z-offset

        for i in range(total_pixels):
            offset = i * 4
            r, g, b, a = (
                pixels[offset],
                pixels[offset + 1],
                pixels[offset + 2],
                pixels[offset + 3],
            )

            # Simple luminance + alpha check
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            if lum > 1:
                is_inside[i] = 1
                # Seed the boundary
                grid_dx[i] = 0.0
                grid_dy[i] = 0.0
                # Subpixel: how far inside are we?
                z = 1.0 - (lum / 255)
                additional_dist[i] = z  # * z
            else:
                is_inside[i] = 0

        timings["Init"] = time.perf_counter() - t0

        # ---------------------------------------------------------
        # BLOCK 3: 8SSEDT PASSES (THE CORE LOGIC)
        # ---------------------------------------------------------
        t0 = time.perf_counter()

        def index_to_coords(index, width):
            y = int(index // width)
            x = int(index % width)
            return x, y

        def coords_to_index(x, y, width):
            return int(y * width + x)

        # offset from neighbor to target in coordinates
        def compare_and_update(
            current_idx, neighbor_idx, offset_x, offset_y
        ):  # Calculate potential new vector using neighbor's existing displacement
            new_x = grid_dx[neighbor_idx] + offset_x
            new_y = grid_dy[neighbor_idx] + offset_y

            # Get the seed pixel that this neighbor is currently pointing to
            neighbor_seed = seed_idx[neighbor_idx]

            # New distance squared = X^2 + Y^2 + Precalculated_Z^2
            new_dist = (
                math.sqrt((new_x * new_x) + (new_y * new_y))
                + additional_dist[neighbor_seed]
            )

            # Current distance squared
            curr_seed = seed_idx[current_idx]
            curr_dist = (
                math.sqrt(
                    (grid_dx[current_idx] * grid_dx[current_idx])
                    + (grid_dy[current_idx] * grid_dy[current_idx])
                )
                + additional_dist[curr_seed]
            )

            if new_dist < curr_dist:
                grid_dx[current_idx] = new_x
                grid_dy[current_idx] = new_y
                seed_idx[current_idx] = neighbor_seed

        # 1 Pass: Top-Left to Bottom-Right
        for y in range(height):
            y_coord = y * width
            for x in range(width):
                i = y_coord + x
                # Check neighbors: Left, Top-Left, Top
                if x > 0:  # Left
                    ox, oy = 1.0, 0.0
                    compare_and_update(i, i - 1, ox, oy)
                if y > 0:
                    # Top
                    ox, oy = 0.0, 1.0
                    compare_and_update(i, i - width, ox, oy)
                    if x > 0:  # Top-Left
                        ox, oy = 1.0, 1.0
                        compare_and_update(i, i - width - 1, ox, oy)

        # 2 Pass: Bottom-Right to Top-Left
        for y in range(height - 1, -1, -1):
            y_coord = y * width
            for x in range(width - 1, -1, -1):
                i = y_coord + x
                # Check neighbors: Right, Bottom-Right, Bottom
                if x < width - 1:  # Right
                    ox, oy = -1.0, 0.0
                    compare_and_update(i, i + 1, ox, oy)
                if y < height - 1:
                    # Bottom
                    ox, oy = 0.0, -1.0
                    compare_and_update(i, i + width, ox, oy)
                    if x < width - 1:  # Bottom-Right
                        ox, oy = -1.0, -1.0
                        compare_and_update(i, i + width + 1, ox, oy)

        # 3 Pass: Top-Right to Bottom-Left
        for y in range(height):
            y_coord = y * width
            for x in range(width - 1, -1, -1):
                i = y_coord + x
                # Check neighbors: Right, Top-Right, Top
                if x < width - 1:  # Right
                    ox, oy = -1.0, 0.0
                    compare_and_update(i, i + 1, ox, oy)
                if y > 0:
                    # Top
                    ox, oy = 0.0, 1.0
                    compare_and_update(i, i - width, ox, oy)
                    if x < width - 1:  # Top-Right
                        ox, oy = -1.0, 1.0
                        compare_and_update(i, i - width + 1, ox, oy)

        # 4 Pass: Bottom-Left to Top-Right
        for y in range(height - 1, -1, -1):
            y_coord = y * width
            for x in range(width):
                i = y_coord + x
                # Check neighbors: Left, Bottom, Bottom-Left
                if x > 0:  # Left
                    ox, oy = 1.0, 0.0
                    compare_and_update(i, i - 1, ox, oy)
                if y < height - 1:
                    # Bottom
                    ox, oy = 0.0, -1.0
                    compare_and_update(i, i + width, ox, oy)
                    if x > 0:  # Bottom-Left
                        ox, oy = 1.0, -1.0
                        compare_and_update(i, i + width - 1, ox, oy)

        timings["8SSEDT"] = time.perf_counter() - t0

        # ---------------------------------------------------------
        # BLOCK 4: OUTPUT RENDERING
        # ---------------------------------------------------------
        t0 = time.perf_counter()
        out = bytearray(total_pixels * 4)
        for i in range(total_pixels):
            # Final Euclidean Distance + subpixel tweak
            s_idx = seed_idx[i]
            dist = math.sqrt(grid_dx[i] ** 2 + grid_dy[i] ** 2) + additional_dist[s_idx]
            # Normalize to 0.0 - 1.0 (0.5 is edge)
            if is_inside[i]:
                # temp, we didn't make inside distances yet
                val = 1
            else:
                # val = 0.5 * (1.0 - min(dist, max_range) / max_range)
                val = remap_clamped(dist, 0, max_range + 1, 0.5, 0)

            gray = int(val * 255)
            offset = i * 4
            out[offset] = out[offset + 1] = out[offset + 2] = gray
            out[offset + 3] = 255
        timings["Render"] = time.perf_counter() - t0

        # Create Layer
        new_node = doc.createNode("SDF_8SSEDT", "paintLayer")
        doc.rootNode().addChildNode(new_node, node)
        new_node.setPixelData(bytes(out), 0, 0, width, height)
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
