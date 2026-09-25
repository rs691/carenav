from agents.rag_lookup import RagLookupAgent


class PriorAuthAgent(RagLookupAgent):
    def __init__(self):
        super().__init__(
            agent_id="prior_auth",
            doc_type="policy",
            prompt_id="prior_auth_status",
        )
