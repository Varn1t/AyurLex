# AyurLex web UI. Ollama runs on the HOST, not in this image:
#   docker build -t ayurlex .
#   docker run --rm -p 8000:8000 ayurlex          -> http://localhost:8000
# With no reachable Ollama it still answers, extractively (quotes the provision).
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml requirements.txt README.md LICENSE ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install --no-cache-dir --no-deps -e . \
 && python samhita/ingest.py \
 && python samhita/priorart.py \
 && python samhita/schedules.py

ENV OLLAMA_HOST=http://host.docker.internal:11434 \
    PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["ayurlex", "serve", "--host", "0.0.0.0", "--port", "8000"]
