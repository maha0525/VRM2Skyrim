"""Read back original skin retained inside standard-slot clothing."""
from contextlib import ExitStack
from itertools import permutations
import json
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import maximum_bipartite_matching


def validate_skin_triangles(expected, actual, tolerance=.001):
    """One-to-one face matching, robust to float32 seams without rounding bins."""
    expected, actual = np.asarray(expected), np.asarray(actual)
    if len(expected) != len(actual) or not len(actual):
        raise ValueError(f'Standard clothing skin face count: expected={len(expected)}, actual={len(actual)}')
    tree = cKDTree(expected.mean(axis=1))
    neighbors = tree.query_ball_point(actual.mean(axis=1), tolerance)
    orders = np.asarray(list(permutations(range(3))))
    rows, columns = [], []
    for index, candidates in enumerate(neighbors):
        for candidate in candidates:
            reference = expected[candidate][orders]
            if np.any(np.all(np.linalg.norm(reference-actual[index], axis=2) <= tolerance, axis=1)):
                rows.append(index)
                columns.append(candidate)
    graph = csr_matrix((np.ones(len(rows), dtype=bool), (rows, columns)), shape=(len(actual), len(expected)))
    matching = maximum_bipartite_matching(graph, perm_type='column')
    if np.any(matching < 0):
        raise ValueError(f'Standard clothing lost or duplicated original skin faces: unmatched={np.sum(matching < 0)}')


def validate_clothing_skin(output, settings):
    from custom_skeleton import NifFile
    output = Path(output)
    root = output/'mod/meshes'/settings.asset_dir
    manifest = json.loads((output/'appearance.json').read_text(encoding='utf8'))
    result = []
    for part in manifest['components']:
        if not part.get('retained_skin'):
            continue
        files = (['body.nif', 'hands.nif', 'feet.nif'] if part.get('item_kind') == 'full' and part['slot'] == 32
                 else ['hands.nif' if part['slot'] == 33 else 'feet.nif' if part['slot'] == 37 else 'body.nif'])
        slots = set(part.get('slots', [part['slot']]))
        references = {}
        expected = {}
        with ExitStack() as stack:
            sources = [stack.enter_context(NifFile(str(root/file))) for file in files]
            for shape in [shape for source in sources for shape in source.shapes]:
                if not set(p.id for p in shape.partitions).issubset(slots):
                    continue
                key = shape.textures['Diffuse']
                points = np.column_stack((shape.verts, shape.uvs))
                references.setdefault(key, []).append((points, np.asarray(shape.normals), shape))
                expected.setdefault(key, []).extend(points[np.asarray(shape.tris)])
            trees = {key: (cKDTree(np.concatenate([p for p, _, _ in values])),
                           np.concatenate([n for _, n, _ in values])) for key, values in references.items()}
            actual = {}
            maximum_distance = 0.
            with NifFile(str(root/part['file'])) as clothing:
                for shape in clothing.shapes:
                    if not shape.name.startswith('V2SClothingSkin_'):
                        continue
                    key = shape.textures['Diffuse']
                    points = np.column_stack((shape.verts, shape.uvs))
                    tree, normals = trees[key]
                    distances, indices = tree.query(points, k=min(12, len(normals)))
                    if distances.ndim == 1:
                        distances, indices = distances[:, None], indices[:, None]
                    if distances[:, 0].max() > .001:
                        raise ValueError('Standard clothing moved original skin/UVs')
                    maximum_distance = max(maximum_distance, float(distances[:, 0].max()))
                    observed = np.asarray(shape.normals)[:, None, :]
                    denominator = np.linalg.norm(observed, axis=2)*np.linalg.norm(normals[indices], axis=2)
                    cosine = (observed*normals[indices]).sum(axis=2)/np.maximum(denominator, 1e-12)
                    cosine[distances > .001] = -2
                    if cosine.max(axis=1).min() < .997:
                        raise ValueError('Standard clothing changed original skin normals')
                    sums = np.zeros(len(points))
                    counts = np.zeros(len(points), dtype=int)
                    for pairs in shape.bone_weights.values():
                        for vertex, weight in pairs:
                            sums[vertex] += weight
                            counts[vertex] += 1
                    if np.any(counts == 0) or np.any(counts > 4) or np.max(np.abs(sums-1)) > .015:
                        raise ValueError('Standard clothing has invalid retained skin weights')
                    actual.setdefault(key, []).extend(points[np.asarray(shape.tris)])
            if set(actual) != set(expected):
                raise ValueError('Standard clothing skin material/face sets changed: '+part['id'])
            for key in expected:
                validate_skin_triangles(expected[key], actual[key])
        result.append({'garment': part['id'], 'original_skin_faces': sum(len(faces) for faces in actual.values()),
                       'max_vertex_uv_distance': maximum_distance, 'preserved': True})
    return result
