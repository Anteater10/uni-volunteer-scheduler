export function parseApiDate(value) {
  if (!value) return null;
  if (value instanceof Date) return value;

  if (typeof value === "string") {
    const hasZone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value);
    return new Date(hasZone ? value : `${value}Z`);
  }

  return new Date(value);
}

export function toEpochMs(value) {
  const d = parseApiDate(value);
  if (!d) return Number.NaN;
  return d.getTime();
}

export function formatApiDateTimeLocal(value) {
  const d = parseApiDate(value);
  if (!d || Number.isNaN(d.getTime())) return "Invalid date";
  return d.toLocaleString();
}
