import FreeCAD
import FreeCADGui
import Part

from PySide2 import QtWidgets, QtCore, QtGui

from geometry import GeometryExtractor
from stock_intelligent import (
    detect_best_stock_type,
    compute_auto_margins,
    create_intelligent_stock,
)

from machining_tools import get_all_tool_names, get_tool
from op_dialog import OperationDialog
from tool_manager import ToolManagerDialog


# ======================================================================
#  CONSTANTES MATIÈRES (densités kg/dm3)
# ======================================================================

MATERIALS = {
    "Acier": 7.85,
    "Aluminium": 2.70,
    "Inox": 8.00,
    "Fonte": 7.00,
    "Laiton": 8.40,
}


# ======================================================================
#  PANEL PRINCIPAL
# ======================================================================

class PartCostingPanel(QtWidgets.QDockWidget):
    """Panel principal Part Costing Pro."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Part Costing Pro")

        self.operations = []      # liste de dicts {type, time_h, mode}
        self.stocks = []          # objets FreeCAD marqués PC_IsStock
        self.selected_stock = None

        # Widget principal
        main_widget = QtWidgets.QWidget()
        main_layout = QtWidgets.QVBoxLayout(main_widget)

        self.tabs = QtWidgets.QTabWidget()
        main_layout.addWidget(self.tabs)

        self.setWidget(main_widget)

        # Onglets
        self._init_tab_analyse()
        self._init_tab_stock()
        self._init_tab_machining()

    # ==================================================================
    # ONGLET 1 : ANALYSE
    # ==================================================================
    def _init_tab_analyse(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)

        # Sélection pièce
        self.btn_analyse = QtWidgets.QPushButton("Analyser la pièce sélectionnée")
        self.btn_analyse.clicked.connect(self.on_analyse)
        layout.addWidget(self.btn_analyse)

        # Résumé géométrie
        self.text_geo = QtWidgets.QTextEdit()
        self.text_geo.setReadOnly(True)
        layout.addWidget(self.text_geo)

        # Choix matière
        form_mat = QtWidgets.QFormLayout()
        self.combo_material = QtWidgets.QComboBox()
        self.combo_material.addItems(list(MATERIALS.keys()))
        form_mat.addRow("Matière :", self.combo_material)
        layout.addLayout(form_mat)

        # Poids
        self.btn_weight = QtWidgets.QPushButton("Calculer les masses (pièce + brut)")
        self.btn_weight.clicked.connect(self.compute_weights)
        layout.addWidget(self.btn_weight)

        self.text_weight = QtWidgets.QTextEdit()
        self.text_weight.setReadOnly(True)
        layout.addWidget(self.text_weight)

        self.tabs.addTab(tab, "Analyse")

    def on_analyse(self):
        doc = FreeCAD.ActiveDocument
        if not doc:
            self.text_geo.setPlainText("❌ Aucun document actif.")
            return

        sel = FreeCADGui.Selection.getSelection()
        if not sel:
            self.text_geo.setPlainText("❌ Sélectionnez une pièce.")
            return

        obj = sel[0]
        if not hasattr(obj, "Shape"):
            self.text_geo.setPlainText("❌ L'objet sélectionné n'a pas de Shape.")
            return

        extractor = GeometryExtractor(obj.Shape)
        summary = extractor.summary()
        self.text_geo.setPlainText(summary)

    def compute_weights(self):
        doc = FreeCAD.ActiveDocument
        if not doc:
            self.text_weight.setPlainText("❌ Aucun document actif.")
            return

        part = self._find_reference_part()
        stock = self.selected_stock

        if not part:
            self.text_weight.setPlainText("❌ Aucune pièce détectée.")
            return

        rho = MATERIALS[self.combo_material.currentText()]  # kg/dm3
        v_piece = part.Shape.Volume * 1e-9  # mm3 → dm3
        m_piece = v_piece * rho

        txt = [f"🟦 Pièce : {m_piece:.2f} kg"]

        if stock and hasattr(stock, "Shape"):
            v_brut = stock.Shape.Volume * 1e-9
            m_brut = v_brut * rho
            txt += [
                f"🟧 Brut : {m_brut:.2f} kg",
                f"🛠️ Matière à enlever : {m_brut - m_piece:.2f} kg",
            ]
        else:
            txt += ["⚠️ Aucun brut sélectionné (onglet Brut)."]

        self.text_weight.setPlainText("\n".join(txt))

    # ==================================================================
    # ONGLET 2 : BRUT (STOCK)
    # ==================================================================
    def _init_tab_stock(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)

        # ----------- Liste des bruts existants -----------
        group_list = QtWidgets.QGroupBox("Bruts existants")
        v_list = QtWidgets.QVBoxLayout(group_list)

        self.combo_stocks = QtWidgets.QComboBox()
        self.combo_stocks.currentIndexChanged.connect(self.on_stock_changed)
        self.btn_refresh_stock = QtWidgets.QPushButton("Rafraîchir la liste")
        self.btn_refresh_stock.clicked.connect(self.refresh_stock_list)

        v_list.addWidget(self.combo_stocks)
        v_list.addWidget(self.btn_refresh_stock)

        layout.addWidget(group_list)

        # ----------- Création brut automatique -----------
        group_auto = QtWidgets.QGroupBox("Brut automatique (Bounding Box + surép internes)")
        v_auto = QtWidgets.QVBoxLayout(group_auto)

        self.lbl_auto_info = QtWidgets.QLabel(
            "Utilise la pièce sélectionnée.\n"
            "Type brut proposé (Bloc/Rond) + surép internes : XY = 2.5 | Z+ = 2 | Z- = 5."
        )
        v_auto.addWidget(self.lbl_auto_info)

        self.btn_new_auto = QtWidgets.QPushButton("Créer brut automatique")
        self.btn_new_auto.clicked.connect(self.create_auto_stock)
        v_auto.addWidget(self.btn_new_auto)

        layout.addWidget(group_auto)

        # ----------- Création brut manuel (dimensions réelles) -----------
        group_manual = QtWidgets.QGroupBox("Brut manuel (dimensions achetées)")
        v_man = QtWidgets.QVBoxLayout(group_manual)

        # Bloc
        group_block = QtWidgets.QGroupBox("Brut rectangulaire (bloc)")
        f_block = QtWidgets.QFormLayout(group_block)
        self.man_length = QtWidgets.QLineEdit()
        self.man_width = QtWidgets.QLineEdit()
        self.man_height = QtWidgets.QLineEdit()
        f_block.addRow("Longueur (X mm) :", self.man_length)
        f_block.addRow("Largeur (Y mm)  :", self.man_width)
        f_block.addRow("Épaisseur (Z mm):", self.man_height)

        # Cylindre
        group_cyl = QtWidgets.QGroupBox("Brut rond (barre / lopin)")
        f_cyl = QtWidgets.QFormLayout(group_cyl)
        self.man_diam = QtWidgets.QLineEdit()
        self.man_cyl_len = QtWidgets.QLineEdit()
        f_cyl.addRow("Diamètre (mm) :", self.man_diam)
        f_cyl.addRow("Longueur (mm) :", self.man_cyl_len)

        v_man.addWidget(group_block)
        v_man.addWidget(group_cyl)

        # Boutons création / mise à jour
        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_new_manual = QtWidgets.QPushButton("Créer brut manuel")
        self.btn_new_manual.clicked.connect(self.create_manual_stock)
        btn_layout.addWidget(self.btn_new_manual)

        self.btn_update_stock = QtWidgets.QPushButton("Mettre à jour le brut sélectionné")
        self.btn_update_stock.clicked.connect(self.update_current_stock_from_fields)
        btn_layout.addWidget(self.btn_update_stock)

        v_man.addLayout(btn_layout)

        layout.addWidget(group_manual)

        # ----------- Infos brut sélectionné -----------
        group_info = QtWidgets.QGroupBox("Informations brut")
        v_info = QtWidgets.QVBoxLayout(group_info)
        self.text_stock = QtWidgets.QTextEdit()
        self.text_stock.setReadOnly(True)
        v_info.addWidget(self.text_stock)
        layout.addWidget(group_info)

        self.tabs.addTab(tab, "Brut")

        # Init liste
        self.refresh_stock_list()

    # ----- Gestion liste stocks -----
    def refresh_stock_list(self):
        self.combo_stocks.clear()
        self.stocks = []
        self.selected_stock = None

        doc = FreeCAD.ActiveDocument
        if not doc:
            return

        for obj in doc.Objects:
            if hasattr(obj, "PC_IsStock") and getattr(obj, "PC_IsStock", False):
                self.stocks.append(obj)
                self.combo_stocks.addItem(obj.Label)

        if self.stocks:
            self.selected_stock = self.stocks[0]
            self.update_stock_info(self.selected_stock)
        else:
            self.text_stock.setPlainText("Aucun brut défini.\nUtilisez les boutons ci-dessus.")

    def on_stock_changed(self, idx):
        if idx < 0 or idx >= len(self.stocks):
            self.selected_stock = None
            self.text_stock.setPlainText("Aucun brut sélectionné.")
            return
        self.selected_stock = self.stocks[idx]
        self.update_stock_info(self.selected_stock)

    # ----- Création brut auto -----
    def create_auto_stock(self):
        doc = FreeCAD.ActiveDocument
        if not doc:
            QtWidgets.QMessageBox.warning(None, "Erreur", "Aucun document actif.")
            return

        sel = FreeCADGui.Selection.getSelection()
        if not sel:
            QtWidgets.QMessageBox.warning(None, "Erreur", "Sélectionnez la pièce (un seul objet).")
            return

        obj = sel[0]
        if not hasattr(obj, "Shape"):
            QtWidgets.QMessageBox.warning(None, "Erreur", "L'objet sélectionné n'a pas de Shape.")
            return

        shape = obj.Shape

        margins = compute_auto_margins(shape)
        stock_type = detect_best_stock_type(shape)

        stock, stock_type, margins_out, orientation = create_intelligent_stock(
            shape,
            margins=margins,
            stock_type=stock_type,
        )

        # Positionner le brut autour de la pièce (centré XY, Z- = 5)
        self._place_stock_around_part(stock)

        # Style visuel
        self._set_stock_visual(stock)

        doc.recompute()
        self.refresh_stock_list()
        self.update_stock_info(stock)

    # ----- Création brut manuel -----
    def create_manual_stock(self):
        doc = FreeCAD.ActiveDocument
        if not doc:
            QtWidgets.QMessageBox.warning(None, "Erreur", "Aucun document actif.")
            return

        # Bloc rectangulaire ?
        L = float(self.man_length.text() or 0)
        W = float(self.man_width.text() or 0)
        H = float(self.man_height.text() or 0)

        D = float(self.man_diam.text() or 0)
        Lc = float(self.man_cyl_len.text() or 0)

        obj = None
        stock_type = None

        # Cas bloc
        if L > 0 and W > 0 and H > 0:
            name = self._unique_name("StockBlock")
            obj = doc.addObject("Part::Box", name)
            obj.Length = L
            obj.Width = W
            obj.Height = H
            obj.Label = self._unique_label("BrutBloc_")
            stock_type = "Block"

        # Cas cylindre
        elif D > 0 and Lc > 0:
            name = self._unique_name("StockCylinder")
            obj = doc.addObject("Part::Cylinder", name)
            obj.Radius = D / 2.0
            obj.Height = Lc
            obj.Label = self._unique_label("BrutRond_")
            stock_type = "Cylinder"

        else:
            QtWidgets.QMessageBox.warning(
                None,
                "Erreur",
                "Dimensions de brut invalides.\n"
                "Remplissez soit bloc (L, l, e), soit rond (Ø, L).",
            )
            return

        # Tag PartCosting
        if not hasattr(obj, "PC_IsStock"):
            obj.addProperty("App::PropertyBool", "PC_IsStock", "PartCosting", "Objet brut PartCosting.")
        obj.PC_IsStock = True

        if not hasattr(obj, "PC_StockType"):
            obj.addProperty("App::PropertyString", "PC_StockType", "PartCosting", "Type de brut.")
        obj.PC_StockType = stock_type

        # Position automatique autour de la pièce
        self._place_stock_around_part(obj)
        self._set_stock_visual(obj)

        doc.recompute()
        self.refresh_stock_list()
        self.update_stock_info(obj)

    # ----- Mise à jour du brut sélectionné selon les champs -----
    def update_current_stock_from_fields(self):
        if not self.selected_stock:
            QtWidgets.QMessageBox.warning(None, "Erreur", "Aucun brut sélectionné.")
            return

        doc = FreeCAD.ActiveDocument
        if not doc:
            return

        typ = getattr(self.selected_stock, "PC_StockType", "Block")

        # Bloc
        if typ == "Block":
            try:
                L = float(self.man_length.text())
                W = float(self.man_width.text())
                H = float(self.man_height.text())
            except Exception:
                QtWidgets.QMessageBox.warning(None, "Erreur", "Dimensions bloc invalides.")
                return

            self.selected_stock.Length = L
            self.selected_stock.Width = W
            self.selected_stock.Height = H

        # Cylindre
        elif typ == "Cylinder":
            try:
                D = float(self.man_diam.text())
                Lc = float(self.man_cyl_len.text())
            except Exception:
                QtWidgets.QMessageBox.warning(None, "Erreur", "Dimensions cylindre invalides.")
                return

            self.selected_stock.Radius = D / 2.0
            self.selected_stock.Height = Lc

        # Repositionner autour de la pièce
        self._place_stock_around_part(self.selected_stock)
        self._set_stock_visual(self.selected_stock)

        doc.recompute()
        self.update_stock_info(self.selected_stock)

    # ----- Utils nommage / infos -----
    def _unique_name(self, prefix):
        doc = FreeCAD.ActiveDocument
        existing = {o.Name for o in doc.Objects}
        if prefix not in existing:
            return prefix
        i = 1
        while f"{prefix}{i}" in existing:
            i += 1
        return f"{prefix}{i}"

    def _unique_label(self, prefix):
        doc = FreeCAD.ActiveDocument
        existing = {o.Label for o in doc.Objects}
        i = 1
        while f"{prefix}{i:02d}" in existing:
            i += 1
        return f"{prefix}{i:02d}"

    def update_stock_info(self, stock):
        if not stock or not hasattr(stock, "Shape"):
            self.text_stock.setPlainText("Aucun brut sélectionné.")
            return

        typ = getattr(stock, "PC_StockType", "?")
        bb = stock.Shape.BoundBox

        txt = [
            f"Brut : {stock.Label}",
            f"Type : {typ}",
            "",
            f"X : {bb.XLength:.2f} mm",
            f"Y : {bb.YLength:.2f} mm",
            f"Z : {bb.ZLength:.2f} mm",
        ]
        self.text_stock.setPlainText("\n".join(txt))

        # Remplir les champs dimensions en fonction du type
        if typ == "Block":
            self.man_length.setText(f"{bb.XLength:.2f}")
            self.man_width.setText(f"{bb.YLength:.2f}")
            self.man_height.setText(f"{bb.ZLength:.2f}")
            self.man_diam.clear()
            self.man_cyl_len.clear()
        elif typ == "Cylinder":
            # On lit directement les propriétés Radius/Height plutôt que la bbox
            try:
                D = float(stock.Radius) * 2.0
                Lc = float(stock.Height)
            except Exception:
                D = bb.XLength   # fallback
                Lc = bb.ZLength
            self.man_diam.setText(f"{D:.2f}")
            self.man_cyl_len.setText(f"{Lc:.2f}")
            self.man_length.clear()
            self.man_width.clear()
            self.man_height.clear()

    # ----- Aide : trouver la pièce de référence -----
    def _find_reference_part(self):
        doc = FreeCAD.ActiveDocument
        if not doc:
            return None

        # On prend le premier objet avec Shape qui n'est pas un brut
        for obj in doc.Objects:
            if hasattr(obj, "Shape") and not getattr(obj, "PC_IsStock", False):
                return obj
        return None

    # ----- Aide : placer le brut autour de la pièce (centré XY, Z- = 5mm) -----
    def _place_stock_around_part(self, stock):
        part = self._find_reference_part()
        if not part or not hasattr(stock, "Shape"):
            return

        bbp = part.Shape.BoundBox   # bounding box pièce
        bbs = stock.Shape.BoundBox  # bounding box brut

        L = bbs.XLength
        W = bbs.YLength
        H = bbs.ZLength

        # Centre XY de la pièce
        cx = (bbp.XMin + bbp.XMax) * 0.5
        cy = (bbp.YMin + bbp.YMax) * 0.5

        # Base Z = Zmin pièce - 5mm (marge interne)
        z0 = bbp.ZMin - 5.0

        typ = getattr(stock, "PC_StockType", "Block")

        if typ == "Cylinder":
            # Cylindre : centre base au centre XY
            stock.Placement.Base = FreeCAD.Vector(cx, cy, z0)
        else:
            # Bloc : base = coin min
            x0 = cx - L * 0.5
            y0 = cy - W * 0.5
            stock.Placement.Base = FreeCAD.Vector(x0, y0, z0)

    # ----- Aide visuelle : transparence + mode d'affichage -----
    def _set_stock_visual(self, stock):
        try:
            vo = stock.ViewObject
            vo.Transparency = 70
            vo.DisplayMode = "Flat Lines"
        except Exception:
            pass

    # ==================================================================
    # ONGLET 3 : OPÉRATIONS / TEMPS
    # ==================================================================
    def _init_tab_machining(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)

        # Boutons haut
        btn_layout = QtWidgets.QHBoxLayout()

        btn_add = QtWidgets.QPushButton("➕ Ajouter une opération")
        btn_add.clicked.connect(self.on_add_operation)
        btn_layout.addWidget(btn_add)

        btn_tools = QtWidgets.QPushButton("🛠 Gérer les outils")
        btn_tools.clicked.connect(self.on_manage_tools)
        btn_layout.addWidget(btn_tools)

        layout.addLayout(btn_layout)

        # Tableau opérations
        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["#", "Type", "Temps (h)", "Mode"])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        # Totaux
        self.lbl_total_time = QtWidgets.QLabel("Temps total : 0.00 h")
        self.lbl_total_cost = QtWidgets.QLabel("Coût total : 0.00 €")
        layout.addWidget(self.lbl_total_time)
        layout.addWidget(self.lbl_total_cost)

        # Taux horaire
        form = QtWidgets.QFormLayout()
        self.edit_rate = QtWidgets.QLineEdit("60.0")
        form.addRow("Taux horaire (€/h) :", self.edit_rate)
        layout.addLayout(form)

        self.tabs.addTab(tab, "Opérations")

    # ==================================================================
    # Gestion des opérations
    # ==================================================================
    def on_add_operation(self):
        dlg = OperationDialog()
        if dlg.exec_() == QtWidgets.QDialog.Accepted and dlg.result:
            op = dlg.result
            self.operations.append(op)
            self._add_operation_to_table(op)
            self.recompute_totals()

    def _add_operation_to_table(self, op):
        row = self.table.rowCount()
        self.table.insertRow(row)

        item_idx = QtWidgets.QTableWidgetItem(str(row + 1))
        item_type = QtWidgets.QTableWidgetItem(op.get("type", ""))
        item_time = QtWidgets.QTableWidgetItem(f"{op.get('time_h', 0.0):.2f}")
        item_mode = QtWidgets.QTableWidgetItem(op.get("source", ""))

        self.table.setItem(row, 0, item_idx)
        self.table.setItem(row, 1, item_type)
        self.table.setItem(row, 2, item_time)
        self.table.setItem(row, 3, item_mode)

    # ==================================================================
    # 🛠 Gestion outils
    # ==================================================================
    def on_manage_tools(self):
        dlg = ToolManagerDialog()
        dlg.exec_()

    # ==================================================================
    # 🔢 Totaux
    # ==================================================================
    def recompute_totals(self):
        total_h = 0.0
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 2)
            if not item:
                continue
            try:
                total_h += float(item.text().replace(",", "."))
            except Exception:
                pass

        self.lbl_total_time.setText(f"Temps total : {total_h:.2f} h")

        try:
            rate = float(self.edit_rate.text().replace(",", "."))
        except Exception:
            rate = 0.0
        cost = rate * total_h
        self.lbl_total_cost.setText(f"Coût total : {cost:.2f} €")


# ======================================================================
# FONCTION D'AFFICHAGE DANS FREECAD
# ======================================================================

def show_panel():
    mw = FreeCADGui.getMainWindow()
    panel = PartCostingPanel()
    mw.addDockWidget(QtCore.Qt.RightDockWidgetArea, panel)
