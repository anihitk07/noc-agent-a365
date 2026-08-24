"""Production entrypoint: Key Vault-managed signing key + Azure Managed Redis client."""

import logging
import os
import time

from azure.core.credentials import AccessToken

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from redis.credentials import CredentialProvider
from redis.asyncio import Redis

from run_ledger.app import AppDeps, app_factory
from run_ledger.config import Settings
from run_ledger.service import RunLedgerService, RunTokenSigner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


class EntraRedisCredentialProvider(CredentialProvider):
    def __init__(self, credential: DefaultAzureCredential, username: str):
        self._credential = credential
        self._username = username
        self._token: AccessToken | None = None

    def _current_token(self) -> str:
        if self._token is None or self._token.expires_on <= time.time() + 120:
            self._token = self._credential.get_token("https://redis.azure.com/.default")
        return self._token.token

    def get_credentials(self):
        return self._username, self._current_token()

    async def get_credentials_async(self):
        return self.get_credentials()


def build_app():
    settings = Settings.from_env()
    credential = DefaultAzureCredential()
    secret_client = SecretClient(vault_url=settings.key_vault_url, credential=credential)
    signing_secret = secret_client.get_secret(settings.run_token_signing_secret_name).value

    redis_credential_provider = EntraRedisCredentialProvider(
        credential=credential,
        username=os.environ["REDIS_USER_OBJECT_ID"],
    )
    redis = Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        ssl=True,
        decode_responses=True,
        credential_provider=redis_credential_provider,
        socket_timeout=10,
        socket_connect_timeout=10,
    )

    signer = RunTokenSigner(
        issuer=settings.jwt_issuer,
        secret=signing_secret,
        lifetime_seconds=settings.jwt_lifetime_seconds,
    )
    service = RunLedgerService(redis=redis, signer=signer, settings=settings)
    return app_factory(AppDeps(service=service))


app = build_app()
