import { useState } from 'react';
import { EmptyState, ListLimit, SectionTitle } from './UI.jsx';
import { clock, eventName, isNumber, metric, teamName } from '../lib/format.js';

export default function Events({ data, onSeek }) {
  const [type, setType] = useState('all');
  const events = (data.events || []).filter(event => type === 'all' || event.type === type);
  const types = [...new Set((data.events || []).map(event => event.type))];
  return <div className="tab-content"><SectionTitle eyebrow="MOMENTS THAT MATTER" title="An evidence-led event timeline.">Detected actions, with their estimated confidence. Probable shots are hypotheses, not confirmed outcomes.</SectionTitle>
    <div className="toolbar"><label>Event type <select value={type} onChange={event => setType(event.target.value)}><option value="all">All events</option>{types.map(item => <option key={item} value={item}>{eventName(item)}</option>)}</select></label><span className="muted">{metric(data.counts?.events, '', 0)} events in the full analysis</span></div>
    <ListLimit info={data.lists?.events} label="events (the latest events are shown)" />
    {data.event_detection?.shots?.reason && <p className="notice">{data.event_detection.shots.reason}</p>}
    {!events.length ? <EmptyState icon="time" title={type === 'all' ? 'No qualifying match events were detected in this analysis.' : 'No events match this filter.'}>Events appear only when the available tracking supports them.</EmptyState> :
      <div className="event-list">{events.map((event, index) => <article className="event-row" key={`${event.type}-${event.frame}-${index}`}><button className="event-time" onClick={() => onSeek(event.timestamp)} disabled={!isNumber(event.timestamp)} aria-label={`Open match video at ${clock(event.timestamp)}`}>{clock(event.timestamp)}</button><div className="event-body"><span className={`event-tag ${event.type === 'shot' ? 'shot' : ''}`}>{eventName(event.type)}</span><h3>{event.type === 'pass' ? `Player ${event.player_from ?? 'unavailable'} → Player ${event.player_to ?? 'unavailable'}` : event.player != null ? `Player ${event.player}` : 'Player unavailable'}</h3><p>{teamName(event.team)}{isNumber(event.distance) ? ` · ${metric(event.distance, 'm')} estimated pass distance` : ''}</p></div><div className="confidence"><strong>{isNumber(event.confidence) ? metric(event.confidence * 100, '%', 0) : 'Unavailable'}</strong><span>heuristic confidence</span></div></article>)}</div>}
  </div>;
}
