from django.urls import path
from . import views

urlpatterns = [
    path('cart/',                           views.cart_view,       name='cart'),
    path('cart/add/<int:course_id>/',       views.cart_add,        name='cart_add'),
    path('cart/remove/<int:course_id>/',    views.cart_remove,     name='cart_remove'),
    path('checkout/',                       views.checkout_view,   name='checkout'),
    path('checkout/initiate/',              views.checkout_initiate, name='checkout_initiate'),
    path('payment/verify/<str:reference>/', views.payment_verify,  name='payment_verify'),
]
