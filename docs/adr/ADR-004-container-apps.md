# ADR-004: Azure Container Apps over AKS for the build week

Decision: Container Apps (consumption) with KEDA scaling on Event Hubs lag; simulator as an ACA job.
Why: `azd up` provisions and deploys in one command; event-driven scaling is native; AKS would cost
a day of setup the team does not have.
Status (Oct 27): KEDA scaling is not built. Each app runs a fixed replica count, and ingest stays at one
replica until the consumer has a checkpoint store (`infra/modules/apps.bicep`). The SLA hold runs in the API, not
a Logic App.
Consequences: the Cloud Native category story is Container Apps + Event Hubs + Logic Apps + Cosmos,
not Kubernetes; an AKS variant could be added after the hackathon.
