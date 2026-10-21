import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';
import './styles/main.css';

// Prevent touchpad / mousewheel scroll from accidentally mutating number inputs platform-wide
if (typeof window !== 'undefined') {
  document.addEventListener(
    'wheel',
    (e) => {
      const target = e.target as HTMLElement | null;
      const active = document.activeElement as HTMLElement | null;

      if (target && target.tagName === 'INPUT' && (target as HTMLInputElement).type === 'number') {
        e.preventDefault();
        target.blur();
      } else if (active && active.tagName === 'INPUT' && (active as HTMLInputElement).type === 'number') {
        active.blur();
      }
    },
    { passive: false }
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
