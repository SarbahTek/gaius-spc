from django.conf import settings
from django.db import models


class CourseGenerationJob(models.Model):
    STATUS_PENDING    = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_COMPLETED  = 'completed'
    STATUS_FAILED     = 'failed'

    STATUS_CHOICES = [
        (STATUS_PENDING,    'Pending'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_COMPLETED,  'Completed'),
        (STATUS_FAILED,     'Failed'),
    ]

    created_by        = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='generation_jobs'
    )
    pdf_file          = models.FileField(upload_to='course_pdfs/')
    original_filename = models.CharField(max_length=255)
    subject_area      = models.ForeignKey(
        'curriculum.SubjectArea', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='generation_jobs'
    )
    status            = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    generated_course  = models.ForeignKey(
        'curriculum.Course', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='generation_job'
    )
    error_message     = models.TextField(blank=True)
    created_at        = models.DateTimeField(auto_now_add=True)
    completed_at      = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Job #{self.pk} — {self.original_filename} [{self.status}]"
