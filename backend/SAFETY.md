# The Vigil — Player Safety & Narrative Ethics

The Nyx Engine deliberately authors **tragedy**: permanent death, doom,
self-destruction, grim themes. It is a **public** repo, every API route is
unauthenticated, and `player_id` is a client-supplied string. "The Vigil" is the
duty-of-care layer for the **real human at the keyboard** — the one axis where
softening is the improvement, because the only thing it is gentle toward is the
person, never the character. The fiction stays exactly as merciless.

## The boundary (non-negotiable)
This layer governs **depiction-to-the-human** and **signposting-to-real-help**.
It MUST NOT weaken the character's friction: death stays permanent, the
consequence economy is byte-for-byte untouched, Clotho stays lowest authority.
Any welfare organ that screens a render is wired through the same authority
inversion the engine already trusts for Momus/Sophia — a frozen verdict
structurally incapable of writing game state, that only ever selects which prose
string is emitted.

---

## Phase 1 — SHIPPED (pure engineering; no authored crisis content)

Two safe, high-value pieces that require **no** human-authored crisis copy or
detection design, coupling only to the *existing* `atropos_death_keywords`:

1. **Death permanence (the miracle-exemption).** A death that originates from a
   self-destruction keyword (`AtroposResponse.self_destruction_origin`, set in
   `atropos.py` trigger 3) is **exempt from the Eris miracle** in `resolver.py`.
   A vulnerable player who types real-world self-harm framing can never be
   rewarded with survival-by-luck — the cruelest possible "the dice saved you,
   keep playing" mixed signal. This *hardens* permanence; it is on-soul.

2. **Input redaction at source (privacy).** On a turn whose action contains a
   self-destruction framing (`services/welfare.flags_sensitive_input`, reusing
   the existing keyword list), the action is replaced with
   `[redacted: welfare-flagged input]` at **every durable/observable store** —
   the turn log, `create_turn(action=)` (the unauthenticated DB), and
   `rag.add_turn(action=)` (the vector store). The fiction's math is computed
   from the **real** action and is byte-for-byte identical; only the stored
   copy is redacted. A typed crisis disclosure no longer lands in a
   world-readable log or an unauthenticated row.

Both are deterministic and **keyless** — they protect the default public engine.
Tests: `backend/tests/test_welfare.py` (the Phase-1 permanence/redaction floor) +
`backend/tests/test_crisis_routing.py` (the Phase-2 crisis-routing surface + gating).

---

## Phase 2 — SHIPPED, but GATED (inert until `welfare_copy_reviewed` is flipped)

The crisis-routing **seam** is built and tested, and **inert by default**:
`settings.welfare_copy_reviewed` is `False`, so nothing user-facing renders until
a human (ideally clinical) reviewer signs the words and flips the flag. *An AI
must not author the live crisis copy a vulnerable person reads* — so the copy
ships as a clearly-marked **DRAFT** and the flag-flip is a human decision, not a
build step.

- **One canonical detector** (`services/welfare.detect_crisis` / `is_flagged`) —
  the real-world-framed subset of `atropos_death_keywords` UNION a first-person
  ideation pattern set (`_IDEATION_PATTERNS`). It drives BOTH the care channel and
  the durable-store redaction from one lexicon (so they can never desync) and runs
  on **every** turn regardless of the gate — only the *display* is gated.
- **Server-owned crisis copy** (`CRISIS_RESOURCES`) — 988 + findahelpline.com +
  the "this is a game, not counseling" disclaimer, with an import-time guard that
  refuses to start without all three. **DRAFT, pending review.**
- **Routes** — `/action` attaches `crisis_resources` and `/turn` yields a
  `crisis_resources` SSE event FIRST, both only when flagged AND
  `welfare_copy_reviewed`; `GET /safety` returns the gate state + (when reviewed)
  the copy.
- **Frontend** — `ConsentGate.svelte` (content warning + self-asserted consent),
  `CrisisInterstitial.svelte` (the in-flow card, above the death surface), and the
  always-on, network-independent `CrisisLink.svelte` backstop on every screen.

Tests: `backend/tests/test_crisis_routing.py` (detector superset, gating, the
resources contract) + `frontend/src/lib/safety.test.ts` (the always-on link copy).

---

## DEFERRED — requires human + clinical review before it ships

The full hardened plan (`~/.claude/plans/`, "The Vigil") specifies the rest of
the duty-of-care **surface**. Engineering ships the seam; **a human signs the
words.** Still unbuilt:

- **Ideation detection-pattern expansion** — the shipped `_IDEATION_PATTERNS` is
  a deliberately high-precision, **low-recall** floor. A fuller detector
  (indirect/past-tense/metaphorical framings) is a clinically-informed design, not
  an engineering guess. The always-reachable `CrisisLink` is the honest backstop
  for everything the regex misses; no copy claims completeness.
- **Per-theme content opt-outs** — beyond the single consent gate.
- **Aletheia, the output welfare classifier** — a guardian sibling of Sophia
  (frozen verdict, zero state authority, deterministic mock) that softens a
  *depiction* (never the consequence) when a player has opted out. The seam
  mirrors Sophia exactly; its rubric and the soften/veto copy need review.
- **Flipping `welfare_copy_reviewed`** — the gate itself. A human reviews the
  DRAFT copy + detection above, then flips it. That review *is* the ship gate.

### Constraints carried forward (from the hardened plan, SAFE-E1..E7)
- **Superset coupling:** any real-world phrase that can cause a keyword-death
  must *also* raise the care channel — one shared lexicon, never disjoint.
- **Zero state authority:** the welfare verdict schema cannot express a state
  write or cancel a death (mirror `JudgeCritique`).
- **Keyless deterministic floor:** the protective softening must run with no API
  key; a real-model classifier is a bonus layer, never the floor.
- **Death-turn reachability:** the screen must be wired *inside* `_handle_death`
  (the death render is assembled there, after the early `if ctx.terminal`).
- **Honest signposting, not impersonation;** privacy: never log/persist the
  matched substring or action text on a crisis turn (Phase 1 already enforces
  redaction).
- **Not an enforced age wall;** self-asserted consent is documented as such.

The character still dies on schedule and the world stays grim. Phase 1 (always
on) stops the engine leaking a person's crisis disclosure and handing a
self-destructive input a lucky survival; Phase 2 (built, gated) adds the
signposting-to-real-help surface. The gate stays closed until a human signs the
words.
