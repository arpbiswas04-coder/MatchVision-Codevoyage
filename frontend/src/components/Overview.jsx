import { MetricCard, SectionTitle } from './UI.jsx';
import { isNumber, metric, notesFor } from '../lib/format.js';

export default function Overview({ data, onReport }) {
  const teams = data.teams || [];
  const distances = teams.map(team => team.total_distance_m).filter(isNumber);
  const percentages = data.possession?.team_percentages || {};
  const cards = [
    ...[1, 2].filter(id => isNumber(percentages[String(id)])).map(id => [`Team ${id} possession`, metric(percentages[String(id)], '%'), 'Of known team-control frames', 'target']),
    ...(isNumber(data.counts?.players) ? [['Players tracked', metric(data.counts.players, '', 0), 'Logical identities, not a verified roster', 'players']] : []),
    ...(distances.length ? [['Distance analyzed', metric(distances.reduce((a, b) => a + b, 0), 'm'), 'Sum of available team distance estimates', 'activity']] : []),
    ...(isNumber(data.counts?.events) ? [['Events detected', metric(data.counts.events, '', 0), 'Supported events across this analysis', 'time']] : []),
    ...(isNumber(data.counts?.highlights) ? [['Highlights generated', metric(data.counts.highlights, '', 0), 'Clips from eligible actions', 'play']] : []),
  ];
  const notes = notesFor(data);
  return <div className="tab-content">
    <SectionTitle eyebrow="THE MATCH AT A GLANCE" title="The bigger picture.">A view of the measurements available from your footage.</SectionTitle>
    <div className="metrics-grid">{cards.map(([label, value, hint, icon]) => <MetricCard key={label} {...{ label, value, hint, icon }} />)}</div>
    {!cards.length && <p className="notice">Summary metrics are not available for this analysis.</p>}
    <div className="overview-columns"><section className="panel possession-panel"><div className="card-heading"><h3>Ball control</h3><span className="subtle-label">Estimated possession</span></div>
      {[1, 2].map(id => <div className="possession-row" key={id}><div><span><i className={`legend ${id === 1 ? 'green' : 'blue'}`} />Team {id}</span><strong>{metric(percentages[String(id)], '%')}</strong></div>{isNumber(percentages[String(id)]) ? <div className="possession-track"><span className={id === 1 ? 'team-one' : 'team-two'} style={{ width: `${Math.max(0, Math.min(100, percentages[String(id)]))}%` }} /></div> : <p className="muted small-text">No supported possession estimate.</p>}</div>)}
      <p className="muted small-text">Team possession carries the previous known assignment forward. Unknown frames are excluded from the percentage denominator.</p>
    </section><section className="panel report-invite"><span className="eyebrow">TAKE IT TO THE TEAM</span><h3>A report built from<br />what was measured.</h3><p>A concise, printable view of possession, movement and supported tactical insights.</p><button className="button secondary" onClick={onReport}>Open coach report</button></section></div>
    {notes.length > 0 && <details className="panel analysis-notes"><summary>Analysis notes <span>{notes.length} notes & limitations</span></summary><ul>{notes.map(note => <li key={note}>{note}</li>)}</ul></details>}
  </div>;
}
