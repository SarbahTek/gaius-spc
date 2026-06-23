import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from curriculum.models import Course
from .models import Cart, CartItem, Enrollment, Payment
from . import paystack as ps


# ── Cart ──────────────────────────────────────────────────────────────

@login_required
def cart_view(request):
    cart, _ = Cart.objects.get_or_create(user=request.user)
    items   = cart.items.select_related('course', 'course__subject_area').all()
    return render(request, 'courses/cart.html', {'cart': cart, 'items': items})


@login_required
@require_POST
def cart_add(request, course_id):
    course = get_object_or_404(Course, pk=course_id, is_published=True)

    if Enrollment.objects.filter(user=request.user, course=course).exists():
        messages.info(request, 'You are already enrolled in this course.')
        return redirect('course_detail', pk=course_id)

    cart, _ = Cart.objects.get_or_create(user=request.user)
    CartItem.objects.get_or_create(cart=cart, course=course)
    messages.success(request, f'"{course.title}" added to cart.')
    return redirect('cart')


@login_required
@require_POST
def cart_remove(request, course_id):
    cart = get_object_or_404(Cart, user=request.user)
    CartItem.objects.filter(cart=cart, course_id=course_id).delete()
    return redirect('cart')


# ── Checkout ─────────────────────────────────────────────────────────

@login_required
def checkout_view(request):
    cart  = get_object_or_404(Cart, user=request.user)
    items = cart.items.select_related('course').all()
    if not items:
        messages.warning(request, 'Your cart is empty.')
        return redirect('cart')

    total       = cart.total
    public_key  = __import__('django.conf', fromlist=['settings']).settings.PAYSTACK_PUBLIC_KEY

    return render(request, 'courses/checkout.html', {
        'cart':       cart,
        'items':      items,
        'total':      total,
        'public_key': public_key,
    })


@login_required
@require_POST
def checkout_initiate(request):
    """Creates a Payment record and redirects to Paystack."""
    cart  = get_object_or_404(Cart, user=request.user)
    items = cart.items.select_related('course').all()
    if not items:
        return redirect('cart')

    total     = cart.total
    reference = f"SPC-{uuid.uuid4().hex[:12].upper()}"
    course_ids = list(items.values_list('course_id', flat=True))

    payment = Payment.objects.create(
        user      = request.user,
        reference = reference,
        amount    = total,
        email     = request.user.email,
        metadata  = {'course_ids': course_ids},
    )

    callback_url = request.build_absolute_uri(f'/payment/verify/{reference}/')

    try:
        resp = ps.initialize_transaction(
            email        = request.user.email,
            amount_ghs   = float(total),
            reference    = reference,
            callback_url = callback_url,
        )
        auth_url = resp['data']['authorization_url']
        return redirect(auth_url)
    except Exception as exc:
        payment.status = Payment.STATUS_FAILED
        payment.save(update_fields=['status'])
        messages.error(request, f'Payment initialisation failed: {exc}')
        return redirect('checkout')


@login_required
def payment_verify(request, reference):
    """Paystack redirects here after payment. We verify and create Enrollments."""
    payment = get_object_or_404(Payment, reference=reference, user=request.user)

    if payment.status == Payment.STATUS_SUCCESS:
        messages.info(request, 'Payment already processed.')
        return redirect('learner_dashboard')

    try:
        resp = ps.verify_transaction(reference)
        data = resp.get('data', {})

        if data.get('status') == 'success':
            payment.status      = Payment.STATUS_SUCCESS
            payment.verified_at = timezone.now()
            payment.save(update_fields=['status', 'verified_at'])

            course_ids = payment.metadata.get('course_ids', [])
            for cid in course_ids:
                course = Course.objects.filter(pk=cid).first()
                if course:
                    Enrollment.objects.get_or_create(
                        user   = request.user,
                        course = course,
                        defaults={
                            'amount_paid':       payment.amount / len(course_ids),
                            'payment_reference': reference,
                        }
                    )

            # Clear the cart
            Cart.objects.filter(user=request.user).delete()

            messages.success(request, 'Payment successful! You are now enrolled.')
            return redirect('my_courses')

        else:
            payment.status = Payment.STATUS_FAILED
            payment.save(update_fields=['status'])
            messages.error(request, 'Payment was not successful. Please try again.')
            return redirect('cart')

    except Exception as exc:
        messages.error(request, f'Could not verify payment: {exc}')
        return redirect('cart')
