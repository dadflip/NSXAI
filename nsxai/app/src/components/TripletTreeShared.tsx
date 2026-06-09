import React, { useMemo } from 'react';
import { ChevronRight, ChevronDown, Link as LinkIcon } from 'lucide-react';
import {
  type Triple,
  RDF_TYPE,
  RDFS_LABEL,
  getDisplayLabel,
  getPrimaryTypeUris as getTypes,
  predicateSortOrder,
  shouldShowTriple,
  typeColorClass,
  literalColorClass,
  shortTypeName,
  isGeneratedResource
} from '../lib/core';
import { GeneratedBadge } from './studio/StudioPrimitives';

export function TypeSuffix({
  typeUri,
  getShortUri,
  onClickType,
}: {
  typeUri: string;
  getShortUri: (u: string) => string;
  onClickType?: (e: React.MouseEvent) => void;
}) {
  const short = shortTypeName(typeUri) || getShortUri(typeUri);
  return (
    <span className="text-[11px] text-neutral-500 font-normal">
      {' '}
      <span className="text-neutral-600">a</span>{' '}
      <span
        className={`font-medium ${typeColorClass(typeUri)} ${onClickType ? 'hover:underline cursor-pointer' : ''}`}
        onClick={onClickType}
        role={onClickType ? 'button' : undefined}
      >
        {short}
      </span>
    </span>
  );
}

export function highlightText(text: string, query: string): React.ReactNode {
  if (!query.trim()) return text;
  const q = query.trim().toLowerCase();
  const idx = text.toLowerCase().indexOf(q);
  if (idx < 0) return text;
  return (
    <>
      {text.slice(0, idx)}
      <mark className="bg-amber-500/25 text-amber-100 rounded px-0.5">{text.slice(idx, idx + q.length)}</mark>
      {text.slice(idx + q.length)}
    </>
  );
}

export interface TreeNodeContext {
  subjectsMap: Map<string, Triple[]>;
  getShortUri: (u: string) => string;
  maxDepth: number;
  expanded: Set<string>;
  onToggle: (id: string) => void;
  onSelectNode: (id: string) => void;
  searchQuery: string;
  renderEditSlot?: (subject: string) => React.ReactNode;
}

export function SubjectTreeNode({
  subject,
  level,
  ctx,
}: {
  subject: string;
  level: number;
  ctx: TreeNodeContext;
}) {
  const properties = ctx.subjectsMap.get(subject) || [];
  const isOpen = ctx.expanded.has(subject);
  const displayLabel = getDisplayLabel(subject, properties, ctx.getShortUri);
  const typeUris = getTypes(properties);

  const groupedProps = useMemo(() => {
    const map = new Map<string, Triple[]>();
    properties.forEach((t) => {
      if (!shouldShowTriple(t, 'all', subject)) return;
      if (!map.has(t.predicate)) map.set(t.predicate, []);
      map.get(t.predicate)!.push(t);
    });
    return Array.from(map.entries()).sort((a, b) =>
      predicateSortOrder(a[0], b[0], 'label')
    );
  }, [properties]);

  return (
    <div className="flex flex-col w-full text-[12px] md:text-[13px]">
      <div className="flex items-start gap-2 py-1.5 px-2 hover:bg-neutral-800/30 rounded group transition-colors">
        <button
          type="button"
          className="mt-0.5 text-neutral-500 hover:text-neutral-300 shrink-0"
          onClick={() => ctx.onToggle(subject)}
        >
          {isOpen ? (
            <ChevronDown className="w-3.5 h-3.5" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5" />
          )}
        </button>
        <div
          className="flex-1 min-w-0 cursor-pointer"
          onClick={() => ctx.onSelectNode(subject)}
        >
          <div className="flex items-baseline gap-1 flex-wrap">
            {/* Label principal — rdfs:label si dispo, sinon local name */}
            <span className="font-medium text-neutral-200 group-hover:text-white leading-snug">
              {highlightText(displayLabel, ctx.searchQuery)}
            </span>
            {/* Badge si le label vient de l'URI (pas de rdfs:label) */}
            {!properties.find(t => t.predicate === RDFS_LABEL) && (
              <span className="text-[10px] text-neutral-600 font-medium bg-neutral-800/40 px-1.5 py-0.5 rounded-sm ml-1 uppercase tracking-wider">uri</span>
            )}
            {isGeneratedResource(subject, displayLabel) && <GeneratedBadge />}
            {typeUris.map((tu) => (
              <React.Fragment key={tu}>
                <TypeSuffix
                  typeUri={tu}
                  getShortUri={ctx.getShortUri}
                  onClickType={(e) => {
                    e.stopPropagation();
                    ctx.onSelectNode(tu);
                  }}
                />
              </React.Fragment>
            ))}
          </div>
          <div className="text-[11px] text-neutral-500/80 truncate mt-0.5 tracking-wide">
            {highlightText(subject, ctx.searchQuery)}
          </div>
        </div>
      </div>

      {isOpen && (
        <div className="ml-5 pl-4 border-l border-neutral-800/50 my-1 space-y-1">
          {groupedProps.length === 0 && (
            <div className="text-neutral-600 italic py-1 px-2 text-[11px]">Aucune propriété</div>
          )}
          {groupedProps.map(([predicate, entries]) => (
            <React.Fragment key={predicate}>
              <PredicateGroup
                predicate={predicate}
                entries={entries}
                level={level}
                ctx={ctx}
              />
            </React.Fragment>
          ))}
          {ctx.renderEditSlot?.(subject)}
        </div>
      )}
    </div>
  );
}

function PredicateGroup({
  predicate,
  entries,
  level,
  ctx,
}: {
  predicate: string;
  entries: Triple[];
  level: number;
  ctx: TreeNodeContext;
}) {
  const isTypePred = predicate === RDF_TYPE;
  return (
    <div className="flex flex-col mt-2 first:mt-0">
      <div
        className="py-1 px-2 text-[11px] text-neutral-400 flex items-center gap-1.5 cursor-pointer hover:text-neutral-200"
        onClick={() => ctx.onSelectNode(predicate)}
      >
        <LinkIcon className="w-3.5 h-3.5 text-neutral-500/40 shrink-0" />
        <span className="tracking-wide">{highlightText(ctx.getShortUri(predicate), ctx.searchQuery)}</span>
      </div>
      <div className="space-y-1 ml-4 border-l border-neutral-800/30 pl-2 mt-1">
        {entries.map((t, idx) => (
          <React.Fragment key={`${t.subject}-${t.predicate}-${t.object}-${idx}`}>
            <ObjectTreeNode triple={t} level={level + 1} ctx={ctx} isTypePred={isTypePred} />
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}

function ObjectTreeNode({
  triple,
  level,
  ctx,
  isTypePred,
}: {
  triple: Triple;
  level: number;
  ctx: TreeNodeContext;
  isTypePred: boolean;
}) {
  if (triple.objectType === 'Literal') {
    return (
      <div className={`py-1.5 px-2 text-[11.5px] ml-2 leading-tight ${literalColorClass()}`}>
        &quot;{highlightText(triple.object, ctx.searchQuery)}&quot;
      </div>
    );
  }

  if (isTypePred) {
    return (
      <div
        className="py-1 px-2 ml-2 cursor-pointer hover:bg-neutral-800/30 rounded"
        onClick={() => ctx.onSelectNode(triple.object)}
      >
        <TypeSuffix typeUri={triple.object} getShortUri={ctx.getShortUri} />
      </div>
    );
  }

  const hasChildren = ctx.subjectsMap.has(triple.object);
  if (hasChildren && level < ctx.maxDepth) {
    return (
      <SubjectTreeNode subject={triple.object} level={level} ctx={ctx} />
    );
  }

  const label = ctx.subjectsMap.get(triple.object)?.find((p) => p.predicate === RDFS_LABEL);
  const display = label?.object || ctx.getShortUri(triple.object);
  const objTypes = getTypes(ctx.subjectsMap.get(triple.object) || []);

  return (
    <div
      className="py-1 px-2 ml-2 flex items-baseline flex-wrap gap-0 cursor-pointer hover:bg-neutral-800/40 rounded group"
      onClick={() => ctx.onSelectNode(triple.object)}
    >
      <span className="text-neutral-300 group-hover:text-white">
        {highlightText(display, ctx.searchQuery)}
      </span>
      {isGeneratedResource(triple.object, display) && <GeneratedBadge />}
      {objTypes.map((tu) => (
        <TypeSuffix typeUri={tu} getShortUri={ctx.getShortUri} />
      ))}
      {hasChildren && level >= ctx.maxDepth && (
        <span className="text-[9px] text-neutral-600 ml-1">…</span>
      )}
    </div>
  );
}
