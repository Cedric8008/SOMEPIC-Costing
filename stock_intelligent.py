# -*- coding: utf-8 -*-
"""
stock_intelligent.py
---------------------

Gestion "intelligente" du brut pour PartCosting Pro.

Rôle de ce module :
- Proposer un type de brut (bloc / rond) en fonction de la géométrie.
- Calculer des surépaisseurs automatiques (internes au calcul).
- Générer un brut FreeCAD (Part::Box ou Part::Cylinder) autour de la pièce.
- Stocker quelques métadonnées pour lier plus tard les opérations à un brut donné.

IMPORTANT :
- L'utilisateur, lui, saisit les dimensions RÉELLES du brut acheté
  (L, l, e ou Ø, L).
- Les surépaisseurs internes servent aux calculs (passes, volume, etc.),
  pas à la saisie.

Ce fichier est volontairement autonome et simple : il expose uniquement
4 fonctions utilisées par le panel :

    detect_best_stock_type(shape) -> "Block" | "Cylinder"
    compute_auto_margins(shape)   -> dict marges internes
    compute_best_orientation(shape) -> string ou tuple
    create_intelligent_stock(shape, margins=None, stock_type=None, name=None)
        -> (stock_obj, stock_type, margins, orientation)

"""

import math
import json

try:
    import FreeCAD
    import Part
except ImportError:
    # Permet d'importer le module en dehors de FreeCAD (ex : tests)
    FreeCAD = None
    Part = None


# ======================================================================
#  PARAMÈTRES GLOBAUX DE SURÉPAISSEUR (internes calcul)
# ======================================================================

DEFAULT_MARGINS = {
    # Surépaisseur latérale : ±2.5 mm
    "x_minus": 2.5,
    "x_plus": 2.5,
    "y_minus": 2.5,
    "y_plus": 2.5,
    # Surépaisseur en profondeur : Z- = 5 mm
    "z_minus": 5.0,
    # Surépaisseur en surépaisseur "au-dessus" : Z+ = 2 mm
    "z_plus": 2.0,
}


# ======================================================================
#  FONCTIONS UTILITAIRES
# ======================================================================

def _get_bb(shape):
    """Retourne la bounding box FreeCAD d'une shape."""
    return shape.BoundBox


def _as_dict_margins(margins=None):
    """Normalise un dict de marges, en fallback sur DEFAULT_MARGINS."""
    base = DEFAULT_MARGINS.copy()
    if margins:
        base.update(margins)
    return base


def _find_unique_name(doc, base_name):
    """Trouve un nom unique pour un nouvel objet (StockBlock, StockCylinder...)."""
    existing = {obj.Name for obj in doc.Objects}
    if base_name not in existing:
        return base_name
    i = 1
    while True:
        candidate = f"{base_name}{i}"
        if candidate not in existing:
            return candidate
        i += 1


def _label_with_index(doc, prefix):
    """Propose un Label type 'Brut01', 'Brut02', ..."""
    existing_labels = [obj.Label for obj in doc.Objects]
    i = 1
    while True:
        lbl = f"{prefix}{i:02d}"
        if lbl not in existing_labels:
            return lbl
        i += 1


# ======================================================================
#  DETECTION TYPE DE BRUT
# ======================================================================

def detect_best_stock_type(shape):
    """
    Retourne "Block" ou "Cylinder" en fonction de la géométrie.

    Heuristique simple :
    - Si X et Y proches, Z comparable, on peut proposer "Cylinder".
    - Sinon "Block".

    Cette logique est volontairement simple et robuste.
    """
    bb = _get_bb(shape)

    lx = bb.XLength
    ly = bb.YLength
    lz = bb.ZLength

    if lx <= 0 or ly <= 0 or lz <= 0:
        return "Block"

    # Ratio X/Y
    ratio_xy = abs(lx - ly) / max(lx, ly)

    # Si X et Y très proches (±10%) et Z raisonnablement proportionné → Cylindre possible
    if ratio_xy < 0.10:
        # si Z n'est pas ridicule par rapport à X/Y
        if lz > min(lx, ly) * 0.3:
            return "Cylinder"

    # Dans le doute → Block
    return "Block"


def compute_auto_margins(shape):
    """
    Calcule des surépaisseurs internes à partir de la taille de la pièce.

    Pour l'instant :
    - On applique juste DEFAULT_MARGINS.
    - On pourrait adapter légèrement les marges pour les très grosses pièces.

    Retourne un dict similaire à DEFAULT_MARGINS.
    """
    bb = _get_bb(shape)
    diag = math.sqrt(bb.XLength ** 2 + bb.YLength ** 2 + bb.ZLength ** 2)

    margins = DEFAULT_MARGINS.copy()

    # Exemple d'ajustement : grosses pièces → marges un peu augmentées
    if diag > 500.0:  # pièces > ~500 mm de diagonale
        factor = 1.5
        for k in margins:
            margins[k] *= factor

    return margins


def compute_best_orientation(shape):
    """
    Détermine une orientation "logique" du brut.

    Pour l'instant :
    - On se contente de dire "Z up (pièce telle quelle)".
    - Plus tard on pourra analyser les faces pour proposer une orientation d'usinage.
    """
    # Placeholder simple
    return "Z+ up (orientation par défaut)"


# ======================================================================
#  CREATION BRUT INTELLIGENT
# ======================================================================

def create_intelligent_stock(shape, margins=None, stock_type=None, name=None):
    """
    Crée un brut FreeCAD autour de la shape.

    Params
    ------
    shape : Part.Shape
        Géométrie de la pièce.
    margins : dict or None
        Surépaisseurs internes à utiliser.
        Si None → compute_auto_margins(shape).
    stock_type : str or None
        "Block" ou "Cylinder".
        Si None → detect_best_stock_type(shape).
    name : str or None
        Nom interne FreeCAD (Name), si None → généré.

    Retourne
    --------
    (stock_obj, stock_type, margins, orientation)

    - stock_obj : l'objet FreeCAD créé (Part::Box ou Part::Cylinder).
    - stock_type : "Block" ou "Cylinder".
    - margins : dict complet des marges utilisées.
    - orientation : string (pour affichage dans le panel).
    """
    if FreeCAD is None or Part is None:
        raise RuntimeError("Ce module doit être exécuté dans FreeCAD (FreeCAD/Part introuvables).")

    doc = FreeCAD.ActiveDocument
    if doc is None:
        doc = FreeCAD.newDocument("PartCosting")

    bb = _get_bb(shape)
    margins = _as_dict_margins(margins)
    if stock_type is None:
        stock_type = detect_best_stock_type(shape)

    orientation = compute_best_orientation(shape)

    # ------------------------------------------------------------------
    #  BRUT BLOC
    # ------------------------------------------------------------------
    if stock_type == "Cylinder":
        # On crée un cylindre englobant, axe Z
        # Diamètre : max(X,Y) + 2 * marge_max_xy
        max_xy = max(bb.XLength, bb.YLength)
        marge_xy = max(
            margins["x_minus"], margins["x_plus"],
            margins["y_minus"], margins["y_plus"],
        )
        dia = max_xy + 2.0 * marge_xy
        length = bb.ZLength + margins["z_minus"] + margins["z_plus"]

        # Centre XY = centre de la bounding box de la pièce
        cx = (bb.XMin + bb.XMax) * 0.5
        cy = (bb.YMin + bb.YMax) * 0.5

        # Base du cylindre : on descend de z_minus
        z0 = bb.ZMin - margins["z_minus"]

        obj_name = _find_unique_name(doc, "StockCylinder")
        stock = doc.addObject("Part::Cylinder", obj_name)
        stock.Radius = dia * 0.5
        stock.Height = length
        stock.Placement.Base = FreeCAD.Vector(cx - stock.Radius, cy - stock.Radius, z0)

        label = _label_with_index(doc, "BrutRond_")
        stock.Label = label

    else:
        # Bloc rectangulaire englobant
        lx = bb.XLength + margins["x_minus"] + margins["x_plus"]
        ly = bb.YLength + margins["y_minus"] + margins["y_plus"]
        lz = bb.ZLength + margins["z_minus"] + margins["z_plus"]

        # Origine du bloc : on étend la bbox en négatif selon les marges -
        x0 = bb.XMin - margins["x_minus"]
        y0 = bb.YMin - margins["y_minus"]
        z0 = bb.ZMin - margins["z_minus"]

        obj_name = _find_unique_name(doc, "StockBlock")
        stock = doc.addObject("Part::Box", obj_name)
        stock.Length = lx
        stock.Width = ly
        stock.Height = lz
        stock.Placement.Base = FreeCAD.Vector(x0, y0, z0)

        label = _label_with_index(doc, "BrutBloc_")
        stock.Label = label

    # ------------------------------------------------------------------
    #  METADONNÉES (pour liaison ultérieure avec PartCosting)
    # ------------------------------------------------------------------
    try:
        if not hasattr(stock, "PC_IsStock"):
            stock.addProperty("App::PropertyBool", "PC_IsStock", "PartCosting",
                              "Indique que cet objet est un brut PartCosting.")
        stock.PC_IsStock = True

        if not hasattr(stock, "PC_StockType"):
            stock.addProperty("App::PropertyString", "PC_StockType", "PartCosting",
                              "Type de brut (Block / Cylinder).")
        stock.PC_StockType = stock_type

        if not hasattr(stock, "PC_MarginsJSON"):
            stock.addProperty("App::PropertyString", "PC_MarginsJSON", "PartCosting",
                              "Surépaisseurs internes utilisées (JSON).")
        stock.PC_MarginsJSON = json.dumps(margins)

        if not hasattr(stock, "PC_Orientation"):
            stock.addProperty("App::PropertyString", "PC_Orientation", "PartCosting",
                              "Orientation utilisée pour générer le brut.")
        stock.PC_Orientation = str(orientation)

    except Exception:
        # En cas d'environnement sans App::Property* (tests), on ignore
        pass

    doc.recompute()
    return stock, stock_type, margins, orientation
