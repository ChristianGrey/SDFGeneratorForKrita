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
            "distance_map", "Generate True Dual SDF", "tools/scripts"
        )
        action.triggered.connect(self.run)

    def compute_distance_field(self, width, height, is_seed, weight_sq, inf):
        """
        Computes Euclidean Distance Transform.
        is_seed: bytearray (1 if pixel is a source, 0 otherwise)
        weight_sq: float array (initial squared distance for seeds)
        """
        # Step 1: Vertical Pass (Meijster Phase 1)
        # Calculates squared vertical distance to nearest seed in column
        g = array("f", [inf] * (width * height))

        for x in range(width):
            # Scan Down
            last_dist = inf
            for y in range(height):
                idx = y * width + x
                if is_seed[idx]:
                    g[idx] = weight_sq[idx]
                else:
                    # If not a seed, it's 1 unit further from the seed above it
                    # Note: We use Manhattan here temporarily then square properly
                    # because it's a 1D column.
                    pass

            # Simplified Vertical: find nearest seed y_i for each y
            # For 1D, we can just find the nearest seed index
            seeds_in_col = [y for y in range(height) if is_seed[y * width + x]]
            if not seeds_in_col:
                continue

            curr_seed_idx = 0
            for y in range(height):
                # Move to the closest seed (either the one before or after current y)
                while curr_seed_idx + 1 < len(seeds_in_col) and abs(
                    seeds_in_col[curr_seed_idx + 1] - y
                ) < abs(seeds_in_col[curr_seed_idx] - y):
                    curr_seed_idx += 1

                s_y = seeds_in_col[curr_seed_idx]
                dist_vert = abs(y - s_y)
                # Correct Euclidean: (y - y_i)^2 + initial_weight^2
                g[y * width + x] = (
                    dist_vert + math.sqrt(weight_sq[s_y * width + x])
                ) ** 2

        # Step 2: Horizontal Pass (Meijster Phase 2 - Parabolic)
        dist_out = array("f", [inf] * (width * height))
        for y in range(height):
            row_off = y * width
            s = [0] * width
            t = [0.0] * (width + 1)
            t[0], t[1] = -inf, inf
            q = 0
            for u in range(1, width):
                while q >= 0:
                    f_u, f_s = g[row_off + u], g[row_off + s[q]]
                    if f_u >= inf:
                        break
                    inv_denom = 1.0 / (2 * (u - s[q]))
                    inter_x = ((f_u + u**2) - (f_s + s[q] ** 2)) * inv_denom
                    if inter_x <= t[q]:
                        q -= 1
                    else:
                        q += 1
                        s[q], t[q], t[q + 1] = u, inter_x, inf
                        break

            for u in range(width):
                while t[q] > u and q > 0:
                    q -= 1  # Safety backtrack
                while t[q + 1] < u:
                    q += 1
                dx = u - s[q]
                dist_out[row_off + u] = math.sqrt(dx**2 + g[row_off + s[q]])
        return dist_out

    def run(self):
        doc = Krita.instance().activeDocument()
        if not doc:
            return
        width, height = doc.width(), doc.height()
        active_layer = doc.activeNode()

        max_range, ok = QInputDialog.getInt(
            None, "SDF Settings", "Max Pixel Range:", 64, 1, 1024
        )
        if not ok:
            return

        pixels = bytearray(active_layer.pixelData(0, 0, width, height))
        inf = float(width**2 + height**2)

        # Separate seeds for Outside (to find distance to white)
        # and Inside (to find distance to black)
        is_inside = bytearray(width * height)
        weight_sq_out = array("f", [0.0] * (width * height))
        weight_sq_in = array("f", [0.0] * (width * height))

        is_seed_ext = bytearray(width * height)  # Seeds for exterior pass
        is_seed_int = bytearray(width * height)  # Seeds for interior pass

        for i in range(width * height):
            v = pixels[i * 4 + 2] / 255.0  # Red channel
            if v > 0.5:
                is_inside[i] = 1
                is_seed_ext[i] = 1  # White pixels are seeds for the outside world
                weight_sq_out[i] = ((1.0 - v) * 1.0) ** 2
            else:
                is_inside[i] = 0
                is_seed_int[i] = 1  # Black pixels are seeds for the inside world
                weight_sq_in[i] = (v * 1.0) ** 2

        # Run Passes
        dist_ext = self.compute_distance_field(
            width, height, is_seed_ext, weight_sq_out, inf
        )
        dist_int = self.compute_distance_field(
            width, height, is_seed_int, weight_sq_in, inf
        )

        # Composite Result
        res = bytearray(width * height * 4)
        for i in range(width * height):
            if is_inside[i]:
                # Positive distance (0.5 to 1.0)
                d = dist_int[i]
                f = 0.5 + 0.5 * min(1.0, d / max_range)
            else:
                # Negative distance (0.5 down to 0.0)
                d = dist_ext[i]
                f = 0.5 - 0.5 * min(1.0, d / max_range)

            gray = int(f * 255)
            res[i * 4] = res[i * 4 + 1] = res[i * 4 + 2] = gray
            res[i * 4 + 3] = 255

        new_layer = doc.createNode("SDF_Final", "paintLayer")
        doc.rootNode().addChildNode(new_layer, None)
        new_layer.setPixelData(bytes(res), 0, 0, width, height)
        doc.refreshProjection()


# Krita.instance().addExtension(SDFGenerator(Krita.instance()))
