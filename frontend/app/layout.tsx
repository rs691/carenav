import type { Metadata } from "next"
import { Source_Sans_3, Fraunces, Geist } from "next/font/google"
import { AppShell } from "@/components/layout/app-shell"
import { ThemeProvider } from "@/components/theme-provider"
import { TooltipProvider } from "@/components/ui/tooltip"
import "./globals.css"
import { cn } from "@/lib/utils"

const geist = Geist({ subsets: ["latin"], variable: "--font-sans" })

const sans = Source_Sans_3({
  variable: "--font-care-sans",
  subsets: ["latin"],
})

const display = Fraunces({
  variable: "--font-care-display",
  subsets: ["latin"],
})

export const metadata: Metadata = {
  title: "CareNav",
  description: "Multi-tenant healthcare benefits assistant",
}

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={cn(
        "h-full",
        "antialiased",
        sans.variable,
        display.variable,
        "font-sans",
        geist.variable,
      )}
    >
      <body className="min-h-full font-[family-name:var(--font-care-sans)]">
        <ThemeProvider defaultTheme="system" storageKey="carenav-ui-theme">
          <TooltipProvider>
            <AppShell>{children}</AppShell>
          </TooltipProvider>
        </ThemeProvider>
      </body>
    </html>
  )
}
