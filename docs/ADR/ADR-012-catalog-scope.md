# ADR-012 — Catalog Scope: what counts as "a drama in the archive"

- **Status:** Accepted
- **Date:** 2026-09-28
- **Related:** AIRFLOW_DAGS §4/§9 구현 현황, DATA_MODEL `drama.status`, V16 `hidden_reason`, README 진행 상태

## Context

Wikidata, the only open catalog source, files variety and reality programmes under
the same "television series" class as dramas, has no clear "aired yet" flag, and
lists every channel and platform a title touched. Left as-is the archive showed
《런닝맨》 next to 《도깨비》, listed dramas that had not aired, and duplicated the
same title under an OTT that merely re-streams it.

The product owner decided (2026-09-28):

1. only dramas — no variety, reality, talk, news, lists, episodes of magazines;
2. only titles that have started airing;
3. for now only **KBS, MBC, SBS, tvN, JTBC**, started 2006 or later — platforms
   mostly re-run what those channels aired, so they add duplicates rather than
   titles. Widen when asked.

## Decision

Scope is enforced **after publish, as a reversible status**, never by deleting
canonical rows or by filtering at the source:

```text
drama.status = 'HIDDEN' + drama.hidden_reason ∈ { not_a_drama | foreign | upcoming | out_of_scope }
```

- `program_kind` (classes, genres, kowiki categories) decides drama vs not at
  discovery, in the parser and in the quality gate; the publish DAG hides rows the
  discovery run excludes (`not_a_drama`, `foreign`) and restores them when they
  return to the manifest.
- `hide_upcoming`: start_date > today → `upcoming`; restored the day it airs.
- `apply_scope`: broadcaster not in `DRAMAMEMORY_SCOPE_BROADCASTERS` (or unknown),
  or start_date before `DRAMAMEMORY_SCOPE_YEAR_FROM` (2006) → `out_of_scope`;
  restored when the scope widens or a channel is inferred.
- Rows hidden by hand (`hidden_reason IS NULL`) are never touched automatically.
- Every projection (search documents, embeddings, Neo4j, sitemap, API) reads
  `status = 'PUBLISHED'` only, so hiding a row removes it everywhere on the next
  asset run; provenance, credits and identity mappings stay intact.

## Consequences

- 2026-09-28 run: 2,989 canonical dramas → 1,924 published; hidden 861 out of
  scope (channel or pre-2006), 190 not a drama, 14 upcoming. Retrieval quality rose on both golden sets
  (fewer same-title distractors).
- Netflix/Disney+ originals with no network run are hidden too. That is accepted
  for now and is the first thing to revisit.
- The Wikidata parser prefers the original network when P449 lists a network and
  a platform, so a KBS drama streamed on Netflix files under KBS.

## Removal condition

- Widening channels needs no code: set the env, the next publish run restores
  the rows. If the product later wants platform originals, add their codes.
- If the source mix changes so that a per-source classifier is needed (e.g. a
  broadcaster feed with its own taxonomy), `program_kind` moves behind the parser
  interface; the status/reason mechanism stays.
