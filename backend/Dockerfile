FROM python:3.11-slim

# Chrome + the standard set of shared libs it needs to not crash headless on
# bare Debian. curl/gnupg/ca-certificates are only needed to add Google's own
# apt key/repo (installing their real google-chrome-stable package, not
# Debian's chromium, so Selenium Manager's browser/driver version pairing
# matches what it's actually tested against).
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl gnupg ca-certificates \
      fonts-liberation libnss3 libatk-bridge2.0-0 libgtk-3-0 \
      libgbm1 libasound2 libxss1 libxshmfence1 libdrm2 \
    && curl -fsSL https://dl.google.com/linux/linux_signing_key.pub \
         | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" \
         > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y --no-install-recommends google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Chrome's --no-sandbox flag (already set in every setup_driver() in this
# codebase) is what makes running as non-root work without the setuid
# sandbox helper.
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 5666

# --workers 1 is required, not a tuning knob: pipeline_active/log_queue/
# allotment_run_control live as in-process Python globals (app/shared.py,
# app/pipeline/fast_runner.py) with no file/DB backing, so a second worker
# process would silently run its own independent copy of that state.
# --worker-class gthread --threads 8 gives real concurrency within that one
# process instead. --timeout 0 disables gunicorn's own worker timeout, which
# would otherwise kill the long-lived SSE streams (/api/*/stream) that block
# on queue.Queue.get() until the pipeline finishes.
CMD ["gunicorn", "--bind", "0.0.0.0:5666", \
     "--workers", "1", "--worker-class", "gthread", "--threads", "8", \
     "--timeout", "0", \
     "run:app"]
