from django.contrib import admin
from .models import Enrollment, Cart, CartItem, Payment


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display  = ('user', 'course', 'amount_paid', 'enrolled_at', 'is_active')
    list_filter   = ('is_active',)
    search_fields = ('user__username', 'course__title')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display  = ('reference', 'user', 'amount', 'status', 'created_at')
    list_filter   = ('status',)
    search_fields = ('reference', 'user__username', 'email')
    readonly_fields = ('created_at', 'verified_at')


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('user', 'item_count', 'total', 'created_at')


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ('cart', 'course', 'added_at')
