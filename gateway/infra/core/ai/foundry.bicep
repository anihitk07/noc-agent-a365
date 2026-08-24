targetScope = 'resourceGroup'

type deploymentType = {
  name: string
  modelName: string
  modelFormat: string
  modelVersion: string
  skuName: string
  capacity: int
}

@description('Azure region for the Azure AI Services / Foundry account.')
param location string = resourceGroup().location

@description('Tags applied to all taggable resources in this module.')
param tags object = {}

@description('Deterministic name suffix shared across resources in this stack.')
param nameSuffix string

@description('Unique token used where Azure requires globally-unique names.')
param resourceToken string

@description('Subnet used for the Azure AI Services private endpoint.')
param privateEndpointSubnetId string

@description('Private DNS zones for cognitiveservices, services.ai, and openai endpoints.')
param privateDnsZoneIds string[]

@description('Foundry deployments to create.')
param deployments deploymentType[]

var accountName = 'ais-${take(resourceToken, 18)}'

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: accountName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: accountName
    disableLocalAuth: true
    publicNetworkAccess: 'Disabled'
    allowProjectManagement: true
    networkAcls: {
      defaultAction: 'Deny'
      ipRules: []
      virtualNetworkRules: []
    }
  }
}

@batchSize(1) // ponytail: Azure OpenAI/Cognitive Services rejects concurrent deployment writes on the same account; serialize.
resource deploymentResources 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = [for deployment in deployments: {
  parent: account
  name: deployment.name
  sku: {
    name: deployment.skuName
    capacity: deployment.capacity
  }
  properties: {
    model: {
      format: deployment.modelFormat
      name: deployment.modelName
      version: deployment.modelVersion
    }
  }
}]

resource privateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: 'pe-ais-${nameSuffix}'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: privateEndpointSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: 'psc-ais'
        properties: {
          privateLinkServiceId: account.id
          groupIds: [
            'account'
          ]
        }
      }
    ]
  }
  // ponytail: without this, the PE PUT races the serialized model-deployment loop's
  // own PUTs onto the same account, which flips the account's provisioningState to
  // 'Accepted' mid-loop and fails the PE with AccountProvisioningStateInvalid.
  dependsOn: [
    deploymentResources
  ]
}

resource privateDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: privateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [for (zoneId, index) in privateDnsZoneIds: {
      name: 'zone-${index}'
      properties: {
        privateDnsZoneId: zoneId
      }
    }]
  }
}

output accountId string = account.id
output accountName string = account.name
output endpoint string = 'https://${accountName}.cognitiveservices.azure.com'
output endpointOpenAiV1 string = 'https://${accountName}.openai.azure.com/openai/v1'
output deploymentNames string[] = [for deployment in deployments: deployment.name]
