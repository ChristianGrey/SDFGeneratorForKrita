from krita import Krita, Extension
from PyQt5.QtWidgets import QInputDialog,QMessageBox
import math, time
from array import array

class SDFGenerator(Extension):
    def __init__(self, parent):
        super().__init__(parent)

    def setup(self):
        pass

    def createActions(self, window):
        action = window.createAction("distance_map", "Generate Distance Map", "tools/scripts")
        action.triggered.connect(self.run)

    def run(self):
        app = Krita.instance()
        doc = app.activeDocument()
        if not doc:
            return
        node = doc.activeNode()
        if not node:
            return

        w, h = doc.width(), doc.height()
        ok = True
        RANGE, ok = QInputDialog.getInt(None, "Distance Map Range",
                                        "Max range in pixels (clamps distances):", 50, 1, max(w, h), 1)
        if not ok:
            return

        timings = {}

        # Step 0: fetch pixels
        t0 = time.perf_counter()
        pixelData = node.pixelData(0, 0, w, h)
        data = bytearray(pixelData)
        timings["fetch pixels"] = time.perf_counter() - t0

        # Step 1: classify pixels
        t0 = time.perf_counter()
        mask = bytearray(w*h)        # 0=black/transparent, 1=white
        seed_white = bytearray(w*h)
        seed_black = bytearray(w*h)
        multipliers = array('f', [0.0] * (w*h))

        for i in range(w*h):
            r, g, b, a = data[i*4:i*4+4]
            if a < 127:
                mask[i] = 0
                seed_black[i] = 1
            else:
                lum = 0.299*r + 0.587*g + 0.114*b
                if lum > 127:
                    mask[i] = 1
                    seed_white[i] = 1
                    multipliers[i] = 1 - ((lum - 128) / 127)

                else:
                    mask[i] = 0
                    seed_black[i] = 1
                    multipliers[i] = lum / 127
        timings["classify"] = time.perf_counter() - t0

        # Step 2: find border pixels
        t0 = time.perf_counter()
        ortho = [(-1,0),(1,0),(0,-1),(0,1)]
        border_pixels = []
        for y in range(h):
            for x in range(w):
                idx = y*w + x
                if multipliers[idx] > 0: 
                    border_pixels.append((x, y))# if mask[idx] != 1:
                #     continue
                # if any(0 <= x+dx < w and 0 <= y+dy < h and mask[(y+dy)*w + (x+dx)] == 0 for dx, dy in ortho):
                #     border_pixels.append((x, y))
        timings["find borders"] = time.perf_counter() - t0

        # Step 3: precompute distance mask
        t0 = time.perf_counter()
        size = 2*RANGE + 1
        dist_mask = array('f', (0.0,) * (size*size))
        for dy in range(-RANGE, RANGE+1):
            for dx in range(-RANGE, RANGE+1):
                dist_mask[(dy+RANGE)*size + (dx+RANGE)] = math.hypot(dx, dy)
        timings["build mask"] = time.perf_counter() - t0

        # Step 4: stamp distances
        t0 = time.perf_counter()
        Distance = array('f', [float('inf')] * (w*h))
        offsets = [(dx, dy, dist_mask[(dy+RANGE)*size + (dx+RANGE)]) for dy in range(-RANGE,RANGE+1) for dx in range(-RANGE,RANGE+1)]
        for bx, by in border_pixels:
            bidx = by*w + bx
            # Sub-pixel correction: 
            # A multiplier of 1.0 means the edge is at the center (dist 0)
            # A multiplier of 0.0 means the edge is 1 full pixel away.
            subpixel_correction = (1.0 - multipliers[bidx])

            for dx, dy, d in offsets:
                nx, ny = bx+dx, by+dy
                if 0 <= nx < w and 0 <= ny < h:
                    nidx = ny*w + nx

                    adjusted_dist = d + subpixel_correction

                    if adjusted_dist < Distance[nidx]:
                        Distance[nidx] = adjusted_dist

                    # if d < Distance[nidx]:
                    #     # use multipliers here somehow
                    #     Distance[nidx] = d
        timings["apply mask"] = time.perf_counter() - t0

        # Step 5: render output
        t0 = time.perf_counter()
        out = bytearray(len(data))
        for idx in range(w*h):
            if seed_white[idx]:
                d = min(Distance[idx], RANGE)
                val = 0.5 + 0.5 * (d / RANGE)       # white -> 1.0
            elif seed_black[idx]:
                d = min(Distance[idx], RANGE)
                val = 0.5 * max(0.0, 1.0 - d / RANGE)  # black -> 0.0
            else:
                val = 0.0
            gray = max(0, min(255, int(val*255)))
            off = idx*4
            out[off]   = gray
            out[off+1] = gray
            out[off+2] = gray
            out[off+3] = 255
        timings["render"] = time.perf_counter() - t0

        # Step 6: create layer
        t0 = time.perf_counter()
        new_node = doc.createNode("SDF", "paintLayer")
        doc.rootNode().addChildNode(new_node, node)
        new_node.setPixelData(bytes(out), 0, 0, w, h)
        doc.refreshProjection()
        timings["create layer"] = time.perf_counter() - t0

        # Report timings
        msg = "\n".join([f"{step}: {ms*1000:.2f} ms" for step, ms in timings.items()])
        print("[SDF timings]\n" + msg)
        QMessageBox.information(None, "SDF timings", msg)


#Krita.instance().addExtension(SDFGenerator(Krita.instance()))
