# Telegram message organization — 2.6.3

The previous loop could publish a market scenario immediately before an entry, then publish unrelated market reports while that entry was still active. Long repeated explanations made it difficult to identify which signal a follow-up belonged to.

## Behavior

- An entry is a compact card with its direction, persistent signal ID, reference price, stop, two targets, qualification label and Palestine timestamps.
- During an active signal, one routine update per five-minute UTC bucket follows that signal, including at quarter-hour boundaries. Telegram replies point to the acknowledged entry message.
- Without an active signal, the existing 15-minute market summaries and five-minute follow-ups continue. Summary follow-ups reply to their own acknowledged summary.
- A fresh entry, target milestone, exit or emergency replaces unsent routine messages in that five-minute bucket. This does not delete delivered history, suppress emergency events, change signal generation, or skip future update buckets. Repeated calls and restarts cannot create duplicate follow-ups.
- Emergency messages remain first in the delivery queue. When transitions and a new entry share a timestamp, the old signal's milestone/exit precedes the new entry. Each replies to its own parent.
- Reply targets come only from successful delivery acknowledgments. An unknown acknowledgment sends a standalone update with the visible signal ID. Deleted parents do not prevent delivery: Telegram's [ReplyParameters](https://core.telegram.org/bots/api#replyparameters) supports `allow_sending_without_reply` for replies in the same chat.
- Forced directional selections are labeled preliminary/high risk, and cannot claim the full entry gate was met. The strict qualification label follows the existing six-of-seven/core-condition gate. Neither label claims guaranteed success or a measured probability.
- A versioned, deduplicated release notice explains the new layout once.

No strategy, market provider, entry schedule, risk limit, broker execution, credentials, deployment settings or database schema changes are part of this release.

## Example layout

Illustrative formatting only; these are not live prices or a trade recommendation.

```text
🟢 شراء | إشارة ذهب جديدة
المرجع: example-001
ترجيح أولي — غير مضمون، خطر مرتفع

الدخول المرجعي: 2500.00
الوقف المقترح: 2495.00
هدف 1: 2506.00
هدف 2: 2510.00

الشروط المتحققة: 4/7؛ ليست نسبة نجاح.
آخر إغلاق 5د: 15/09 18:00 فلسطين
وقت الإشارة: 15/09 18:01 فلسطين

صلاحية اقتراح الدخول دقيقتان؛ افحص السعر الحالي عند وسيطك.
التحديث كل 5د كردّ على هذه الرسالة. التنفيذ والوقف عند وسيطك.
```

An update names the same signal, reports the latest closed price and its time, the change in gold's price since the original reference, the current model stop and next target. It explicitly remains an update, not a new entry. A data failure reports that the update is unavailable instead of presenting the old quote as current.

## Validation

- All 15 new notification tests pass with mocked Telegram HTTP, SQLite restart persistence, entry/report overlap, active and idle cadence, emergencies, milestones, exit-before-entry ordering, separate reply parents, unavailable data, uncertain/failed acknowledgments, retry behavior, escaping and qualification semantics.
- Existing suite baseline at `1023e95808ff2bdebe0a5748d3dc971242323d7e`: 111 tests, six failure instances across five test methods. The combined suite is 126 tests with the same six failure instances and no additional failures.
- Existing failures concern strategy/context and RSI veto expectations, the former entry schedule, missing standalone scenario emergency detection, and stale-entry rejection after market/news delays (two subcases). They predate this presentation change and remain visible in the suite. This release does not certify the strategy, emergency coverage or trading performance.
- `requests==2.32.5` is used for the final local tests. All HTTP calls in the notification tests are mocked; no sample signals are sent externally.
