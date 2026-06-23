from django.urls import path
from . import views

urlpatterns = [
    # Courses
    path("courses/",                                views.CourseListView.as_view(),      name="course-list"),
    path("courses/<int:pk>/",                       views.CourseDetailView.as_view(),    name="course-detail"),
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
]