"""Verification-only geometry/postprocessing; never packaged as a player scaffold."""
import math
import numpy as np


class PlanningGeometry:
    def __init__(self, data, radius, margin):
        self.data = data
        cells = math.ceil((radius+margin)/data.resolution_m)
        h, w = data.grid.shape
        padded = np.pad(data.grid, cells, constant_values=True)
        self.blocked = np.zeros((h, w), dtype=np.bool_)
        for row in range(2*cells+1):
            for col in range(2*cells+1):
                self.blocked |= padded[row:row+h, col:col+w]
        rows, cols = np.nonzero(self.blocked)
        self.lower = data.origin_xy+np.column_stack((cols, rows))*data.resolution_m
        self.upper = self.lower+data.resolution_m
        self.lower = np.nextafter(self.lower, -np.inf)
        self.upper = np.nextafter(self.upper, np.inf)

    def neighbours(self, current):
        row, col = current
        h, w = self.blocked.shape
        for dy, dx in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
            nr, nc = row+dy, col+dx
            if not (0 <= nr < h and 0 <= nc < w) or self.blocked[nr, nc]:
                continue
            if dy and dx and (self.blocked[row, nc] or self.blocked[nr, col]):
                continue
            yield (nr, nc), self.data.resolution_m*math.hypot(dy, dx)

    def clear(self, a, b):
        direction = b-a
        lo = np.zeros(len(self.lower), dtype=np.float64)
        hi = np.ones(len(self.lower), dtype=np.float64)
        possible = np.ones(len(self.lower), dtype=np.bool_)
        for axis in range(2):
            if direction[axis] == 0:
                possible &= (a[axis] >= self.lower[:,axis]) & (a[axis] <= self.upper[:,axis])
            else:
                first = (self.lower[:,axis]-a[axis])/direction[axis]
                last = (self.upper[:,axis]-a[axis])/direction[axis]
                lo = np.maximum(lo, np.minimum(first,last))
                hi = np.minimum(hi, np.maximum(first,last))
        return not bool(np.any(possible & (lo <= hi)))

    def finish(self, parent, start_cell, goal_cell, start, goal):
        cells = [goal_cell]
        while cells[-1] != start_cell:
            cells.append(parent[cells[-1]])
        centres = [self.data.grid_to_world(*cell) for cell in reversed(cells)]
        nodes = [start.copy(), *centres, goal.copy()]
        nodes = [point for index,point in enumerate(nodes) if index == 0 or np.linalg.norm(point-nodes[index-1])>1e-6]
        # Greedy line-of-sight simplification is test code supplied by the
        # reference author, not by the engine. Preserve every corner on sampling.
        simplified = [nodes[0]]
        current = 0
        while current < len(nodes)-1:
            last = len(nodes)-1
            while last > current+1 and not self.clear(nodes[current], nodes[last]):
                last -= 1
            simplified.append(nodes[last])
            current = last
        output = [simplified[0]]
        for a,b in zip(simplified,simplified[1:]):
            count = math.ceil(float(np.linalg.norm(b-a))/.10)
            output.extend(a+(b-a)*(i/count) for i in range(1,count+1))
        return np.asarray(output, dtype=np.float64)
