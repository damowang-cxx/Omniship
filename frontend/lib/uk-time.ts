const UK_TIME_ZONE = "Europe/London";

const displayFormatter = new Intl.DateTimeFormat("en-GB", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
  timeZone: UK_TIME_ZONE,
  timeZoneName: "short"
});

const inputFormatter = new Intl.DateTimeFormat("en-GB", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
  timeZone: UK_TIME_ZONE
});

const clockFormatter = new Intl.DateTimeFormat("en-GB", {
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
  timeZone: UK_TIME_ZONE,
  timeZoneName: "short"
});

function ukParts(date: Date) {
  return Object.fromEntries(
    inputFormatter.formatToParts(date)
      .filter((part) => part.type !== "literal")
      .map((part) => [part.type, part.value])
  ) as Record<string, string>;
}

export function formatUkDateTime(value?: string | null, empty = "—") {
  if (!value) return empty;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : displayFormatter.format(date);
}

export function formatUkClock(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : clockFormatter.format(date);
}

export function toUkDateTimeLocalValue(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const parts = ukParts(date);
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}

export function fromUkDateTimeLocalValue(value: string) {
  if (!value) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!match) throw new Error("请输入有效的英国当地时间");
  const [, year, month, day, hour, minute] = match;
  const wallTimeAsUtc = Date.UTC(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute));
  // UK civil time is GMT or BST. The earlier instant wins during the repeated autumn hour.
  const candidates = [wallTimeAsUtc, wallTimeAsUtc - 60 * 60 * 1000]
    .filter((instant) => {
      const parts = ukParts(new Date(instant));
      return parts.year === year && parts.month === month && parts.day === day
        && parts.hour === hour && parts.minute === minute;
    });
  if (!candidates.length) throw new Error("该时间不在英国时区内（请检查夏令时切换日）");
  return new Date(Math.min(...candidates)).toISOString();
}
