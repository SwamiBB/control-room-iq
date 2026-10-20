FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY packages ./packages
COPY services ./services
RUN pip install --no-cache-dir -e .
ENV PYTHONPATH=/app/packages/schemas:/app/services/simulator:/app/services/ingest:/app/services/agents:/app/services/api
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
