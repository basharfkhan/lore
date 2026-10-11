# The web service only: the agent, its two tools and the page. The corpus ships compressed in
# corpus/ and is unpacked at startup, so nothing from the data pipeline is installed here.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

COPY pyproject.toml README.md ./
COPY lore ./lore
# Editable, so the package keeps resolving corpus/ and web/ relative to /app.
RUN pip install -e ".[serve]"

COPY configs ./configs
COPY corpus ./corpus
COPY web ./web

EXPOSE 8000
CMD ["sh", "-c", "uvicorn lore.serve.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
