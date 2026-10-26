param app string
param suffix string
param location string
param tags object
param identityPrincipalId string

resource ehns 'Microsoft.EventHub/namespaces@2024-01-01' = {
  name: 'evhns-${app}-${suffix}'
  location: location
  tags: tags
  sku: { name: 'Standard', tier: 'Standard', capacity: 1 }
  // Entra ID only, like Cosmos and Foundry: every client signs in with a credential, none uses a SAS key.
  properties: { isAutoInflateEnabled: true, maximumThroughputUnits: 4, minimumTlsVersion: '1.2', disableLocalAuth: true }
}

var hubs = [
  { name: 'crq-events', partitions: 8 }
  { name: 'crq-moments', partitions: 4 }
  { name: 'crq-overlay', partitions: 4 }
]

resource hub 'Microsoft.EventHub/namespaces/eventhubs@2024-01-01' = [for h in hubs: {
  parent: ehns
  name: h.name
  properties: { partitionCount: h.partitions, messageRetentionInDays: 1 }
}]

// Azure Event Hubs Data Owner
resource ehRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(ehns.id, identityPrincipalId, 'ehowner')
  scope: ehns
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'f526a384-b230-433a-b45c-95f59c4a2dec')
    principalId: identityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: 'cosmos-${app}-${suffix}'
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    locations: [ { locationName: location, failoverPriority: 0 } ]
    // Azure turns this on for new accounts; declaring it stops every provision from switching it off. With one
    // region it has nothing to fail over to either way.
    enableAutomaticFailover: true
    capabilities: [ { name: 'EnableServerless' } ]
    disableLocalAuth: true
    minimalTlsVersion: 'Tls12'
  }
}

resource db 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: cosmos
  name: 'crq'
  properties: { resource: { id: 'crq' } }
}

var containers = [ 'matches', 'state', 'moments', 'proposals', 'decisions', 'narratives', 'evaluations' ]

resource cont 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = [for c in containers: {
  parent: db
  name: c
  properties: { resource: { id: c, partitionKey: { paths: [ '/match_id' ], kind: 'Hash' } } }
}]

// Cosmos DB Built-in Data Contributor (data-plane RBAC)
resource cosmosRole 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = {
  parent: cosmos
  name: guid(cosmos.id, identityPrincipalId, 'datacontrib')
  properties: {
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002'
    principalId: identityPrincipalId
    scope: cosmos.id
  }
}

output eventHubNamespaceFqdn string = '${ehns.name}.servicebus.windows.net'
output cosmosEndpoint string = cosmos.properties.documentEndpoint
