export function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function relativeTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const minutes = Math.round((Date.now() - date.getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  return days < 30 ? `${days} d ago` : formatDateTime(value);
}

/** Incident times are compared across tools, so they are always shown in UTC. */
export function utcTime(value: string, withDate = false) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const time = date.toISOString().slice(11, 16);
  return withDate ? `${date.toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "UTC" })} ${time}` : time;
}

export function formatDuration(minutes: number) {
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return `${hours} h${minutes % 60 ? ` ${minutes % 60} min` : ""}`;
}

export const shortSha = (sha: string) => sha.slice(0, 7);

export function formatMs(ms: number) {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${ms} ms`;
}
