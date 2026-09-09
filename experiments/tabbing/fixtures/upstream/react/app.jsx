import React from 'react';
import { createRoot } from 'react-dom/client';

// React 19 attaches a single delegated listener at the root container, so
// DOMDebugger.getEventListeners on any element below returns nothing.
function App() {
  const [log, setLog] = React.useState([]);
  const fired = (id) => setLog((l) => [...l, id]);

  return (
    <div>
      <h1>R — React (delegated handlers)</h1>

      <h2>The defect, in JSX</h2>
      <div className="row">
        <div data-probe="p50" className="btnish" onClick={() => fired('p50')}>
          &lt;div onClick&gt;, no tabIndex, no role
        </div>
        <span data-probe="p53" className="icon-btn btnish" onClick={() => fired('p53')}>
          <i className="material-icons">calendar_month</i>
        </span>
      </div>

      <h2>Correct</h2>
      <div className="row">
        <button data-probe="p51" className="btn" onClick={() => fired('p51')}>
          real button
        </button>
        <div
          data-probe="p52"
          role="button"
          tabIndex={0}
          className="btnish"
          onClick={() => fired('p52')}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fired('p52'); }
          }}
        >
          role=button + tabIndex + onKeyDown
        </div>
      </div>

      <h2>Focusable but not actionable</h2>
      <div className="row">
        <div data-probe="p54" tabIndex={0} className="btnish" onClick={() => fired('p54')}>
          tabIndex=0, onClick only
        </div>
      </div>

      <h2>Styled like a control, no handler</h2>
      <div className="row">
        <div data-probe="p55" className="btn btn-primary btnish">no onClick at all</div>
      </div>

      <div id="baseline-target" style={{ height: 48, marginTop: 24, background: '#fafafa' }}>
        baseline (no handler)
      </div>
      <div id="sink">{log.map((id, i) => <div key={i}>fired: {id}</div>)}</div>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
