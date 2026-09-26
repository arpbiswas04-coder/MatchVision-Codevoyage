import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { getAnalysisStatus, getAnalysisSummary, mediaUrl } from '../api/matchvision.js';
import { ErrorState, Icon, Loading } from '../components/UI.jsx';
import Overview from '../components/Overview.jsx';
import MediaPlayer from '../components/MediaPlayer.jsx';
import Players from '../components/Players.jsx';
import Heatmaps from '../components/Heatmaps.jsx';
import Events from '../components/Events.jsx';
import Tactics from '../components/Tactics.jsx';
import Highlights from '../components/Highlights.jsx';
import CoachReport from '../components/CoachReport.jsx';
import { clock, rememberMatch } from '../lib/format.js';

const tabs = [['overview', 'Overview'], ['video', 'Match video'], ['players', 'Players'], ['heatmaps', 'Heatmaps'], ['events', 'Events'], ['tactics', 'Tactics'], ['highlights', 'Highlights'], ['report', 'Coach report']];

export default function Analysis() {
  const { analysisId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const [attempt, setAttempt] = useState(0);
  const [tab, setTab] = useState('overview');
  const [seekTime, setSeekTime] = useState(null);
  useEffect(() => {
    const controller = new AbortController();
    setData(null); setError(null); setTab('overview'); setSeekTime(null);
    async function load() {
      try {
        const status = await getAnalysisStatus(analysisId, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setJob(status);
        if (status.status !== 'completed') { navigate(`/processing/${analysisId}`, { replace: true }); return; }
        rememberMatch({ analysis_id: analysisId, filename: status.filename });
        const summary = await getAnalysisSummary(analysisId, { signal: controller.signal });
        if (!controller.signal.aborted) setData(summary);
      } catch (err) {
        if (err.name === 'AbortError') return;
        if (err.status === 409) navigate(`/processing/${analysisId}`, { replace: true });
        else setError(err);
      }
    }
    load();
    return () => controller.abort();
  }, [analysisId, attempt, navigate]);
  function seek(time) { setSeekTime(time); setTab('video'); }
  if (error) return <main className="container page"><ErrorState error={error} retry={() => setAttempt(value => value + 1)}><Link to="/upload" className="button secondary">Upload a match</Link></ErrorState></main>;
  if (!data) return <main className="container page"><Loading>Opening your match analysis…</Loading></main>;
  const video = data.annotated_video || {};
  return <main className="container page dashboard">
    <header className="dashboard-header no-print"><div><p className="eyebrow">MATCHVISION WORKSPACE</p><h1>Match Analysis</h1><div className="match-meta"><span className="filename">{job?.filename || 'Uploaded match'}</span><span>{clock(data.duration_seconds)}</span><span className="status-pill"><Icon name="check" size={14} />Completed</span></div></div><div className="button-row"><button className="button secondary" onClick={() => setTab('report')}><Icon name="file" size={16} /> Coach report</button><Link to="/upload" className="button">New analysis</Link></div></header>
    <nav className="dashboard-tabs no-print" aria-label="Analysis sections">{tabs.map(([key, label]) => <button key={key} className={tab === key ? 'active' : ''} aria-current={tab === key ? 'page' : undefined} onClick={() => setTab(key)}>{label}</button>)}</nav>
    <div className="dashboard-content">
      {tab === 'overview' && <Overview data={data} onReport={() => setTab('report')} />}
      {tab === 'video' && <div className="tab-content"><div className="section-title"><p className="eyebrow">REVIEW THE MATCH</p><h2>The footage, with a new perspective.</h2><p className="muted">Player identities, ball tracking and available movement annotations.</p></div><section className="panel match-video-panel"><MediaPlayer url={mediaUrl(video.url, analysisId)} downloadUrl={mediaUrl(video.download_url, analysisId)} browserAvailable={video.browser_available === true} title="Annotated match" reason={video.conversion?.reason} seekTime={seekTime} /></section></div>}
      {tab === 'players' && <Players data={data} />}
      {tab === 'heatmaps' && <Heatmaps data={data} analysisId={analysisId} />}
      {tab === 'events' && <Events data={data} onSeek={seek} />}
      {tab === 'tactics' && <Tactics data={data} />}
      {tab === 'highlights' && <Highlights data={data} analysisId={analysisId} />}
      {tab === 'report' && <CoachReport data={data} filename={job?.filename} createdAt={job?.created_at} />}
    </div>
    <div className="dashboard-footnote no-print"><span>Estimates describe the footage available, not every action on the pitch.</span>{mediaUrl(data.full_results_url, analysisId) && <a href={mediaUrl(data.full_results_url, analysisId)} target="_blank" rel="noreferrer">Open full analysis JSON (large file)</a>}</div>
  </main>;
}
