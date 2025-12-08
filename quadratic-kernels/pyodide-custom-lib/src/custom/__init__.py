from typing import Any, Dict, Iterable, Mapping, Optional, Union, List

import httpx
import numpy as np
import pandas as pd

# Global JWT used for all calls
jwt: str = ""

BASE_URL = "https://quadraticsc.kountouris.org"


def _auth_headers() -> Dict[str, str]:
    """
    Build Authorization header from global jwt.
    Make sure to set `jwt` before calling the helper functions.
    """
    if not jwt:
        raise ValueError("Global `jwt` is empty. Set it before making API calls.")
    return {"Authorization": f"Bearer {jwt}"}


def get_raw_file(filename: str) -> bytes:
    """
    Download a raw file from /data/files/{filename}.

    Returns:
        Raw bytes of the file.
    """
    url = f"{BASE_URL}/data/files/{filename}"
    resp = httpx.get(url, headers=_auth_headers(), timeout=60.0)
    resp.raise_for_status()
    return resp.content


def query_sqlite(
    filename: str,
    sql: str,
    params: Optional[Union[Iterable[Any], Mapping[str, Any]]] = None,
) -> pd.DataFrame:
    """
    Query a SQLite file via /data/files/{filename} and return a pandas DataFrame.

    Args:
        filename: Name of the .db or .sqlite file on the server.
        sql: SELECT statement (read-only; enforced by server).
        params: Optional parameters for the SQL query:
            - sequence -> positional parameters
            - mapping  -> named parameters

    Returns:
        pandas.DataFrame with columns/rows from the server.
    """
    url = f"{BASE_URL}/data/files/{filename}"

    body: Dict[str, Any] = {"sql": sql}

    if params is None:
        body["params"] = None
    elif isinstance(params, Mapping):
        # Named parameters -> JSON object
        body["params"] = dict(params)
    else:
        # Positional parameters -> JSON array
        body["params"] = list(params)

    resp = httpx.post(url, json=body, headers=_auth_headers(), timeout=60.0)
    resp.raise_for_status()

    payload = resp.json()
    columns = payload.get("columns", [])
    rows = payload.get("rows", [])

    df = pd.DataFrame(rows, columns=columns)
    return df


def query_hdf5(
    filename: str,
    dataset: str,
    index: Optional[List[Any]] = None,
) -> pd.DataFrame:
    """
    Query an HDF5 file via /data/files/{filename} and return a pandas DataFrame.

    Args:
        filename: Name of the .h5 / .hdf5 file on the server.
        dataset: HDF5 dataset path, e.g. "/group/dset".
        index: Optional index specification matching the API format:
            - None -> full dataset
            - list of per-dimension specs:
                * int       -> direct index
                * [start, stop] or [start, stop, step] -> slice
                * null (None) -> ":" (full dimension)

    Returns:
        pandas.DataFrame built from the returned numeric/array data.
        - 0D:    single-value DataFrame with column "value"
        - 1D:    one-column DataFrame with column "value"
        - 2D:    DataFrame with shape matching the 2D array
        - >2D:   Flattened to 2D: (N, -1)
    """
    url = f"{BASE_URL}/data/files/{filename}"

    body: Dict[str, Any] = {"dataset": dataset}
    if index is not None:
        body["index"] = index

    resp = httpx.post(url, json=body, headers=_auth_headers(), timeout=60.0)
    resp.raise_for_status()

    payload = resp.json()
    data = payload.get("data", [])

    arr = np.array(data)

    if arr.ndim == 0:
        # Scalar
        df = pd.DataFrame([[arr.item()]], columns=["value"])
    elif arr.ndim == 1:
        # 1D vector
        df = pd.DataFrame(arr, columns=["value"])
    elif arr.ndim == 2:
        # 2D matrix
        df = pd.DataFrame(arr)
    else:
        # Higher-dimensional: flatten everything except last axis
        new_shape = (-1, arr.shape[-1]) if arr.shape[-1] != 0 else (arr.size, 1)
        flat = arr.reshape(new_shape)
        df = pd.DataFrame(flat)

    return df
