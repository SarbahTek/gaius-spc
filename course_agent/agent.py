import json
import logging
import uuid
from pathlib import Path

import anthropic
import pdfplumber
from django.conf import settings
from django.utils import timezone

from curriculum.models import (
    Course, Week, Concept, Question, ConceptLesson,
)

logger = logging.getLogger(__name__)


class CourseGenerationAgent:
    """
    PDF → Claude course structure → Django DB → (optional) OpenAI TTS audio.

    Usage (always call from a background thread — this is synchronous and slow):
        agent = CourseGenerationAgent()
        agent.process(job)
    """

    MODEL        = "claude-sonnet-4-6"
    MAX_PDF_CHARS = 100_000  # Trim very long PDFs before sending to Claude

    def __init__(self):
        self._claude = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        openai_key = getattr(settings, 'OPENAI_API_KEY', '')
        if openai_key:
            from openai import OpenAI
            self._tts = OpenAI(api_key=openai_key)
        else:
            self._tts = None

    # ── Public entry point ────────────────────────────────────────────────

    def process(self, job) -> None:
        """
        Main pipeline. Mutates `job` status as it progresses.
        Exceptions are caught, logged, and persisted to job.error_message.
        """
        try:
            job.status = 'processing'
            job.save(update_fields=['status'])

            pdf_text  = self._extract_pdf(job.pdf_file)
            structure = self._generate_structure(pdf_text, job.subject_area)
            course    = self._build_course(structure, job)

            if self._tts:
                self._generate_audio_for_course(course)

            job.generated_course = course
            job.status           = 'completed'
            job.completed_at     = timezone.now()
            job.save(update_fields=['generated_course', 'status', 'completed_at'])

        except Exception as exc:
            logger.exception("Course generation failed — job #%s", job.pk)
            job.status        = 'failed'
            job.error_message = str(exc)
            job.save(update_fields=['status', 'error_message'])

    # ── Step 1: PDF text extraction ───────────────────────────────────────

    def _extract_pdf(self, pdf_file) -> str:
        pages = []
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages.append(text.strip())
        full_text = '\n\n'.join(pages)
        if len(full_text) > self.MAX_PDF_CHARS:
            full_text = full_text[:self.MAX_PDF_CHARS] + '\n\n[Content trimmed — document too long]'
        return full_text

    # ── Step 2: AI course structure generation ────────────────────────────

    def _generate_structure(self, pdf_text: str, subject_area) -> dict:
        subject_name = subject_area.display_name if subject_area else "General"

        system = (
            "You are an expert curriculum designer. "
            "You ALWAYS respond with valid JSON only — no markdown fences, no explanation text, "
            "just the raw JSON object."
        )

        user = f"""Subject area: {subject_name}

Learning material:
---
{pdf_text}
---

Analyse the material above and produce a complete course. Return a single JSON object matching this schema exactly:

{{
  "course": {{
    "title": "string",
    "description": "string — 2-3 sentences describing what learners will achieve"
  }},
  "weeks": [
    {{
      "number": 1,
      "title": "string — week theme",
      "summary": "string — 1-2 sentences",
      "concepts": [
        {{
          "day_introduced": 1,
          "order": 1,
          "title": "string",
          "description": "string — one sentence",
          "tutor_script": "string — 250 to 400 words written as a friendly tutor talking directly to the student. Use real-world analogies, build from simple to complex, ask a rhetorical question to deepen thinking, end with a brief one-sentence summary the student can hold onto.",
          "questions": [
            {{
              "question_type": "mcq",
              "difficulty": 1,
              "content": {{"prompt": "string", "options": ["A", "B", "C", "D"]}},
              "answer_rubric": {{"correct_index": 0, "explanation": "string"}},
              "socratic_clue": "string",
              "scaffolded_hint": "string",
              "micro_explanation": "string"
            }},
            {{
              "question_type": "mcq",
              "difficulty": 2,
              "content": {{"prompt": "string", "options": ["A", "B", "C", "D"]}},
              "answer_rubric": {{"correct_index": 0, "explanation": "string"}},
              "socratic_clue": "string",
              "scaffolded_hint": "string",
              "micro_explanation": "string"
            }},
            {{
              "question_type": "code_scratch",
              "difficulty": 3,
              "content": {{"prompt": "string", "starter_code": ""}},
              "answer_rubric": {{"approach": "string", "key_points": ["point 1", "point 2"]}},
              "socratic_clue": "string",
              "scaffolded_hint": "string",
              "micro_explanation": "string"
            }}
          ]
        }}
      ]
    }}
  ]
}}

Rules:
- 2-4 weeks based on content depth
- 3-5 concepts per week, spread across days 1-5 (day_introduced must be 1-5)
- Each concept gets exactly 3 questions: easy MCQ (difficulty 1), medium MCQ (difficulty 2), hard practical (difficulty 3)
- For hard practical questions the question_type can be any of: code_scratch, debug, extend, explain, design, spot_bug, refactor, edge_case
- For MCQ: content = {{"prompt": "...", "options": ["A","B","C","D"]}}, answer_rubric = {{"correct_index": 0-3, "explanation": "..."}}
- For practical: content = {{"prompt": "...", "starter_code": "optional"}}, answer_rubric = {{"approach": "...", "key_points": [...]}}
- The tutor_script must sound like a real human tutor, NOT a textbook
- Return ONLY the JSON — no markdown, no prose outside the JSON"""

        response = self._claude.messages.create(
            model=self.MODEL,
            max_tokens=8000,
            system=system,
            messages=[{"role": "user", "content": user}],
        )

        raw = response.content[0].text.strip()

        # Strip any accidental markdown code fences
        if raw.startswith('```'):
            raw = raw.split('\n', 1)[1]
            raw = raw.rsplit('```', 1)[0]

        return json.loads(raw)

    # ── Step 3: Persist to database ───────────────────────────────────────

    def _build_course(self, structure: dict, job) -> Course:
        c_data = structure['course']
        course = Course.objects.create(
            title        = c_data['title'],
            description  = c_data['description'],
            subject_area = job.subject_area,
            instructor   = job.created_by,   # course is owned by whoever uploaded the PDF
            is_published = False,   # Admin must review before learners can access
        )

        for week_data in structure['weeks']:
            week = Week.objects.create(
                course  = course,
                number  = week_data['number'],
                title   = week_data['title'],
                summary = week_data.get('summary', ''),
            )

            for concept_data in week_data['concepts']:
                concept = Concept.objects.create(
                    week           = week,
                    day_introduced = concept_data['day_introduced'],
                    order          = concept_data.get('order', 1),
                    title          = concept_data['title'],
                    description    = concept_data['description'],
                )

                ConceptLesson.objects.create(
                    concept      = concept,
                    tutor_script = concept_data.get('tutor_script', ''),
                )

                for q in concept_data.get('questions', []):
                    Question.objects.create(
                        concept            = concept,
                        generated_for_week = week.number,
                        question_type      = q['question_type'],
                        difficulty         = q['difficulty'],
                        content            = q['content'],
                        answer_rubric      = q['answer_rubric'],
                        socratic_clue      = q.get('socratic_clue', ''),
                        scaffolded_hint    = q.get('scaffolded_hint', ''),
                        micro_explanation  = q.get('micro_explanation', ''),
                        is_ai_generated    = True,
                    )

        return course

    # ── Step 4: TTS audio (optional) ─────────────────────────────────────

    def _generate_audio_for_course(self, course: Course) -> None:
        for week in course.weeks.prefetch_related('concepts').all():
            for concept in week.concepts.all():
                try:
                    lesson = concept.lesson
                    if lesson.tutor_script and not lesson.audio_file:
                        self._synthesise(lesson)
                except ConceptLesson.DoesNotExist:
                    pass

    def _synthesise(self, lesson: ConceptLesson) -> None:
        response = self._tts.audio.speech.create(
            model="tts-1",
            voice="nova",           # Warm, clear, educational-sounding voice
            input=lesson.tutor_script,
        )

        filename  = f"concept_{lesson.concept_id}_{uuid.uuid4().hex[:8]}.mp3"
        audio_dir = Path(settings.MEDIA_ROOT) / 'concept_audio'
        audio_dir.mkdir(parents=True, exist_ok=True)

        filepath = audio_dir / filename
        with open(filepath, 'wb') as fh:
            fh.write(response.content)

        lesson.audio_file = f'concept_audio/{filename}'
        lesson.save(update_fields=['audio_file'])
