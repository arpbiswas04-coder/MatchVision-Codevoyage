import { useMemo, useState } from 'react';
import { EmptyState, ListLimit, SectionTitle } from './UI.jsx';
import { clock, isNumber, metric, teamName, possessionTime, passPartners } from '../lib/format.js';

export default function Players({ data }) {
  const [sort, setSort] = useState({ key: 'distance_m', descending: true });
  const [team, setTeam] = useState('all');
  const players = useMemo(() => [...(data.players || [])]
    .filter(player => team === 'all' || String(player.team_id ?? 'unknown') === team)
    .sort((a, b) => {
      const left = a[sort.key], right = b[sort.key];
      if (!isNumber(left)) return isNumber(right) ? 1 : 0;
      if (!isNumber(right)) return -1;
      return (left - right) * (sort.descending ? -1 : 1);
    }), [data.players, sort, team]);
  function sortBy(key) { setSort(current => ({ key, descending: current.key === key ? !current.descending : true })); }
  const sortable = (key, label) => <th scope="col" aria-sort={sort.key === key ? (sort.descending ? 'descending' : 'ascending') : 'none'}><button onClick={() => sortBy(key)}>{label} {sort.key === key ? (sort.descending ? '↓' : '↑') : '↕'}</button></th>;
  return <div className="tab-content"><SectionTitle eyebrow="INDIVIDUAL CONTRIBUTIONS" title="Movement, player by player.">Measured observations grouped by logical player identity. Missing values remain unavailable.</SectionTitle>
    <div className="toolbar"><label>Filter team <select value={team} onChange={event => setTeam(event.target.value)}><option value="all">All players</option><option value="1">Team 1</option><option value="2">Team 2</option><option value="unknown">Unassigned</option></select></label><span className="muted">{players.length} displayed identities</span></div>
    <ListLimit info={data.lists?.players} label="players" />
    {!players.length ? <EmptyState icon="players" title="No player statistics to show">Try a different team filter, or review the analysis notes for tracking coverage.</EmptyState> :
      <div className="table-wrap panel"><table><caption className="sr-only">Player movement and possession estimates. Select a column heading to sort.</caption><thead><tr>{sortable('player_id', 'Player')}<th scope="col">Team</th>{sortable('distance_m', 'Distance')}{sortable('average_speed_kmh', 'Avg. speed')}{sortable('max_speed_kmh', 'Max. speed')}<th scope="col">Time tracked</th><th scope="col">Possession</th><th scope="col">Passes sent</th><th scope="col">Received</th></tr></thead><tbody>{players.map(player => <tr key={player.player_id}><th scope="row"><span className="player-number">{player.player_id}</span></th><td><span className={`team-label team-${player.team_id}`}>{teamName(player.team_id)}</span></td><td>{metric(player.distance_m, 'm')}</td><td>{metric(player.average_speed_kmh, 'km/h')}</td><td>{metric(player.max_speed_kmh, 'km/h')}</td><td>{clock(player.tracked_time_seconds)}</td><td>{possessionTime(player.possession_time_seconds)}{isNumber(player.possession_percentage_of_known_possession) && <small className="cell-note">{metric(player.possession_percentage_of_known_possession, '%')} of known stable possession</small>}</td><td className="pass-cell">{passPartners(player.successful_passes, player.passes_sent_to, "→")}</td><td className="pass-cell">{passPartners(player.passes_received, player.passes_received_from, "←")}</td></tr>)}</tbody></table></div>}
    <p className="muted small-text">Track identities can still fragment or switch. Distance and speed describe available calibrated observations, not unobserved movement.</p>
  </div>;
}

