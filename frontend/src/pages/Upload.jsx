import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { uploadMatch } from '../api/matchvision.js';
import { ErrorState, Icon } from '../components/UI.jsx';
import { rememberMatch } from '../lib/format.js';

export default function Upload() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState('');
  const [previewFailed, setPreviewFailed] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [calibration, setCalibration] = useState('');
  const input = useRef(null);
  const controller = useRef(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!file) { setPreview(''); return; }
    const url = URL.createObjectURL(file);
    setPreview(url); setPreviewFailed(false);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  useEffect(() => () => controller.current?.abort(), []);

  function selectFiles(files) {
    if (busy) return;
    setDragging(false);
    if (files.length !== 1) { setError(new Error('Choose one match video at a time.')); return; }
    const next = files[0];
    if (!/\.(mp4|avi|mov|mkv)$/i.test(next.name)) { setError(new Error('Choose an MP4, AVI, MOV or MKV video.')); return; }
    if (!next.size) { setError(new Error('This file is empty. Choose a video with content.')); return; }
    setFile(next); setError(null);
  }
  function removeFile() {
    setFile(null); setError(null);
    if (input.current) input.current.value = '';
  }
  async function submit(event) {
    event.preventDefault();
    if (!file || busy) return;
    if (calibration.trim()) {
      try {
        const value = JSON.parse(calibration);
        if (!value || Array.isArray(value) || typeof value !== 'object') throw new Error();
      } catch { setError(new Error('Optional calibration must be a valid JSON object, or leave it blank.')); return; }
    }
    setBusy(true); setError(null);
    const abort = new AbortController();
    controller.current = abort;
    try {
      const job = await uploadMatch(file, calibration, { signal: abort.signal });
      if (!/^[0-9a-f]{32}$/.test(job.analysis_id || '')) throw new Error('The upload response did not contain a valid analysis ID.');
      rememberMatch({ analysis_id: job.analysis_id, filename: job.filename || file.name });
      navigate(`/processing/${job.analysis_id}`);
    } catch (err) {
      if (err.name !== 'AbortError') setError(err);
    } finally { if (!abort.signal.aborted) setBusy(false); }
  }

  return <main className="container page upload-page">
    <div className="page-heading"><p className="eyebrow">YOUR MATCH, YOUR PERSPECTIVE</p><h1>Bring the game into view.</h1><p>Start with a video from your computer. We’ll take it from here.</p></div>
    <div className="upload-layout"><form className="panel upload-panel" onSubmit={submit}>
      <div className="panel-heading"><span className="number-tag">01</span><div><h2>Upload match footage</h2><p>One video, a complete analysis workspace.</p></div></div>
      <label htmlFor="match-file" className={`dropzone ${dragging ? 'dragging' : ''} ${busy ? 'disabled' : ''}`}
        onDragOver={event => { event.preventDefault(); if (!busy) setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={event => { event.preventDefault(); selectFiles(event.dataTransfer.files); }}>
        <span className="upload-symbol"><Icon name="upload" size={30} /></span><strong>{file ? 'Choose a different video' : 'Drop your match video here'}</strong><span>or <span className="text-green">browse files</span> on your computer</span><small>MP4 · AVI · MOV · MKV</small>
      </label>
      <input ref={input} id="match-file" type="file" className="sr-only" accept=".mp4,.avi,.mov,.mkv" disabled={busy} onChange={event => selectFiles(event.target.files)} />
      {file && <div className="selected-file"><Icon name="file" size={24} /><div><strong title={file.name}>{file.name}</strong><small>{(file.size / 1024 / 1024).toLocaleString(undefined, { maximumFractionDigits: 1 })} MB · {file.name.split('.').pop().toUpperCase()}</small></div><button type="button" className="icon-button" disabled={busy} aria-label="Remove selected video" onClick={removeFile}><Icon name="close" /></button></div>}
      {preview && !previewFailed && <video className="upload-preview" src={preview} controls playsInline preload="metadata" onError={() => setPreviewFailed(true)} aria-label="Selected video preview" />}
      {previewFailed && <p className="notice">This browser cannot preview the selected format. You can still upload it for the backend to validate.</p>}
      <details className="advanced-options"><summary>Optional shot calibration</summary><p>Only add calibration validated for this exact camera view. Leave blank otherwise; tracking still works, but shots and highlights may be unavailable.</p><label htmlFor="calibration">Input-specific calibration JSON</label><textarea id="calibration" value={calibration} onChange={event => setCalibration(event.target.value)} rows={4} maxLength={65536} disabled={busy} placeholder="Leave blank unless you have validated calibration" /></details>
      {error && <ErrorState error={error} />}
      <button className="button full-width" disabled={!file || busy} type="submit">{busy ? <><span className="spinner small-spinner" /> Uploading & validating…</> : <>Analyze match <Icon name="arrow" /></>}</button>
      <p className="form-footnote" role="status">{busy ? 'Keep this page open until your upload is accepted. Analysis begins in the background.' : 'The server validates video readability and its configured upload-size limit.'}</p>
    </form><aside className="upload-aside"><p className="eyebrow">WHAT HAPPENS NEXT</p><h2>From the touchline<br />to the details.</h2><ol className="vertical-steps"><li><Icon name="upload" /><div><h3>Your footage, securely separated</h3><p>Each upload gets its own analysis and media files.</p></div></li><li><Icon name="activity" /><div><h3>Follow real progress</h3><p>See each stage as your match is processed.</p></div></li><li><Icon name="chart" /><div><h3>Review the whole picture</h3><p>Explore movement, possession, events and team shape.</p></div></li></ol><div className="note-box"><strong>A useful starting point</strong><p>Choose a short, clear clip with a steady view of the pitch. Measurements depend on visibility and pitch calibration; missing data is never filled with invented statistics.</p></div></aside></div>
  </main>;
}
