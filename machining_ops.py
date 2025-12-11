import math

# ================================================================
# MODULE USINAGE — CALCUL DES VOLUMES SELON L’OPÉRATION
# ================================================================

class MachiningOperation:
    """Structure simple contenant les infos d’usinage."""
    def __init__(self, op_type, depth, area=None, nb_holes=None, hole_diam=None,
                 length=None, width=None, chamfer_width=None):
        self.op_type = op_type
        self.depth = depth

        # Données additionnelles selon opération
        self.area = area                # Surfaçage, Poche, Chanfrein
        self.nb_holes = nb_holes        # Perçage
        self.hole_diam = hole_diam      # Perçage
        self.length = length            # Rainurage, Contournage
        self.width = width              # Rainurage
        self.chamfer_width = chamfer_width  # Chanfrein


# ================================================================
# CALCUL DU VOLUME À ENLEVER (en mm3)
# ================================================================

def compute_volume_mm3(op: MachiningOperation):
    """Retourne le volume en mm3 pour l’opération donnée."""

    # ------------------------------------------------------------
    # 1) SURFAÇAGE / POCHE → Volume = Aire × Profondeur
    # ------------------------------------------------------------
    if op.op_type in ("Surfaçage", "Poche"):
        if op.area is None:
            raise ValueError("Aire de la face manquante pour cet usinage.")
        return op.area * op.depth

    # ------------------------------------------------------------
    # 2) PERCAGE → nb × π × (Ø/2)² × profondeur
    # ------------------------------------------------------------
    if op.op_type == "Perçage":
        if op.nb_holes is None or op.hole_diam is None:
            raise ValueError("Données trou manquantes.")
        radius = op.hole_diam / 2
        vol_one = math.pi * radius * radius * op.depth
        return op.nb_holes * vol_one

    # ------------------------------------------------------------
    # 3) RAINURAGE → Volume = longueur × largeur × profondeur
    # ------------------------------------------------------------
    if op.op_type == "Rainurage":
        if op.length is None or op.width is None:
            raise ValueError("Largeur ou longueur manquantes pour rainurage.")
        return op.length * op.width * op.depth

    # ------------------------------------------------------------
    # 4) CONTOURNAGE (2D) → Volume = profondeur × (longueur toolpath × largeur)
    # Largeur usinée = Ø outil (≈ simplification)
    # ------------------------------------------------------------
    if op.op_type == "Contournage":
        if op.length is None:
            raise ValueError("Longueur de contour manquante.")
        return op.length * op.depth  # largeur prise en charge plus tard par outil

    # ------------------------------------------------------------
    # 5) CHANFREIN → Volume ≈ Aire × profondeur / 2 (pente 45°)
    # ------------------------------------------------------------
    if op.op_type == "Chanfrein":
        if op.chamfer_width is None or op.area is None:
            raise ValueError("Données chanfrein manquantes.")
        # Modèle simple : volume triangulaire : aire × profondeur / 2
        return op.area * op.depth * 0.5

    # ------------------------------------------------------------
    # ERREUR
    # ------------------------------------------------------------
    raise ValueError(f"Opération inconnue : {op.op_type}")
