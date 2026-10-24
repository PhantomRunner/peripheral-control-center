FROM node:24-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    XDG_DATA_HOME=/data \
    XDG_RUNTIME_DIR=/tmp \
    PCC_STATIC_DIR=/app/static \
    PCC_PORT=8080
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && mkdir /data \
    && chmod 1777 /data
COPY backend/pcc/ ./pcc/
COPY --from=frontend /build/frontend/dist/ ./static/
USER 1000:1000
CMD ["python", "-m", "pcc.container"]
