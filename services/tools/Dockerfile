FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/tmp

# LibreOffice renders Office files to PDF/PNG for previews and visual checks.
# Carlito/Caladea are metric-compatible with Calibri/Cambria so layouts match Word.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-writer libreoffice-impress libreoffice-calc \
        poppler-utils curl \
        fonts-crosextra-carlito fonts-crosextra-caladea fonts-liberation2 \
        fonts-dejavu-core fonts-noto-core fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY pyproject.toml ./
COPY app ./app
RUN pip install .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers"]
