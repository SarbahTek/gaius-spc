import threading

from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView

from curriculum.models import SubjectArea, Course
from .agent import CourseGenerationAgent
from .models import CourseGenerationJob
from .permissions import IsAdminRole
from .serializers import CourseGenerationJobSerializer


# ── Course generation ─────────────────────────────────────────────────────

class CourseGenerateView(APIView):
    """
    POST /api/admin/courses/generate/

    Accepts a PDF upload and optional subject_area_id.
    Returns a job ID immediately; generation runs in a background thread.
    Poll /api/admin/generation-jobs/<id>/ to check status.
    """
    permission_classes = [IsAdminRole]
    parser_classes     = [MultiPartParser, FormParser]

    def post(self, request):
        pdf_file = request.FILES.get('pdf')
        if not pdf_file:
            return Response({'error': 'A PDF file is required (field name: pdf)'}, status=400)
        if not pdf_file.name.lower().endswith('.pdf'):
            return Response({'error': 'Uploaded file must be a PDF'}, status=400)

        subject_area = None
        subject_area_id = request.data.get('subject_area_id')
        if subject_area_id:
            try:
                subject_area = SubjectArea.objects.get(pk=subject_area_id)
            except SubjectArea.DoesNotExist:
                return Response({'error': f'SubjectArea {subject_area_id} not found'}, status=400)

        job = CourseGenerationJob.objects.create(
            created_by        = request.user,
            pdf_file          = pdf_file,
            original_filename = pdf_file.name,
            subject_area      = subject_area,
        )

        thread = threading.Thread(
            target=CourseGenerationAgent().process,
            args=(job,),
            daemon=True,
        )
        thread.start()

        return Response({
            'job_id':  job.pk,
            'status':  job.status,
            'poll_url': f'/api/admin/generation-jobs/{job.pk}/',
            'message': 'Course generation started. Poll the poll_url to check progress.',
        }, status=status.HTTP_202_ACCEPTED)


# ── Job status ────────────────────────────────────────────────────────────

class GenerationJobListView(generics.ListAPIView):
    """GET /api/admin/generation-jobs/ — lists the calling admin's jobs."""
    permission_classes = [IsAdminRole]
    serializer_class   = CourseGenerationJobSerializer

    def get_queryset(self):
        return CourseGenerationJob.objects.filter(created_by=self.request.user)


class GenerationJobDetailView(APIView):
    """GET /api/admin/generation-jobs/<id>/"""
    permission_classes = [IsAdminRole]

    def get(self, request, pk):
        job = get_object_or_404(CourseGenerationJob, pk=pk, created_by=request.user)
        return Response(CourseGenerationJobSerializer(job).data)


# ── Course publish / unpublish ────────────────────────────────────────────

class CoursePublishView(APIView):
    """
    POST /api/admin/courses/<id>/publish/   → publish
    POST /api/admin/courses/<id>/unpublish/ → unpublish (pull back for edits)
    """
    permission_classes = [IsAdminRole]

    def post(self, request, pk, action):
        course = get_object_or_404(Course, pk=pk)
        if action == 'publish':
            course.is_published = True
        elif action == 'unpublish':
            course.is_published = False
        else:
            return Response({'error': 'Unknown action'}, status=400)
        course.save(update_fields=['is_published'])
        return Response({'id': course.pk, 'is_published': course.is_published})
