from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.shortcuts import get_object_or_404

from .models import (
    Course, Week, Concept, Question,
    UserAttempt, ConceptMastery, DayProgress, ConceptLesson,
)
from .serializers import (
    CourseListSerializer, CourseDetailSerializer,
    WeekSerializer, ConceptSerializer,
    QuestionSerializer, QuestionWithClueSerializer,
    SubmitAttemptSerializer, UserAttemptSerializer,
    ConceptMasterySerializer, DayProgressSerializer,
    ConceptLessonSerializer,
)
from .services import EvaluationService, MasteryService, ClueService


# ─────────────────────────────────────────────
# COURSES
# ─────────────────────────────────────────────

class CourseListView(generics.ListAPIView):
    """GET /api/curriculum/courses/"""
    serializer_class   = CourseListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs      = Course.objects.filter(is_published=True).select_related("subject_area")
        subject = self.request.query_params.get("subject")
        if subject:
            qs = qs.filter(subject_area__name=subject)
        return qs


class CourseDetailView(generics.RetrieveAPIView):
    """GET /api/curriculum/courses/<id>/"""
    serializer_class   = CourseDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Course.objects.filter(is_published=True).prefetch_related(
            "weeks", "weeks__concepts"
        ).select_related("subject_area")


class WeekDetailView(generics.RetrieveAPIView):
    """GET /api/curriculum/weeks/<id>/"""
    serializer_class   = WeekSerializer
    permission_classes = [IsAuthenticated]
    queryset           = Week.objects.prefetch_related("concepts")


class ConceptDetailView(generics.RetrieveAPIView):
    """GET /api/curriculum/concepts/<id>/"""
    serializer_class   = ConceptSerializer
    permission_classes = [IsAuthenticated]
    queryset           = Concept.objects.select_related("week")


# ─────────────────────────────────────────────
# QUESTIONS
# ─────────────────────────────────────────────

class ConceptQuestionsView(APIView):
    """
    GET /api/curriculum/concepts/<concept_id>/questions/?difficulty=1&day=1

    day=1  → all types including MCQ
    day=2+ → practicals only, no MCQ
    Already-correct questions are excluded so students always get fresh ones.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, concept_id):
        try:
            concept = Concept.objects.get(pk=concept_id)
        except Concept.DoesNotExist:
            return Response({"detail": "Concept not found."}, status=status.HTTP_404_NOT_FOUND)

        # Sequential gating: the concept must be unlocked for this learner.
        from .services import GatingService
        access = GatingService.concept_access(request.user, concept)
        if not access["unlocked"]:
            return Response({"detail": access["reason"], "locked": True},
                            status=status.HTTP_403_FORBIDDEN)

        difficulty = request.query_params.get("difficulty")
        day        = int(request.query_params.get("day", 1))

        qs = Question.objects.filter(concept=concept)
        if difficulty:
            qs = qs.filter(difficulty=int(difficulty))
        if day > 1:
            qs = qs.exclude(question_type=Question.TYPE_MCQ)

        already_correct = UserAttempt.objects.filter(
            user=request.user,
            question__in=qs,
            outcome=UserAttempt.OUTCOME_CORRECT,
        ).values_list("question_id", flat=True)

        qs = qs.exclude(pk__in=already_correct)
        return Response(QuestionSerializer(qs, many=True).data)


# ─────────────────────────────────────────────
# ATTEMPTS
# ─────────────────────────────────────────────

class SubmitAttemptView(APIView):
    """
    POST /api/curriculum/attempts/submit/

    The core learning loop in one endpoint:
      1. Validate submission
      2. Evaluate (EvaluationService)
      3. Update mastery (MasteryService — 80/3 rule)
      4. Attach clue on failure (ClueService)
      5. Check day completion and unlock next day
      6. Return everything the frontend needs in one response
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SubmitAttemptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        question = serializer.validated_data["question_id"]  # resolved to Question obj
        answer   = serializer.validated_data["answer"]
        user     = request.user

        # Sequential gating: can't answer a locked concept's questions.
        from .services import GatingService
        access = GatingService.concept_access(user, question.concept)
        if not access["unlocked"]:
            return Response({"detail": access["reason"], "locked": True},
                            status=status.HTTP_403_FORBIDDEN)

        attempt = UserAttempt.objects.create(user=user, question=question, answer=answer)

        evaluation = EvaluationService.evaluate(question=question, answer=answer, user=user)

        attempt.outcome      = evaluation["outcome"]
        attempt.score        = evaluation["score"]
        attempt.ai_feedback  = evaluation["feedback"]
        attempt.evaluated_at = timezone.now()
        attempt.save()

        mastery = MasteryService.record(
            user=user,
            question=question,
            is_correct=(evaluation["outcome"] == UserAttempt.OUTCOME_CORRECT),
            score=evaluation["score"],
        )

        response_data = {
            "attempt":    UserAttemptSerializer(attempt).data,
            "mastery":    ConceptMasterySerializer(mastery).data,
            "passed":     evaluation["outcome"] == UserAttempt.OUTCOME_CORRECT,
        }

        if evaluation["outcome"] != UserAttempt.OUTCOME_CORRECT:
            clue_data = ClueService.get_clue(question=question, attempt_number=attempt.attempt_number)
            response_data["clue"] = clue_data

            update_fields = []
            if attempt.attempt_number == 1:
                attempt.clue_used = True;        update_fields.append("clue_used")
            elif attempt.attempt_number == 2:
                attempt.hint_used = True;        update_fields.append("hint_used")
            else:
                attempt.explanation_used = True; update_fields.append("explanation_used")
            attempt.save(update_fields=update_fields)

        response_data["day_status"] = MasteryService.check_day_completion(
            user=user, concept=question.concept
        )

        return Response(response_data, status=status.HTTP_200_OK)


class AttemptHistoryView(generics.ListAPIView):
    """GET /api/curriculum/attempts/?concept_id=<id>"""
    serializer_class   = UserAttemptSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = UserAttempt.objects.filter(
            user=self.request.user
        ).select_related("question", "question__concept").order_by("-submitted_at")

        concept_id = self.request.query_params.get("concept_id")
        if concept_id:
            qs = qs.filter(question__concept_id=concept_id)
        return qs


# ─────────────────────────────────────────────
# CLUES
# ─────────────────────────────────────────────

class ClueView(APIView):
    """GET /api/curriculum/questions/<question_id>/clue/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, question_id):
        try:
            question = Question.objects.get(pk=question_id)
        except Question.DoesNotExist:
            return Response({"detail": "Question not found."}, status=status.HTTP_404_NOT_FOUND)

        attempt_number = UserAttempt.objects.filter(
            user=request.user, question=question
        ).count()

        return Response({
            "question": QuestionWithClueSerializer(question, context={"attempt_number": attempt_number}).data,
            "clue":     ClueService.get_clue(question=question, attempt_number=attempt_number),
        })


# ─────────────────────────────────────────────
# MASTERY
# ─────────────────────────────────────────────

class ConceptMasteryView(APIView):
    """
    GET /api/curriculum/mastery/              → all user masteries
    GET /api/curriculum/mastery/?concept_id=5 → single concept
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        concept_id = request.query_params.get("concept_id")

        if concept_id:
            try:
                mastery = ConceptMastery.objects.get(user=request.user, concept_id=concept_id)
                return Response(ConceptMasterySerializer(mastery).data)
            except ConceptMastery.DoesNotExist:
                return Response({
                    "concept": int(concept_id), "status": "not_started",
                    "consecutive_correct_hard": 0, "highest_difficulty_passed": 0,
                    "total_attempts": 0, "total_correct": 0, "total_failures": 0,
                    "best_score": 0.0, "accuracy": 0.0, "mastered_at": None,
                })

        masteries = ConceptMastery.objects.filter(
            user=request.user
        ).select_related("concept").order_by("concept__week__number", "concept__day_introduced")
        return Response(ConceptMasterySerializer(masteries, many=True).data)


class WeakConceptsView(generics.ListAPIView):
    """GET /api/curriculum/mastery/weak/"""
    serializer_class   = ConceptMasterySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ConceptMastery.objects.filter(
            user=self.request.user,
            status=ConceptMastery.STATUS_WEAK,
        ).select_related("concept")


# ─────────────────────────────────────────────
# DAY PROGRESS
# ─────────────────────────────────────────────

class DayProgressView(APIView):
    """GET /api/curriculum/progress/week/<week_id>/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, week_id):
        try:
            week = Week.objects.get(pk=week_id)
        except Week.DoesNotExist:
            return Response({"detail": "Week not found."}, status=status.HTTP_404_NOT_FOUND)

        progresses = DayProgress.objects.filter(user=request.user, week=week).order_by("day_number")

        if not progresses.exists():
            DayProgress.objects.create(
                user=request.user, week=week, day_number=1,
                status=DayProgress.STATUS_UNLOCKED, unlocked_at=timezone.now(),
            )
            progresses = DayProgress.objects.filter(user=request.user, week=week)

        return Response({
            "week_id":    week_id,
            "summary":    MasteryService.get_week_summary(user=request.user, week=week),
            "days":       DayProgressSerializer(progresses, many=True).data,
        })


# ─────────────────────────────────────────────
# CONCEPT LESSON (AI tutor text + audio)
# ─────────────────────────────────────────────

class ConceptLessonView(APIView):
    """GET /api/curriculum/concepts/<concept_id>/lesson/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, concept_id):
        concept = get_object_or_404(Concept, pk=concept_id)
        try:
            lesson = concept.lesson
        except ConceptLesson.DoesNotExist:
            return Response({
                "concept_id":    concept.id,
                "concept_title": concept.title,
                "tutor_script":  None,
                "audio_url":     None,
                "generated_at":  None,
            })
        return Response(
            ConceptLessonSerializer(lesson, context={"request": request}).data
        )


# ─────────────────────────────────────────────
# PROJECTS (weekly capstone / problem of the day)
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
# THE LADDER — Day-1 test sets + Days 2-6 daily problems
# ─────────────────────────────────────────────

def _test_set_payload(session, include_questions=False):
    data = {
        "set_number": session.set_number, "status": session.status,
        "score": session.score, "correct_count": session.correct_count,
        "total": len(session.question_ids or []),
        "scheduled_for": session.scheduled_for.isoformat() if session.scheduled_for else None,
    }
    if include_questions and session.status in ("available", "failed"):
        qs = Question.objects.filter(pk__in=session.question_ids or [])
        by_id = {q.id: q for q in qs}
        ordered = [by_id[i] for i in session.question_ids if i in by_id]
        data["questions"] = QuestionSerializer(ordered, many=True).data
    return data


class WeekLadderView(APIView):
    """
    GET /api/curriculum/weeks/<week_id>/ladder/
    The full week state for the gated UI: lesson, both test sets, daily problems,
    and whether the week is complete / unlocked.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, week_id):
        from .services import LadderService, GatingService
        from .models import TestSession, DayProblem, DayProblemSubmission, ConceptMastery
        week = get_object_or_404(Week, pk=week_id)
        user = request.user
        concept = LadderService.week_concept(week)

        unlocked = LadderService.week_unlocked(user, week)
        mastery = ConceptMastery.objects.filter(user=user, concept=concept).first() if concept else None

        set_a = LadderService.get_or_create_set(user, concept, TestSession.SET_A) if (concept and unlocked and mastery and mastery.lesson_completed_at) else None
        set_b = None
        if set_a:
            set_b = LadderService.get_or_create_set(user, concept, TestSession.SET_B)
            LadderService.refresh_set_availability(set_b)

        problems = []
        for p in DayProblem.objects.filter(week=week):
            access = LadderService.day_problem_access(user, p)
            sub = DayProblemSubmission.objects.filter(user=user, problem=p).first()
            problems.append({
                "id": p.id, "day_number": p.day_number, "title": p.title,
                "prompt": p.prompt, "starter_code": p.starter_code,
                "is_cumulative": p.is_cumulative,
                "unlocked": access["unlocked"], "lock_reason": access["reason"],
                "available_at": access.get("available_at"),
                "status": sub.status if sub else None,
                "feedback": sub.ai_feedback if sub else None,
                "score": (sub.ai_score or {}).get("total") if sub and sub.ai_score else None,
            })

        return Response({
            "week_id": week.id, "number": week.number, "title": week.title,
            "summary": week.summary,
            "unlocked": unlocked,
            "concept": {"id": concept.id, "title": concept.title} if concept else None,
            "lesson_completed": bool(mastery and mastery.lesson_completed_at),
            "concept_mastered": bool(mastery and mastery.status == ConceptMastery.STATUS_MASTERED),
            "test_set_a": _test_set_payload(set_a) if set_a else None,
            "test_set_b": _test_set_payload(set_b) if set_b else None,
            "daily_problems": problems,
            "week_complete": LadderService.week_complete(user, week),
        })


class LessonCompleteView(APIView):
    """POST /api/curriculum/concepts/<concept_id>/lesson/complete/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, concept_id):
        from .services import LadderService, GatingService
        concept = get_object_or_404(Concept, pk=concept_id)
        if not GatingService.is_enrolled(request.user, concept.week.course):
            return Response({"detail": "Enroll first."}, status=403)
        LadderService.complete_lesson(request.user, concept)
        return Response({"lesson_completed": True})


class TestSetView(APIView):
    """GET /api/curriculum/concepts/<concept_id>/test-set/<set_number>/ — questions when available."""
    permission_classes = [IsAuthenticated]

    def get(self, request, concept_id, set_number):
        from .services import LadderService, GatingService
        from .models import TestSession
        concept = get_object_or_404(Concept, pk=concept_id)
        if not GatingService.is_enrolled(request.user, concept.week.course):
            return Response({"detail": "Enroll first."}, status=403)
        session = LadderService.get_or_create_set(request.user, concept, int(set_number))
        LadderService.refresh_set_availability(session)
        return Response(_test_set_payload(session, include_questions=True))


class TestSetSubmitView(APIView):
    """POST /api/curriculum/concepts/<concept_id>/test-set/<set_number>/submit/  body: {answers: {qid: payload}}"""
    permission_classes = [IsAuthenticated]

    def post(self, request, concept_id, set_number):
        from .services import LadderService
        from .models import TestSession
        concept = get_object_or_404(Concept, pk=concept_id)
        session = LadderService.get_or_create_set(request.user, concept, int(set_number))
        answers = request.data.get("answers", {})
        session, error = LadderService.submit_test_set(request.user, session, answers)
        payload = _test_set_payload(session)
        if error:
            payload["error"] = error
        return Response(payload)


class TestSetScheduleView(APIView):
    """POST /api/curriculum/concepts/<concept_id>/test-set/schedule-b/  body: {scheduled_for}"""
    permission_classes = [IsAuthenticated]

    def post(self, request, concept_id):
        from .services import LadderService
        from django.utils.dateparse import parse_datetime
        concept = get_object_or_404(Concept, pk=concept_id)
        when = parse_datetime(request.data.get("scheduled_for", ""))
        if not when:
            return Response({"detail": "Provide a valid scheduled_for datetime."}, status=400)
        session, error = LadderService.schedule_set_b(request.user, concept, when)
        if error and session is None:
            return Response({"detail": error}, status=400)
        return Response(_test_set_payload(session) | ({"error": error} if error else {}))


class DayProblemSubmitView(APIView):
    """POST /api/curriculum/day-problems/<problem_id>/submit/  body: {github_url?, code_submission?}"""
    permission_classes = [IsAuthenticated]

    def post(self, request, problem_id):
        from .services import LadderService
        from .models import DayProblem
        problem = get_object_or_404(DayProblem, pk=problem_id)
        sub, error = LadderService.submit_day_problem(
            request.user, problem,
            github_url=request.data.get("github_url", ""),
            code_submission=request.data.get("code_submission", ""),
        )
        if sub is None:
            return Response({"detail": error, "locked": True}, status=403)
        return Response({
            "status": sub.status, "feedback": sub.ai_feedback,
            "score": (sub.ai_score or {}).get("total"),
            "submission_count": sub.submission_count,
            **({"error": error} if error else {}),
        })


class CourseOutlineView(APIView):
    """
    GET /api/curriculum/courses/<pk>/outline/

    The Udemy-style curriculum with SPC gating: every concept carries an
    `unlocked` + `mastered` flag for the current learner, so clients can render
    locks and progress without guessing the rule.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        from .services import GatingService
        course = get_object_or_404(Course, pk=pk, is_published=True)
        enrolled = GatingService.is_enrolled(request.user, course)

        mastered_ids = set(ConceptMastery.objects.filter(
            user=request.user, concept__week__course=course,
            status=ConceptMastery.STATUS_MASTERED,
        ).values_list("concept_id", flat=True))

        weeks_out = []
        for week in course.weeks.prefetch_related("concepts").all():
            concepts_out = []
            week_concepts = list(week.concepts.all())
            for c in week_concepts:
                access = GatingService.concept_access(request.user, c)
                concepts_out.append({
                    "id": c.id, "title": c.title, "day_introduced": c.day_introduced,
                    "order": c.order,
                    "unlocked": access["unlocked"],
                    "mastered": c.id in mastered_ids,
                    "lock_reason": access["reason"],
                })
            week_mastered = all(c["mastered"] for c in concepts_out) if concepts_out else False
            weeks_out.append({
                "id": week.id, "number": week.number, "title": week.title,
                "summary": week.summary,
                "completed": week_mastered,
                "concepts": concepts_out,
            })

        return Response({
            "course_id": course.id, "title": course.title,
            "enrolled": enrolled, "weeks": weeks_out,
        })


class ProjectListView(generics.ListAPIView):
    """GET /api/curriculum/projects/?week_id=<id> — caller's project(s)."""
    serializer_class   = None  # set below to avoid early import
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        from .serializers import ProjectSerializer
        return ProjectSerializer

    def get_queryset(self):
        from .models import Project
        qs = Project.objects.filter(user=self.request.user).select_related("week")
        week_id = self.request.query_params.get("week_id")
        if week_id:
            qs = qs.filter(week_id=week_id)
        return qs


class ProjectSubmitView(APIView):
    """
    POST /api/curriculum/projects/submit/
    body: {week_id, github_url?, code_submission?, title?, description?}

    Fetches the GitHub repo (or pasted code), AI-assesses it, and returns the
    verdict (passed / revision_needed) with feedback.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .serializers import ProjectSubmitSerializer, ProjectSerializer
        from .services import ProjectService

        serializer = ProjectSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        week = get_object_or_404(Week, pk=data["week_id"])
        project, error = ProjectService.submit(
            user=request.user, week=week,
            github_url=data.get("github_url", ""),
            code_submission=data.get("code_submission", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
        )
        body = ProjectSerializer(project).data
        if error:
            body["error"] = error
        return Response(body)