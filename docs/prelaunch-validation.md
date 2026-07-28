# Pre-launch validation

Validated 2026-07-27 against the local production-shaped frontend and API.

## Priority workflow walkthroughs

These are structured first-time-user walkthroughs, not a substitute for sessions
with recruited participants.

| Workflow | Shared state restored | Result completed | Provenance visible | Mobile overflow |
| --- | --- | --- | --- | --- |
| Artist Habitat | Artist | Yes | Contextual | None |
| Mood Map | Selected territory | Yes | Contextual | None |
| Time Capsule | Era | Yes | Measured | None |
| Playlist Language | Public playlist | Yes, with partial-import notice | Contextual | None |
| Editorial Overlap | Public playlist | Yes, with non-causal wording | Measured | None |
| Soundtrack Gift | Brief | Yes, six-stage route | Model-assisted | None |
| Transition Finder | Start and destination | Yes, scored route | Model-assisted | None |
| Doppelganger | Artist | Yes, coverage disclosed | Model-assisted | None |

All eight views displayed a corpus snapshot date, confidence class, evidence
contract, and a copyable result link. Browser console warnings/errors: none.

## Endpoint measurements

Local measurements after startup warmup. Previous averages are from the
process-local `/api/ops` snapshot before this pass.

| Endpoint | Before | After |
| --- | ---: | ---: |
| Soundtrack Gift | ~8.5 s | ~2.8 s |
| Song Passport | ~16.5 s | ~0.17 s first result; ~0.01 s cached |
| Group Blend | ~7.0 s | ~3.8 s first result; ~0.005 s cached |
| Collision | up to ~41.7 s cold | ~2.7 s first result; ~0.003 s cached |

Changes responsible:

- Indexed Soundtrack Gift artist lookups instead of repeatedly filtering the
  complete artist table.
- Batched Group Blend graph-neighborhood reads and cached deterministic results.
- Localized and cached Song Passport ListenBrainz lookups.
- Warmed graph and ListenBrainz artifacts during API startup.

## Automated checks

- Python compilation: passed.
- Frontend lint: passed.
- Frontend production build: passed.
- Full Python suite (unit, smoke, semantic, telemetry, and frontend contracts):
  66 passed.
- Legacy-route configuration contract: passed with the API in both enabled and
  disabled modes.

Reproducible production-shaped command:

```sh
./deploy/validate_local.sh
```

The validator starts the repository's `.venv` API when needed, waits for
`/ready` to report that R2-backed artifacts are loaded, runs the complete test
suite without copying the server's legacy-route flag into pytest, and then runs
Python compilation, frontend lint, and the production build. It cleans up only
the API process it started.

The API advertises its actual `legacy_heavy_endpoints` state through
`/api/capabilities`; smoke tests use that server-reported value. `pytest.ini`
also adds the repository root to the import path so cache and telemetry tests
collect consistently. Direct smoke-test runs now abort once with an actionable
readiness message when the live API prerequisite is absent or degraded.

Frontend contract regressions now assert that:

- the shared premium page shell injects the evidence contract and copy control,
- all eight priority walkthroughs restore their documented URL inputs, and
- Overlap Arena preserves both compared artists in its result URL.

The build retains a third-party `lottie-web` warning about direct `eval`; it is
inside the dependency bundle and did not produce a browser runtime warning.

## Human validation still required

Recruit five unfamiliar users and give each only the workflow task—not an
explanation of the metric. Record whether they can:

1. choose a valid input,
2. explain the result in their own words,
3. identify the coverage limitation,
4. share the exact result,
5. recover from an invalid or unavailable input.
