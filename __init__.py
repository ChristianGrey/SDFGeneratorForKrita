from krita import Krita
from .SDFGenerator import SDFGenerator

# Register SDF generator as an extension
Krita.instance().addExtension(SDFGenerator(Krita.instance()))