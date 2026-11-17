---
name: noemeo-graphic-design
description: Creates distinctive visual designs for a Noemeo website or marketing page -- visual identity (palette, type, imagery style, design tokens), several different art directions to choose from, and the chosen one built in the site's HTML and CSS on a branch -- with real, licensed imagery only, never fake photos or invented product sessions, and the accessibility floor kept. Use when asked to design, redesign or restyle a website, landing or pricing page, define a visual identity or style guide, choose imagery, write a brief for a logo or artwork, or critique a page's look. Not for usability or accessibility review (noemeo-ux-review), copy (noemeo-go-to-market), or product UI code.
---

# Noemeo graphic design

Procedure for the graphic design role
(`../../roles/product/graphic-design.md` relative to this skill's base
directory). Read its **Hard limits** before any step. The owner chooses
the direction and merges; UX design reviews before that.

## Step 1: Read the ground

- The website repo's `CLAUDE.md` or README: how it's built, how it
  publishes (a site served from its default branch publishes on merge),
  and which pages or scripts are off limits.
- The product's vision doc and any brand or design docs; go-to-market's
  messaging brief and claims table, if there is one.
- The current site, rendered: screenshots at phone and desktop widths,
  if a browser tool is available. If you can't see it rendered, say so.
- What real imagery exists: the owner's own photographs or artwork,
  real product captures, and their rights.

A source that's missing is reported, not guessed.

## Step 2: Directions

Offer two or three directions that differ in kind, not in shade. For
each:

- **Idea:** one sentence on what it says about the product, and why it
  belongs to this product's subject and audience.
- **Palette** (hex values, with contrast ratios for text pairs),
  **type** (families, licences, a scale), **composition** (grid,
  rhythm, what the eye meets first), **imagery** (which real images,
  how they're treated, what's illustration) and **motion**, if any.
- **A sketch:** a small static mock of the key screen, as a file
  outside every repo, or a description precise enough to judge.
- **Risks:** what it costs in legibility, performance or maintenance.

Avoid the generic default look of current web templates. If the
`frontend-design` skill is available, use it for the build-quality
side of a distinctive look. Stop here for the owner to choose, unless
the request already chose.

## Step 3: Build, on a branch

- Only in the website's source, only when asked, on a new branch from
  its default branch, in its own worktree if another role (such as
  go-to-market with copy) works on the same site. Never commit to a
  branch that publishes; push only with the request's approval.
- Put the identity into tokens first (CSS custom properties for color,
  type, spacing), then pages. Respect the site's existing build: no new
  framework or build step without the owner's approval.
- Style around payment, account and analytics scripts; never change
  them.
- Responsive from phone width up; `prefers-reduced-motion` honoured;
  visible focus; contrast checked by computing ratios, not by eye.
- Copy stays as go-to-market wrote it. If the layout needs different
  words, propose them to go-to-market.

## Step 4: Imagery and assets

- Follow the role's **Nothing fake** limit; it lists what may and may
  not be done to photographs and captures.
- Real photographs and artwork only from the owner or a licensed
  source. Record each in an asset list beside the files: file, source,
  licence, who is in it and their permission where a person is
  recognisable.
- Product captures come from real runs on real input. Record in the
  asset list what run each came from and what was done to it (crop,
  frame, blur).
- A logo, original artwork or new photography: write a brief (purpose,
  mood, sizes and formats, references with their sources, what to
  avoid) for the owner or an artist.

## Step 5: Check and hand off

- Look at the rendered result at phone and desktop widths, if a browser
  tool is available, and compare it with the chosen direction.
- Run the repo's checks, if it has any (HTML validation, link checks).
- Ship the branch through the repo's normal path (`noemeo-ship` where
  it applies), so `noemeo-code-reviewer` checks the diff, including
  that payment, account and analytics scripts are untouched.
- Hand it to UX design in a fresh context: the `noemeo-ux-designer`
  agent, or another session. Never run `noemeo-ux-review` on your own
  design and call it reviewed.
- Fix what UX blocks on evidence; argue taste with reasons, and take
  what the evidence doesn't settle to the owner. Any edit after a
  review goes back for another, so the owner merges only a reviewed
  head.

## Step 6: Report

- The direction chosen and why; the branch and the files changed.
- Screenshots or the files to look at, and what wasn't seen rendered.
- The asset list, with anything whose rights are unclear flagged.
- UX review's findings and what was done about them.
- What the owner does next: choose, supply images, commission a brief,
  merge (which publishes, if the site serves its default branch).
