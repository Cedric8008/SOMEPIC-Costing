import FreeCAD
import FreeCADGui
import os
import FreeCAD as App

from geometry import GeometryExtractor


class PC_AnalyzeGeometry:
    """Commande : Analyse géométrique"""

    def GetResources(self):
        icon = os.path.join(
            App.getUserAppDataDir(),
            "Mod",
            "PartCosting",
            "Resources",
            "icons",
            "analyze_geometry.png",
        )
        return {
            "Pixmap": icon,
            "MenuText": "Analyze Geometry",
            "ToolTip": "Analyze the active part and display geometric summary",
        }

    def Activated(self):
        extractor = GeometryExtractor()
        if extractor.load_part():
            summary = extractor.summary()
            FreeCAD.Console.PrintMessage("\n=== Geometry Summary ===\n")
            FreeCAD.Console.PrintMessage(str(summary) + "\n")
        else:
            FreeCAD.Console.PrintError("No solid found in the document.\n")

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None


class PC_CreateStock:
    """
    Ancienne commande brute.  
    Désormais redirigée vers le panneau 'Brut intelligent'.
    """

    def GetResources(self):
        icon = os.path.join(
            App.getUserAppDataDir(),
            "Mod",
            "PartCosting",
            "Resources",
            "icons",
            "create_stock.png",
        )
        return {
            "Pixmap": icon,
            "MenuText": "Créer brut (simple)",
            "ToolTip": "Créer un brut simple (utilisez plutôt le panneau 'Brut intelligent')",
        }

    def Activated(self):
        FreeCAD.Console.PrintMessage(
            "ℹ Utilisez plutôt le panneau 'Brut intelligent' à droite.\n"
        )

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None


# Enregistrement des commandes dans FreeCAD
FreeCADGui.addCommand("PC_AnalyzeGeometry", PC_AnalyzeGeometry())
FreeCADGui.addCommand("PC_CreateStock", PC_CreateStock())
