---
title: "Fetch status diagnostic sensors"
date: 2026-09-20
type: feat          # feat | fix | refactor | chore
area: "diagnostic sensors"
status: implemented       # draft | ready | implemented
refs: [2026-09-20-fetch-failed-trigger]
---

## Background

When price fetching from ENTSO-E fails, the Home Assistant UI shows very little. A failure to fetch today's prices makes the price entities unavailable, without saying why. A failure to fetch tomorrow's prices is only a log warning, and every entity keeps working, so the user learns about it only when tomorrow's prices are missing.

The "Fetch failed and recovered triggers" specification adds automation triggers for these transitions. Triggers fire on changes only, so they cannot answer the questions a user asks when looking at the device page or building a dashboard: is fetching failing right now, why, and how old is the data I am looking at. This specification adds diagnostic entities that answer those questions, using the same recorded failure state, and a state-based counterpart of the existing trigger for tomorrow's prices becoming available.

## Current behavior

The device has diagnostic sensors for VAT, transfer fee and price resolution. None of them describes the state of fetching. All price entities become unavailable when today's fetch fails. The time of the last successful fetch is not shown anywhere and is lost on restart.

## Expected behavior

The Electricity Price device gains three diagnostic entities, shown in the device's diagnostic section: "Last successful fetch", "Price fetch failing" and "Tomorrow prices available".

"Last successful fetch" is a timestamp sensor. Its value is the time of the last request to ENTSO-E that completed successfully, shown in the user's timezone by Home Assistant. A "not published yet" answer counts as completed successfully, since ENTSO-E responded normally. The value survives restarts and reloads. Before the first successful request it is unknown.

"Price fetch failing" is a binary sensor with the problem device class. It is on while either today's or tomorrow's fetch is failing and off otherwise. While it is on, its attributes carry the failing scope ("today" or "tomorrow") and the error text of the failure, the same text the failed trigger provides. While it is off, both attributes are empty.

"Tomorrow prices available" is a binary sensor. It is on while a complete set of tomorrow's prices is available and off otherwise, using the same completeness rule as the existing "Tomorrow prices available" trigger. It turns on at the same moment that trigger fires. At the change of day, when tomorrow's prices become today's, it turns off until the next day's prices have been fetched.

"Last successful fetch" and "Price fetch failing" describe fetching itself, so they stay available while price fetching is failing. That includes the outage where the price entities are unavailable, since that is when they are most useful. "Price fetch failing" changes state at the same moment the failed and recovered triggers fire, and shows the same scope. "Tomorrow prices available" describes the price data, so it is unavailable whenever the price entities are.

The entity names are translated in English and Finnish.

## Acceptance criteria

1. The Electricity Price device page lists "Last successful fetch", "Price fetch failing" and "Tomorrow prices available" in the diagnostic section, in English and in Finnish.
2. After a successful fetch, "Last successful fetch" shows the time of that fetch, and "Price fetch failing" is off with empty attributes.
3. When ENTSO-E is unreachable while today's prices are being fetched, "Price fetch failing" turns on with scope "today" and the error text in its attributes, while it and "Last successful fetch" stay available and the price entities and "Tomorrow prices available" become unavailable.
4. When ENTSO-E is unreachable while only tomorrow's prices need fetching, "Price fetch failing" turns on with scope "tomorrow" and the error text in its attributes, and the price entities stay available.
5. During a failure, "Last successful fetch" keeps the time of the last fetch that succeeded and does not advance.
6. When a later fetch succeeds, "Price fetch failing" turns off with empty attributes, and "Last successful fetch" updates.
7. ENTSO-E reporting that tomorrow's prices are not published yet does not turn "Price fetch failing" on.
8. After a restart of Home Assistant, "Last successful fetch" shows the time it had before the restart until a new fetch succeeds.
9. "Price fetch failing" changes state at the same time as the failed and recovered triggers, with the same scope.
10. Before tomorrow's prices are published, "Tomorrow prices available" is off. Once a complete set has been fetched it turns on, at the same time the "Tomorrow prices available" trigger fires.
11. At the change of day, "Tomorrow prices available" turns off, and turns on again when the next day's prices have been fetched.
12. The user documentation lists all three entities and what their values and attributes mean.

## Constraints and edge cases

The entities read the failure state the coordinator records for the failed and recovered triggers. That state is shared and not implemented twice, so the triggers specification is a dependency and its work comes first.

"Last successful fetch" advances on any successful request, including when only one of today's and tomorrow's fetches succeeds. It therefore does not prove that both are current. "Price fetch failing" is the indicator for that. The time is kept in the coordinator's persisted data.

If both scopes could be failing at once, the attributes show the most recent failure. In practice tomorrow's fetch is not attempted while today's is failing.

The error text is an attribute and not the state, because Home Assistant does not store a state longer than 255 characters and error texts have no fixed length.

Behaviour when the integration cannot be set up at all is unchanged, and the entities do not exist in that case.

Out of scope: a separate sensor for the error text, a consecutive failure counter, a timestamp for when tomorrow's prices were published, notifications or repair issues, and changes to fetch retry behaviour.
