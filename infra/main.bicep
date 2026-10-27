targetScope = 'subscription'

// The {env} part of every name, e.g. poc in the sandbox. Seven characters at most keeps container app names within 32.
@minLength(1)
@maxLength(7)
param environmentName string
param location string = 'eastus2'
// The {instance} part of every name; bump it if a globally unique name is taken.
param instance string = '01'
param ownerAlias string = 'platform'
param expires string = '2026-11-30'
// Whether each app exists already; azd fills these from SERVICE_*_RESOURCE_EXISTS (main.parameters.json).
param apiExists bool = false
param ingestExists bool = false
param webExists bool = false
// Record prompt and response text in traces (CRQ_TRACE_CONTENT). On because all match data is synthetic; a
// deployment with real viewer data sets it false.
param traceContent string = 'true'

// Naming convention: resource group {app}-rg-{env}-{region}-{instance}, resources {type}-{app}-{env}-{region}-{instance}.
var app = 'crq'
var suffix = toLower('${environmentName}-${location}-${instance}')
var tags = { project: 'control-room-iq', owner: ownerAlias, expires: expires, 'azd-env-name': environmentName }

resource rg 'Microsoft.Resources/resourceGroups@2023-07-01' = {
  name: '${app}-rg-${suffix}'
  location: location
  tags: tags
}

module core 'modules/core.bicep' = {
  name: 'core'
  scope: rg
  params: { app: app, suffix: suffix, location: location, tags: tags }
}

module data 'modules/data.bicep' = {
  name: 'data'
  scope: rg
  params: { app: app, suffix: suffix, location: location, tags: tags, identityPrincipalId: core.outputs.identityPrincipalId }
}

module ai 'modules/ai.bicep' = {
  name: 'ai'
  scope: rg
  params: {
    app: app
    suffix: suffix
    location: location
    tags: tags
    identityPrincipalId: core.outputs.identityPrincipalId
    appInsightsId: core.outputs.appInsightsId
    appInsightsConnectionString: core.outputs.appInsightsConnectionString
  }
}

module apps 'modules/apps.bicep' = {
  name: 'apps'
  scope: rg
  params: {
    app: app
    suffix: suffix
    location: location
    tags: tags
    identityId: core.outputs.identityId
    acrLoginServer: core.outputs.acrLoginServer
    logAnalyticsId: core.outputs.logAnalyticsId
    appInsightsId: core.outputs.appInsightsId
    appInsightsConnectionString: core.outputs.appInsightsConnectionString
    eventHubNamespaceFqdn: data.outputs.eventHubNamespaceFqdn
    cosmosEndpoint: data.outputs.cosmosEndpoint
    foundryProjectEndpoint: ai.outputs.projectEndpoint
    openAiEndpoint: ai.outputs.openAiEndpoint
    contentSafetyEndpoint: ai.outputs.contentSafetyEndpoint
    apiExists: apiExists
    ingestExists: ingestExists
    webExists: webExists
    traceContent: traceContent
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = core.outputs.acrLoginServer
output FOUNDRY_PROJECT_ENDPOINT string = ai.outputs.projectEndpoint
output AZURE_OPENAI_ENDPOINT string = ai.outputs.openAiEndpoint
output EVENTHUB_NAMESPACE string = data.outputs.eventHubNamespaceFqdn
output COSMOS_ENDPOINT string = data.outputs.cosmosEndpoint
output WEB_URL string = apps.outputs.webUrl
