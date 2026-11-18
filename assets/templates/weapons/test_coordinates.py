import math
import unittest
import numpy as np
from numpy.typing import NDArray
from tankbot import Pose2D
from tankbot.transforms import validate_se3
from perception.transforms import radar_to_map


class CoordinateTest(unittest.TestCase):
    def test_rotated_robot(self) -> None:
        matrix: NDArray[np.float64] = validate_se3(radar_to_map(Pose2D(1.0, 3.0, math.pi/2)), tolerance=1e-8)
        point: NDArray[np.float64] = matrix @ np.array([2.0, 0.0, 0.0, 1.0])
        np.testing.assert_allclose(point, [1.0, 5.0, 0.0, 1.0], atol=1e-8)

    def test_translation_and_direction(self) -> None:
        matrix: NDArray[np.float64] = validate_se3(radar_to_map(Pose2D(2.0, -1.0, 0.0)), tolerance=1e-8)
        np.testing.assert_allclose(matrix @ np.array([1.0, 2.0, 0.0, 1.0]), [3.0, 1.0, 0.0, 1.0])
        np.testing.assert_allclose(matrix @ np.array([1.0, 2.0, 0.0, 0.0]), [1.0, 2.0, 0.0, 0.0])
