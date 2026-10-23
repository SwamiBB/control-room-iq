param app string
param suffix string
param location string
param tags object
param identityPrincipalId string

// Microsoft Foundry resource (AIServices kind) with a project, model router, and a fallback model.
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
resource modelRouter 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: foundry
  name: 'model-router'
  dependsOn: [ project ]
  sku: { name: 'GlobalStandard', capacity: 100 }
  properties: {
    model: { format: 'OpenAI', name: 'model-router', version: '2025-11-18' }
  }
}

resource fallback 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: foundry
  name: 'gpt-4.1-mini'
  dependsOn: [ modelRouter ]
  sku: { name: 'GlobalStandard', capacity: 100 }
  properties: {
    model: { format: 'OpenAI', name: 'gpt-4.1-mini', version: '2025-04-14' }
  }
}

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
output speechEndpoint string = speech.properties.endpoint
