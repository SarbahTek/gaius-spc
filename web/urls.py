from django.urls import path
from . import views

urlpatterns = [
    # Landing
    path('', views.landing, name='landing'),

    # Auth
    path('login/',        views.login_view,       name='login'),
    path('register/',     views.register_view,    name='register'),
    path('account-type/', views.account_type_view, name='account_type'),
    path('logout/',       views.logout_view,      name='logout'),

    # Language
    path('lang/<str:lang_code>/', views.set_language, name='set_language'),

    # Public course pages
    path('courses/',              views.course_catalog, name='course_catalog'),
    path('courses/<int:pk>/',     views.course_detail,  name='course_detail'),

    # Learner
    path('dashboard/',                              views.learner_dashboard, name='learner_dashboard'),
    path('my-courses/',                             views.my_courses,        name='my_courses'),
    path('study/<int:concept_id>/',                 views.study_view,        name='study'),
    path('progress/<int:course_id>/',               views.progress_view,     name='progress'),

    # Admin panel
    path('admin-panel/',                            views.admin_dashboard,      name='admin_dashboard'),
    path('admin-panel/courses/',                    views.admin_courses,        name='admin_courses'),
    path('admin-panel/courses/<int:pk>/toggle/',    views.admin_course_toggle,  name='admin_course_toggle'),
    path('admin-panel/students/',                   views.admin_students,       name='admin_students'),
    path('admin-panel/upload/',                     views.admin_upload,         name='admin_upload'),

    # Settings
    path('settings/',             views.settings_view,    name='settings'),
    path('settings/profile/',     views.settings_profile, name='settings_profile'),
    path('settings/password/',    views.settings_password, name='settings_password'),
]
