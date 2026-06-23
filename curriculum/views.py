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