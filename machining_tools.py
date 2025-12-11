import os
import csv

TOOLS = {}

def load_tools():
    """Charge les outils depuis tools.csv"""
    global TOOLS

    base_dir = os.path.dirname(__file__)
    csv_path = os.path.join(base_dir, "tools.csv")

    if not os.path.isfile(csv_path):
        print(f"[PartCosting] ⚠️ tools.csv introuvable : {csv_path}")
        return {}

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            name = row["Name"]
            try:
                TOOLS[name] = {
                    "name": name,
                    "diam": float(row["Diam"]),
                    "z": int(row["Z"]),
                    "vc": float(row["Vc"]),
                    "fz": float(row["Fz"]),
                }
            except Exception as e:
                print(f"[PartCosting] Erreur dans tools.csv ligne {row}: {e}")

    return TOOLS


def get_tool(name):
    """Retourne un outil par son nom"""
    return TOOLS.get(name)


def get_all_tool_names():
    """Retourne la liste des outils"""
    return list(TOOLS.keys())


# Chargement automatique au démarrage
load_tools()
