# -*- coding: utf-8 -*-
import math

import FreeCAD
import FreeCADGui
import Part
from PySide2 import QtWidgets, QtCore


def find_part_and_stock():
    """
    Détection robuste :
    - BRUT = solide avec le plus grand volume
    - PIECE = plus petit solide visible
    """
    doc = FreeCAD.ActiveDocument
    if not doc:
        return (None, None)

    solids = []

    for o in doc.Objects:
        if not hasattr(o, "Shape"):
            continue
        try:
            vol = o.Shape.Volume
        except Exception:
            continue

        if vol <= 0:
            continue

        visible = True
        try:
            visible = o.ViewObject.Visibility
        except Exception:
            pass

        solids.append((o, vol, visible))

    if not solids:
        return (None, None)

    solids.sort(key=lambda x: x[1])  # petit → grand

    # BRUT = plus gros volume
    stock = solids[-1][0]

    # PIECE = plus petit volume visible
    part = None
    for o, vol, vis in solids:
        if vis:
            part = o
            break

    if not part:
        part = solids[0][0]

    if part == stock:
        part = solids[0][0]

    return (part, stock)


def compute_feed_mm_min(vc_m_min, diam_mm, z_teeth, fz_mm):
    """
    Vf = rpm * Z * fz
    rpm = (1000 * Vc) / (π * D)
    """
    if vc_m_min <= 0 or diam_mm <= 0 or z_teeth <= 0 or fz_mm <= 0:
        return 0.0
    rpm = (1000.0 * vc_m_min) / (math.pi * diam_mm)
    vf = rpm * z_teeth * fz_mm
    return vf


class OperationDialog(QtWidgets.QDialog):
    """
    Boîte de dialogue principale pour la création d'une opération :
    - Surfaçage (Face)
    - Contournage (Profil)
    - Poche (placeholder)
    """

    def __init__(self, parent=None):
        super(OperationDialog, self).__init__(parent)
        self.setWindowTitle("Part Costing Pro — Nouvelle opération")
        self.setMinimumWidth(900)

        self._faces = []   # faces sélectionnées
        self.result = None

        main = QtWidgets.QVBoxLayout(self)

        # ------------------------------------------------------------------
        # 1. Sélection FreeCAD
        # ------------------------------------------------------------------
        box_sel = QtWidgets.QGroupBox("Sélection FreeCAD")
        main.addWidget(box_sel)
        lay_sel = QtWidgets.QHBoxLayout(box_sel)

        lab = QtWidgets.QLabel("Faces :")
        lay_sel.addWidget(lab)

        self.ed_faces = QtWidgets.QLineEdit("Aucune face sélectionnée")
        self.ed_faces.setReadOnly(True)
        lay_sel.addWidget(self.ed_faces)

        self.btn_read = QtWidgets.QPushButton("Lire la sélection")
        self.btn_read.clicked.connect(self.read_selection)
        lay_sel.addWidget(self.btn_read)

        # ------------------------------------------------------------------
        # 2. Type d'opération
        # ------------------------------------------------------------------
        box_kind = QtWidgets.QGroupBox("Type d'opération")
        main.addWidget(box_kind)
        lay_kind = QtWidgets.QHBoxLayout(box_kind)

        self.cmb_kind = QtWidgets.QComboBox()
        self.cmb_kind.addItems([
            "Face (Surfaçage)",
            "Profil (Contournage)",
            "Poche (ébauche)",
        ])
        lay_kind.addWidget(self.cmb_kind)

        # ------------------------------------------------------------------
        # 3. Outil
        # ------------------------------------------------------------------
        box_tool = QtWidgets.QGroupBox("Outil")
        main.addWidget(box_tool)
        lay_tool = QtWidgets.QGridLayout(box_tool)

        r = 0
        lay_tool.addWidget(QtWidgets.QLabel("Bibliothèque outil :"), r, 0)
        self.cmb_tool = QtWidgets.QComboBox()
        # L'utilisateur pourra adapter les noms, mais on parse Ø et Z automatiquement
        self.cmb_tool.addItems([
            "Fraise Ø6 Z2",
            "Fraise Ø10 Z4",
            "Fraise Ø16 Z4",
            "Fraise surf Ø50 Z6",
        ])
        self.cmb_tool.currentIndexChanged.connect(self.on_tool_changed)
        lay_tool.addWidget(self.cmb_tool, r, 1)
        r += 1

        lay_tool.addWidget(QtWidgets.QLabel("Ø (mm) :"), r, 0)
        self.ed_diam = QtWidgets.QLineEdit("6.0")
        lay_tool.addWidget(self.ed_diam, r, 1)
        r += 1

        lay_tool.addWidget(QtWidgets.QLabel("Z dents :"), r, 0)
        self.ed_z = QtWidgets.QLineEdit("2")
        lay_tool.addWidget(self.ed_z, r, 1)
        r += 1

        lay_tool.addWidget(QtWidgets.QLabel("Vc (m/min) :"), r, 0)
        self.ed_vc = QtWidgets.QLineEdit("150.0")
        lay_tool.addWidget(self.ed_vc, r, 1)
        r += 1

        lay_tool.addWidget(QtWidgets.QLabel("Fz (mm/dent) :"), r, 0)
        self.ed_fz = QtWidgets.QLineEdit("0.04")
        lay_tool.addWidget(self.ed_fz, r, 1)
        r += 1

        # ------------------------------------------------------------------
        # 4. Conditions de coupe
        # ------------------------------------------------------------------
        box_cut = QtWidgets.QGroupBox("Conditions de coupe")
        main.addWidget(box_cut)
        lay_cut = QtWidgets.QGridLayout(box_cut)

        r = 0
        lay_cut.addWidget(QtWidgets.QLabel("Ae (% du Ø) :"), r, 0)
        self.ed_ae_percent = QtWidgets.QLineEdit("40")
        lay_cut.addWidget(self.ed_ae_percent, r, 1)
        r += 1

        lay_cut.addWidget(QtWidgets.QLabel("Ae (mm calculé) :"), r, 0)
        self.ed_ae_mm = QtWidgets.QLineEdit("")
        self.ed_ae_mm.setReadOnly(True)
        lay_cut.addWidget(self.ed_ae_mm, r, 1)
        r += 1

        lay_cut.addWidget(QtWidgets.QLabel("Ap max (mm/passe) :"), r, 0)
        self.ed_ap = QtWidgets.QLineEdit("2.0")
        lay_cut.addWidget(self.ed_ap, r, 1)
        r += 1

        # Surplus brut Z+ et XY (optionnel – utilisé pour passes radiales/Z)
        lay_cut.addWidget(QtWidgets.QLabel("Surépaisseur Z+ brut (mm) :"), r, 0)
        self.ed_z_plus = QtWidgets.QLineEdit("2.0")
        lay_cut.addWidget(self.ed_z_plus, r, 1)
        r += 1

        lay_cut.addWidget(QtWidgets.QLabel("Surépaisseur XY brut (mm) :"), r, 0)
        self.ed_xy_surplus = QtWidgets.QLineEdit("2.5")
        lay_cut.addWidget(self.ed_xy_surplus, r, 1)
        r += 1

        # ------------------------------------------------------------------
        # 5. Paramètres opération
        # ------------------------------------------------------------------
        box_par = QtWidgets.QGroupBox("Paramètres opération")
        main.addWidget(box_par)
        lay_par = QtWidgets.QGridLayout(box_par)

        r = 0
        lay_par.addWidget(QtWidgets.QLabel("Profondeur totale (mm) :"), r, 0)
        self.ed_depth = QtWidgets.QLineEdit("0.0")
        lay_par.addWidget(self.ed_depth, r, 1)
        r += 1

        lay_par.addWidget(QtWidgets.QLabel("Surface considérée (mm²) :"), r, 0)
        self.ed_area = QtWidgets.QLineEdit("0.0")
        self.ed_area.setReadOnly(True)
        lay_par.addWidget(self.ed_area, r, 1)
        r += 1

        lay_par.addWidget(QtWidgets.QLabel("Longueur équivalente (mm) :"), r, 0)
        self.ed_length = QtWidgets.QLineEdit("0.0")
        self.ed_length.setReadOnly(True)
        lay_par.addWidget(self.ed_length, r, 1)
        r += 1

        lay_par.addWidget(QtWidgets.QLabel("Z sécurité (mm) :"), r, 0)
        self.ed_zsafe = QtWidgets.QLineEdit("50.0")
        lay_par.addWidget(self.ed_zsafe, r, 1)
        r += 1

        # ------------------------------------------------------------------
        # 6. Mode de calcul (pour mémoire, on reste sur débit copeaux)
        # ------------------------------------------------------------------
        box_mode = QtWidgets.QGroupBox("Mode de calcul")
        main.addWidget(box_mode)
        lay_mode = QtWidgets.QHBoxLayout(box_mode)

        self.rb_chips = QtWidgets.QRadioButton("Débit copeaux (déterministe)")
        self.rb_chips.setChecked(True)
        lay_mode.addWidget(self.rb_chips)

        # ------------------------------------------------------------------
        # 7. Calcul + résultat
        # ------------------------------------------------------------------
        self.btn_compute = QtWidgets.QPushButton("Calculer le temps")
        self.btn_compute.clicked.connect(self.compute_time)
        main.addWidget(self.btn_compute)

        self.lbl_result = QtWidgets.QLabel("Temps : -- h")
        main.addWidget(self.lbl_result)

        # ------------------------------------------------------------------
        # 8. OK / Annuler
        # ------------------------------------------------------------------
        lay_buttons = QtWidgets.QHBoxLayout()
        main.addLayout(lay_buttons)

        btn_ok = QtWidgets.QPushButton("OK")
        btn_ok.clicked.connect(self.accept)
        lay_buttons.addWidget(btn_ok)

        btn_cancel = QtWidgets.QPushButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        lay_buttons.addWidget(btn_cancel)

        # Initialisation de l’outil par défaut
        self.on_tool_changed()

    # ------------------------------------------------------------------
    # Sélection des faces
    # ------------------------------------------------------------------
    def read_selection(self):
        """Lit les faces sélectionnées dans FreeCAD et met à jour self._faces."""

        sel_ex = FreeCADGui.Selection.getSelectionEx()
        faces = []
        labels = []

        for s in sel_ex:
            obj = s.Object
            for name, sub in zip(s.SubElementNames, s.SubObjects):
                if isinstance(sub, Part.Face):
                    faces.append(sub)
                    labels.append(f"{obj.Label}/{name}")

        self._faces = faces

        if labels:
            self.ed_faces.setText(", ".join(labels))
        else:
            self.ed_faces.setText("Aucune face sélectionnée")

        # On peut en profiter pour deviner une profondeur et une surface
        if faces:
            f0 = faces[0]
            bb = f0.BoundBox
            depth_guess = bb.ZMax - bb.ZMin
            self.ed_depth.setText(f"{depth_guess:.3f}")
            area = f0.Area
            self.ed_area.setText(f"{area:.1f}")

    # ------------------------------------------------------------------
    # Changement d’outil → parse Ø et Z depuis le texte
    # ------------------------------------------------------------------
    def on_tool_changed(self):
        """
        Parse automatiquement le Ø et le Z depuis le texte de l'outil.
        Exemple : 'Fraise Ø16 Z4'
        """
        txt = self.cmb_tool.currentText()
        # Chercher un nombre pour le Ø
        import re
        m_d = re.search(r"(\d+(?:\.\d+)?)", txt)
        if m_d:
            try:
                d = float(m_d.group(1))
                self.ed_diam.setText(f"{d:.3f}")
            except Exception:
                pass
        # Chercher 'Z' pour le nombre de dents
        m_z = re.search(r"Z\s*(\d+)", txt, re.IGNORECASE)
        if m_z:
            self.ed_z.setText(m_z.group(1))

    # ------------------------------------------------------------------
    # type d'opération interne
    # ------------------------------------------------------------------
    def _op_kind(self):
        txt = self.cmb_kind.currentText().lower()
        if "face" in txt or "surfa" in txt:
            return "face"
        if "profil" in txt or "contourn" in txt:
            return "profile"
        if "poche" in txt:
            return "pocket"
        return "face"

    # ------------------------------------------------------------------
    # Longueur totale de contour = somme des périmètres
    # ------------------------------------------------------------------
    def _get_profile_length_from_faces(self):
        import FreeCAD
        total = 0.0

        if not hasattr(self, "_faces") or not self._faces:
            return 0.0

        for face in self._faces:
            max_len = 0.0

            # Récupérer les edges
            for e in face.Edges:
                p1 = e.Vertexes[0].Point
                p2 = e.Vertexes[1].Point

                # On garde uniquement les edges "horizontales" (contournage)
                if abs(p1.z - p2.z) < 0.001:  # tolérance en mm
                    L = float(e.Length)
                    if L > max_len:
                        max_len = L

            # Ajout entrée/sortie léger
            if max_len > 0:
                total += max_len + 4.0  # +2 mm entrée +2 mm sortie

        return total

    # ------------------------------------------------------------------
    # Calcul du temps d'usinage
    # ------------------------------------------------------------------
    def compute_time(self):
        if not self._faces:
            QtWidgets.QMessageBox.warning(
                self, "Erreur", "Aucune face sélectionnée."
            )
            return

        # Récupération des paramètres outil
        try:
            diam = float(self.ed_diam.text())
            z_teeth = int(self.ed_z.text())
            vc = float(self.ed_vc.text())
            fz = float(self.ed_fz.text())
            ae_percent = float(self.ed_ae_percent.text())
            ap_max = float(self.ed_ap.text())
            z_plus = float(self.ed_z_plus.text())
            xy_surplus = float(self.ed_xy_surplus.text())
            depth_total = float(self.ed_depth.text())
        except Exception:
            QtWidgets.QMessageBox.warning(
                self, "Erreur", "Paramètres numériques invalides."
            )
            return

        ae_mm = (ae_percent / 100.0) * diam
        if ae_mm <= 0:
            ae_mm = diam
        self.ed_ae_mm.setText(f"{ae_mm:.3f}")

        vf = compute_feed_mm_min(vc, diam, z_teeth, fz)
        if vf <= 0:
            QtWidgets.QMessageBox.warning(
                self, "Erreur", "Impossible de calculer l’avance (Vf)."
            )
            return

        kind = self._op_kind()

        part, stock = find_part_and_stock()

        # ------------------------------------------------------------------
        # CONTORNAGE
        # ------------------------------------------------------------------
        if kind == "profile":
            base_length = self._get_profile_length_from_faces()
            if base_length <= 0:
                QtWidgets.QMessageBox.warning(
                    self, "Erreur", "Longueur de contour nulle."
                )
                return

            # Surépaisseur radiale issue du brut (XY) :
            # on utilise soit le champ, soit diff. brut / pièce si possible
            stock_rad = 0.0
            if stock and part:
                bb_p = part.Shape.BoundBox
                bb_s = stock.Shape.BoundBox
                sur_x = (bb_s.XLength - bb_p.XLength) / 2.0
                sur_y = (bb_s.YLength - bb_p.YLength) / 2.0
                stock_rad = max(sur_x, sur_y, 0.0)
            # on additionne la surépaisseur saisie si non nulle
            stock_rad = max(stock_rad, xy_surplus)

            # Passes radiales
            if stock_rad > 0:
                passes_rad = max(1, math.ceil(stock_rad / ae_mm))
            else:
                passes_rad = 1

            # Profondeur = soit depth_total, soit utilisation surépaisseur Z+
            if depth_total <= 0 and part and stock:
                bb_p = part.Shape.BoundBox
                bb_s = stock.Shape.BoundBox
                depth_total = max(0.0, (bb_s.ZMax - bb_p.ZMax))
            if depth_total <= 0:
                depth_total = z_plus

            # Passes en Z
            if ap_max > 0:
                passes_z = max(1, math.ceil(depth_total / ap_max))
            else:
                passes_z = 1

            length_total = base_length * passes_rad * passes_z
            time_min = length_total / vf
            time_h = time_min / 60.0

            self.ed_length.setText(f"{length_total:.1f}")
            self.lbl_result.setText(
                f"Temps : {time_h:.3f} h  "
                f"(L={length_total:.0f} mm, Vf={vf:.0f} mm/min, "
                f"passes Z={passes_z}, passes radiales={passes_rad})"
            )

            self.result = {
                "kind": "contournage",
                "time_h": time_h,
                "length_mm": length_total,
                "vf_mm_min": vf,
                "passes_z": passes_z,
                "passes_rad": passes_rad,
                "ae_mm": ae_mm,
                "depth_mm": depth_total,
            }
            return

        # ------------------------------------------------------------------
        # SURFAÇAGE
        # ------------------------------------------------------------------
        if kind == "face":
            if not stock:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Attention",
                    "Brut introuvable, le surfaçage utilisera uniquement la surface de la face.",
                )
                f0 = self._faces[0]
                bb = f0.BoundBox
                length = bb.XLength
                width = bb.YLength
            else:
                bb_s = stock.Shape.BoundBox
                length = bb_s.XLength
                width = bb_s.YLength

            area = length * width
            self.ed_area.setText(f"{area:.1f}")

            # Surépaisseur Z à enlever
            if depth_total <= 0 and part and stock:
                bb_p = part.Shape.BoundBox
                bb_s = stock.Shape.BoundBox
                depth_total = max(0.0, (bb_s.ZMax - bb_p.ZMax))
            if depth_total <= 0:
                depth_total = z_plus

            # Passes en Z
            if ap_max > 0:
                passes_z = max(1, math.ceil(depth_total / ap_max))
            else:
                passes_z = 1

            # Passes radiales : largeur / Ae
            if ae_mm > 0:
                passes_rad = max(1, math.ceil(width / ae_mm))
            else:
                passes_rad = 1

            length_total = length * passes_rad * passes_z
            self.ed_length.setText(f"{length_total:.1f}")

            time_min = length_total / vf
            time_h = time_min / 60.0

            self.lbl_result.setText(
                f"Temps : {time_h:.3f} h  "
                f"(Surf brut={area:.0f} mm², L={length_total:.0f} mm, "
                f"Vf={vf:.0f} mm/min, passes Z={passes_z}, passes radiales={passes_rad})"
            )

            self.result = {
                "kind": "surfacage",
                "time_h": time_h,
                "length_mm": length_total,
                "vf_mm_min": vf,
                "passes_z": passes_z,
                "passes_rad": passes_rad,
                "ae_mm": ae_mm,
                "depth_mm": depth_total,
                "area_mm2": area,
            }
            return

        # ------------------------------------------------------------------
        # POCHE (placeholder basique pour l’instant)
        # ------------------------------------------------------------------
        if kind == "pocket":
            # On réutilise la surface de la première face comme base
            f0 = self._faces[0]
            area = f0.Area
            self.ed_area.setText(f"{area:.1f}")

            # On suppose un recouvrement en bandes Ae
            if ae_mm > 0:
                # On approxime une dimension carrée : L ≈ sqrt(area)
                width = math.sqrt(area)
                length = width
                passes_rad = max(1, math.ceil(width / ae_mm))
            else:
                width = math.sqrt(area)
                length = width
                passes_rad = 1

            # Profondeur + passes Z
            if depth_total <= 0:
                depth_total = z_plus
            if ap_max > 0:
                passes_z = max(1, math.ceil(depth_total / ap_max))
            else:
                passes_z = 1

            length_total = length * passes_rad * passes_z
            self.ed_length.setText(f"{length_total:.1f}")

            time_min = length_total / vf
            time_h = time_min / 60.0

            self.lbl_result.setText(
                f"Temps : {time_h:.3f} h  "
                f"(Approx. poche, L={length_total:.0f} mm, "
                f"Vf={vf:.0f} mm/min, passes Z={passes_z}, passes radiales={passes_rad})"
            )

            self.result = {
                "kind": "poche",
                "time_h": time_h,
                "length_mm": length_total,
                "vf_mm_min": vf,
                "passes_z": passes_z,
                "passes_rad": passes_rad,
                "ae_mm": ae_mm,
                "depth_mm": depth_total,
                "area_mm2": area,
            }
            return
