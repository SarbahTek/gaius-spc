from rest_framework import serializers

from curriculum.models import Course, Concept, ConceptMastery
from .models import Enrollment


class EnrolledCourseSerializer(serializers.ModelSerializer):
    """A learner's enrolled course with computed progress, for the mobile app."""
    course_id    = serializers.IntegerField(source="course.id", read_only=True)
    title        = serializers.CharField(source="course.title", read_only=True)
    subject      = serializers.CharField(source="course.subject_area.display_name", read_only=True)
    thumbnail    = serializers.SerializerMethodField()
    progress_pct = serializers.SerializerMethodField()
    total_concepts    = serializers.SerializerMethodField()
    mastered_concepts = serializers.SerializerMethodField()

    class Meta:
        model  = Enrollment
        fields = ("id", "course_id", "title", "subject", "thumbnail",
                  "amount_paid", "enrolled_at", "is_active",
                  "progress_pct", "total_concepts", "mastered_concepts")

    def _concepts(self, obj):
        return Concept.objects.filter(week__course=obj.course)

    def get_thumbnail(self, obj):
        request = self.context.get("request")
        thumb = obj.course.thumbnail
        if thumb and request:
            return request.build_absolute_uri(thumb.url)
        return thumb.url if thumb else None

    def get_total_concepts(self, obj):
        return self._concepts(obj).count()

    def get_mastered_concepts(self, obj):
        user = self.context["request"].user
        return ConceptMastery.objects.filter(
            user=user, concept__in=self._concepts(obj),
            status=ConceptMastery.STATUS_MASTERED,
        ).count()

    def get_progress_pct(self, obj):
        total = self.get_total_concepts(obj)
        if not total:
            return 0
        return round(self.get_mastered_concepts(obj) / total * 100)


class FreeEnrollSerializer(serializers.Serializer):
    course_id = serializers.IntegerField()

    def validate_course_id(self, value):
        try:
            course = Course.objects.get(pk=value, is_published=True)
        except Course.DoesNotExist:
            raise serializers.ValidationError("Published course not found.")
        if course.price and course.price > 0:
            raise serializers.ValidationError("This is a paid course; use checkout instead.")
        return course


class PaystackInitSerializer(serializers.Serializer):
    course_id = serializers.IntegerField()

    def validate_course_id(self, value):
        try:
            course = Course.objects.get(pk=value, is_published=True)
        except Course.DoesNotExist:
            raise serializers.ValidationError("Published course not found.")
        if not course.price or course.price <= 0:
            raise serializers.ValidationError("This course is free; use the free-enroll endpoint.")
        return course
