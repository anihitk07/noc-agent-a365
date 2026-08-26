targetScope = 'resourceGroup'

@description('Azure region for the Azure Container Registry.')
param location string = resourceGroup().location

@description('Tags applied to the registry.')
param tags object = {}

@description('Short workload prefix used in the registry name.')
param prefix string

@description('Unique token used to make the registry name globally unique.')
param resourceToken string

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: toLower(take('acr${prefix}gw${resourceToken}', 50))
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
    networkRuleBypassOptions: 'AzureServices'
  }
}

output registryId string = registry.id
output registryName string = registry.name
output loginServer string = registry.properties.loginServer
