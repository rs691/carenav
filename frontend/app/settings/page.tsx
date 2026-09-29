"use client"

import { useState } from "react"
import { unlinkMember } from "@/lib/api"
import { useMe } from "@/lib/use-me"
import { MemberLinkForm } from "@/components/member-link-form"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Field, FieldLabel } from "@/components/ui/field"
import { ModeToggle } from "@/components/mode-toggle"

export default function SettingsPage() {
  const { me, loading, error, refresh } = useMe()
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  async function unlink() {
    setActionError(null)
    setBusy(true)
    try {
      await unlinkMember()
      await refresh()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Couldn't unlink your plan")
    } finally {
      setBusy(false)
    }
  }

  async function linked() {
    setEditing(false)
    await refresh()
  }

  const showForm = editing || (me && !me.linked)

  return (
    <div className="mx-auto flex w-full max-w-lg flex-col gap-6 p-6 md:p-8">
      <Card>
        <CardHeader>
          <CardTitle>Your health plan</CardTitle>
          <CardDescription>
            {me?.linked
              ? "CareNav answers using your plan's documents."
              : "Not linked. CareNav gives general answers until you link a plan."}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {loading && !me && <p className="text-sm text-muted-foreground">Loading…</p>}
          {error && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}

          {me?.linked && !editing && (
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
              <dt className="text-muted-foreground">Plan</dt>
              <dd>{me.plan_name}</dd>
              {me.member ? (
                <>
                  <dt className="text-muted-foreground">Member</dt>
                  <dd>
                    {me.member.first_name} {me.member.last_name}
                  </dd>
                  <dt className="text-muted-foreground">Member ID</dt>
                  <dd>{me.member.member_number}</dd>
                  <dt className="text-muted-foreground">Group</dt>
                  <dd>{me.member.group_number}</dd>
                  <dt className="text-muted-foreground">Coverage</dt>
                  <dd>{me.member.coverage_tier}</dd>
                </>
              ) : (
                <>
                  <dt className="text-muted-foreground">Member</dt>
                  <dd>Plan only: add your member ID for personal details</dd>
                </>
              )}
            </dl>
          )}

          {me?.linked && !editing && (
            <div className="flex gap-2">
              <Button type="button" variant="outline" onClick={() => setEditing(true)}>
                {me.member ? "Change" : "Add member ID"}
              </Button>
              <Button type="button" variant="ghost" disabled={busy} onClick={unlink}>
                {busy ? "Unlinking…" : "Unlink plan"}
              </Button>
            </div>
          )}

          {showForm && (
            <MemberLinkForm
              submitLabel={me?.linked ? "Update" : "Link my plan"}
              onLinked={linked}
              secondaryAction={
                editing ? (
                  <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
                    Cancel
                  </Button>
                ) : undefined
              }
            />
          )}

          {actionError && (
            <p className="text-sm text-destructive" role="alert">
              {actionError}
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Account</CardTitle>
          <CardDescription>{me?.email ?? ""}</CardDescription>
        </CardHeader>
        <CardContent>
          <Field>
            <FieldLabel>Appearance</FieldLabel>
            <div className="flex items-center gap-3">
              <ModeToggle />
              <span className="text-sm text-muted-foreground">Light / dark / system</span>
            </div>
          </Field>
        </CardContent>
      </Card>
    </div>
  )
}
