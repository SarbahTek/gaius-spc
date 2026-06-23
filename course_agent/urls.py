from django.urls import path
from . import views

urlpatterns = [
    # Generate a course from a PDF upload
    path('courses/generate/',                     views.CourseGenerateView.as_view(),       name='course-generate'),

    # Publish / unpublish a generated course
    path('courses/<int:pk>/<str:action>/',        views.CoursePublishView.as_view(),        name='course-publish'),

    # Job status polling
    path('generation-jobs/',                      views.GenerationJobListView.as_view(),    name='job-list'),
    path('generation-jobs/<int:pk>/',             views.GenerationJobDetailView.as_view(),  name='job-detail'),
]
