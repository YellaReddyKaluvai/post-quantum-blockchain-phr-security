# liboqs has no wheel, so it is built from source. Kept in a separate stage so
# the runtime image carries the compiled library without the build toolchain.
FROM python:3.12-slim AS liboqs-build

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake ninja-build git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ARG LIBOQS_VERSION=0.16.0
RUN git clone --branch ${LIBOQS_VERSION} --depth 1 \
        https://github.com/open-quantum-safe/liboqs.git /tmp/liboqs \
 && cmake -GNinja -S /tmp/liboqs -B /tmp/liboqs/build \
        -DBUILD_SHARED_LIBS=ON \
        -DCMAKE_INSTALL_PREFIX=/usr/local \
        -DOQS_BUILD_ONLY_LIB=ON \
 && cmake --build /tmp/liboqs/build --parallel \
 && cmake --install /tmp/liboqs/build \
 && rm -rf /tmp/liboqs


FROM python:3.12-slim

COPY --from=liboqs-build /usr/local/lib/liboqs* /usr/local/lib/
COPY --from=liboqs-build /usr/local/include/oqs /usr/local/include/oqs
RUN ldconfig

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Fail fast if the post-quantum mechanisms are unavailable. A container that
# starts without them would silently lose every signature guarantee, which is
# the exact failure this project was built to eliminate.
RUN python -c "\
from app.crypto_service import pqc_available, ML_KEM_ALG, ML_DSA_ALG; \
assert pqc_available(), 'liboqs missing %s / %s' % (ML_KEM_ALG, ML_DSA_ALG); \
print('PQC available:', ML_KEM_ALG, ML_DSA_ALG)"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
