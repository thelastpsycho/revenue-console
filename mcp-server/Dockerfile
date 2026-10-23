FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .

RUN useradd -m -u 1000 appuser
USER appuser

EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8765/health',timeout=3).status==200 else 1)"
CMD ["python", "server.py", "--http"]
