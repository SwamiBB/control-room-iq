FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY packages ./packages
COPY services ./services
RUN pip install --no-cache-dir -e .
# After the install, so new reference data doesn't rebuild the dependency layer. The hosted replay and
# StateFolder read the reference matches and their tracking files (#13).
COPY data/reference ./data/reference
ENV PYTHONPATH=/app/packages/schemas:/app/services/simulator:/app/services/ingest:/app/services/agents:/app/services/api

CMD ["python", "-m", "ingest.consumer"]
