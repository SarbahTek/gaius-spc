from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone


# ── Shorthand — curriculum never imports from accounts directly ────────
def user_fk(**kwargs):
    return models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        **kwargs,
    )


# ─────────────────────────────────────────────
# CURRICULUM STRUCTURE
# ─────────────────────────────────────────────

class SubjectArea(models.Model):
    AREA_CHOICES = [
        ("programming",   "Programming"),
        ("aws",           "AWS & Cloud"),
        ("system_design", "System Design & Architecture"),
        ("ml_ai",         "ML & AI"),
        ("blockchain",    "Blockchain"),
        ("ai_agents",     "AI Agents"),
        ("devops",        "DevOps"),
        ("security",      "Security"),
    ]
    name         = models.CharField(max_length=50, choices=AREA_CHOICES, unique=True)
    display_name = models.CharField(max_length=100)
    description  = models.TextField(blank=True)
    icon         = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return self.display_name


class Course(models.Model):
    title        = models.CharField(max_length=200)
    subject_area = models.ForeignKey(SubjectArea, on_delete=models.PROTECT, related_name="courses")
    description  = models.TextField()
    is_published = models.BooleanField(default=False)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title


class Week(models.Model):
    course  = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="weeks")
    number  = models.PositiveIntegerField()
    title   = models.CharField(max_length=200)
    summary = models.TextField(blank=True)

    class Meta:
        unique_together = ("course", "number")
        ordering        = ["number"]

    def __str__(self):
        return f"{self.course.title} — Week {self.number}: {self.title}"


class Concept(models.Model):
    week           = models.ForeignKey(Week, on_delete=models.CASCADE, related_name="concepts")
    day_introduced = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    title                  = models.CharField(max_length=200)
    description            = models.TextField()
    video_url              = models.URLField(blank=True)
    video_duration_seconds = models.PositiveIntegerField(default=0)
    order                  = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["week", "day_introduced", "order"]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.video_duration_seconds > 300:
            raise ValidationError(
                {"video_duration_seconds": "Videos must be 5 minutes or under."}
            )

    def __str__(self):
        return f"Week {self.week.number} / Day {self.day_introduced} — {self.title}"

    @property
    def all_prior_concepts(self):
        """All concepts before this one in the course. Used by Question Generator."""
        return Concept.objects.filter(
            week__course=self.week.course,
            week__number__lte=self.week.number,
        ).exclude(pk=self.pk).order_by("week__number", "day_introduced", "order")


# ─────────────────────────────────────────────
# QUESTIONS
# ─────────────────────────────────────────────

class Question(models.Model):

    TYPE_CODE_SCRATCH = "code_scratch"
    TYPE_DEBUG        = "debug"
    TYPE_EXTEND       = "extend"
    TYPE_EXPLAIN      = "explain"
    TYPE_DESIGN       = "design"
    TYPE_REVIEW       = "review"
    TYPE_MCQ          = "mcq"
    TYPE_SPOT_BUG     = "spot_bug"
    TYPE_REFACTOR     = "refactor"
    TYPE_EDGE_CASE    = "edge_case"

    QUESTION_TYPE_CHOICES = [
        (TYPE_CODE_SCRATCH, "Code from scratch"),
        (TYPE_DEBUG,        "Debug this"),
        (TYPE_EXTEND,       "Extend this"),
        (TYPE_EXPLAIN,      "Explain your code"),
        (TYPE_DESIGN,       "Design this"),
        (TYPE_REVIEW,       "Review this"),
        (TYPE_MCQ,          "Multiple choice"),
        (TYPE_SPOT_BUG,     "Spot the bug"),
        (TYPE_REFACTOR,     "Refactor this"),
        (TYPE_EDGE_CASE,    "Security / edge case"),
    ]

    DIFFICULTY_EASY   = 1
    DIFFICULTY_MEDIUM = 2
    DIFFICULTY_HARD   = 3

    DIFFICULTY_CHOICES = [
        (DIFFICULTY_EASY,   "Easy"),
        (DIFFICULTY_MEDIUM, "Medium"),
        (DIFFICULTY_HARD,   "Hard"),
    ]

    concept            = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name="questions")
    generated_for_week = models.PositiveIntegerField()
    question_type      = models.CharField(max_length=20, choices=QUESTION_TYPE_CHOICES)
    difficulty         = models.IntegerField(choices=DIFFICULTY_CHOICES)

    # Never expose answer_rubric or clues to the student
    content       = models.JSONField()
    answer_rubric = models.JSONField()

    # Clue chain — populated lazily by ClueAgent on first failure
    socratic_clue     = models.TextField(blank=True)
    scaffolded_hint   = models.TextField(blank=True)
    micro_explanation = models.TextField(blank=True)

    is_ai_generated = models.BooleanField(default=True)
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["concept", "difficulty"]

    def __str__(self):
        return f"[{self.get_difficulty_display()}] {self.get_question_type_display()} — {self.concept.title}"

    @property
    def is_practical(self):
        return self.question_type != self.TYPE_MCQ


# ─────────────────────────────────────────────
# USER ATTEMPTS
# ─────────────────────────────────────────────

class UserAttempt(models.Model):
    OUTCOME_CORRECT   = "correct"
    OUTCOME_INCORRECT = "incorrect"
    OUTCOME_PARTIAL   = "partial"

    OUTCOME_CHOICES = [
        (OUTCOME_CORRECT,   "Correct"),
        (OUTCOME_INCORRECT, "Incorrect"),
        (OUTCOME_PARTIAL,   "Partial"),
    ]

    user     = user_fk(related_name="attempts")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="attempts")
    answer   = models.JSONField()

    outcome     = models.CharField(max_length=20, choices=OUTCOME_CHOICES, blank=True)
    ai_feedback = models.TextField(blank=True)
    score       = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)],
    )

    attempt_number   = models.PositiveIntegerField(default=1)
    clue_used        = models.BooleanField(default=False)
    hint_used        = models.BooleanField(default=False)
    explanation_used = models.BooleanField(default=False)

    submitted_at = models.DateTimeField(auto_now_add=True)
    evaluated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["submitted_at"]

    def __str__(self):
        return (
            f"{self.user} · Q{self.question_id} · "
            f"Attempt {self.attempt_number} · {self.outcome or 'pending'}"
        )

    def save(self, *args, **kwargs):
        if not self.pk:
            prior = UserAttempt.objects.filter(
                user=self.user, question=self.question
            ).count()
            self.attempt_number = prior + 1
        super().save(*args, **kwargs)


# ─────────────────────────────────────────────
# MASTERY
# ─────────────────────────────────────────────

class ConceptMastery(models.Model):
    STATUS_NOT_STARTED = "not_started"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_MASTERED    = "mastered"
    STATUS_WEAK        = "weak"

    STATUS_CHOICES = [
        (STATUS_NOT_STARTED, "Not started"),
        (STATUS_IN_PROGRESS, "In progress"),
        (STATUS_MASTERED,    "Mastered"),
        (STATUS_WEAK,        "Weak — needs revisit"),
    ]

    user    = user_fk(related_name="masteries")
    concept = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name="masteries")
    status  = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NOT_STARTED)

    consecutive_correct_hard  = models.PositiveIntegerField(default=0)
    highest_difficulty_passed = models.IntegerField(
        default=0, validators=[MinValueValidator(0), MaxValueValidator(3)]
    )

    total_attempts = models.PositiveIntegerField(default=0)
    total_correct  = models.PositiveIntegerField(default=0)
    best_score     = models.FloatField(
        default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)]
    )

    first_attempted_at = models.DateTimeField(null=True, blank=True)
    last_attempted_at  = models.DateTimeField(null=True, blank=True)
    mastered_at        = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together      = ("user", "concept")
        ordering             = ["concept"]
        verbose_name_plural  = "Concept masteries"

    def __str__(self):
        return f"{self.user} · {self.concept.title} · {self.get_status_display()}"

    @property
    def accuracy(self):
        if self.total_attempts == 0:
            return 0.0
        return round((self.total_correct / self.total_attempts) * 100, 1)

    @property
    def total_failures(self):
        return self.total_attempts - self.total_correct

    def record_attempt(self, is_correct: bool, difficulty: int, score: float):
        """Applies the 80/3 mastery rule. Call after every evaluated attempt."""
        now = timezone.now()

        if not self.first_attempted_at:
            self.first_attempted_at = now
        self.last_attempted_at = now
        self.total_attempts   += 1
        self.best_score        = max(self.best_score, score)

        if is_correct:
            self.total_correct += 1
            if difficulty == Question.DIFFICULTY_HARD:
                self.consecutive_correct_hard += 1
            else:
                self.consecutive_correct_hard = 0

            self.highest_difficulty_passed = max(self.highest_difficulty_passed, difficulty)

            if (
                score >= 80.0
                and self.consecutive_correct_hard >= 3
                and self.status != self.STATUS_MASTERED
            ):
                self.status     = self.STATUS_MASTERED
                self.mastered_at = now
            elif self.status == self.STATUS_NOT_STARTED:
                self.status = self.STATUS_IN_PROGRESS
        else:
            self.consecutive_correct_hard = 0
            if self.status == self.STATUS_NOT_STARTED:
                self.status = self.STATUS_IN_PROGRESS
            if self.total_failures >= 4 and self.status != self.STATUS_MASTERED:
                self.status = self.STATUS_WEAK

        self.save()


# ─────────────────────────────────────────────
# DAY PROGRESS & SCHEDULING
# ─────────────────────────────────────────────

class DayProgress(models.Model):
    STATUS_LOCKED      = "locked"
    STATUS_UNLOCKED    = "unlocked"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_PASSED      = "passed"

    STATUS_CHOICES = [
        (STATUS_LOCKED,      "Locked"),
        (STATUS_UNLOCKED,    "Unlocked"),
        (STATUS_IN_PROGRESS, "In progress"),
        (STATUS_PASSED,      "Passed"),
    ]

    user       = user_fk(related_name="day_progresses")
    week       = models.ForeignKey(Week, on_delete=models.CASCADE, related_name="day_progresses")
    day_number = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(7)])
    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_LOCKED)
    unlocked_at = models.DateTimeField(null=True, blank=True)
    passed_at   = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("user", "week", "day_number")
        ordering        = ["day_number"]

    def __str__(self):
        return f"{self.user} · {self.week} · Day {self.day_number} · {self.get_status_display()}"


class ScheduledTest(models.Model):
    STATUS_PENDING   = "pending"
    STATUS_DELIVERED = "delivered"
    STATUS_MISSED    = "missed"

    STATUS_CHOICES = [
        (STATUS_PENDING,   "Pending"),
        (STATUS_DELIVERED, "Delivered"),
        (STATUS_MISSED,    "Missed"),
    ]

    user           = user_fk(related_name="scheduled_tests")
    concept        = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name="scheduled_tests")
    scheduled_for  = models.DateTimeField()
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    delivered_at   = models.DateTimeField(null=True, blank=True)
    celery_task_id = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["scheduled_for"]

    def __str__(self):
        return f"{self.user} · {self.concept.title} · {self.scheduled_for:%Y-%m-%d %H:%M}"


# ─────────────────────────────────────────────
# PROJECTS & BUILD LOG
# ─────────────────────────────────────────────

class Project(models.Model):
    STATUS_DRAFT           = "draft"
    STATUS_SUBMITTED       = "submitted"
    STATUS_EVALUATING      = "evaluating"
    STATUS_PASSED          = "passed"
    STATUS_REVISION_NEEDED = "revision_needed"
    STATUS_FAILED          = "failed"

    STATUS_CHOICES = [
        (STATUS_DRAFT,           "Draft"),
        (STATUS_SUBMITTED,       "Submitted"),
        (STATUS_EVALUATING,      "Evaluating"),
        (STATUS_PASSED,          "Passed"),
        (STATUS_REVISION_NEEDED, "Revision needed"),
        (STATUS_FAILED,          "Failed"),
    ]

    user             = user_fk(related_name="projects")
    week             = models.ForeignKey(Week, on_delete=models.CASCADE, related_name="projects")
    title            = models.CharField(max_length=200)
    description      = models.TextField(blank=True)
    github_url       = models.URLField(blank=True)
    code_submission  = models.TextField(blank=True)
    readme           = models.TextField(blank=True)
    status           = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    submission_count = models.PositiveIntegerField(default=0)
    ai_score         = models.JSONField(null=True, blank=True)
    ai_feedback_summary = models.TextField(blank=True)
    submitted_at     = models.DateTimeField(null=True, blank=True)
    evaluated_at     = models.DateTimeField(null=True, blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "week")
        ordering        = ["-created_at"]

    def __str__(self):
        return f"{self.user} · {self.week} · {self.get_status_display()}"

    @property
    def total_score(self):
        return self.ai_score.get("total", 0) if self.ai_score else 0

    @property
    def can_resubmit(self):
        return self.submission_count < 2 and self.status == self.STATUS_REVISION_NEEDED


class BuildLog(models.Model):
    user           = user_fk(related_name="build_logs")
    week           = models.ForeignKey(Week, on_delete=models.CASCADE, related_name="build_logs")
    day_number     = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(7)])
    entry          = models.TextField()
    ai_prompt_used = models.TextField(blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "week", "day_number")
        ordering        = ["week", "day_number"]

    def __str__(self):
        return f"{self.user} · {self.week} · Day {self.day_number}"