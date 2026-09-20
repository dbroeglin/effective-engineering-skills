---
name: effective-writing
description: Write clear, effective prose that respects the reader's time, for documentation, corporate and business documents, and social posts. Use this skill whenever you draft or edit writing meant for people — technical documentation, READMEs, guides, corporate memos, reports, proposals, business cases, executive summaries, business emails, announcements, release notes, and LinkedIn or other social posts. Apply it even when the user doesn't explicitly ask to improve the writing; any time the deliverable is prose a person will read. Skip it for code, commit messages, data transforms, and config files.
license: Apache-2.0
---

# Effective Writing

Most workplace writing wastes the reader's time. It buries the point, hedges,
leans on jargon, and makes the reader do the work the writer should have done.
This skill helps you write the opposite: prose that gets to the point, reads
easily, and moves the reader to understand or act.

The guidance here is a synthesis of long-established, publicly available writing
practice (plain-language standards, journalism, technical-writing frameworks, and
business-communication conventions). See `references/sources.md` for attributions.

## How to use this skill

1. **Name the job.** Who is the reader, and what should they know, feel, or do
   after reading? Everything else follows from this.
2. **Pick the format** and read the matching guide (see the router below). Each
   format has its own shape and conventions.
3. **Apply the core principles** while drafting.
4. **Self-edit** with the checklist before you hand the writing back.

Don't lecture the user about writing or explain these principles to them unless
they ask — just produce writing that reflects them.

## Core principles

These apply to almost everything. They're a way of thinking, not a rulebook —
understand *why* each matters so you can use judgment when they conflict.

1. **Start from the reader, not yourself.** Picture a specific, busy person. Write
   what *they* need to know, in the order *they* need it — not the order you
   discovered it or the order that flatters your effort.

2. **Lead with the point.** Put the conclusion, answer, or ask first, then support
   it (BLUF / inverted pyramid). Readers skim; if they read only the first line or
   two, they should still get the essential message. Never make them dig for it.

3. **Respect the reader's time.** Treat their attention as more valuable than your
   own convenience. If a sentence doesn't help the reader, cut it. Shorter is
   usually better — but clarity beats brevity when they conflict.

4. **Prefer plain words and the active voice.** "Use" beats "utilize"; "help"
   beats "facilitate." "We shipped it" beats "it was shipped." Active voice names
   who does what, which is clearer and shorter. Use passive deliberately, not by
   default (e.g., when the actor is unknown or irrelevant).

5. **One idea per sentence; keep sentences and paragraphs short.** Long,
   multi-clause sentences hide the point. Break them up. A paragraph should carry
   one thought and open with its most important sentence.

6. **Make it scannable.** Real readers scan before they read. Use meaningful
   headings, short paragraphs, and lists for parallel items. Front-load each
   heading and paragraph with the words that tell the reader what's there.

7. **Cut the fluff.** Delete throat-clearing ("It is important to note that…"),
   empty intensifiers ("very," "really"), hedges ("basically," "sort of"), and
   redundancy ("end result," "future plans"). Define jargon or avoid it; never use
   it to sound impressive.

8. **Be concrete and specific.** Replace abstractions with facts, numbers,
   examples, and names. "Improved performance" is weak; "cut load time from 4s to
   1.2s" is strong. Specifics build trust; vagueness erodes it.

9. **Revise deliberately.** First drafts are for you; revisions are for the reader.
   After drafting, cut roughly 10-20% of the words. Read it aloud (or imagine it) —
   if you stumble, the reader will too.

10. **Match tone and length to the medium.** A reference doc, a board memo, and a
    LinkedIn post reward very different voices and lengths. Adapt; don't apply one
    register everywhere.

## Choose the format guide

Read the reference file that fits the task. When a piece spans formats (e.g., a
release note announced on LinkedIn), read both and lead with the reader's primary
context.

| If you're writing…                                                        | Read                        |
| ------------------------------------------------------------------------- | --------------------------- |
| Docs, READMEs, guides, tutorials, API/reference material, help content    | `references/documentation.md` |
| Memos, reports, proposals, business cases, exec summaries, business email | `references/corporate.md`   |
| LinkedIn posts and other professional social content                      | `references/linkedin.md`    |

For attributions and further reading: `references/sources.md`.

## Self-edit checklist

Run this pass before delivering. It catches the most common failures.

- **Point first?** Does the opening line carry the main message or ask?
- **Reader-shaped?** Is it ordered by what the reader needs, not what you wrote first?
- **Every sentence earns its place?** Cut anything that doesn't inform or move the reader.
- **Active and plain?** Swap passive-by-default and fancy words for direct ones.
- **Scannable?** Headings, short paragraphs, and lists where they help.
- **Concrete?** Abstractions replaced with specifics, numbers, examples.
- **No fluff?** Throat-clearing, hedges, empty intensifiers, and redundancy removed.
- **Tight?** Try cutting 10-20% of the words. Did meaning survive? Usually yes.
- **Right register?** Tone and length fit the medium and audience.

## Before / after

Short, illustrative rewrites. Notice what each change buys the reader.

**Bury vs. lead (and trim):**
- Before: *"In order to ensure that we are able to meet the project deadline that
  has been set, it is important that all team members submit their status updates
  in a timely fashion."*
- After: *"Submit your status update by Thursday so we can hit the deadline."*

**Passive and vague vs. active and concrete:**
- Before: *"It was decided that the rollout would be delayed due to issues that
  were encountered."*
- After: *"We delayed the rollout a week to fix the login bug."*

**Jargon vs. meaning:**
- Before: *"We leverage cross-functional synergies to operationalize best-in-class
  solutions."*
- After: *"We combine our teams' strengths to ship products that work."*

**Throat-clearing vs. getting on with it:**
- Before: *"It is important to note that, at this point in time, the feature is not
  currently available."*
- After: *"The feature isn't available yet."*

## Common traps

- **Writing to impress instead of to communicate.** Big words and long sentences
  signal effort but cost clarity. Confidence reads as simplicity.
- **Front-loading context nobody asked for.** Background belongs after the point,
  or in a linked appendix — not before it.
- **Hedging everything.** Endless qualifiers ("might," "perhaps," "in some cases")
  drain authority. State things plainly; qualify only where it genuinely matters.
- **One draft.** The gap between a first draft and a revised one is where most of
  the quality lives. Always take the editing pass.
