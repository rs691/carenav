"use client"

import { FormEvent, useState } from "react"
import { verifyMember } from "@/lib/api"
import { Button } from "@/components/ui/button"
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"

export function MemberLinkForm({
  submitLabel = "Find my plan",
  onLinked,
  secondaryAction,
}: {
  submitLabel?: string
  onLinked: (planName: string) => void
  secondaryAction?: React.ReactNode
}) {
  const [memberNumber, setMemberNumber] = useState("")
  const [groupNumber, setGroupNumber] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const result = await verifyMember({
        member_number: memberNumber.trim() || undefined,
        group_number: groupNumber.trim(),
      })
      onLinked(result.plan_name)
    } catch (err) {
      setError(err instanceof Error ? err.message : "We couldn't verify that")
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={onSubmit}>
      <FieldGroup>
        <Field>
          <FieldLabel htmlFor="member-number">Member ID</FieldLabel>
          <Input
            id="member-number"
            placeholder="e.g. BCB100001"
            value={memberNumber}
            onChange={(e) => setMemberNumber(e.target.value)}
            autoComplete="off"
            className="uppercase"
          />
          <FieldDescription>
            On the front of your member ID card. Lets CareNav pull up your own
            coverage details.
          </FieldDescription>
        </Field>
        <Field>
          <FieldLabel htmlFor="group-number">Group / plan number</FieldLabel>
          <Input
            id="group-number"
            placeholder="e.g. BCBS-2026"
            required
            value={groupNumber}
            onChange={(e) => setGroupNumber(e.target.value)}
            autoComplete="off"
            className="uppercase"
          />
          <FieldDescription>
            Also on your card, or from your employer. On its own it links your
            plan without your personal details.
          </FieldDescription>
        </Field>
        {error && (
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
        )}
        <Field>
          <Button type="submit" disabled={loading || !groupNumber.trim()}>
            {loading ? "Checking…" : submitLabel}
          </Button>
          {secondaryAction}
        </Field>
      </FieldGroup>
    </form>
  )
}
