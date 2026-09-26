import { Icon } from './UI.jsx';
import { clock, eventName, isNumber, metric, notesFor } from '../lib/format.js';

export default function CoachReport({ data, filename, createdAt }) {
  const players = data.players || [];
  const distances = players.filter(player => isNumber(player.distance_m)).sort((a, b) => b.distance_m - a.distance_m);
  const speeds = players.filter(player => isNumber(player.max_speed_kmh)).sort((a, b) => b.max_speed_kmh - a.max_speed_kmh);
  const percentages = data.possession?.team_percentages || {};
  const notes = notesFor(data);
  return <article className="coach-report panel">
    <header className="report-header"><div><p className="eyebrow">MATCHVISION / COACH REPORT</p><h2>Match observations</h2><p className="filename">{filename || 'Uploaded match'}</p></div><button className="button secondary no-print" onClick={() => window.print()}><Icon name="file" size={17} /> Print / Save Report</button></header>
    <div className="report-meta"><span>Duration: {clock(data.duration_seconds)}</span>{createdAt && <span>Submitted: {new Date(createdAt).toLocaleString()}</span>}<span>Status: {data.status || 'Unavailable'}</span></div>
    <p className="report-intro">This report summarizes computed observations from the uploaded footage. It does not assess unobserved play or make claims about tactical intent.</p>
    <section><h3>01 / Ball control</h3>{[1, 2].map(id => <p key={id}>Team {id}: {isNumber(percentages[String(id)]) ? `${metric(percentages[String(id)], '%')} of known team-control frames.` : 'No supported possession estimate.'}</p>)}<p className="muted">Unknown frames are excluded. The possession method carries the previous known team assignment forward.</p></section>
    <section><h3>02 / Player movement</h3><p>{metric(data.counts?.players, '', 0)} logical player identities were recorded. Identities are not a verified count of distinct people.</p>{distances.length > 0 ? <p>The highest available distance among displayed players is <strong>{metric(distances[0].distance_m, 'm')}</strong>, recorded for Player {distances[0].player_id}.</p> : <p>Distance measurements are unavailable.</p>}{speeds.length > 0 ? <p>The highest available maximum speed among displayed players is <strong>{metric(speeds[0].max_speed_kmh, 'km/h')}</strong>, recorded for Player {speeds[0].player_id}.</p> : <p>Speed measurements are unavailable.</p>}{data.lists?.players?.omitted > 0 && <p className="notice">This report covers the displayed player subset; {data.lists.players.omitted} more player records are available in full results.</p>}<p className="muted">Speed and distance are partial estimates affected by visibility, identity continuity and pitch calibration.</p></section>
    <section><h3>03 / Events & highlights</h3><p>{data.counts?.events === 0 ? 'No qualifying match events were detected.' : `${metric(data.counts?.events, '', 0)} events were detected across the analysis.`}</p>{Object.entries(data.counts?.events_by_type || {}).map(([type, count]) => <p key={type}>{eventName(type)}: {metric(count, '', 0)}</p>)}<p>{isNumber(data.counts?.highlights) ? `${metric(data.counts.highlights, '', 0)} highlight clips were generated.` : 'Highlight count is unavailable.'}</p><p className="muted">Detected shots are probable events, not confirmed shots or goals.</p></section>
    <section><h3>04 / Team shape</h3>{Object.keys(data.tactics?.teams || {}).length === 0 && <p>Tactical information is unavailable.</p>}{Object.values(data.tactics?.teams || {}).map(team => <div key={team.team_id}><h4>Team {team.team_id}</h4><p>Approximate formation: {team.formation?.label || 'Unknown / insufficient tracking data'}.</p><p>Average width: {metric(team.geometry?.average_width_m, 'm')}. Average depth: {metric(team.geometry?.average_length_m, 'm')}. Mean compactness radius: {metric(team.geometry?.average_compactness_mean_radius_m, 'm')}.</p><p className="muted">{team.formation?.reason}</p></div>)}</section>
    {notes.length > 0 && <section><h3>05 / Analysis notes & limitations</h3><ul>{notes.map(note => <li key={note}>{note}</li>)}</ul></section>}
    <footer className="report-footer">MatchVision · Video-Based Match Analytics for Teams<br /><span>Analysis reference: {data.analysis_id}</span></footer>
  </article>;
}

