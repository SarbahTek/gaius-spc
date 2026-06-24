"""
AI evaluation for practical (code) questions and GitHub project submissions.

Uses Anthropic Claude when ANTHROPIC_API_KEY is set. When it isn't, every
function degrades to a deterministic heuristic so the learning flow keeps
working locally — the *interface* never changes, mirroring the SMS stub pattern.

Grading philosophy (per the SPC algorithm): a learner only advances when they
demonstrate real understanding. Scores map to outcomes:
    score >= 80 → correct   (counts toward the 80/3 mastery rule)
    score >= 50 → partial
    score <  50 → incorrect
"""
import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"

# Outcome thresholds — single source of truth.
PASS_SCORE    = 80.0
PARTIAL_SCORE = 50.0


def is_configured() -> bool:
    return bool(getattr(settings, "ANTHROPIC_API_KEY", ""))


def _client():
    if not is_configured():
        return None
    try:
        import anthropic
        return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Anthropic client unavailable: %s", exc)
        return None


def _outcome_for(score: float) -> str:
    from .models import UserAttempt
    if score >= PASS_SCORE:
        return UserAttempt.OUTCOME_CORRECT
    if score >= PARTIAL_SCORE:
        return UserAttempt.OUTCOME_PARTIAL
    return UserAttempt.OUTCOME_INCORRECT


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(raw)


# ─────────────────────────────────────────────────────────────────────────
# PRACTICAL QUESTION EVALUATION
# ─────────────────────────────────────────────────────────────────────────

def evaluate_practical(question, answer: dict) -> dict:
    """
    Grade a practical answer against its rubric.
    Returns {outcome, score, feedback}.
    """
    submission = (
        answer.get("code")
        or answer.get("answer")
        or answer.get("text")
        or ""
    ).strip() if isinstance(answer, dict) else str(answer)

    if not submission:
        return {"outcome": _outcome_for(0), "score": 0.0,
                "feedback": "No answer submitted yet — write your solution and try again."}

    rubric  = question.answer_rubric or {}
    prompt  = (question.content or {}).get("prompt", "")
    qtype   = question.get_question_type_display()
    approach   = rubric.get("approach") or rubric.get("expected_approach", "")
    key_points = rubric.get("key_points", [])

    client = _client()
    if client is None:
        return _heuristic_practical(submission, key_points)

    system = (
        "You are a rigorous but encouraging programming instructor grading a student's "
        "answer. You reward genuine understanding, not keyword matching. Be fair to "
        "correct solutions that differ from the reference approach. Return ONLY JSON."
    )
    user = f"""Grade this {qtype} answer.

QUESTION:
{prompt}

EXPECTED APPROACH:
{approach}

KEY POINTS THE ANSWER SHOULD COVER:
{json.dumps(key_points, indent=2)}

STUDENT'S ANSWER:
```
{submission[:6000]}
```

Return JSON exactly:
{{"score": <0-100 integer>, "covered": ["key point met", ...], "missing": ["key point not met", ...], "feedback": "<2-4 sentences: what was good, what to improve, encouraging tone>"}}"""

    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=1024, system=system,
            messages=[{"role": "user", "content": user}],
        )
        data  = _parse_json(resp.content[0].text)
        score = float(max(0, min(100, data.get("score", 0))))
        return {"outcome": _outcome_for(score), "score": score,
                "feedback": data.get("feedback", "Answer evaluated.")}
    except Exception as exc:
        logger.warning("AI practical evaluation failed, using heuristic: %s", exc)
        return _heuristic_practical(submission, key_points)


def _heuristic_practical(submission: str, key_points: list) -> dict:
    """No-AI fallback: coarse coverage score by key-point keyword overlap."""
    text = submission.lower()
    if not key_points:
        # Without a rubric we can't truly grade; give partial credit for effort.
        score = 60.0 if len(submission.split()) >= 8 else 30.0
        return {"outcome": _outcome_for(score), "score": score,
                "feedback": "Recorded. (Set ANTHROPIC_API_KEY for full AI grading.)"}
    hits = 0
    for kp in key_points:
        words = [w for w in str(kp).lower().split() if len(w) > 3]
        if words and sum(1 for w in words if w in text) / len(words) >= 0.5:
            hits += 1
    score = round(hits / len(key_points) * 100, 1)
    return {"outcome": _outcome_for(score), "score": score,
            "feedback": f"Heuristic grade: covered {hits}/{len(key_points)} key points. "
                        "(Set ANTHROPIC_API_KEY for full AI grading.)"}


# ─────────────────────────────────────────────────────────────────────────
# PROJECT (GitHub repo) ASSESSMENT — "problem of the day / week"
# ─────────────────────────────────────────────────────────────────────────

def assess_project(project, repo_text: str) -> dict:
    """
    Assess a project submission (a fetched GitHub codebase) against the project
    brief. Returns a structured verdict:
        {passed, total, breakdown{correctness, code_quality, completeness}, feedback}
    """
    brief = f"{project.title}\n\n{project.description or ''}".strip()

    client = _client()
    if client is None:
        return _heuristic_project(repo_text)

    system = (
        "You are a senior engineer reviewing a student's project submission for a "
        "coding bootcamp. Assess whether it genuinely satisfies the brief. Be rigorous "
        "— a pass means the work is correct, complete, and reasonably clean. Return ONLY JSON."
    )
    user = f"""PROJECT BRIEF:
{brief}

SUBMITTED CODEBASE (concatenated key files, truncated):
```
{repo_text[:18000]}
```

Score each 0-100 and decide pass/fail. Return JSON exactly:
{{"correctness": <0-100>, "code_quality": <0-100>, "completeness": <0-100>, "total": <0-100>, "passed": <true|false>, "feedback": "<3-6 sentences of specific, actionable review>"}}"""

    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=1500, system=system,
            messages=[{"role": "user", "content": user}],
        )
        data  = _parse_json(resp.content[0].text)
        total = float(max(0, min(100, data.get("total", 0))))
        return {
            "passed": bool(data.get("passed", total >= PASS_SCORE)),
            "total":  total,
            "breakdown": {
                "correctness":  data.get("correctness", 0),
                "code_quality": data.get("code_quality", 0),
                "completeness": data.get("completeness", 0),
            },
            "feedback": data.get("feedback", "Project assessed."),
        }
    except Exception as exc:
        logger.warning("AI project assessment failed, using heuristic: %s", exc)
        return _heuristic_project(repo_text)


def evaluate_day_problem(problem, submission: str, prior_concepts: list) -> dict:
    """
    Assess a 'Problem of the Day' submission. When cumulative, the AI is told the
    concepts from weeks 1..N so it can check the solution integrates prior topics.
    Returns the same verdict shape as assess_project.
    """
    if not (submission or "").strip():
        return {"passed": False, "total": 0.0,
                "breakdown": {"correctness": 0, "code_quality": 0, "completeness": 0},
                "feedback": "No solution submitted yet."}

    client = _client()
    if client is None:
        return _heuristic_project(submission)

    cumulative = ""
    if prior_concepts:
        cumulative = ("This is a CUMULATIVE problem — the solution should correctly apply "
                      f"these concepts learned so far: {', '.join(prior_concepts)}.\n")

    system = (
        "You are a senior engineer grading a daily coding problem in a mastery-based "
        "bootcamp. Pass only genuinely correct, working solutions. Return ONLY JSON."
    )
    user = f"""{cumulative}PROBLEM:
{problem.title}
{problem.prompt}

EXPECTED APPROACH / KEY POINTS:
{json.dumps(problem.answer_rubric or {}, indent=2)}

STUDENT SUBMISSION:
```
{submission[:16000]}
```

Return JSON exactly:
{{"correctness": <0-100>, "code_quality": <0-100>, "completeness": <0-100>, "total": <0-100>, "passed": <true|false>, "feedback": "<3-6 sentences of specific review>"}}"""

    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=1200, system=system,
            messages=[{"role": "user", "content": user}],
        )
        data  = _parse_json(resp.content[0].text)
        total = float(max(0, min(100, data.get("total", 0))))
        return {
            "passed": bool(data.get("passed", total >= PASS_SCORE)),
            "total":  total,
            "breakdown": {
                "correctness":  data.get("correctness", 0),
                "code_quality": data.get("code_quality", 0),
                "completeness": data.get("completeness", 0),
            },
            "feedback": data.get("feedback", "Assessed."),
        }
    except Exception as exc:
        logger.warning("AI day-problem evaluation failed, heuristic: %s", exc)
        return _heuristic_project(submission)


def _heuristic_project(repo_text: str) -> dict:
    size = len(repo_text or "")
    total = 70.0 if size > 500 else (40.0 if size > 0 else 0.0)
    return {
        "passed": total >= PASS_SCORE,
        "total":  total,
        "breakdown": {"correctness": total, "code_quality": total, "completeness": total},
        "feedback": "Submission received. (Set ANTHROPIC_API_KEY for full AI code review.)",
    }
