import { isNumber, metric } from '../lib/format.js';

export default function TeamPitch({ window, coordinates }) {
  const bounds = coordinates?.bounds;
  const nodes = window?.player_positions || [];
  if (!bounds || !nodes.length) return <p className="notice">No supported spatial observations in this window.</p>;
  const length = bounds.x_max - bounds.x_min, width = bounds.y_max - bounds.y_min;
  if (!(length > 0 && width > 0)) return null;
  const h = 300 * length / width;
  const points = nodes.filter(node => Array.isArray(node.position) && node.position.every(isNumber));
  return <figure className="team-pitch"><svg viewBox={`-16 -16 332 ${h + 32}`} role="img" aria-label="Average observed player positions in the calibrated region">
    <rect width="300" height={h} fill="#153c29" stroke="#a1c6ae" />
    {[.25, .5, .75].map(f => <line key={f} x1={300*f} y1="0" x2={300*f} y2={h} stroke="#426e51" strokeDasharray="3 4" />)}
    {points.map(node => {
      const x = 300 * (node.position[1]-bounds.y_min)/width;
      const y = h * (1-(node.position[0]-bounds.x_min)/length);
      return <g key={node.player_id} transform={`translate(${x},${y})`}><title>{`Player ${node.player_id}: ${metric(node.coverage_percentage, '%')} window coverage`}</title><circle r="6" fill="#b5eb83" stroke="#0c2115" /><text y="-9" textAnchor="middle" fill="#e4f2e8" fontSize="9">{node.player_id}</text></g>;
    })}
  </svg><figcaption>Observed spatial shape · calibrated region, not a full-pitch placement. Average positions in the selected window are not a simultaneous lineup. {window.omitted_positions > 0 ? window.omitted_positions + " additional identities are retained in full results." : ""} {window.available ? '' : 'Partial tactical coverage; only available observations are shown.'}</figcaption></figure>;
}

