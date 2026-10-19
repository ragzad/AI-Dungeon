FROM python:3.12-slim

# run as a normal user (Hugging Face Spaces expects uid 1000)
RUN useradd -m -u 1000 user
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user dungeon ./dungeon
COPY --chown=user static ./static
COPY --chown=user server.py .

USER user
# saves and caches go somewhere writable; they don't survive a restart
ENV PORT=7860 \
    SAVE_DIR=/tmp/dungeon/saves \
    CACHE_DIR=/tmp/dungeon/cache \
    PYTHONUNBUFFERED=1
EXPOSE 7860

CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
