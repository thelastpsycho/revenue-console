# Minimal image for the --schedule loop: it only talks HTTP to the backend
# container, it never touches Selenium/Chrome itself, so this deliberately
# does NOT reuse backend/Dockerfile's much heavier Chrome-laden image.
# Build context is the repo root (not scripts/) so this can copy the one
# file it needs without duplicating it anywhere.
FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir requests python-dotenv
COPY scripts/trigger_fast_pipeline.py scripts/trigger_fast_pipeline.py
ENTRYPOINT ["python", "scripts/trigger_fast_pipeline.py"]
