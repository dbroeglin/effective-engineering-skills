# Writing documentation

Documentation exists to help someone **use or understand** a product, system, or
process. The reader arrives with a job to do and little patience. Good docs get
them to that job fast and get out of the way.

## Match the document to the reader's intent (Diátaxis)

A reliable way to keep docs useful is to recognize that reader needs fall into
four distinct modes, and to keep each document to **one** mode. Mixing them —
theory in the middle of a task, or a tutorial that stops to catalog every option —
is the most common reason docs feel bloated and hard to follow.

| Mode            | Reader's need         | Shape                                                        |
| --------------- | --------------------- | ----------------------------------------------------------- |
| **Tutorial**    | "Teach me by doing."  | A guided, start-to-finish lesson with a guaranteed result.  |
| **How-to guide**| "Help me do X."       | Focused steps to accomplish one real task.                  |
| **Reference**   | "Let me look it up."  | Dry, complete, consistent facts — params, flags, APIs.      |
| **Explanation** | "Help me understand." | Background, concepts, and the *why* behind the design.      |

If a page is trying to do two of these, split it and cross-link.

## Universal practices for all docs

- **Be task-focused.** Organize around what the reader wants to do, not around how
  the software is built. Titles should name the task ("Deploy to staging"), not the
  feature ("The deployment subsystem").
- **Front-load.** Start each page with what it covers and who it's for. Start each
  section with its key point. Readers scan headings first — make them informative.
- **Show, with examples.** A concrete command, snippet, or screenshot beats a
  paragraph of description. Ensure examples actually run.
- **Keep steps atomic and testable.** One action per numbered step. Tell the reader
  what success looks like ("You should see `Build passed`.").
- **Be consistent.** One term per concept, every time. Switching between "user,"
  "account," and "profile" for the same thing quietly confuses people.
- **Stay accurate.** Wrong docs are worse than none. Note versions/dates where
  behavior changes, and remove or flag anything stale.

## Style conventions

- Address the reader as **"you"** and use the **imperative** for instructions:
  "Run `npm install`," not "The user should run npm install."
- Prefer the **present tense** and the **active voice**.
- Define a term or acronym once, on first use, then use it consistently.
- Keep sentences short. In steps, put the condition before the action: "To cancel,
  press `Esc`" — so the reader can stop reading once it doesn't apply to them.

## Shapes to reuse

**How-to guide**
1. Title states the task.
2. One line on when/why you'd do this, plus prerequisites.
3. Numbered steps, each a single action with its expected result.
4. A short "verify it worked" step.
5. Links to related reference and explanation pages.

**Tutorial**
1. Promise the outcome ("By the end, you'll have a running X.").
2. List prerequisites plainly.
3. Walk the whole path in order; keep the reader succeeding at every step.
4. Minimize digressions — link out for depth instead of explaining inline.
5. End by showing the finished result and suggesting a next step.

## README essentials

A README is the front door. In the first screen, a newcomer should learn:

1. **What it is** — one sentence, plain language, no marketing.
2. **Why it exists / what problem it solves.**
3. **How to install and run it** — the shortest path to a working example.
4. **A minimal usage example.**
5. **Where to go next** — docs, contributing, license, support.

Lead with the fastest route to value. Push exhaustive configuration and edge cases
into linked docs; the README is a launchpad, not a manual.

## Before / after

- Before: *"The system provides functionality that enables the configuration of
  notification preferences to be performed by users."*
- After: *"You can change your notification settings on the **Preferences** page."*

The rewrite names the reader, uses the active voice, and points to the exact place
to act — the three things a doc reader almost always wants.
