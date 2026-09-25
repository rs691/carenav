export type ChatRole = "user" | "assistant"

export interface ChatMessage {
  id: string
  role: ChatRole
  content: string
  agentUsed?: string | null
  intent?: string | null
  phiScrubbed?: boolean
}

export interface ChatRequest {
  member_id: string
  session_id: string
  message: string
}

export interface ChatResponse {
  reply: string
  agent_used: string | null
  intent: string | null
  confidence: number | null
  phi_scrubbed: boolean
  turn_count: number
}
