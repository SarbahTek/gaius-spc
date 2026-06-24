from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from .models import (
    Question, UserAttempt, ConceptMastery, DayProgress, Concept, Week, Project,
    TestSession, DayProblem, DayProblemSubmission,
)


class EvaluationService:
    """
    MCQ auto-marks instantly; practical/code answers are graded by the AI
    evaluator (Anthropic) against their rubric, with a heuristic fallback when
    no API key is configured. The interface never changes — views don't care
    how evaluation happens.
    """

    @classmethod
    def evaluate(cls, question: Question, answer: dict, user) -> dict:
        if question.question_type == Question.TYPE_MCQ:
            return cls._evaluate_mcq(question, answer)
        from .ai_evaluation import evaluate_practical
        return evaluate_practical(question, answer)

    @classmethod
    def _evaluate_mcq(cls, question: Question, answer: dict) -> dict:
        correct_index  = question.answer_rubric.get("correct_index")
        selected_index = answer.get("selected_index")

        if selected_index is None:
            return {"outcome": UserAttempt.OUTCOME_INCORRECT, "score": 0.0, "feedback": "No option selected."}

        if selected_index == correct_index:
            return {"outcome": UserAttempt.OUTCOME_CORRECT, "score": 100.0, "feedback": "Correct."}

        options      = question.content.get("options", [])
        correct_text = options[correct_index] if correct_index < len(options) else "—"
        return {
            "outcome":  UserAttempt.OUTCOME_INCORRECT,
            "score":    0.0,
            "feedback": f"Incorrect. The correct answer was: {correct_text}.",
        }

    # Replaced by ai_evaluation.evaluate_practical (kept for reference):
    # @classmethod
    # def _evaluate_stub(cls, question: Question, answer: dict) -> dict:
    #     """Placeholder. Phase 2 wires Anthropic API here."""
    #     return {
    #         "outcome":  UserAttempt.OUTCOME_PARTIAL,
    #         "score":    0.0,
    #         "feedback": "Answer recorded. AI evaluation coming in Phase 2.",
    #     }


class MasteryService:
    """Updates ConceptMastery and handles day gating after every attempt."""

    @classmethod
    def record(cls, user, question: Question, is_correct: bool, score: float) -> ConceptMastery:
        mastery, _ = ConceptMastery.objects.get_or_create(user=user, concept=question.concept)
        mastery.record_attempt(is_correct=is_correct, difficulty=question.difficulty, score=score)
        return mastery

    @classmethod
    def check_day_completion(cls, user, concept: Concept) -> dict:
        day_number   = concept.day_introduced
        week         = concept.week
        day_concepts = Concept.objects.filter(week=week, day_introduced=day_number).values_list("id", flat=True)

        mastered_count = ConceptMastery.objects.filter(
            user=user,
            concept_id__in=day_concepts,
            status=ConceptMastery.STATUS_MASTERED,
        ).count()

        day_passed = mastered_count >= len(day_concepts)

        if day_passed:
            DayProgress.objects.update_or_create(
                user=user, week=week, day_number=day_number,
                defaults={"status": DayProgress.STATUS_PASSED, "passed_at": timezone.now()},
            )
            next_day = day_number + 1 if day_number < 7 else None
            if next_day:
                DayProgress.objects.update_or_create(
                    user=user, week=week, day_number=next_day,
                    defaults={"status": DayProgress.STATUS_UNLOCKED, "unlocked_at": timezone.now()},
                )
        else:
            DayProgress.objects.update_or_create(
                user=user, week=week, day_number=day_number,
                defaults={"status": DayProgress.STATUS_IN_PROGRESS},
            )

        return {
            "day_number": day_number,
            "day_passed": day_passed,
            "next_day":   (day_number + 1) if day_passed and day_number < 7 else None,
        }

    @classmethod
    def get_week_summary(cls, user, week: Week) -> dict:
        week_concepts = Concept.objects.filter(week=week).values_list("id", flat=True)
        masteries     = ConceptMastery.objects.filter(user=user, concept_id__in=week_concepts)
        return {
            "total":       len(week_concepts),
            "mastered":    masteries.filter(status=ConceptMastery.STATUS_MASTERED).count(),
            "in_progress": masteries.filter(status=ConceptMastery.STATUS_IN_PROGRESS).count(),
            "weak":        masteries.filter(status=ConceptMastery.STATUS_WEAK).count(),
            "not_started": len(week_concepts) - masteries.count(),
        }


class GatingService:
    """
    Sequential unlocking — "until one is complete, don't unlock the next."

    Access rule (day-granular): a concept is unlocked only when the learner is
    enrolled AND every concept in an *earlier* day (within the same week) and in
    every *earlier* week of the course is mastered. Day 1 of Week 1 is the entry
    point. This is what makes the curriculum a guided path, not a buffet.
    """

    @classmethod
    def is_enrolled(cls, user, course) -> bool:
        from payments.models import Enrollment
        return Enrollment.objects.filter(user=user, course=course, is_active=True).exists()

    @classmethod
    def prior_concepts(cls, concept: Concept):
        """All concepts that must be mastered before `concept` becomes available."""
        course = concept.week.course
        return Concept.objects.filter(week__course=course).filter(
            models.Q(week__number__lt=concept.week.number) |
            models.Q(week__number=concept.week.number, day_introduced__lt=concept.day_introduced)
        )

    @classmethod
    def concept_access(cls, user, concept: Concept) -> dict:
        """Return {unlocked: bool, reason: str|None}."""
        course = concept.week.course
        if not cls.is_enrolled(user, course):
            return {"unlocked": False, "reason": "Enroll in this course to start learning."}

        prior_ids = list(cls.prior_concepts(concept).values_list("id", flat=True))
        if not prior_ids:
            return {"unlocked": True, "reason": None}

        mastered = ConceptMastery.objects.filter(
            user=user, concept_id__in=prior_ids, status=ConceptMastery.STATUS_MASTERED
        ).count()
        if mastered >= len(prior_ids):
            return {"unlocked": True, "reason": None}
        remaining = len(prior_ids) - mastered
        return {
            "unlocked": False,
            "reason": f"Master the {remaining} earlier concept(s) first to unlock this.",
        }


class LadderService:
    """
    The SPC ladder (one Concept per Week):
        Day 1   : lesson → Test Set A (N=10) → (later same day) Test Set B (N=10)
        Days 2-6: one cumulative Problem of the Day each (daily practice)
    Master the week (both sets passed + every daily problem passed) → next week.
    """

    # ── helpers ──────────────────────────────────────────────────────────
    @staticmethod
    def week_concept(week: Week):
        """The week's single teaching concept (Day-1 introduced)."""
        return week.concepts.order_by("day_introduced", "order").first()

    @staticmethod
    def _set_size():
        return int(getattr(settings, "LADDER_TEST_SET_SIZE", 10))

    @classmethod
    def _select_questions(cls, concept: Concept):
        ids = list(Question.objects.filter(concept=concept)
                   .order_by("difficulty", "id").values_list("id", flat=True))
        n = cls._set_size()
        if not ids:
            return []
        # Repeat to reach N if the bank is small (keeps the "10 questions" shape).
        out = []
        i = 0
        while len(out) < n and ids:
            out.append(ids[i % len(ids)])
            i += 1
        return out[:n]

    # ── lesson + test sets (Day 1) ───────────────────────────────────────
    @classmethod
    def complete_lesson(cls, user, concept: Concept):
        mastery, _ = ConceptMastery.objects.get_or_create(user=user, concept=concept)
        if not mastery.lesson_completed_at:
            mastery.lesson_completed_at = timezone.now()
            if mastery.status == ConceptMastery.STATUS_NOT_STARTED:
                mastery.status = ConceptMastery.STATUS_IN_PROGRESS
            mastery.save(update_fields=["lesson_completed_at", "status"])
        # Open Test Set A immediately.
        cls.get_or_create_set(user, concept, TestSession.SET_A)
        return mastery

    @classmethod
    def get_or_create_set(cls, user, concept: Concept, set_number: int) -> TestSession:
        session, created = TestSession.objects.get_or_create(
            user=user, concept=concept, set_number=set_number,
            defaults={"question_ids": cls._select_questions(concept),
                      "status": TestSession.STATUS_AVAILABLE if set_number == TestSession.SET_A
                                else TestSession.STATUS_LOCKED},
        )
        if created and not session.question_ids:
            session.question_ids = cls._select_questions(concept)
            session.save(update_fields=["question_ids"])
        return session

    @classmethod
    def schedule_set_b(cls, user, concept: Concept, scheduled_for):
        """After Set A passes, the learner picks a later time (same day) for Set B."""
        set_a = cls.get_or_create_set(user, concept, TestSession.SET_A)
        if not set_a.is_passed:
            return None, "Pass Set A before scheduling Set B."
        set_b = cls.get_or_create_set(user, concept, TestSession.SET_B)
        if set_b.is_passed:
            return set_b, "Set B already completed."
        set_b.scheduled_for = scheduled_for
        set_b.status = TestSession.STATUS_SCHEDULED
        set_b.save(update_fields=["scheduled_for", "status"])
        return set_b, None

    @classmethod
    def refresh_set_availability(cls, session: TestSession):
        """Promote a scheduled Set B to available once its time arrives."""
        if session.status == TestSession.STATUS_SCHEDULED and session.scheduled_for:
            if timezone.now() >= session.scheduled_for:
                session.status = TestSession.STATUS_AVAILABLE
                session.save(update_fields=["status"])
        return session

    @classmethod
    def submit_test_set(cls, user, session: TestSession, answers: dict):
        """
        Grade a whole set. `answers` maps question_id → answer payload.
        Records each as a UserAttempt (feeds mastery) and tallies the set.
        """
        cls.refresh_set_availability(session)
        if session.status not in (TestSession.STATUS_AVAILABLE, TestSession.STATUS_FAILED):
            return session, "This test set isn't available yet."

        session.started_at = session.started_at or timezone.now()
        correct = 0
        q_ids = session.question_ids or []
        for qid in q_ids:
            question = Question.objects.filter(pk=qid).first()
            if not question:
                continue
            payload = answers.get(str(qid)) or answers.get(qid) or {}
            attempt = UserAttempt.objects.create(user=user, question=question, answer=payload)
            ev = EvaluationService.evaluate(question=question, answer=payload, user=user)
            attempt.outcome = ev["outcome"]; attempt.score = ev["score"]
            attempt.ai_feedback = ev["feedback"]; attempt.evaluated_at = timezone.now()
            attempt.save()
            MasteryService.record(user, question, ev["outcome"] == UserAttempt.OUTCOME_CORRECT, ev["score"])
            if ev["outcome"] == UserAttempt.OUTCOME_CORRECT:
                correct += 1

        total = len(q_ids) or 1
        session.correct_count = correct
        session.score = round(correct / total * 100, 1)
        session.completed_at = timezone.now()
        session.status = (TestSession.STATUS_PASSED
                          if session.score >= TestSession.PASS_THRESHOLD
                          else TestSession.STATUS_FAILED)
        session.save()

        cls._maybe_master_concept(user, session.concept)
        return session, None

    @classmethod
    def _maybe_master_concept(cls, user, concept: Concept):
        """Concept (Day-1) is mastered when BOTH test sets pass."""
        sets = TestSession.objects.filter(user=user, concept=concept)
        passed = {s.set_number for s in sets if s.is_passed}
        if {TestSession.SET_A, TestSession.SET_B}.issubset(passed):
            mastery, _ = ConceptMastery.objects.get_or_create(user=user, concept=concept)
            if mastery.status != ConceptMastery.STATUS_MASTERED:
                mastery.status = ConceptMastery.STATUS_MASTERED
                mastery.mastered_at = timezone.now()
                mastery.save(update_fields=["status", "mastered_at"])
            return True
        return False

    # ── daily problems (Days 2-6) ────────────────────────────────────────
    @classmethod
    def _prev_step_passed_at(cls, user, week: Week, day_number: int):
        """When the prerequisite for `day_number` was completed (for the drip)."""
        if day_number <= 2:
            concept = cls.week_concept(week)
            sb = TestSession.objects.filter(
                user=user, concept=concept, set_number=TestSession.SET_B,
                status=TestSession.STATUS_PASSED).first()
            return sb.completed_at if sb else None
        prev = DayProblemSubmission.objects.filter(
            user=user, problem__week=week, problem__day_number=day_number - 1,
            status=DayProblemSubmission.STATUS_PASSED).first()
        return prev.evaluated_at if prev else None

    @classmethod
    def day_problem_access(cls, user, problem: DayProblem) -> dict:
        prereq_at = cls._prev_step_passed_at(user, problem.week, problem.day_number)
        if prereq_at is None:
            return {"unlocked": False, "reason": "Finish the previous day first."}
        drip = int(getattr(settings, "LADDER_DAILY_DRIP_HOURS", 20))
        ready_at = prereq_at + timedelta(hours=drip)
        if timezone.now() < ready_at:
            return {"unlocked": False, "reason": "Come back tomorrow — one problem a day.",
                    "available_at": ready_at.isoformat()}
        return {"unlocked": True, "reason": None}

    @classmethod
    def submit_day_problem(cls, user, problem: DayProblem, *, github_url="", code_submission=""):
        from .ai_evaluation import evaluate_day_problem
        from .github_service import fetch_repo_text, RepoError

        access = cls.day_problem_access(user, problem)
        if not access["unlocked"]:
            return None, access["reason"]

        sub, _ = DayProblemSubmission.objects.get_or_create(user=user, problem=problem)
        if sub.is_passed:
            return sub, "Already passed."
        sub.github_url = github_url or sub.github_url
        sub.code_submission = code_submission or sub.code_submission
        sub.status = DayProblemSubmission.STATUS_EVALUATING
        sub.submission_count += 1
        sub.submitted_at = timezone.now()
        sub.save()

        material = code_submission or ""
        if github_url:
            try:
                material = fetch_repo_text(github_url)
            except RepoError as exc:
                sub.status = DayProblemSubmission.STATUS_REVISION_NEEDED
                sub.ai_feedback = str(exc); sub.evaluated_at = timezone.now(); sub.save()
                return sub, str(exc)
            except Exception as exc:
                sub.status = DayProblemSubmission.STATUS_REVISION_NEEDED
                sub.ai_feedback = f"Could not fetch repo: {exc}"; sub.evaluated_at = timezone.now(); sub.save()
                return sub, sub.ai_feedback

        prior = cls._cumulative_concepts(problem.week) if problem.is_cumulative else []
        verdict = evaluate_day_problem(problem, material, prior)
        sub.ai_score = verdict
        sub.ai_feedback = verdict.get("feedback", "")
        sub.status = (DayProblemSubmission.STATUS_PASSED if verdict.get("passed")
                      else DayProblemSubmission.STATUS_REVISION_NEEDED)
        sub.evaluated_at = timezone.now()
        sub.save()
        return sub, None

    @staticmethod
    def _cumulative_concepts(week: Week):
        """Concept titles from week 1..N (for cumulative problem context)."""
        return list(Concept.objects.filter(
            week__course=week.course, week__number__lte=week.number
        ).order_by("week__number").values_list("title", flat=True))

    # ── week completion + unlock ─────────────────────────────────────────
    @classmethod
    def week_complete(cls, user, week: Week) -> bool:
        concept = cls.week_concept(week)
        if not concept:
            return False
        mastery = ConceptMastery.objects.filter(user=user, concept=concept).first()
        if not (mastery and mastery.status == ConceptMastery.STATUS_MASTERED):
            return False
        problems = DayProblem.objects.filter(week=week)
        if not problems.exists():
            return True
        passed = DayProblemSubmission.objects.filter(
            user=user, problem__in=problems, status=DayProblemSubmission.STATUS_PASSED
        ).count()
        return passed >= problems.count()

    @classmethod
    def week_unlocked(cls, user, week: Week) -> bool:
        if not GatingService.is_enrolled(user, week.course):
            return False
        prev = Week.objects.filter(course=week.course, number__lt=week.number).order_by("-number").first()
        return prev is None or cls.week_complete(user, prev)


class ProjectService:
    """
    Handles weekly capstone / "problem of the day" submissions: a learner
    submits a GitHub repo (or pasted code), we fetch + AI-assess it, and record
    a pass/revision verdict. Max 2 resubmissions when revision is needed.
    """

    MAX_SUBMISSIONS = 3  # initial + 2 resubmissions

    @classmethod
    def submit(cls, user, week, *, github_url="", code_submission="", title="", description=""):
        from .ai_evaluation import assess_project
        from .github_service import fetch_repo_text, RepoError

        project, _ = Project.objects.get_or_create(
            user=user, week=week,
            defaults={"title": title or f"Week {week.number} Project",
                      "description": description or week.summary},
        )

        if project.status == Project.STATUS_PASSED:
            return project, "This project is already passed."
        if project.submission_count >= cls.MAX_SUBMISSIONS and project.status != Project.STATUS_PASSED:
            return project, "You have used all your submission attempts for this project."

        if title:
            project.title = title
        if description:
            project.description = description
        project.github_url      = github_url or project.github_url
        project.code_submission = code_submission or project.code_submission
        project.status          = Project.STATUS_EVALUATING
        project.submission_count += 1
        project.submitted_at    = timezone.now()
        project.save()

        # Gather the material to assess.
        repo_text = code_submission or ""
        error = None
        if github_url:
            try:
                repo_text = fetch_repo_text(github_url)
            except RepoError as exc:
                error = str(exc)
            except Exception as exc:  # network etc.
                error = f"Could not fetch the repository: {exc}"

        if error:
            project.status = Project.STATUS_REVISION_NEEDED
            project.ai_feedback_summary = error
            project.evaluated_at = timezone.now()
            project.save()
            return project, error

        verdict = assess_project(project, repo_text)
        project.ai_score = verdict
        project.ai_feedback_summary = verdict.get("feedback", "")
        project.status = Project.STATUS_PASSED if verdict.get("passed") else Project.STATUS_REVISION_NEEDED
        project.evaluated_at = timezone.now()
        project.save()
        return project, None


class ClueService:
    """
    Serves the right clue level by attempt number.
    Phase 2: ClueAgent generates clues via Anthropic API and stores them
    on the Question before this service reads them.
    """

    DEFAULTS = {
        Question.TYPE_MCQ:          "Can you rule out any options? What does each one actually do?",
        Question.TYPE_CODE_SCRATCH: "Break the problem into steps. What's the very first thing that needs to happen?",
        Question.TYPE_DEBUG:        "What is the code supposed to do? Where does actual behaviour differ from expected?",
        Question.TYPE_EXTEND:       "What does the existing code handle well? What scenario isn't covered yet?",
        Question.TYPE_EXPLAIN:      "Trace the code line by line. What does each line produce or change?",
        Question.TYPE_DESIGN:       "What are the main components? How would they talk to each other?",
        Question.TYPE_REVIEW:       "What happens with unexpected or empty input? Are there edge cases unhandled?",
        Question.TYPE_SPOT_BUG:     "Walk through with a simple example. At which exact line does it go wrong?",
        Question.TYPE_REFACTOR:     "What makes this hard to read or change? What would make it immediately clearer?",
        Question.TYPE_EDGE_CASE:    "What assumptions does this system make? Which ones could an attacker violate?",
    }

    @classmethod
    def get_clue(cls, question: Question, attempt_number: int) -> dict:
        if attempt_number <= 1:
            return {
                "level":              "socratic",
                "label":              "Think about this...",
                "text":               question.socratic_clue or cls.DEFAULTS.get(question.question_type, "What is this question really testing?"),
                "attempts_remaining": 2,
            }
        elif attempt_number == 2:
            return {
                "level":              "scaffolded",
                "label":              "Here's a scaffold...",
                "text":               question.scaffolded_hint or "Review the concept. A detailed scaffold will be AI-generated in Phase 2.",
                "attempts_remaining": 1,
            }
        else:
            rubric   = question.answer_rubric
            approach = rubric.get("approach") or rubric.get("expected_approach", "")
            text     = question.micro_explanation or (
                f"Key approach: {approach}" if approach
                else "This concept is flagged for extra practice and will resurface in upcoming tests."
            )
            return {
                "level":                  "explanation",
                "label":                  "Let's break this down...",
                "text":                   text,
                "attempts_remaining":     0,
                "concept_will_resurface": True,
            }