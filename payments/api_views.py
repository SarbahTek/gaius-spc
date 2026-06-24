"""
JSON API for the mobile app — enrollment + Paystack checkout.

The web frontend uses server-rendered template flows (payments/views.py); these
DRF endpoints expose the same capabilities to the Flutter learner app over JWT.
"""
import uuid

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from curriculum.models import Course
from .models import Enrollment, Payment
from .api_serializers import (
    EnrolledCourseSerializer, FreeEnrollSerializer, PaystackInitSerializer,
)
from . import paystack as ps


class MyEnrollmentsView(APIView):
    """GET /api/payments/enrollments/ — learner's enrolled courses + progress."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = (Enrollment.objects
              .filter(user=request.user, is_active=True)
              .select_related("course", "course__subject_area"))
        data = EnrolledCourseSerializer(qs, many=True, context={"request": request}).data
        return Response(data)


class FreeEnrollView(APIView):
    """POST /api/payments/enroll/free/  body: {course_id}"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = FreeEnrollSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        course = serializer.validated_data["course_id"]
        enrollment, created = Enrollment.objects.get_or_create(
            user=request.user, course=course, defaults={"amount_paid": 0},
        )
        return Response(
            {"enrolled": True, "created": created, "course_id": course.id},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PaystackInitView(APIView):
    """POST /api/payments/paystack/init/  body: {course_id}

    Returns an authorization_url the app opens in a WebView, plus the reference
    the app polls via the verify endpoint once Paystack redirects to callback.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PaystackInitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        course = serializer.validated_data["course_id"]

        if Enrollment.objects.filter(user=request.user, course=course).exists():
            return Response({"detail": "Already enrolled."}, status=400)

        reference = f"SPC-{uuid.uuid4().hex[:12].upper()}"
        payment = Payment.objects.create(
            user=request.user, reference=reference, amount=course.price,
            email=request.user.email, metadata={"course_ids": [course.id]},
        )
        callback_url = request.build_absolute_uri(f"/api/payments/paystack/verify/{reference}/")
        try:
            resp = ps.initialize_transaction(
                email=request.user.email, amount_ghs=float(course.price),
                reference=reference, callback_url=callback_url,
            )
            return Response({
                "reference":         reference,
                "authorization_url": resp["data"]["authorization_url"],
                "access_code":       resp["data"].get("access_code"),
                "public_key":        __import__("django.conf", fromlist=["settings"]).settings.PAYSTACK_PUBLIC_KEY,
            })
        except Exception as exc:
            payment.status = Payment.STATUS_FAILED
            payment.save(update_fields=["status"])
            return Response({"detail": f"Payment initialisation failed: {exc}"}, status=502)


class PaystackVerifyView(APIView):
    """GET /api/payments/paystack/verify/<reference>/ — verify + enroll."""
    permission_classes = [IsAuthenticated]

    def get(self, request, reference):
        payment = Payment.objects.filter(reference=reference, user=request.user).first()
        if not payment:
            return Response({"detail": "Payment not found."}, status=404)

        if payment.status == Payment.STATUS_SUCCESS:
            return Response({"status": "success", "already_processed": True})

        try:
            resp = ps.verify_transaction(reference)
        except Exception as exc:
            return Response({"detail": f"Could not verify: {exc}"}, status=502)

        data = resp.get("data", {})
        if data.get("status") == "success":
            payment.status = Payment.STATUS_SUCCESS
            payment.verified_at = timezone.now()
            payment.save(update_fields=["status", "verified_at"])

            course_ids = payment.metadata.get("course_ids", [])
            enrolled = []
            for cid in course_ids:
                course = Course.objects.filter(pk=cid).first()
                if course:
                    Enrollment.objects.get_or_create(
                        user=request.user, course=course,
                        defaults={"amount_paid": payment.amount / max(len(course_ids), 1),
                                  "payment_reference": reference},
                    )
                    enrolled.append(cid)
            return Response({"status": "success", "enrolled_course_ids": enrolled})

        payment.status = Payment.STATUS_FAILED
        payment.save(update_fields=["status"])
        return Response({"status": "failed"}, status=402)
