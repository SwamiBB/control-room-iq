FROM python:3.12-slim
WORKDIR /app
# The base image ships an older pip with known CVEs (Trivy); upgrade it before installing anything.
RUN pip install --no-cache-dir --upgrade pip
COPY pyproject.toml README.md ./
COPY packages ./packages
COPY services ./services
RUN pip install --no-cache-dir -e .
# After the install, so new reference data doesn't rebuild the dependency layer. Ingest reads only the tracking
# files (StateFolder's distances); the match files are for the API's replay (#13).
COPY data/reference/tracking-*.jsonl.gz ./data/reference/
# Run as an unprivileged user (Trivy DS-0002): nothing writes to the image at runtime.
RUN useradd --system --uid 10001 --create-home --home-dir /home/app app
USER 10001
ENV PYTHONPATH=/app/packages/schemas:/app/services/simulator:/app/services/ingest:/app/services/agents:/app/services/api

CMD ["python", "-m", "ingest.consumer"]
