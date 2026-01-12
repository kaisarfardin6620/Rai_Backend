from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from django.db.models import Count, Q
from django.contrib.auth import get_user_model
from rest_framework.pagination import PageNumberPagination

from authentication.models import User
from community.models import Community
from support.models import SupportTicket
from .models import AppPage
from .serializers import (
    AdminUserListSerializer, 
    AdminCommunityListSerializer, 
    AdminSupportTicketSerializer,
    AppPageSerializer
)
from Rai_Backend.utils import api_response

class DashboardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class AdminUserViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminUser]
    serializer_class = AdminUserListSerializer
    pagination_class = DashboardPagination
    http_method_names = ['get', 'post', 'patch', 'delete'] # Limit methods

    def get_queryset(self):
        queryset = User.objects.filter(is_superuser=False).order_by('-created_at')
        search = self.request.query_params.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search) | 
                Q(email__icontains=search) | 
                Q(phone__icontains=search)
            )
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=['post'])
    def toggle_status(self, request, pk=None):
        """Action to Ban/Unban user"""
        user = self.get_object()
        user.is_active = not user.is_active
        user.save()
        status_text = "Active" if user.is_active else "Inactive"
        return api_response(message=f"User status changed to {status_text}", data={"status": status_text})

class AdminCommunityViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminUser]
    serializer_class = AdminCommunityListSerializer
    pagination_class = DashboardPagination
    http_method_names = ['get', 'delete']

    def get_queryset(self):
        queryset = Community.objects.annotate(
            member_count=Count('memberships')
        ).order_by('-created_at')
        
        search = self.request.query_params.get('search', '').strip()
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return api_response(message="Community deleted successfully", status_code=200)

class AdminSupportViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminUser]
    serializer_class = AdminSupportTicketSerializer
    pagination_class = DashboardPagination
    http_method_names = ['get', 'patch']

    def get_queryset(self):
        queryset = SupportTicket.objects.select_related('user').order_by('-created_at')
        search = self.request.query_params.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(message__icontains=search) | 
                Q(user__username__icontains=search) |
                Q(user__email__icontains=search)
            )
        return queryset

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        admin_response = request.data.get('admin_response')
        
        if admin_response:
            instance.admin_response = admin_response
            instance.status = 'resolved'
            instance.save()
            return api_response(message="Reply sent successfully", status_code=200)
            
        return super().partial_update(request, *args, **kwargs)

class AdminPageSettingsViewSet(viewsets.ModelViewSet):
    queryset = AppPage.objects.all()
    serializer_class = AppPageSerializer
    lookup_field = 'slug'

    def get_permissions(self):
        if self.action in ['retrieve', 'list']:
            return [permissions.AllowAny()]
        return [permissions.IsAdminUser()]

    @action(detail=True, methods=['post', 'patch'])
    def update_content(self, request, slug=None):
        page = self.get_object()
        content = request.data.get('content')
        
        if content:
            page.content = content
            page.save()
            return api_response(message=f"{page.title} updated successfully")
        
        return api_response(message="Content cannot be empty", success=False, status_code=400)