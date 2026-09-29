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

export interface MemberInfo {
  member_number: string
  group_number: string
  first_name: string
  last_name: string
  coverage_tier: string
  effective_date: string | null
}

export interface Me {
  user_id: string
  email: string | null
  full_name: string | null
  first_name: string | null
  onboarded: boolean
  linked: boolean
  tenant_id: string | null
  plan_name: string | null
  member: MemberInfo | null
}
