import { Icon, MetricCard } from './UI.jsx';
import { clock, eventName, isNumber, metric, notesFor, possessionTime, teamName } from '../lib/format.js';

export default function CoachReport({ data, filename, createdAt }) {
  const players = data.players || [];
  const distances = players.filter(player => isNumber(player.distance_m)).sort((a, b) => b.distance_m - a.distance_m);
  const speeds = players.filter(player => isNumber(player.max_speed_kmh)).sort((a, b) => b.max_speed_kmh - a.max_speed_kmh);
  const percentages = data.possession?.team_percentages || {};
  const teams = Object.values(data.tactics?.teams || {});
  const notes = notesFor(data);
  const observations = [1, 2].filter(id => isNumber(percentages[String(id)])).map(id =>
    'Team ' + id + ' controlled ' + metric(percentages[String(id)], '%') + ' of known team-possession frames.');
  if (distances[0]) observations.push('Player ' + distances[0].player_id + ' recorded the highest displayed distance: ' + metric(distances[0].distance_m, 'm') + '.');
  if (speeds[0]) observations.push('Player ' + speeds[0].player_id + ' recorded the highest displayed speed: ' + metric(speeds[0].max_speed_kmh, 'km/h') + '.');
  if (data.counts?.events_by_type?.shot === 0) observations.push('No qualifying shot events were detected.');
  if (data.lists?.players?.omitted > 0) notes.push('Player rankings use the displayed summary subset, not every identity in full results.');
  const snapshot = [
    ['Duration', clock(data.duration_seconds)], ['Team 1 possession', metric(percentages['1'], '%')],
    ['Team 2 possession', metric(percentages['2'], '%')], ['Players tracked', metric(data.counts?.players, '', 0)],
    ['Events detected', metric(data.counts?.events, '', 0)], ['Highlights', metric(data.counts?.highlights, '', 0)],
  ];
  return <article className="coach-report panel">
    <header className="report-header"><div><p className="eyebrow">MATCHVISION / COACH REPORT</p><h2>Match observations</h2><p className="filename">{filename || 'Uploaded match'}</p></div><button className="button secondary no-print" onClick={() => window.print()}><Icon name="file" size={17} /> Print / Save Report</button></header>
    <div className="report-meta">{createdAt && <span>Submitted: {new Date(createdAt).toLocaleString()}</span>}<span>Recorded observations · {data.status || 'Unavailable'}</span></div>
    <section><h3>Match snapshot</h3><div className="report-snapshot">{snapshot.map(([label, value]) => <MetricCard key={label} label={label} value={value} />)}</div></section>
    <section><h3>Key observations</h3><ul className="observation-cards">{observations.map(text => <li key={text}>{text}</li>)}</ul>{!observations.length && <p>No supported observations are available.</p>}</section>
    <section><h3>Player performance</h3><p className="small-text muted">Top five displayed identities by measured distance.</p>
      {distances.length ? <div className="table-wrap"><table className="report-table"><thead><tr><th>Player</th><th>Team</th><th>Distance</th><th>Max speed</th><th>Possession</th><th>Passes sent</th></tr></thead><tbody>{distances.slice(0, 5).map(player => <tr key={player.player_id}><td>#{player.player_id}</td><td>{teamName(player.team_id)}</td><td>{metric(player.distance_m, 'm')}</td><td>{metric(player.max_speed_kmh, 'km/h')}</td><td>{possessionTime(player.possession_time_seconds)}</td><td>{metric(player.successful_passes, '', 0)}</td></tr>)}</tbody></table></div> : <p>Player distance rankings are unavailable.</p>}
    </section>
    <section><h3>Team shape</h3><div className="report-team-grid">{teams.map(team => {
      const shape = team.temporal?.summary || team.geometry || {};
      const formation = shape.most_common_supported_formation || team.formation || {};
      return <div className="report-team-card" key={team.team_id}><h4>Team {team.team_id}</h4><dl>
        <div><dt>Observed formation</dt><dd>{formation.label || 'Unknown / insufficient tracking data'}</dd><small>Most frequent supported shape; not tactical intent.</small></div>
        <div><dt>Average width</dt><dd>{metric(shape.average_width_m, 'm')}</dd><small>Side-to-side spread.</small></div>
        <div><dt>Average depth</dt><dd>{metric(shape.average_length_m, 'm')}</dd><small>Front-to-back spread.</small></div>
        <div><dt>Compactness</dt><dd>{metric(shape.average_compactness_mean_radius_m, 'm')}</dd><small>Mean distance to the visible team centre.</small></div>
        <div><dt>Tactical coverage</dt><dd>{metric(shape.coverage_percentage, '%')}</dd><small>Match time with sufficient observations.</small></div>
      </dl></div>;
    })}</div>{!teams.length && <p>Team shape is unavailable.</p>}</section>
    <section><h3>Events & highlights</h3>
      {data.availability?.events === false ? <p>Event detection was unavailable because of insufficient evidence.</p> : data.counts?.events === 0 ? <p>No qualifying events were detected in this analysis.</p> : <div className="report-event-grid">{Object.entries(data.counts?.events_by_type || {}).map(([type, count]) => <MetricCard key={type} label={eventName(type)} value={metric(count, '', 0)} />)}</div>}
      {(data.events || []).length > 0 && <ol className="report-timeline">{data.events.slice(-5).map((event, index) => <li key={index}><strong>{clock(event.timestamp)}</strong> {eventName(event.type)} · {teamName(event.team)}</li>)}</ol>}
      <p>{isNumber(data.counts?.highlights) ? metric(data.counts.highlights, '', 0) + ' highlight clips generated.' : 'Highlight assessment or export is unavailable.'}</p>
    </section>
    <section className="report-notes"><h3>Analysis notes</h3><p>All values are estimates from the visible calibrated region. Stable player possession excludes unknown/interpolated ball frames. Zero means evaluated with no detected contribution; unavailable means insufficient evidence.</p><ul>{notes.map(note => <li key={note}>{note}</li>)}</ul></section>
    <footer className="report-footer">MatchVision · Video-Based Match Analytics for Teams<br /><span>Analysis reference: {data.analysis_id}</span></footer>
  </article>;
}
