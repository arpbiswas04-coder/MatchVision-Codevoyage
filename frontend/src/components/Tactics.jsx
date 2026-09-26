import { useState } from 'react';
import { EmptyState, MetricCard, SectionTitle } from './UI.jsx';
import { clock, isNumber, metric } from '../lib/format.js';

function TeamShape({ team }) {
  const [selected, setSelected] = useState(0);
  const temporal = team.temporal;
  const shape = temporal?.summary || team.geometry || {};
  const formation = shape.most_common_supported_formation || team.formation || {};
  const windows = temporal?.windows || [];
  const window = windows[selected] || windows[0];
  const period = value => value ? clock(value.start_seconds) + ' – ' + clock(value.end_seconds) : 'Unavailable';
  return <section className="panel tactics-team">
    <div className="card-heading"><h3>Team {team.team_id}</h3><span className="subtle-label">Visible spatial shape</span></div>
    <div className="formation"><span>Most frequently observed supported shape</span>
      <strong className={formation.status === 'heuristic_estimate' ? 'text-green' : 'unavailable-formation'}>{formation.label || 'Unknown / insufficient tracking data'}</strong>
      <p>{formation.reason || 'No supported formation estimate is available.'}</p>
      <small>Match-time support: {metric(formation.support_percentage ?? (isNumber(formation.supported_time_fraction) ? formation.supported_time_fraction * 100 : null), '%')} — a coverage measure, not a probability.</small>
    </div>
    <div className="tactical-metrics">
      <MetricCard label="Average width" value={metric(shape.average_width_m, 'm')} hint="How spread out the visible team is from side to side." />
      <MetricCard label="Average depth" value={metric(shape.average_length_m, 'm')} hint="How stretched the visible team is from front to back." />
      <MetricCard label="Compactness radius" value={metric(shape.average_compactness_mean_radius_m, 'm')} hint="How tightly grouped the visible players are; lower is tighter." />
      <MetricCard label="Tactical coverage" value={metric(shape.coverage_percentage, '%')} hint="Match time with enough usable visible-player observations." />
    </div>
    <dl className="detail-list">
      <div><dt>Width range</dt><dd>{metric(shape.minimum_width_m, 'm')} – {metric(shape.maximum_width_m, 'm')}</dd></div>
      <div><dt>Centroid — average team position</dt><dd>{Array.isArray(shape.average_centroid) ? shape.average_centroid.map(value => metric(value, 'm')).join(' / ') : 'Unavailable'}</dd></div>
      <div><dt>Widest period</dt><dd>{period(shape.widest_period)}</dd></div>
      <div><dt>Narrowest period</dt><dd>{period(shape.narrowest_period)}</dd></div>
      <div><dt>Most compact period</dt><dd>{period(shape.most_compact_period)}</dd></div>
      <div><dt>Detected successful passes</dt><dd>{metric(team.passing_network?.total_passes, '', 0)}</dd></div>
    </dl>
    {windows.length > 0 && <div className="tactical-window">
      <label>Explore a time window<select value={selected} onChange={event => setSelected(Number(event.target.value))}>{windows.map((item, index) => <option key={index} value={index}>{period(item)}</option>)}</select></label>
      {temporal.omitted_windows > 0 && <p className="small-text muted">{windows.length} representative windows shown; full results retain all {temporal.total_windows}.</p>}
      <dl className="detail-list"><div><dt>Average visible players</dt><dd>{metric(window.average_visible_players)}</dd></div><div><dt>Coverage</dt><dd>{metric(window.coverage_percentage, '%')}</dd></div><div><dt>Width / depth</dt><dd>{metric(window.average_width_m, 'm')} / {metric(window.average_length_m, 'm')}</dd></div><div><dt>Compactness</dt><dd>{metric(window.average_compactness_mean_radius_m, 'm')}</dd></div><div><dt>Observed shape</dt><dd>{window.formation?.label || 'Unavailable'}</dd></div></dl>
      {!window.available && <p className="notice">Not enough visible-player coverage for geometry in this period.</p>}
    </div>}
  </section>;
}
export default function Tactics({ data }) {
  const teams = Object.values(data.tactics?.teams || {});
  return <div className="tab-content"><SectionTitle eyebrow="THE SHAPE OF THE GAME" title="Team structure, over time.">Coverage-qualified measurements of visible players. Spatial shape is not confirmed coaching intent.</SectionTitle>
    {teams.length ? <div className="tactics-grid">{teams.map(team => <TeamShape team={team} key={team.team_id} />)}</div> : <EmptyState title="Tactical information is unavailable">Usable positions and sufficient player coverage are needed.</EmptyState>}
  </div>;
}

