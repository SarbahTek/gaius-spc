# SPC Campus — The Learning Engine

This document explains **how learning works** on SPC Campus: the structure, the
mastery algorithm, sequential unlocking, assessment (including code & GitHub
project review), and how courses are rendered on web and mobile. It is the
source of truth for the "learning experience" — the heart of the platform.

> Design goal: a guided, mastery-based path where **the poorest and least
> experienced learner can become a professional**, in their own language, by
> proving real understanding before advancing. Not a video buffet — a ladder.

---

## 1. Content structure

```
SubjectArea            (Programming, AWS, ML/AI, …)
└── Course             (price, language, is_published, instructor)
    └── Week           (numbered; has a weekly Project / "problem")
        └── Concept    (tied to a Day 1–5; ordered)
            ├── ConceptLesson   tutor script (Markdown) + optional TTS audio
            └── Question        10 types × 3 difficulties
```

A **Week** is a unit of work spread over 7 days: Days 1–5 introduce concepts,
Days 6–7 are review + the weekly **Project**. Each **Concept** has an AI tutor
lesson (text + audio for the auditory learner) and a bank of **Questions**.

### Question types (10) and difficulties (3)
MCQ + 9 practical types (`code_scratch`, `debug`, `extend`, `explain`, `design`,
`review`, `spot_bug`, `refactor`, `edge_case`). Difficulty: Easy(1), Medium(2),
Hard(3). `content` (shown) and `answer_rubric` (never shown) are JSON.

---

## 2. The 80/3 mastery rule  *(`ConceptMastery.record_attempt`)*

A concept is **mastered** when the learner answers **3 consecutive Hard
questions correctly with score ≥ 80%**. Tracked per concept:

- `consecutive_correct_hard` — resets to 0 on any wrong answer
- `best_score`, `total_attempts`, `total_correct`, `highest_difficulty_passed`
- status: `not_started → in_progress → mastered`, or `weak` after 4+ failures
  (weak concepts resurface via spaced repetition — `ScheduledTest`).

This is deliberately demanding: mastery means *consistent* high performance at
the hardest level, not a single lucky pass.

---

## 3. Sequential unlocking  *(`GatingService` — "don't unlock the next until one is complete")*

Access is **day-granular and strictly ordered**:

> A concept is **unlocked** only when the learner is **enrolled** AND every
> concept in an **earlier day of the same week** and in **every earlier week**
> is **mastered**. Week 1 / Day 1 is the single entry point.

Enforced server-side (clients can't bypass it):
- `GET /concepts/<id>/questions/` → **403 `{locked:true, detail}`** if locked.
- `POST /attempts/submit/` → **403** if the concept is locked.
- `GET /courses/<id>/outline/` → returns every concept with `unlocked`,
  `mastered`, and `lock_reason` so the UI can render locks (Udemy-style) without
  re-deriving the rule.

This balances **timed learning** (a 7-day weekly cadence via `DayProgress`) with
**self-paced mastery** (you advance the moment you've proven the current step,
not before).

---

## 4. The core loop  *(`POST /api/curriculum/attempts/submit/`)*

One endpoint runs the whole loop:

1. **Gate check** — concept must be unlocked (else 403).
2. **Evaluate** (`EvaluationService`):
   - **MCQ** → instant auto-mark vs `correct_index`.
   - **Practical/code** → **AI evaluation** (see §5).
3. **Update mastery** (80/3 rule).
4. **Progressive clues on failure** (`ClueService`): attempt 1 → Socratic nudge,
   attempt 2 → scaffolded hint, attempt 3+ → micro-explanation (and the concept
   is flagged for spaced repetition). This is how the "dumbest person can
   understand" — the system never just says "wrong"; it teaches.
5. **Day/week completion** check → unlocks the next day when all its concepts are
   mastered.

Response: `{attempt, mastery, passed, clue?, day_status}`.

---

## 5. Assessment — making practice *real*

### 5a. Practical / code answers  *(`curriculum/ai_evaluation.py`)*
`evaluate_practical()` grades the learner's code against the question's rubric
(`approach`, `key_points`) using **Anthropic Claude** (`claude-sonnet-4-6`). It
returns `{score 0–100, outcome, feedback}`. Score → outcome thresholds:
`≥80 correct`, `≥50 partial`, `<50 incorrect`.

If `ANTHROPIC_API_KEY` is unset, it **degrades gracefully** to a key-point
keyword-coverage heuristic so the flow still works locally — same interface,
mirroring the SMS stub. Set the key for full AI grading.

### 5b. "Problem of the day/week" — GitHub project review  *(`ProjectService` + `github_service.py`)*
Each Week has a **Project**. The learner submits a **GitHub repo URL** (or
pastes code). The platform:

1. Parses the repo, fetches a **bounded, curated snapshot** of source files via
   the GitHub REST API (skips `node_modules`, lockfiles, binaries; caps files &
   bytes). Public repos need no credentials.
2. **AI-assesses** the codebase against the project brief →
   `{passed, total, breakdown{correctness, code_quality, completeness}, feedback}`.
3. Records the verdict on the `Project` (`passed` / `revision_needed`), max
   **3 submissions** (initial + 2 resubmissions).

Endpoints: `POST /api/curriculum/projects/submit/`,
`GET /api/curriculum/projects/?week_id=`.

**Private repos / "grant us access":** today public repos work out of the box.
For private repos set `GITHUB_TOKEN` (a token that can read them). A first-class
"grant access" flow (GitHub App installation or user OAuth) is the documented
next step — see `github_service._auth_headers` (integration point, like SMS).

---

## 6. Rendering (Udemy-style, SPC algorithm)

Both web and the Flutter app render a course as a **curriculum outline**:
Weeks → Days → Concepts, each with a **lock icon** when not yet unlocked and a
**checkmark** when mastered. Data comes from `GET /courses/<id>/outline/`.

- **Lesson view**: Markdown tutor script + an audio player (TTS) for the lesson,
  then the question flow for that concept.
- **Locked items** are visible but not enterable (so learners see the path
  ahead), exactly like Udemy — but here the unlock is *earned by mastery*, not
  just "next video".
- **Languages**: courses carry a `language`; the platform UI is translated (Twi,
  Ewe, Hausa, Ga, Dagbani, Fante, English) so content can be delivered in a
  learner's mother tongue.

### Client status
- **API**: complete — evaluation, gating, outline, projects all live & tested.
- **Web**: study/lesson + MCQ flow live; gated outline rendering + project
  submission UI are the next web tasks.
- **App**: lesson + MCQ/practical question flow live; consuming the `outline`
  endpoint for gated rendering, an in-app **code editor** for practical answers,
  and the project-submission screen are the next app tasks.

---

## 7. Configuration

| Env var | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Full AI grading of code answers & projects (else heuristic) |
| `OPENAI_API_KEY` | TTS audio for lessons (optional) |
| `GITHUB_TOKEN` | Higher GitHub rate limits + private-repo reads (optional) |

---

## 8. What's tested

Automated smoke checks cover: practical AI/heuristic grading, project submission
(code + GitHub URL, including unreachable-repo handling), and **sequential
gating** (not-enrolled blocked, day-2 locked until day-1 mastered, unlock on
mastery, outline flags). MCQ marking + the 80/3 mastery progression are exercised
by the broader attempt-submit tests.
