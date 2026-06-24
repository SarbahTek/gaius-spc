from django.urls import path
from . import views

urlpatterns = [
    # Landing
    path('', views.landing, name='landing'),

    # Auth
    path('login/',         views.login_view,        name='login'),
    path('login/phone/',   views.login_phone_view,  name='login_phone'),
    path('studio/login/',  views.studio_login_view, name='studio_login'),
    path('register/',      views.register_view,     name='register'),
    path('verify-email/',  views.verify_email_view, name='verify_email'),
    path('verify-phone/',  views.verify_phone_view, name='verify_phone'),
    path('account-type/',  views.account_type_view, name='account_type'),
    path('logout/',        views.logout_view,       name='logout'),

    # Legal
    path('privacy/', views.privacy_policy_view, name='privacy_policy'),
    path('terms/',   views.terms_view,          name='terms'),

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

    # Manual course authoring (instructor + admin)
    path('admin-panel/courses/new/',                views.course_create,        name='course_create'),
    path('admin-panel/courses/<int:pk>/edit/',      views.course_edit,          name='course_edit'),
    path('admin-panel/courses/<int:pk>/delete/',    views.course_delete,        name='course_delete'),
    path('admin-panel/courses/<int:pk>/manage/',    views.course_manage,        name='course_manage'),
    path('admin-panel/courses/<int:course_pk>/weeks/new/', views.week_create,   name='week_create'),
    path('admin-panel/weeks/<int:pk>/edit/',        views.week_edit,            name='week_edit'),
    path('admin-panel/weeks/<int:pk>/delete/',      views.week_delete,          name='week_delete'),
    path('admin-panel/weeks/<int:week_pk>/concepts/new/', views.concept_create, name='concept_create'),
    path('admin-panel/concepts/<int:pk>/edit/',     views.concept_edit,         name='concept_edit'),
    path('admin-panel/concepts/<int:pk>/delete/',   views.concept_delete,       name='concept_delete'),
    path('admin-panel/concepts/<int:concept_pk>/questions/new/', views.question_create, name='question_create'),
    path('admin-panel/questions/<int:pk>/edit/',    views.question_edit,        name='question_edit'),
    path('admin-panel/questions/<int:pk>/delete/',  views.question_delete,      name='question_delete'),

    # Settings
    path('settings/',             views.settings_view,    name='settings'),
    path('settings/profile/',     views.settings_profile, name='settings_profile'),
    path('settings/password/',    views.settings_password, name='settings_password'),
]
