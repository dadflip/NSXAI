import React from 'react';

const SOURCE_META: Record<string, { label: string; color: string }> = {
  schema:    { label: 'schéma',    color: 'text-blue-400' },
  assertion: { label: 'assertion', color: 'text-emerald-400' },
  topology:  { label: 'topologie', color: 'text-amber-400' },
  graph:     { label: 'graphe',    color: 'text-neutral-500' },
};

export function SourceBadge({ source }: { source?: string }) {
  const meta = SOURCE_META[source ?? ''] ?? { label: source ?? '?', color: 'text-neutral-600' };
  return <span className={`text-[9px] font-mono ${meta.color}`}>{meta.label}</span>;
}
