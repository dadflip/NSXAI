/**
 * Base URL for the Python FastAPI backend.
 * Empty in dev: Vite proxies /api/* to localhost:8000.
 * Set VITE_API_BASE at build time for production (e.g. http://localhost:8000).
 */
export const API_BASE = import.meta.env.DEV
  ? ''
  : (import.meta.env.VITE_API_BASE ?? 'http://localhost:8000');

/**
 * Build a full API URL from a path like '/api/sparql'
 */
export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}
