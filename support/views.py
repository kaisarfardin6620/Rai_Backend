from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle
from .models import SupportTicket
from .serializers import SupportTicketSerializer
from Rai_Backend.utils import api_response

class SupportViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = SupportTicketSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'user' # Reuse your existing throttle scope

    def get_queryset(self):
        # Users see only their own tickets
        return SupportTicket.objects.filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return api_response(message="Support tickets fetched", data=serializer.data, request=request)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user)
            return api_response(message="Concern submitted successfully", data=serializer.data, status_code=201, request=request)
        return api_response(message="Validation failed", data=serializer.errors, success=False, status_code=400, request=request)