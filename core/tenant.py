from dataclasses import dataclass, field


@dataclass
class TenantConfig:
    tenant_id: str
    plan_name: str
    rag_namespace: str           # Qdrant collection name
    formulary_version: str
    enabled_agents: list[str]
    tone_profile: str            # "empathetic_plain" | "clinical_formal"
    sso_provider: str
    plan_doc_ids: list[str] = field(default_factory=list)


# Seed configs — in production these come from the DB
TENANT_REGISTRY: dict[str, TenantConfig] = {
    "tenant_bcbs": TenantConfig(
        tenant_id="tenant_bcbs",
        plan_name="BlueCross Premier PPO",
        rag_namespace="tenant_bcbs_2026",
        formulary_version="2026-Q1",
        enabled_agents=["benefits", "formulary", "claims", "prior_auth", "escalation"],
        tone_profile="empathetic_plain",
        sso_provider="azure_ad",
    ),
    "tenant_medicaid": TenantConfig(
        tenant_id="tenant_medicaid",
        plan_name="Illinois Medicaid",
        rag_namespace="tenant_medicaid_il_2026",
        formulary_version="2026-medicaid",
        enabled_agents=["benefits", "formulary", "escalation"],
        tone_profile="plain_language",
        sso_provider="state_idp",
    ),
    "tenant_employer": TenantConfig(
        tenant_id="tenant_employer",
        plan_name="Acme Corp Benefits",
        rag_namespace="tenant_acme_2026",
        formulary_version="2026-acme",
        enabled_agents=["benefits", "claims", "escalation"],
        tone_profile="corporate_formal",
        sso_provider="okta",
    ),
}


def get_tenant(tenant_id: str) -> TenantConfig:
    config = TENANT_REGISTRY.get(tenant_id)
    if not config:
        raise ValueError(f"Unknown tenant: {tenant_id}")
    return config