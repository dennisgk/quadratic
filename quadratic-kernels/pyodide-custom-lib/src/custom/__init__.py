import requests
import pandas as pd
import pyodide
from js import globalThis, fetch

jwt = ""

async def sql(sql_str, **kwargs):
    global jwt

    response = await fetch("https://quadraticapi.kountouris.org/v0/pyodide/info", pyodide.ffi.to_js({
        "method": "GET",
        "headers": {
            "Authorization": f"Bearer {jwt}"
        }
    }, dict_converter=globalThis.Object.fromEntries))
    
    inf = (await response.json()).to_py()

    url = inf["db"] + "/" + inf["name"] + ".json"

    params = {
        "sql": sql_str,
        "_shape": "objects",
        **kwargs,
    }

    resp = requests.get(url, params=params, auth=(inf["user"], inf["pass"]))
    try:
        resp.raise_for_status()
        j = resp.json()
        rows = j.get("rows", [])

        # Auto-detect columns: json_normalize handles nested dicts & missing keys
        if not rows:
            return pd.DataFrame()

        df = pd.json_normalize(rows)   # <-- auto-detects columns
        return df

    except Exception:
        print("SQL:", sql_str)
        print("URL:", resp.url)
        print("Response:", resp.text)
        raise
