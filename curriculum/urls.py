from django.urls import path
from . import views

urlpatterns = [
    # Courses
    path("courses/",                                views.CourseListView.as_view(),      name="course-list"),
    path("courses/<int:pk>/",                       views.CourseDetailView.as_view(),    name="course-detail"),
    path("courses/<int:pk>/outline/",               views.CourseOutlineView.as_view(),   name="course-outline"),
    path("weeks/<int:pk>/",                         views.WeekDetailView.as_view(),      name="week-detail"),
    path("concepts/<int:pk>/",                      views.ConceptDetailView.as_view(),   name="concept-detail"),

    # Questions
    path("concepts/<int:concept_id>/questions/",    views.ConceptQuestionsView.as_view(), name="concept-questions"),
    path("questions/<int:question_id>/clue/",       views.ClueView.as_view(),            name="question-clue"),

    # Attempts
    path("attempts/submit/",                        views.SubmitAttemptView.as_view(),   name="attempt-submit"),
    path("attempts/",                               views.AttemptHistoryView.as_view(),  name="attempt-history"),

    # Mastery
    path("mastery/",                                views.ConceptMasteryView.as_view(),  name="mastery"),
    path("mastery/weak/",                           views.WeakConceptsView.as_view(),    name="mastery-weak"),

    # Progress
    path("progress/week/<int:week_id>/",            views.DayProgressView.as_view(),     name="day-progress"),

    # AI Lesson (tutor script + audio)
    path("concepts/<int:concept_id>/lesson/",       views.ConceptLessonView.as_view(),   name="concept-lesson"),

    # Projects (weekly capstone / problem of the day)
    path("projects/",                               views.ProjectListView.as_view(),     name="project-list"),
    path("projects/submit/",                        views.ProjectSubmitView.as_view(),   name="project-submit"),

    # The Ladder — Day-1 test sets + Days 2-6 daily problems
    path("weeks/<int:week_id>/ladder/",                         views.WeekLadderView.as_view(),     name="week-ladder"),
    path("concepts/<int:concept_id>/lesson/complete/",          views.LessonCompleteView.as_view(), name="lesson-complete"),
    path("concepts/<int:concept_id>/test-set/<int:set_number>/",        views.TestSetView.as_view(),        name="test-set"),
    path("concepts/<int:concept_id>/test-set/<int:set_number>/submit/", views.TestSetSubmitView.as_view(),  name="test-set-submit"),
    path("concepts/<int:concept_id>/test-set/schedule-b/",      views.TestSetScheduleView.as_view(), name="test-set-schedule-b"),
    path("day-problems/<int:problem_id>/submit/",               views.DayProblemSubmitView.as_view(),name="day-problem-submit"),
]