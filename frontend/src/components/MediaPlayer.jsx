import { useEffect, useRef, useState } from 'react';
import { EmptyState, Icon } from './UI.jsx';
import { isNumber } from '../lib/format.js';

export default function MediaPlayer({ url, downloadUrl, browserAvailable = true, title = 'Match video', reason, seekTime }) {
  const player = useRef(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [url]);
  function seek() {
    const video = player.current;
    if (video && isNumber(seekTime) && video.readyState >= 1) {
      video.currentTime = Math.max(0, Math.min(seekTime, Number.isFinite(video.duration) ? video.duration : seekTime));
    }
  }
  useEffect(seek, [seekTime, url]);
  return <div className="media-player">
    {url && browserAvailable && !failed
      ? <video ref={player} key={url} src={url} controls playsInline preload="metadata" onError={() => setFailed(true)} onLoadedMetadata={seek} aria-label={title} />
      : <EmptyState icon="play" title={failed ? 'Playback is unavailable in this browser' : browserAvailable ? 'No video is available' : 'Download this video to watch it'}>
          {failed ? 'The format may be unsupported, or the media could not be reached. Try the download in a desktop video player.' : reason || 'AVI files may not play in your browser. Use the download below with a compatible desktop player.'}
        </EmptyState>}
    <div className="media-caption"><span><Icon name="play" size={16} /> {title}</span>{(downloadUrl || url) && <a className="text-link" href={downloadUrl || url} target="_blank" rel="noreferrer">Open / download video <Icon name="arrow" size={15} /></a>}</div>
  </div>;
}
