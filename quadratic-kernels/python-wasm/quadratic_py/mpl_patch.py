import logging
import micropip

class IgnoreFontCache(logging.Filter):
    def filter(self, record):
        return "font cache" not in record.getMessage().lower()

def custom_show(*args, **kwargs):
    import matplotlib.pyplot as plt
    import plotly.tools as tls
    
    return tls.mpl_to_plotly(plt.gcf())

async def apply_mpl_patch(code):
    import pyodide.code

    if "matplotlib" not in pyodide.code.find_imports(code):
        return

    await micropip.install("plotly")

    logger = logging.getLogger("matplotlib.font_manager")
    if not any(isinstance(fltr, IgnoreFontCache) for fltr in logger.filters):
        logger.addFilter(IgnoreFontCache())

    import os
    if "MPLBACKEND" not in os.environ:
        os.environ["MPLBACKEND"] = "Agg"

    import matplotlib
    import matplotlib.pyplot as plt
    if plt.show is not custom_show:
        plt.show = custom_show
