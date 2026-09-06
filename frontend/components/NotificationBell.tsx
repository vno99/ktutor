'use client';

import { useState } from 'react';
import { Bell } from 'lucide-react';
import { useNotificationsStore } from '@/lib/stores/notificationsStore';

export interface NotificationBellProps {
  unreadCount: number;
  onClick: () => void;
}

export function NotificationBell({ unreadCount, onClick }: NotificationBellProps) {
  const [open, setOpen] = useState(false);
  const notifications = useNotificationsStore((s) => s.notifications);

  const handleClick = () => {
    setOpen((prev) => !prev);
    onClick();
  };

  const recent = notifications.slice(0, 5);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={handleClick}
        aria-label="Notifications"
        aria-expanded={open}
        className="relative inline-flex items-center justify-center h-8 w-8 rounded-full hover:bg-surface-subtle transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas"
      >
        <Bell size={20} className="text-text-secondary" aria-hidden="true" />
        {unreadCount > 0 && (
          <span
            className="absolute top-0 right-0 h-[18px] min-w-[18px] px-1 flex items-center justify-center rounded-full bg-error text-xs font-semibold text-white"
            aria-label={`${unreadCount} notification${unreadCount > 1 ? 's' : ''} non lue${unreadCount > 1 ? 's' : ''}`}
          >
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>
      {open && (
        <div
          className="absolute right-0 mt-2 w-64 bg-surface border border-border rounded-md shadow-kt-md z-20 overflow-hidden"
          role="menu"
        >
          <div className="px-3 py-2 text-xs font-semibold text-text-secondary border-b border-border uppercase tracking-wide">
            Récentes
          </div>
          {recent.length === 0 ? (
            <div className="px-3 py-3 text-sm text-text-secondary">
              Aucune notification
            </div>
          ) : (
            <ul className="py-1">
              {recent.map((n) => (
                <li key={n.id} className="px-3 py-2 text-sm text-text-primary hover:bg-surface-subtle border-b border-border last:border-b-0">
                  <div className="font-medium">{n.message}</div>
                  <div className="text-xs text-text-secondary mt-0.5">{n.type}</div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
