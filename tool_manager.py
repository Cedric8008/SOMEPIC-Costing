import csv
import os

from PySide2 import QtWidgets, QtCore, QtGui
from machining_tools import get_all_tool_names, get_tool, TOOLS, load_tools


class ToolManagerDialog(QtWidgets.QDialog):
    """Fenêtre permettant la gestion complète des outils (tools.csv)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gestion des outils")
        self.resize(600, 450)

        layout = QtWidgets.QVBoxLayout(self)

        # ==================================================================
        # Tableau des outils
        # ==================================================================
        self.table = QtWidgets.QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Nom", "Diam", "Z", "Vc", "Fz", "Type"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QtWidgets.QTableWidget.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)

        layout.addWidget(self.table)

        # ==================================================================
        # Boutons gestion
        # ==================================================================
        btn_layout = QtWidgets.QHBoxLayout()

        self.btn_add = QtWidgets.QPushButton("Ajouter")
        self.btn_edit = QtWidgets.QPushButton("Modifier")
        self.btn_delete = QtWidgets.QPushButton("Supprimer")
        self.btn_reload = QtWidgets.QPushButton("Recharger")
        self.btn_save = QtWidgets.QPushButton("Enregistrer CSV")

        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_edit)
        btn_layout.addWidget(self.btn_delete)
        btn_layout.addWidget(self.btn_reload)
        btn_layout.addWidget(self.btn_save)

        layout.addLayout(btn_layout)

        # ==================================================================
        # Connexions
        # ==================================================================
        self.btn_add.clicked.connect(self.add_tool)
        self.btn_edit.clicked.connect(self.edit_tool)
        self.btn_delete.clicked.connect(self.delete_tool)
        self.btn_reload.clicked.connect(self.reload_table)
        self.btn_save.clicked.connect(self.save_csv)

        # ==================================================================
        # Charger outils
        # ==================================================================
        self.reload_table()

    # ======================================================================
    # Chargement du tableau
    # ======================================================================
    def reload_table(self):
        self.table.setRowCount(0)
        load_tools()

        for name in get_all_tool_names():
            tool = get_tool(name)
            row = self.table.rowCount()
            self.table.insertRow(row)

            self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(name))
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(tool.get("diam", ""))))
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(str(tool.get("z", ""))))
            self.table.setItem(row, 3, QtWidgets.QTableWidgetItem(str(tool.get("vc", ""))))
            self.table.setItem(row, 4, QtWidgets.QTableWidgetItem(str(tool.get("fz", ""))))
            self.table.setItem(row, 5, QtWidgets.QTableWidgetItem(tool.get("type", "")))

    # ======================================================================
    # Ajouter outil
    # ======================================================================
    def add_tool(self):
        dlg = ToolEditorDialog(parent=self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            data = dlg.get_tool_data()

            name = data["Name"]
            if name in TOOLS:
                QtWidgets.QMessageBox.warning(self, "Erreur", "Un outil avec ce nom existe déjà.")
                return

            TOOLS[name] = data
            self.reload_table()

    # ======================================================================
    # Modifier outil
    # ======================================================================
    def edit_tool(self):
        row = self.table.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.warning(self, "Erreur", "Sélectionnez un outil.")
            return

        name = self.table.item(row, 0).text()
        tool = TOOLS.get(name)
        if not tool:
            return

        dlg = ToolEditorDialog(initial_data=tool, parent=self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            new_data = dlg.get_tool_data()

            # si nom changé → suppression ancien
            if new_data["Name"] != name and new_data["Name"] in TOOLS:
                QtWidgets.QMessageBox.warning(self, "Erreur", "Nom déjà existant.")
                return

            del TOOLS[name]
            TOOLS[new_data["Name"]] = new_data
            self.reload_table()

    # ======================================================================
    # Supprimer outil
    # ======================================================================
    def delete_tool(self):
        row = self.table.currentRow()
        if row < 0:
            return

        name = self.table.item(row, 0).text()

        confirm = QtWidgets.QMessageBox.question(
            self, "Supprimer", f"Supprimer l’outil '{name}' ?"
        )
        if confirm != QtWidgets.QMessageBox.Yes:
            return

        if name in TOOLS:
            del TOOLS[name]

        self.reload_table()

    # ======================================================================
    # Sauvegarde CSV
    # ======================================================================
    def save_csv(self):
        """Écrit tools.csv en UTF-8 propre."""
        base_dir = os.path.dirname(__file__)
        csv_path = os.path.join(base_dir, "tools.csv")

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["Name", "Diam", "Z", "Vc", "Fz", "Type"])
            for name, data in TOOLS.items():
                writer.writerow([
                    name,
                    data.get("diam", ""),
                    data.get("z", ""),
                    data.get("vc", ""),
                    data.get("fz", ""),
                    data.get("type", ""),
                ])

        QtWidgets.QMessageBox.information(self, "OK", "tools.csv enregistré.")

# ======================================================================
# Éditeur d'un outil
# ======================================================================
class ToolEditorDialog(QtWidgets.QDialog):
    def __init__(self, initial_data=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Outil")
        self.resize(350, 300)

        layout = QtWidgets.QFormLayout(self)

        self.edit_name = QtWidgets.QLineEdit()
        self.edit_diam = QtWidgets.QLineEdit()
        self.edit_z = QtWidgets.QLineEdit()
        self.edit_vc = QtWidgets.QLineEdit()
        self.edit_fz = QtWidgets.QLineEdit()
        self.edit_type = QtWidgets.QLineEdit()

        layout.addRow("Nom :", self.edit_name)
        layout.addRow("Diamètre (mm) :", self.edit_diam)
        layout.addRow("Z dents :", self.edit_z)
        layout.addRow("Vc (m/min) :", self.edit_vc)
        layout.addRow("Fz (mm/dent) :", self.edit_fz)
        layout.addRow("Type :", self.edit_type)

        btns = QtWidgets.QHBoxLayout()
        btn_ok = QtWidgets.QPushButton("Valider")
        btn_cancel = QtWidgets.QPushButton("Annuler")

        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)

        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)

        layout.addRow(btns)

        if initial_data:
            self.edit_name.setText(initial_data.get("Name", ""))
            self.edit_diam.setText(str(initial_data.get("diam", "")))
            self.edit_z.setText(str(initial_data.get("z", "")))
            self.edit_vc.setText(str(initial_data.get("vc", "")))
            self.edit_fz.setText(str(initial_data.get("fz", "")))
            self.edit_type.setText(initial_data.get("type", ""))

    # ------------------------------------------------------------------
    def get_tool_data(self):
        return {
            "Name": self.edit_name.text().strip(),
            "diam": float(self.edit_diam.text().replace(",", ".")),
            "z": int(self.edit_z.text()),
            "vc": float(self.edit_vc.text().replace(",", ".")),
            "fz": float(self.edit_fz.text().replace(",", ".")),
            "type": self.edit_type.text().strip(),
        }
