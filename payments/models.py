from django.conf import settings
from django.db import models

from curriculum.models import Course


def user_fk(**kwargs):
    return models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, **kwargs)


class Enrollment(models.Model):
    """Records that a user has paid for and has access to a course."""
    user               = user_fk(related_name='enrollments')
    course             = models.ForeignKey(Course, on_delete=models.PROTECT, related_name='enrollments')
    amount_paid        = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    payment_reference  = models.CharField(max_length=100, blank=True)
    enrolled_at        = models.DateTimeField(auto_now_add=True)
    is_active          = models.BooleanField(default=True)

    class Meta:
        unique_together = ('user', 'course')
        ordering = ['-enrolled_at']

    def __str__(self):
        return f"{self.user} → {self.course.title}"


class Cart(models.Model):
    user       = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cart')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Cart — {self.user}"

    @property
    def total(self):
        return sum(item.course.price for item in self.items.select_related('course').all())

    @property
    def item_count(self):
        return self.items.count()


class CartItem(models.Model):
    cart     = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    course   = models.ForeignKey(Course, on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('cart', 'course')

    def __str__(self):
        return f"{self.cart.user} — {self.course.title}"


class Payment(models.Model):
    STATUS_PENDING  = 'pending'
    STATUS_SUCCESS  = 'success'
    STATUS_FAILED   = 'failed'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED,  'Failed'),
    ]

    user       = user_fk(related_name='payments')
    reference  = models.CharField(max_length=100, unique=True)
    amount     = models.DecimalField(max_digits=10, decimal_places=2)
    email      = models.EmailField()
    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    metadata   = models.JSONField(default=dict, blank=True)  # stores course IDs purchased
    created_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.reference} — {self.status} — GHS {self.amount}"
