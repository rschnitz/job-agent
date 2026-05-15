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
        new: "bg-blue-100 text-blue-800 border-blue-200",
        ready: "bg-violet-100 text-violet-800 border-violet-200",
        applied: "bg-amber-100 text-amber-800 border-amber-200",
        acked: "bg-amber-100 text-amber-800 border-amber-200",
        screened: "bg-orange-100 text-orange-800 border-orange-200",
        screening: "bg-orange-100 text-orange-800 border-orange-200",
        interviewed: "bg-orange-100 text-orange-800 border-orange-200",
        offer: "bg-green-100 text-green-800 border-green-200",
        offered: "bg-green-100 text-green-800 border-green-200",
        accepted: "bg-emerald-100 text-emerald-800 border-emerald-200",
        rejected: "bg-red-100 text-red-800 border-red-200",
        withdrawn: "bg-zinc-100 text-zinc-700 border-zinc-200",
        ghosted: "bg-zinc-100 text-zinc-700 border-zinc-200",
        closed: "bg-zinc-100 text-zinc-700 border-zinc-200",
        declined: "bg-zinc-100 text-zinc-700 border-zinc-200",
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
