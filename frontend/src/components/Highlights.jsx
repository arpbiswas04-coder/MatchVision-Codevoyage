import { useState } from 'react';
import { mediaUrl } from '../api/matchvision.js';
import { EmptyState, Icon, ListLimit, SectionTitle } from './UI.jsx';
import MediaPlayer from './MediaPlayer.jsx';
import { clock, eventName, isNumber, metric } from '../lib/format.js';

export default function Highlights({ data, analysisId }) {
  const [index, setIndex] = useState(0);
  const clips = data.highlights || [];
  const clip = clips[index] || clips[0];
  const url = mediaUrl(clip?.video_path, analysisId);
  const status = data.highlight_generation?.status;
  const noClipsTitle = status === 'no_eligible_events'
    ? 'No eligible highlight events were detected for this match.'
    : status === 'failed' ? 'Highlight generation was unavailable.'
    : status === 'disabled' ? 'Highlights were disabled for this analysis.'
    : 'No highlight clips are available.';
  return <div className="tab-content"><SectionTitle eyebrow="BACK TO THE ACTION" title="The moments worth revisiting.">Clips from supported high-confidence events. Ordinary passes are not turned into highlights.</SectionTitle>
    <ListLimit info={data.lists?.highlights} label="highlights" />
    {(data.highlight_generation?.warnings || []).map((warning, i) => <p className="notice" key={i}>{warning}</p>)}
    {!clips.length ? <EmptyState icon="play" title={noClipsTitle}>{status === 'failed' ? 'The rest of the match analysis is still available. Check the backend log for export details.' : 'Clips are created only when qualifying events and usable source footage are available.'}</EmptyState> :
      <div className="highlight-layout"><section className="panel highlight-view"><MediaPlayer key={clip.asset_id || clip.video_path} url={url} downloadUrl={url} browserAvailable={clip.backend === 'ffmpeg' || /\.mp4(?:\?|$)/i.test(url || '')} title={`${eventName(clip.event_type)} · ${clock(clip.timestamp)}`} /><div className="highlight-description"><span>Source: {clip.source === 'annotated' ? 'Annotated match' : clip.source === 'original' ? 'Original upload' : 'Unavailable'}</span><span>{clock(clip.start)} – {clock(clip.end)}</span>{clip.audio_mode?.includes('not_available') && <span>Silent video export</span>}</div></section><div className="clip-list" aria-label="Choose a highlight">{clips.map((item, i) => <button className={`clip-card ${i === index ? 'selected' : ''}`} key={item.asset_id || i} onClick={() => setIndex(i)} aria-pressed={i === index}><span className="clip-icon"><Icon name="play" /></span><span><strong>{eventName(item.event_type)}</strong><small>{clock(item.timestamp)} · {isNumber(item.confidence) ? metric(item.confidence * 100, '%', 0) + ' confidence' : 'Confidence unavailable'}</small></span></button>)}</div></div>}
  </div>;
}
