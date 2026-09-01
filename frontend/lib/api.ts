import axios from 'axios';

/*
 * Axios client — single point of contact with the FastAPI backend.
 *
 * `NEXT_PUBLIC_API_URL` is the convention from CLAUDE.md § Variables
 * d'Environnement. The default points to the local dev backend
 * (http://localhost:8000). In s11a, no JWT interceptor is added (real
 * auth arrives in s12-s15). The chat and upload flows added in s11b/s11c
 * import this client and rely on the baseURL.
 *
 * The CI job `frontend` injects NEXT_PUBLIC_API_URL via env. The
 * frontend/scripts/check-api-url.sh script greps the codebase for any
 * hardcoded backend URL (other than this file) to prevent drift.
 */
const baseURL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export const apiClient = axios.create({
  baseURL,
  headers: {
    Accept: 'application/json',
  },
});

export const API_BASE_URL = baseURL;
