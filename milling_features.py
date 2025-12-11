import FreeCAD
import Part
import math

# Axes
XAXIS = FreeCAD.Vector(1, 0, 0)
YAXIS = FreeCAD.Vector(0, 1, 0)
ZAXIS = FreeCAD.Vector(0, 0, 1)

TOL_DIR = 0.1
TOL_DIST = 0.5
TOL_RADIUS = 0.2


# ─────────────────────────────────────────────────────────────
#  UTILS
# ─────────────────────────────────────────────────────────────

def is_parallel(v1, v2, tol=TOL_DIR):
    v1n = v1.normalize()
    v2n = v2.normalize()
    return abs(abs(v1n.dot(v2n)) - 1) <= tol


def is_horizontal(normal):
    return is_parallel(normal, ZAXIS)


def is_vertical(normal):
    return is_parallel(normal, XAXIS) or is_parallel(normal, YAXIS)


# ─────────────────────────────────────────────────────────────
#  DETECTION PLANS HORIZONTAUX
# ─────────────────────────────────────────────────────────────

class PlaneFeature:
    def __init__(self, faces, z, area, kind):
        self.faces = faces
        self.z = z
        self.area = area
        self.kind = kind


def detect_horizontal_planes(shape):
    planes = {}
    for face in shape.Faces:
        if isinstance(face.Surface, Part.Plane):
            n = face.normalAt(0.5, 0.5)
            if is_horizontal(n):
                bb = face.BoundBox
                z = round(bb.ZMax, 3)
                if z not in planes:
                    planes[z] = {"faces": [], "area": 0}
                planes[z]["faces"].append(face)
                planes[z]["area"] += face.Area

    out = []
    for z, d in planes.items():
        kind = "outer_top" if z > 0 else "outer_bottom"
        out.append(PlaneFeature(d["faces"], z, d["area"], kind))
    return out


# ─────────────────────────────────────────────────────────────
#  DETECTION FLANCS VERTICAUX
# ─────────────────────────────────────────────────────────────

class VerticalFlank:
    def __init__(self, faces, normal, area):
        self.faces = faces
        self.normal = normal
        self.area = area


def detect_vertical_flanks(shape):
    clusters = []

    for face in shape.Faces:
        if isinstance(face.Surface, Part.Plane):
            n = face.normalAt(0.5, 0.5)
            if is_vertical(n):
                added = False
                for c in clusters:
                    if is_parallel(n, c.normal):
                        c.faces.append(face)
                        c.area += face.Area
                        added = True
                        break

                if not added:
                    clusters.append(VerticalFlank([face], n, face.Area))

    return clusters


# ─────────────────────────────────────────────────────────────
#  DETECTION TROUS CYLINDRIQUES (corrigée)
# ─────────────────────────────────────────────────────────────

class CylindricalHole:
    def __init__(self, faces, center, radius, ztop, zbottom, kind):
        self.faces = faces
        self.center = center
        self.radius = radius
        self.ztop = ztop
        self.zbottom = zbottom
        self.kind = kind


def detect_cylindrical_holes(shape):
    raw = []

    for face in shape.Faces:
        surf = face.Surface

        if isinstance(surf, Part.Cylinder):

            # Axe ≈ vertical
            if not is_parallel(surf.Axis, ZAXIS):
                continue

            # IGNORER LES CHANFREINS autour des trous
            if face.Area < 30:   # seuil très efficace pour virer chanfreins
                continue

            bb = face.BoundBox
            center = bb.Center

            cx = round(center.x, 1)
            cy = round(center.y, 1)

            r = round(surf.Radius, 3)

            raw.append({
                "face": face,
                "cx": cx,
                "cy": cy,
                "radius": r,
                "ztop": round(bb.ZMax, 3),
                "zbottom": round(bb.ZMin, 3)
            })

    # ─────────────── Fusion des cylindres correspondant au même trou ───────────────
    holes = []
    used = [False] * len(raw)
    XY_TOL = 0.2
    R_TOL = 0.2

    for i, h in enumerate(raw):
        if used[i]:
            continue

        faces = [h["face"]]
        cx, cy = h["cx"], h["cy"]
        r = h["radius"]
        ztop = h["ztop"]
        zbottom = h["zbottom"]

        used[i] = True

        for j in range(i + 1, len(raw)):
            if used[j]:
                continue
            hj = raw[j]

            if (
                abs(hj["cx"] - cx) <= XY_TOL and
                abs(hj["cy"] - cy) <= XY_TOL and
                abs(hj["radius"] - r) <= R_TOL
            ):
                faces.append(hj["face"])
                used[j] = True
                ztop = max(ztop, hj["ztop"])
                zbottom = min(zbottom, hj["zbottom"])

        kind = "blind_from_bottom"

        holes.append(
            CylindricalHole(
                faces,
                FreeCAD.Vector(cx, cy, 0),
                r,
                ztop,
                zbottom,
                kind
            )
        )

    return holes


# ─────────────────────────────────────────────────────────────
#  STRUCTURE DE RESULTATS
# ─────────────────────────────────────────────────────────────

class MillingFeatures:
    def __init__(self, planes, flanks, holes):
        self.planes = planes
        self.flanks = flanks
        self.holes = holes


# ─────────────────────────────────────────────────────────────
#  FONCTION PRINCIPALE
# ─────────────────────────────────────────────────────────────

def detect_milling_features(shape):
    planes = detect_horizontal_planes(shape)
    flanks = detect_vertical_flanks(shape)
    holes = detect_cylindrical_holes(shape)
    return MillingFeatures(planes, flanks, holes)


# ─────────────────────────────────────────────────────────────
#  DEBUG
# ─────────────────────────────────────────────────────────────

def debug_detect_features():
    doc = FreeCAD.ActiveDocument
    if not doc:
        print("Aucun document ouvert.")
        return

    shape_obj = None

    # Objet sélectionné
    try:
        import FreeCADGui
        sel = FreeCADGui.Selection.getSelection()
        if sel:
            shape_obj = sel[0]
    except:
        pass

    # Sinon premier solide
    if not shape_obj:
        for o in doc.Objects:
            if hasattr(o, "Shape") and o.Shape.Solids:
                shape_obj = o
                break

    if not shape_obj:
        print("Aucun solide trouvé.")
        return

    shape = shape_obj.Shape
    feats = detect_milling_features(shape)

    print("\n=== FEATURES FRAISAGE DÉTECTÉES ===")
    print("Faces planes horizontales :", len(feats.planes))
    print("Flancs verticaux regroupés :", len(feats.flanks))
    print("Trous cylindriques verticaux :", len(feats.holes))
    print("Chanfreins détectés : ignorés pour les trous\n")

    # Plans
    for i, p in enumerate(feats.planes, 1):
        print(f"[Plan {i}] Z={p.z}, Aire={round(p.area,1)} mm²")

    # Trous
    for i, h in enumerate(feats.holes, 1):
        print(f"[Trou {i}] Ø={2*h.radius} mm, XY=({h.center.x},{h.center.y}), "
              f"Ztop={h.ztop}, Zbottom={h.zbottom}, type={h.kind}")
