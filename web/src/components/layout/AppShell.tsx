import {
  CheckSquare, CircleGauge, FileStack, HelpCircle, LineChart, LogOut, type LucideIcon, Menu, Settings as SettingsIcon, Timer,
} from "lucide-react";
import { type ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { useAppState } from "@/hooks/use-app-state";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import type { AppState } from "@/lib/api";

const NAV: { to: string; label: string; icon: LucideIcon; badge?: (s: AppState) => number }[] = [
  { to: "/", label: "Pipeline", icon: CircleGauge },
  { to: "/approvals", label: "Approvals", icon: CheckSquare, badge: (s) => s.approvals.length },
  { to: "/questions", label: "Questions", icon: HelpCircle, badge: (s) => s.questions.length },
  { to: "/roles", label: "Roles & resumes", icon: FileStack },
  { to: "/budgets", label: "Budgets", icon: Timer },
  { to: "/outcomes", label: "Outcomes", icon: LineChart },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
];

export default function AppShell({ children }: { children: ReactNode }) {
  const { logout } = useAuth();
  const { state } = useAppState();
  const navigate = useNavigate();
  return (
    <div className="flex min-h-svh bg-muted/30">
      <aside className="hidden w-64 shrink-0 flex-col border-r bg-background p-4 sm:flex">
        <div className="mb-6 px-2">
          <h1 className="text-lg font-semibold">applyloop</h1>
          <p className="text-xs text-muted-foreground">Your local job-search agent</p>
        </div>
        <nav className="flex-1 space-y-1">
          {NAV.map(({ to, label, icon: Icon, badge }) => {
            const count = state && badge ? badge(state) : 0;
            return (
              <NavLink
                key={to}
                to={to}
                end={to === "/"}
                className={({ isActive }) =>
                  cn(
                    "flex items-center justify-between rounded-md px-3 py-2 text-sm font-medium transition-colors",
                    isActive ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                  )
                }
              >
                <span className="flex items-center gap-2">
                  <Icon className="size-4" />
                  {label}
                </span>
                {count > 0 && <Badge variant="secondary">{count}</Badge>}
              </NavLink>
            );
          })}
        </nav>
        <Button variant="ghost" size="sm" className="justify-start gap-2 text-muted-foreground" onClick={logout}>
          <LogOut className="size-4" /> Sign out
        </Button>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b bg-background px-4 py-3 sm:hidden">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon">
                <Menu className="size-5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              {NAV.map(({ to, label, icon: Icon, badge }) => (
                <DropdownMenuItem key={to} onClick={() => navigate(to)} className="gap-2">
                  <Icon className="size-4" />
                  {label}
                  {state && badge && badge(state) > 0 && <Badge variant="secondary" className="ml-auto">{badge(state)}</Badge>}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
          <h1 className="text-base font-semibold">applyloop</h1>
          <Button variant="ghost" size="icon" onClick={logout}>
            <LogOut className="size-4" />
          </Button>
        </header>
        <main className="flex-1 overflow-y-auto p-4 sm:p-6">{children}</main>
      </div>
    </div>
  );
}
