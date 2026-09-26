import { EmptyState, MetricCard, SectionTitle } from './UI.jsx';
import { isNumber, metric } from '../lib/format.js';

export default function Tactics({ data }) {
  const teams = Object.values(data.tactics?.teams || {});
  return <div className="tab-content"><SectionTitle eyebrow="THE SHAPE OF THE GAME" title="Team structure, in context.">Geometry of visible players in the calibrated region. Formation estimates describe spatial shape, not confirmed tactical intent.</SectionTitle>
    {!teams.length ? <EmptyState icon="pitch" title="Tactical information is unavailable">More usable tracking and calibration data is needed to describe team shape.</EmptyState> :
      <div className="tactics-grid">{teams.map(team => {
        const shape = team.geometry || {};
        const formation = team.formation || {};
        return <section className="panel tactics-team" key={team.team_id}><div className="card-heading"><h3>Team {team.team_id}</h3><span className="subtle-label">Observed team shape</span></div><div className="formation"><span>Approximate formation</span><strong className={formation.status === 'heuristic_estimate' ? 'text-green' : 'unavailable-formation'}>{formation.label || 'Unknown / insufficient tracking data'}</strong><p>{formation.reason || 'No supported formation estimate is available.'}</p>{isNumber(formation.supported_time_fraction) && <small>Supported time coverage: {metric(formation.supported_time_fraction * 100, '%')}</small>}</div>
          <div className="tactical-metrics">{[['Average width', shape.average_width_m, 'm'], ['Average depth', shape.average_length_m, 'm'], ['Compactness radius', shape.average_compactness_mean_radius_m, 'm']].map(([label, value, unit]) => <MetricCard key={label} label={label} value={metric(value, unit)} />)}</div>
          <dl className="detail-list"><div><dt>Average centroid</dt><dd>{Array.isArray(shape.average_centroid) && shape.average_centroid.length === 2 ? `x ${metric(shape.average_centroid[0], 'm')} · y ${metric(shape.average_centroid[1], 'm')}` : 'Unavailable'}</dd></div><div><dt>Detected passes</dt><dd>{metric(team.passing_network?.total_passes, '', 0)}</dd></div><div><dt>Passing connections</dt><dd>{metric(team.passing_network?.connection_count, '', 0)}</dd></div></dl><p className="muted small-text">Width is lateral spread; depth is longitudinal spread. Compactness is mean distance from the team centroid—lower values describe a tighter visible group.</p></section>;
      })}</div>}
  </div>;
}
