import { Trophy } from 'lucide-react';
import { useTranslations } from 'next-intl';

export interface LevelBadgeProps {
  level: string;
  totalPoints: number;
  className?: string;
}

const LEVEL_MAP: Record<string, { token: string; labelKey: string }> = {
  Apprenti: { token: 'primary', labelKey: 'level.apprentice' },
  Confirmé: { token: 'success', labelKey: 'level.confirmed' },
  Expert: { token: 'accent-warm', labelKey: 'level.expert' },
};

export function LevelBadge({ level, totalPoints, className = '' }: LevelBadgeProps) {
  const t = useTranslations('rewards');
  const mapping = LEVEL_MAP[level] || LEVEL_MAP['Apprenti'];
  const token = mapping!.token;
  const labelKey = mapping!.labelKey;

  // Design tokens: primary (#3D5AFE), success (#16A34A), accent-warm (#FF6B4A)
  const colorClasses: Record<string, { border: string; text: string; bg: string; iconText: string }> = {
    primary: {
      border: 'border-primary',
      text: 'text-primary',
      bg: 'bg-primary/10',
      iconText: 'text-primary',
    },
    success: {
      border: 'border-success',
      text: 'text-success',
      bg: 'bg-success/10',
      iconText: 'text-success',
    },
    'accent-warm': {
      border: 'border-accent-warm',
      text: 'text-accent-warm',
      bg: 'bg-accent-warm/10',
      iconText: 'text-accent-warm',
    },
  };

  const colors = colorClasses[token]!;

  return (
    <div
      className={`flex flex-col sm:flex-row items-start sm:items-center gap-3 sm:gap-4 rounded-xl border p-4 bg-surface shadow-kt-default ${colors.border} ${colors.bg} ${className}`.trim()}
      aria-label={`${t('badgeAria', { level: t(labelKey as any), points: totalPoints })}`}
    >
      <div
        className={`inline-flex items-center gap-2 rounded-full border-2 px-3 py-1 text-sm font-bold ${colors.border} ${colors.text}`}
        aria-hidden="true"
      >
        <Trophy size={20} className={colors.iconText} aria-hidden="true" />
        <span>{t(labelKey as any)}</span>
      </div>
      <div className="flex flex-col">
        <span className="text-xl md:text-2xl font-bold tracking-tight text-text-primary leading-none">
          {totalPoints} {t('points')}
        </span>
        <span className="text-xs text-text-secondary">{t('rewards.section')}</span>
      </div>
    </div>
  );
}
