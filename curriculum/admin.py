from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import (
    SubjectArea, Course, Week, Concept,
    Question, UserAttempt, ConceptMastery,
    DayProgress, ScheduledTest, Project, BuildLog,
)


@admin.register(SubjectArea)
class SubjectAreaAdmin(admin.ModelAdmin):
    list_display = ("display_name", "name")


class WeekInline(admin.TabularInline):
    model  = Week
    extra  = 1
    fields = ("number", "title")


class ConceptInline(admin.TabularInline):
    model  = Concept
    extra  = 1
    fields = ("day_introduced", "title", "video_url", "video_duration_seconds", "order")


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display  = ("title", "subject_area", "is_published", "created_at")
    list_filter   = ("subject_area", "is_published")
    search_fields = ("title",)
    inlines       = [WeekInline]


@admin.register(Week)
class WeekAdmin(admin.ModelAdmin):
    list_display = ("__str__", "course", "number")
    list_filter  = ("course",)
    inlines      = [ConceptInline]


@admin.register(Concept)
class ConceptAdmin(admin.ModelAdmin):
    list_display  = ("title", "week", "day_introduced", "video_duration_seconds")
    list_filter   = ("week__course", "day_introduced")
    search_fields = ("title",)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display    = ("__str__", "concept", "question_type", "difficulty", "is_ai_generated", "created_at")
    list_filter     = ("question_type", "difficulty", "is_ai_generated")
    search_fields   = ("concept__title",)
    readonly_fields = ("created_at",)


@admin.register(UserAttempt)
class UserAttemptAdmin(admin.ModelAdmin):
    list_display    = ("user", "question", "attempt_number", "outcome", "score", "submitted_at")
    list_filter     = ("outcome", "clue_used", "hint_used", "explanation_used")
    search_fields   = ("user__username",)
    readonly_fields = ("attempt_number", "submitted_at", "evaluated_at")


@admin.register(ConceptMastery)
class ConceptMasteryAdmin(admin.ModelAdmin):
    list_display    = ("user", "concept", "status", "accuracy", "consecutive_correct_hard", "total_attempts", "mastered_at")
    list_filter     = ("status", "concept__week__course")
    search_fields   = ("user__username", "concept__title")
    readonly_fields = ("first_attempted_at", "last_attempted_at", "mastered_at")


@admin.register(DayProgress)
class DayProgressAdmin(admin.ModelAdmin):
    list_display = ("user", "week", "day_number", "status", "passed_at")
    list_filter  = ("status",)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display    = ("user", "week", "title", "status", "total_score", "submission_count")
    list_filter     = ("status",)
    readonly_fields = ("submitted_at", "evaluated_at", "created_at")