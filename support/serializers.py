from rest_framework import serializers
from .models import SupportTicket

class SupportTicketSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = SupportTicket
        fields = ['id', 'message', 'status', 'status_display', 'admin_response', 'created_at']
        read_only_fields = ['id', 'status', 'admin_response', 'created_at']