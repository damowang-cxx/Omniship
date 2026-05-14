import Link from "next/link";
import type { AirWaybillItem } from "@/lib/types";
import type {
  AirWaybillSortState,
  SortableAirWaybillKey
} from "@/lib/sort";
import { ArrowDown, ArrowUp, RotateCcw } from "lucide-react";
import { StatusBadge } from "./StatusBadge";
import styles from "./AirWaybillsTable.module.css";

const columns: Array<{
  key: keyof AirWaybillItem;
  label: string;
  sortable?: boolean;
}> = [
  { key: "number", label: "Number", sortable: true },
  { key: "status", label: "Status", sortable: true },
  { key: "weightKgRaw", label: "Weight(kg)", sortable: true },
  { key: "receivedRaw", label: "Received", sortable: true },
  { key: "parcelsRaw", label: "Parcels", sortable: true },
  { key: "inWarehouseRaw", label: "In Warehouse" },
  { key: "releasedRaw", label: "Released" },
  { key: "outboundRaw", label: "Out Bound" }
];

function getSortIcon(
  sortState: AirWaybillSortState,
  key: SortableAirWaybillKey
) {
  if (!sortState || sortState.key !== key) {
    return <ArrowUp aria-hidden="true" size={14} />;
  }

  if (sortState.direction === "asc") {
    return <ArrowDown aria-hidden="true" size={14} />;
  }

  return <RotateCcw aria-hidden="true" size={14} />;
}

function getSortLabel(
  sortState: AirWaybillSortState,
  key: SortableAirWaybillKey,
  label: string
) {
  if (!sortState || sortState.key !== key) {
    return `${label} 升序排序`;
  }

  if (sortState.direction === "asc") {
    return `${label} 降序排序`;
  }

  return `${label} 恢复默认排序`;
}

export function AirWaybillsTable({
  items,
  isLoading,
  emptyMessage = "暂无最新成功抓取数据",
  sortState,
  onSort
}: {
  items: AirWaybillItem[];
  isLoading?: boolean;
  emptyMessage?: string;
  sortState?: AirWaybillSortState;
  onSort?: (key: SortableAirWaybillKey) => void;
}) {
  if (isLoading) {
    return <div className={styles.empty}>正在加载数据...</div>;
  }

  if (!items.length) {
    return <div className={styles.empty}>{emptyMessage}</div>;
  }

  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key}>
                {column.sortable && onSort ? (
                  <button
                    aria-label={getSortLabel(
                      sortState ?? null,
                      column.key as SortableAirWaybillKey,
                      column.label
                    )}
                    className={styles.sortButton}
                    data-active={sortState?.key === column.key}
                    onClick={() => onSort(column.key as SortableAirWaybillKey)}
                    type="button"
                  >
                    <span>{column.label}</span>
                    <span className={styles.sortIcon}>
                      {getSortIcon(
                        sortState ?? null,
                        column.key as SortableAirWaybillKey
                      )}
                    </span>
                  </button>
                ) : (
                  column.label
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((item, index) => (
            <tr key={`${item.number}-${index}`}>
              {columns.map((column) => (
                <td key={column.key}>
                  {column.key === "status" ? (
                    <StatusBadge value={item.status} />
                  ) : column.key === "number" ? (
                    <Link
                      className={styles.numberLink}
                      href={`/air-waybills/${encodeURIComponent(item.number)}`}
                    >
                      {item.number}
                    </Link>
                  ) : (
                    <span>{item[column.key] ?? "-"}</span>
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
