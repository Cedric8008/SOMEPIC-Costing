# -*- coding: utf-8 -*-
import FreeCAD
import FreeCADGui
import Part
from PySide2 import QtWidgets, QtCore

import machining
import os
import csv

TOOLS_CSV = "tools.csv"


# ---------------------------------------------------------------------------
# Gestion de la bibliothèque d'outils (tools.csv)
# ---------------------------------------------------------------------------

TOOLS_CSV = os.path.join(os.path.dirname(__file__), "tools.csv")


def _parse_float(text, default=0.0):
    """Convertit une chaîne en float, en acceptant les virgules."""
    if text is None:
        return default
    s = str(text).strip()
    if not s:
        return default
    s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return default


def load_tool_library():
    """Lit tools.csv et renvoie une liste de dicts outils.

    Chaque dict contient au minimum :
      - name
      - diam
      - z_teeth
      - vc
      - fz
    """
    tools = []

    if not os.path.isfile(TOOLS_CSV):
        return tools

    with open(TOOLS_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            name = (row.get("name") or "").strip()
            if not name:
                continue

            tool = {
                "name": name,
                "diam": _parse_float(row.get("diam")),
                "z_teeth": int(_parse_float(row.get("z_teeth"), 0)),
                "vc": _parse_float(row.get("vc")),
                "fz": _parse_float(row.get("fz")),
            }
            tools.append(tool)

    return tools




class OperationDialog(QtWidgets.QDialog):

    def __init__(self):
        super(OperationDialog, self).__init__()

        self.setWindowTitle("Part Costing Pro — Nouvelle opération")
        self.resize(950, 650)

        # Faces sélectionnées FreeCAD
        self._faces = []

        # ----- WIDGETS -----
        self.layout = QtWidgets.QVBoxLayout(self)

        # Bloc Sélection FreeCAD
        box_sel = QtWidgets.QGroupBox("Sélection FreeCAD")
        self.layout.addWidget(box_sel)
        lay_sel = QtWidgets.QHBoxLayout(box_sel)

        self.ed_faces = QtWidgets.QLineEdit()
        self.ed_faces.setReadOnly(True)
        lay_sel.addWidget(self.ed_faces)

        self.btn_read = QtWidgets.QPushButton("Lire la sélection")
        self.btn_read.clicked.connect(self.read_selection)
        lay_sel.addWidget(self.btn_read)

        # Bloc Type d’opération
        box_kind = QtWidgets.QGroupBox("Type d’opération")
        self.layout.addWidget(box_kind)
        lay_kind = QtWidgets.QHBoxLayout(box_kind)

        self.cmb_kind = QtWidgets.QComboBox()
        self.cmb_kind.addItems(["Face (Surfaçage)", "Profil (Contournage)", "Poche (Ébauche)"])
        lay_kind.addWidget(self.cmb_kind)

        # Bloc Outil
        box_tool = QtWidgets.QGroupBox("Outil")
        self.layout.addWidget(box_tool)
        lay_tool = QtWidgets.QGridLayout(box_tool)

        self.cmb_tool = QtWidgets.QComboBox()
        self.cmb_tool.currentIndexChanged.connect(self._on_tool_change)
        lay_tool.addWidget(QtWidgets.QLabel("Bibliothèque outil :"), 0, 0)
        lay_tool.addWidget(self.cmb_tool, 0, 1)

        self.ed_diam = QtWidgets.QLineEdit()
        self.ed_z = QtWidgets.QLineEdit()
        self.ed_vc = QtWidgets.QLineEdit()
        self.ed_fz = QtWidgets.QLineEdit()

        lay_tool.addWidget(QtWidgets.QLabel("Ø (mm) :"), 1, 0)
        lay_tool.addWidget(self.ed_diam, 1, 1)
        lay_tool.addWidget(QtWidgets.QLabel("Z dents :"), 2, 0)
        lay_tool.addWidget(self.ed_z, 2, 1)
        lay_tool.addWidget(QtWidgets.QLabel("Vc (m/min) :"), 3, 0)
        lay_tool.addWidget(self.ed_vc, 3, 1)
        lay_tool.addWidget(QtWidgets.QLabel("Fz (mm/dent) :"), 4, 0)
        lay_tool.addWidget(self.ed_fz, 4, 1)

        # Bloc Conditions de coupe
        box_cut = QtWidgets.QGroupBox("Conditions de coupe")
        self.layout.addWidget(box_cut)
        lay_cut = QtWidgets.QGridLayout(box_cut)

        self.ed_ae_percent = QtWidgets.QLineEdit()
        self.ed_ae = QtWidgets.QLineEdit()
        self.ed_ap = QtWidgets.QLineEdit()
        self.ed_z_plus = QtWidgets.QLineEdit()
        self.ed_xy_surplus = QtWidgets.QLineEdit()

        lay_cut.addWidget(QtWidgets.QLabel("Ae (% du Ø) :"), 0, 0)
        lay_cut.addWidget(self.ed_ae_percent, 0, 1)
        lay_cut.addWidget(QtWidgets.QLabel("Ae (mm calculé) :"), 1, 0)
        lay_cut.addWidget(self.ed_ae, 1, 1)
        lay_cut.addWidget(QtWidgets.QLabel("Ap max (mm/passe) :"), 2, 0)
        lay_cut.addWidget(self.ed_ap, 2, 1)
        lay_cut.addWidget(QtWidgets.QLabel("Surépaisseur Z+ brut (mm) :"), 3, 0)
        lay_cut.addWidget(self.ed_z_plus, 3, 1)
        lay_cut.addWidget(QtWidgets.QLabel("Surépaisseur XY brut (mm) :"), 4, 0)
        lay_cut.addWidget(self.ed_xy_surplus, 4, 1)

        # Bloc Paramètres opération
        box_param = QtWidgets.QGroupBox("Paramètres opération")
        self.layout.addWidget(box_param)
        lay_param = QtWidgets.QGridLayout(box_param)

        self.ed_depth_total = QtWidgets.QLineEdit()
        self.ed_surface = QtWidgets.QLineEdit()
        self.ed_length = QtWidgets.QLineEdit()
        self.ed_safez = QtWidgets.QLineEdit()

        lay_param.addWidget(QtWidgets.QLabel("Profondeur totale (mm) :"), 0, 0)
        lay_param.addWidget(self.ed_depth_total, 0, 1)
        lay_param.addWidget(QtWidgets.QLabel("Surface considérée (mm²) :"), 1, 0)
        lay_param.addWidget(self.ed_surface, 1, 1)
        lay_param.addWidget(QtWidgets.QLabel("Longueur équivalente (mm) :"), 2, 0)
        lay_param.addWidget(self.ed_length, 2, 1)
        lay_param.addWidget(QtWidgets.QLabel("Z sécurité (mm) :"), 3, 0)
        lay_param.addWidget(self.ed_safez, 3, 1)

        # Mode calcul
        box_mode = QtWidgets.QGroupBox("Mode de calcul")
        self.layout.addWidget(box_mode)
        lay_mode = QtWidgets.QHBoxLayout(box_mode)

        self.rb_chip = QtWidgets.QRadioButton("Débit copeaux (déterministe)")
        self.rb_chip.setChecked(True)
        lay_mode.addWidget(self.rb_chip)

        # Bouton calcul
        self.btn_compute = QtWidgets.QPushButton("Calculer le temps")
        self.btn_compute.clicked.connect(self.compute_time)
        self.layout.addWidget(self.btn_compute)

        # Sortie temps
        self.lbl_time = QtWidgets.QLabel("Temps : -- h")
        self.layout.addWidget(self.lbl_time)

        # Boutons fin
        lay_bottom = QtWidgets.QHBoxLayout()
        self.layout.addLayout(lay_bottom)

        self.btn_ok = QtWidgets.QPushButton("OK")
        lay_bottom.addWidget(self.btn_ok)

        self.btn_cancel = QtWidgets.QPushButton("Annuler")
        lay_bottom.addWidget(self.btn_cancel)

        # CHARGE LES OUTILS
        self._load_tools()

        # ------------------------------------------------------------------
        # Chargement des outils depuis tools.csv
        # ------------------------------------------------------------------
        def _load_tools(self):
            """Charge la bibliothèque d'outils et remplit la combo."""
            self.tools = load_tool_library()

            # Combo des outils : adapte le nom du widget à ton code
            # (cb_tool, cmb_tool, self.cb_outil, etc.)
            combo = self.cb_tool  # <= change si ton widget a un autre nom

            combo.clear()
            for t in self.tools:
                combo.addItem(t["name"])

            combo.currentIndexChanged.connect(self.on_tool_changed)

    # ------------------------------------------------------------------
    # Quand l'utilisateur change d'outil dans la combo
    # ------------------------------------------------------------------
    def on_tool_changed(self, index):
        """Quand l'utilisateur change d'outil dans la combo."""
        if not hasattr(self, "tools"):
            return
        if index < 0 or index >= len(self.tools):
            return

        tool = self.tools[index]

        # Adapte les noms des champs selon ton code :
        # Ø (mm), Z dents, Vc, Fz
        self.ed_diam.setText(f"{tool['diam']:.3f}")
        self.ed_z_teeth.setText(str(tool["z_teeth"]))
        self.ed_vc.setText(f"{tool['vc']:.1f}")
        self.ed_fz.setText(f"{tool['fz']:.3f}")

    
    # ------------------------------------------------------------
    # Mise à jour des champs quand on change d’outil
    # ------------------------------------------------------------
    def _on_tool_change(self):
        """Load tool parameters into the UI when selection changes."""
        name = self.cmb_tool.currentText()
        if not name:
            return

        from machining_tools import get_tool
        tool = get_tool(name)
        if not tool:
            return

        # Remplissage des champs
        self.ed_diam.setText(str(tool["Diam"]))
        self.ed_z_teeth.setText(str(tool["Z"]))
        self.ed_vc.setText(str(tool["Vc"]))
        self.ed_fz.setText(str(tool["Fz"]))

    # ------------------------------------------------------------
    # Lecture des faces FreeCAD sélectionnées
    # ------------------------------------------------------------
    def read_selection(self):
        """Lit la sélection FreeCAD et extrait les faces correctement."""
        sel = FreeCADGui.Selection.getSelectionEx()

        self._faces = []
        labels = []

        for s in sel:
            if not hasattr(s, "SubObjects"):
                continue

            for so in s.SubObjects:
                # On ne garde que les faces
                if isinstance(so, Part.Face):
                    self._faces.append(so)
                    labels.append(so.Label if hasattr(so, "Label") else so.__repr__())

        # Affichage texte
        if labels:
            self.ed_faces.setText(", ".join(labels))
        else:
            self.ed_faces.setText("Aucune face sélectionnée")

    # ------------------------------------------------------------
    # Correction automatique de l’orientation
    # ------------------------------------------------------------
    def _get_orientation_axes(self, face):
        """
        Retourne (X, Y, Z) = dimensions de la bounding box de la face.
        Sert à détecter la plus petite dimension (épaisseur).
        """
        bb = face.BoundBox
        return bb.XLength, bb.YLength, bb.ZLength

    def _get_part_orientation_factor(self):
        """
        Si Z géométrique ≠ Z usinage, renvoie un facteur 1 ou -1 pour corriger.
        Si la pièce est couchée, on l'interprète comme redressée.
        """
        if not self._faces:
            return 1

        # On prend la 1ère face pour déterminer l’orientation
        face = self._faces[0]
        dims = self._get_orientation_axes(face)

        # axe le plus petit → direction Z usinage
        smallest = min(dims)

        if smallest == dims[2]:
            return 1  # Z déjà correct
        else:
            return -1  # pièce couchée → on inverse profondeur Z

    # ------------------------------------------------------------
    # Détection profondeur réelle (orientée)
    # ------------------------------------------------------------
    def _get_real_depth(self):
        """
        La profondeur réelle = plus petite dimension de la bounding box
        des faces sélectionnées.
        Orientation : si la pièce est couchée, on réinterprète l’axe Z.
        """
        if not self._faces:
            return 0.0

        bb_min = FreeCAD.Vector( 1e9,  1e9,  1e9)
        bb_max = FreeCAD.Vector(-1e9, -1e9, -1e9)

        # bounding box globale des faces
        for f in self._faces:
            bb = f.BoundBox
            bb_min.x = min(bb_min.x, bb.XMin)
            bb_min.y = min(bb_min.y, bb.YMin)
            bb_min.z = min(bb_min.z, bb.ZMin)
            bb_max.x = max(bb_max.x, bb.XMax)
            bb_max.y = max(bb_max.y, bb.YMax)
            bb_max.z = max(bb_max.z, bb.ZMax)

        Lx = bb_max.x - bb_min.x
        Ly = bb_max.y - bb_min.y
        Lz = bb_max.z - bb_min.z

        # profondeur = plus petite dimension (axe d’usinage)
        depth = min(Lx, Ly, Lz)

        return abs(depth)

    # ------------------------------------------------------------
    # Longueur contour — compatible cylindres + faces planes
    # ------------------------------------------------------------
    def _get_contour_length(self):
        """
        Contournage :
        - Cylindres → périmètre = 2πR
        - Faces planes → longueur = max(X,Y) + marge
        - Multi-faces → somme
        - +2mm entrée +2mm sortie (per Cédric)
        """

        total = 0.0

        for f in self._faces:
            surf = f.Surface

            # ---- CAS CYLINDRE ----
            if isinstance(surf, Part.Cylinder):
                R = surf.Radius
                total += (2 * math.pi * R)
                continue

            # ---- CAS FACE PLANE ----
            bb = f.BoundBox
            dims = sorted([bb.XLength, bb.YLength, bb.ZLength])
            longest = dims[-1]      # contour = côté le plus long
            total += longest

        # Ajout entrée + sortie
        if total > 0:
            total += 4.0  # +2 mm +2 mm

        return total

    # ------------------------------------------------------------
    # Surface utile pour surfaçage ou poche
    # ------------------------------------------------------------
    def _get_face_area(self):
        """Utilise Area de la 1ère face."""
        try:
            return float(self._faces[0].Area)
        except:
            return 0.0

    # ------------------------------------------------------------
    # CALCUL TEMPS PRINCIPAL
    # ------------------------------------------------------------
    def compute_time(self):
        if not self._faces:
            QtWidgets.QMessageBox.warning(self, "Erreur", "Aucune face sélectionnée.")
            return

        # Lecture type opération
        kind = self.cmb_kind.currentText().lower()

        # Lecture outil
        try:
            diam = float(self.ed_diam.text())
            z_teeth = int(self.ed_z.text())
            vc = float(self.ed_vc.text())
            fz = float(self.ed_fz.text())
        except:
            QtWidgets.QMessageBox.warning(self, "Erreur", "Paramètres outil invalides.")
            return

        # Conditions coupe
        try:
            ae_pct = float(self.ed_ae_percent.text())
            ap_max = float(self.ed_ap.text())
            z_plus = float(self.ed_z_plus.text())
            xy_surplus = float(self.ed_xy_surplus.text())
        except:
            QtWidgets.QMessageBox.warning(self, "Erreur", "Paramètres coupe invalides.")
            return

        # Calcul Ae réel
        ae_mm = (ae_pct / 100.0) * diam
        self.ed_ae.setText(f"{ae_mm:.3f}")

        # Vitesse d’avance
        rpm = (1000 * vc) / (math.pi * diam)
        vf_mm_min = machining.calc_feed_mm_min(z_teeth, fz, rpm)
        if vf_mm_min <= 0:
            QtWidgets.QMessageBox.warning(self, "Erreur", "Impossible de calculer l'avance Vf.")
            return

        # Profondeur totale
        try:
            depth_user = float(self.ed_depth_total.text())
        except:
            depth_user = 0.0

        depth_auto = self._get_real_depth()

        depth_total = depth_user if depth_user > 0 else depth_auto
        depth_total += abs(z_plus)  # surépaisseur Z+

        # ---------------------------
        # SURFACAGE
        # ---------------------------
        if "face" in kind:
            area = self._get_face_area()
            self.ed_surface.setText(f"{area:.1f}")

            time_min, passes_z, passes_rad = machining.compute_face_time(
                area, depth_total, ap_max, ae_mm, vf_mm_min
            )

            self.ed_length.setText(f"{area/ae_mm:.1f}")

            self.lbl_time.setText(
                f"Temps : {time_min/60:.3f} h  "
                f"(Surf={area:.0f}mm², Z={passes_z}, Rad={passes_rad}, Vf={vf_mm_min:.0f})"
            )
            return

        # ---------------------------
        # CONTOURNAGE
        # ---------------------------
        if "profil" in kind:
            L = self._get_contour_length()
            self.ed_length.setText(f"{L:.1f}")

            time_min, passes_z, passes_rad = machining.compute_profile_time(
                L, depth_total, ap_max, xy_surplus, ae_mm, vf_mm_min
            )

            self.lbl_time.setText(
                f"Temps : {time_min/60:.3f} h  "
                f"(L={L:.0f}mm, passes Z={passes_z}, passes rad={passes_rad})"
            )
            return

        # ---------------------------
        # POCHES
        # ---------------------------
        if "poche" in kind:
            area = self._get_face_area()
            self.ed_surface.setText(f"{area:.1f}")

            time_min, passes_z, passes_rad = machining.compute_pocket_time(
                area, depth_total, ap_max, xy_surplus, ae_mm, vf_mm_min
            )

            L_equiv = area / max(ae_mm, 0.001)
            self.ed_length.setText(f"{L_equiv:.1f}")

            self.lbl_time.setText(
                f"Temps : {time_min/60:.3f} h  "
                f"(Surf={area:.0f}mm², L≈{L_equiv:.0f}mm, Z={passes_z}, Rad={passes_rad})"
            )
            return




