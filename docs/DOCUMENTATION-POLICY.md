# Documentation Policy

Every functionality change in CryptoBridge **must** be reflected in documentation **in the same change** (same PR or commit series). Do not merge behavior changes without updating docs.

## When to update what

| Change type | Required updates |
|-------------|------------------|
| New user-facing feature | [FEATURES.md](./FEATURES.md) + [CHANGELOG.md](./CHANGELOG.md) |
| API route added/changed/removed | [FEATURES.md](./FEATURES.md) § API + [CHANGELOG.md](./CHANGELOG.md) |
| WebSocket message shape change | [FEATURES.md](./FEATURES.md) § WebSocket + [architecture.md](./architecture.md) |
| MongoDB schema change | [FEATURES.md](./FEATURES.md) § Data model + [CHANGELOG.md](./CHANGELOG.md) |
| Env var / config change | [FEATURES.md](./FEATURES.md) § Configuration + [project-context.md](./project-context.md) |
| Delta integration change | [delta-api-capabilities.md](./delta-api-capabilities.md) coverage matrix + [CHANGELOG.md](./CHANGELOG.md) |
| UI page or major component change | [FEATURES.md](./FEATURES.md) § Frontend |
| Bug fix affecting documented behavior | [CHANGELOG.md](./CHANGELOG.md) |
| Manual test step change | [backend-python/tests/FRONTEND_SMOKE.md](../backend-python/tests/FRONTEND_SMOKE.md) |

## Document map (source of truth)

| Document | Role |
|----------|------|
| [FEATURES.md](./FEATURES.md) | **Complete** feature & API reference — nothing user- or integrator-facing should be missing here |
| [CHANGELOG.md](./CHANGELOG.md) | Chronological record of what changed and why |
| [architecture.md](./architecture.md) | System design, data flows, diagrams |
| [project-context.md](./project-context.md) | Onboarding summary, conventions, glossary, links |
| [delta-api-capabilities.md](./delta-api-capabilities.md) | Delta Exchange API catalog vs app coverage |
| [FRONTEND_SMOKE.md](../backend-python/tests/FRONTEND_SMOKE.md) | Manual regression checklist |

## CHANGELOG entry format

```markdown
## YYYY-MM-DD — Short title

### Added / Changed / Fixed / Removed
- **Area:** What changed and user-visible effect.
- **API:** `METHOD /path` — description (if applicable).
- **Docs:** Files updated.
```

## FEATURES.md maintenance rules

1. List **every** REST endpoint, WebSocket event, page, modal, and background job.
2. Document request/response shapes for APIs that frontends or scripts call.
3. Document business rules (risk caps, precision, state machines) where they affect users.
4. Keep frontend pages table in sync with `App.jsx` `currentPage` values.
5. Keep MongoDB collections table in sync with services that write them.

## Review checklist (before merge)

- [ ] FEATURES.md updated for new/changed behavior
- [ ] CHANGELOG.md has dated entry
- [ ] architecture.md updated if data flow or components changed materially
- [ ] project-context.md “Documentation Map” still accurate
- [ ] FRONTEND_SMOKE.md updated if manual QA steps changed
- [ ] README.md feature bullets still accurate (high level only)
