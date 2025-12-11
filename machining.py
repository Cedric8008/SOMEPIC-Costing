# -*- coding: utf-8 -*-
"""
machining.py — Moteur de calcul corrigé et unifié pour le module PartCosting Pro
"""

import math
from machining_tools


# ----------------------------------------------------------
# Outil : calcul de Vf (avance) en mm/min
# ----------------------------------------------------------
def calc_feed_mm_min(z_teeth, fz, rpm):
    try:
        return float(z_teeth) * float(fz) * float(rpm)
    except Exception:
        return 0.0


# ----------------------------------------------------------
# Outil : nombre de passes profondeur
# ----------------------------------------------------------
def compute_passes_z(depth_total, ap_max):
    depth_total = abs(float(depth_total))
    ap_max = abs(float(ap_max))
    if ap_max <= 0:
        return 1
    return max(1, int(math.ceil(depth_total / ap_max)))


# ----------------------------------------------------------
# Outil : nombre de passes radiales
# ----------------------------------------------------------
def compute_passes_radial(xy_surplus, ae_mm):
    xy_surplus = abs(float(xy_surplus))
    ae_mm = abs(float(ae_mm))

    if ae_mm <= 0:
        return 1

    if xy_surplus <= 0:
        return 1

    return max(1, int(math.ceil(xy_surplus / ae_mm)))


# ----------------------------------------------------------
# Surfaçage — calcul rapide par surface & Vf
# ----------------------------------------------------------
def compute_face_time(surface_mm2, depth_total, ap_max, ae_mm, vf_mm_min):
    """
    surface_mm2 : surface à surfacer
    depth_total : profondeur totale
    ap_max       : passe max
    ae_mm        : engagement radial
    vf_mm_min    : avance
    """
    if vf_mm_min <= 0:
        return 0.0, 0, 0

    passes_z = compute_passes_z(depth_total, ap_max)
    passes_rad = compute_passes_radial(ae_mm, ae_mm)  # radial = 1 pour le moment

    length_equiv = surface_mm2 / max(ae_mm, 0.001)
    time_min = length_equiv / vf_mm_min

    return time_min, passes_z, passes_rad


# ----------------------------------------------------------
# Contournage — calcul (L total + passes Z + passes radiales)
# ----------------------------------------------------------
def compute_profile_time(length_total, depth_total, ap_max, xy_surplus, ae_mm, vf_mm_min):
    if vf_mm_min <= 0:
        return 0.0, 0, 0

    passes_z = compute_passes_z(depth_total, ap_max)
    passes_rad = compute_passes_radial(xy_surplus, ae_mm)

    time_min = (length_total * passes_z * passes_rad) / vf_mm_min
    return time_min, passes_z, passes_rad


# ----------------------------------------------------------
# Poche — modèle approx (longueur équivalente)
# ----------------------------------------------------------
def compute_pocket_time(surface_mm2, depth_total, ap_max, xy_surplus, ae_mm, vf_mm_min):
    if vf_mm_min <= 0:
        return 0.0, 0, 0

    passes_z = compute_passes_z(depth_total, ap_max)
    passes_rad = compute_passes_radial(xy_surplus, ae_mm)

    # longueur équivalente = surface divisée par Ae
    length_equiv = surface_mm2 / max(ae_mm, 0.001)

    time_min = (length_equiv * passes_z * passes_rad) / vf_mm_min

    return time_min, passes_z, passes_rad


