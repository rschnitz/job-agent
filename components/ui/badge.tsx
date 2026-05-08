import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        outline: "text-foreground",
        new: "border-transparent bg-blue-500/20 text-blue-300 border-blue-500/30",
        ready: "border-transparent bg-violet-500/20 text-violet-300 border-violet-500/30",
        applied: "border-transparent bg-yellow-500/20 text-yellow-300 border-yellow-500/30",
        acked: "border-transparent bg-yellow-500/20 text-yellow-300 border-yellow-500/30",
        screened: "border-transparent bg-orange-500/20 text-orange-300 border-orange-500/30",
        screening: "border-transparent bg-orange-500/20 text-orange-300 border-orange-500/30",
        interviewed: "border-transparent bg-orange-500/20 text-orange-300 border-orange-500/30",
        offer: "border-transparent bg-green-500/20 text-green-300 border-green-500/30",
        offered: "border-transparent bg-green-500/20 text-green-300 border-green-500/30",
        accepted: "border-transparent bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
        rejected: "border-transparent bg-red-500/20 text-red-400 border-red-500/30",
        withdrawn: "border-transparent bg-zinc-500/20 text-zinc-400 border-zinc-500/30",
        ghosted: "border-transparent bg-zinc-500/20 text-zinc-400 border-zinc-500/30",
        closed: "border-transparent bg-zinc-500/20 text-zinc-400 border-zinc-500/30",
        declined: "border-transparent bg-zinc-500/20 text-zinc-400 border-zinc-500/30",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
