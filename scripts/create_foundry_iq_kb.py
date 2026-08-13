#!/usr/bin/env python3
"""
Create the Foundry IQ knowledge source + knowledge base over the NOC corpus
(runbooks, tickets, equipment specs, infra specs).

Pattern follows the Build26 LAB532 "File Knowledge Source" notebook:
  1. Create a FILE knowledge source per corpus folder (service auto-chunks + embeds).
  2. Upload every doc in data/{runbooks,tickets,equipment_specs,infra_specs}.
  3. Create one knowledge base (answerSynthesis) spanning all four sources.

The knowledge base is exposed by Azure AI Search at:
  {search}/knowledgebases/{kb}/mcp?api-version=2026-05-01-preview
which infra/main.bicep wires into the Foundry project as an MCP RemoteTool
connection (kb-mcp-connection) so the MAF agent can call it as a Foundry IQ tool.

Env vars required:
  AZURE_AI_SEARCH_SERVICE_ENDPOINT   e.g. https://search-xxxxx.search.windows.net
  AZURE_OPENAI_ENDPOINT              e.g. https://ai-account-xxxxx.services.ai.azure.com
Optional:
  EMBEDDING_DEPLOYMENT   default: text-embedding-3-small
  CHAT_DEPLOYMENT        default: gpt-5.4
  KB_NAME                default: noc-knowledge-kb
  DATA_DIR                default: <repo>/data
"""

import os
from pathlib import Path

from azure.identity import AzureCliCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    AzureOpenAIVectorizerParameters,
    FileKnowledgeSource,
    FileKnowledgeSourceParameters,
    KnowledgeBase,
    KnowledgeBaseAzureOpenAIModel,
    KnowledgeSourceReference,
)
from azure.search.documents.knowledgebases.models import (
    KnowledgeRetrievalOutputMode,
    KnowledgeSourceAzureOpenAIVectorizer,
    KnowledgeSourceIngestionParameters,
)

SEARCH_ENDPOINT = os.environ["AZURE_AI_SEARCH_SERVICE_ENDPOINT"]
AOAI_ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"]
EMBED_DEPLOY = os.environ.get("EMBEDDING_DEPLOYMENT", "text-embedding-3-small")
CHAT_DEPLOY = os.environ.get("CHAT_DEPLOYMENT", "gpt-5.4")
KB_NAME = os.environ.get("KB_NAME", "noc-knowledge-kb")
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parent.parent / "data"))

# Corpus folder -> knowledge source name
CORPORA = {
    "runbooks": "noc-runbooks-ks",
    "tickets": "noc-tickets-ks",
    "equipment_specs": "noc-equipment-ks",
    "infra_specs": "noc-infra-specs-ks",
}

# Azure AI Search has local auth disabled -> use AAD.
# Requires "Search Index Data Contributor" + "Search Service Contributor" on the service.
cred = AzureCliCredential()
index_client = SearchIndexClient(endpoint=SEARCH_ENDPOINT, credential=cred)

ks_refs = []
for folder_name, ks_name in CORPORA.items():
    folder = DATA_DIR / folder_name
    if not folder.is_dir():
        print(f"  WARNING: {folder} not found, skipping.")
        continue

    file_ks = FileKnowledgeSource(
        name=ks_name,
        description=f"NOC {folder_name.replace('_', ' ')} corpus (Foundry IQ knowledge source).",
        file_parameters=FileKnowledgeSourceParameters(
            ingestion_parameters=KnowledgeSourceIngestionParameters(
                embedding_model=KnowledgeSourceAzureOpenAIVectorizer(
                    azure_open_ai_parameters=AzureOpenAIVectorizerParameters(
                        resource_url=AOAI_ENDPOINT,
                        deployment_name=EMBED_DEPLOY,
                        model_name=EMBED_DEPLOY,
                    )
                ),
                content_extraction_mode="minimal",
            )
        ),
    )
    index_client.create_or_update_knowledge_source(file_ks)
    print(f"[ks] '{ks_name}' created/updated.")

    docs = sorted(p for p in folder.iterdir() if p.is_file())
    for doc in docs:
        content = doc.read_bytes()
        uploaded = index_client.upload_knowledge_source_file(ks_name, content, filename=doc.name)
        print(f"    uploaded {doc.name} (file_id={getattr(uploaded, 'file_id', '?')})")

    ks_refs.append(KnowledgeSourceReference(name=ks_name))

if not ks_refs:
    raise SystemExit("No corpus folders found under DATA_DIR -- nothing to index.")

kb = KnowledgeBase(
    name=KB_NAME,
    description="Foundry IQ knowledge base over NOC runbooks, tickets, equipment and infra specs.",
    models=[
        KnowledgeBaseAzureOpenAIModel(
            azure_open_ai_parameters=AzureOpenAIVectorizerParameters(
                resource_url=AOAI_ENDPOINT,
                deployment_name=CHAT_DEPLOY,
                model_name=CHAT_DEPLOY,
            )
        )
    ],
    knowledge_sources=ks_refs,
    output_mode=KnowledgeRetrievalOutputMode.ANSWER_SYNTHESIS,
)
kb.retrieval_instructions = (
    "Use this knowledge base for questions about incident runbooks (fibre cuts, BGP flaps, "
    "amplifier failures, power outages), past ticket resolutions, field equipment specs "
    "(OTDR, splicers, safety kit), and site/link infra specs (amplifier sites, MPLS paths, "
    "SLA terms). Prefer the most specific matching source."
)
kb.answer_instructions = (
    "Answer strictly from retrieved content. Cite the runbook, ticket ID, or spec document. "
    "If the corpus does not cover the question, say so rather than guessing."
)
index_client.create_or_update_knowledge_base(kb)
print(f"[kb] '{KB_NAME}' created/updated over {len(ks_refs)} knowledge source(s).")

mcp = f"{SEARCH_ENDPOINT}/knowledgebases/{KB_NAME}/mcp?api-version=2026-05-01-preview"
print(f"\nFoundry IQ knowledge base MCP endpoint:\n  {mcp}")
