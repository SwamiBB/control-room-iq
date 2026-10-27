param app string
param suffix string
param location string
param tags object
param identityPrincipalId string
param appInsightsId string
param appInsightsConnectionString string

// Microsoft Foundry resource (AIServices kind) with a project, a fallback model and one model router per routing mode.
resource foundry 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: 'aif-${app}-${suffix}'
  location: location
  tags: tags
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: 'aif-${app}-${suffix}'
    allowProjectManagement: true
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: foundry
  name: 'proj-${app}-${suffix}'
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: { displayName: 'Control Room IQ', description: 'Inside the Game hackathon' }
}

// The account takes one operation at a time, so the project and deployments are created in sequence.
resource fallback 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: foundry
  name: 'gpt-4.1-mini'
  dependsOn: [ project ]
  sku: { name: 'GlobalStandard', capacity: 100 }
  properties: {
    model: { format: 'OpenAI', name: 'gpt-4.1-mini', version: '2025-04-14' }
  }
}

// One model-router deployment per routing mode: the routing mode is a deployment setting (#47). Agents pick theirs
// through AGENT_ROUTING in services/agents/agents/config.py. Every call sends about 11K input tokens, and up to three
// moments run at once, so each gets 100K tokens/min. batchSize(1) keeps the account to one operation at a time.
var routingModes = [ 'quality', 'balanced', 'cost' ]

@batchSize(1)
resource routers 'Microsoft.CognitiveServices/accounts/deployments@2025-10-01-preview' = [for mode in routingModes: {
  parent: foundry
  name: 'router-${mode}'
  dependsOn: [ fallback ]
  sku: { name: 'GlobalStandard', capacity: 100 }
  properties: {
    model: { format: 'OpenAI', name: 'model-router', version: '2025-11-18' }
    routing: { mode: mode }
  }
}]

resource speech 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: 'spch-${app}-${suffix}'
  location: location
  tags: tags
  kind: 'SpeechServices'
  sku: { name: 'S0' }
  properties: { customSubDomainName: 'spch-${app}-${suffix}', disableLocalAuth: true }
}

// Azure AI User on the Foundry resource for the workload identity
resource aiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, identityPrincipalId, 'aiuser')
  scope: foundry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '53ca6127-db72-4b80-b1b0-d745d6d5456d')
    principalId: identityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource appi 'Microsoft.Insights/components@2020-02-02' existing = {
  name: last(split(appInsightsId, '/'))
}

// Connects the project to Application Insights so traces show under Observability > Traces. The project signs in
// with its own managed identity, since the resource takes Entra ID only. A project allows one AppInsights connection.
resource appiConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-09-01' = {
  parent: project
  name: 'appinsights'
  properties: {
    category: 'AppInsights'
    target: appInsightsId
    // Accepted by the service but not yet in the Bicep type definitions.
    #disable-next-line BCP036
    authType: 'ProjectManagedIdentity'
    isSharedToAll: false
    metadata: {
      ApiType: 'Azure'
      ResourceId: appInsightsId
      ApplicationInsightsConnectionString: appInsightsConnectionString
    }
  }
}

// Monitoring Metrics Publisher for the project's identity, as the portal grants when you pick "Project managed
// identity", so server-side traces can be ingested.
resource projectAppiPublisher 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(appi.id, project.id, 'metricspub')
  scope: appi
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '3913510d-42f4-4e42-8a64-420c390055eb')
    principalId: project.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Monitoring Reader for the project's identity: the Foundry portal reads the traces as the project, so without it
// the agents' Monitor and Traces pages say "Setup incomplete" though the traces are there.
resource projectAppiReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(appi.id, project.id, 'monitoringreader')
  scope: appi
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '43d0d8ad-25c7-4714-9337-8ba259a9fe05')
    principalId: project.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource speechUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(speech.id, identityPrincipalId, 'speechuser')
  scope: speech
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'f2dc8367-1007-4938-bd23-fe263f013447')
    principalId: identityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output projectEndpoint string = 'https://${foundry.properties.customSubDomainName}.services.ai.azure.com/api/projects/${project.name}'
output openAiEndpoint string = 'https://${foundry.properties.customSubDomainName}.openai.azure.com/'
// Azure AI Content Safety on the same account: the API checks an operator's override line with it (Entra ID).
output contentSafetyEndpoint string = 'https://${foundry.properties.customSubDomainName}.cognitiveservices.azure.com/'
output speechEndpoint string = speech.properties.endpoint
