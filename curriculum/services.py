from django.utils import timezone

from .models import (
    Question, UserAttempt, ConceptMastery, DayProgress, Concept, Week,
)


class EvaluationService:
    """
    Week 1: MCQ auto-marks, code returns stub.
    Phase 2: _evaluate_stub() replaced with Anthropic API call.
    Interface never changes — views don't care how evaluation happens.
    """

    @classmethod
    def evaluate(cls, question: Question, answer: dict, user) -> dict:
        if question.question_type == Question.TYPE_MCQ:
            return cls._evaluate_mcq(question, answer)
        return cls._evaluate_stub(question, answer)

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

    @classmethod
    def _evaluate_stub(cls, question: Question, answer: dict) -> dict:
        """Placeholder. Phase 2 wires Anthropic API here."""
        return {
            "outcome":  UserAttempt.OUTCOME_PARTIAL,
            "score":    0.0,
            "feedback": "Answer recorded. AI evaluation coming in Phase 2.",
        }


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