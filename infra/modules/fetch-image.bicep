// The image a container app is running right now, so provisioning keeps it instead of resetting the app to the
// placeholder (the azd template pattern). Read from Azure, not from anyone's local azd .env, so it can't roll an
// app back to an older image. Empty when the app doesn't exist yet.
param name string
param exists bool

resource app 'Microsoft.App/containerApps@2024-03-01' existing = if (exists) {
  name: name
}

output image string = exists ? app!.properties.template.containers[0].image : ''
