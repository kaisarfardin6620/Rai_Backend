from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.response import Response
from rest_framework import status
from .models import SupportTicket
from .serializers import SupportTicketSerializer

class SupportViewSet(viewsets.ModelViewSet):
    queryset = SupportTicket.objects.all()
    
    permission_classes = [IsAuthenticated]
    serializer_class = SupportTicketSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'user'

    def get_queryset(self):
        return SupportTicket.objects.filter(user=self.request.user).order_by('-created_at')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)