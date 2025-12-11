import math

# ================================================================
# MODE CAM : CALCUL DU TEMPS À PARTIR D'UNE OPÉRATION PATH EXISTANTE
# ================================================================
#
# Principe :
#  - On prend une opération Path existante (Face, Pocket, Profile, Drill...)
#  - On lit son Path.Commands (G0, G1, G2, G3...)
#  - On reconstruit la longueur totale des déplacements
#  - On applique :
#       * ton avance de coupe (Vf) pour G1/G2/G3
#       * un feed rapide (optionnel) pour G0
#  - On retourne un temps (min) + les longueurs
#
# Avantage :
#  - S'appuie VRAIMENT sur les parcours générés par le CAM FreeCAD
#  - Indépendant de la manière dont FreeCAD calcule Duration/EstimatedTime
#
# Limitation :
#  - Nécessite une opération Path déjà présente dans le document
#    (créée à la main ou plus tard automatiquement par ton module)


def _extract_path_segments(path):
    """
    Reconstruit les segments de déplacement à partir de path.Commands.
    Retourne une liste de (code, dist_mm).
    """
    cmds = getattr(path, "Commands", None)
    if cmds is None:
        return []

    segments = []

    last_x = 0.0
    last_y = 0.0
    last_z = 0.0
    first = True

    for cmd in cmds:
        name = cmd.Name.upper()  # ex: 'G0', 'G1', 'G2', ...
        params = getattr(cmd, "Parameters", {})

        # On récupère les nouvelles coordonnées si présentes
        x = params.get("X", last_x)
        y = params.get("Y", last_y)
        z = params.get("Z", last_z)

        if first:
            # Premier point : pas de segment à calculer
            first = False
        else:
            dx = x - last_x
            dy = y - last_y
            dz = z - last_z
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)
            segments.append((name, dist))

        last_x, last_y, last_z = x, y, z

    return segments


def compute_time_from_path_op(op,
                              feed_mm_min,
                              rapid_feed_mm_min=None,
                              include_rapids=False):
    """
    Calcule un temps d'usinage basé sur une opération Path existante.

    Paramètres
    ----------
    op : objet Path (Face, Pocket, Profile, Drill...)
        L'opération FreeCAD Path.
    feed_mm_min : float
        Avance de coupe que TU veux utiliser (mm/min).
        (on ne fait pas confiance aveuglément au F de FreeCAD).
    rapid_feed_mm_min : float ou None
        Avance rapide pour les G0. Si None, on ignore G0 ou
        on les prend au même feed que le feed_mm_min (si include_rapids=True).
    include_rapids : bool
        - False : on ne prend en compte que G1/G2/G3
        - True  : on ajoute aussi le temps des G0

    Retour
    ------
    dict :
        {
            "length_cut_mm": ...,
            "length_rapid_mm": ...,
            "time_cut_min": ...,
            "time_rapid_min": ...,
            "time_total_min": ...,
        }
    """
    path = getattr(op, "Path", None)
    if path is None:
        raise ValueError("L'opération fournie ne possède pas de Path.")

    if feed_mm_min <= 0:
        raise ValueError("L'avance de coupe (feed_mm_min) doit être > 0.")

    segments = _extract_path_segments(path)

    length_cut = 0.0
    length_rapid = 0.0

    for code, dist in segments:
        if code in ("G1", "G01", "G2", "G02", "G3", "G03"):
            length_cut += dist
        elif code in ("G0", "G00"):
            length_rapid += dist

    # Temps de coupe
    time_cut_min = length_cut / feed_mm_min if feed_mm_min > 0 else 0.0

    # Temps rapides
    time_rapid_min = 0.0
    if include_rapids:
        eff_rapid_feed = rapid_feed_mm_min or feed_mm_min
        if eff_rapid_feed > 0:
            time_rapid_min = length_rapid / eff_rapid_feed

    time_total_min = time_cut_min + time_rapid_min

    return {
        "length_cut_mm": length_cut,
        "length_rapid_mm": length_rapid,
        "time_cut_min": time_cut_min,
        "time_rapid_min": time_rapid_min,
        "time_total_min": time_total_min,
    }
