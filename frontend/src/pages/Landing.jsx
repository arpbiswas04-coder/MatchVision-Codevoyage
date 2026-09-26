import { Link } from 'react-router-dom';
import { Icon } from '../components/UI.jsx';
import { lastMatch } from '../lib/format.js';

const features = [
  ['players', 'Player tracking', 'Follow player movement with consistent logical identities.'],
  ['pitch', 'Team analysis', 'Bring team-level movement and performance into focus.'],
  ['chart', 'Possession', 'Understand estimated ball control across the match.'],
  ['activity', 'Speed & distance', 'Explore the available movement estimates for each player.'],
  ['target', 'Heatmaps', 'See where tracked players and teams spend their time.'],
  ['time', 'Event detection', 'Review detected passes and probable shot events.'],
  ['pitch', 'Tactical analysis', 'Examine team shape, spatial spread and formation hypotheses.'],
  ['play', 'Automatic highlights', 'Revisit high-confidence actions when eligible events exist.'],
];
function PitchIllustration() {
  return <div className="pitch-illustration"><div className="board-header"><span className="live-dot" /> THE GAME, IN VIEW <Icon name="pitch" /></div><svg viewBox="0 0 460 540" role="img" aria-label="Illustrative football pitch with player tracking markers, not actual match data">
    <rect x="30" y="25" width="400" height="490" rx="2" fill="#122c27" stroke="#45695b" />
    {[0, 1, 2, 3, 4, 5].map(i => <rect key={i} x="31" y={26 + i * 80} width="398" height="40" fill="#17362c" />)}
    <g fill="none" stroke="#638472" strokeWidth="1.2"><path d="M30 270h400M140 25v80h180V25M180 25v35h100V25M140 515v-80h180v80M180 515v-35h100v35" /><circle cx="230" cy="270" r="58" /><circle cx="230" cy="270" r="2" /><path d="M192 105q38 50 76 0M192 435q38-50 76 0" /></g>
    <path d="m105 350 82-68 59 64 79-136" fill="none" stroke="#77d29a" strokeWidth="2" strokeDasharray="5 7" opacity=".65" />
    {[[105, 350], [187, 282], [246, 346], [325, 210], [220, 450]].map(([x, y], i) => <g key={i}><rect x={x - 15} y={y - 19} width="30" height="38" rx="5" fill="none" stroke="#8ae1ac" opacity=".8" /><circle cx={x} cy={y} r="6" fill="#8ae1ac" /></g>)}
    {[[140, 180], [280, 155], [150, 395], [350, 325], [215, 86]].map(([x, y], i) => <circle key={i} cx={x} cy={y} r="7" fill="#91a9d1" />)}
    <circle cx="202" cy="290" r="4" fill="#f8f5e6" />
  </svg><div className="board-footer"><span><i className="legend green" /> Player movement</span><span><i className="legend blue" /> Team shape</span></div><p className="illustration-note">Concept illustration · Your insights come from your footage.</p></div>;
}
export default function Landing() {
  const previous = lastMatch();
  return <main>
    <section className="container hero">
      <div className="hero-copy"><p className="eyebrow"><span className="line-accent" /> A CLEARER VIEW OF YOUR GAME</p><h1>Every movement.<br />A better <em>understanding.</em></h1><h2>Video-Based Match Analytics for Teams</h2><p className="hero-description">Turn ordinary match footage into actionable tactical and performance insights. Your video. Your team. A new perspective on the game.</p><div className="button-row"><Link to="/upload" className="button">Analyze match <Icon name="arrow" /></Link><a href="#how-it-works" className="button secondary">See how it works</a></div>{previous?.analysis_id && <Link className="resume-link" to={`/processing/${previous.analysis_id}`}>Return to your last analysis <Icon name="arrow" size={16} /></Link>}<div className="hero-caption"><Icon name="file" size={16} /> Upload your own footage. Review only what the data supports.</div></div>
      <PitchIllustration />
    </section>
    <section id="how-it-works" className="workflow-section"><div className="container"><div className="section-heading"><div><p className="eyebrow">FROM FOOTAGE TO FEEDBACK</p><h2>Your next team talk starts here.</h2></div><p>One upload. A connected view of performance.</p></div><ol className="workflow">{['Upload match', 'AI analysis', 'Player & ball tracking', 'Tactical insights', 'Coach report'].map((step, i) => <li key={step}><span className="step-number">0{i + 1}</span><h3>{step}</h3>{i < 4 && <Icon name="arrow" size={17} />}</li>)}</ol></div></section>
    <section className="container feature-section"><div className="section-heading"><div><p className="eyebrow">MADE FOR THE PEOPLE BEHIND THE TEAM</p><h2>Less guesswork.<br />More to work with.</h2></div><p>A practical analysis workspace for coaches, college teams and amateur clubs.</p></div><div className="feature-grid">{features.map(([icon, title, text]) => <article className="feature-card" key={title}><Icon name={icon} size={24} /><h3>{title}</h3><p>{text}</p></article>)}</div></section>
    <section className="container bottom-cta"><div><p className="eyebrow">BRING YOUR NEXT MATCH INTO FOCUS</p><h2>The footage is yours.<br />The next insight could be, too.</h2></div><Link to="/upload" className="button">Analyze match <Icon name="arrow" /></Link></section>
  </main>;
}
