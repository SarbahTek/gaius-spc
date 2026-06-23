from django.contrib import messages
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from auth_manager.models import User
from curriculum.models import (
    Course, SubjectArea, Week, Concept, ConceptLesson,
    ConceptMastery, DayProgress,
)
from payments.models import Cart, CartItem, Enrollment, Payment


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
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            nxt = request.GET.get('next')
            if nxt:
                return redirect(nxt)
            if user.role == User.ROLE_ADMIN:
                return redirect('admin_dashboard')
            return redirect('learner_dashboard')
        messages.error(request, 'Invalid username or password.')
    return render(request, 'auth/login.html')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('landing')
    if request.method == 'POST':
        username  = request.POST.get('username', '').strip()
        email     = request.POST.get('email', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')
        role      = request.POST.get('role', User.ROLE_STUDENT)

        if password1 != password2:
            messages.error(request, 'Passwords do not match.')
        elif User.objects.filter(username=username).exists():
            messages.error(request, 'Username already taken.')
        elif User.objects.filter(email=email).exists():
            messages.error(request, 'An account with that email already exists.')
        elif len(password1) < 8:
            messages.error(request, 'Password must be at least 8 characters.')
        else:
            if role not in (User.ROLE_STUDENT, User.ROLE_INSTRUCTOR):
                role = User.ROLE_STUDENT
            user = User.objects.create_user(username=username, email=email, password=password1, role=role)
            login(request, user)
            messages.success(request, f'Welcome to SPC Campus, {user.username}!')
            return redirect('learner_dashboard')

    return render(request, 'auth/register.html')


def account_type_view(request):
    """Shown after initial registration to let user pick student vs instructor."""
    return render(request, 'auth/account_type.html')


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

def admin_required(view_func):
    """Decorator: redirect non-admins."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or request.user.role != User.ROLE_ADMIN:
            messages.error(request, 'Admin access required.')
            return redirect('landing')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


@admin_required
def admin_dashboard(request):
    stats = {
        'total_courses':   Course.objects.count(),
        'published':       Course.objects.filter(is_published=True).count(),
        'total_students':  User.objects.filter(role=User.ROLE_STUDENT).count(),
        'total_enrollments': Enrollment.objects.count(),
        'revenue':         sum(p.amount for p in Payment.objects.filter(status=Payment.STATUS_SUCCESS)),
    }
    recent_enrollments = Enrollment.objects.select_related('user', 'course').order_by('-enrolled_at')[:10]
    recent_payments    = Payment.objects.select_related('user').filter(status=Payment.STATUS_SUCCESS).order_by('-created_at')[:5]

    from course_agent.models import CourseGenerationJob
    recent_jobs = CourseGenerationJob.objects.select_related('generated_course').order_by('-created_at')[:5]

    return render(request, 'admin_panel/dashboard.html', {
        'stats':              stats,
        'recent_enrollments': recent_enrollments,
        'recent_payments':    recent_payments,
        'recent_jobs':        recent_jobs,
    })


@admin_required
def admin_courses(request):
    courses       = Course.objects.select_related('subject_area').order_by('-created_at')
    subject_areas = SubjectArea.objects.all()
    return render(request, 'admin_panel/courses.html', {
        'courses':       courses,
        'subject_areas': subject_areas,
    })


@admin_required
@require_POST
def admin_course_toggle(request, pk):
    course = get_object_or_404(Course, pk=pk)
    course.is_published = not course.is_published
    course.save(update_fields=['is_published'])
    state = 'published' if course.is_published else 'unpublished'
    messages.success(request, f'"{course.title}" {state}.')
    return redirect('admin_courses')


@admin_required
def admin_students(request):
    students = User.objects.filter(role=User.ROLE_STUDENT).prefetch_related('enrollments').order_by('-created_at')
    return render(request, 'admin_panel/students.html', {'students': students})


@admin_required
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
    avatar     = request.POST.get('avatar', '').strip()

    user.first_name = first_name
    user.last_name  = last_name
    user.bio        = bio
    user.avatar     = avatar
    user.save(update_fields=['first_name', 'last_name', 'bio', 'avatar'])
    messages.success(request, 'Profile updated.')
    return redirect('/settings/?tab=profile')


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
