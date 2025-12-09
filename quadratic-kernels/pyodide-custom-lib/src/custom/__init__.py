from typing import Any, Dict, Iterable, Mapping, Optional, Union, List
import requests
import numpy as np
import pandas as pd
import base64
import json
import marshal
import sys
import types
import platform

# ---------------------------------------------------------
# GLOBAL CONFIG
# ---------------------------------------------------------

BASE_URL = "https://quadraticsc.kountouris.org"

# Global JWT – must be set by the user before calling functions
jwt: str = ""


# ---------------------------------------------------------
# INTERNAL UTILITY
# ---------------------------------------------------------

def _auth_headers() -> Dict[str, str]:
    """
    Builds Authorization header from global jwt.
    """
    if not jwt:
        raise ValueError("Global `jwt` is empty. Set it before making API calls.")
    return {
        "Authorization": f"Bearer {jwt}"
    }


# ---------------------------------------------------------
# RAW FILE DOWNLOAD
# ---------------------------------------------------------

def get_raw_file(filename: str) -> bytes:
    """
    GET /data/files/{filename}
    Returns raw bytes of the file.
    """
    url = f"{BASE_URL}/data/files/{filename}"

    resp = requests.get(url, headers=_auth_headers(), timeout=60)
    resp.raise_for_status()
    return resp.content


# ---------------------------------------------------------
# SQLITE QUERY
# ---------------------------------------------------------

def query_sqlite(
    filename: str,
    sql: str,
    params: Optional[Union[Iterable[Any], Mapping[str, Any]]] = None,
) -> pd.DataFrame:
    """
    POST /data/files/{filename}
    Runs a read-only SQLite query and returns pandas DataFrame.
    """
    url = f"{BASE_URL}/data/files/{filename}"

    # Body matches server schema
    body: Dict[str, Any] = {"sql": sql}

    if params is None:
        body["params"] = None
    elif isinstance(params, Mapping):
        body["params"] = dict(params)
    else:
        body["params"] = list(params)

    resp = requests.post(url, json=body, headers=_auth_headers(), timeout=60)
    resp.raise_for_status()
    payload = resp.json()

    rows = payload.get("rows", [])
    columns = payload.get("columns", [])

    df = pd.DataFrame(rows, columns=columns)
    return df


# ---------------------------------------------------------
# HDF5 QUERY
# ---------------------------------------------------------

def query_hdf5(
    filename: str,
    dataset: str,
    index: Optional[List[Any]] = None
) -> pd.DataFrame:
    """
    POST /data/files/{filename}
    Returns a slice of an HDF5 dataset as a pandas DataFrame.
    """
    url = f"{BASE_URL}/data/files/{filename}"

    body: Dict[str, Any] = {"dataset": dataset}
    if index is not None:
        body["index"] = index

    resp = requests.post(url, json=body, headers=_auth_headers(), timeout=60)
    resp.raise_for_status()
    payload = resp.json()

    arr = np.array(payload.get("data", []))

    # Convert to DataFrame depending on dimensionality
    if arr.ndim == 0:
        df = pd.DataFrame([[arr.item()]], columns=["value"])
    elif arr.ndim == 1:
        df = pd.DataFrame(arr, columns=["value"])
    elif arr.ndim == 2:
        df = pd.DataFrame(arr)
    else:
        # Flatten dimensions ≥3
        flat = arr.reshape(arr.shape[0], -1)
        df = pd.DataFrame(flat)

    return df


# ---------------------------------------------------------
# FILE UPLOAD
# ---------------------------------------------------------

def upload_file(filename: str, data: bytes) -> Dict[str, Any]:
    """
    POST /data/upload/{filename}
    Upload raw bytes; returns metadata including sha256sum.
    """
    url = f"{BASE_URL}/data/upload/{filename}"

    resp = requests.post(
        url,
        data=data,
        headers=_auth_headers(),
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()

def encode_function(func) -> str:
    """
    Take a Python function, grab its code object, serialize it together with
    Python version metadata, and return a single base64-encoded string.
    """
    if not hasattr(func, "__code__"):
        raise TypeError("encode_function only works on pure Python functions with a __code__ object.")

    code_obj = func.__code__
    code_bytes = marshal.dumps(code_obj)  # serialize the code object

    payload = {
        "impl": platform.python_implementation(),          # e.g. "CPython"
        "major": sys.version_info.major,
        "minor": sys.version_info.minor,
        "micro": sys.version_info.micro,
        "name": func.__name__,
        "code_b64": base64.b64encode(code_bytes).decode("ascii"),
    }

    json_bytes = json.dumps(payload).encode("utf-8")
    outer_b64 = base64.b64encode(json_bytes).decode("ascii")
    return outer_b64


def _decode_payload(encoded: str) -> dict:
    """Internal helper: base64 -> JSON -> dict."""
    json_bytes = base64.b64decode(encoded.encode("ascii"))
    payload = json.loads(json_bytes.decode("utf-8"))
    return payload


def get_function_name_from_encoded(encoded: str) -> str:
    """
    Extract the original func.__name__ from an encoded function string
    without reconstructing the function.
    """
    payload = _decode_payload(encoded)
    return payload.get("name", "<unknown>")


def get_encoded_function(encoded: str):
    """
    Decode a base64-encoded function payload, check that the current Python
    version is compatible, then return the reconstructed function object.

    You can then call it like:

        func = get_encoded_function(encoded)
        result = func(*args, **kwargs)
    """
    payload = _decode_payload(encoded)

    impl = payload["impl"]
    major = payload["major"]
    minor = payload["minor"]
    name = payload.get("name", "restored_function")

    # Implementation check
    current_impl = platform.python_implementation()
    if current_impl != impl:
        raise RuntimeError(
            f"Incompatible Python implementation: encoded for {impl}, "
            f"running on {current_impl}"
        )

    # Version check (strict: same major + minor)
    cur_major = sys.version_info.major
    cur_minor = sys.version_info.minor
    if (cur_major, cur_minor) != (major, minor):
        raise RuntimeError(
            f"Incompatible Python version: encoded for {major}.{minor}, "
            f"running on {cur_major}.{cur_minor}"
        )

    # Decode and reconstruct code object
    code_b64 = payload["code_b64"]
    code_bytes = base64.b64decode(code_b64.encode("ascii"))
    code_obj = marshal.loads(code_bytes)

    # Recreate function in current module's global namespace
    func = types.FunctionType(code_obj, globals(), name)
    return func
