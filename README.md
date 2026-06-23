# SPC Campus — Learning Platform API

A Django REST API backend for an adaptive, mastery-based learning platform. Learners progress through structured courses by answering questions, earning mastery over concepts through a strict 80/3 rule, and completing weekly capstone projects. Admins can generate entire courses from a PDF upload using an AI agent.

---

## Table of Contents

1. [Tech Stack](#tech-stack)
2. [Project Structure](#project-structure)
3. [Environment Setup](#environment-setup)
4. [Existing Implementation](#existing-implementation)
   - [Authentication](#authentication)
   - [Curriculum Structure](#curriculum-structure)
   - [Questions & Assessments](#questions--assessments)
   - [Mastery Tracking](#mastery-tracking)
   - [Day & Week Progress Gating](#day--week-progress-gating)
   - [Projects & Build Logs](#projects--build-logs)
   - [Learner API Endpoints](#learner-api-endpoints)
5. [Added Feature — AI Course Generation Agent](#added-feature--ai-course-generation-agent)
   - [How It Works](#how-it-works)
   - [New App: course_agent](#new-app-course_agent)
   - [New Model: ConceptLesson](#new-model-conceptlesson)
   - [Admin API Endpoints](#admin-api-endpoints)
   - [Learner Lesson Endpoint](#learner-lesson-endpoint)
   - [Required Environment Variables](#required-environment-variables)
6. [Full API Reference](#full-api-reference)
7. [Data Model Overview](#data-model-overview)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | Django 4.2 + Django REST Framework |
| Auth | JWT via `djangorestframework-simplejwt` |
| Database | SQLite3 (development) |
| CORS | `django-cors-headers` |
| AI — Course Generation | Anthropic Claude (`claude-sonnet-4-6`) |
| AI — Text to Speech | OpenAI TTS API (`tts-1`, voice: `nova`) |
| PDF Parsing | `pdfplumber` |
| Dependency Management | `pipenv` |

---

## Project Structure

```
gaius-spc/
├── spc_campus/          # Django project config (settings, root URLs)
├── auth_manager/        # User model, registration, login, JWT
├── curriculum/          # Core learning content (courses, questions, mastery, progress)
├── course_agent/        # AI agent — PDF → course generation (new)
├── media/               # Uploaded PDFs and generated audio files (created at runtime)
├── db.sqlite3           # SQLite database
├── Pipfile              # Pipenv dependency manifest
└── Pipfile.lock         # Locked dependency versions
```

---

## Environment Setup

### 1. Install pipenv (if not already installed)

```bash
pip3 install pipenv
```

### 2. Create the virtual environment and install all dependencies

```bash
pipenv install
```

### 3. Set required environment variables

```bash
export ANTHROPIC_API_KEY=sk-ant-...          # Required for course generation
export OPENAI_API_KEY=sk-...                 # Optional — enables TTS audio generation
```

### 4. Apply database migrations

```bash
pipenv run python manage.py migrate
```

### 5. Create a superuser (for Django admin panel)

```bash
pipenv run python manage.py createsuperuser
```

### 6. Run the development server

```bash
pipenv run python manage.py runserver
```

The API will be available at `http://localhost:8000`.  
The Django admin panel is at `http://localhost:8000/admin/`.

---

## Existing Implementation

### Authentication

**App:** `auth_manager`

**User model** extends `AbstractUser` with a `role` field:

| Role | Description |
|---|---|
| `student` | Default role. Learner-facing access only. |
| `instructor` | Reserved for future instructor features. |
| `admin` | Full access including course generation and publishing. |

**JWT Configuration:**
- Access token lifetime: **1 hour**
- Refresh token lifetime: **7 days**
- Refresh token rotation enabled (old token invalidated on refresh)

**Endpoints:**

| Method | URL | Description |
|---|---|---|
| `POST` | `/api/accounts/register/` | Create account — returns access + refresh tokens immediately |
| `POST` | `/api/accounts/login/` | Login — returns access + refresh tokens + role |
| `POST` | `/api/accounts/token/refresh/` | Exchange refresh token for a new access token |
| `GET` | `/api/accounts/me/` | Get current user profile |
| `PUT` | `/api/accounts/me/` | Update bio or avatar URL |

All protected endpoints require the header:
```
Authorization: Bearer <access_token>
```

---

### Curriculum Structure

**App:** `curriculum`

The course hierarchy from top to bottom:

```
SubjectArea
└── Course  (is_published flag — learners only see published courses)
    └── Week  (numbered, ordered)
        └── Concept  (tied to a specific day 1–5, ordered within the day)
            ├── Question  (multiple per concept, all types and difficulties)
            └── ConceptLesson  (AI-generated tutor script + audio — see new feature)
```

**SubjectArea** — 8 predefined areas:

| Key | Display Name |
|---|---|
| `programming` | Programming |
| `aws` | AWS & Cloud |
| `system_design` | System Design & Architecture |
| `ml_ai` | ML & AI |
| `blockchain` | Blockchain |
| `ai_agents` | AI Agents |
| `devops` | DevOps |
| `security` | Security |

**Course** fields: `title`, `description`, `subject_area`, `is_published`

**Week** fields: `number`, `title`, `summary`, `course`
- Unique constraint: `(course, number)`

**Concept** fields: `title`, `description`, `video_url`, `video_duration_seconds` (max 300s / 5 min), `day_introduced` (1–5), `order`

---

### Questions & Assessments

**10 question types:**

| Type Key | Display Name | Practical? |
|---|---|---|
| `mcq` | Multiple choice | No |
| `code_scratch` | Code from scratch | Yes |
| `debug` | Debug this | Yes |
| `extend` | Extend this | Yes |
| `explain` | Explain your code | Yes |
| `design` | Design this | Yes |
| `review` | Review this | Yes |
| `spot_bug` | Spot the bug | Yes |
| `refactor` | Refactor this | Yes |
| `edge_case` | Security / edge case | Yes |

**3 difficulty levels:** Easy (1), Medium (2), Hard (3)

**Question fields:**
- `content` (JSONField) — question data shown to the student
- `answer_rubric` (JSONField) — correct answer / rubric, **never exposed to students**
- `socratic_clue`, `scaffolded_hint`, `micro_explanation` — progressive hint chain
- `is_ai_generated` — flag for AI-generated questions

**MCQ content format:**
```json
{ "prompt": "What does X do?", "options": ["A", "B", "C", "D"] }
```
**MCQ rubric format:**
```json
{ "correct_index": 2, "explanation": "Because..." }
```

**Practical content format:**
```json
{ "prompt": "Write a function that...", "starter_code": "def foo():\n    pass" }
```
**Practical rubric format:**
```json
{ "approach": "Use a hash map...", "key_points": ["O(n) time", "handles empty input"] }
```

**Answer evaluation:**
- MCQ: auto-marked immediately against `correct_index`
- Practical: stub returns `partial / 0.0` — wired for Anthropic API evaluation in Phase 2

**Clue chain** (served progressively on failure):
1. Attempt 1 fail → Socratic clue ("Think about…")
2. Attempt 2 fail → Scaffolded hint ("Here's a scaffold…")
3. Attempt 3+ fail → Micro explanation (direct answer + concept flagged for spaced repetition)

---

### Mastery Tracking

**Model:** `ConceptMastery`

The platform uses an **80/3 mastery rule**: a concept is mastered when a learner answers **3 consecutive Hard questions correctly with a score ≥ 80%**.

**Mastery statuses:**

| Status | Meaning |
|---|---|
| `not_started` | No attempts yet |
| `in_progress` | Attempts made, rule not yet met |
| `mastered` | 3 consecutive hard ≥ 80% achieved |
| `weak` | 4+ failures — concept flagged for extra spaced-repetition review |

**Tracked per attempt:**
- `consecutive_correct_hard` — resets to 0 on any wrong answer
- `highest_difficulty_passed`
- `total_attempts`, `total_correct`, `best_score`
- `accuracy` (computed property)

**Spaced repetition:** Weak concepts are scheduled for future review via `ScheduledTest` (Celery-ready, `celery_task_id` stored for async delivery).

---

### Day & Week Progress Gating

**Model:** `DayProgress`

Learners unlock days sequentially. A day passes only when **all concepts in that day are mastered**.

**Day statuses:**

| Status | Meaning |
|---|---|
| `locked` | Not yet accessible |
| `unlocked` | Available to attempt |
| `in_progress` | At least one attempt made |
| `passed` | All concepts in this day mastered |

**Unlock logic:**
- Week starts with Day 1 unlocked, all others locked
- When Day N passes → Day N+1 automatically unlocks
- Days 1–5 map to `day_introduced` on Concept; days 6–7 are reserved for review/projects

**On MCQ restriction:** Questions on `day > 1` exclude MCQ type — practical questions only.

---

### Projects & Build Logs

**Model:** `Project` — one capstone project per student per week

**Project statuses:** `draft → submitted → evaluating → passed / revision_needed / failed`

**Resubmission rule:** Maximum 2 resubmissions when status is `revision_needed`.

**Project fields:** `title`, `description`, `github_url`, `code_submission` (text), `readme`, `ai_score` (JSONField), `ai_feedback_summary`

**AI evaluation:** Stub in place — Anthropic API integration planned for Phase 2.

**Model:** `BuildLog` — one daily work-log entry per student per week per day. Tracks `entry` (text) and `ai_prompt_used`.

---

### Learner API Endpoints

All endpoints require `Authorization: Bearer <token>`.

| Method | URL | Description |
|---|---|---|
| `GET` | `/api/curriculum/courses/` | List published courses. Filter: `?subject=aws` |
| `GET` | `/api/curriculum/courses/<id>/` | Course detail with all weeks and concepts |
| `GET` | `/api/curriculum/weeks/<id>/` | Week detail with concepts |
| `GET` | `/api/curriculum/concepts/<id>/` | Single concept |
| `GET` | `/api/curriculum/concepts/<id>/lesson/` | AI tutor script + audio URL *(new)* |
| `GET` | `/api/curriculum/concepts/<id>/questions/` | Available questions. Filters: `?difficulty=1&day=1` |
| `GET` | `/api/curriculum/questions/<id>/clue/` | Appropriate clue for current attempt number |
| `POST` | `/api/curriculum/attempts/submit/` | Submit an answer — returns evaluation, mastery update, day status |
| `GET` | `/api/curriculum/attempts/` | Attempt history. Filter: `?concept_id=5` |
| `GET` | `/api/curriculum/mastery/` | All concept masteries for current user |
| `GET` | `/api/curriculum/mastery/?concept_id=5` | Single concept mastery |
| `GET` | `/api/curriculum/mastery/weak/` | Concepts flagged as weak |
| `GET` | `/api/curriculum/progress/week/<id>/` | Week day statuses + summary stats |

**Submit attempt request body:**
```json
{ "question_id": 42, "answer": { "selected_index": 2 } }
```

**Submit attempt response:**
```json
{
  "attempt": { "id": 1, "outcome": "correct", "score": 100.0, "ai_feedback": "..." },
  "mastery": { "status": "in_progress", "consecutive_correct_hard": 1, ... },
  "clue": null,
  "day_status": { "day_number": 1, "day_passed": false, "next_day": null }
}
```

---

## Added Feature — AI Course Generation Agent

### How It Works

An admin uploads a PDF (lecture notes, a textbook chapter, a course syllabus, etc.). The platform automatically generates a fully structured course including weeks, concepts, tutor explanations, and assessment questions — all via Claude. Optionally, each concept's tutor script is converted to spoken audio via OpenAI TTS.

**Pipeline:**

```
Admin uploads PDF
        │
        ▼
[1] pdfplumber extracts full text
        │
        ▼
[2] Claude (claude-sonnet-4-6) generates:
      • Course title & description
      • Weeks with titles and summaries
      • Concepts per day (3–5 per week)
      • Tutor script per concept (250–400 words, conversational tone)
      • 3 questions per concept (easy MCQ, medium MCQ, hard practical)
        │
        ▼
[3] Django ORM creates:
      Course → Weeks → Concepts → ConceptLessons → Questions
      (course is_published = False — admin reviews before publishing)
        │
        ▼
[4] OpenAI TTS (optional) converts each tutor script → .mp3
      Saved to: media/concept_audio/<filename>.mp3
        │
        ▼
Admin reviews in Django admin, sets is_published = True
        │
        ▼
Learners access course — text + audio on every concept
```

The generation runs in a **background thread** so the upload endpoint returns immediately with a `job_id`. The admin polls a status endpoint until the job completes.

---

### New App: course_agent

```
course_agent/
├── agent.py         # CourseGenerationAgent — the full PDF → DB → audio pipeline
├── models.py        # CourseGenerationJob — tracks status of each generation job
├── views.py         # Admin-only API views
├── serializers.py   # Job serializer
├── permissions.py   # IsAdminRole permission class
├── urls.py          # Routes under /api/admin/
├── admin.py         # Django admin registration
└── migrations/
    └── 0001_initial.py
```

**`CourseGenerationJob` model fields:**

| Field | Type | Description |
|---|---|---|
| `created_by` | FK → User | Admin who triggered the job |
| `pdf_file` | FileField | Stored under `media/course_pdfs/` |
| `original_filename` | CharField | Original name of uploaded file |
| `subject_area` | FK → SubjectArea | Optional — passed to Claude as context |
| `status` | CharField | `pending` → `processing` → `completed` / `failed` |
| `generated_course` | FK → Course | Set on completion |
| `error_message` | TextField | Populated on failure |
| `created_at` | DateTimeField | Job creation timestamp |
| `completed_at` | DateTimeField | Set when pipeline finishes |

---

### New Model: ConceptLesson

Added to the `curriculum` app — lives alongside `Concept`.

| Field | Type | Description |
|---|---|---|
| `concept` | OneToOneField → Concept | Parent concept |
| `tutor_script` | TextField | Full conversational tutor explanation (Markdown-compatible) |
| `audio_file` | FileField | MP3 audio of the tutor script (blank if TTS not configured) |
| `generated_at` | DateTimeField | Auto-set on creation |

---

### Admin API Endpoints

All endpoints require a JWT token with `role: admin`.

#### Upload PDF and start generation

```
POST /api/admin/courses/generate/
Content-Type: multipart/form-data

Fields:
  pdf              (file, required)  — the PDF learning material
  subject_area_id  (int, optional)   — links generated course to a SubjectArea
```

**Response `202 Accepted`:**
```json
{
  "job_id":   1,
  "status":   "pending",
  "poll_url": "/api/admin/generation-jobs/1/",
  "message":  "Course generation started. Poll the poll_url to check progress."
}
```

#### Poll job status

```
GET /api/admin/generation-jobs/<id>/
```

**Response while running:**
```json
{ "id": 1, "status": "processing", "original_filename": "intro_to_python.pdf", ... }
```

**Response on success:**
```json
{
  "id": 1,
  "status":        "completed",
  "course_id":     7,
  "course_title":  "Introduction to Python",
  "completed_at":  "2026-06-22T14:35:02Z"
}
```

**Response on failure:**
```json
{
  "id": 1,
  "status":        "failed",
  "error_message": "JSONDecodeError: Expecting value at line 1"
}
```

#### List all jobs (for this admin)

```
GET /api/admin/generation-jobs/
```

#### Publish / unpublish a course

```
POST /api/admin/courses/<id>/publish/
POST /api/admin/courses/<id>/unpublish/
```

**Response:**
```json
{ "id": 7, "is_published": true }
```

---

### Learner Lesson Endpoint

```
GET /api/curriculum/concepts/<id>/lesson/
```

**Response when lesson exists:**
```json
{
  "concept":      5,
  "tutor_script": "Let's talk about variables. Imagine you have a box...",
  "audio_url":    "http://localhost:8000/media/concept_audio/concept_5_a3f1b2c4.mp3",
  "generated_at": "2026-06-22T14:35:02Z"
}
```

**Response when no lesson exists (manually created concept, no AI generation):**
```json
{
  "concept_id":    5,
  "concept_title": "Variables",
  "tutor_script":  null,
  "audio_url":     null,
  "generated_at":  null
}
```

The frontend should:
- Render `tutor_script` as rich text (Markdown) for the visual experience
- Play `audio_url` in an `<audio>` element for the auditory experience
- Fall back gracefully when either field is `null`

---

### Required Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes (for generation) | Claude API — course structure and question generation |
| `OPENAI_API_KEY` | No | OpenAI TTS — converts tutor scripts to MP3 audio. Feature works text-only without this. |

Set before running the server:
```bash
export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...
pipenv run python manage.py runserver
```

---

## Full API Reference

### Auth (`/api/accounts/`)

| Method | URL | Auth | Description |
|---|---|---|---|
| POST | `/register/` | None | Register + get tokens |
| POST | `/login/` | None | Login + get tokens |
| POST | `/token/refresh/` | Refresh token | Get new access token |
| GET | `/me/` | Bearer | Get own profile |
| PUT | `/me/` | Bearer | Update bio / avatar |

### Curriculum — Learner (`/api/curriculum/`)

| Method | URL | Auth | Description |
|---|---|---|---|
| GET | `/courses/` | Bearer | List published courses |
| GET | `/courses/<id>/` | Bearer | Course detail (all weeks + concepts) |
| GET | `/weeks/<id>/` | Bearer | Week detail |
| GET | `/concepts/<id>/` | Bearer | Concept detail |
| GET | `/concepts/<id>/lesson/` | Bearer | AI tutor script + audio |
| GET | `/concepts/<id>/questions/` | Bearer | Questions for concept |
| GET | `/questions/<id>/clue/` | Bearer | Progressive clue by attempt number |
| POST | `/attempts/submit/` | Bearer | Submit answer + get evaluation |
| GET | `/attempts/` | Bearer | Attempt history |
| GET | `/mastery/` | Bearer | All masteries |
| GET | `/mastery/?concept_id=<id>` | Bearer | Single concept mastery |
| GET | `/mastery/weak/` | Bearer | Weak concepts |
| GET | `/progress/week/<id>/` | Bearer | Week day progress |

### Course Agent — Admin (`/api/admin/`)

| Method | URL | Auth | Description |
|---|---|---|---|
| POST | `/courses/generate/` | Bearer (admin) | Upload PDF → start generation |
| POST | `/courses/<id>/publish/` | Bearer (admin) | Publish course to learners |
| POST | `/courses/<id>/unpublish/` | Bearer (admin) | Pull course back for edits |
| GET | `/generation-jobs/` | Bearer (admin) | List all generation jobs |
| GET | `/generation-jobs/<id>/` | Bearer (admin) | Poll job status |

---

## Data Model Overview

```
SubjectArea
│
└── Course (is_published)
    │   ▲
    │   └── CourseGenerationJob  [course_agent app]
    │         created_by → User (admin)
    │         pdf_file, status, error_message
    │
    └── Week
        │
        └── Concept
            ├── ConceptLesson       tutor_script + audio_file
            ├── Question            content, answer_rubric, clue chain
            ├── ScheduledTest       spaced-repetition schedule per user
            │
            └── [per-user data]
                ├── ConceptMastery  80/3 rule tracking
                ├── DayProgress     locked / unlocked / passed
                ├── UserAttempt     every submitted answer
                ├── Project         weekly capstone (max 2 resubmissions)
                └── BuildLog        daily work journal
```
