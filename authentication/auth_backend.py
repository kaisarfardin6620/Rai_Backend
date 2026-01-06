from django.contrib.auth.backends import ModelBackend
from django.db.models import Q
from django.contrib.auth import get_user_model

User = get_user_model()


class MultiFieldAuthBackend(ModelBackend):

    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            user = User.objects.get(
                Q(username=username) |
                Q(email=username) |
                Q(phone=username)
            )
        except User.DoesNotExist:
            return None

        if user.check_password(password):
            return user
        return None
