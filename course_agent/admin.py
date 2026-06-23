from django.contrib import admin
from .models import CourseGenerationJob


@admin.register(CourseGenerationJob)
class CourseGenerationJobAdmin(admin.ModelAdmin):
    list_display    = ('id', 'original_filename', 'created_by', 'subject_area', 'status', 'created_at', 'completed_at')
    list_filter     = ('status', 'subject_area')
    search_fields   = ('original_filename', 'created_by__username')
    readonly_fields = ('created_at', 'completed_at', 'error_message', 'generated_course')
