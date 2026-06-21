from rest_framework import serializers

from auth_manager.serializers import PublicUserSerializer
from .models import (
    SubjectArea, Course, Week, Concept,
    Question, UserAttempt, ConceptMastery, DayProgress,
)


# ─────────────────────────────────────────────
# CURRICULUM
# ─────────────────────────────────────────────

class SubjectAreaSerializer(serializers.ModelSerializer):
    class Meta:
        model  = SubjectArea
        fields = ("id", "name", "display_name", "description", "icon")


class ConceptSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Concept
        fields = (
            "id", "title", "description",
            "video_url", "video_duration_seconds",
            "day_introduced", "order",
        )


class WeekSerializer(serializers.ModelSerializer):
    concepts = ConceptSerializer(many=True, read_only=True)

    class Meta:
        model  = Week
        fields = ("id", "number", "title", "summary", "concepts")


class CourseListSerializer(serializers.ModelSerializer):
    """Lightweight — list views only."""
    subject_area = SubjectAreaSerializer(read_only=True)

    class Meta:
        model  = Course
        fields = ("id", "title", "description", "subject_area")


class CourseDetailSerializer(serializers.ModelSerializer):
    subject_area = SubjectAreaSerializer(read_only=True)
    weeks        = WeekSerializer(many=True, read_only=True)

    class Meta:
        model  = Course
        fields = ("id", "title", "description", "subject_area", "weeks")


# ─────────────────────────────────────────────
# QUESTIONS
# ─────────────────────────────────────────────

class QuestionSerializer(serializers.ModelSerializer):
    """Student-facing. No rubric, no clues."""
    class Meta:
        model  = Question
        fields = ("id", "question_type", "difficulty", "content", "is_practical")


class QuestionWithClueSerializer(serializers.ModelSerializer):
    """Returned after a failed attempt."""
    clue = serializers.SerializerMethodField()

    class Meta:
        model  = Question
        fields = ("id", "question_type", "difficulty", "content", "clue")

    def get_clue(self, obj):
        attempt_number = self.context.get("attempt_number", 1)
        if attempt_number <= 1:
            return {"level": "socratic",     "text": obj.socratic_clue}
        elif attempt_number == 2:
            return {"level": "scaffolded",   "text": obj.scaffolded_hint}
        else:
            return {"level": "explanation",  "text": obj.micro_explanation}


# ─────────────────────────────────────────────
# ATTEMPTS
# ─────────────────────────────────────────────

class SubmitAttemptSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    answer      = serializers.JSONField()

    def validate_question_id(self, value):
        try:
            return Question.objects.get(pk=value)
        except Question.DoesNotExist:
            raise serializers.ValidationError("Question not found.")


class UserAttemptSerializer(serializers.ModelSerializer):
    question = QuestionSerializer(read_only=True)

    class Meta:
        model  = UserAttempt
        fields = (
            "id", "question", "answer", "outcome",
            "ai_feedback", "score", "attempt_number",
            "clue_used", "hint_used", "explanation_used",
            "submitted_at", "evaluated_at",
        )
        read_only_fields = fields


# ─────────────────────────────────────────────
# MASTERY
# ─────────────────────────────────────────────

class ConceptMasterySerializer(serializers.ModelSerializer):
    concept_title  = serializers.CharField(source="concept.title", read_only=True)
    accuracy       = serializers.FloatField(read_only=True)
    total_failures = serializers.IntegerField(read_only=True)

    class Meta:
        model  = ConceptMastery
        fields = (
            "id", "concept", "concept_title", "status",
            "consecutive_correct_hard", "highest_difficulty_passed",
            "total_attempts", "total_correct", "total_failures",
            "best_score", "accuracy",
            "first_attempted_at", "last_attempted_at", "mastered_at",
        )
        read_only_fields = fields


class DayProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model        = DayProgress
        fields       = ("id", "day_number", "status", "unlocked_at", "passed_at")
        read_only_fields = fields