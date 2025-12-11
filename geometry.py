# geometry.py
# First module for Part Costing: geometry extraction
# Minimal, beginner-friendly implementation

import FreeCAD
import FreeCADGui
import Part

class GeometryExtractor:
    """
    Extracts basic geometric information from the active FreeCAD document.
    """

    def __init__(self, doc=None):
        self.doc = doc or FreeCAD.ActiveDocument
        self.shape = None

    def load_part(self):
        """Load the first solid found in the document."""
        for obj in self.doc.Objects:
            if hasattr(obj, 'Shape') and obj.Shape.Solids:
                self.shape = obj.Shape
                return True
        return False

    def get_bounding_box(self):
        if not self.shape:
            return None
        return self.shape.BoundBox

    def get_volume(self):
        if not self.shape:
            return None
        return self.shape.Volume

    def get_faces(self):
        if not self.shape:
            return []
        return self.shape.Faces

    def summary(self):
        if not self.shape:
            return "No shape loaded."
        bb = self.get_bounding_box()
        return {
            "volume_mm3": self.get_volume(),
            "bbox": {
                "x": bb.XLength,
                "y": bb.YLength,
                "z": bb.ZLength
            },
            "face_count": len(self.get_faces())
        }

# Example usage inside FreeCAD console:
# extractor = GeometryExtractor()
# extractor.load_part()
# print(extractor.summary())
