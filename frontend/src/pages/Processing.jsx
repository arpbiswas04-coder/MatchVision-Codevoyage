import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { getAnalysisStatus } from '../api/matchvision.js';
import { EmptyState, ErrorState, Icon, Loading } from '../components/UI.jsx';
import { isNumber, rememberMatch } from '../lib/format.js';

export default function Processing() {
  const { analysisId } = useParams();
  const navigate = useNavigate();
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let timer;
    setError(null); setJob(null);
    async function poll() {
      try {
        const result = await getAnalysisStatus(analysisId, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setJob(result);
        rememberMatch({ analysis_id: analysisId, filename: result.filename });
        if (result.status === 'completed') { navigate(`/analysis/${analysisId}`, { replace: true }); return; }
        if (result.status === 'failed') return;
        timer = window.setTimeout(poll, 3000);
      } catch (err) {
        if (err.name !== 'AbortError') setError(err);
      }
    }
    poll();
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [analysisId, attempt, navigate]);
  const progress = isNumber(job?.progress) ? Math.max(0, Math.min(100, job.progress)) : null;
  return <main className="container page processing-page"><div className="page-heading centered"><p className="eyebrow">BUILDING YOUR MATCH PICTURE</p><h1>The game is in motion.</h1><p>Your footage is being turned into a connected analysis.</p></div>
    <section className="panel processing-panel">
      {error ? <ErrorState error={error} retry={() => setAttempt(value => value + 1)}><Link to="/upload" className="button secondary">Back to upload</Link></ErrorState> :
       !job ? <Loading>Connecting to your analysis…</Loading> :
       job.status === 'failed' ? <EmptyState title="This analysis couldn’t be completed" icon="file" action={<Link to="/upload" className="button">Return to upload</Link>}>{job.error || 'The analysis stopped before it could finish. Check the backend log for details.'}</EmptyState> :
       <><div className="processing-top"><span className="processing-symbol"><Icon name="pitch" size={34} /></span><span className="status-pill"><span className="live-dot" />{job.status === 'queued' ? 'In the queue' : 'Analysis in progress'}</span></div><h2 className="filename">{job.filename || 'Your uploaded match'}</h2><div className="progress-heading"><span role="status" aria-live="polite">{job.stage || 'Waiting for a processing stage'}</span><strong>{progress === null ? '—' : `${progress}%`}</strong></div><div className="progress-track" role="progressbar" aria-label="Match analysis progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress ?? undefined}><div style={{ width: `${progress ?? 0}%` }} /></div><p className="muted">Progress updates when the backend reaches a new stage. Detection can take a while; the percentage may stay unchanged while it works.</p><div className="processing-footer"><Icon name="check" size={18} /><span>Your upload has been accepted. This page will open your dashboard when it’s ready.</span></div></>}
    </section><p className="centered muted small-text">Refreshing this page reconnects to the same job while the backend remains running.</p>
  </main>;
}
