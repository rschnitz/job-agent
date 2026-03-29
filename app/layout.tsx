import type { Metadata } from "next";
import { Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";
import Link from "next/link";
import { Briefcase } from "lucide-react";
import { NavLinks } from "@/components/nav-links";

const jakartaSans = Plus_Jakarta_Sans({ subsets: ["latin"], weight: ["400", "500", "600", "700"] });

export const metadata: Metadata = {
  title: "Job Agent",
  description: "AI-powered job tracking and application assistant",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${jakartaSans.className} bg-background text-foreground min-h-screen`}>
        <nav className="sticky top-0 z-50 border-b border-border bg-background/80 backdrop-blur-sm px-6 py-3 flex items-center gap-1">
          <Link href="/" className="font-bold text-foreground mr-4 flex items-center gap-2 whitespace-nowrap">
            <div className="h-6 w-6 rounded-md bg-primary flex items-center justify-center">
              <Briefcase className="h-3.5 w-3.5 text-white" />
            </div>
            Job Agent
          </Link>
          <NavLinks />
        </nav>
        <main className="p-6">{children}</main>
      </body>
    </html>
  );
}
