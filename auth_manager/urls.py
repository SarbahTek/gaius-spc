from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [

    # ── Auth ──────────────────────────────────────────────────────────
    path("register/",      views.RegisterView.as_view(),      name="auth-register"),
    path("login/",         views.LoginView.as_view(),         name="auth-login"),
    path("token/refresh/", TokenRefreshView.as_view(),        name="auth-token-refresh"),
    path("me/",            views.MeView.as_view(),            name="auth-me"),

    # ── OTP (email verification + phone login) ────────────────────────
    path("otp/request/",   views.OtpRequestView.as_view(),    name="auth-otp-request"),
    path("otp/verify/",    views.OtpVerifyView.as_view(),     name="auth-otp-verify"),
]