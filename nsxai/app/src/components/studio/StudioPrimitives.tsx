import React from 'react';

export function StudioCard({
  title,
  subtitle,
  children,
  className = '',
  compact = false,
}: {
  title?: string;
  subtitle?: string;
  children: React.ReactNode;
  className?: string;
  compact?: boolean;
}) {
  return (
    <section
      className={`rounded-2xl border border-neutral-800/60 bg-gradient-to-br from-neutral-900/40 to-neutral-950/30 overflow-hidden backdrop-blur-sm ${className}`}
    >
      {(title || subtitle) && (
        <header className={`border-b border-neutral-800/40 bg-neutral-950/50 ${compact ? 'px-4 py-2' : 'px-6 py-4'}`}>
          {title && <h3 className={`font-semibold text-neutral-100 ${compact ? 'text-xs' : 'text-sm'}`}>{title}</h3>}
          {subtitle && <p className="text-xs text-neutral-400 mt-0.5 leading-relaxed">{subtitle}</p>}
        </header>
      )}
      <div className={compact ? 'p-3' : 'p-6'}>{children}</div>
    </section>
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-2">
      <span className="text-xs font-semibold text-neutral-200">{label}</span>
      {hint && <span className="block text-[11px] text-neutral-500">{hint}</span>}
      {children}
    </label>
  );
}

export const studioInputClass =
  'w-full rounded-xl border border-neutral-700/80 bg-neutral-950/80 px-4 py-3 text-sm text-neutral-100 placeholder:text-neutral-600 focus:outline-none focus:border-indigo-500/60 focus:ring-2 focus:ring-indigo-500/20 transition-all';

export const studioSelectClass =
  'rounded-lg border border-neutral-700/80 bg-neutral-950/80 px-2.5 py-1 text-xs text-neutral-200 focus:outline-none focus:border-indigo-500/60 focus:ring-1 focus:ring-indigo-500/20 transition-all';

export function Segmented({
  value,
  options,
  onChange,
}: {
  value: string;
  options: { id: string; label: string; icon?: React.ReactNode }[];
  onChange: (id: string) => void;
}) {
  return (
    <div className="inline-flex p-1.5 rounded-xl bg-neutral-950/80 border border-neutral-800/60 backdrop-blur-sm">
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          onClick={() => onChange(o.id)}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
            value === o.id
              ? 'bg-neutral-200 text-neutral-900'
              : 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/50'
          }`}
        >
          {o.icon}
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function PrimaryButton({
  children,
  onClick,
  disabled,
  variant = 'primary',
}: {
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: 'primary' | 'danger' | 'ghost';
}) {
  const cls =
    variant === 'primary'
      ? 'bg-neutral-200 text-neutral-900 hover:bg-neutral-100'
      : variant === 'danger'
        ? 'bg-red-950/50 text-red-200 border border-red-800/50 hover:bg-red-900/40'
        : 'border border-neutral-700/60 text-neutral-400 hover:text-white hover:border-neutral-600 hover:bg-neutral-800/50';
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium transition-all disabled:opacity-40 disabled:cursor-not-allowed ${cls}`}
    >
      {children}
    </button>
  );
}

export function StepIndicator({ step, total, label }: { step: number; total: number; label: string }) {
  return (
    <div className="flex items-center gap-3 text-xs text-neutral-400">
      <span className="flex items-center justify-center w-7 h-7 rounded-full bg-neutral-800 text-neutral-300 border border-neutral-700 font-semibold">
        {step}
      </span>
      <span className="font-medium">
        Étape {step}/{total} — {label}
      </span>
    </div>
  );
}

export function GeneratedBadge() {
  return (
    <span className="inline-flex items-center px-2.5 py-1 rounded-md text-[10px] font-semibold bg-amber-950/40 text-amber-200/90 border border-amber-800/40 shrink-0">
      Généré
    </span>
  );
}