targetScope = 'resourceGroup'

@description('Azure region for the API Management service.')
param location string = resourceGroup().location

@description('Tags applied to all taggable resources in this module.')
param tags object = {}

@description('Deterministic name suffix shared across resources in this stack.')
param nameSuffix string

@description('Unique token used where Azure requires globally-unique names.')
param resourceToken string

@description('APIM SKU name. Supports v2 names such as PremiumV2 and legacy classic Name_Capacity values such as Developer_1.')
param skuName string

@description('Publisher display name.')
param publisherName string

@description('Publisher contact email.')
param publisherEmail string

@description('Subnet for APIM PremiumV2 VNet injection.')
param apimSubnetId string

@description('Azure OpenAI account resource ID.')
param openaiAccountId string

@description('Azure AI Services / Foundry account resource ID.')
param foundryAccountId string

@description('OpenAI backend base URL for APIM.')
param openaiPathBase string

@description('Foundry backend base URL for APIM.')
param foundryV1Base string

@description('Azure OpenAI api-version used by downgrade rewrites.')
param openaiApiVersion string

@description('OpenAPI spec URL imported into APIM for Azure OpenAI compatibility.')
param openaiOpenapiSpecUrl string

@description('Application Insights resource ID used for APIM diagnostics.')
param appInsightsId string

@description('Application Insights instrumentation key used by the APIM logger.')
param appInsightsInstrumentationKey string

@description('Fallback token-per-minute limit used when a consumer has no explicit tier.')
param tokensPerMinute int

@description('Fallback token quota used when a consumer has no explicit tier.')
param tokenQuota int

@description('Fallback token quota reset period used when a consumer has no explicit tier.')
param tokenQuotaPeriod string

@description('Client-requestable deployment aliases.')
param allowedModels string[]

@description('Per-consumer rate tiers that become APIM named values.')
param rateTiers object

@allowed([
  'subscription-key'
  'entra-id'
])
@description('Authentication mode enforced by APIM.')
param clientAuthMode string

@description('Entra tenant ID used by validate-jwt when entra-id auth mode is enabled.')
param entraTenantId string

@description('Entra audience claim expected by validate-jwt when entra-id auth mode is enabled.')
param entraApiAudience string

@description('JWT claim used to derive the consumer identifier in entra-id mode.')
param entraTeamClaim string

@description('Base URL of the internal run-ledger service.')
param runLedgerBaseUrl string

@description('Run-scoped token-per-minute limit enforced before the ledger hop.')
param runTokensPerMinute int

@description('Run-scoped token quota enforced before the ledger hop.')
param runTokenQuota int

@description('Run-scoped token quota reset period enforced before the ledger hop.')
param runTokenQuotaPeriod string

@description('Resource ID of the Key Vault that stores the run-token signing secret.')
param keyVaultResourceId string

@description('Unversioned Key Vault secret identifier for the run-token signing key.')
@secure()
param runTokenSigningSecretIdentifier string

var apimName = toLower(take('apim${replace(nameSuffix, '-', '')}${resourceToken}', 50))
var skuParts = split(skuName, '_')
var skuBaseName = length(skuParts) > 1 ? skuParts[0] : skuName
var skuCapacity = length(skuParts) > 1 ? int(skuParts[1]) : 1
var openaiPolicyTemplate = loadTextContent('../../policies/openai-pipeline.xml')
var foundryPolicyTemplate = loadTextContent('../../policies/foundry-pipeline.xml')
var jwtBlock = clientAuthMode == 'entra-id' ? '<validate-jwt header-name="Authorization" failed-validation-httpcode="401" failed-validation-error-message="Unauthorized"><openid-config url="${environment().authentication.loginEndpoint}${entraTenantId}/v2.0/.well-known/openid-configuration" /><audiences><audience>${entraApiAudience}</audience></audiences><require-scheme>Bearer</require-scheme></validate-jwt>' : ''
var allowedModelsJson = string(allowedModels)
var runLedgerBaseUrlNamedValueName = 'run-ledger-base-url'
var runTokenSigningKeyNamedValueName = 'run-token-signing-key'
var runLedgerBaseUrlNamedValueReference = '{{${runLedgerBaseUrlNamedValueName}}}'
var runTokenSigningKeyNamedValueReference = '{{${runTokenSigningKeyNamedValueName}}}'
var openaiPolicy = replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(openaiPolicyTemplate, '{{JWT_BLOCK}}', jwtBlock), '{{CLIENT_AUTH_MODE}}', clientAuthMode), '{{ENTRA_TEAM_CLAIM}}', entraTeamClaim), '{{ALLOWED_MODELS_JSON}}', allowedModelsJson), '{{DEFAULT_TPM}}', string(tokensPerMinute)), '{{DEFAULT_QUOTA}}', string(tokenQuota)), '{{DEFAULT_QUOTA_PERIOD}}', tokenQuotaPeriod), '{{OPENAI_BASE_URL}}', openaiPathBase), '{{RUN_LEDGER_BASE_URL}}', runLedgerBaseUrlNamedValueReference), '{{RUN_TOKEN_SIGNING_KEY_NAMED_VALUE}}', runTokenSigningKeyNamedValueReference), '{{RUN_TOKEN_QUOTA}}', string(runTokenQuota)), '{{RUN_TOKEN_QUOTA_PERIOD}}', runTokenQuotaPeriod), '{{RUN_TOKENS_PER_MINUTE}}', string(runTokensPerMinute))
var openaiPolicyRendered = replace(replace(openaiPolicy, '{{FOUNDRY_BASE_URL}}', foundryV1Base), '{{OPENAI_API_VERSION}}', openaiApiVersion)
var foundryPolicy = replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(foundryPolicyTemplate, '{{JWT_BLOCK}}', jwtBlock), '{{CLIENT_AUTH_MODE}}', clientAuthMode), '{{ENTRA_TEAM_CLAIM}}', entraTeamClaim), '{{ALLOWED_MODELS_JSON}}', allowedModelsJson), '{{FOUNDRY_BASE_URL}}', foundryV1Base), '{{OPENAI_BASE_URL}}', openaiPathBase), '{{RUN_LEDGER_BASE_URL}}', runLedgerBaseUrlNamedValueReference), '{{RUN_TOKEN_SIGNING_KEY_NAMED_VALUE}}', runTokenSigningKeyNamedValueReference), '{{RUN_TOKEN_QUOTA}}', string(runTokenQuota)), '{{RUN_TOKEN_QUOTA_PERIOD}}', runTokenQuotaPeriod), '{{RUN_TOKENS_PER_MINUTE}}', string(runTokensPerMinute))
var foundryPolicyRendered = replace(foundryPolicy, '{{OPENAI_API_VERSION}}', openaiApiVersion)
var defaultConsumerConfig = base64('{}')
var keyVaultSecretsUserRoleDefinitionId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
var coreNamedValueEntries = [
  {
    name: 'consumer-config-json'
    value: defaultConsumerConfig
  }
  {
    name: 'allowed-models'
    value: allowedModelsJson
  }
  {
    name: 'token-tpm-default'
    value: string(tokensPerMinute)
  }
  {
    name: 'token-quota-default'
    value: string(tokenQuota)
  }
  {
    name: 'token-quota-period-default'
    value: tokenQuotaPeriod
  }
  {
    name: runLedgerBaseUrlNamedValueName
    value: runLedgerBaseUrl
  }
]
var tierTpmNamedValues = [for tierName in items(rateTiers): {
  name: 'tier-${tierName.key}-tpm'
  value: string(tierName.value.tpm)
}]
var tierQuotaNamedValues = [for tierName in items(rateTiers): {
  name: 'tier-${tierName.key}-quota'
  value: string(tierName.value.quota)
}]
var tierPeriodNamedValues = [for tierName in items(rateTiers): {
  name: 'tier-${tierName.key}-period'
  value: string(tierName.value.period)
}]
var namedValueEntries = concat(coreNamedValueEntries, tierTpmNamedValues, tierQuotaNamedValues, tierPeriodNamedValues)

resource openAiAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  scope: resourceGroup()
  name: last(split(openaiAccountId, '/'))
}

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  scope: resourceGroup()
  name: last(split(foundryAccountId, '/'))
}

resource keyVault 'Microsoft.KeyVault/vaults@2024-11-01' existing = {
  scope: resourceGroup()
  name: last(split(keyVaultResourceId, '/'))
}

resource apim 'Microsoft.ApiManagement/service@2024-05-01' = {
  name: apimName
  location: location
  tags: tags
  sku: {
    name: skuBaseName
    capacity: skuCapacity
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    publisherName: publisherName
    publisherEmail: publisherEmail
    // ponytail: PremiumV2 injection is the private-only path; use v2 integration instead if you need public inbound.
    virtualNetworkType: 'Internal'
    virtualNetworkConfiguration: {
      subnetResourceId: apimSubnetId
    }
    publicNetworkAccess: 'Enabled'
  }
}

resource apimKeyVaultSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, apim.id, 'apim-kv-secrets-user')
  scope: keyVault
  properties: {
    principalId: apim.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: keyVaultSecretsUserRoleDefinitionId
  }
}

resource appInsightsLogger 'Microsoft.ApiManagement/service/loggers@2024-05-01' = {
  parent: apim
  name: 'appinsights'
  properties: {
    loggerType: 'applicationInsights'
    resourceId: appInsightsId
    credentials: {
      instrumentationKey: appInsightsInstrumentationKey
    }
  }
}

resource namedValues 'Microsoft.ApiManagement/service/namedValues@2024-05-01' = [for entry in namedValueEntries: {
  parent: apim
  name: entry.name
  properties: {
    displayName: entry.name
    value: entry.value
    secret: false
  }
}]

resource runTokenSigningKeyNamedValue 'Microsoft.ApiManagement/service/namedValues@2024-05-01' = {
  parent: apim
  name: runTokenSigningKeyNamedValueName
  properties: {
    displayName: runTokenSigningKeyNamedValueName
    keyVault: {
      secretIdentifier: runTokenSigningSecretIdentifier
    }
    secret: true
  }
  dependsOn: [
    apimKeyVaultSecretsUser
  ]
}

resource openAiApi 'Microsoft.ApiManagement/service/apis@2024-05-01' = {
  parent: apim
  name: 'openai-gateway'
  properties: {
    path: 'openai'
    displayName: 'Azure OpenAI gateway'
    format: 'openapi-link'
    value: openaiOpenapiSpecUrl
    protocols: [
      'https'
    ]
    subscriptionRequired: clientAuthMode == 'subscription-key'
  }
}

resource foundryApi 'Microsoft.ApiManagement/service/apis@2024-05-01' = {
  parent: apim
  name: 'foundry-gateway'
  properties: {
    path: 'foundry'
    displayName: 'Foundry gateway'
    format: 'openapi+json'
    value: '{"openapi":"3.0.1","info":{"title":"Foundry proxy","version":"1.0.0"},"paths":{"/responses":{"post":{"responses":{"200":{"description":"OK"}}}}}}'
    protocols: [
      'https'
    ]
    subscriptionRequired: clientAuthMode == 'subscription-key'
  }
}

resource openAiApiPolicy 'Microsoft.ApiManagement/service/apis/policies@2024-05-01' = {
  parent: openAiApi
  name: 'policy'
  properties: {
    format: 'xml'
    value: openaiPolicyRendered
  }
}

resource foundryApiPolicy 'Microsoft.ApiManagement/service/apis/policies@2024-05-01' = {
  parent: foundryApi
  name: 'policy'
  properties: {
    format: 'xml'
    value: foundryPolicyRendered
  }
}

resource openAiDiagnostics 'Microsoft.ApiManagement/service/apis/diagnostics@2024-05-01' = {
  parent: openAiApi
  name: 'applicationinsights'
  properties: {
    loggerId: appInsightsLogger.id
    sampling: {
      samplingType: 'fixed'
      percentage: 100
    }
    frontend: {
      request: {
        headers: [
          '*'
        ]
        body: {
          bytes: 0
        }
      }
      response: {
        headers: [
          '*'
        ]
        body: {
          bytes: 0
        }
      }
    }
    backend: {
      request: {
        headers: [
          '*'
        ]
        body: {
          bytes: 0
        }
      }
      response: {
        headers: [
          '*'
        ]
        body: {
          bytes: 0
        }
      }
    }
    metrics: true
    verbosity: 'information'
    httpCorrelationProtocol: 'W3C'
  }
}

resource foundryDiagnostics 'Microsoft.ApiManagement/service/apis/diagnostics@2024-05-01' = {
  parent: foundryApi
  name: 'applicationinsights'
  properties: {
    loggerId: appInsightsLogger.id
    sampling: {
      samplingType: 'fixed'
      percentage: 100
    }
    frontend: {
      request: {
        headers: [
          '*'
        ]
        body: {
          bytes: 0
        }
      }
      response: {
        headers: [
          '*'
        ]
        body: {
          bytes: 0
        }
      }
    }
    backend: {
      request: {
        headers: [
          '*'
        ]
        body: {
          bytes: 0
        }
      }
      response: {
        headers: [
          '*'
        ]
        body: {
          bytes: 0
        }
      }
    }
    metrics: true
    verbosity: 'information'
    httpCorrelationProtocol: 'W3C'
  }
}

resource openAiUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(apim.id, openAiAccount.id, 'openai-user')
  scope: openAiAccount
  properties: {
    principalId: apim.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
  }
}

resource foundryUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(apim.id, foundryAccount.id, 'foundry-user')
  scope: foundryAccount
  properties: {
    principalId: apim.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'a97b65f3-24c7-4388-baec-2e87135dc908')
  }
}

output apimId string = apim.id
output apimName string = apim.name
output gatewayUrl string = 'https://${apim.name}.azure-api.net'
output privateIpAddress string = !empty(apim.properties.privateIPAddresses) ? apim.properties.privateIPAddresses[0] : ''
output identityPrincipalId string = apim.identity.principalId
