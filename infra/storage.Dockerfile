# Build context contains only this file, pyproject.toml and uv.lock.
FROM python:3.11.15-slim-bookworm@sha256:d29f48a31a8b408ed19272ca1e7b10ebae13b240a27e862d3d4217c528e2e0c3
WORKDIR /app
RUN pip install --no-cache-dir uv==0.10.8
COPY pyproject.toml uv.lock ./
RUN uv sync --locked
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 LAKEHOUSE_ROOT=/lakehouse
# Application/owner source and a named volume are mounted explicitly at runtime.
CMD ["python", "-m", "pytest", "tests/pipelines/test_storage.py", "-q", "--tb=short"]
