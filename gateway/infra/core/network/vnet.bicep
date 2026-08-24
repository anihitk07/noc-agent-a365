targetScope = 'resourceGroup'

@description('Azure region for the virtual network resources.')
param location string = resourceGroup().location

@description('Tags applied to all taggable resources in this module.')
param tags object = {}

@description('Deterministic name suffix shared across resources in this stack.')
param nameSuffix string

@description('Unique token used where Azure requires globally-unique names.')
param resourceToken string

@description('When true, the APIM subnet admits inbound HTTPS from the internet for external VNet mode.')
param apimPublic bool = false

@description('Address space for the gateway virtual network.')
param vnetCidr string = '10.40.0.0/16'

@description('CIDR for the APIM subnet.')
param apimSubnetCidr string = '10.40.1.0/24'

@description('CIDR for the private endpoint subnet.')
param privateEndpointSubnetCidr string = '10.40.2.0/24'

@description('CIDR for the Container Apps infrastructure subnet.')
param containerAppsSubnetCidr string = '10.40.5.0/27'

var apimSecurityRules = concat([
  {
    name: 'in-client-https'
    properties: {
      description: 'Allow VNet clients to reach APIM on HTTP/HTTPS.'
      protocol: 'Tcp'
      sourcePortRange: '*'
      destinationPortRanges: [
        '80'
        '443'
      ]
      sourceAddressPrefix: 'VirtualNetwork'
      destinationAddressPrefix: 'VirtualNetwork'
      access: 'Allow'
      priority: 100
      direction: 'Inbound'
    }
  }
  {
    name: 'in-apim-management'
    properties: {
      description: 'Allow APIM management plane traffic on 3443.'
      protocol: 'Tcp'
      sourcePortRange: '*'
      destinationPortRange: '3443'
      sourceAddressPrefix: 'ApiManagement'
      destinationAddressPrefix: 'VirtualNetwork'
      access: 'Allow'
      priority: 110
      direction: 'Inbound'
    }
  }
  {
    name: 'in-load-balancer'
    properties: {
      description: 'Allow Azure load balancer health probes used by classic APIM VNet injection.'
      protocol: 'Tcp'
      sourcePortRange: '*'
      destinationPortRange: '6390'
      sourceAddressPrefix: 'AzureLoadBalancer'
      destinationAddressPrefix: 'VirtualNetwork'
      access: 'Allow'
      priority: 120
      direction: 'Inbound'
    }
  }
], apimPublic ? [
  {
    name: 'in-internet-https'
    properties: {
      description: 'Only added for APIM external mode. Pair with edge protection before using in production.'
      protocol: 'Tcp'
      sourcePortRange: '*'
      destinationPortRange: '443'
      sourceAddressPrefix: 'Internet'
      destinationAddressPrefix: 'VirtualNetwork'
      access: 'Allow'
      priority: 105
      direction: 'Inbound'
    }
  }
] : [])

resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: 'vnet-${nameSuffix}'
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        vnetCidr
      ]
    }
  }
}

resource apimNsg 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: 'nsg-apim-${nameSuffix}'
  location: location
  tags: tags
  properties: {
    securityRules: apimSecurityRules
  }
}

resource apimSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' = {
  parent: vnet
  name: 'snet-apim'
  properties: {
    addressPrefix: apimSubnetCidr
    networkSecurityGroup: {
      id: apimNsg.id
    }
  }
}

resource privateEndpointSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' = {
  parent: vnet
  name: 'snet-pe'
  properties: {
    addressPrefix: privateEndpointSubnetCidr
    privateEndpointNetworkPolicies: 'Disabled'
  }
}

resource containerAppsSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' = {
  parent: vnet
  name: 'snet-aca'
  properties: {
    addressPrefix: containerAppsSubnetCidr
    delegations: [
      {
        name: 'aca-delegation'
        properties: {
          serviceName: 'Microsoft.App/environments'
        }
      }
    ]
  }
}

resource apimPublicIp 'Microsoft.Network/publicIPAddresses@2024-05-01' = {
  name: 'pip-apim-${nameSuffix}'
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
    dnsSettings: {
      domainNameLabel: 'apim-${take(resourceToken, 12)}'
    }
  }
}

resource openAiDns 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.openai.azure.com'
  location: 'global'
  tags: tags
}

resource keyVaultDns 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.vaultcore.azure.net'
  location: 'global'
  tags: tags
}

resource cosmosDns 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.documents.azure.com'
  location: 'global'
  tags: tags
}

resource cognitiveServicesDns 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.cognitiveservices.azure.com'
  location: 'global'
  tags: tags
}

resource aiServicesDns 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.services.ai.azure.com'
  location: 'global'
  tags: tags
}

resource openAiDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: openAiDns
  name: 'link-openai'
  location: 'global'
  tags: tags
  properties: {
    virtualNetwork: {
      id: vnet.id
    }
    registrationEnabled: false
  }
}

resource keyVaultDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: keyVaultDns
  name: 'link-keyvault'
  location: 'global'
  tags: tags
  properties: {
    virtualNetwork: {
      id: vnet.id
    }
    registrationEnabled: false
  }
}

resource cosmosDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: cosmosDns
  name: 'link-cosmos'
  location: 'global'
  tags: tags
  properties: {
    virtualNetwork: {
      id: vnet.id
    }
    registrationEnabled: false
  }
}

resource cognitiveServicesDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: cognitiveServicesDns
  name: 'link-cognitiveservices'
  location: 'global'
  tags: tags
  properties: {
    virtualNetwork: {
      id: vnet.id
    }
    registrationEnabled: false
  }
}

resource aiServicesDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: aiServicesDns
  name: 'link-aiservices'
  location: 'global'
  tags: tags
  properties: {
    virtualNetwork: {
      id: vnet.id
    }
    registrationEnabled: false
  }
}

output vnetId string = vnet.id
output apimSubnetId string = apimSubnet.id
output privateEndpointSubnetId string = privateEndpointSubnet.id
output containerAppsSubnetId string = containerAppsSubnet.id
output apimPublicIpId string = apimPublicIp.id
output openAiPrivateDnsZoneId string = openAiDns.id
output keyVaultPrivateDnsZoneId string = keyVaultDns.id
output cosmosPrivateDnsZoneId string = cosmosDns.id
output cognitiveServicesPrivateDnsZoneId string = cognitiveServicesDns.id
output aiServicesPrivateDnsZoneId string = aiServicesDns.id
