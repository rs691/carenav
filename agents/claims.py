from agents.rag_lookup import RagLookupAgent


class ClaimsAgent(RagLookupAgent):
    def __init__(self):
        super().__init__(
            agent_id="claims",
            doc_type="policy",
            prompt_id="claim_status",
        )
