# AGENTS.md

## Design Philosophy

**Avoid unnecessary secondary labels and descriptions. Let the layout do the explaining.**

Every extra word on screen is a tax. If a heading, icon, spacing, or border already
communicates something, do not also say it in text. When in doubt, delete the label
and see if the UI still reads.

## The Rule

Before adding any text element, ask:
1. Does the layout already convey this? → cut the text.
2. Is it restating the heading? → cut it.
3. Is it a caption for something self-evident? → cut it.
4. Is it a sentence where 2 words would do? → shorten it.

If you remove a label and the UI becomes ambiguous, put back the *smallest*
possible affordance — a heading change, a divider, an icon, a placeholder —
before falling back to prose.

## Labels

- No redundant section headings. One heading per region, not per component.
- No label above a field when a placeholder or the value itself is unambiguous.
- No "Description:" / "Details:" / "Info:" prefixes. Just show the thing.
- No helper text under an input unless it prevents a real mistake.
- Buttons say the verb: "Save", "Invite", not "Submit" or "Click here to save".
- No icon + text + tooltip all saying the same word. Pick one.

## Descriptions

- Kill the subtitle under a page title unless it adds facts.
- Kill card body copy that repeats the card title.
- Kill "empty state" paragraphs. One short line, then the action.
- Metadata should be scannable tokens, not sentences: `3 files · 2 min ago`, not
  "This folder contains 3 files and was last modified 2 minutes ago."
- No em dashes chaining three clauses in a subtitle. Split or cut.

## Layout Does The Work

- **Hierarchy:** size, weight, and position first. Color second. Text last.
- **Grouping:** proximity and whitespace group things. You rarely need a box or a
  divider to do it. Never use both a border AND a background AND a heading.
- **Separation:** prefer a spacing jump over a horizontal rule.
- **Alignment:** a shared left edge is the strongest label there is.
- **Repetition:** if a pattern repeats 5+ times, the pattern is the label — drop
  per-item headings.

## Spacing

- Use a scale: 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64. Nothing off-scale.
- Space *between* groups > space *within* groups. Make the ratio obvious.
- Generous padding beats borders. Let the content breathe instead of framing it.
- Tighten dense data; loosen marketing and empty states.

## Color

- One accent. Neutrals do the rest.
- Background layers, not outlines: `bg`, `bg-subtle`, `bg-elevated`.
- Text: 3 tiers max — primary, secondary, muted. Most UI needs 2.
- Never rely on color alone to carry meaning.
- Gradients: subtle, low-saturation, or none. No rainbow buttons.

## Typography

- 2 font sizes for body, 1 for headings scale. Don't invent sizes.
- Line height 1.4–1.6 body, 1.1–1.25 headings.
- Max line length 65–75 characters.
- Uppercase micro-labels: use sparingly, with tracking, and only for one tier.
- Tabular numerals for anything in a column or that updates.
- Truncate, don't wrap, in dense rows. Wrap in prose.

## Components

- Border radius: one value for controls, one for containers. Consistent.
- Borders: 1px, low contrast, or none at all. Hairlines only where needed.
- Shadows: one soft elevation token, not five ad-hoc ones.
- Icons: one set, one stroke width, one size scale. Icons support text, not replace it
  — except in universally understood cases (search, close, menu).
- States: default / hover / active / focus / disabled / loading. All six, every
  interactive element. Focus rings must be visible.

## Motion

- 120–200ms for micro, 200–300ms for transitions. Nothing slower.
- Ease-out on enter, ease-in on exit.
- Animate `transform` and `opacity` only.
- Respect `prefers-reduced-motion`.
- Motion clarifies cause and effect — it is not decoration.

## Empty, Loading, Error

- Empty: one line + one action. No illustration unless it earns its space.
- Loading: skeleton that matches the final layout, not a centered spinner.
- Error: what happened + what to do. No stack traces, no "Oops!".
- Never show a blank screen. Never show "No data" with no next step.

## Forms

- Label or placeholder, not both.
- Validate on blur, not on every keystroke.
- Inline error replaces helper text in the same slot. Don't stack them.
- Disable the submit button's *reason*, not the button — or explain why.
- One column. Group by meaning. Short labels, short inputs.

## Accessibility

- Contrast 4.5:1 body, 3:1 large text and UI borders.
- Every control reachable and operable by keyboard.
- `aria-label` only where the visual label is absent — don't duplicate visible text.
- Semantic elements over div soup.
- Hit targets 44x44 minimum.

## Anti-Patterns — Reject On Sight

- A card with a title, a subtitle, an icon, a tag, and a description.
- Section header + subheader + helper text all restating each other.
- Icon + label + tooltip saying the same thing.
- Gray caption under every single input.
- "Welcome back! Here's an overview of your..." greeting blocks.
- Emoji as bullet points.
- Borders AND shadows AND backgrounds on the same element.
- Centered text for anything longer than two lines.
- Placeholder text as the only label.
- Purple-to-blue gradient on everything.
- Three different radii, four different grays, five font sizes.
- Tooltips that just repeat the button label.

## Self-Check Before Finishing

1. Read every string on screen. Delete any that a user could infer from layout.
2. Count your grays, radii, and font sizes. Collapse duplicates.
3. Check the 3 hardest states: empty, loading, error.
4. Tab through it. Can you see focus everywhere?
5. Squint. Is the hierarchy still obvious with the text blurred? If not, fix the
   layout before adding words back.
6. Confirm spacing is on-scale and group gaps > internal gaps.

## When You Change Existing UI

Match the existing system before inventing. If the codebase already has tokens,
radii, and spacing scales, use them. Only introduce a new pattern if the old one
genuinely cannot express the requirement — and say so in the commit message.