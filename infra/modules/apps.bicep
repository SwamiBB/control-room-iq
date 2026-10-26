param app string
param suffix string
param location string
param tags object
param identityId string
param acrLoginServer string
param logAnalyticsId string
param appInsightsConnectionString string
param eventHubNamespaceFqdn string
param cosmosEndpoint string
param foundryProjectEndpoint string
param openAiEndpoint string
// The images azd deployed last (SERVICE_*_IMAGE_NAME), so a provision keeps the running apps instead of resetting
// them to the placeholder. Empty on the very first provision, before anything is built.
param apiImageName string = ''
param ingestImageName string = ''
param webImageName string = ''

var placeholderImage = 'mcr.microsoft.com/k8se/quickstart:latest'

resource cae 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'caenv-${app}-${suffix}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: reference(logAnalyticsId, '2023-09-01').customerId
        sharedKey: listKeys(logAnalyticsId, '2023-09-01').primarySharedKey
      }
    }
  }
}

var commonEnv = [
  { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsightsConnectionString }
  { name: 'EVENTHUB_NAMESPACE', value: eventHubNamespaceFqdn }
  { name: 'COSMOS_ENDPOINT', value: cosmosEndpoint }
  { name: 'FOUNDRY_PROJECT_ENDPOINT', value: foundryProjectEndpoint }
  { name: 'AZURE_OPENAI_ENDPOINT', value: openAiEndpoint }
  { name: 'MODEL_FALLBACK_DEPLOYMENT', value: 'gpt-4.1-mini' }
  { name: 'ROUTER_QUALITY', value: 'router-quality' }
  { name: 'ROUTER_BALANCED', value: 'router-balanced' }
  { name: 'ROUTER_COST', value: 'router-cost' }
  { name: 'AZURE_CLIENT_ID', value: reference(identityId, '2023-01-31').clientId }
]

resource api 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-${app}-api-${suffix}'
  location: location
  tags: union(tags, { 'azd-service-name': 'api' })
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${identityId}': {} } }
  properties: {
    managedEnvironmentId: cae.id
    configuration: {
      // Internal: reachable only inside the environment. The web app's nginx is the one public door (#14, #22).
      ingress: { external: false, targetPort: 8000, transport: 'auto' }
      registries: [ { server: acrLoginServer, identity: identityId } ]
    }
    template: {
      containers: [ {
        name: 'api'
        image: empty(apiImageName) ? placeholderImage : apiImageName
        env: commonEnv
        resources: { cpu: json('1.0'), memory: '2Gi' }
      } ]
      // One replica: proposals, decisions and viewer sockets live in memory in the API.
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
}

resource ingest 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-${app}-ingest-${suffix}'
  location: location
  tags: union(tags, { 'azd-service-name': 'ingest' })
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${identityId}': {} } }
  properties: {
    managedEnvironmentId: cae.id
    configuration: { registries: [ { server: acrLoginServer, identity: identityId } ] }
    template: {
      containers: [ {
        name: 'ingest'
        image: empty(ingestImageName) ? placeholderImage : ingestImageName
        env: commonEnv
        resources: { cpu: json('0.5'), memory: '1Gi' }
      } ]
      // One replica until the consumer has a checkpoint store: without one, every replica reads every
      // partition and moments are duplicated, so an Event Hubs scale rule would do more harm than good.
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
}

resource web 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-${app}-web-${suffix}'
  location: location
  tags: union(tags, { 'azd-service-name': 'web' })
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${identityId}': {} } }
  properties: {
    managedEnvironmentId: cae.id
    configuration: {
      ingress: { external: true, targetPort: 8080 } // the unprivileged nginx image's port
      registries: [ { server: acrLoginServer, identity: identityId } ]
    }
    template: {
      containers: [ {
        name: 'web'
        image: empty(webImageName) ? placeholderImage : webImageName
        // The web image's nginx proxies the API paths here (#14); the API has no public address of its own.
        env: [ { name: 'API_UPSTREAM', value: 'https://${api.properties.configuration.ingress.fqdn}' } ]
        resources: { cpu: json('0.25'), memory: '0.5Gi' }
      } ]
      scale: { minReplicas: 1, maxReplicas: 2 }
    }
  }
}

output webUrl string = 'https://${web.properties.configuration.ingress.fqdn}'
