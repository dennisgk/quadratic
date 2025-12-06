FROM python:3.11-slim

# Install system libs for h5py / HDF5
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libhdf5-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
RUN pip install --no-cache-dir \
    fastapi \
    "uvicorn[standard]" \
    h5py \
    numpy \
    httpx \
    "python-jose[cryptography]" \
    requests

# Copy the API code
COPY ./quadratic-simple-connection/api_server.py /app/api_server.py
COPY ./quadratic-simple-connection/ory_jwt.py /app/ory_jwt.py

EXPOSE 3010

CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "3010"]
