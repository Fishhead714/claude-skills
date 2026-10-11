# reading-mentor

A reading mentor for Claude Code that runs for months, not one chat. It decides
**what to read next** from a map of what you want to understand, and checks
**whether it went in** with a closed-book retelling after each book. All state
lives in plain Markdown files, so every session picks up where the last one
stopped.

## The problem

Asking an AI "what should I read" gets you a confident list, some of it
invented, with no memory of what you read last month. Asking it to summarise
the book gets you the AI's reading instead of your own. This skill narrows the
AI to two jobs and leaves the reading and thinking to you.

## How it works

- **Domain map**: 5-8 areas you care about, each `empty -> intro -> core -> applied`.
  The next book is picked from the emptiest cell.
- **Verified list**: every item says which question it answers and when to skip
  it, and is checked to exist. Free means officially free; everything else is
  "buy or borrow".
- **Finishing a book**: you answer three questions from memory first (claim,
  limits, what you will try); only then does the AI add evidence from the
  text, the strongest objection and links to other authors.
- **Tagged notes**: every line is `[quote]`, `[paraphrase]`, `[AI]` or `[me]`.
- **Critics on purpose**: after two mainstream books in a domain, the next one
  argues against them.

Details and reasoning: [METHOD.md](METHOD.md).

## Use

1. Install the plugin, or copy this folder into `~/.claude/skills/reading-mentor/`.
2. Optionally set `READING_PATH_DIR` (default: `./reading-path`).
3. Say "start my reading path". The mentor copies `templates/`, asks one
   question per domain as a baseline, and recommends the first book.
4. Afterwards: "I'm on chapter 3 of X", "I finished X", "what next",
   "show my reading map", "monthly review". Chinese phrasing works too.

`examples/` shows the files after a few weeks, for a fictional reader with
fictional books.

## E-reader progress and highlights (optional)

If your reading app offers an official, user-authorised way to read your own
progress and highlights, the mentor can use it instead of asking you. For
WeChat Reading (微信读书), install Tencent's official skill
(`npx skills add Tencent/WeChatReading`) and get your own key at
<https://weread.qq.com/r/weread-skills>. This project ships no API client and
is not affiliated with Tencent; the app's own terms apply. Keep your key
local and never commit it.

## Limits

- It is a prompt-only skill: quality depends on the model following the order
  "you first, AI second". The files make drift visible but do not prevent it.
- It checks whether a book exists; it does not judge whether a book is good.
- No scheduling or reminders. You come back when you have read something.

## Credits

See the end of [METHOD.md](METHOD.md). The analysis questions are adapted from a
widely shared prompt whose author is unknown; if you know the source, please
open an issue.

Part of [claude-skills](../../../../). MIT — see the repository root [`LICENSE`](../../../../LICENSE).
