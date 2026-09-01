import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        primary: 'var(--color-primary)',
        'primary-strong': 'var(--color-primary-strong)',
        canvas: 'var(--color-canvas)',
        surface: 'var(--color-surface)',
        'surface-subtle': 'var(--color-surface-subtle)',
        border: 'var(--color-border)',
        'text-primary': 'var(--color-text-primary)',
        'text-secondary': 'var(--color-text-secondary)',
        'text-tertiary': 'var(--color-text-tertiary)',
        'accent-warm': 'var(--color-accent-warm)',
        success: 'var(--color-success)',
        warning: 'var(--color-warning)',
        error: 'var(--color-error)',
        info: 'var(--color-info)',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      borderRadius: {
        xs: '4px',
        sm: '6px',
        md: '8px',
        lg: '12px',
        xl: '16px',
      },
      boxShadow: {
        'kt-sm': '0 1px 2px 0 rgba(13, 15, 20, 0.04)',
        'kt-default': '0 2px 4px 0 rgba(13, 15, 20, 0.06), 0 1px 2px 0 rgba(13, 15, 20, 0.04)',
        'kt-md': '0 4px 12px 0 rgba(13, 15, 20, 0.08)',
        'kt-lg': '0 12px 32px 0 rgba(13, 15, 20, 0.12)',
      },
    },
  },
  plugins: [],
};

export default config;
