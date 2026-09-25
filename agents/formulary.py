from agents.rag_lookup import RagLookupAgent


class FormularyAgent(RagLookupAgent):
    def __init__(self):
        super().__init__(
            agent_id="formulary",
            doc_type="formulary",
            prompt_id="formulary_lookup",
        )
