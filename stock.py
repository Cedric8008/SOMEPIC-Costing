import FreeCAD
import Part


class StockCreator:
    """
    Création de bruts simples (bloc ou cylindre).
    Ce module NE DOIT PAS importer stock_intelligent (sinon circular import).
    """

    def __init__(self, shape):
        self.shape = shape
        self.doc = FreeCAD.ActiveDocument

    # ================================================================
    # 🟩  Création d'un bloc rectangulaire
    # ================================================================
    def create_block(
        self,
        margin_x_minus,
        margin_x_plus,
        margin_y_minus,
        margin_y_plus,
        margin_z_minus,
        margin_z_plus,
        transparency=70,
    ):
        bb = self.shape.BoundBox

        # nouvelles limites
        x0 = bb.XMin - margin_x_minus
        x1 = bb.XMax + margin_x_plus
        y0 = bb.YMin - margin_y_minus
        y1 = bb.YMax + margin_y_plus
        z0 = bb.ZMin - margin_z_minus
        z1 = bb.ZMax + margin_z_plus

        dx = x1 - x0
        dy = y1 - y0
        dz = z1 - z0

        # création du bloc
        box = Part.makeBox(dx, dy, dz)
        box.translate(FreeCAD.Vector(x0, y0, z0))

        obj = self.doc.addObject("Part::Feature", "StockBlock")
        obj.Shape = box
        obj.ViewObject.Transparency = transparency
        self.doc.recompute()

        return obj

    # ================================================================
    # 🟦  Création automatique d'un cylindre (surépaisseurs)
    # ================================================================
    def create_cylinder(
        self,
        margin_x_minus,
        margin_x_plus,
        margin_y_minus,
        margin_y_plus,
        margin_z_minus,
        margin_z_plus,
        transparency=70,
    ):
        bb = self.shape.BoundBox

        # centre de la pièce
        cx = (bb.XMin + bb.XMax) / 2.0
        cy = (bb.YMin + bb.YMax) / 2.0
        cz = (bb.ZMin + bb.ZMax) / 2.0

        # rayon = diagonale XY/2 + marges max
        rx = (bb.XMax - bb.XMin) / 2.0 + max(margin_x_minus, margin_x_plus)
        ry = (bb.YMax - bb.YMin) / 2.0 + max(margin_y_minus, margin_y_plus)
        radius = max(rx, ry)

        # hauteur = dimension Z + surépaisseurs
        height = (bb.ZMax - bb.ZMin) + margin_z_minus + margin_z_plus

        # on centre le cylindre par rapport à la pièce en Z
        z0 = cz - height / 2.0

        cyl = Part.makeCylinder(radius, height)
        cyl.translate(FreeCAD.Vector(cx, cy, z0))

        obj = self.doc.addObject("Part::Feature", "StockCylinder")
        obj.Shape = cyl
        obj.ViewObject.Transparency = transparency
        self.doc.recompute()

        return obj

    # ================================================================
    # 🟦  Création manuelle d’un cylindre (diamètre + longueur)
    #     → axe Z, centré sur la pièce. Orientation gérée ensuite.
    # ================================================================
    def create_cylinder_manual(self, diameter, length, transparency=70):
        bb = self.shape.BoundBox

        # centre de la pièce
        cx = (bb.XMin + bb.XMax) / 2.0
        cy = (bb.YMin + bb.YMax) / 2.0
        cz = (bb.ZMin + bb.ZMax) / 2.0

        radius = diameter / 2.0

        # cylindre vertical (axe Z) centré sur la pièce
        z0 = cz - length / 2.0
        cyl = Part.makeCylinder(radius, length)
        cyl.translate(FreeCAD.Vector(cx, cy, z0))

        obj = self.doc.addObject("Part::Feature", "StockCylinder")
        obj.Shape = cyl
        obj.ViewObject.Transparency = transparency
        self.doc.recompute()

        return obj
