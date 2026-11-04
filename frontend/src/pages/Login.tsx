import React, { useState } from 'react';
import {
  Layers,
  ShieldCheck,
  ArrowRight,
  Lock,
  Mail,
  CheckCircle2,
  UserPlus,
  User as UserIcon,
  Eye,
  EyeOff,
} from 'lucide-react';
import { api } from '../services/api';
import type { User } from '../types/domain';

interface LoginProps {
  onSuccess: (user: User) => void;
}

export const Login: React.FC<LoginProps> = ({ onSuccess }) => {
  const [mode, setMode] = useState<'login' | 'register'>('login');

  // Login fields (clean defaults, remembering last registered/used email)
  const [email, setEmail] = useState(() => {
    return localStorage.getItem('rebase_last_email') || '';
  });
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  // Registration fields
  const [regFullName, setRegFullName] = useState('');
  const [regEmail, setRegEmail] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [regConfirmPassword, setRegConfirmPassword] = useState('');
  const [showRegPassword, setShowRegPassword] = useState(false);
  const [showRegConfirmPassword, setShowRegConfirmPassword] = useState(false);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanEmail = email.trim().toLowerCase();
    if (!cleanEmail) {
      setError('Please enter your work email.');
      return;
    }
    if (!password) {
      setError('Please enter your password.');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      setSuccessMessage(null);
      const user = await api.login(cleanEmail, password);
      localStorage.setItem('rebase_last_email', cleanEmail);
      onSuccess(user);
    } catch (err: any) {
      setError(err.message || 'Authentication failed. Please verify your credentials.');
    } finally {
      setLoading(false);
    }
  };

  const handleRegisterSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccessMessage(null);

    const cleanName = regFullName.trim();
    const cleanEmail = regEmail.trim().toLowerCase();

    if (!cleanName) {
      setError('Please provide your full name.');
      return;
    }
    if (!cleanEmail) {
      setError('Please provide a valid work email.');
      return;
    }
    if (regPassword.length < 8) {
      setError('Password must contain at least 8 characters.');
      return;
    }
    if (regPassword !== regConfirmPassword) {
      setError('Passwords do not match. Please re-enter.');
      return;
    }

    try {
      setLoading(true);
      const user = await api.register(cleanName, cleanEmail, regPassword);
      localStorage.setItem('rebase_last_email', cleanEmail);
      setEmail(cleanEmail);
      setPassword('');
      onSuccess(user);
    } catch (err: any) {
      setError(err.message || 'Registration failed. Please check your information.');
    } finally {
      setLoading(false);
    }
  };

  const handlePresetSelect = (presetEmail: string, presetPassword: string) => {
    setEmail(presetEmail);
    setPassword(presetPassword);
    setMode('login');
    setError(null);
    setSuccessMessage(null);
  };

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        minHeight: '100vh',
        backgroundColor: 'var(--background)',
      }}
    >
      {/* Left Column: Brand & Security Proof */}
      <div
        style={{
          backgroundColor: 'var(--sidebar-surface)',
          borderRight: '1px solid var(--border)',
          padding: '60px 80px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', fontSize: '26px', fontWeight: 800 }}>
            <Layers color="var(--primary)" size={32} />
            <span>Rebase<span style={{ color: 'var(--primary)' }}>.</span></span>
          </div>
          <div style={{ marginTop: '12px', fontSize: '13px', color: 'var(--muted-foreground)' }}>
            Enterprise Multi-Agent Legacy Code Modernization Platform
          </div>

          <div style={{ marginTop: '80px', maxWidth: '440px' }}>
            <h2 style={{ fontSize: '28px', fontWeight: 700, lineHeight: 1.3, marginBottom: '16px' }}>
              Autonomous legacy migration with mathematical behavioral equivalence.
            </h2>
            <p style={{ fontSize: '13px', color: 'var(--muted-foreground)', lineHeight: 1.7 }}>
              Transform enterprise legacy codebases into modern, cloud-native architectures using sandboxed specialist multi-agent coordination.
            </p>
          </div>
        </div>

        {/* Security & Governance Badges */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', maxWidth: '440px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '12px' }}>
            <CheckCircle2 size={16} color="var(--primary)" />
            <span>Strict G1–G4 human-in-the-loop approval gates</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '12px' }}>
            <CheckCircle2 size={16} color="var(--primary)" />
            <span>Dual-harness frozen characterization verification</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '12px' }}>
            <CheckCircle2 size={16} color="var(--primary)" />
            <span>Append-only PostgreSQL cryptographic audit logging</span>
          </div>
        </div>
      </div>

      {/* Right Column: Sign In / Register Forms */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '40px',
        }}
      >
        <div style={{ width: '100%', maxWidth: '420px' }}>
          {/* Mode Switcher Tabs */}
          <div
            style={{
              display: 'flex',
              borderBottom: '1px solid var(--border)',
              marginBottom: '28px',
            }}
          >
            <button
              type="button"
              onClick={() => { setMode('login'); setError(null); }}
              style={{
                flex: 1,
                padding: '12px 16px',
                border: 'none',
                background: 'none',
                fontWeight: mode === 'login' ? 700 : 500,
                color: mode === 'login' ? 'var(--primary)' : 'var(--muted-foreground)',
                borderBottom: mode === 'login' ? '2px solid var(--primary)' : '2px solid transparent',
                cursor: 'pointer',
                fontSize: '13px',
                transition: 'all 0.15s ease',
              }}
            >
              Sign in to Workspace
            </button>
            <button
              type="button"
              onClick={() => { setMode('register'); setError(null); }}
              style={{
                flex: 1,
                padding: '12px 16px',
                border: 'none',
                background: 'none',
                fontWeight: mode === 'register' ? 700 : 500,
                color: mode === 'register' ? 'var(--primary)' : 'var(--muted-foreground)',
                borderBottom: mode === 'register' ? '2px solid var(--primary)' : '2px solid transparent',
                cursor: 'pointer',
                fontSize: '13px',
                transition: 'all 0.15s ease',
              }}
            >
              Create Account
            </button>
          </div>

          <div style={{ marginBottom: '24px' }}>
            <h1 style={{ fontSize: '22px', fontWeight: 700, marginBottom: '6px' }}>
              {mode === 'login' ? 'Sign in to Workspace' : 'Create Workspace Account'}
            </h1>
            <p style={{ fontSize: '12px', color: 'var(--muted-foreground)' }}>
              {mode === 'login'
                ? 'Enter your registered credentials or select a demo identity.'
                : 'Register a new enterprise profile. All credentials persist to PostgreSQL.'}
            </p>
          </div>

          {error && (
            <div
              style={{
                padding: '10px 14px',
                backgroundColor: 'var(--danger-surface)',
                color: 'var(--destructive)',
                borderRadius: 'var(--radius-md)',
                fontSize: '12px',
                marginBottom: '20px',
                border: '1px solid rgba(239, 68, 68, 0.2)',
              }}
            >
              {error}
            </div>
          )}

          {successMessage && (
            <div
              style={{
                padding: '10px 14px',
                backgroundColor: 'rgba(34, 197, 94, 0.1)',
                color: 'var(--success)',
                borderRadius: 'var(--radius-md)',
                fontSize: '12px',
                marginBottom: '20px',
                border: '1px solid rgba(34, 197, 94, 0.2)',
              }}
            >
              {successMessage}
            </div>
          )}

          {/* Mode 1: LOGIN FORM */}
          {mode === 'login' ? (
            <form onSubmit={handleLoginSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div className="form-field">
                <label>Work Email</label>
                <div style={{ position: 'relative' }}>
                  <input
                    type="email"
                    className="field"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="name@company.com"
                    autoComplete="email"
                    required
                  />
                </div>
              </div>

              <div className="form-field">
                <label>Password</label>
                <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                  <input
                    type={showPassword ? 'text' : 'password'}
                    className="field"
                    style={{ paddingRight: '38px', width: '100%' }}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter your password"
                    autoComplete="current-password"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    style={{
                      position: 'absolute',
                      right: '10px',
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      color: 'var(--muted-foreground)',
                      display: 'flex',
                      alignItems: 'center',
                    }}
                    title={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                className="button button-primary"
                style={{ width: '100%', padding: '10px', marginTop: '6px' }}
                disabled={loading}
              >
                {loading ? 'Authenticating...' : 'Sign in to Platform'}
                <ArrowRight size={14} />
              </button>

              <div style={{ textAlign: 'center', marginTop: '8px' }}>
                <button
                  type="button"
                  onClick={() => { setMode('register'); setError(null); }}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: 'var(--primary)',
                    fontSize: '12px',
                    cursor: 'pointer',
                    textDecoration: 'underline',
                  }}
                >
                  Don't have an account? Create an enterprise profile
                </button>
              </div>
            </form>
          ) : (
            /* Mode 2: REGISTRATION FORM */
            <form onSubmit={handleRegisterSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div className="form-field">
                <label>Full Name</label>
                <input
                  type="text"
                  className="field"
                  value={regFullName}
                  onChange={(e) => setRegFullName(e.target.value)}
                  placeholder="e.g. Elena Rostova"
                  autoComplete="name"
                  required
                />
              </div>

              <div className="form-field">
                <label>Work Email</label>
                <input
                  type="email"
                  className="field"
                  value={regEmail}
                  onChange={(e) => setRegEmail(e.target.value)}
                  placeholder="name@company.com"
                  autoComplete="email"
                  required
                />
              </div>

              <div className="form-field">
                <label>Password (min 8 characters)</label>
                <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                  <input
                    type={showRegPassword ? 'text' : 'password'}
                    className="field"
                    style={{ paddingRight: '38px', width: '100%' }}
                    value={regPassword}
                    onChange={(e) => setRegPassword(e.target.value)}
                    placeholder="Choose a secure password"
                    minLength={8}
                    autoComplete="new-password"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowRegPassword(!showRegPassword)}
                    style={{
                      position: 'absolute',
                      right: '10px',
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      color: 'var(--muted-foreground)',
                      display: 'flex',
                      alignItems: 'center',
                    }}
                    title={showRegPassword ? 'Hide password' : 'Show password'}
                  >
                    {showRegPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>

              <div className="form-field">
                <label>Confirm Password</label>
                <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                  <input
                    type={showRegConfirmPassword ? 'text' : 'password'}
                    className="field"
                    style={{ paddingRight: '38px', width: '100%' }}
                    value={regConfirmPassword}
                    onChange={(e) => setRegConfirmPassword(e.target.value)}
                    placeholder="Re-enter password"
                    minLength={8}
                    autoComplete="new-password"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowRegConfirmPassword(!showRegConfirmPassword)}
                    style={{
                      position: 'absolute',
                      right: '10px',
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      color: 'var(--muted-foreground)',
                      display: 'flex',
                      alignItems: 'center',
                    }}
                    title={showRegConfirmPassword ? 'Hide password' : 'Show password'}
                  >
                    {showRegConfirmPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                className="button button-primary"
                style={{ width: '100%', padding: '10px', marginTop: '6px' }}
                disabled={loading}
              >
                {loading ? 'Creating Profile...' : 'Create Account & Enter Platform'}
                <UserPlus size={14} />
              </button>

              <div style={{ textAlign: 'center', marginTop: '8px' }}>
                <button
                  type="button"
                  onClick={() => { setMode('login'); setError(null); }}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: 'var(--primary)',
                    fontSize: '12px',
                    cursor: 'pointer',
                    textDecoration: 'underline',
                  }}
                >
                  Already registered? Sign in to workspace
                </button>
              </div>
            </form>
          )}

          {/* Quick Demo Identities */}
          <div style={{ marginTop: '32px', borderTop: '1px solid var(--border)', paddingTop: '18px' }}>
            <div style={{ fontSize: '10px', fontWeight: 700, color: 'var(--muted-foreground)', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '10px' }}>
              Quick Demo Identities:
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <button
                type="button"
                className="button button-secondary button-sm"
                style={{ justifyContent: 'flex-start' }}
                onClick={() => handlePresetSelect('alex.morgan@acme.corp', 'AdminSecure123!')}
              >
                <ShieldCheck size={13} color="var(--primary)" />
                <strong>Alex Morgan</strong> · Lead Architect (Admin)
              </button>
              <button
                type="button"
                className="button button-secondary button-sm"
                style={{ justifyContent: 'flex-start' }}
                onClick={() => handlePresetSelect('sarah.chen@acme.corp', 'Password123!')}
              >
                <ShieldCheck size={13} color="var(--warning)" />
                <strong>Sarah Chen</strong> · Security Officer (Reviewer)
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
