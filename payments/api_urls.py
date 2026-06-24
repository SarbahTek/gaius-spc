from django.urls import path
from . import api_views as v

urlpatterns = [
    path("enrollments/",                      v.MyEnrollmentsView.as_view(),  name="api_enrollments"),
    path("enroll/free/",                      v.FreeEnrollView.as_view(),     name="api_enroll_free"),
    path("paystack/init/",                    v.PaystackInitView.as_view(),   name="api_paystack_init"),
    path("paystack/verify/<str:reference>/",  v.PaystackVerifyView.as_view(), name="api_paystack_verify"),
]
