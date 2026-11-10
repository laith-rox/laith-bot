# Experimental Laith gold calendar: operator checklist

Scope: **Railway `laith-bot` only**, Telegram `@LaithGoldSignalsBot`, manual signals only. Do not modify `laith-v4-worker`, Single, or `live-signal-relay`. Do not merge PR #40 as part of activation.

## Current fail-closed blocker

`v4_runtime.py` requires **both** `V4_VERIFIED_BROKER_SESSIONS` and `V4_VERIFIED_NEWS_EVENTS`. A missing or malformed value means **no XAUUSD entry**. `verified_calendar_sessions=0 verified_news_events=0` is diagnostic, not proof of a closed market; an empty *verified* news calendar is allowed, but an absent news calendar is not.

## Before configuring any live calendar

1. Obtain the **actual XAUUSD session hours for this user's JustMarkets account/server** from an authoritative broker terminal specification or verified broker notice, including holiday/maintenance exceptions. Do not substitute generic gold market hours or assume a timezone.
2. Convert only confirmed session openings/closings to **timezone-aware ISO-8601 timestamps**. Cover the relevant dates; do not fabricate future sessions. The parser rejects intervals longer than 24 hours, Saturday UTC sessions and overlaps.
3. Obtain a current economic-event calendar from a trusted source, with release times, relevant currencies and any known changes. Independently confirm that a calendar containing zero events really is verified for the intended period. Never invent an empty calendar merely to bypass the gate.
4. Prepare JSON values in Railway **only for service `laith-bot`**. The examples below show *schema only* and use placeholder values: **DO NOT deploy them**.

```json
{"verified":true,"sessions":[{"open":"<BROKER_VERIFIED_UTC_START>","close":"<BROKER_VERIFIED_UTC_END>"}]}
```

```json
{"verified":true,"events":[{"id":"<SOURCE_EVENT_ID>","title":"<VERIFIED_EVENT_TITLE>","release_at":"<VERIFIED_UTC_RELEASE_TIME>"}]}
```

Use `{"verified":true,"events":[]}` **only when a source has positively verified that no relevant events exist in the covered interval**. The current schema does not encode coverage or expiry, so the operator must refresh it and must not treat an old empty calendar as ongoing verification.

## Deployment and acceptance

- Confirm CI for the exact Git commit. Deploy **only** `laith-bot`; Railway has unrelated staged changes, so never accept the whole environment patch.
- Keep existing `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TWELVE_DATA_API_KEY` and `/data` mount; the experimental DB is `/data/laith_v4_experiment.db`, separate from legacy `/data/laith.db`.
- Check deployment `SUCCESS`, startup logs and `verified_calendar_sessions`/`verified_news_events`; check the verified session gate state and news gate separately.
- Test a **closed session**, a **news blackout**, a **stale price**, a **duplicate slot**, and a **fresh eligible session** before trusting Telegram entry messages. Verify Telegram delivery, not merely message generation. Never place a broker order from this service.
- If any broker/news source is unavailable, leave gold entries blocked and report the exact missing source. BTC Telegram alerts are independent and do not validate gold readiness.
