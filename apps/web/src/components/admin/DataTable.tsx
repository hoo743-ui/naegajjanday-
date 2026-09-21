"use client";

import type { ReactNode } from "react";
import { EmptyState, ErrorState } from "@/components/mascot/EmptyState";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { JjaniMood } from "@/lib/mascot-copy";
import { cn } from "@/lib/utils";

export interface Column<T> {
  key: string;
  header: ReactNode;
  cell: (row: T) => ReactNode;
  align?: "left" | "right" | "center";
  /** 좁은 화면에서 숨길 열 */
  hideBelow?: "sm" | "md" | "lg";
  className?: string;
}

interface DataTableProps<T> {
  /** 스크린리더용 표 제목 */
  caption: string;
  columns: Column<T>[];
  rows: T[] | undefined;
  rowKey: (row: T) => string;
  isLoading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  empty: { title: string; description?: ReactNode; mood?: JjaniMood; action?: ReactNode };
  /** 행 선택 (체크박스). 넘기면 선택 열이 생긴다. */
  selection?: {
    selected: ReadonlySet<string>;
    onChange: (next: Set<string>) => void;
    isSelectable?: (row: T) => boolean;
  };
  onRowClick?: (row: T) => void;
  rowLabel?: (row: T) => string;
  minWidth?: number;
}

const HIDE = { sm: "hidden sm:table-cell", md: "hidden md:table-cell", lg: "hidden lg:table-cell" } as const;
const ALIGN = { left: "text-left", right: "text-right", center: "text-center" } as const;

export function DataTable<T>({
  caption,
  columns,
  rows,
  rowKey,
  isLoading = false,
  error,
  onRetry,
  empty,
  selection,
  onRowClick,
  rowLabel,
  minWidth = 640,
}: DataTableProps<T>) {
  if (error && !rows) return <ErrorState error={error} onRetry={onRetry} size="sm" />;

  if (isLoading && !rows) {
    return (
      <div role="status" aria-label={`${caption} 불러오는 중`} className="grid gap-2">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="h-12 rounded-xl" />
        ))}
      </div>
    );
  }

  if (!rows || rows.length === 0) {
    return (
      <EmptyState mood={empty.mood ?? "think"} title={empty.title} description={empty.description} size="sm">
        {empty.action}
      </EmptyState>
    );
  }

  const selectable = selection ? rows.filter((r) => selection.isSelectable?.(r) ?? true) : [];
  const allSelected = selectable.length > 0 && selectable.every((r) => selection?.selected.has(rowKey(r)));
  const someSelected = selectable.some((r) => selection?.selected.has(rowKey(r)));

  const toggleAll = (checked: boolean) => {
    if (!selection) return;
    const next = new Set(selection.selected);
    for (const row of selectable) {
      if (checked) next.add(rowKey(row));
      else next.delete(rowKey(row));
    }
    selection.onChange(next);
  };

  const toggleRow = (id: string, checked: boolean) => {
    if (!selection) return;
    const next = new Set(selection.selected);
    if (checked) next.add(id);
    else next.delete(id);
    selection.onChange(next);
  };

  return (
    <div className="overflow-x-auto rounded-2xl border">
      <Table style={{ minWidth }}>
        <caption className="sr-only">{caption}</caption>
        <TableHeader className="bg-soft">
          <TableRow className="hover:bg-transparent">
            {selection ? (
              <TableHead className="w-10 pl-4">
                <Checkbox
                  aria-label="이 페이지의 모든 행 선택"
                  checked={allSelected ? true : someSelected ? "indeterminate" : false}
                  onCheckedChange={(v) => toggleAll(v === true)}
                  disabled={selectable.length === 0}
                />
              </TableHead>
            ) : null}
            {columns.map((col) => (
              <TableHead
                key={col.key}
                scope="col"
                className={cn(
                  "h-11 text-xs font-extrabold whitespace-nowrap text-ink-2",
                  ALIGN[col.align ?? "left"],
                  col.hideBelow && HIDE[col.hideBelow],
                  col.className,
                )}
              >
                {col.header}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => {
            const id = rowKey(row);
            const canSelect = selection ? (selection.isSelectable?.(row) ?? true) : false;
            const isSelected = selection?.selected.has(id) ?? false;
            return (
              <TableRow
                key={id}
                data-state={isSelected ? "selected" : undefined}
                className={cn("data-[state=selected]:bg-blue-soft/60", onRowClick && "cursor-pointer")}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
              >
                {selection ? (
                  <TableCell className="w-10 pl-4" onClick={(e) => e.stopPropagation()}>
                    <Checkbox
                      aria-label={`${rowLabel?.(row) ?? id} 선택`}
                      checked={isSelected}
                      disabled={!canSelect}
                      onCheckedChange={(v) => toggleRow(id, v === true)}
                    />
                  </TableCell>
                ) : null}
                {columns.map((col, ci) => (
                  <TableCell
                    key={col.key}
                    className={cn("py-3 text-sm text-ink", ALIGN[col.align ?? "left"], col.hideBelow && HIDE[col.hideBelow], col.className)}
                  >
                    {ci === 0 && onRowClick ? (
                      // 키보드 사용자를 위해 첫 열은 실제 버튼으로 연다
                      <button
                        type="button"
                        className="text-left font-bold hover:text-blue-deep"
                        onClick={(e) => {
                          e.stopPropagation();
                          onRowClick(row);
                        }}
                      >
                        {col.cell(row)}
                      </button>
                    ) : (
                      col.cell(row)
                    )}
                  </TableCell>
                ))}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
