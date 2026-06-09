export const NS = {
  RDF: 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
  RDFS: 'http://www.w3.org/2000/01/rdf-schema#',
  OWL: 'http://www.w3.org/2002/07/owl#',
  XSD: 'http://www.w3.org/2001/XMLSchema#',
};

export const URIS = {
  RDF_TYPE: `${NS.RDF}type`,
  RDFS_LABEL: `${NS.RDFS}label`,
  RDFS_SUBCLASS: `${NS.RDFS}subClassOf`,
  RDFS_LITERAL: `${NS.RDFS}Literal`,
  RDFS_STRING: `${NS.RDFS}string`,
  OWL_CLASS: `${NS.OWL}Class`,
  OWL_OP: `${NS.OWL}ObjectProperty`,
  OWL_DP: `${NS.OWL}DatatypeProperty`,
  OWL_NI: `${NS.OWL}NamedIndividual`,
  OWL_THING: `${NS.OWL}Thing`,
  OWL_ONTOLOGY: `${NS.OWL}Ontology`,
  OWL_ANNOTATION_PROP: `${NS.OWL}AnnotationProperty`,
};

export const META_TYPES = new Set([
  URIS.OWL_NI,
  URIS.OWL_CLASS,
  URIS.OWL_OP,
  URIS.OWL_DP,
  URIS.OWL_THING,
]);

export function getShortUri(uri: string): string {
  if (!uri) return '';
  if (uri.startsWith('_:')) return `Blank Node (${uri.substring(2, 8)}...)`;
  const parts = uri.split(/[/#]/);
  return parts[parts.length - 1] || uri;
}

export function isLiteralRange(range?: string): boolean {
  if (!range) return false;
  const lowerRange = range.toLowerCase();
  return (
    range.startsWith(NS.XSD) ||
    range === URIS.RDFS_LITERAL ||
    range === URIS.RDFS_STRING ||
    lowerRange.includes('literal') ||
    lowerRange.includes('string') ||
    lowerRange.includes('integer')
  );
}

export function getOntologyOrigin(uri: string): string | null {
  if (!uri) return null;
  const match = uri.match(/\/ontologies\/([^#]+)#/);
  if (match) {
    const parts = match[1].split('/');
    return parts[parts.length - 1];
  }
  return null;
}

import { CONFIG } from '../config';

export function isGeneratedResource(uri: string, label?: string): boolean {
  const local = (uri || '').split(/[/#]/).pop() || '';
  const prefix = CONFIG.ontology.generatedLocalPrefix;
  if (local.startsWith(`${prefix}_`) || local === prefix) {
    return true;
  }
  if (label?.trim().toLowerCase().startsWith(prefix.toLowerCase())) return true;
  return false;
}

export function isGeneratedLiteral(value: string): boolean {
  return String(value).startsWith(`${CONFIG.ontology.generatedLocalPrefix}_`);
}

export interface Triple {
  subject: string;
  predicate: string;
  object: string;
  objectType: string;
  datatype?: string;
}

export function isLiteralType(type: string): boolean {
  if (!type) return false;
  const t = type.toLowerCase();
  return t === 'literal' || t === 'typed-literal';
}

export type NodeKind =
  | 'class'
  | 'individual'
  | 'property'
  | 'literal'
  | 'ontology'
  | 'blank'
  | 'unknown';

export interface PredicateSuggestion {
  uri: string;
  domains?: string[];
  range?: string;
  label?: string;
  comment?: string;
  source?: string;
  type?: string;
}

export interface ObjectCandidate {
  uri: string;
  label?: string;
  kind: 'instance' | 'literal' | 'iri' | 'new_instance' | 'new_uri';
  classUri?: string;
  datatype?: string;
}

export interface PathStep {
  id: string;
  subject: string;
  predicate: string;
  object: string;
  isLiteral: boolean;
  datatype?: string;
  objectLabel?: string;
  predicateLabel?: string;
}

export const NATIVE_PREFIXES = [
  NS.RDF,
  NS.RDFS,
  NS.OWL,
];

export function isNativePred(uri: string): boolean {
  return NATIVE_PREFIXES.some((p) => uri.startsWith(p));
}

export const RDF_TYPE = URIS.RDF_TYPE;
export const RDFS_LABEL = URIS.RDFS_LABEL;
export const RDFS_SUBCLASS = URIS.RDFS_SUBCLASS;

export function buildSubjectsMap(triples: Triple[]): Map<string, Triple[]> {
  const map = new Map<string, Triple[]>();
  for (const t of triples) {
    if (!map.has(t.subject)) map.set(t.subject, []);
    map.get(t.subject)!.push(t);
  }
  return map;
}

export function inferNodeKinds(
  triples: Triple[],
  architecture?: {
    classes?: { uri: string }[];
    properties?: { uri: string }[];
    individuals?: { uri: string }[];
  } | null
): Map<string, NodeKind> {
  const kinds = new Map<string, NodeKind>();

  architecture?.classes?.forEach((c) => kinds.set(c.uri, 'class'));
  architecture?.properties?.forEach((p) => kinds.set(p.uri, 'property'));
  architecture?.individuals?.forEach((i) => kinds.set(i.uri, 'individual'));

  for (const t of triples) {
    if (!kinds.has(t.subject)) {
      kinds.set(t.subject, t.subject.startsWith('_:') ? 'blank' : 'unknown');
    }
    if (t.objectType === 'Literal') continue;
    if (!kinds.has(t.object)) {
      kinds.set(t.object, t.object.startsWith('_:') ? 'blank' : 'unknown');
    }
  }

  for (const t of triples) {
    if (t.predicate !== RDF_TYPE || t.objectType === 'Literal') continue;
    const o = t.object;
    if (o === URIS.OWL_CLASS) kinds.set(t.subject, 'class');
    else if (o === URIS.OWL_OP || o === URIS.OWL_DP) kinds.set(t.subject, 'property');
    else if (o === URIS.OWL_NI) kinds.set(t.subject, 'individual');
    else if (o.includes('Ontology')) kinds.set(t.subject, 'ontology');
    else if (kinds.get(t.subject) === 'unknown') kinds.set(t.subject, 'individual');
  }

  return kinds;
}

export function findRootSubjects(triples: Triple[], subjectsMap: Map<string, Triple[]>): string[] {
  const referenced = new Set<string>();
  for (const t of triples) {
    if (t.objectType !== 'Literal' && t.predicate !== RDF_TYPE) {
      referenced.add(t.object);
    }
  }
  const roots = Array.from(subjectsMap.keys()).filter((s) => !referenced.has(s));
  if (roots.length === 0) {
    return Array.from(subjectsMap.keys());
  }
  return roots;
}

export function getDisplayLabel(
  subject: string,
  properties: Triple[],
  getShortUri: (u: string) => string
): string {
  const label = properties.find((t) => t.predicate === RDFS_LABEL);
  return label ? label.object : getShortUri(subject);
}

export function kindBadgeClass(kind: NodeKind): string {
  switch (kind) {
    case 'class':
      return 'bg-indigo-900/30 text-indigo-300 border-indigo-700/40';
    case 'property':
      return 'bg-orange-900/30 text-orange-300 border-orange-700/40';
    case 'individual':
      return 'bg-emerald-900/30 text-emerald-300 border-emerald-700/40';
    case 'literal':
      return 'bg-neutral-800 text-neutral-400 border-neutral-700';
    case 'ontology':
      return 'bg-violet-900/30 text-violet-300 border-violet-700/40';
    default:
      return 'bg-neutral-900/50 text-neutral-500 border-neutral-800';
  }
}

export function collectAncestorSubjects(
  target: string,
  triples: Triple[],
  visited = new Set<string>()
): Set<string> {
  const ancestors = new Set<string>();
  if (visited.has(target)) return ancestors;
  visited.add(target);

  for (const t of triples) {
    if (t.object === target && t.objectType !== 'Literal') {
      ancestors.add(t.subject);
      collectAncestorSubjects(t.subject, triples, visited).forEach((a) => ancestors.add(a));
    }
  }
  return ancestors;
}

export function getPrimaryTypeUris(properties: Triple[]): string[] {
  return properties
    .filter((t) => t.predicate === RDF_TYPE && t.objectType !== 'Literal')
    .map((t) => t.object);
}

export function resolveAllSubjects(
  subjectsMap: Map<string, Triple[]>
): string[] {
  return Array.from(subjectsMap.keys());
}

export function sortSubjects(
  subjects: string[],
  getShortUri: (u: string) => string
): string[] {
  const copy = [...subjects];
  return copy.sort((a, b) => getShortUri(a).localeCompare(getShortUri(b)));
}

export function subjectMatchesSearch(
  subject: string,
  subjectsMap: Map<string, Triple[]>,
  query: string,
  getShortUri: (u: string) => string,
  visited = new Set<string>()
): boolean {
  if (!query.trim()) return true;
  if (visited.has(subject)) return false;
  visited.add(subject);
  const q = query.toLowerCase().trim();
  if (subject.toLowerCase().includes(q) || getShortUri(subject).toLowerCase().includes(q)) {
    return true;
  }
  for (const t of subjectsMap.get(subject) || []) {
    if (getShortUri(t.predicate).toLowerCase().includes(q)) return true;
    if (String(t.object).toLowerCase().includes(q)) return true;
    if (t.objectType !== 'Literal' && subjectsMap.has(t.object)) {
      if (subjectMatchesSearch(t.object, subjectsMap, query, getShortUri, visited)) {
        return true;
      }
    }
  }
  return false;
}

export function filterVisibleRoots(
  roots: string[],
  subjectsMap: Map<string, Triple[]>,
  search: string,
  getShortUri: (u: string) => string
): string[] {
  if (!search.trim()) return roots;
  return roots.filter((r) => subjectMatchesSearch(r, subjectsMap, search, getShortUri));
}

export function collectKnownTypeUris(
  triples: Triple[],
  architecture?: { classes?: { uri: string }[] } | null
): string[] {
  const set = new Set<string>([
    URIS.OWL_CLASS,
    URIS.OWL_OP,
    URIS.OWL_DP,
    URIS.OWL_NI,
    URIS.OWL_ANNOTATION_PROP,
    URIS.OWL_ONTOLOGY,
  ]);
  triples.forEach((t) => {
    if (t.predicate === RDF_TYPE && t.objectType !== 'Literal') set.add(t.object);
  });
  architecture?.classes?.forEach((c) => set.add(c.uri));
  return Array.from(set).sort((a, b) => a.localeCompare(b));
}

export function shouldShowTriple(
  triple: Triple,
  viewFilter: ViewFilter,
  subjectUri?: string
): boolean {
  if (viewFilter === 'hide-literals' && triple.objectType === 'Literal') return false;
  if (viewFilter === 'generated-only' && subjectUri && !isGeneratedResource(subjectUri)) {
    return false;
  }
  return true;
}

export function filterRootsByGenerated(roots: string[], mode: ViewFilter): string[] {
  if (mode !== 'generated-only') return roots;
  return roots.filter((r) => isGeneratedResource(r));
}

export function predicateSortOrder(a: string, b: string, sort: SortPreset): number {
  if (sort === 'type-first') {
    const typeA = a.includes('type') ? 0 : 1;
    const typeB = b.includes('type') ? 0 : 1;
    if (typeA !== typeB) return typeA - typeB;
  }
  return a.localeCompare(b);
}

export function findUsedBy(targetUri: string, triples: Triple[]): string[] {
  const users = new Set<string>();
  for (const t of triples) {
    if (t.object === targetUri && t.objectType !== 'Literal') {
      users.add(t.subject);
    }
  }
  return Array.from(users);
}

export function filterUsedByTriples(targetUri: string, triples: Triple[]): Triple[] {
  return triples.filter((t) => t.object === targetUri && t.objectType !== 'Literal');
}

export function countUsages(targetUri: string, triples: Triple[]): number {
  return triples.filter((t) => t.object === targetUri && t.objectType !== 'Literal').length;
}

const TYPE_COLORS: Record<string, string> = {
  Class: 'text-indigo-400',
  NamedIndividual: 'text-emerald-400',
  ObjectProperty: 'text-orange-400',
  DatatypeProperty: 'text-amber-400',
  AnnotationProperty: 'text-yellow-600/90',
  Ontology: 'text-violet-400',
  Restriction: 'text-fuchsia-400',
  Thing: 'text-neutral-300',
};

export function shortTypeName(typeUri: string): string {
  if (!typeUri) return '';
  return typeUri.split(/[/#]/).pop() || typeUri;
}

export function typeColorClass(typeUri: string): string {
  const short = shortTypeName(typeUri);
  return TYPE_COLORS[short] || 'text-sky-400';
}

export function literalColorClass(): string {
  return 'text-neutral-400 italic';
}

export function computeApplicablePredicates(
  subject: string,
  triples: Triple[],
  architecture?: {
    classes?: { uri: string; subClassOfs?: string[] }[];
    properties?: { uri: string; domains?: string[]; ranges?: string[]; label?: string; comment?: string; type?: string }[];
  } | null
): PredicateSuggestion[] {
  const result = new Map<string, PredicateSuggestion>();

  // 1. Ajouter rdf:type manuellement car demandé par l'utilisateur
  result.set(URIS.RDF_TYPE, {
    uri: URIS.RDF_TYPE,
    label: 'type',
    range: URIS.OWL_CLASS,
    source: 'native',
    type: URIS.OWL_OP
  });

  // Trouver le(s) type(s) du sujet
  const types = triples
    .filter(t => t.subject === subject && t.predicate === URIS.RDF_TYPE && t.objectType !== 'Literal')
    .map(t => t.object);

  // Construire la hiérarchie des classes pour trouver les domaines applicables
  const applicableDomains = new Set<string>(types);
  if (architecture?.classes) {
    const classMap = new Map(architecture.classes.map(c => [c.uri, c]));
    let toProcess = [...types];
    while (toProcess.length > 0) {
      const curr = toProcess.pop()!;
      const cls = classMap.get(curr);
      if (cls && cls.subClassOfs) {
        for (const parent of cls.subClassOfs) {
          if (!applicableDomains.has(parent)) {
            applicableDomains.add(parent);
            toProcess.push(parent);
          }
        }
      }
    }
  }

  const hasType = types.length > 0;

  // 2. Propriétés de l'architecture (Schema)
  if (architecture?.properties) {
    for (const p of architecture.properties) {
      if (p.uri === URIS.RDF_TYPE) continue;

      let applies = false;
      if (!hasType) {
        applies = true; // S'il n'a pas de type, toutes les propriétés sont techniquement possibles
      } else if (!p.domains || p.domains.length === 0) {
        applies = true; // Si la propriété n'a pas de domaine, elle s'applique à tout
      } else {
        // S'applique si un de ses domaines fait partie de la hiérarchie des types du sujet
        applies = p.domains.some(d => applicableDomains.has(d));
      }

      if (applies) {
        result.set(p.uri, {
          uri: p.uri,
          domains: p.domains,
          range: p.ranges && p.ranges.length > 0 ? p.ranges[0] : undefined,
          label: p.label,
          comment: p.comment,
          type: p.type,
          source: 'schema'
        });
      }
    }
  }

  // 3. Assertions existantes (si le sujet possède déjà cette propriété, elle doit être dans la liste)
  for (const t of triples) {
    if (t.subject === subject && t.predicate !== URIS.RDF_TYPE) {
      if (!result.has(t.predicate)) {
        result.set(t.predicate, {
          uri: t.predicate,
          source: 'assertion'
        });
      }
    }
  }

  return Array.from(result.values());
}

