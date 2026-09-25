"use client"

import * as React from "react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { GalleryVerticalEndIcon, MessageSquarePlusIcon } from "lucide-react"
import { createChatId } from "@/lib/session"
import { createClient } from "@/lib/supabase/client"
import { SearchForm } from "@/components/search-form"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar"
import { ModeToggle } from "@/components/mode-toggle"
import { Button } from "@/components/ui/button"

const DEFAULT_LOCAL = "en"
const DEFAULT_WORKSPACE = "default"

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const router = useRouter()
  const pathname = usePathname()
  const [signedIn, setSignedIn] = React.useState(false)

  React.useEffect(() => {
    if (!process.env.NEXT_PUBLIC_SUPABASE_URL) return
    const supabase = createClient()
    supabase.auth.getSession().then(({ data }) => {
      setSignedIn(!!data.session)
    })
    const { data: sub } = supabase.auth.onAuthStateChange((_e, session) => {
      setSignedIn(!!session)
    })
    return () => sub.subscription.unsubscribe()
  }, [])

  function newChat() {
    const id = createChatId()
    router.push(`/${DEFAULT_LOCAL}/${DEFAULT_WORKSPACE}/chat/${id}`)
  }

  async function signOut() {
    const supabase = createClient()
    await supabase.auth.signOut()
    sessionStorage.removeItem("carenav_access_token")
    router.push("/login")
    router.refresh()
  }

  const chatActive =
    pathname?.includes("/chat/") || pathname === "/" || pathname === null

  return (
    <Sidebar {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              size="lg"
              render={<Link href="/" />}
            >
              <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                <GalleryVerticalEndIcon className="size-4" />
              </div>
              <div className="flex flex-col gap-0.5 leading-none">
                <span className="font-medium">CareNav</span>
                <span className="text-muted-foreground">Benefits chat</span>
              </div>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
        <SearchForm
          onSubmit={(e) => {
            e.preventDefault()
          }}
        />
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Chat</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton
                  isActive={!!chatActive}
                  onClick={newChat}
                >
                  <MessageSquarePlusIcon />
                  New chat
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
        <SidebarGroup>
          <SidebarGroupLabel>Account</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton
                  isActive={pathname === "/settings"}
                  render={<Link href="/settings" />}
                >
                  Settings
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                {signedIn ? (
                  <SidebarMenuButton onClick={signOut}>
                    Sign out
                  </SidebarMenuButton>
                ) : (
                  <SidebarMenuButton
                    isActive={pathname === "/login"}
                    render={<Link href="/login" />}
                  >
                    Sign in
                  </SidebarMenuButton>
                )}
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <div className="flex items-center justify-between gap-2 px-2 pb-2">
          <Button variant="outline" size="sm" onClick={newChat} className="flex-1">
            New chat
          </Button>
          <ModeToggle />
        </div>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
