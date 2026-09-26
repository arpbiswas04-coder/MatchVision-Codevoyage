export const isNumber = value => typeof value === 'number' && Number.isFinite(value);
export function metric(value, unit = '', digits = 1) {
  return isNumber(value) ? `${value.toLocaleString(undefined, { maximumFractionDigits: digits })}${unit ? ' ' + unit : ''}` : 'Unavailable';
}
export function clock(value) {
  if (!isNumber(value) || value < 0) return 'Unavailable';
  const total = Math.floor(value);
  const seconds = String(total % 60).padStart(2, '0');
  const minutes = Math.floor(total / 60);
  return minutes >= 60 ? `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}:${seconds}` : `${minutes}:${seconds}`;
}
export function teamName(id) { return id === 1 || id === 2 ? `Team ${id}` : 'Team unassigned'; }
export function eventName(type) {
  return type === 'shot' ? 'Probable shot' : type === 'pass' ? 'Detected pass' : String(type || 'Event').replaceAll('_', ' ');
}
export function notesFor(data) {
  const values = [
    ...(data.warnings || []), ...(data.tracking?.limitations || []),
    ...(data.tactics?.limitations || []), ...(data.highlight_generation?.warnings || []),
    ...(Array.isArray(data.event_detection?.passes?.limitations) ? data.event_detection.passes.limitations : []),
    ...(Array.isArray(data.event_detection?.shots?.limitations) ? data.event_detection.shots.limitations : []),
    ...(Array.isArray(data.event_detection?.shots?.reasons) ? data.event_detection.shots.reasons : []),
    data.event_detection?.shots?.reason,
  ];
  return [...new Set(values.filter(item => typeof item === 'string' && item.trim()))];
}
export function rememberMatch(record) {
  try { sessionStorage.setItem('matchvision:last', JSON.stringify(record)); } catch { /* Storage is optional. */ }
}
export function lastMatch() {
  try { return JSON.parse(sessionStorage.getItem('matchvision:last') || 'null'); } catch { return null; }
}

export function possessionTime(value) {
  if (!isNumber(value)) return 'Unavailable';
  return value < 60 ? metric(value, 's', 2) : clock(value);
}
export function passPartners(total, partners, direction) {
  if (!isNumber(total)) return 'Unavailable';
  if (total === 0) return '0';
  const names = (partners || []).map(item => '#' + item.player_id + ' (' + item.count + ')').join(', ');
  return String(total) + (names ? ' ' + direction + ' ' + names : '');
}

