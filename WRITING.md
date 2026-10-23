# Writing

How text in this repo should sound: commit messages, pull requests, release
notes, README, GUIDE, the website, code comments and words in the app.

Write like the person who made Hanami, telling a friend what changed. Plain
words, short sentences, nothing to impress anyone.

## Don't

- No em dashes. Use a comma, a colon, a full stop or brackets.
- No emoji, in text or as bullets.
- No hype or filler: robust, seamless, comprehensive, enhance, leverage,
  utilize, streamline, elevate, empower, delve, powerful, effortless,
  cutting-edge, "ensure", "in order to", "it's worth noting", "this PR",
  "this commit".
- No "not just X, but Y", and no lists of three for rhythm.
- No bold lead-in on every bullet, and no bullets all the same length and
  shape. Two related facts make a sentence, not a list.
- No headings in anything shorter than a screen.
- No closing line that sums up what was just said.
- Don't say how careful or thorough the work was. Show it in the change.
- Don't explain what the reader can see in the diff.

## Do

- Say what changed for the person using Hanami, then why if it isn't obvious.
- Use the words players use: "the panel", "a game", "the settings file",
  not "the UI component" or "the configuration".
- Be specific: "Epic games you uninstalled no longer show up", not
  "improved Epic detection".
- Keep it short. A small fix gets one line.

## Commits

Follow the history: `type(area): what changed`, lowercase, under 72
characters, no full stop. Types: feat, fix, docs, chore, ci. Add a body only
when the why isn't clear from the subject, a few plain lines at most.

    fix(gog): games without an exe in the registry start again
    feat(controller): pick the buttons that open the panel

## Pull requests

The title reads like a commit subject. The description is a few lines:
what it does and anything that needs trying by hand. No "Summary" or
"Testing" sections; CI already shows whether checks pass.

## Release notes

What a player will notice, one line each, most noticeable first. Leave out
internal changes unless they fix something people ran into.

## Code comments

Only where the code can't say it: why something odd is needed, what a
platform does that you wouldn't guess. Match the comments already there.
