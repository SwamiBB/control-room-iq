# Setup

## Local (no Azure)

```powershell
git clone https://github.com/<org>/control-room-iq; cd control-room-iq
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env            # CRQ_OFFLINE=1 by default
python -m simulator.cli generate --seed 42 --out data/match.jsonl
pytest
uvicorn api.main:app --reload          # API on :8000
cd web; npm install; npm run dev       # console on :5173 -> /operator and /viewer
```

In the console press **Start replay**; proposals arrive from the offline fallbacks.

## Azure sandbox

Prerequisites: Azure CLI, Azure Developer CLI (`winget install Microsoft.Azd`), Docker, Contributor +
User Access Administrator on the sandbox subscription, model router quota in East US 2.

```powershell
az login
azd auth login
azd env new dev
azd env set AZURE_LOCATION eastus2
azd up                                  # provisions infra/main.bicep and deploys api, ingest, web
azd env get-values | Out-File .env      # endpoints for local runs; set CRQ_OFFLINE=0
python -m simulator.cli replay data/match.jsonl --speed 20 --eventhub
```

Everything authenticates with Entra ID (managed identity in Azure, your `az login` locally). No keys.

## Quotas to request on day one

- `model-router` (version 2025-11-18), GlobalStandard: three deployments (`router-quality`, `router-balanced`,
  `router-cost`) at 100K TPM each
- `gpt-4.1-mini`, GlobalStandard, 100K TPM
- Confirm Foundry Agent Service and evaluations availability in East US 2
