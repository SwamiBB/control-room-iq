targetScope = 'subscription'

@minLength(1)
@maxLength(16)
param environmentName string
param location string = 'eastus2'
param ownerAlias string = 'aicoe'
param expires string = '2026-11-30'

var prefix = 'crq-${environmentName}'
var tags = { project: 'control-room-iq', owner: ownerAlias, expires: expires, 'azd-env-name': environmentName }

resource rg 'Microsoft.Resources/resourceGroups@2023-07-01' = {
  name: 'rg-${prefix}'
  location: location
  tags: tags
}

module core 'modules/core.bicep' = {
  name: 'core'
  scope: rg
  params: { prefix: prefix, location: location, tags: tags }
}

module data 'modules/data.bicep' = {
  name: 'data'
  scope: rg
  params: { prefix: prefix, location: location, tags: tags, identityPrincipalId: core.outputs.identityPrincipalId }
}

module ai 'modules/ai.bicep' = {
  name: 'ai'
  scope: rg
  params: { prefix: prefix, location: location, tags: tags, identityPrincipalId: core.outputs.identityPrincipalId }
}

module apps 'modules/apps.bicep' = {
  name: 'apps'
  scope: rg
  params: {
    prefix: prefix
    location: location
    tags: tags
    identityId: core.outputs.identityId
    acrLoginServer: core.outputs.acrLoginServer
    logAnalyticsId: core.outputs.logAnalyticsId
    appInsightsConnectionString: core.outputs.appInsightsConnectionString
    eventHubNamespaceFqdn: data.outputs.eventHubNamespaceFqdn
    cosmosEndpoint: data.outputs.cosmosEndpoint
    foundryProjectEndpoint: ai.outputs.projectEndpoint
    openAiEndpoint: ai.outputs.openAiEndpoint
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = core.outputs.acrLoginServer
output FOUNDRY_PROJECT_ENDPOINT string = ai.outputs.projectEndpoint
output AZURE_OPENAI_ENDPOINT string = ai.outputs.openAiEndpoint
output EVENTHUB_NAMESPACE string = data.outputs.eventHubNamespaceFqdn
output COSMOS_ENDPOINT string = data.outputs.cosmosEndpoint
output API_URL string = apps.outputs.apiUrl
output WEB_URL string = apps.outputs.webUrl
