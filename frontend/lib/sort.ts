import type { AirWaybillItem } from "./types";
import { normalizeWaybillNumber } from "./search";

export const SORTABLE_AIR_WAYBILL_KEYS = [
  "number",
  "status",
  "weightKgRaw",
  "receivedRaw",
  "parcelsRaw"
] as const;

export type SortableAirWaybillKey = (typeof SORTABLE_AIR_WAYBILL_KEYS)[number];
export type SortDirection = "asc" | "desc";
export type AirWaybillSortState = {
  key: SortableAirWaybillKey;
  direction: SortDirection;
} | null;

function parseNumber(value?: string | null): number | null {
  if (!value) {
    return null;
  }

  const match = value.replace(/,/g, "").match(/-?\d+(?:\.\d+)?/);
  return match ? Number(match[0]) : null;
}

function compareOptionalText(
  a?: string | null,
  b?: string | null,
  direction: SortDirection = "asc"
) {
  const aText = a?.trim();
  const bText = b?.trim();

  if (!aText && !bText) {
    return 0;
  }
  if (!aText) {
    return 1;
  }
  if (!bText) {
    return -1;
  }

  const result = aText.localeCompare(bText, undefined, {
    numeric: true,
    sensitivity: "base"
  });
  return direction === "asc" ? result : -result;
}

function compareNumericText(
  a?: string | null,
  b?: string | null,
  direction: SortDirection = "asc"
) {
  const aNumber = parseNumber(a);
  const bNumber = parseNumber(b);

  if (aNumber !== null && bNumber !== null) {
    return direction === "asc" ? aNumber - bNumber : bNumber - aNumber;
  }

  return compareOptionalText(a, b, direction);
}

function compareByKey(
  a: AirWaybillItem,
  b: AirWaybillItem,
  key: SortableAirWaybillKey,
  direction: SortDirection
) {
  if (key === "number") {
    return compareOptionalText(
      normalizeWaybillNumber(a.number),
      normalizeWaybillNumber(b.number),
      direction
    );
  }

  if (key === "weightKgRaw" || key === "receivedRaw" || key === "parcelsRaw") {
    return compareNumericText(a[key], b[key], direction);
  }

  return compareOptionalText(a[key], b[key], direction);
}

export function sortAirWaybills(
  items: AirWaybillItem[],
  sortState: AirWaybillSortState
): AirWaybillItem[] {
  if (!sortState) {
    return [...items];
  }

  const decorated = items.map((item, index) => ({ item, index }));

  decorated.sort((a, b) => {
    const result = compareByKey(
      a.item,
      b.item,
      sortState.key,
      sortState.direction
    );

    return result || a.index - b.index;
  });

  return decorated.map(({ item }) => item);
}

export function getNextSortState(
  current: AirWaybillSortState,
  key: SortableAirWaybillKey
): AirWaybillSortState {
  if (!current || current.key !== key) {
    return { key, direction: "asc" };
  }

  if (current.direction === "asc") {
    return { key, direction: "desc" };
  }

  return null;
}
