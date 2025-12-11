import math

# ===================================================================
# MODE CALCUL USINAGE PAR DÉBIT COPEAUX (CHIFFRAGE)
# ===================================================================

def compute_rpm(vc_m_min, tool_diam_mm):
    """n (tr/min) = 1000 * Vc / (π * D)"""
    if vc_m_min <= 0 or tool_diam_mm <= 0:
        return 0
    return (1000 * vc_m_min) / (math.pi * tool_diam_mm)


def compute_feed(rpm, z, fz):
    """Avance Vf (mm/min) = n × Z × Fz"""
    if rpm <= 0 or z <= 0 or fz <= 0:
        return 0
    return rpm * z * fz


def compute_chip_flow(ap_mm, ae_mm, feed_mm_min):
    """Débit copeaux mm3/min"""
    if ap_mm <= 0 or ae_mm <= 0:
        return 0
    return ap_mm * ae_mm * feed_mm_min


def compute_time_chip(volume_mm3, chip_flow_cm3_min):
    """Temps = Volume / Débit"""
    if chip_flow_cm3_min <= 0:
        raise ValueError("Débit copeaux doit être > 0.")

    vol_cm3 = volume_mm3 / 1000.0
    time_min = vol_cm3 / chip_flow_cm3_min
    return time_min


# ===================================================================
# FONCTION PRINCIPALE : CALCUL COMPLET
# ===================================================================
def compute_chip_based_time(tool_diam_mm, z, vc_m_min, fz_mm,
                             ap_mm, ae_mm,
                             volume_mm3,
                             chipflow_override_cm3_min=None):
    """
    Calcule un temps d’usinage par débit copeaux en utilisant :
    - paramètres outil (Ø, Z, Vc, Fz)
    - engagement : Ap, Ae
    - volume à enlever
    - OU un débit copeaux manuel (chipflow_override)

    Retourne un dict complet pour affichage ou UI.
    """

    # 1) vitesse de rotation
    rpm = compute_rpm(vc_m_min, tool_diam_mm)

    # 2) avance
    feed = compute_feed(rpm, z, fz_mm)

    # 3) débit copeaux naturel
    chip_mm3_min = compute_chip_flow(ap_mm, ae_mm, feed)
    chip_cm3_min = chip_mm3_min / 1000.0

    # 4) si l’utilisateur saisit un débit copeaux manuel
    if chipflow_override_cm3_min is not None and chipflow_override_cm3_min > 0:
        chip_cm3_min = chipflow_override_cm3_min

    # 5) temps
    time_min = compute_time_chip(volume_mm3, chip_cm3_min)

    return {
        "rpm": rpm,
        "feed_mm_min": feed,
        "chip_cm3_min": chip_cm3_min,
        "time_min": time_min,
        "volume_mm3": volume_mm3,
        "volume_cm3": volume_mm3 / 1000.0,
    }
