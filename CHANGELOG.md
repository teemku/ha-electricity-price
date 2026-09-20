# Changelog

All notable changes to this project are documented here.
This file is generated — do not edit it manually.

## [1.1.0] - 2026-09-20

### Added

- The integration now waits longer between attempts while ENTSO-E is failing: 15 minutes, 30 minutes, 1 hour, and then every 2 hours for as long as the outage lasts. It returns to the normal schedule after the first successful request, or after an answer that tomorrow's prices are not published yet.
- A "Retry price fetch" button on the device page makes a request immediately, ignoring the waiting period. It can also be pressed from automations with the standard button press action.
- "Price fetch failed" and "Price fetch recovered" device triggers fire when fetching prices from ENTSO-E starts failing and when it works again.
- Three diagnostic entities show the state of price fetching: the time of the last successful fetch, whether fetching is failing (with the affected day and the error), and whether tomorrow's prices are available.
- VAT and transfer fee can be edited directly from the device page. Prices update immediately without a reload or a new request to ENTSO-E.

### Changed

- The card registration code is loaded only when needed.

### Fixed

- Request timeouts to ENTSO-E are now handled as connection errors instead of escaping as unexpected failures.

### Security

- The API key no longer appears in network error messages.
