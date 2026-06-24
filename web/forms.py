"""
Forms for the shared instructor/admin portal — manual authoring of
courses, weeks, concepts and questions.

The Question model stores `content` and `answer_rubric` as JSON. Rather than
expose raw JSON to instructors, QuestionForm presents friendly fields and
serialises them into the shapes the learner API + evaluator expect
(documented in the curriculum README).
"""
from django import forms

from curriculum.models import Course, Week, Concept, Question


class StyledFormMixin:
    """Adds the site's `form-control` class to every text/select/textarea widget."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.RadioSelect, forms.CheckboxInput,
                                   forms.CheckboxSelectMultiple)):
                continue
            css = widget.attrs.get('class', '')
            widget.attrs['class'] = (css + ' form-control').strip()


# ─────────────────────────────────────────────
# COURSE
# ─────────────────────────────────────────────

class CourseForm(StyledFormMixin, forms.ModelForm):
    PRICING_FREE = 'free'
    PRICING_PAID = 'paid'

    pricing = forms.ChoiceField(
        choices=[(PRICING_FREE, 'Free'), (PRICING_PAID, 'Paid')],
        widget=forms.RadioSelect,
        initial=PRICING_FREE,
    )

    class Meta:
        model  = Course
        fields = ['title', 'subject_area', 'description', 'language', 'price', 'thumbnail']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'price':       forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['price'].required = False
        # Pre-select pricing mode from existing price when editing.
        if self.instance and self.instance.pk:
            self.fields['pricing'].initial = (
                self.PRICING_PAID if self.instance.price and self.instance.price > 0
                else self.PRICING_FREE
            )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('pricing') == self.PRICING_FREE:
            cleaned['price'] = 0
        else:
            price = cleaned.get('price')
            if not price or price <= 0:
                self.add_error('price', 'Enter a price greater than 0 for a paid course.')
        return cleaned


# ─────────────────────────────────────────────
# WEEK
# ─────────────────────────────────────────────

class WeekForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model  = Week
        fields = ['number', 'title', 'summary']
        widgets = {'summary': forms.Textarea(attrs={'rows': 3})}


# ─────────────────────────────────────────────
# CONCEPT
# ─────────────────────────────────────────────

class ConceptForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model  = Concept
        fields = ['day_introduced', 'order', 'title', 'description',
                  'video_url', 'video_duration_seconds']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'day_introduced': forms.NumberInput(attrs={'min': 1, 'max': 5}),
        }


# ─────────────────────────────────────────────
# QUESTION
# ─────────────────────────────────────────────

class QuestionForm(StyledFormMixin, forms.Form):
    """Friendly question authoring for both MCQ and practical types."""

    question_type = forms.ChoiceField(choices=Question.QUESTION_TYPE_CHOICES)
    difficulty    = forms.ChoiceField(choices=Question.DIFFICULTY_CHOICES)

    # MCQ fields
    prompt      = forms.CharField(widget=forms.Textarea(attrs={'rows': 2}))
    option_a    = forms.CharField(required=False)
    option_b    = forms.CharField(required=False)
    option_c    = forms.CharField(required=False)
    option_d    = forms.CharField(required=False)
    correct_index = forms.ChoiceField(
        required=False,
        choices=[(0, 'Option A'), (1, 'Option B'), (2, 'Option C'), (3, 'Option D')],
    )
    explanation = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}))

    # Practical fields
    starter_code = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 4}))
    approach     = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}))
    key_points   = forms.CharField(
        required=False, widget=forms.Textarea(attrs={'rows': 3}),
        help_text='One key point per line.',
    )

    def clean(self):
        cleaned = super().clean()
        qtype = cleaned.get('question_type')
        if qtype == Question.TYPE_MCQ:
            opts = [cleaned.get(f'option_{c}') for c in ('a', 'b', 'c', 'd')]
            opts = [o for o in opts if o]
            if len(opts) < 2:
                self.add_error('option_a', 'Provide at least two options for an MCQ.')
            if cleaned.get('correct_index') in (None, ''):
                self.add_error('correct_index', 'Select the correct option.')
            elif int(cleaned['correct_index']) >= len(opts):
                self.add_error('correct_index', 'Correct option is empty.')
        else:
            if not cleaned.get('approach'):
                self.add_error('approach', 'Describe the expected approach for a practical question.')
        return cleaned

    def build_content_and_rubric(self):
        """Return (content, answer_rubric) JSON dicts from cleaned data."""
        cd = self.cleaned_data
        if cd['question_type'] == Question.TYPE_MCQ:
            options = [cd.get(f'option_{c}') for c in ('a', 'b', 'c', 'd')]
            options = [o for o in options if o]
            content = {'prompt': cd['prompt'], 'options': options}
            rubric  = {
                'correct_index': int(cd['correct_index']),
                'explanation':   cd.get('explanation', ''),
            }
        else:
            content = {'prompt': cd['prompt'], 'starter_code': cd.get('starter_code', '')}
            key_points = [ln.strip() for ln in cd.get('key_points', '').splitlines() if ln.strip()]
            rubric = {'approach': cd.get('approach', ''), 'key_points': key_points}
        return content, rubric

    @classmethod
    def initial_from_instance(cls, q: Question) -> dict:
        """Build initial form values from an existing Question."""
        data = {
            'question_type': q.question_type,
            'difficulty':    q.difficulty,
            'prompt':        q.content.get('prompt', ''),
        }
        if q.question_type == Question.TYPE_MCQ:
            for i, c in enumerate(('a', 'b', 'c', 'd')):
                opts = q.content.get('options', [])
                data[f'option_{c}'] = opts[i] if i < len(opts) else ''
            data['correct_index'] = q.answer_rubric.get('correct_index', 0)
            data['explanation']   = q.answer_rubric.get('explanation', '')
        else:
            data['starter_code'] = q.content.get('starter_code', '')
            data['approach']     = q.answer_rubric.get('approach', '')
            data['key_points']   = '\n'.join(q.answer_rubric.get('key_points', []))
        return data
