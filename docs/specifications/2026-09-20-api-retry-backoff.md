---
title: "API retry backoff"
date: 2026-09-20
type: feat          # feat | fix | refactor | chore
area: "coordinator"
status: implemented       # draft | ready | implemented
refs: []
---

## Background

The ENTSO-E API was out of service for a long period this month. During the outage the integration kept asking for prices at its normal pace, which is wasteful for the service and fills the log with repeated warnings. A long outage should make the integration ask less and less often, and a return to normal should be picked up without manual action. When the user knows the service is back, they should also be able to force an attempt right away instead of waiting for the backoff window.

## Current behavior

The coordinator refreshes hourly. On top of that, every 15-minute slot boundary after 13:00 local time it requests a refresh whenever tomorrow's prices are missing. An outage cannot be told apart from "not published yet" on that path, so during an outage the API is hit roughly four to five times an hour, every day, for as long as the outage lasts. Nothing slows the attempts down after a failure, and a failed fetch for tomorrow does not fail the update, so it never triggers any Home Assistant level retry handling either. There is no way to force a fetch from the device other than reloading the integration.

## Expected behavior

### Backoff

The coordinator keeps a count of consecutive failed fetches. While the count is above zero, the time between requests to ENTSO-E grows with each further failure: 15 minutes after the first failure, then 30 minutes, 1 hour, and 2 hours from there on. The cap is 2 hours.

The backoff window applies to every path that can cause a request. The hourly refresh waits for the window to pass, and the 15-minute slot-boundary refresh is skipped until it has passed. Refreshes that make no request, because prices come from the on-disk store or the in-memory cache, are not held back.

A fetch counts as failed when ENTSO-E cannot be reached, answers with an error, or returns no prices for today. A failed fetch for tomorrow counts as well. A successful request resets the count to zero and restores the normal schedule. So does an answer that tomorrow's prices are not published yet, since the service responded normally.

Authentication failures are not part of the backoff. They keep going through the existing reauthentication flow.

The backoff state is kept in memory only. After a reload or a Home Assistant restart the first refresh is made immediately, and the count starts from zero.

### Retry now button

Each device gets a button entity that forces a refresh immediately, ignoring any backoff window. The result is handled like any other refresh: a success or a "not published yet" answer resets the backoff, and a failure counts as one more consecutive failure and starts the next window from that moment.

The button is available at all times, including while the last update has failed, because that is when it is needed. Pressing it while a refresh is already running does not start a second one.

Being a Home Assistant button entity, it is also usable as an automation action through the standard press action for buttons. No separate integration service is added for it.

Everything else stays as it is. Sensors still receive the cached data at every slot boundary, `fetch_errors` and `last_success` keep their current meaning, and the fetch failed and recovered triggers fire on the same transitions as before.

## Acceptance criteria

1. After a first failed fetch, the next request to ENTSO-E is made no sooner than 15 minutes later.
2. With ENTSO-E unreachable, the gap between consecutive requests doubles from 15 minutes up to 2 hours and stays at 2 hours after that.
3. During an outage after 13:00 local time with tomorrow's prices missing, requests are no longer made at every 15-minute slot boundary but follow the backoff schedule.
4. The first successful request after an outage brings the schedule back to normal, meaning hourly refreshes and 15-minute checks for tomorrow's prices after 13:00.
5. An answer that tomorrow's prices are not published yet also brings the schedule back to normal.
6. During an outage the sensors keep updating at every slot boundary from cached data, and last_success keeps the time of the last completed request.
7. Reloading the integration during an outage makes one request straight away, and the schedule starts again from 15 minutes if it fails.
8. An invalid API key still raises the reauthentication issue immediately and is not delayed by the backoff.
9. The fetch failed trigger fires once when the outage starts and the recovered trigger fires once when it ends, as before.
10. The device shows a retry button that stays available while the last update has failed.
11. Pressing the button during a backoff window makes a request to ENTSO-E immediately, and if ENTSO-E has recovered the entities return to normal and the recovered trigger fires.
12. If the request made by the button fails, the next automatic request follows the backoff schedule counted from that press.
13. An automation that presses the button with the standard button press action has the same effect as pressing it on the device.

## Constraints and edge cases

Out of scope: a user setting for the backoff schedule, keeping the failure count across restarts, and random jitter on the request times.

Today's and tomorrow's fetches share one count, since an outage of the service affects both. When today's fetch fails, tomorrow's is not attempted, as today.

A refresh that is skipped because of the backoff must not clear `fetch_errors`, or the failed and recovered triggers would report a recovery that did not happen.

At day rollover the prices for the new day are promoted from tomorrow's cache. If today's prices are missing after that, the fetch for them still follows the backoff window rather than bypassing it.

The button runs the normal refresh, which still uses the on-disk store and the in-memory cache first. When both today's and tomorrow's prices are already complete no request is needed, so pressing the button then changes nothing.

The button bypasses the backoff window only for the press itself. It does not clear the failure count, so a failed press does not restart the schedule from 15 minutes.
