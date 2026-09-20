---
title: "Fetch failed and recovered triggers"
date: 2026-09-20
type: feat          # feat | fix | refactor | chore
area: "device triggers"
status: implemented       # draft | ready | implemented
refs: []
---

## Background

The integration fetches day-ahead prices from ENTSO-E and already offers device triggers for price events such as tomorrow's prices becoming available. There is no way to react to the opposite case: the fetch failing, or to the moment it starts working again. Users who schedule devices by price cannot be notified, or switch to a fallback plan and back, when ENTSO-E is unreachable or rejects the request.

Failures also differ in how visible they are today. A failed fetch for today's prices makes the entities unavailable. A failed fetch for tomorrow's prices is only written to the log as a warning, and the entities keep working with today's data, so nothing in the Home Assistant UI reveals it.

## Expected behavior

The Electricity Price device offers two new automation triggers next to the existing device triggers: "Price fetch failed" and "Price fetch recovered". Neither has configuration fields.

"Price fetch failed" fires once when price fetching goes from healthy to failing. It does not fire again while the failure continues, however many retries fail.

"Price fetch recovered" fires once when fetching goes from failing back to healthy. It fires only for a failure that the automation has observed since it was attached, so attaching or reloading never produces a recovery on its own. After a recovery, the next healthy-to-failing transition fires the failed trigger again.

Today's prices and tomorrow's prices are tracked independently, and both triggers report which one changed. A failure to fetch today's prices, including a rejected API key, fires the failed trigger with scope "today". A failure to fetch tomorrow's prices fires it with scope "tomorrow", even though the integration keeps working with today's data. Recovery is reported with the same scope as the failure it ends. If both are failing, each fires its own transition once. In practice tomorrow's fetch is not attempted while today's is failing, so only "today" fires until today's fetch recovers.

The failed trigger's data contains the scope ("today" or "tomorrow") and the error text describing the failure. The recovered trigger's data contains the scope. The trigger descriptions read like the existing triggers, for example "electricity_price fetch failed (tomorrow)" and "electricity_price fetch recovered (tomorrow)".

ENTSO-E answering that tomorrow's prices are not published yet is not a failure. Neither is receiving fewer slots than a complete day for tomorrow. For today's prices the picture differs: connection problems, unparseable responses, non-success HTTP statuses and authentication errors count, and so does ENTSO-E returning no prices for today, since the price entities become unavailable in that case too.

For tomorrow's scope, "recovered" means the fetch no longer fails. It can therefore fire when ENTSO-E answers that tomorrow's prices are not published yet, before any prices are available. The existing "tomorrow's prices available" trigger is the one to use for the prices actually arriving.

Both trigger names are translated in English and Finnish.

## Acceptance criteria

1. In the automation editor, the Electricity Price device lists "Price fetch failed" and "Price fetch recovered" triggers, each with no extra fields, in English and in Finnish.
2. When ENTSO-E is unreachable while today's prices are being fetched, an automation using the failed trigger runs once, with scope "today" and a non-empty error text.
3. When ENTSO-E is unreachable while only tomorrow's prices need fetching, the automation runs once, with scope "tomorrow", and the price entities stay available with today's data.
4. While the same failure continues across further refresh attempts, the failed automation does not run again.
5. When ENTSO-E becomes reachable again after a failure the automation has seen, an automation using the recovered trigger runs once, with the scope of the failure that ended.
6. After a recovery, a new failure runs the failed automation again.
7. An invalid API key on today's fetch runs the failed automation with scope "today" and an error text mentioning the invalid key, in addition to the existing re-authentication prompt.
8. ENTSO-E reporting that tomorrow's prices are not yet available, before they are published, does not run the failed automation.
9. Reloading the integration or restarting Home Assistant while a failure is ongoing runs neither automation on startup. The recovered automation runs only if a failure has been observed since the reload and then ends.
10. The user documentation lists both triggers and their trigger data.
11. When ENTSO-E returns no prices for today, the failed automation runs once with scope "today" and an error text saying no data was returned.

## Constraints and edge cases

Both triggers follow the behavior of the existing device triggers: they track state from the moment the automation is attached, and an already-failing state at that moment is not reported. The failed trigger fires on the next healthy-to-failing transition. The recovered trigger fires only after a failure was seen.

Recovery for tomorrow's scope counts any fetch that no longer fails, including a "not yet published" response, and reuse of tomorrow's prices that are already stored or cached. Recovery for today's scope is a successful fetch, or today's prices served from the stored or cached copy.

The coordinator has to record tomorrow's fetch failure and its error text in a way listeners can read, because that failure is currently swallowed and the update counts as a success. The exact carrier, for example a field on the price data, is left to the implementation. Both triggers share this recorded state.

Out of scope: a required number of consecutive failures before firing, retry backoff, repair issues or persistent notifications, and changes to how often fetches are retried.
