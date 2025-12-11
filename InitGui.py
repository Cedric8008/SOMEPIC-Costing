import FreeCADGui
import os
import FreeCAD as App


class PartCostingWorkbench(FreeCADGui.Workbench):
    """PartCosting Workbench"""

    # Nom affiché dans FreeCAD
    MenuText = "PartCosting"
    ToolTip = "Workbench for machining cost estimation"

    # Icône du Workbench
    Icon = os.path.join(
        App.getUserAppDataDir(),
        "Mod",
        "PartCosting",
        "Resources",
        "icons",
        "icon_workbench.png",
    )

    def Initialize(self):
        # Chargement des commandes
        import Commands
        from panel import show_panel

        # Barre d'outils
        self.appendToolbar(
            "PartCosting Tools",
            ["PC_AnalyzeGeometry", "PC_CreateStock"],
        )

        # Menu principal
        self.appendMenu(
            "PartCosting",
            ["PC_AnalyzeGeometry", "PC_CreateStock"],
        )

        # Affichage du panneau latéral
        show_panel()

    def GetClassName(self):
        return "Gui::PythonWorkbench"


# Enregistrement du Workbench dans FreeCAD
FreeCADGui.addWorkbench(PartCostingWorkbench())
