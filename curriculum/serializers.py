from rest_framework import serializers

from auth_manager.serializers import PublicUserSerializer
from .models import (
    SubjectArea, Course, Week, Concept,
    Question, UserAttempt, ConceptMastery, DayProgress,
    ConceptLesson, Project,
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


class _CourseEnrollmentMixin(serializers.ModelSerializer):
    """Shared computed fields for course serializers (mobile-facing)."""
    subject_area = SubjectAreaSerializer(read_only=True)
    thumbnail    = serializers.SerializerMethodField()
    is_free      = serializers.SerializerMethodField()
    is_enrolled  = serializers.SerializerMethodField()
    instructor_name = serializers.CharField(source="instructor.username", read_only=True, default=None)

    def get_thumbnail(self, obj):
        request = self.context.get("request")
        if obj.thumbnail and request:
            return request.build_absolute_uri(obj.thumbnail.url)
        return obj.thumbnail.url if obj.thumbnail else None

    def get_is_free(self, obj):
        return not obj.price or obj.price <= 0

    def get_is_enrolled(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.enrollments.filter(user=request.user, is_active=True).exists()


class CourseListSerializer(_CourseEnrollmentMixin):
    """Lightweight — list views only."""

    class Meta:
        model  = Course
        fields = ("id", "title", "description", "subject_area", "price", "is_free",
                  "language", "thumbnail", "instructor_name", "is_enrolled")


class CourseDetailSerializer(_CourseEnrollmentMixin):
    weeks = WeekSerializer(many=True, read_only=True)

    class Meta:
        model  = Course
        fields = ("id", "title", "description", "subject_area", "price", "is_free",
                  "language", "thumbnail", "instructor_name", "is_enrolled", "weeks")


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


# ─────────────────────────────────────────────
# LESSON (AI-generated tutor content)
# ─────────────────────────────────────────────

class ConceptLessonSerializer(serializers.ModelSerializer):
    audio_url = serializers.SerializerMethodField()

    class Meta:
        model  = ConceptLesson
        fields = ("concept", "tutor_script", "audio_url", "generated_at")
        read_only_fields = fields

    def get_audio_url(self, obj):
        request = self.context.get('request')
        if obj.audio_file and request:
            return request.build_absolute_uri(obj.audio_file.url)
        return None


# ─────────────────────────────────────────────
# PROJECTS (weekly capstone / problem of the day)
# ─────────────────────────────────────────────

class ProjectSerializer(serializers.ModelSerializer):
    can_resubmit = serializers.BooleanField(read_only=True)
    total_score  = serializers.IntegerField(read_only=True)

    class Meta:
        model  = Project
        fields = ("id", "week", "title", "description", "github_url", "code_submission",
                  "status", "submission_count", "ai_score", "ai_feedback_summary",
                  "total_score", "can_resubmit", "submitted_at", "evaluated_at")
        read_only_fields = ("id", "status", "submission_count", "ai_score",
                            "ai_feedback_summary", "submitted_at", "evaluated_at")


class ProjectSubmitSerializer(serializers.Serializer):
    week_id         = serializers.IntegerField()
    github_url      = serializers.URLField(required=False, allow_blank=True)
    code_submission = serializers.CharField(required=False, allow_blank=True)
    title           = serializers.CharField(required=False, allow_blank=True)
    description     = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if not attrs.get("github_url") and not attrs.get("code_submission"):
            raise serializers.ValidationError("Provide a GitHub URL or paste your code.")
        return attrs