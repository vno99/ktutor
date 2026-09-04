'use client';

import { create } from 'zustand';
import axios from 'axios';
import { apiClient } from '@/lib/api';
import { useAuthStore, isValidPseudo } from '@/lib/stores/authStore';

// uploadStore — handles multipart upload of a single document to the
// s10 backend.
//
// Backend contract (gelé, ff21046) :
//   POST /api/documents/upload  FormData(subject, file)
//     (s15 — `pseudo` removed from body; the backend reads it from the
//      JWT via `Depends(get_current_user)`. apiClient injects
//      `Authorization: Bearer <token>` from the s13 interceptor.)
//     201 → { document_id, status: "indexed" | "manual_review_needed",
//             chunks_count, ocr_confidence }
//     401 → { error, code: "invalid_token" }   (no JWT / bad JWT)
//     403 → { error, code: "forbidden" }       (cross-tenant attempt)
//     413 → { error, code: "invalid_file" }   (taille)
//     415 → { error, code: "invalid_file" }   (extension)
//     422 → { error, code: "invalid_pseudo" | "ocr_failure" }
//     500 → { error, code: "storage_failure" }
//
// CRITICAL: do NOT set Content-Type manually. apiClient.post(url,
// FormData) lets axios inject `multipart/form-data; boundary=...`.
// A manual Content-Type would strip the boundary and the backend
// would reject the upload (Piège T1).
//
// CRITICAL: discriminate 413 vs 415 on response.status, NOT on
// `code` alone (both share `code: "invalid_file"`, cf.
// backend/app/api/documents/router.py:199-210).
//
// Refs:
//   backend/app/api/documents/router.py:81-210
//   backend/app/api/documents/schemas.py:35-72
//   backend/app/services/rag/upload_service.py:39   (ALLOWED_EXTENSIONS)

export type Subject = 'maths' | 'francais';

export type UploadSuccess = {
  document_id: string;
  status: 'indexed' | 'manual_review_needed';
  chunks_count: number;
  ocr_confidence: number | null;
};

export type UploadErrorCode =
  | 'invalid_pseudo'
  | 'invalid_file'
  | 'ocr_failure'
  | 'storage_failure'
  | 'network';

export type UploadError = {
  code: UploadErrorCode;
  message: string;
};

export interface UploadState {
  selectedFile: File | null;
  subject: Subject | null;
  isUploading: boolean;
  lastResponse: UploadSuccess | null;
  lastError: UploadError | null;
  lastHttpStatus: number | null;
  hydrated: boolean;
  hydrate: () => void;
  selectFile: (file: File | null) => void;
  setSubject: (s: Subject) => void;
  clearFile: () => void;
  upload: () => Promise<void>;
  retry: () => Promise<void>;
  reset: () => void;
}

interface UploadErrorBody {
  error?: string;
  code?: UploadErrorCode;
}

export const useUploadStore = create<UploadState>((set, get) => ({
  selectedFile: null,
  subject: null,
  isUploading: false,
  lastResponse: null,
  lastError: null,
  lastHttpStatus: null,
  hydrated: false,

  // No client-only data to load; the flag exists to keep parity with
  // the auth/chat stores (cf. ADR 011) and to let the page wait for
  // the first paint before showing controls.
  hydrate: () => {
    set({ hydrated: true });
  },

  selectFile: (file) => {
    // Piège T8: ignore a select while a request is in flight.
    if (get().isUploading) return;
    set({
      selectedFile: file,
      lastResponse: null,
      lastError: null,
      lastHttpStatus: null,
    });
  },

  setSubject: (s) => {
    set({
      subject: s,
      lastResponse: null,
      lastError: null,
    });
  },

  // clearFile is used by "Retirer" AND "Uploader un autre document"
  // (Q4). It must NOT touch the subject or pseudo so the user can
  // upload a second document to the same subject without re-selecting.
  clearFile: () => {
    set({
      selectedFile: null,
      lastResponse: null,
      lastError: null,
      lastHttpStatus: null,
    });
  },

  upload: async () => {
    // StrictMode guard (P9 s11b): never open a second request while
    // one is in flight.
    if (get().isUploading) return;

    const pseudo = useAuthStore.getState().pseudo;
    if (!isValidPseudo(pseudo)) {
      set({
        lastResponse: null,
        lastError: { code: 'invalid_pseudo', message: '' },
        lastHttpStatus: null,
        isUploading: false,
      });
      return;
    }

    const { selectedFile, subject } = get();
    if (!selectedFile || !subject) return;

    const formData = new FormData();
    formData.append('subject', subject);
    formData.append('file', selectedFile);

    set({
      isUploading: true,
      lastResponse: null,
      lastError: null,
      lastHttpStatus: null,
    });

    try {
      const response = await apiClient.post<UploadSuccess>(
        '/api/documents/upload',
        formData,
      );
      set({
        isUploading: false,
        lastResponse: response.data,
        lastError: null,
        lastHttpStatus: response.status,
      });
    } catch (err) {
      // Piège T4: 413 and 415 both carry code "invalid_file" — the UI
      // must look at lastHttpStatus, not just the code.
      if (axios.isAxiosError(err) && err.response) {
        const status = err.response.status;
        const data = (err.response.data ?? {}) as UploadErrorBody;
        const code: UploadErrorCode = data.code ?? 'storage_failure';
        set({
          isUploading: false,
          lastError: { code, message: data.error ?? '' },
          lastHttpStatus: status,
        });
      } else {
        // No response at all: network error.
        set({
          isUploading: false,
          lastError: { code: 'network', message: '' },
          lastHttpStatus: null,
        });
      }
    }
  },

  retry: async () => {
    // The store has no idea about the picker's open state; the parent
    // component watches lastHttpStatus === 415 and re-opens the picker.
    await get().upload();
  },

  reset: () => {
    set({
      selectedFile: null,
      subject: null,
      lastResponse: null,
      lastError: null,
      lastHttpStatus: null,
      isUploading: false,
    });
  },
}));
