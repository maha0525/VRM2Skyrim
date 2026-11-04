"""Hidden plates that keep the legs inside a skirt, and side links between its chains.

A skirt is a ring of cloth chains that a VRM lets touch the leg colliders. Without help a
thigh slips between two chains. Each skirt bone carries a hidden FSMP plate (a per-triangle
shape the leg collider surfaces push out of), so the leg pushes the skirt instead, and
neighbouring chains are tied together at each height so the ring keeps its shape.

FSMP hands a triangle's contact to every bone of its three vertices, so a triangle spanning
two bones drags a hip bone with a knee contact; every plate triangle belongs to one bone.
The plate follows the cloth, not the bones: a VRM's front chains may curl between the legs
at knee height (Lucia's) while the cloth hangs in front of them.
"""
import numpy as np

PLATE = 'V2SCollision_SkirtPlate'
# Each bone's strip reaches this share of the way to each neighbouring chain (they overlap 10%).
REACH = .55
# A side link's point may move this many units from rest along each axis; 4 let the knees through.
LINK_SLACK = 2.
# The plate sits this far inside the cloth.
CLOTH_GAP = .5
# Plate points must be this much further from a leg surface at rest than its contact margins.
REST_CLEARANCE = .3
LEG_BONES = ('Thigh', 'Calf')
# A VRM may hang each half of a skirt from its own thigh (Air's); both halves still form the
# one ring around the hips.
HIPS = 'NPC Pelvis [Pelv]'


def segment_distance(point, head, tail):
    point, head = np.asarray(point), np.asarray(head)
    if tail is None:
        return float(np.linalg.norm(point-head))
    axis = np.asarray(tail)-head
    position = np.clip(np.dot(point-head, axis) / max(np.dot(axis, axis), 1e-12), 0, 1)
    return float(np.linalg.norm(point-head-position*axis))


def leg_groups(groups):
    """Collider groups with a collider on a thigh or calf."""
    return sorted(g for g, colliders in groups.items()
                  if any(part in c['bone'] for c in colliders for part in LEG_BONES))


def _head(bones, name):
    return np.asarray(bones[name]['matrix'])[:3, 3]


def _chains(bones, touching):
    """Root-to-leaf paths below the tops of the touching movers that contain one of them."""
    children = {}
    for name, info in bones.items():
        children.setdefault(info['parent'], []).append(name)
    tops = set()
    for name in touching:
        while bones[name]['parent'] in bones:
            name = bones[name]['parent']
        tops.add(name)
    paths = []

    def walk(path):
        kids = [k for k in children.get(path[-1], []) if k in bones]
        if not kids:
            paths.append(path)
        for kid in kids:
            walk(path + [kid])
    for top in sorted(tops):
        walk([top])
    return [p for p in paths if set(p) & set(touching)]


def _polyline(bones, path):
    """Joint points down the chain and the bone carrying each segment; zero-length segments dropped."""
    points, owners = [_head(bones, path[0])], []
    for i, name in enumerate(path):
        if i + 1 < len(path):
            end = _head(bones, path[i+1])
        else:
            tail = bones[name].get('spring_tail')
            previous = next(((points[-1]-points[j]) for j in range(len(points)-2, -1, -1)
                             if np.linalg.norm(points[-1]-points[j]) > .5), None)
            start = _head(bones, name)
            if previous is not None:
                end = start + previous
                # A VRM tail bent far from the chain's direction is not where the cloth goes.
                if tail is not None and np.dot(np.asarray(tail)-start, previous) > \
                        np.cos(np.radians(30))*np.linalg.norm(np.asarray(tail)-start)*np.linalg.norm(previous):
                    end = np.asarray(tail)
            elif tail is not None:
                end = np.asarray(tail)
            else:
                continue
        if np.linalg.norm(end - points[-1]) < .5:
            points[-1] = end
            continue
        points.append(end)
        owners.append(name)
    return np.asarray(points), owners


def _sample(points, owners, height):
    """Point at a height and the bone whose segment ends at or below it; None above or below the chain."""
    for a, b, owner in zip(points[:-1], points[1:], owners):
        # A height on a joint belongs to the segment that ends there (the median height of
        # a ring is only equal to its joints within rounding).
        if a[2] > height + .05 and height >= b[2] - .05:
            t = (a[2]-height)/(a[2]-b[2])
            return a + t*(b-a), owner
    return None


def _angle_gap(angles, towards):
    return abs((angles-towards+np.pi) % (2*np.pi)-np.pi)


def skirt_plate(bones, touching, samples, sample_weights, legs, margin, cloth_triangles=()):
    """Plate and side links for every ring of skirt chains, or None without a ring.

    bones: the system's physics bones; touching: movers the VRM lets touch a leg;
    samples/sample_weights: the garment's skinned vertices per bone (world, rest);
    legs: the leg colliders (world, rest); margin: the triangle margin of the plate and legs;
    cloth_triangles: the garment's triangles as (3x3 world corners, the bones weighted over .3 at
    each corner), so cloth whose few vertices all sit near the chains still counts between them.
    Angles are taken around the actor's origin, which the converter stands the hips over.
    Returns {'vertices', 'triangles', 'weights': {bone: [(vertex, 1.)]}, 'links': [(a, b, point)],
    'rings': [{'anchor', 'chains', 'heights', 'bands', 'joined'}], 'left_out': triangles touching a leg}.
    """
    def leg_distance(point):
        return min(segment_distance(point, leg['head'], leg['tail']) - leg['radius'] for leg in legs)

    def touches(corners):
        a, b, e = corners
        for u in np.linspace(0, 1, 6):
            for v in np.linspace(0, 1-u, max(2, int(6*(1-u)))):
                if leg_distance(a + u*(b-a) + v*(e-a)) < 2*margin:
                    return True
        return False

    rings = {}
    for path in _chains(bones, touching):
        anchor = bones[path[0]]['parent']
        rings.setdefault(HIPS if any(part in anchor for part in LEG_BONES) else anchor, []).append(path)
    vertices, weights, triangles, links, summary, left_out = [], {}, [], [], [], 0
    for anchor, ring_paths in sorted(rings.items()):
        lines = [line for line in (_polyline(bones, p) for p in ring_paths) if len(line[1])]
        if not lines:
            continue
        # Common heights: the joint heights below the top joint, taken from the longest chains.
        longest = max(len(owners) for _, owners in lines)
        heights = np.median([points[1:, 2] for points, owners in lines if len(owners) == longest], axis=0)
        columns = []
        for points, owners in lines:
            column = [_sample(points, owners, h) for h in heights]
            if sum(c is not None for c in column) >= 2:
                columns.append(column)
        if len(columns) < 3:
            continue
        # Chains start in ring order at the top; lower down some cross or converge.
        columns.sort(key=lambda column: np.arctan2(*next(c[0] for c in column if c is not None)[:2]))
        count = len(columns)
        ring_bones = {n for p in ring_paths for n in p}
        cloth = np.concatenate([np.asarray(samples[n])[np.asarray(sample_weights[n]) > .3]
                                for n in sorted(ring_bones) if n in samples])
        cloth_angle = np.arctan2(cloth[:, 0], cloth[:, 1])
        faces = np.asarray([corners for corners, owners in cloth_triangles
                            if all(set(o) & ring_bones for o in owners)]).reshape(-1, 3, 3)
        face_angle = np.arctan2(faces[:, :, 0], faces[:, :, 1])
        radius = np.hypot(cloth[:, 0], cloth[:, 1])
        for column in columns:
            for k, entry in enumerate(column):
                if entry is None:
                    continue
                point, owner = entry
                towards = np.arctan2(point[0], point[1])
                near = _angle_gap(cloth_angle, towards) < np.radians(6)
                if not near.any():
                    continue
                # Below the hem the plate carries the hem's radius straight down.
                level = near & (abs(cloth[:, 2]-point[2]) < 2)
                if not level.any():
                    level = near & (cloth[:, 2] < cloth[near, 2].min() + 2)
                r = radius[level].min() - CLOTH_GAP
                # A tight skirt sits within the contact margin of the legs at rest; keep the
                # plate just clear of them rather than leaving the band without plate.
                while r < 40 and leg_distance([r*np.sin(towards), r*np.cos(towards), point[2]]) < \
                        2*margin + REST_CLEARANCE:
                    r += .1
                column[k] = (np.array([r*np.sin(towards), r*np.cos(towards), point[2]]), owner)

        def cloth_between(a, b):
            """Whether the ring's cloth reaches the direction halfway between two chain points.

            A cloth vertex near that direction, or a cloth triangle across it: a low-poly skirt
            (Air's) has no vertex there, but its triangles span the gap a slit leaves open.
            """
            middle = (a+b)/2
            towards = np.arctan2(middle[0], middle[1])
            near = (abs(cloth[:, 2]-middle[2]) < 3) & (_angle_gap(cloth_angle, towards) < np.radians(5))
            side = (face_angle-towards+np.pi) % (2*np.pi)-np.pi
            across = (side.min(1) < 0) & (side.max(1) > 0) & (side.max(1)-side.min(1) < np.pi/2) & \
                (faces[:, :, 2].min(1) < middle[2]+3) & (faces[:, :, 2].max(1) > middle[2]-3)
            return bool(near.any() or across.any())
        joined = set()  # (column, neighbour, band); an open cloak front or a robe's slit stays apart
        for c in range(count):
            d = (c+1) % count
            for k in range(len(heights)-1):
                corners = [columns[c][k], columns[c][k+1], columns[d][k], columns[d][k+1]]
                if all(x is not None for x in corners) and \
                        cloth_between((corners[0][0]+corners[1][0])/2, (corners[2][0]+corners[3][0])/2):
                    joined |= {(c, d, k), (d, c, k)}
        summary.append({'anchor': anchor, 'chains': count, 'heights': np.round(heights, 2).tolist(),
                        'bands': count*(len(heights)-1), 'joined': len(joined)//2})
        for c in range(count):
            for k in range(len(heights)-1):
                top, bottom = columns[c][k], columns[c][k+1]
                if top is None or bottom is None:
                    continue
                owner = bottom[1]
                if not bones[owner]['dynamic']:
                    continue
                for n in ((c-1) % count, (c+1) % count):
                    if (c, n, k) not in joined:
                        continue
                    quad = [top[0], bottom[0], bottom[0] + REACH*(columns[n][k+1][0]-bottom[0]),
                            top[0] + REACH*(columns[n][k][0]-top[0])]
                    # Push a strip that grazes a leg at rest outward until it is clear, so a
                    # tight skirt keeps its plate where the thigh will push.
                    for _ in range(60):
                        if not touches(quad[:3]) and not touches([quad[0], quad[2], quad[3]]):
                            break
                        quad = [np.array([q[0], q[1], 0])*(1+.1/np.hypot(q[0], q[1])) + [0, 0, q[2]] for q in quad]
                    start = len(vertices)
                    vertices.extend(tuple(map(float, q)) for q in quad)
                    weights.setdefault(owner, []).extend((start+i, 1.) for i in range(4))
                    for tri in ((start, start+1, start+2), (start, start+2, start+3)):
                        a, b, e = (np.asarray(vertices[i]) for i in tri)
                        if np.dot(np.cross(b-a, e-a)[:2], ((a+b+e)/3)[:2]) > 0:  # face the legs inside
                            tri = (tri[0], tri[2], tri[1])
                        if touches([np.asarray(vertices[i]) for i in tri]):
                            left_out += 1
                        else:
                            triangles.append(tri)
        for c, d in sorted({(c, d) for c, d, _ in joined if c < d}):
            for k in range(len(heights)):
                if (c, d, k) not in joined and (c, d, k-1) not in joined:
                    continue
                a, b = columns[c][k][1], columns[d][k][1]
                if a != b and bones[a]['dynamic'] and bones[b]['dynamic']:
                    links.append((a, b, (columns[c][k][0]+columns[d][k][0])/2))
    if not triangles:
        return None
    # Drop the vertices of strips whose triangles were all left out.
    used = sorted({v for t in triangles for v in t})
    remap = {v: i for i, v in enumerate(used)}
    weights = {b: [(remap[v], w) for v, w in pairs if v in remap] for b, pairs in sorted(weights.items())}
    return {'vertices': [vertices[v] for v in used], 'triangles': [tuple(remap[v] for v in t) for t in triangles],
            'weights': {b: pairs for b, pairs in weights.items() if pairs}, 'links': links,
            'rings': summary, 'left_out': left_out}
