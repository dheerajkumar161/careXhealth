/**
 * Demo mode relaxes real-world time windows (record a dose before it is due, mark a session attended or
 * upload a result ahead of its date). The backend is the source of truth (`DEMO_MODE`); the flag arrives
 * with /api/auth/me and is cached here for synchronous render-time checks.
 */
let enabled = false;

export const setDemoMode = (on: boolean) => {
  enabled = on;
};

export const demoMode = () => enabled;
