targetScope = 'resourceGroup'

type deploymentType = {
  name: string
  modelName: string
  modelVersion: string
  skuName: string
  capacity: int
}

@description('Azure region for the Azure OpenAI account.')
param location string = resourceGroup().location

@description('Tags applied to all taggable resources in this module.')
param tags object = {}

@description('Deterministic name suffix shared across resources in this stack.')
param nameSuffix string

@description('Unique token used where Azure requires globally-unique names.')
param resourceToken string

@description('Subnet used for the Azure OpenAI private endpoint.')
param privateEndpointSubnetId string

@description('Private DNS zone for privatelink.openai.azure.com.')
param privateDnsZoneId string

@description('Azure OpenAI deployments to create.')
param deployments deploymentType[]

var accountName = 'oai-${take(resourceToken, 18)}'

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: accountName
  location: location
  tags: tags
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: accountName
    disableLocalAuth: true
    publicNetworkAccess: 'Disabled'
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
      format: 'OpenAI'
      name: deployment.modelName
      version: deployment.modelVersion
    }
  }
}]

resource privateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: 'pe-oai-${nameSuffix}'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: privateEndpointSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: 'psc-oai'
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
    privateDnsZoneConfigs: [
      {
        name: 'openai'
        properties: {
          privateDnsZoneId: privateDnsZoneId
        }
      }
    ]
  }
}

output accountId string = account.id
output accountName string = account.name
output endpoint string = 'https://${accountName}.openai.azure.com'
output deploymentNames string[] = [for deployment in deployments: deployment.name]
