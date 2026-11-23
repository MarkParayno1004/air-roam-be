from django.urls import path

from payments.views import XenditWebhookView

urlpatterns = [path("payments/xendit/webhook", XenditWebhookView.as_view())]
