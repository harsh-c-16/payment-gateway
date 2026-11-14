# Optional local encoder; keep the core application lock and evaluation image unchanged.
FROM group3-m04-storage:local
COPY embedding_requirements.txt /tmp/embedding_requirements.txt
RUN uv pip install --python /app/.venv/bin/python --require-hashes -r /tmp/embedding_requirements.txt
ENV EMBEDDING_MODEL_DIR=/app/embedding-model
