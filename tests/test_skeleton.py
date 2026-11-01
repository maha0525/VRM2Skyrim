"""Custom skeleton contract: animated bone-local transforms land on the custom joints."""
from pathlib import Path
import tempfile
import unittest

import numpy as np

from custom_skeleton import NifFile, create_skeleton, matrix, rigid_buffer


def placed(translation):
    result = np.eye(4)
    result[:3, 3] = translation
    return result


class SkeletonTests(unittest.TestCase):
    def build(self, directory, animated):
        source, target = Path(directory) / 'skeleton.nif', Path(directory) / 'private.nif'
        with NifFile() as file:
            file.initialize('SKYRIMSE', str(source))
            hand = file.add_node('Hand', rigid_buffer(placed([0, 0, 10])), file.rootNode)
            file.add_node('Finger', rigid_buffer(placed([0, 0, 2])), hand)
            file.save()
        create_skeleton(source, target, {'Finger': [0, 0, 14]}, None, animated)
        return target

    def test_animation_translation_keeps_the_custom_joint(self):
        # Female fingers: the NIF says 2 units, every HKX frame writes 3.
        with tempfile.TemporaryDirectory() as directory, NifFile(str(self.build(directory, {'Finger': [0, 0, 3]}))) as file:
            finger = file.nodes['Finger']
            np.testing.assert_allclose(matrix(finger.global_transform)[:3, 3], [0, 0, 14], atol=1e-4)
            np.testing.assert_allclose(matrix(finger.transform)[:3, 3], [0, 0, 3], atol=1e-5)
            # The animation replaces only the bone's own local transform; the proxy above it is fixed.
            runtime = matrix(finger.parent.global_transform) @ placed([0, 0, 3])
            np.testing.assert_allclose(runtime[:3, 3], [0, 0, 14], atol=1e-4)

    def test_matching_animation_keeps_the_nif_translation(self):
        with tempfile.TemporaryDirectory() as directory, NifFile(str(self.build(directory, {'Finger': [0, 0, 2]}))) as file:
            np.testing.assert_allclose(matrix(file.nodes['Finger'].transform)[:3, 3], [0, 0, 2], atol=1e-5)
            np.testing.assert_allclose(matrix(file.nodes['Finger'].global_transform)[:3, 3], [0, 0, 14], atol=1e-4)


if __name__ == '__main__':
    unittest.main()
