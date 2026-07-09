# Series vs. cluster: don't overload a name for two different mechanisms

**Decision** (noemeo-roles#2, resolved 2026-07-09): when checking a
newly-added single image for redundancy against a project's existing
images, match against **series** (topical/temporal grouping, matched via
classification/narrative signals + timestamp proximity, system-suggested
but user-mergeable/splittable) -- not **cluster** (Tier 0a's existing,
narrower concept: perceptual-hash near-duplicate/burst detection).

## Why this came up

The proposal that prompted this ("check similarity with existing
clusters... implies the cluster needs metadata describing the timestamp
distribution and the topics") described a genuinely different mechanism
than what "cluster" already meant in `noemeo-backend/docs/architecture.md`
(Tier 0a). Perceptual hashing catches near-identical frames from a burst;
it would not catch two shots of the same waterfall five minutes apart from
different angles, which needs semantic/topical similarity instead.
Reusing "cluster" for both would have made the term ambiguous.

## The general lesson

This is the same failure mode `image_worth_scorer` was renamed to avoid
(`tier1_scoring` / "potential scoring" read ambiguously, and risked
conflating with the product's internal "pixels vs. intent" jargon). The
pattern: **when a new requirement resembles an existing concept but uses
a different underlying mechanism, give it a different name rather than
extending the existing term's meaning.** Cheap to do while the codebase is
young; expensive to unwind once "cluster" has been used both ways in
several places.

**How to apply:** before reusing an existing term for a new mechanism,
check whether the *implementation* is actually the same, not just whether
the *user-facing effect* rhymes. If the mechanism differs, the name
should too, even if it means introducing new vocabulary.
