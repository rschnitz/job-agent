"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  type ColumnDef,
  type SortingState,
  type ColumnFiltersState,
  type VisibilityState,
  flexRender,
} from "@tanstack/react-table";
import { supabase, type Job, jobDisplayStatus } from "@/lib/supabase";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CompanyAvatar } from "@/components/company-avatar";
import { ArrowUpDown, ExternalLink, Columns3, X, LayoutGrid } from "lucide-react";
import { cn } from "@/lib/utils";

const DISPLAY_STATUS_ORDER: Record<string, number> = {
  offered: 0,
  interviewed: 1,
  screened: 2,
  acked: 3,
  applied: 4,
  new: 5,
  accepted: 6,
  rejected: 7,
  withdrawn: 8,
  ghosted: 9,
  closed: 10,
  declined: 11,
};

const AGENCY_COMPANIES = new Set([
  "jobgether", "remotehunter", "harnham", "lensa", "jobs via dice",
  "futuretech recruitment", "harrison clarke", "day one partners", "andiamo",
  "empathy talent", "coffeespace", "saragossa", "jack & jill", "techtree",
  "elios talent", "tessera data", "code red partners", "ladders", "nextdeavor",
  "vocator", "gruve",
]);

function computePriority(job: Job): number {
  const suit = job.ras_interest ?? job.lib_score ?? (job.haiku_score != null ? job.haiku_score * 10 : 0);
  const fit = job.ras_fit ?? null;

  // Merit (0-100)
  const merit = fit != null
    ? suit * 0.4 + fit * 7.5
    : suit * 0.7 + 15;

  // CompAdj (-10 to +15)
  let compAdj = 0;
  if (job.salary_min && job.salary_max) {
    const range = job.salary_max - job.salary_min;
    const lo = job.salary_min + 0.1 * range;
    const hi = job.salary_max - 0.1 * range;
    const avg = (200000 + job.salary_min + job.salary_max) / 3;
    const salEst = Math.min(hi, Math.max(lo, avg));
    if (salEst < 180000) compAdj = Math.max(-10, -3 + (salEst - 180000) / 40000 * 7);
    else if (salEst < 200000) compAdj = -3 * (200000 - salEst) / 20000;
    else if (salEst < 220000) compAdj = 3 * (salEst - 200000) / 20000;
    else compAdj = 3 + 12 * (1 - Math.exp(-(salEst - 220000) / 100000));
  }

  // Recency (dual-exponential, 0.50-1.30)
  let recency = 0.50; // floor when posted_at unknown
  if (job.posted_at) {
    const age = (Date.now() - new Date(job.posted_at).getTime()) / (1000 * 60 * 60 * 24);
    recency = 0.50 + 0.45 * Math.exp(-age / 14) + 0.35 * Math.exp(-age / 1.5);
  }

  // Agency discount
  const agency = AGENCY_COMPANIES.has(job.company.toLowerCase()) ? 0.75 : 1.0;

  return (merit + compAdj) * recency * agency;
}

const ACTIVE_STAGES = new Set(["new", "applied", "acked", "screened", "interviewed", "offered"]);

const columns: ColumnDef<Job>[] = [
  {
    accessorKey: "ras_id",
    header: "J-ID",
    cell: ({ row }) => (
      <span className="text-xs font-mono text-muted-foreground">{row.original.ras_id ?? "—"}</span>
    ),
    enableSorting: false,
  },
  {
    id: "priority",
    header: ({ column }) => (
      <button className="flex items-center gap-1 hover:text-foreground transition-colors" onClick={() => column.toggleSorting()}>
        Pri <ArrowUpDown className="h-3 w-3" />
      </button>
    ),
    accessorFn: (row) => computePriority(row),
    cell: ({ row }) => {
      const p = computePriority(row.original);
      const color = p >= 95 ? "text-emerald-600 font-semibold" : p >= 85 ? "text-foreground" : "text-muted-foreground";
      return <span className={`text-sm tabular-nums ${color}`}>{p.toFixed(0)}</span>;
    },
    sortingFn: "basic",
  },
  {
    accessorKey: "company",
    header: ({ column }) => (
      <button className="flex items-center gap-1 hover:text-foreground transition-colors" onClick={() => column.toggleSorting()}>
        Company <ArrowUpDown className="h-3 w-3" />
      </button>
    ),
    cell: ({ row }) => (
      <div className="flex items-center gap-2">
        <CompanyAvatar company={row.original.company} />
        <span className="font-medium text-sm">{row.original.company}</span>
      </div>
    ),
  },
  {
    accessorKey: "title",
    header: ({ column }) => (
      <button className="flex items-center gap-1 hover:text-foreground transition-colors" onClick={() => column.toggleSorting()}>
        Title <ArrowUpDown className="h-3 w-3" />
      </button>
    ),
    cell: ({ row }) => (
      <Link href={`/jobs/${row.original.id}`} className="text-sm hover:text-primary transition-colors hover:underline">
        {row.original.title}
      </Link>
    ),
  },
  {
    id: "displayStatus",
    header: ({ column }) => (
      <button className="flex items-center gap-1 hover:text-foreground transition-colors" onClick={() => column.toggleSorting()}>
        Status <ArrowUpDown className="h-3 w-3" />
      </button>
    ),
    accessorFn: (row) => jobDisplayStatus(row),
    cell: ({ row }) => {
      const ds = jobDisplayStatus(row.original);
      return <Badge variant={ds as any} className="text-[11px]">{ds}</Badge>;
    },
    sortingFn: (a, b) =>
      (DISPLAY_STATUS_ORDER[jobDisplayStatus(a.original)] ?? 99) -
      (DISPLAY_STATUS_ORDER[jobDisplayStatus(b.original)] ?? 99),
  },
  {
    accessorKey: "ras_fit",
    header: ({ column }) => (
      <button className="flex items-center gap-1 hover:text-foreground transition-colors" onClick={() => column.toggleSorting()}>
        Fit <ArrowUpDown className="h-3 w-3" />
      </button>
    ),
    cell: ({ row }) => {
      const fit = row.original.ras_fit;
      if (fit == null) return <span className="text-xs text-muted-foreground">—</span>;
      const color = fit >= 8 ? "text-emerald-600 font-semibold" : fit >= 7 ? "text-foreground" : "text-muted-foreground";
      return <span className={`text-sm tabular-nums ${color}`}>{fit}</span>;
    },
  },
  {
    accessorKey: "ras_interest",
    header: ({ column }) => (
      <button className="flex items-center gap-1 hover:text-foreground transition-colors" onClick={() => column.toggleSorting()}>
        Interest <ArrowUpDown className="h-3 w-3" />
      </button>
    ),
    cell: ({ row }) => {
      const suit = row.original.ras_interest;
      if (suit == null) return <span className="text-xs text-muted-foreground">—</span>;
      const color = suit >= 85 ? "text-emerald-600 font-semibold" : suit >= 70 ? "text-foreground" : "text-muted-foreground";
      return <span className={`text-sm tabular-nums ${color}`}>{suit}</span>;
    },
  },
  {
    accessorKey: "lib_score",
    header: ({ column }) => (
      <button className="flex items-center gap-1 hover:text-foreground transition-colors" onClick={() => column.toggleSorting()}>
        Lib <ArrowUpDown className="h-3 w-3" />
      </button>
    ),
    cell: ({ row }) => {
      const s = row.original.lib_score;
      if (s == null) return <span className="text-xs text-muted-foreground">—</span>;
      const color = s >= 75 ? "text-emerald-600 font-semibold" : s >= 60 ? "text-foreground" : "text-muted-foreground";
      return <span className={`text-sm tabular-nums ${color}`}>{s}</span>;
    },
  },
  {
    accessorKey: "haiku_score",
    header: ({ column }) => (
      <button className="flex items-center gap-1 hover:text-foreground transition-colors" onClick={() => column.toggleSorting()}>
        Haiku <ArrowUpDown className="h-3 w-3" />
      </button>
    ),
    cell: ({ row }) => {
      const h = row.original.haiku_score;
      if (h == null) return <span className="text-xs text-muted-foreground">—</span>;
      return <span className="text-sm tabular-nums text-muted-foreground">{h}</span>;
    },
  },
  {
    accessorKey: "salary_max",
    header: ({ column }) => (
      <button className="flex items-center gap-1 hover:text-foreground transition-colors" onClick={() => column.toggleSorting()}>
        Salary <ArrowUpDown className="h-3 w-3" />
      </button>
    ),
    cell: ({ row }) => {
      const min = row.original.salary_min;
      const max = row.original.salary_max;
      if (min && max) return <span className="text-xs tabular-nums">${Math.round(min/1000)}k-${Math.round(max/1000)}k</span>;
      if (max) return <span className="text-xs tabular-nums">Up to ${Math.round(max/1000)}k</span>;
      return <span className="text-xs text-muted-foreground">—</span>;
    },
  },
  {
    accessorKey: "location",
    header: "Location",
    cell: ({ row }) => (
      <span className="text-xs text-muted-foreground truncate max-w-[150px] block">{row.original.location ?? "—"}</span>
    ),
  },
  {
    accessorKey: "applicant_count",
    header: ({ column }) => (
      <button className="flex items-center gap-1 hover:text-foreground transition-colors" onClick={() => column.toggleSorting()}>
        Appl <ArrowUpDown className="h-3 w-3" />
      </button>
    ),
    cell: ({ row }) => {
      const count = row.original.applicant_count;
      if (count == null) return <span className="text-xs text-muted-foreground">—</span>;
      const color = count <= 10 ? "text-emerald-600 font-semibold" : count <= 50 ? "text-foreground" : "text-muted-foreground";
      return <span className={`text-xs tabular-nums ${color}`}>{count}</span>;
    },
  },
  {
    accessorKey: "source",
    header: "Source",
    cell: ({ row }) => (
      <span className="text-xs text-muted-foreground capitalize">{row.original.source ?? "manual"}</span>
    ),
  },
  {
    accessorKey: "created_at",
    header: ({ column }) => (
      <button className="flex items-center gap-1 hover:text-foreground transition-colors" onClick={() => column.toggleSorting()}>
        Added <ArrowUpDown className="h-3 w-3" />
      </button>
    ),
    cell: ({ row }) => (
      <span className="text-xs text-muted-foreground tabular-nums">
        {new Date(row.original.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
      </span>
    ),
  },
  {
    accessorKey: "url",
    header: "Link",
    cell: ({ row }) =>
      row.original.url ? (
        <a href={row.original.url} target="_blank" rel="noopener noreferrer" className="text-muted-foreground hover:text-primary transition-colors">
          <ExternalLink className="h-3.5 w-3.5" />
        </a>
      ) : null,
    enableSorting: false,
  },
  {
    accessorKey: "notes",
    header: "Notes",
    cell: ({ row }) =>
      row.original.notes ? (
        <span className="text-xs text-muted-foreground truncate max-w-[200px] block">{row.original.notes}</span>
      ) : null,
    enableSorting: false,
  },
];

export default function JobsTablePage() {
  const [mounted, setMounted] = useState(false);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [sorting, setSorting] = useState<SortingState>([{ id: "priority", desc: true }]);
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({ notes: false, source: false, applicant_count: false, lib_score: false, haiku_score: false });
  const [globalFilter, setGlobalFilter] = useState("");
  const [showClosed, setShowClosed] = useState(false);

  useEffect(() => { setMounted(true); }, []);

  useEffect(() => {
    supabase.from("jobs").select("*").order("created_at", { ascending: false }).then(({ data }) => {
      setJobs(data ?? []);
      setLoading(false);
    });
  }, []);

  const filteredJobs = useMemo(
    () => showClosed ? jobs : jobs.filter((j) => !j.outcome || j.outcome === "active"),
    [jobs, showClosed]
  );

  const table = useReactTable({
    data: filteredJobs,
    columns,
    state: { sorting, columnFilters, columnVisibility, globalFilter },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onColumnVisibilityChange: setColumnVisibility,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });


  const [showColumnPicker, setShowColumnPicker] = useState(false);

  if (!mounted) return null;

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl font-semibold">All Jobs</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {filteredJobs.length} jobs{!showClosed ? " (active)" : ""}
          </p>
        </div>
        <Link href="/">
          <Button variant="outline" size="sm">
            <LayoutGrid className="h-3.5 w-3.5" />
            Board view
          </Button>
        </Link>
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <Input
          placeholder="Search jobs..."
          value={globalFilter}
          onChange={(e) => setGlobalFilter(e.target.value)}
          className="max-w-xs h-8 text-sm"
        />

        {/* Active / all toggle */}
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => setShowClosed(false)}
            className={cn(
              "text-[11px] px-2 py-1 rounded-full border transition-all",
              !showClosed
                ? "bg-primary/10 border-primary/30 text-primary"
                : "border-border text-muted-foreground hover:text-foreground"
            )}
          >
            Active
          </button>
          <button
            onClick={() => setShowClosed(true)}
            className={cn(
              "text-[11px] px-2 py-1 rounded-full border transition-all",
              showClosed
                ? "bg-primary/10 border-primary/30 text-primary"
                : "border-border text-muted-foreground hover:text-foreground"
            )}
          >
            All
          </button>
        </div>

        {/* Column picker */}
        <div className="relative ml-auto">
          <Button variant="outline" size="sm" className="h-8" onClick={() => setShowColumnPicker(!showColumnPicker)}>
            <Columns3 className="h-3.5 w-3.5" />
            Columns
          </Button>
          {showColumnPicker && (
            <div className="absolute right-0 top-full mt-1 bg-card border border-border rounded-lg shadow-lg p-2 z-50 min-w-[160px]">
              {table.getAllLeafColumns().map((column) => (
                <label key={column.id} className="flex items-center gap-2 px-2 py-1.5 text-xs hover:bg-accent rounded cursor-pointer">
                  <input
                    type="checkbox"
                    checked={column.getIsVisible()}
                    onChange={column.getToggleVisibilityHandler()}
                    className="rounded"
                  />
                  <span className="capitalize">{column.id.replace("_", " ")}</span>
                </label>
              ))}
              <button
                onClick={() => setShowColumnPicker(false)}
                className="w-full text-center text-[10px] text-muted-foreground mt-1 pt-1 border-t border-border hover:text-foreground"
              >
                Close
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Table */}
      <div className="rounded-lg border border-border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <TableHead key={header.id}>
                    {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {loading ? (
              Array.from({ length: 8 }).map((_, i) => (
                <TableRow key={i}>
                  {table.getVisibleLeafColumns().map((col) => (
                    <TableCell key={col.id}><div className="h-4 bg-muted rounded animate-pulse w-24" /></TableCell>
                  ))}
                </TableRow>
              ))
            ) : table.getRowModel().rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={columns.length} className="text-center text-muted-foreground py-8">
                  No jobs match your filters.
                </TableCell>
              </TableRow>
            ) : (
              table.getRowModel().rows.map((row) => (
                <TableRow key={row.id}>
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
