FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY dungeon ./dungeon
COPY static ./static
COPY server.py .

ENV PORT=8010
EXPOSE 8010

CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT}"]
