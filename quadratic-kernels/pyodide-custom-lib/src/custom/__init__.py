from typing import Any, Dict, Iterable, Mapping, Optional, Union, List
import requests
import numpy as np
import pandas as pd

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
