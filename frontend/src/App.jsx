import { Component, useEffect } from 'react';
import { Link, Route, Routes, useLocation } from 'react-router-dom';
import { Brand, Icon } from './components/UI.jsx';
import Landing from './pages/Landing.jsx';
import Upload from './pages/Upload.jsx';
import Processing from './pages/Processing.jsx';
import Analysis from './pages/Analysis.jsx';

class ErrorBoundary extends Component {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <main className="container page"><div className="error-state"><h1>Something interrupted the page</h1><p>Your backend analysis is not cancelled. Refresh to reconnect.</p><button className="button" onClick={() => window.location.reload()}>Reload page</button></div></main>;
    return this.props.children;
  }
}
export default function App() {
  const location = useLocation();
  useEffect(() => {
    if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView({ behavior: 'smooth' });
    else window.scrollTo(0, 0);
  }, [location.pathname, location.hash]);
  return <ErrorBoundary>
    <a href="#main-content" className="skip-link">Skip to content</a>
    <header className="site-header no-print"><div className="container header-inner"><Brand /><nav aria-label="Main navigation"><Link to="/#how-it-works" className="quiet-link">How it works</Link><Link to="/upload" className="button small">Analyze match <Icon name="arrow" size={16} /></Link></nav></div></header>
    <div id="main-content" tabIndex={-1}>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/upload" element={<Upload />} />
        <Route path="/processing/:analysisId" element={<Processing />} />
        <Route path="/analysis/:analysisId" element={<Analysis />} />
        <Route path="*" element={<main className="container page"><h1>Page not found</h1><Link className="button" to="/">Back to MatchVision</Link></main>} />
      </Routes>
    </div>
    <footer className="site-footer no-print"><div className="container footer-inner"><span>MatchVision</span><span>From match footage to a clearer team picture.</span><span>Built for the touchline.</span></div></footer>
  </ErrorBoundary>;
}
