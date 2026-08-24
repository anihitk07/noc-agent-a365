targetScope = 'resourceGroup'

@description('Azure region for the run-ledger Container App.')
param location string = resourceGroup().location

@description('Tags applied to the run-ledger resources.')
param tags object = {}

@description('Deterministic name suffix shared across resources in this stack.')
param nameSuffix string

@description('Existing Container Apps environment resource ID.')
param managedEnvironmentId string

@description('Azure Container Registry resource ID.')
param acrId string

@description('Azure Container Registry login server.')
param acrLoginServer string

@description('Run-ledger image reference. Empty skips the app.')
param runLedgerImage string

@description('Run-ledger managed identity resource ID.')
param runLedgerIdentityId string

@description('Run-ledger managed identity principal ID.')
param runLedgerPrincipalId string

@description('Run-ledger managed identity client ID.')
param runLedgerClientId string

@description('Key Vault URL used by the run-ledger app.')
param keyVaultUrl string

@description('Key Vault secret name holding the run-token signing key.')
param runTokenSigningSecretName string = 'run-token-signing-key'

@description('Azure Managed Redis hostname. Leave empty until Redis is provisioned.')
param redisHostName string = ''

@description('Azure Managed Redis TLS port.')
param redisPort int = 10000

@description('Serialized per-model prices injected into the run-ledger app.')
param modelPricesJson string = '{}'

@description('Expose the run-ledger publicly. False keeps it internal to the environment.')
param runLedgerPublic bool = false

var runLedgerEnabled = !empty(runLedgerImage)
var appName = runLedgerEnabled ? 'ca-runledger-${nameSuffix}' : ''
var acrPullRoleDefinitionId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')

resource runLedgerAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (runLedgerEnabled) {
  name: guid(acrId, runLedgerPrincipalId, 'runledger-acrpull')
  scope: resourceGroup()
  properties: {
    principalId: runLedgerPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: acrPullRoleDefinitionId
  }
}

resource runLedgerApp 'Microsoft.App/containerApps@2024-10-02-preview' = if (runLedgerEnabled) {
  name: appName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${runLedgerIdentityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: managedEnvironmentId
    configuration: {
      activeRevisionsMode: 'Single'
      registries: [
        {
          server: acrLoginServer
          identity: runLedgerIdentityId
        }
      ]
      ingress: {
        external: runLedgerPublic
        targetPort: 8000
        transport: 'auto'
      }
    }
    template: {
      containers: [
        {
          name: 'run-ledger'
          image: runLedgerImage
          env: [
            {
              name: 'AZURE_CLIENT_ID'
              value: runLedgerClientId
            }
            {
              name: 'KEY_VAULT_URL'
              value: keyVaultUrl
            }
            {
              name: 'RUN_TOKEN_SIGNING_SECRET_NAME'
              value: runTokenSigningSecretName
            }
            {
              name: 'REDIS_HOST_NAME'
              value: redisHostName
            }
            {
              name: 'REDIS_PORT'
              value: string(redisPort)
            }
            {
              name: 'REDIS_USER_OBJECT_ID'
              value: runLedgerPrincipalId
            }
            {
              name: 'MODEL_PRICES_JSON'
              value: modelPricesJson
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 2
      }
    }
  }
}

output appName string = appName
output appFqdn string = runLedgerEnabled ? 'https://${runLedgerApp!.properties.configuration.ingress.fqdn}' : ''
