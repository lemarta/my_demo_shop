from django.urls import path
from payments.views import (
    TopUpView, 
    SuccessView, 
    CancelView, 
    WebhookView, 
    GetInvoiceView
)

app_name = 'payments'

urlpatterns = [
    path('top-up/', TopUpView.as_view(), name='top_up'),    
    path('success/', SuccessView.as_view(), name='success'),
    path('cancel/', CancelView.as_view(), name='cancel'),
    path('webhooks/stripe/', WebhookView.as_view(), name='stripe-webhook'),
    path('invoice/<int:invoice_pk>', GetInvoiceView.as_view(), name='invoice_pdf'),
]