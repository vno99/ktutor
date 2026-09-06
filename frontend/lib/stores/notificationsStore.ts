'use client';

import { create } from 'zustand';
import { apiClient } from '../api';

export type NotificationItem = {
  id: string;
  type: string;
  message: string;
  is_read: boolean;
  created_at: string;
  related_id: string | null;
};

export interface NotificationsState {
  notifications: NotificationItem[];
  unreadCount: number;
  hydrated: boolean;
  pollIntervalId: number | null;
  poll: () => Promise<void>;
  startPoll: () => void;
  stopPoll: () => void;
  markRead: (id: string) => Promise<void>;
  hydrate: () => void;
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export const useNotificationsStore = create<NotificationsState>((set, get) => ({
  notifications: [],
  unreadCount: 0,
  hydrated: false,
  pollIntervalId: null,

  poll: async () => {
    try {
      const res = await apiClient.get('/api/notifications?unread_only=true');
      const data: NotificationItem[] = res.data as NotificationItem[];
      set({
        notifications: data,
        unreadCount: data.filter((n) => !n.is_read).length,
      });
    } catch {
      // Best-effort polling: ignore network errors.
    }
  },

  startPoll: () => {
    if (get().pollIntervalId !== null) return;
    // Immediate first poll, then every 30s.
    get().poll();
    const id = window.setInterval(() => {
      get().poll();
    }, 30000);
    set({ pollIntervalId: id });
  },

  stopPoll: () => {
    const id = get().pollIntervalId;
    if (id !== null) {
      window.clearInterval(id);
    }
    set({ pollIntervalId: null });
  },

  markRead: async (id: string) => {
    try {
      const res = await apiClient.post(`/api/notifications/${id}/read`);
      if (res.status !== 200 && res.status !== 201) return;
      // Update local state immediately for responsive UI.
      set((state) => ({
        notifications: state.notifications.map((n) =>
          n.id === id ? { ...n, is_read: true } : n
        ),
        unreadCount: Math.max(0, state.unreadCount - 1),
      }));
    } catch {
      // Best-effort: ignore network errors.
    }
  },

  hydrate: () => {
    set({ hydrated: true });
  },
}));
