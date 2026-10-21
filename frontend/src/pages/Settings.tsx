import React, { useState } from 'react';
import { Settings as SettingsIcon, Shield, Lock, IndianRupee, Save, CheckCircle2 } from 'lucide-react';

export const Settings: React.FC = () => {
  const [defaultBudget, setDefaultBudget] = useState(15000);
  const [maxRepairRetries, setMaxRepairRetries] = useState(3);
  const [sandboxMode, setSandboxMode] = useState('gVisor-rootless');
  const [networkEgress, setNetworkEgress] = useState('air-gapped');
  const [secretRedaction, setSecretRedaction] = useState(true);
  const [minRationaleChars, setMinRationaleChars] = useState(10);
  const [saved, setSaved] = useState(false);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  };

  return (
    <div>
      <div className="page-heading">
        <div>
          <h1>Platform Governance & Security Settings</h1>
          <p className="subtitle">
            Configure enterprise budget guardrails, container sandbox isolation, and secret redaction policies.
          </p>
        </div>
        <div className="heading-actions">
          {saved && (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', color: 'var(--success)', fontSize: '12px', fontWeight: 600 }}>
              <CheckCircle2 size={16} /> Policies Saved
            </span>
          )}
        </div>
      </div>

      <form onSubmit={handleSave}>
        <div className="form-layout">
          <div>
            {/* Section 1: Budget Limits */}
            <div className="form-section">
              <h2>1. Autonomous Spend Limits</h2>
              <p>Prevent uncontrolled LLM inference costs and execution cycles.</p>

              <div className="form-grid">
                <div className="form-field">
                  <label>Default Autonomous Job Budget (₹ INR)</label>
                  <input
                    type="number"
                    className="field"
                    value={defaultBudget}
                    onChange={(e) => setDefaultBudget(Number(e.target.value))}
                    onWheel={(e) => (e.target as HTMLElement).blur()}
                    min={50}
                    max={1000000}
                    step={100}
                  />
                  <small>Jobs halt automatically when spend exceeds 100% of this cap.</small>
                </div>

                <div className="form-field">
                  <label>Max Inner-Loop Repair Retries</label>
                  <input
                    type="number"
                    className="field"
                    value={maxRepairRetries}
                    onChange={(e) => setMaxRepairRetries(Number(e.target.value))}
                    onWheel={(e) => (e.target as HTMLElement).blur()}
                    min={1}
                    max={5}
                  />
                  <small>Maximum repair iterations before marking a module as degraded.</small>
                </div>
              </div>
            </div>

            {/* Section 2: Sandboxing */}
            <div className="form-section">
              <h2>2. Container Sandboxing & Isolation</h2>
              <p>CodeWriter and TestRunner sandboxed execution boundary policies.</p>

              <div className="form-grid">
                <div className="form-field">
                  <label>Sandbox Runtime</label>
                  <select
                    className="field"
                    value={sandboxMode}
                    onChange={(e) => setSandboxMode(e.target.value)}
                  >
                    <option value="gVisor-rootless">gVisor (runsc) Rootless Container (Recommended)</option>
                    <option value="docker-rootless">Docker Rootless with seccomp profile</option>
                  </select>
                </div>

                <div className="form-field">
                  <label>Network Egress Isolation</label>
                  <select
                    className="field"
                    value={networkEgress}
                    onChange={(e) => setNetworkEgress(e.target.value)}
                  >
                    <option value="air-gapped">Air-Gapped (Zero Outbound Network Access)</option>
                    <option value="package-whitelist">Whitelisted Registries Only (npm / Maven Central)</option>
                  </select>
                </div>
              </div>
            </div>

            {/* Section 3: Governance & Security */}
            <div className="form-section">
              <h2>3. Gate Governance & Secrets</h2>
              <p>Audit trail enforcement and non-bypassable reviewer requirements.</p>

              <div className="form-grid">
                <div className="form-field">
                  <label>Minimum Reviewer Rationale Length</label>
                  <input
                    type="number"
                    className="field"
                    value={minRationaleChars}
                    onChange={(e) => setMinRationaleChars(Number(e.target.value))}
                    onWheel={(e) => (e.target as HTMLElement).blur()}
                    min={10}
                    max={200}
                  />
                  <small>Ensures compliance audit logs record substantive justification.</small>
                </div>

                <div className="form-field span-two">
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={secretRedaction}
                      onChange={(e) => setSecretRedaction(e.target.checked)}
                    />
                    <span><strong>Enforce Automated Secret Redaction</strong> (Masks AWS keys, GitHub tokens, and DB passwords before storage)</span>
                  </label>
                </div>
              </div>
            </div>

            <div className="form-actions">
              <button type="submit" className="button button-primary">
                <Save size={14} />
                <span>Save Platform Policies</span>
              </button>
            </div>
          </div>
        </div>
      </form>
    </div>
  );
};
