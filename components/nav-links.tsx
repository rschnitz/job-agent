"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Briefcase, List, MessageSquare, User, LayoutList, ArrowLeftRight } from "lucide-react";
import { cn } from "@/lib/utils";

const links = [
  { href: "/", icon: Briefcase, label: "Board" },
  { href: "/jobs", icon: List, label: "Table" },
  { href: "/pipeline", icon: LayoutList, label: "Pipeline" },
  { href: "/compare", icon: ArrowLeftRight, label: "Compare" },
  { href: "/chat", icon: MessageSquare, label: "Chat" },
  { href: "/profile", icon: User, label: "Profile" },
];

export function NavLinks() {
  const pathname = usePathname();
  return (
    <>
      {links.map(({ href, icon: Icon, label }) => {
        const active = pathname === href;
        return (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-md transition-colors",
              active
                ? "bg-primary/10 text-primary font-medium"
                : "text-muted-foreground hover:text-foreground hover:bg-accent"
            )}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </Link>
        );
      })}
    </>
  );
}
