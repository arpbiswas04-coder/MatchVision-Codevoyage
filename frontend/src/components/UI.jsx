import { Link } from 'react-router-dom';

const paths = {
  arrow: 'M5 12h14m-6-6 6 6-6 6',
  upload: 'M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5',
  play: 'm9 5 11 7-11 7V5Z',
  players: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m15-12a4 4 0 0 1 0 8M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z',
  pitch: 'M3 4h18v16H3V4Zm9 0v16M3 8h4v8H3m18-8h-4v8h4',
  chart: 'M4 20h17M7 16v-5m5 5V5m5 11V9',
  activity: 'M2 12h5l3-8 4 16 3-8h5',
  target: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 5a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z',
  check: 'm5 12 4 4L19 6',
  file: 'M14 2H5v20h14V7l-5-5Zm0 0v6h5M8 13h8m-8 4h6',
  close: 'm6 6 12 12M6 18 18 6',
  time: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 4v5l3 2',
};
export function Icon({ name, size = 20 }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name] || paths.chart} /></svg>;
}
export function Brand() {
  return <Link to="/" className="brand" aria-label="MatchVision home"><span className="brand-mark"><Icon name="pitch" size={24} /></span>Match<span>Vision</span></Link>;
}
export function SectionTitle({ eyebrow, title, children }) {
  return <div className="section-title">{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h2>{title}</h2>{children && <p className="muted">{children}</p>}</div>;
}
export function EmptyState({ title, children, icon = 'pitch', action }) {
  return <div className="empty-state"><span className="empty-icon"><Icon name={icon} size={28} /></span><h3>{title}</h3>{children && <p>{children}</p>}{action}</div>;
}
export function ErrorState({ error, retry, children }) {
  return <div className="error-state" role="alert"><h3>We couldn’t complete that request</h3><p>{error?.message || String(error || 'Please try again.')}</p><div className="button-row">{retry && <button className="button secondary" onClick={retry}>Try again</button>}{children}</div></div>;
}
export function Loading({ children = 'Loading match insights…' }) {
  return <div className="loading-state" role="status"><span className="spinner" /><p>{children}</p></div>;
}
export function MetricCard({ label, value, hint, icon = 'chart' }) {
  return <div className="metric-card"><div className="metric-top"><span>{label}</span><Icon name={icon} /></div><strong>{value}</strong>{hint && <small>{hint}</small>}</div>;
}
export function ListLimit({ info, label }) {
  return info?.omitted > 0 ? <p className="notice">Showing a limited selection of {label}; {info.omitted.toLocaleString()} additional records are available in the full analysis.</p> : null;
}
