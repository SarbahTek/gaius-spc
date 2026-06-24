from django.contrib import messages
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from auth_manager.models import User
from curriculum.models import (
    Course, SubjectArea, Week, Concept, ConceptLesson,
    ConceptMastery, DayProgress, Question,
)
from payments.models import Cart, CartItem, Enrollment, Payment
from .forms import CourseForm, WeekForm, ConceptForm, QuestionForm


# ─────────────────────────────────────────────
# LANGUAGE SWITCHING
# ─────────────────────────────────────────────

def set_language(request, lang_code):
    valid = [l[0] for l in User.LANGUAGE_CHOICES]
    if lang_code not in valid:
        lang_code = 'en'
    request.session['lang'] = lang_code
    if request.user.is_authenticated:
        request.user.language_preference = lang_code
        request.user.save(update_fields=['language_preference'])
    return redirect(request.META.get('HTTP_REFERER', '/'))


# ─────────────────────────────────────────────
# LANDING
# ─────────────────────────────────────────────

def landing(request):
    if request.user.is_authenticated:
        if request.user.role == User.ROLE_ADMIN:
            return redirect('admin_dashboard')
        return redirect('learner_dashboard')

    featured_courses = Course.objects.filter(is_published=True).select_related('subject_area')[:6]
    subject_areas    = SubjectArea.objects.all()
    stats = {
        'courses':  Course.objects.filter(is_published=True).count(),
        'students': User.objects.filter(role=User.ROLE_STUDENT).count(),
        'subjects': SubjectArea.objects.count(),
    }
    return render(request, 'landing/index.html', {
        'featured_courses': featured_courses,
        'subject_areas':    subject_areas,
        'stats':            stats,
    })


# ─────────────────────────────────────────────
# AUTHENTICATION
# ─────────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated:
        return redirect('landing')
    if request.method == 'POST':
        identifier = request.POST.get('username', '').strip()
        password   = request.POST.get('password', '')
        # Allow logging in with an email as well as a username.
        username = identifier
        if '@' in identifier:
            match = User.objects.filter(email__iexact=identifier).first()
            if match:
                username = match.username
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            nxt = request.GET.get('next')
            if nxt:
                return redirect(nxt)
            if user.role in (User.ROLE_ADMIN, User.ROLE_INSTRUCTOR):
                return redirect('admin_dashboard')
            return redirect('learner_dashboard')
        messages.error(request, 'Invalid username or password.')
    return render(request, 'auth/login.html')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('landing')
    if request.method == 'POST':
        username   = request.POST.get('username', '').strip()
        email      = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name  = request.POST.get('last_name', '').strip()
        phone      = request.POST.get('phone_number', '').strip()
        dob        = request.POST.get('date_of_birth', '').strip()
        password1  = request.POST.get('password1', '')
        password2  = request.POST.get('password2', '')
        role       = request.POST.get('role', User.ROLE_STUDENT)
        terms      = request.POST.get('terms_accepted')
        photo      = request.FILES.get('profile_photo')

        error = None
        if not (first_name and last_name and dob and phone):
            error = 'First name, last name, date of birth and phone number are required.'
        elif password1 != password2:
            error = 'Passwords do not match.'
        elif User.objects.filter(username=username).exists():
            error = 'Username already taken.'
        elif User.objects.filter(email=email).exists():
            error = 'An account with that email already exists.'
        elif User.objects.filter(phone_number=phone).exists():
            error = 'An account with that phone number already exists.'
        elif len(password1) < 8:
            error = 'Password must be at least 8 characters.'
        elif not terms:
            error = 'You must accept the Privacy Policy and Terms to create an account.'

        if error:
            messages.error(request, error)
            return render(request, 'auth/register.html', {
                'form_data': request.POST,
                'today':     timezone.now().date().isoformat(),
            })

        # Public sign-up is learners only — the studio is invite/owner-only.
        role = User.ROLE_STUDENT
        user = User.objects.create_user(
            username=username, email=email, password=password1, role=role,
            first_name=first_name, last_name=last_name, date_of_birth=dob,
            phone_number=phone,
        )
        if photo:
            user.profile_photo = photo
        user.terms_accepted    = True
        user.terms_accepted_at = timezone.now()
        user.email_verified    = False
        user.save()

        # Issue an email verification code and route to the OTP screen.
        from auth_manager import otp_service
        from auth_manager.models import OtpCode
        otp_service.issue(user.email, OtpCode.PURPOSE_EMAIL_VERIFY, OtpCode.CHANNEL_EMAIL)
        request.session['pending_verify_email'] = user.email
        messages.success(request, 'Account created! Check your email for a verification code.')
        return redirect('verify_email')

    return render(request, 'auth/register.html', {
        'today': timezone.now().date().isoformat(),
    })


def verify_email_view(request):
    """Email OTP step shown right after registration."""
    email = request.session.get('pending_verify_email')
    if not email:
        return redirect('login')

    from auth_manager import otp_service
    from auth_manager.models import OtpCode

    if request.method == 'POST':
        if request.POST.get('action') == 'resend':
            otp_service.issue(email, OtpCode.PURPOSE_EMAIL_VERIFY, OtpCode.CHANNEL_EMAIL)
            messages.info(request, 'A new code has been sent to your email.')
            return redirect('verify_email')

        code = request.POST.get('code', '').strip()
        ok, err = otp_service.verify(email, OtpCode.PURPOSE_EMAIL_VERIFY, code)
        if not ok:
            messages.error(request, err)
            return render(request, 'auth/verify_email.html', {'email': email})

        user = User.objects.filter(email__iexact=email).first()
        if user:
            user.email_verified = True
            user.save(update_fields=['email_verified'])
            request.session.pop('pending_verify_email', None)
            login(request, user)
            messages.success(request, 'Email verified — welcome to SPC Campus!')
            if user.role == User.ROLE_INSTRUCTOR:
                return redirect('admin_dashboard')
            return redirect('learner_dashboard')
        messages.error(request, 'Account not found.')
        return redirect('register')

    return render(request, 'auth/verify_email.html', {'email': email})


def login_phone_view(request):
    """Two-step phone + OTP login (no password)."""
    if request.user.is_authenticated:
        return redirect('landing')

    from auth_manager import otp_service
    from auth_manager.models import OtpCode

    step  = 'enter_code' if request.session.get('phone_login_number') else 'enter_phone'
    phone = request.session.get('phone_login_number', '')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'request' or action == 'resend':
            phone = request.POST.get('phone_number', phone).strip()
            user = User.objects.filter(phone_number=phone).first()
            if not user:
                messages.error(request, 'No account is registered with that phone number.')
                request.session.pop('phone_login_number', None)
                return render(request, 'auth/login_phone.html', {'step': 'enter_phone', 'phone': phone})
            otp_service.issue(phone, OtpCode.PURPOSE_PHONE_LOGIN, OtpCode.CHANNEL_SMS)
            request.session['phone_login_number'] = phone
            messages.info(request, 'A login code has been sent to your phone.')
            return render(request, 'auth/login_phone.html', {'step': 'enter_code', 'phone': phone})

        if action == 'verify':
            phone = request.session.get('phone_login_number', '')
            code  = request.POST.get('code', '').strip()
            ok, err = otp_service.verify(phone, OtpCode.PURPOSE_PHONE_LOGIN, code)
            if not ok:
                messages.error(request, err)
                return render(request, 'auth/login_phone.html', {'step': 'enter_code', 'phone': phone})
            user = User.objects.filter(phone_number=phone).first()
            if user:
                request.session.pop('phone_login_number', None)
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                messages.success(request, f'Welcome back, {user.first_name or user.username}!')
                if user.role in (User.ROLE_ADMIN, User.ROLE_INSTRUCTOR):
                    return redirect('admin_dashboard')
                return redirect('learner_dashboard')
            messages.error(request, 'Account not found.')

    return render(request, 'auth/login_phone.html', {'step': step, 'phone': phone})


def studio_login_view(request):
    """Dedicated, private login for the instructor studio (owner only)."""
    if request.user.is_authenticated:
        if is_owner(request.user):
            return redirect('admin_dashboard')
        messages.error(request, 'This account does not have studio access.')
        return redirect('landing')

    if request.method == 'POST':
        identifier = request.POST.get('username', '').strip()
        password   = request.POST.get('password', '')
        username   = identifier
        if '@' in identifier:
            match = User.objects.filter(email__iexact=identifier).first()
            if match:
                username = match.username
        user = authenticate(request, username=username, password=password)
        if user and is_owner(user):
            login(request, user)
            return redirect('admin_dashboard')
        messages.error(request, 'Invalid credentials or no studio access.')
    return render(request, 'auth/studio_login.html')


def account_type_view(request):
    """Shown after initial registration to let user pick student vs instructor."""
    return render(request, 'auth/account_type.html')


def privacy_policy_view(request):
    return render(request, 'legal/privacy.html')


def terms_view(request):
    return render(request, 'legal/terms.html')


@require_POST
def logout_view(request):
    logout(request)
    return redirect('landing')


# ─────────────────────────────────────────────
# COURSES — PUBLIC
# ─────────────────────────────────────────────

def course_catalog(request):
    qs = Course.objects.filter(is_published=True).select_related('subject_area')

    subject  = request.GET.get('subject')
    lang     = request.GET.get('lang')
    price    = request.GET.get('price')
    q        = request.GET.get('q', '').strip()

    if subject:
        qs = qs.filter(subject_area__name=subject)
    if lang:
        qs = qs.filter(language=lang)
    if price == 'free':
        qs = qs.filter(price=0)
    elif price == 'paid':
        qs = qs.filter(price__gt=0)
    if q:
        qs = qs.filter(title__icontains=q)

    subject_areas = SubjectArea.objects.all()
    return render(request, 'courses/catalog.html', {
        'courses':       qs,
        'subject_areas': subject_areas,
        'active_subject': subject,
        'active_lang':    lang,
        'active_price':   price,
        'search_query':   q,
    })


def course_detail(request, pk):
    course = get_object_or_404(Course, pk=pk, is_published=True)
    weeks  = course.weeks.prefetch_related('concepts').all()

    enrolled = False
    in_cart  = False
    if request.user.is_authenticated:
        enrolled = Enrollment.objects.filter(user=request.user, course=course).exists()
        if not enrolled:
            cart = Cart.objects.filter(user=request.user).first()
            in_cart = CartItem.objects.filter(cart=cart, course=course).exists() if cart else False

    concept_count = sum(w.concepts.count() for w in weeks)

    return render(request, 'courses/detail.html', {
        'course':         course,
        'weeks':          weeks,
        'enrolled':       enrolled,
        'in_cart':        in_cart,
        'concept_count':  concept_count,
    })


# ─────────────────────────────────────────────
# LEARNER
# ─────────────────────────────────────────────

@login_required
def learner_dashboard(request):
    enrollments = Enrollment.objects.filter(
        user=request.user, is_active=True
    ).select_related('course', 'course__subject_area')

    # Mastery summary per enrolled course
    enrolled_data = []
    for enr in enrollments:
        course   = enr.course
        concepts = Concept.objects.filter(week__course=course)
        total    = concepts.count()
        mastered = ConceptMastery.objects.filter(
            user=request.user, concept__in=concepts,
            status=ConceptMastery.STATUS_MASTERED
        ).count()
        pct = round((mastered / total * 100) if total else 0)
        enrolled_data.append({'enrollment': enr, 'course': course, 'pct': pct, 'mastered': mastered, 'total': total})

    weak_concepts = ConceptMastery.objects.filter(
        user=request.user, status=ConceptMastery.STATUS_WEAK
    ).select_related('concept')[:5]

    return render(request, 'learner/dashboard.html', {
        'enrolled_data':  enrolled_data,
        'weak_concepts':  weak_concepts,
    })


@login_required
def my_courses(request):
    enrollments = Enrollment.objects.filter(
        user=request.user, is_active=True
    ).select_related('course', 'course__subject_area')
    return render(request, 'learner/my_courses.html', {'enrollments': enrollments})


@login_required
def study_view(request, concept_id):
    concept  = get_object_or_404(Concept, pk=concept_id)
    course   = concept.week.course

    if not Enrollment.objects.filter(user=request.user, course=course).exists():
        messages.error(request, 'You must be enrolled to study this course.')
        return redirect('course_detail', pk=course.pk)

    try:
        lesson = concept.lesson
    except ConceptLesson.DoesNotExist:
        lesson = None

    # Get questions for today (day 1 = MCQ allowed, day > 1 = practical only)
    questions_qs = concept.questions.all()

    # Progress context
    mastery = ConceptMastery.objects.filter(user=request.user, concept=concept).first()
    day_progress = DayProgress.objects.filter(
        user=request.user, week=concept.week, day_number=concept.day_introduced
    ).first()

    # Sidebar: all concepts in this week grouped by day
    week_concepts = Concept.objects.filter(week=concept.week).order_by('day_introduced', 'order')

    return render(request, 'learner/study.html', {
        'concept':       concept,
        'course':        course,
        'lesson':        lesson,
        'questions':     questions_qs,
        'mastery':       mastery,
        'day_progress':  day_progress,
        'week_concepts': week_concepts,
    })


@login_required
def progress_view(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    if not Enrollment.objects.filter(user=request.user, course=course).exists():
        return redirect('course_detail', pk=course_id)

    weeks_data = []
    for week in course.weeks.prefetch_related('concepts').all():
        concepts_data = []
        for concept in week.concepts.all():
            mastery = ConceptMastery.objects.filter(user=request.user, concept=concept).first()
            day_prog = DayProgress.objects.filter(
                user=request.user, week=week, day_number=concept.day_introduced
            ).first()
            concepts_data.append({'concept': concept, 'mastery': mastery, 'day_progress': day_prog})
        weeks_data.append({'week': week, 'concepts': concepts_data})

    return render(request, 'learner/progress.html', {'course': course, 'weeks_data': weeks_data})


# ─────────────────────────────────────────────
# ADMIN PANEL
# ─────────────────────────────────────────────

def is_owner(user):
    """
    Studio access is restricted to the platform owner(s) for now — the public
    site is learners-only. An owner is a superuser, an account whose email is in
    settings.OWNER_EMAILS, or (kept for forward-compat) an admin/instructor role.
    The instructor/admin *implementation* is unchanged; we simply gate who can reach it.
    """
    from django.conf import settings as dj_settings
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    owner_emails = [e.lower() for e in getattr(dj_settings, 'OWNER_EMAILS', [])]
    if user.email and user.email.lower() in owner_emails:
        return True
    return user.role in (User.ROLE_ADMIN, User.ROLE_INSTRUCTOR)


def is_admin_like(user):
    """Owner with full visibility (all courses, student roster, platform stats)."""
    return user.is_authenticated and (
        user.is_superuser or user.role == User.ROLE_ADMIN or is_owner(user)
    )


def admin_required(view_func):
    """Decorator: admin-only pages (platform-wide stats, student roster)."""
    def wrapper(request, *args, **kwargs):
        if not is_admin_like(request.user):
            messages.error(request, 'Admin access required.')
            return redirect('landing')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


def staff_required(view_func):
    """Decorator: the studio (instructor portal) — owner only, for now."""
    def wrapper(request, *args, **kwargs):
        if not is_owner(request.user):
            messages.error(request, 'The instructor studio is private.')
            return redirect('landing')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


def owned_courses(user):
    """Admin-like owners manage every course; instructors only their own."""
    qs = Course.objects.select_related('subject_area')
    if is_admin_like(user):
        return qs
    return qs.filter(instructor=user)


def can_manage_course(user, course):
    """True if user may edit/delete/publish this course."""
    return is_admin_like(user) or course.instructor_id == user.id


@staff_required
def admin_dashboard(request):
    is_admin = is_admin_like(request.user)
    courses  = owned_courses(request.user)
    course_ids = list(courses.values_list('id', flat=True))

    enrollments_qs = Enrollment.objects.filter(course_id__in=course_ids)
    stats = {
        'total_courses':     courses.count(),
        'published':         courses.filter(is_published=True).count(),
        'total_students':    (User.objects.filter(role=User.ROLE_STUDENT).count()
                              if is_admin else
                              enrollments_qs.values('user').distinct().count()),
        'total_enrollments': enrollments_qs.count(),
        'revenue':           sum(e.amount_paid for e in enrollments_qs),
    }
    recent_enrollments = enrollments_qs.select_related('user', 'course').order_by('-enrolled_at')[:10]
    recent_payments    = (Payment.objects.select_related('user')
                          .filter(status=Payment.STATUS_SUCCESS).order_by('-created_at')[:5]
                          if is_admin else [])

    from course_agent.models import CourseGenerationJob
    jobs_qs = CourseGenerationJob.objects.select_related('generated_course')
    if not is_admin:
        jobs_qs = jobs_qs.filter(created_by=request.user)
    recent_jobs = jobs_qs.order_by('-created_at')[:5]

    return render(request, 'admin_panel/dashboard.html', {
        'stats':              stats,
        'recent_enrollments': recent_enrollments,
        'recent_payments':    recent_payments,
        'recent_jobs':        recent_jobs,
        'is_admin':           is_admin,
    })


@staff_required
def admin_courses(request):
    courses       = owned_courses(request.user).order_by('-created_at')
    subject_areas = SubjectArea.objects.all()
    return render(request, 'admin_panel/courses.html', {
        'courses':       courses,
        'subject_areas': subject_areas,
    })


@staff_required
@require_POST
def admin_course_toggle(request, pk):
    course = get_object_or_404(Course, pk=pk)
    if not can_manage_course(request.user, course):
        messages.error(request, 'You can only manage your own courses.')
        return redirect('admin_courses')
    course.is_published = not course.is_published
    course.save(update_fields=['is_published'])
    state = 'published' if course.is_published else 'unpublished'
    messages.success(request, f'"{course.title}" {state}.')
    return redirect('admin_courses')


@admin_required
def admin_students(request):
    students = User.objects.filter(role=User.ROLE_STUDENT).prefetch_related('enrollments').order_by('-created_at')
    return render(request, 'admin_panel/students.html', {'students': students})


# ─────────────────────────────────────────────
# MANUAL COURSE CRUD (instructor + admin)
# ─────────────────────────────────────────────

def _get_owned_course_or_redirect(request, pk):
    """Fetch a course the user is allowed to manage, else (None, redirect)."""
    course = get_object_or_404(Course, pk=pk)
    if not can_manage_course(request.user, course):
        messages.error(request, 'You can only manage your own courses.')
        return None, redirect('admin_courses')
    return course, None


@staff_required
def course_create(request):
    if request.method == 'POST':
        form = CourseForm(request.POST, request.FILES)
        if form.is_valid():
            course = form.save(commit=False)
            course.instructor = request.user
            course.save()
            messages.success(request, f'Course "{course.title}" created. Now add weeks and concepts.')
            return redirect('course_manage', pk=course.pk)
    else:
        form = CourseForm()
    return render(request, 'admin_panel/course_form.html', {
        'form': form, 'mode': 'create', 'active': 'create',
    })


@staff_required
def course_edit(request, pk):
    course, redir = _get_owned_course_or_redirect(request, pk)
    if redir:
        return redir
    if request.method == 'POST':
        form = CourseForm(request.POST, request.FILES, instance=course)
        if form.is_valid():
            form.save()
            messages.success(request, 'Course updated.')
            return redirect('course_manage', pk=course.pk)
    else:
        form = CourseForm(instance=course)
    return render(request, 'admin_panel/course_form.html', {
        'form': form, 'mode': 'edit', 'course': course, 'active': 'courses',
    })


@staff_required
def course_delete(request, pk):
    course, redir = _get_owned_course_or_redirect(request, pk)
    if redir:
        return redir
    if request.method == 'POST':
        if course.enrollments.exists():
            messages.error(request, 'Cannot delete a course that has enrollments. Unpublish it instead.')
            return redirect('admin_courses')
        title = course.title
        course.delete()
        messages.success(request, f'Course "{title}" deleted.')
        return redirect('admin_courses')
    return render(request, 'admin_panel/confirm_delete.html', {
        'object_label': f'course "{course.title}"',
        'cancel_url':   reverse('admin_courses'),
        'warning':      ('This course has enrollments and cannot be deleted.'
                         if course.enrollments.exists() else None),
    })


@staff_required
def course_manage(request, pk):
    course, redir = _get_owned_course_or_redirect(request, pk)
    if redir:
        return redir
    weeks = course.weeks.prefetch_related('concepts__questions').all()
    return render(request, 'admin_panel/course_manage.html', {
        'course': course, 'weeks': weeks, 'active': 'courses',
    })


# ── Weeks ─────────────────────────────────────────────────────────────

@staff_required
def week_create(request, course_pk):
    course, redir = _get_owned_course_or_redirect(request, course_pk)
    if redir:
        return redir
    if request.method == 'POST':
        form = WeekForm(request.POST)
        if form.is_valid():
            week = form.save(commit=False)
            week.course = course
            week.save()
            messages.success(request, f'Week {week.number} added.')
            return redirect('course_manage', pk=course.pk)
    else:
        next_num = (course.weeks.count() or 0) + 1
        form = WeekForm(initial={'number': next_num})
    return render(request, 'admin_panel/simple_form.html', {
        'form': form, 'title': f'Add Week — {course.title}',
        'cancel_url': reverse('course_manage', kwargs={'pk': course.pk}), 'active': 'courses',
    })


@staff_required
def week_edit(request, pk):
    week = get_object_or_404(Week, pk=pk)
    if not can_manage_course(request.user, week.course):
        messages.error(request, 'You can only manage your own courses.')
        return redirect('admin_courses')
    if request.method == 'POST':
        form = WeekForm(request.POST, instance=week)
        if form.is_valid():
            form.save()
            messages.success(request, 'Week updated.')
            return redirect('course_manage', pk=week.course.pk)
    else:
        form = WeekForm(instance=week)
    return render(request, 'admin_panel/simple_form.html', {
        'form': form, 'title': f'Edit Week {week.number}',
        'cancel_url': reverse('course_manage', kwargs={'pk': week.course.pk}), 'active': 'courses',
    })


@staff_required
@require_POST
def week_delete(request, pk):
    week = get_object_or_404(Week, pk=pk)
    if not can_manage_course(request.user, week.course):
        messages.error(request, 'You can only manage your own courses.')
        return redirect('admin_courses')
    course_pk = week.course.pk
    week.delete()
    messages.success(request, 'Week deleted.')
    return redirect('course_manage', pk=course_pk)


# ── Concepts ──────────────────────────────────────────────────────────

@staff_required
def concept_create(request, week_pk):
    week = get_object_or_404(Week, pk=week_pk)
    if not can_manage_course(request.user, week.course):
        messages.error(request, 'You can only manage your own courses.')
        return redirect('admin_courses')
    if request.method == 'POST':
        form = ConceptForm(request.POST)
        if form.is_valid():
            concept = form.save(commit=False)
            concept.week = week
            concept.save()
            messages.success(request, f'Concept "{concept.title}" added.')
            return redirect('course_manage', pk=week.course.pk)
    else:
        form = ConceptForm(initial={'day_introduced': 1, 'order': week.concepts.count() + 1})
    return render(request, 'admin_panel/simple_form.html', {
        'form': form, 'title': f'Add Concept — Week {week.number}',
        'cancel_url': reverse('course_manage', kwargs={'pk': week.course.pk}), 'active': 'courses',
    })


@staff_required
def concept_edit(request, pk):
    concept = get_object_or_404(Concept, pk=pk)
    if not can_manage_course(request.user, concept.week.course):
        messages.error(request, 'You can only manage your own courses.')
        return redirect('admin_courses')
    if request.method == 'POST':
        form = ConceptForm(request.POST, instance=concept)
        if form.is_valid():
            form.save()
            messages.success(request, 'Concept updated.')
            return redirect('course_manage', pk=concept.week.course.pk)
    else:
        form = ConceptForm(instance=concept)
    return render(request, 'admin_panel/simple_form.html', {
        'form': form, 'title': f'Edit Concept — {concept.title}',
        'cancel_url': reverse('course_manage', kwargs={'pk': concept.week.course.pk}), 'active': 'courses',
    })


@staff_required
@require_POST
def concept_delete(request, pk):
    concept = get_object_or_404(Concept, pk=pk)
    if not can_manage_course(request.user, concept.week.course):
        messages.error(request, 'You can only manage your own courses.')
        return redirect('admin_courses')
    course_pk = concept.week.course.pk
    concept.delete()
    messages.success(request, 'Concept deleted.')
    return redirect('course_manage', pk=course_pk)


# ── Questions ─────────────────────────────────────────────────────────

@staff_required
def question_create(request, concept_pk):
    concept = get_object_or_404(Concept, pk=concept_pk)
    if not can_manage_course(request.user, concept.week.course):
        messages.error(request, 'You can only manage your own courses.')
        return redirect('admin_courses')
    if request.method == 'POST':
        form = QuestionForm(request.POST)
        if form.is_valid():
            content, rubric = form.build_content_and_rubric()
            Question.objects.create(
                concept            = concept,
                generated_for_week = concept.week.number,
                question_type      = form.cleaned_data['question_type'],
                difficulty         = int(form.cleaned_data['difficulty']),
                content            = content,
                answer_rubric      = rubric,
                is_ai_generated    = False,
            )
            messages.success(request, 'Question added.')
            return redirect('course_manage', pk=concept.week.course.pk)
    else:
        form = QuestionForm(initial={'question_type': Question.TYPE_MCQ, 'difficulty': Question.DIFFICULTY_EASY})
    return render(request, 'admin_panel/question_form.html', {
        'form': form, 'concept': concept, 'mode': 'create',
        'cancel_url': reverse('course_manage', kwargs={'pk': concept.week.course.pk}), 'active': 'courses',
    })


@staff_required
def question_edit(request, pk):
    question = get_object_or_404(Question, pk=pk)
    concept  = question.concept
    if not can_manage_course(request.user, concept.week.course):
        messages.error(request, 'You can only manage your own courses.')
        return redirect('admin_courses')
    if request.method == 'POST':
        form = QuestionForm(request.POST)
        if form.is_valid():
            content, rubric = form.build_content_and_rubric()
            question.question_type = form.cleaned_data['question_type']
            question.difficulty    = int(form.cleaned_data['difficulty'])
            question.content       = content
            question.answer_rubric = rubric
            question.save()
            messages.success(request, 'Question updated.')
            return redirect('course_manage', pk=concept.week.course.pk)
    else:
        form = QuestionForm(initial=QuestionForm.initial_from_instance(question))
    return render(request, 'admin_panel/question_form.html', {
        'form': form, 'concept': concept, 'mode': 'edit',
        'cancel_url': reverse('course_manage', kwargs={'pk': concept.week.course.pk}), 'active': 'courses',
    })


@staff_required
@require_POST
def question_delete(request, pk):
    question = get_object_or_404(Question, pk=pk)
    course_pk = question.concept.week.course.pk
    if not can_manage_course(request.user, question.concept.week.course):
        messages.error(request, 'You can only manage your own courses.')
        return redirect('admin_courses')
    question.delete()
    messages.success(request, 'Question deleted.')
    return redirect('course_manage', pk=course_pk)


@staff_required
def admin_upload(request):
    from course_agent.models import CourseGenerationJob
    subject_areas = SubjectArea.objects.all()
    jobs          = CourseGenerationJob.objects.filter(created_by=request.user).order_by('-created_at')[:20]
    return render(request, 'admin_panel/upload.html', {
        'subject_areas': subject_areas,
        'jobs':          jobs,
    })


# ─────────────────────────────────────────────
# SETTINGS
# ─────────────────────────────────────────────

@login_required
def settings_view(request):
    tab = request.GET.get('tab', 'profile')
    payment_history = Payment.objects.filter(user=request.user).order_by('-created_at')[:20]
    return render(request, 'settings/index.html', {
        'active_tab':      tab,
        'payment_history': payment_history,
    })


@login_required
@require_POST
def settings_profile(request):
    user       = request.user
    first_name = request.POST.get('first_name', '').strip()
    last_name  = request.POST.get('last_name', '').strip()
    bio        = request.POST.get('bio', '').strip()
    phone      = request.POST.get('phone_number', '').strip()
    dob        = request.POST.get('date_of_birth', '').strip()
    photo      = request.FILES.get('profile_photo')

    # Phone uniqueness check (excluding self).
    if phone and User.objects.filter(phone_number=phone).exclude(pk=user.pk).exists():
        messages.error(request, 'That phone number is already in use by another account.')
        return redirect('/settings/?tab=profile')

    update_fields = ['first_name', 'last_name', 'bio']
    user.first_name = first_name
    user.last_name  = last_name
    user.bio        = bio

    if phone != (user.phone_number or ''):
        user.phone_number   = phone or None
        user.phone_verified = False
        update_fields += ['phone_number', 'phone_verified']

    if dob:
        user.date_of_birth = dob
        update_fields.append('date_of_birth')

    if photo:
        user.profile_photo = photo
        update_fields.append('profile_photo')

    user.save(update_fields=update_fields)
    messages.success(request, 'Profile updated.')
    return redirect('/settings/?tab=profile')


@login_required
def verify_phone_view(request):
    """Verify the logged-in user's phone via SMS OTP."""
    user = request.user
    if not user.phone_number:
        messages.error(request, 'Add a phone number first.')
        return redirect('/settings/?tab=profile')

    from auth_manager import otp_service
    from auth_manager.models import OtpCode

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'request' or action == 'resend':
            otp_service.issue(user.phone_number, OtpCode.PURPOSE_PHONE_VERIFY, OtpCode.CHANNEL_SMS)
            messages.info(request, 'A verification code was sent to your phone.')
            return render(request, 'auth/verify_phone.html', {'phone': user.phone_number, 'sent': True})

        code = request.POST.get('code', '').strip()
        ok, err = otp_service.verify(user.phone_number, OtpCode.PURPOSE_PHONE_VERIFY, code)
        if not ok:
            messages.error(request, err)
            return render(request, 'auth/verify_phone.html', {'phone': user.phone_number, 'sent': True})
        user.phone_verified = True
        user.save(update_fields=['phone_verified'])
        messages.success(request, 'Phone number verified!')
        return redirect('/settings/?tab=profile')

    # GET → issue a code immediately and show the entry form.
    otp_service.issue(user.phone_number, OtpCode.PURPOSE_PHONE_VERIFY, OtpCode.CHANNEL_SMS)
    return render(request, 'auth/verify_phone.html', {'phone': user.phone_number, 'sent': True})


@login_required
@require_POST
def settings_password(request):
    old_pw  = request.POST.get('old_password', '')
    new_pw1 = request.POST.get('new_password1', '')
    new_pw2 = request.POST.get('new_password2', '')

    if not request.user.check_password(old_pw):
        messages.error(request, 'Current password is incorrect.')
    elif new_pw1 != new_pw2:
        messages.error(request, 'New passwords do not match.')
    elif len(new_pw1) < 8:
        messages.error(request, 'Password must be at least 8 characters.')
    else:
        request.user.set_password(new_pw1)
        request.user.save()
        update_session_auth_hash(request, request.user)
        messages.success(request, 'Password changed successfully.')

    return redirect('/settings/?tab=password')
