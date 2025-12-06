# api_server.py
import json
import os
import sqlite3
import hashlib
from pathlib import Path
from typing import Any, List, Optional

import h5py
import httpx
import numpy as np
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
import uvicorn

app = FastAPI(title="File Query API")

# Directory where your data files live
API_FILES_DIR = Path("/api-files")

# ---------------------------
# Auth: Kratos session check
# ---------------------------

async def get_current_session(request: Request) -> dict:
    """
    Validates the Authorization: Bearer <token> header against the Kratos auth server.

    Uses KRATOS_PUBLIC_URL and calls /sessions/whoami.
    If the token is invalid or no active session exists, raises 401.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Empty bearer token")

    kratos_host = os.getenv("KRATOS_PUBLIC_URL")
    if not kratos_host:
        raise HTTPException(status_code=500, detail="KRATOS_PUBLIC_URL is not configured")

    url = kratos_host.rstrip("/") + "/sessions/whoami"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # 2. Send the token in the 'Cookie' header instead of 'Authorization'
            resp = await client.get(
                url,
                headers={
                    # Send the session token as a cookie
                    "Cookie": f"ory_kratos_session={token}",
                    "Accept": "application/json",
                },
            )
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Failed to contact auth server: {e}")

    if resp.status_code != 200:
        # This will catch 401/403 responses from Kratos for invalid/inactive sessions
        raise HTTPException(status_code=401, detail="Invalid or inactive session")

    try:
        session_data = resp.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="Auth server returned invalid JSON")

    # You could inspect session_data["identity"] here if needed
    return session_data


# ---------------------------
# Utility: safe path handling
# ---------------------------

def get_safe_file_path(filename: str) -> Path:
    """
    For reading existing files. Prevent path traversal; only allow files under API_FILES_DIR.
    """
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path = (API_FILES_DIR / filename).resolve()

    try:
        file_path.relative_to(API_FILES_DIR)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filename path")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return file_path


def get_upload_target_path(filename: str) -> Path:
    """
    For writing new/uploaded files. Prevent path traversal; do NOT require existence.
    """
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path = (API_FILES_DIR / filename).resolve()

    try:
        file_path.relative_to(API_FILES_DIR)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filename path")

    return file_path


# ---------------------------
# Utility: very simple SQL safety check
# ---------------------------

FORBIDDEN_SQL_KEYWORDS = [
    "insert", "update", "delete", "drop", "alter", "pragma",
    "create", "replace", "attach", "detach", "vacuum",
]

def assert_sql_is_read_only(sql: str) -> None:
    """
    Very basic SQL safety: only allow statements starting with SELECT
    and reject obvious mutating keywords.
    """
    s = sql.strip().lower()

    if not s.startswith("select "):
        raise HTTPException(
            status_code=400,
            detail="Only SELECT statements are allowed",
        )

    # Disallow semicolons (very simple limiting to one statement)
    if ";" in s:
        raise HTTPException(
            status_code=400,
            detail="Multiple statements are not allowed",
        )

    for kw in FORBIDDEN_SQL_KEYWORDS:
        if kw in s:
            raise HTTPException(
                status_code=400,
                detail=f"SQL contains forbidden keyword: {kw}",
            )


# ---------------------------
# SQLite handler
# ---------------------------

def handle_sqlite_query(file_path: Path, body: dict) -> JSONResponse:
    """
    Execute a safe SELECT query on a SQLite database and return rows as JSON.
    Body must include: {"sql": "SELECT ... "}.
    """
    sql = body.get("sql")
    if not isinstance(sql, str):
        raise HTTPException(status_code=400, detail="Missing or invalid 'sql' field")

    assert_sql_is_read_only(sql)

    # Open SQLite in read-only mode (URI syntax)
    uri = f"file:{file_path.as_posix()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"SQLite open error: {e}")

    # Extra safety: authorizer that denies write operations
    def authorizer(action, arg1, arg2, db_name, trigger_or_view):
        if action in (
            sqlite3.SQLITE_INSERT,
            sqlite3.SQLITE_UPDATE,
            sqlite3.SQLITE_DELETE,
            sqlite3.SQLITE_ALTER_TABLE,
            sqlite3.SQLITE_DROP_TABLE,
            sqlite3.SQLITE_CREATE_TABLE,
            sqlite3.SQLITE_CREATE_INDEX,
            sqlite3.SQLITE_CREATE_VIEW,
            sqlite3.SQLITE_CREATE_TRIGGER,
            sqlite3.SQLITE_DROP_INDEX,
            sqlite3.SQLITE_DROP_VIEW,
            sqlite3.SQLITE_DROP_TRIGGER,
        ):
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    conn.set_authorizer(authorizer)

    try:
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        colnames = [desc[0] for desc in cur.description]
    except sqlite3.Error as e:
        raise HTTPException(status_code=400, detail=f"SQLite query error: {e}")
    finally:
        conn.close()

    return JSONResponse(
        content={
            "columns": colnames,
            "rows": rows,
        }
    )


# ---------------------------
# HDF5 slice helper
# ---------------------------

def parse_h5_index(index_spec: Optional[List[Any]]) -> Any:
    """
    Convert simple JSON index spec into Python indexing (tuple of slices/ints).
    index_spec is a list, one entry per dimension:
      - integer -> used directly
      - [start, stop, step] -> slice(start, stop, step), any can be null
      - null -> slice(None)  (full ':')
    If index_spec is None, caller should treat as full dataset.
    """
    if index_spec is None:
        return Ellipsis

    result = []
    for dim in index_spec:
        if dim is None:
            result.append(slice(None))
        elif isinstance(dim, int):
            result.append(dim)
        elif isinstance(dim, list):
            if len(dim) not in (2, 3):
                raise HTTPException(
                    status_code=400,
                    detail="Slice spec must be [start, stop] or [start, stop, step]",
                )
            start = dim[0]
            stop = dim[1]
            step = dim[2] if len(dim) == 3 else None
            result.append(slice(start, stop, step))
        else:
            raise HTTPException(
                status_code=400,
                detail="Invalid index specification",
            )

    return tuple(result)


def handle_h5_slice(file_path: Path, body: dict) -> JSONResponse:
    """
    Open an HDF5 file and return a slice of a dataset as JSON.
    Body example:
    {
      "dataset": "/path/to/dset",
      "index": [
        [0, 10, 1],
        5,
        null
      ]
    }
    """
    dataset_path = body.get("dataset")
    if not isinstance(dataset_path, str):
        raise HTTPException(status_code=400, detail="Missing or invalid 'dataset' field")

    index_spec = body.get("index")

    try:
        with h5py.File(file_path, "r") as f:
            if dataset_path not in f:
                raise HTTPException(
                    status_code=404,
                    detail=f"Dataset '{dataset_path}' not found",
                )

            dset = f[dataset_path]

            if index_spec is None:
                data = dset[()]
            else:
                idx = parse_h5_index(index_spec)
                data = dset[idx]

            arr = np.array(data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"HDF5 error: {e}")

    return JSONResponse(
        content={
            "shape": list(arr.shape),
            "dtype": str(arr.dtype),
            "data": arr.tolist(),
        }
    )


# ---------------------------
# Main query endpoint
# ---------------------------

@app.api_route("/data/files/{filename}", methods=["GET", "POST"])
async def query_file(
    filename: str,
    request: Request,
    session: dict = Depends(get_current_session),
):
    """
    Query either a SQLite (.db/.sqlite) or HDF5 (.h5/.hdf5) file under ./api-files.

    Request body (JSON):
    - For .db/.sqlite:
        { "sql": "SELECT ... WHERE ..." }

    - For .h5/.hdf5:
        {
          "dataset": "/group/path/to/dset",
          "index": [
             [0, 10, 1],
             5,
             null
          ]
        }

    For any other file extension, the full raw file is streamed back.

    Requires a valid Kratos session for ALL requests.
    """
    file_path = get_safe_file_path(filename)

    # Read body if present
    try:
        body_bytes = await request.body()
        if body_bytes:
            body = json.loads(body_bytes.decode("utf-8"))
        else:
            body = {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")

    lower_name = filename.lower()

    if lower_name.endswith(".db") or lower_name.endswith(".sqlite"):
        return handle_sqlite_query(file_path, body)

    elif lower_name.endswith(".h5") or lower_name.endswith(".hdf5"):
        return handle_h5_slice(file_path, body)

    # Fallback: send raw file for unsupported types
    return FileResponse(
        path=file_path,
        media_type="application/octet-stream",
        filename=file_path.name,
    )


# ---------------------------
# Upload endpoint
# ---------------------------

@app.post("/data/upload/{filename}")
async def upload_file(
    filename: str,
    request: Request,
    session: dict = Depends(get_current_session),
):
    """
    Upload a raw file body and save it under ./api-files/{filename}.
    Returns metadata including SHA-256 hash of the uploaded content.

    - Path: POST /data/upload/{filename}
    - Body: raw bytes (any content-type)
    - Requires a valid Kratos session.
    """
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="Empty request body")

    target_path = get_upload_target_path(filename)

    # Compute SHA-256 BEFORE writing
    sha256_hash = hashlib.sha256(data).hexdigest()

    try:
        with open(target_path, "wb") as f:
            f.write(data)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to write file: {e}")

    return {
        "filename": target_path.name,
        "bytes_written": len(data),
        "sha256sum": sha256_hash,
    }


# ---------------------------
# Dev server entrypoint
# ---------------------------

if __name__ == "__main__":
    uvicorn.run("api_server:app", host="0.0.0.0", port=3010, reload=True)
