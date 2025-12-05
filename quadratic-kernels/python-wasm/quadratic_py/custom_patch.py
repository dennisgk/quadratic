import micropip

async def apply_custom_patch(code, jwt):
    import pyodide.code

    if "custom" not in pyodide.code.find_imports(code):
        return

    await micropip.install("https://quadratic.kountouris.org/custom-0.1.0-py3-none-any.whl")
    import custom
    custom.jwt = jwt