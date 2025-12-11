import FreeCAD
import FreeCADGui
import Part

from PySide2 import QtWidgets, QtCore, QtGui

from geometry import GeometryExtractor
from stock_intelligent import (
    detect_best_stock_type,
    compute_auto_margins,
    compute_best_orientation,
    create_intelligent_stock,
)

from machining_ops import MachiningOperation, compute_volume_mm3
from chip_calc import compute_chip_based_time, compute_rpm, compute_feed
from cam_calc import compute_time_from_path_op
from machining_tools import get_all_tool_names, get_tool


# ================================================================
# 📦 MATIÈRES + DENSITÉS
# ================================================================
MATERIALS = {
    "Acier": 7850,
    "Acier doux": 7700,
    "Inox 304": 8000,
    "Aluminium 6061": 2700,
    "Aluminium 5083": 2650,
    "Titane grade 5": 4430,
    "Laiton": 8530,
    "Cuivre": 8960,
    "POM": 1420,
    "ABS": 1050,
}


class PartCostingPanel(QtWidgets.QDockWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Part Costing")

        main_widget = QtWidgets.QWidget()
        main_layout = QtWidgets.QVBoxLayout(main_widget)

        self.tabs = QtWidgets.QTabWidget()
        main_layout.addWidget(self.tabs)

        # init onglets
        self._init_tab_analyse()
        self._init_tab_stock()
        self._init_tab_machining()

        self.setWidget(main_widget)

        # états internes
        self.selected_faces = []
        self.selected_obj = None
        self.cam_ops_index = []  # liste de (label, Name FreeCAD)

    # ============================================================
    # 🟩 Onglet Analyse
    # ============================================================
    def _init_tab_analyse(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)

        # ----- Analyse géométrique -----
        btn = QtWidgets.QPushButton("Analyser la géométrie")
        btn.clicked.connect(self.analyze_geometry)
        layout.addWidget(btn)

        self.text_analyse = QtWidgets.QTextEdit()
        self.text_analyse.setReadOnly(True)
        layout.addWidget(self.text_analyse)

        # ----- Matière -----
        layout.addWidget(QtWidgets.QLabel("Matière :"))

        self.combo_material = QtWidgets.QComboBox()
        self.combo_material.addItems(sorted(MATERIALS.keys()))
        layout.addWidget(self.combo_material)

        btn_w = QtWidgets.QPushButton("Calculer poids pièce + brut")
        btn_w.clicked.connect(self.compute_weights)
        layout.addWidget(btn_w)

        self.text_weight = QtWidgets.QTextEdit()
        self.text_weight.setReadOnly(True)
        layout.addWidget(self.text_weight)

        self.tabs.addTab(tab, "Analyse")

    def analyze_geometry(self):
        extractor = GeometryExtractor()
        if extractor.load_part():
            data = extractor.summary()
            txt = (
                "=== Résultat Analyse ===\n"
                f"Volume pièce : {data['volume_mm3']:.3f} mm³\n"
                f"Dimensions (bbox) : "
                f"X={data['bbox']['x']:.3f} mm  "
                f"Y={data['bbox']['y']:.3f} mm  "
                f"Z={data['bbox']['z']:.3f} mm\n"
                f"Nombre de faces : {data['face_count']}\n"
            )
            self.text_analyse.setPlainText(txt)
        else:
            self.text_analyse.setPlainText("❌ Aucune pièce solide détectée.")

    # ============================================================
    # ⚖️ Poids pièce + brut
    # ============================================================
    def compute_weights(self):
        doc = FreeCAD.ActiveDocument

        part = None
        stock = None

        # Identification pièce + brut
        for obj in doc.Objects:
            if hasattr(obj, "Shape"):
                if obj.Name.startswith("Stock"):
                    stock = obj
                else:
                    part = obj

        if part is None:
            self.text_weight.setPlainText("❌ Impossible : aucune pièce détectée.")
            return

        mat = self.combo_material.currentText()
        rho = MATERIALS.get(mat, 0)

        # Volume pièce
        v_piece_mm3 = part.Shape.Volume
        v_piece_m3 = v_piece_mm3 * 1e-9
        m_piece = v_piece_m3 * rho

        lines = []
        lines.append(f"📌 Matière : {mat}  (ρ = {rho} kg/m³)")
        lines.append("--------------------------")
        lines.append(f"🟦 Volume pièce : {v_piece_mm3:,.0f} mm³")
        lines.append(f"🟦 Poids pièce : {m_piece:,.2f} kg")
        lines.append("")

        # Volume brut
        if stock:
            v_brut_mm3 = stock.Shape.Volume
            v_brut_m3 = v_brut_mm3 * 1e-9
            m_brut = v_brut_m3 * rho
            m_remove = m_brut - m_piece

            lines.append(f"🟧 Volume brut : {v_brut_mm3:,.0f} mm³")
            lines.append(f"🟧 Poids brut : {m_brut:,.2f} kg")
            lines.append("")
            lines.append(f"🛠️ Matière à enlever : {m_remove:,.2f} kg")
        else:
            lines.append("❌ Aucun brut généré.")

        self.text_weight.setPlainText("\n".join(lines))

    # ============================================================
    # 🟦 Onglet Brut Intelligent
    # ============================================================
    def _init_tab_stock(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)

        # --- Section Auto ---
        group_auto = QtWidgets.QGroupBox("Brut intelligent (auto)")
        auto_layout = QtWidgets.QFormLayout(group_auto)

        self.lbl_type = QtWidgets.QLabel("-")
        self.lbl_orientation = QtWidgets.QLabel("-")
        self.lbl_auto_margins = QtWidgets.QLabel("-")

        auto_layout.addRow("Type de brut :", self.lbl_type)
        auto_layout.addRow("Orientation principale :", self.lbl_orientation)
        auto_layout.addRow("Surépaisseurs auto :", self.lbl_auto_margins)

        layout.addWidget(group_auto)

        # --- Override type de brut ---
        group_override = QtWidgets.QGroupBox("Forcer le type de brut")
        override_layout = QtWidgets.QHBoxLayout(group_override)

        self.chk_force_block = QtWidgets.QCheckBox("Forcer bloc")
        self.chk_force_cylinder = QtWidgets.QCheckBox("Forcer cylindre")

        override_layout.addWidget(self.chk_force_block)
        override_layout.addWidget(self.chk_force_cylinder)

        self.chk_force_block.stateChanged.connect(self._force_block_selected)
        self.chk_force_cylinder.stateChanged.connect(self._force_cylinder_selected)

        layout.addWidget(group_override)

        # --- Orientation du cylindre ---
        group_orient = QtWidgets.QGroupBox("Orientation du cylindre")
        orient_layout = QtWidgets.QHBoxLayout(group_orient)

        self.rb_orient_auto = QtWidgets.QRadioButton("Auto")
        self.rb_orient_x = QtWidgets.QRadioButton("X")
        self.rb_orient_y = QtWidgets.QRadioButton("Y")
        self.rb_orient_z = QtWidgets.QRadioButton("Z")
        self.rb_orient_auto.setChecked(True)

        orient_layout.addWidget(self.rb_orient_auto)
        orient_layout.addWidget(self.rb_orient_x)
        orient_layout.addWidget(self.rb_orient_y)
        orient_layout.addWidget(self.rb_orient_z)

        layout.addWidget(group_orient)

        # --- Dimensions cylindre (manuel)
        group_cyl = QtWidgets.QGroupBox("Dimensions brut cylindre (mm)")
        cyl_layout = QtWidgets.QFormLayout(group_cyl)

        self.edit_cyl_diameter = QtWidgets.QLineEdit("")
        self.edit_cyl_length = QtWidgets.QLineEdit("")

        validator_cyl = QtGui.QDoubleValidator(0.0, 10000.0, 3)
        self.edit_cyl_diameter.setValidator(validator_cyl)
        self.edit_cyl_length.setValidator(validator_cyl)

        cyl_layout.addRow("Diamètre :", self.edit_cyl_diameter)
        cyl_layout.addRow("Longueur :", self.edit_cyl_length)

        layout.addWidget(group_cyl)

        # --- Surépaisseurs manuelles ---
        group_margins = QtWidgets.QGroupBox("Surépaisseurs manuelles (mm)")
        grid = QtWidgets.QGridLayout(group_margins)

        grid.addWidget(QtWidgets.QLabel(""), 0, 0)
        grid.addWidget(QtWidgets.QLabel("-"), 0, 1)
        grid.addWidget(QtWidgets.QLabel("+"), 0, 2)

        # Ligne X
        grid.addWidget(QtWidgets.QLabel("X"), 1, 0)
        self.edit_x_minus = QtWidgets.QLineEdit("2.0")
        self.edit_x_plus = QtWidgets.QLineEdit("2.0")
        grid.addWidget(self.edit_x_minus, 1, 1)
        grid.addWidget(self.edit_x_plus, 1, 2)

        # Ligne Y
        grid.addWidget(QtWidgets.QLabel("Y"), 2, 0)
        self.edit_y_minus = QtWidgets.QLineEdit("2.0")
        self.edit_y_plus = QtWidgets.QLineEdit("2.0")
        grid.addWidget(self.edit_y_minus, 2, 1)
        grid.addWidget(self.edit_y_plus, 2, 2)

        # Ligne Z
        grid.addWidget(QtWidgets.QLabel("Z"), 3, 0)
        self.edit_z_minus = QtWidgets.QLineEdit("3.0")
        self.edit_z_plus = QtWidgets.QLineEdit("1.0")
        grid.addWidget(self.edit_z_minus, 3, 1)
        grid.addWidget(self.edit_z_plus, 3, 2)

        validator = QtGui.QDoubleValidator(0.0, 10000.0, 3)
        for w in [
            self.edit_x_minus,
            self.edit_x_plus,
            self.edit_y_minus,
            self.edit_y_plus,
            self.edit_z_minus,
            self.edit_z_plus,
        ]:
            w.setValidator(validator)

        layout.addWidget(group_margins)

        # --- Boutons ---
        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_auto = QtWidgets.QPushButton("Recalculer auto")
        self.btn_generate = QtWidgets.QPushButton("Générer brut intelligent")

        self.btn_auto.clicked.connect(self.recompute_auto)
        self.btn_generate.clicked.connect(self.generate_stock)

        btn_layout.addWidget(self.btn_auto)
        btn_layout.addWidget(self.btn_generate)

        layout.addLayout(btn_layout)

        # --- Résultat
        self.text_stock = QtWidgets.QTextEdit()
        self.text_stock.setReadOnly(True)
        layout.addWidget(self.text_stock)

        self.tabs.addTab(tab, "Brut intelligent")


    # ============================================================
    # 🔧 Helpers UI Brut
    # ============================================================
    def _force_block_selected(self, state):
        if state == QtCore.Qt.Checked:
            self.chk_force_cylinder.setChecked(False)

    def _force_cylinder_selected(self, state):
        if state == QtCore.Qt.Checked:
            self.chk_force_block.setChecked(False)

    def _read_margin(self, widget, fallback):
        txt = widget.text().replace(",", ".")
        try:
            v = float(txt)
        except ValueError:
            v = fallback
        return max(v, 0.0)

    # ============================================================
    # 🧠 Brut intelligent (auto + génération)
    # ============================================================
    def _compute_auto_info(self, shape):
        stock_type = detect_best_stock_type(shape)
        auto_margins = compute_auto_margins(shape)
        orientation = compute_best_orientation(shape)

        self.lbl_type.setText("Cylindre" if stock_type == "cylinder" else "Bloc")
        self.lbl_orientation.setText(orientation)
        self.lbl_auto_margins.setText(
            f"X-={auto_margins['x_minus']} / X+={auto_margins['x_plus']} — "
            f"Y-={auto_margins['y_minus']} / Y+={auto_margins['y_plus']} — "
            f"Z-={auto_margins['z_minus']} / Z+={auto_margins['z_plus']}"
        )

        return stock_type, auto_margins, orientation

    def recompute_auto(self):
        extractor = GeometryExtractor()
        if not extractor.load_part():
            self.text_stock.setPlainText("❌ Aucune pièce active pour le brut.")
            return

        shape = extractor.shape
        stock_type, auto_margins, orientation = self._compute_auto_info(shape)

        self.text_stock.setPlainText(
            "Surépaisseurs automatiques recalculées.\n"
            f"Type : {'Cylindre' if stock_type == 'cylinder' else 'Bloc'}\n"
            f"Orientation principale : {orientation}\n"
        )

    def generate_stock(self):
        extractor = GeometryExtractor()
        if not extractor.load_part():
            self.text_stock.setPlainText("❌ Aucune pièce active pour le brut.")
            return

        shape = extractor.shape

        # Auto info
        stock_type, auto_margins, orientation_auto = self._compute_auto_info(shape)

        # Override bloc / cylindre
        force_block = self.chk_force_block.isChecked()
        force_cyl = self.chk_force_cylinder.isChecked()

        # Surépaisseurs manuelles
        margins = {
            "x_minus": self._read_margin(self.edit_x_minus, auto_margins["x_minus"]),
            "x_plus": self._read_margin(self.edit_x_plus, auto_margins["x_plus"]),
            "y_minus": self._read_margin(self.edit_y_minus, auto_margins["y_minus"]),
            "y_plus": self._read_margin(self.edit_y_plus, auto_margins["y_plus"]),
            "z_minus": self._read_margin(self.edit_z_minus, auto_margins["z_minus"]),
            "z_plus": self._read_margin(self.edit_z_plus, auto_margins["z_plus"]),
        }

        # Dimensions cylindre (manuel)
        cyl_diameter = (
            float(self.edit_cyl_diameter.text().replace(",", "."))
            if self.edit_cyl_diameter.text().strip()
            else None
        )
        cyl_length = (
            float(self.edit_cyl_length.text().replace(",", "."))
            if self.edit_cyl_length.text().strip()
            else None
        )

        # Orientation manuelle ou auto
        if self.rb_orient_x.isChecked():
            orientation_override = "X"
        elif self.rb_orient_y.isChecked():
            orientation_override = "Y"
        elif self.rb_orient_z.isChecked():
            orientation_override = "Z"
        else:
            orientation_override = None  # auto

        # Création du brut intelligent
        obj, final_type, auto_m, orient = create_intelligent_stock(
            shape,
            margins=margins,
            allow_cylinder=(not force_block),
            force_cylinder=force_cyl,
            orientation_override=orientation_override,
            transparency=70,
            cyl_diameter=cyl_diameter,
            cyl_length=cyl_length,
        )

        # Dimensions du brut
        bb = obj.Shape.BoundBox

        if final_type == "block":
            dim_details = (
                f"Dimensions brut (bloc) :\n"
                f"  X = {bb.XLength:.3f} mm\n"
                f"  Y = {bb.YLength:.3f} mm\n"
                f"  Z = {bb.ZLength:.3f} mm\n"
            )
        else:
            diameter = max(bb.XLength, bb.YLength)
            length = bb.ZLength
            dim_details = (
                f"Dimensions brut (cylindre) :\n"
                f"  Diamètre = {diameter:.3f} mm\n"
                f"  Longueur = {length:.3f} mm\n"
            )

        # Affichage résultat
        txt = (
            "✔ Brut intelligent créé.\n"
            f"Type : {'Cylindre' if final_type == 'cylinder' else 'Bloc'}\n"
            f"Orientation principale : {orient}\n"
            f"{dim_details}"
            f"Surépaisseurs finales : "
            f"X-={margins['x_minus']} / X+={margins['x_plus']} — "
            f"Y-={margins['y_minus']} / Y+={margins['y_plus']} — "
            f"Z-={margins['z_minus']} / Z+={margins['z_plus']}\n"
        )

        self.text_stock.setPlainText(txt)
    # ============================================================
    # 🛠 Onglet Usinage (Débit copeaux + CAM)
    # ============================================================
    def _init_tab_machining(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)

        # ----- Sélection face + type d’usinage -----
        group_sel = QtWidgets.QGroupBox("Sélection & type d’usinage")
        g_sel = QtWidgets.QGridLayout(group_sel)

        self.lbl_selected_face = QtWidgets.QLabel("Aucune face sélectionnée.")
        btn_read_sel = QtWidgets.QPushButton("Lire la sélection FreeCAD")
        btn_read_sel.clicked.connect(self.on_read_selection)

        g_sel.addWidget(QtWidgets.QLabel("Face sélectionnée :"), 0, 0)
        g_sel.addWidget(self.lbl_selected_face, 0, 1)
        g_sel.addWidget(btn_read_sel, 0, 2)

        self.combo_operation = QtWidgets.QComboBox()
        self.combo_operation.addItems([
            "Surfaçage",
            "Poche",
            "Perçage",
            "Contournage",
            "Rainurage",
            "Chanfrein",
        ])

        g_sel.addWidget(QtWidgets.QLabel("Type d’usinage :"), 1, 0)
        g_sel.addWidget(self.combo_operation, 1, 1, 1, 2)

        layout.addWidget(group_sel)

        # ----- Outil -----
        group_tool = QtWidgets.QGroupBox("Outil")
        g_tool = QtWidgets.QFormLayout(group_tool)

        self.combo_tool = QtWidgets.QComboBox()
        self.combo_tool.addItems(get_all_tool_names())
        self.combo_tool.currentTextChanged.connect(self.on_tool_changed)

        self.edit_tool_diam = QtWidgets.QLineEdit()
        self.edit_tool_z = QtWidgets.QLineEdit()

        g_tool.addRow("Outil :", self.combo_tool)
        g_tool.addRow("Ø (mm) :", self.edit_tool_diam)
        g_tool.addRow("Z dents :", self.edit_tool_z)

        layout.addWidget(group_tool)

        # ----- Conditions de coupe + engagement -----
        group_cut = QtWidgets.QGroupBox("Conditions de coupe")
        g_cut = QtWidgets.QFormLayout(group_cut)

        self.edit_vc = QtWidgets.QLineEdit("150.0")
        self.edit_fz = QtWidgets.QLineEdit("0.05")
        self.edit_ap = QtWidgets.QLineEdit("5.0")
        self.edit_ae_percent = QtWidgets.QLineEdit("20")  # engagement par défaut

        g_cut.addRow("Vc (m/min) :", self.edit_vc)
        g_cut.addRow("Fz (mm/dent) :", self.edit_fz)
        g_cut.addRow("Ap (mm) :", self.edit_ap)
        g_cut.addRow("Ae (% engagement fraise) :", self.edit_ae_percent)

        layout.addWidget(group_cut)

        # ----- Paramètres géométriques opération -----
        group_op = QtWidgets.QGroupBox("Paramètres opération")
        g_op = QtWidgets.QFormLayout(group_op)

        self.lbl_depth = QtWidgets.QLabel("Profondeur (mm) :")
        self.edit_depth = QtWidgets.QLineEdit("5.0")

        self.lbl_nb_holes = QtWidgets.QLabel("Nb trous (perçage) :")
        self.edit_nb_holes = QtWidgets.QLineEdit("1")

        self.lbl_hole_diam = QtWidgets.QLabel("Ø trou (mm, perçage) :")
        self.edit_hole_diam = QtWidgets.QLineEdit("")

        self.lbl_length = QtWidgets.QLabel("Longueur (contour/rainure) (mm) :")
        self.edit_length = QtWidgets.QLineEdit("")

        self.lbl_slot_width = QtWidgets.QLabel("Largeur rainure (mm) :")
        self.edit_slot_width = QtWidgets.QLineEdit("")

        self.lbl_chipflow = QtWidgets.QLabel("Débit copeaux manuel (cm³/min) :")
        self.edit_chipflow = QtWidgets.QLineEdit("")

        g_op.addRow(self.lbl_depth, self.edit_depth)
        g_op.addRow(self.lbl_nb_holes, self.edit_nb_holes)
        g_op.addRow(self.lbl_hole_diam, self.edit_hole_diam)
        g_op.addRow(self.lbl_length, self.edit_length)
        g_op.addRow(self.lbl_slot_width, self.edit_slot_width)
        g_op.addRow(self.lbl_chipflow, self.edit_chipflow)

        layout.addWidget(group_op)

        # ----- Mode de calcul -----
        group_mode = QtWidgets.QGroupBox("Mode de calcul")
        g_mode = QtWidgets.QGridLayout(group_mode)

        self.rb_mode_chip = QtWidgets.QRadioButton("Débit copeaux")
        self.rb_mode_cam = QtWidgets.QRadioButton("CAM (parcours)")
        self.rb_mode_chip.setChecked(True)

        g_mode.addWidget(self.rb_mode_chip, 0, 0)
        g_mode.addWidget(self.rb_mode_cam, 0, 1)

        # zone sélection opération CAM (Option B)
        self.combo_cam_op = QtWidgets.QComboBox()
        btn_refresh_cam = QtWidgets.QPushButton("Rafraîchir les opérations CAM")
        btn_refresh_cam.clicked.connect(self.refresh_cam_operations)

        g_mode.addWidget(QtWidgets.QLabel("Opération CAM :"), 1, 0)
        g_mode.addWidget(self.combo_cam_op, 1, 1)
        g_mode.addWidget(btn_refresh_cam, 1, 2)

        layout.addWidget(group_mode)

        # ----- Bouton calcul + résultat -----
        btn_calc = QtWidgets.QPushButton("Calculer le temps d’usinage")
        btn_calc.clicked.connect(self.on_compute_machining_time)
        layout.addWidget(btn_calc)

        self.text_machining = QtWidgets.QTextEdit()
        self.text_machining.setReadOnly(True)
        layout.addWidget(self.text_machining)
        
        # ----- Coût horaire -----
        group_cost = QtWidgets.QGroupBox("Coût")
        cost_layout = QtWidgets.QFormLayout(group_cost)

        self.edit_rate = QtWidgets.QLineEdit("60.0")  # €/h par défaut
        cost_layout.addRow("Taux horaire machine (€/h) :", self.edit_rate)

        layout.addWidget(group_cost)

        # ----- Liste des opérations -----
        group_list = QtWidgets.QGroupBox("Liste des opérations")
        v_list = QtWidgets.QVBoxLayout(group_list)

        self.ops_table = QtWidgets.QTableWidget(0, 4)
        self.ops_table.setHorizontalHeaderLabels(["#", "Type", "Temps (h)", "Source"])
        self.ops_table.horizontalHeader().setStretchLastSection(True)
        self.ops_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.ops_table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)

        v_list.addWidget(self.ops_table)

        # Boutons de gestion
        btn_row_layout = QtWidgets.QHBoxLayout()
        self.btn_remove_op = QtWidgets.QPushButton("Supprimer l'opération")
        self.btn_clear_ops = QtWidgets.QPushButton("Vider la liste")
        btn_row_layout.addWidget(self.btn_remove_op)
        btn_row_layout.addWidget(self.btn_clear_ops)
        v_list.addLayout(btn_row_layout)

        # Totaux
        total_layout = QtWidgets.QHBoxLayout()
        self.lbl_total_time = QtWidgets.QLabel("Temps total : 0.00 h")
        self.lbl_total_cost = QtWidgets.QLabel("Coût total : 0.00 €")
        total_layout.addWidget(self.lbl_total_time)
        total_layout.addWidget(self.lbl_total_cost)
        v_list.addLayout(total_layout)

        layout.addWidget(group_list)

        # Connexions liste opérations
        self.btn_remove_op.clicked.connect(self.on_remove_selected_operation)
        self.btn_clear_ops.clicked.connect(self.on_clear_operations)


        self.tabs.addTab(tab, "Usinage")

        # initialiser l'outil
        if self.combo_tool.count() > 0:
            self.on_tool_changed(self.combo_tool.currentText())

        # UI dynamique selon opération
        self.combo_operation.currentTextChanged.connect(self.update_operation_fields)
        self.update_operation_fields(self.combo_operation.currentText())

    # ---------- Helpers onglet Usinage ----------
    def _parse_float(self, widget, default=None):
        txt = widget.text().strip().replace(",", ".")
        if not txt:
            return default
        try:
            return float(txt)
        except ValueError:
            return default

    def _parse_int(self, widget, default=None):
        txt = widget.text().strip()
        if not txt:
            return default
        try:
            return int(txt)
        except ValueError:
            return default

    def on_tool_changed(self, tool_name):
        """Met à jour Ø et Z quand l’utilisateur change d’outil."""
        data = get_tool(tool_name)
        if not data:
            return
        self.edit_tool_diam.setText(str(data.get("diam", "")))
        self.edit_tool_z.setText(str(data.get("z", "")))

    def on_read_selection(self):
        import FreeCADGui

        sel = FreeCADGui.Selection.getSelectionEx()
        if not sel:
            self.selected_faces = []
            self.selected_obj = None
            self.lbl_selected_face.setText("❌ Aucune face sélectionnée.")
            return

        self.selected_faces = []
        self.selected_obj = sel[0].Object
        face_names = []

        for s in sel:
            for face, name in zip(s.SubObjects, s.SubElementNames):
                if isinstance(face, Part.Face):
                    self.selected_faces.append(face)
                    face_names.append(name)

        if not self.selected_faces:
            self.lbl_selected_face.setText("❌ Aucun élément de type Face.")
        else:
            self.lbl_selected_face.setText(
                f"{self.selected_obj.Label} / " + ", ".join(face_names)
            )

    # ---------- UI dynamique selon opération ----------
    def update_operation_fields(self, op_type):

        widgets = [
            (self.lbl_depth, self.edit_depth),
            (self.lbl_nb_holes, self.edit_nb_holes),
            (self.lbl_hole_diam, self.edit_hole_diam),
            (self.lbl_length, self.edit_length),
            (self.lbl_slot_width, self.edit_slot_width),
            (self.lbl_chipflow, self.edit_chipflow),
        ]
        for label, edit in widgets:
            label.setVisible(False)
            edit.setVisible(False)

        if op_type == "Surfaçage":
            self.edit_ae_percent.setText("70")
            self.lbl_depth.setVisible(True)
            self.edit_depth.setVisible(True)

        elif op_type == "Poche":
            self.edit_ae_percent.setText("40")
            self.lbl_depth.setVisible(True)
            self.edit_depth.setVisible(True)

        elif op_type == "Perçage":
            self.lbl_depth.setVisible(True)
            self.edit_depth.setVisible(True)
            self.lbl_nb_holes.setVisible(True)
            self.edit_nb_holes.setVisible(True)
            self.lbl_hole_diam.setVisible(True)
            self.edit_hole_diam.setVisible(True)

        elif op_type == "Contournage":
            self.edit_ae_percent.setText("100")
            self.lbl_depth.setVisible(True)
            self.edit_depth.setVisible(True)
            self.lbl_length.setVisible(True)
            self.edit_length.setVisible(True)

        elif op_type == "Rainurage":
            self.edit_ae_percent.setText("50")
            self.lbl_depth.setVisible(True)
            self.edit_depth.setVisible(True)
            self.lbl_length.setVisible(True)
            self.edit_length.setVisible(True)
            self.lbl_slot_width.setVisible(True)
            self.edit_slot_width.setVisible(True)

        elif op_type == "Chanfrein":
            self.lbl_depth.setVisible(True)
            self.edit_depth.setVisible(True)

    # ---------- Longueur de contour automatique ----------
    def compute_contour_length(self):
        """Calcule la longueur totale du contour à partir des faces sélectionnées."""
        if not self.selected_faces:
            return None

        total_length = 0.0
        for face in self.selected_faces:
            for edge in face.Edges:
                total_length += edge.Length
        return total_length
    # ---------- Gestion de la liste d'opérations ----------
    def register_operation(self, op_type, temps_h, source):
        """Ajoute une opération dans le tableau et recalcule temps + coût."""
        if temps_h is None or temps_h <= 0:
            return

        row = self.ops_table.rowCount()
        self.ops_table.insertRow(row)

        self.ops_table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(row + 1)))
        self.ops_table.setItem(row, 1, QtWidgets.QTableWidgetItem(op_type))
        self.ops_table.setItem(row, 2, QtWidgets.QTableWidgetItem(f"{temps_h:.2f}"))
        self.ops_table.setItem(row, 3, QtWidgets.QTableWidgetItem(source))

        self.recompute_totals()

    def renumber_operations(self):
        """Réindexe la première colonne (#)."""
        for row in range(self.ops_table.rowCount()):
            item = self.ops_table.item(row, 0)
            if not item:
                item = QtWidgets.QTableWidgetItem()
                self.ops_table.setItem(row, 0, item)
            item.setText(str(row + 1))

    def on_remove_selected_operation(self):
        rows = sorted({idx.row() for idx in self.ops_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.ops_table.removeRow(row)
        if rows:
            self.renumber_operations()
            self.recompute_totals()

    def on_clear_operations(self):
        self.ops_table.setRowCount(0)
        self.recompute_totals()

    def recompute_totals(self):
        """Recalcule temps total et coût total à partir de la table."""
        total_h = 0.0
        for row in range(self.ops_table.rowCount()):
            item = self.ops_table.item(row, 2)
            if not item:
                continue
            txt = item.text().replace(",", ".")
            try:
                total_h += float(txt)
            except ValueError:
                continue

        self.lbl_total_time.setText(f"Temps total : {total_h:.2f} h")

        rate = self._parse_float(self.edit_rate, default=0.0) or 0.0
        cost = total_h * rate
        self.lbl_total_cost.setText(f"Coût total : {cost:.2f} €")

    # ---------- CAM : rafraîchir les opérations ----------
    def refresh_cam_operations(self):
        """Liste les opérations CAM (objets avec Path non vide)."""
        doc = FreeCAD.ActiveDocument
        if not doc:
            self.text_machining.setPlainText("❌ Aucun document actif.")
            return

        self.combo_cam_op.clear()
        self.cam_ops_index = []

        for obj in doc.Objects:
            if hasattr(obj, "Path") and obj.Path is not None:
                label = f"{obj.Label} [{obj.Name}]"
                self.combo_cam_op.addItem(label)
                self.cam_ops_index.append((label, obj.Name))

        if not self.cam_ops_index:
            self.text_machining.setPlainText(
                "❌ Aucune opération CAM avec parcours détectée.\n"
                "Créez d’abord un Job + opérations dans l’atelier CAM."
            )
        else:
            self.text_machining.setPlainText(
                f"{len(self.cam_ops_index)} opération(s) CAM détectée(s)."
            )

    # ---------- Calcul temps usinage ----------
    def on_compute_machining_time(self):
        op_type = self.combo_operation.currentText()

        depth = self._parse_float(self.edit_depth, default=0.0)
        if depth is None or depth <= 0:
            self.text_machining.setPlainText("❌ Profondeur invalide.")
            return

        volume_mm3 = 0.0
        length_for_contour = None

        # --- Volume à enlever (mm3) selon type ---
        if op_type in ("Surfaçage", "Poche", "Chanfrein"):
            if not self.selected_faces:
                self.text_machining.setPlainText("❌ Aucune face sélectionnée.")
                return
            # On prend la première face pour l’aire
            area = self.selected_faces[0].Area  # mm²
            if op_type == "Chanfrein":
                op = MachiningOperation(op_type, depth, area=area, chamfer_width=1.0)
            else:
                op = MachiningOperation(op_type, depth, area=area)
            volume_mm3 = compute_volume_mm3(op)

        elif op_type == "Perçage":
            nb = self._parse_int(self.edit_nb_holes, default=1)
            hole_diam = self._parse_float(self.edit_hole_diam, default=None)
            if hole_diam is None:
                self.text_machining.setPlainText("❌ Ø trou invalide.")
                return
            op = MachiningOperation(op_type, depth, nb_holes=nb, hole_diam=hole_diam)
            volume_mm3 = compute_volume_mm3(op)

        elif op_type == "Rainurage":
            length = self._parse_float(self.edit_length, default=None)
            width = self._parse_float(self.edit_slot_width, default=None)
            if length is None or width is None:
                self.text_machining.setPlainText("❌ Longueur ou largeur rainure manquante.")
                return
            op = MachiningOperation(op_type, depth, length=length, width=width)
            volume_mm3 = compute_volume_mm3(op)

        elif op_type == "Contournage":
            # Essayer d'abord la valeur saisie
            length = self._parse_float(self.edit_length, default=None)

            # Si pas de valeur manuelle → calcul automatique
            if length is None:
                auto_length = self.compute_contour_length()
                if auto_length is None or auto_length <= 0:
                    self.text_machining.setPlainText(
                        "❌ Impossible de calculer la longueur du contour.\n"
                        "Sélectionnez les faces latérales du contour."
                    )
                    return
                length = auto_length
                self.edit_length.setText(f"{length:.2f}")

            length_for_contour = length

        else:
            self.text_machining.setPlainText(f"❌ Type d’usinage non géré : {op_type}")
            return

        # --- Paramètres outil / coupe ---
        tool_diam = self._parse_float(self.edit_tool_diam, default=None)
        z = self._parse_int(self.edit_tool_z, default=None)
        vc = self._parse_float(self.edit_vc, default=None)
        fz = self._parse_float(self.edit_fz, default=None)
        ap = self._parse_float(self.edit_ap, default=None)
        ae_percent = self._parse_float(self.edit_ae_percent, default=None)

        if ae_percent is None or not (0 < ae_percent <= 100):
            self.text_machining.setPlainText("❌ Engagement Ae% invalide.")
            return
        ae = (ae_percent / 100.0) * tool_diam if tool_diam else None

        if not all([tool_diam, z, vc, fz, ap, ae]):
            self.text_machining.setPlainText("❌ Paramètres outil / coupe incomplets.")
            return

        # Volume pour contournage (après calcul Ae)
        if op_type == "Contournage":
            volume_mm3 = length_for_contour * ae * depth

        if volume_mm3 <= 0:
            self.text_machining.setPlainText("❌ Volume à enlever nul ou négatif.")
            return

        volume_cm3 = volume_mm3 / 1000.0

        # Débit override éventuel
        chip_override = self._parse_float(self.edit_chipflow, default=None)

        # ===== Mode débit copeaux =====
        if self.rb_mode_chip.isChecked():
            res = compute_chip_based_time(
                tool_diam_mm=tool_diam,
                z=z,
                vc_m_min=vc,
                fz_mm=fz,
                ap_mm=ap,
                ae_mm=ae,
                volume_mm3=volume_mm3,
                chipflow_override_cm3_min=chip_override,
            )

            temps_h = res["time_min"] / 60.0

            txt = []
            txt.append(f"Type d’usinage : {op_type}")
            txt.append(f"Volume enlevé : {volume_cm3:.2f} cm³")
            txt.append("")
            txt.append(f"n (tr/min) : {res['rpm']:.0f}")
            txt.append(f"Vf (mm/min) : {res['feed_mm_min']:.0f}")
            txt.append(f"Débit copeaux : {res['chip_cm3_min']:.2f} cm³/min")
            txt.append("")
            txt.append(f"Temps (centièmes d’heure) : {temps_h:.2f} h")

            self.text_machining.setPlainText("\n".join(txt))

            # Ajout à la liste des opérations
            self.register_operation(op_type, temps_h, source="Débit copeaux")

            return

        # ===== Mode CAM =====
        if self.rb_mode_cam.isChecked():
            doc = FreeCAD.ActiveDocument
            if not doc:
                self.text_machining.setPlainText("❌ Aucun document actif.")
                return

            if not self.cam_ops_index or self.combo_cam_op.currentIndex() < 0:
                self.text_machining.setPlainText(
                    "❌ Aucune opération CAM sélectionnée.\n"
                    "Clique sur « Rafraîchir » puis sélectionne une opération."
                )
                return

            _, op_name = self.cam_ops_index[self.combo_cam_op.currentIndex()]
            op_cam = doc.getObject(op_name)

            rpm = compute_rpm(vc, tool_diam)
            feed_mm_min = compute_feed(rpm, z, fz)

            if feed_mm_min <= 0:
                self.text_machining.setPlainText("❌ Avance calculée nulle ou négative.")
                return

            cam_res = compute_time_from_path_op(
                op_cam,
                feed_mm_min=feed_mm_min,
                rapid_feed_mm_min=feed_mm_min * 3.0,
                include_rapids=True,
            )

            temps_h = cam_res["time_total_min"] / 60.0

            txt = []
            txt.append(f"Type d’usinage : {op_type}")
            txt.append(f"Volume approx : {volume_cm3:.2f} cm³")
            txt.append("")
            txt.append(f"Outil : Ø{tool_diam} / Z={z}")
            txt.append(f"Vc={vc} m/min, Fz={fz} mm/dent")
            txt.append(f"Vf utilisée : {feed_mm_min:.0f} mm/min")
            txt.append("")
            txt.append(f"Longueur coupe : {cam_res['length_cut_mm']:.1f} mm")
            txt.append(f"Longueur rapides : {cam_res['length_rapid_mm']:.1f} mm")
            txt.append(f"Temps coupe : {cam_res['time_cut_min']:.2f} min")
            txt.append(f"Temps rapides : {cam_res['time_rapid_min']:.2f} min")
            txt.append(f"Temps total CAM (centièmes d’heure) : {temps_h:.2f} h")

            self.text_machining.setPlainText("\n".join(txt))

            # Ajout à la liste des opérations
            self.register_operation(op_type, temps_h, source="CAM")

            return


def show_panel():
    mw = FreeCADGui.getMainWindow()
    panel = PartCostingPanel()
    mw.addDockWidget(QtCore.Qt.RightDockWidgetArea, panel)
