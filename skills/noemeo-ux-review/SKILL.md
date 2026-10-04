---
name: noemeo-ux-review
description: Reviews a Noemeo user interface -- a page, component, flow, plugin dialog or design mock -- for usability, accessibility (WCAG 2.2 AA), visual design and honest presentation of AI output, grounded in Noemeo's principles, and returns prioritized, evidence-backed fixes with concrete code suggestions. Use when asked to review, critique or audit UI/UX, check accessibility, evaluate a design or screenshot, or improve how a screen presents AI suggestions.
---

# Noemeo UX review

Procedure for the UX design role (`../../product/ux-design.md` relative
to this skill's base directory). Review only; implementation belongs to
whoever owns the code.

## Step 1: Context

Identify the target (files, route, screenshot, mock) and who uses it to
do what. Read the product's own docs for design rules and platform
constraints (repo `CLAUDE.md`, `docs/`, any style guide); they override
generic guidance below. If you can't see the rendered UI, say so and
review the markup/styles you can read -- don't guess at visuals.

## Step 2: Blockers first (usability heuristics)

Check, citing the heuristic or research for each finding:

- **Findability and hierarchy:** the primary action is obvious; reading
  order matches importance (F-pattern for text-heavy screens); nothing
  important sits where people learn to ignore it (banner blindness).
- **Recognition over recall:** options visible, labels plain, no hidden
  state the person has to remember.
- **Choice and effort:** few choices per step (Hick's law); frequent
  actions are big and close (Fitts's law; targets at least 44x44 px on
  touch, 24x24 minimum per WCAG 2.2).
- **Feedback and recovery:** every action shows its result; destructive
  or AI-applied changes are undoable; errors say what happened and what
  to do.
- **Consistency:** same thing, same name and look everywhere.

## Step 3: Accessibility (WCAG 2.2 AA)

Contrast (4.5:1 text, 3:1 large text and UI parts); full keyboard use
with visible focus not hidden by other content; semantic structure and
labels for assistive tech; no color-only meaning; text resizes to 200%;
`prefers-reduced-motion` respected; target size; no dragging-only
interactions; consistent help; no redundant entry.

## Step 4: AI output, the Noemeo way

- The person stays the author: suggestions are proposals with clear
  accept / edit / dismiss; nothing is applied silently; undo exists.
- Honest confidence: uncertainty and limits are visible; no visual
  styling that makes a guess look like a fact.
- Progress for slow calls: streaming or skeletons rather than a frozen
  screen; long waits say what's happening.
- Reasoning on demand: a short answer first, the "why" one step away.
- Intent before output: the UI makes it easy to add context before
  generation, not only after.
- Clear data handling: what's sent off the device, and when.

## Step 5: Visual design

Typography, color, spacing, hierarchy and motion serving the content.
Distinctive over generic -- call out default-template looks (stock
fonts, generic gradients, three identical cards) when they make the
product forgettable, but treat brand rules as authoritative. Flag
trendy-but-harmful patterns (low-contrast glass effects, tiny text,
parallax that hurts reading). Keep aesthetic opinions labelled as such.

## Step 6: Report

1. **Verdict** -- one or two sentences.
2. **Issues**, most severe first:

   | # | Severity | Where | Problem | Why (evidence) | Fix (with snippet if useful) | Impact x effort |
   |---|---|---|---|---|---|---|

   Severity: `Blocker` (can't complete the task, or an accessibility
   failure), `Major`, `Minor`, `Taste` (aesthetic preference, never
   blocks).
3. **What works** -- keep these.
4. **One big win** -- the single change with the best impact for effort.
5. **Sources** -- links for cited research and WCAG criteria.

Adapted in part from the "UI/UX Designer" agent by Madina Gbotoe
(claude-code-templates, CC BY 4.0).
