# Changelog instructions

The version comes from the `version` field in the integration's `manifest.json`. A new changelog entry and the matching version bump go in the same commit.

Specifications live in `docs/specifications/`. Only those with `status: implemented` in their frontmatter are collected. Commits not covered by a specification are added as separate items, except housekeeping such as ignore-file changes.

The project is distributed through HACS from GitHub releases. There are no tags or release workflows yet, so the changelog entry is the release note.
