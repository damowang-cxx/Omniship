import type { AirWaybillItem } from "./types";

export function normalizeWaybillNumber(value: string): string {
  return value.replace(/[-\s]/g, "").toLowerCase();
}

export function filterAirWaybillsByNumber(
  items: AirWaybillItem[],
  query: string
): AirWaybillItem[] {
  const rawQuery = query.trim().toLowerCase();
  const normalizedQuery = normalizeWaybillNumber(rawQuery);

  if (!rawQuery) {
    return items;
  }

  return items.filter((item) => {
    const rawNumber = item.number.toLowerCase();
    const normalizedNumber = normalizeWaybillNumber(item.number);

    return (
      rawNumber.includes(rawQuery) ||
      (Boolean(normalizedQuery) && normalizedNumber.includes(normalizedQuery))
    );
  });
}

