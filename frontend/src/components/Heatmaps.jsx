import { useEffect, useState } from 'react';
import { mediaUrl } from '../api/matchvision.js';
import { EmptyState, ListLimit, SectionTitle } from './UI.jsx';
import { teamName } from '../lib/format.js';

export default function Heatmaps({ data, analysisId }) {
  const [group, setGroup] = useState('team');
  const [selected, setSelected] = useState('');
  const [failed, setFailed] = useState(false);
  const maps = (data.heatmaps || []).filter(item => group === 'ball' ? item.name === 'ball.png' : item.name?.startsWith(group + '_'));
  const current = maps.find(item => item.name === selected) || maps[0];
  const playerId = current?.name?.match(/^player_(\d+)\.png$/)?.[1];
  const player = (data.players || []).find(item => String(item.player_id) === playerId);
  const url = mediaUrl(current?.url, analysisId);
  useEffect(() => setFailed(false), [url]);
  function label(item) {
    if (item.name === 'ball.png') return 'Ball locations';
    return item.name.replace('.png', '').replace('player_', 'Player ').replace('team_', 'Team ');
  }
  return <div className="tab-content"><SectionTitle eyebrow="SPACE & MOVEMENT" title="Where the match happened.">Occupancy in the calibrated pitch region, based on observed positions.</SectionTitle><div className="toolbar"><div className="segmented" aria-label="Heatmap category">{[['team', 'Teams'], ['player', 'Players'], ['ball', 'Ball']].map(([key, name]) => <button key={key} aria-pressed={group === key} className={group === key ? 'active' : ''} onClick={() => { setGroup(key); setSelected(''); }}>{name}</button>)}</div>{maps.length > 0 && <label>Select heatmap <select value={current?.name || ''} onChange={event => setSelected(event.target.value)}>{maps.map(item => <option key={item.name} value={item.name}>{label(item)}</option>)}</select></label>}</div><ListLimit info={data.lists?.heatmaps} label="heatmaps" />
    {!current ? <EmptyState icon="target" title="No heatmap is available for this category">A heatmap is generated only when usable transformed positions are available.</EmptyState> :
      <section className="panel heatmap-panel"><div className="card-heading"><h3>{label(current)}</h3>{playerId && <span className="team-label">{teamName(player?.team_id)}</span>}</div>{failed || !url ? <EmptyState title="This heatmap could not be loaded">The file may no longer be available. Check the backend connection.</EmptyState> : <img key={url} src={url} alt={`${label(current)} observed movement heatmap`} loading="lazy" decoding="async" onError={() => setFailed(true)} />}{url && <a className="text-link" href={url} target="_blank" rel="noreferrer">Open full-size heatmap</a>}</section>}
    <p className="muted small-text">Colour scales are independent. The density map shows only the calibrated region: lateral y runs right; longitudinal x runs up. The separate full-pitch outline is an unregistered reference, with no data placed on it.</p>
  </div>;
}

