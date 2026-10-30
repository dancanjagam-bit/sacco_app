"""
Case-insensitive authentication backend.
Allows members to log in as 'dancan', 'Dancan', or 'DANCAN'.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

User = get_user_model()


class CaseInsensitiveModelBackend(ModelBackend):
    """
    Authenticate using username__iexact so that capitalisation
    does not matter at the login form.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None

        try:
            # iexact = case-insensitive exact match
            user = User.objects.get(username__iexact=username)
        except User.DoesNotExist:
            # Run the default password hasher to resist timing attacks
            User().set_password(password)
            return None
        except User.MultipleObjectsReturned:
            # If somehow two users share the same name differing only in case,
            # fall back to an exact match to avoid ambiguity
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user

        return None
