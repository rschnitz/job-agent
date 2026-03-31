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
import { supabase, type Job, type JobStatus } from "@/lib/supabase";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CompanyAvatar } from "@/components/company-avatar";
import { ArrowUpDown, ExternalLink, Columns3, X, LayoutGrid } from "lucide-react";
import { cn } from "@/lib/utils";

const STATUS_ORDER: Record<JobStatus, number> = {
  offer: 0,
  interviewing: 1,
  applied: 2,
  saved: 3,
  new: 4,
  rejected: 5,
};

const ALL_STATUSES: JobStatus[] = ["new", "saved", "applied", "interviewing", "offer", "rejected"];

const columns: ColumnDef<Job>[] = [
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
    accessorKey: "status",
    header: ({ column }) => (
      <button className="flex items-center gap-1 hover:text-foreground transition-colors" onClick={() => column.toggleSorting()}>
        Status <ArrowUpDown className="h-3 w-3" />
      </button>
    ),
    cell: ({ row }) => (
      <Badge variant={row.original.status as any} className="text-[11px]">
        {row.original.status}
      </Badge>
    ),
    sortingFn: (a, b) => STATUS_ORDER[a.original.status] - STATUS_ORDER[b.original.status],
  },
  {
    accessorKey: "fit_score",
    header: ({ column }) => (
      <button className="flex items-center gap-1 hover:text-foreground transition-colors" onClick={() => column.toggleSorting()}>
        Score <ArrowUpDown className="h-3 w-3" />
      </button>
    ),
    cell: ({ row }) => {
      const score = row.original.fit_score;
      if (score == null) return <span className="text-xs text-muted-foreground">—</span>;
      const color = score >= 8 ? "text-emerald-600 font-semibold" : score >= 6 ? "text-foreground" : "text-muted-foreground";
      return <span className={`text-sm tabular-nums ${color}`}>{score}/10</span>;
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
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [sorting, setSorting] = useState<SortingState>([{ id: "created_at", desc: true }]);
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({ notes: false, source: false });
  const [globalFilter, setGlobalFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<Set<JobStatus>>(new Set(["new", "saved", "applied", "interviewing", "offer"]));

  useEffect(() => {
    supabase.from("jobs").select("*").order("created_at", { ascending: false }).then(({ data }) => {
      setJobs(data ?? []);
      setLoading(false);
    });
  }, []);

  const filteredJobs = useMemo(
    () => jobs.filter((j) => statusFilter.has(j.status)),
    [jobs, statusFilter]
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

  const toggleStatus = (s: JobStatus) => {
    setStatusFilter((prev) => {
      const next = new Set(prev);
      if (next.has(s)) next.delete(s);
      else next.add(s);
      return next;
    });
  };

  const [showColumnPicker, setShowColumnPicker] = useState(false);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl font-semibold">All Jobs</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {filteredJobs.length} jobs{statusFilter.size < 6 ? " (filtered)" : ""}
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

        {/* Status filter pills */}
        <div className="flex items-center gap-1.5">
          {ALL_STATUSES.map((s) => (
            <button
              key={s}
              onClick={() => toggleStatus(s)}
              className={cn(
                "text-[11px] px-2 py-1 rounded-full border transition-all capitalize",
                statusFilter.has(s)
                  ? "bg-primary/10 border-primary/30 text-primary"
                  : "border-border text-muted-foreground hover:text-foreground"
              )}
            >
              {s}
            </button>
          ))}
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
                  {columns.map((_, j) => (
                    <TableCell key={j}><div className="h-4 bg-muted rounded animate-pulse w-24" /></TableCell>
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
