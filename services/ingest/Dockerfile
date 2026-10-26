FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY packages ./packages
COPY services ./services
RUN pip install --no-cache-dir -e .
# After the install, so new reference data doesn't rebuild the dependency layer. Ingest reads only the tracking
# files (StateFolder's distances); the match files are for the API's replay (#13).
COPY data/reference/tracking-*.jsonl.gz ./data/reference/
ENV PYTHONPATH=/app/packages/schemas:/app/services/simulator:/app/services/ingest:/app/services/agents:/app/services/api

CMD ["python", "-m", "ingest.consumer"]
