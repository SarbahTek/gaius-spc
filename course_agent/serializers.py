from rest_framework import serializers

from .models import CourseGenerationJob


class CourseGenerationJobSerializer(serializers.ModelSerializer):
    course_id    = serializers.IntegerField(source='generated_course_id', read_only=True)
    course_title = serializers.CharField(source='generated_course.title', read_only=True, default=None)

    class Meta:
        model  = CourseGenerationJob
        fields = (
            'id', 'original_filename', 'status',
            'course_id', 'course_title',
            'error_message', 'created_at', 'completed_at',
        )
        read_only_fields = fields
