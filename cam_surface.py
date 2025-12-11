import FreeCAD
import Path
import PathScripts.PathJob as PathJob
import PathScripts.PathOpFace as PathOpFace


def compute_surface_cam(part_obj, face, tool_diam, vc, fz, z_depth, stock_obj=None):
    doc = FreeCAD.ActiveDocument
    if not doc:
        return {"ok": False, "error": "Aucun document actif"}

    try:
        # --- Job CAM ---
        job = PathJob.Create(part_obj)
        doc.recompute()

        # --- Opération Face Milling ---
        op = PathOpFace.Create('FaceCAM')
        job.Proxy.addOperation(op)
        op.setFace([face])

        # Paramétrage outil
        tool = op.ToolController.Tool
        tool.Diameter = tool_diam

        spindle = (1000 * vc) / (3.14159 * tool_diam)
        feed_mm_min = spindle * fz * tool_diam

        op.ToolController.HorizFeed = feed_mm_min
        op.ToolController.VertFeed = feed_mm_min
        op.FinalDepth = -abs(z_depth)

        doc.recompute()

        # Génération parcours
        PathJob.Command.generateAll(job)
        doc.recompute()

        # Lecture durée et longueur
        duration = getattr(op.Path, "Duration", None)
        length = getattr(op.Path, "Length", 0.0)

        if duration is None:
            return {"ok": False, "error": "Durée CAM indisponible"}

        return {
            "ok": True,
            "time_s": duration,
            "length_mm": length,
            "feed_mm_min": feed_mm_min,
        }

    except Exception as e:
        return {"ok": False, "error": str(e)}
