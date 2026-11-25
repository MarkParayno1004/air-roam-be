from django.urls import path

from payments.views import PayMongoWebhookView

urlpatterns = [path("payments/paymongo/webhook", PayMongoWebhookView.as_view())]
