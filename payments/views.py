import json
import logging

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from payments import paymongo
from payments.settle import settle

log = logging.getLogger(__name__)


@extend_schema(exclude=True)  # called by PayMongo, not by our clients
class PayMongoWebhookView(APIView):
    """Payment event. Signature-verified, then settled from what PayMongo's API says, never from the body."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    def post(self, request):
        if not paymongo.valid_signature(request.body, request.headers.get("Paymongo-Signature", "")):
            log.warning("paymongo webhook rejected: bad signature")
            return Response({"detail": "Invalid signature."}, status=403)
        try:
            event = json.loads(request.body)["data"]["attributes"]
            if event["type"] != "checkout_session.payment.paid":
                return Response({"status": "ignored"})
            session_id = event["data"]["id"]
        except (ValueError, KeyError, TypeError):
            return Response({"detail": "Malformed event."}, status=400)
        try:
            session = paymongo.get_session(session_id)
        except Exception:
            log.exception("could not fetch paymongo session %s", session_id)
            return Response({"detail": "Payment provider unavailable."}, status=503)  # PayMongo retries
        if not paymongo.paid_centavos(session):
            log.warning("paid event for paymongo session %s, which PayMongo reports as unpaid", session_id)
            return Response({"detail": "Session is not paid."}, status=503)  # retry in case their API lags behind the event
        if settle(session) is None:
            log.error("paid paymongo session %s matches no order", session_id)
            return Response({"detail": "Unknown order."}, status=404)
        return Response({"status": "ok"})
