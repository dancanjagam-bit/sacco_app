"""
Non-interactive superuser creation.

Usage:
    python manage.py shell -c "exec(open('scripts/create_superuser.py').read())"

Or with environment variables:
    set SUPERUSER_USERNAME=admin
    set SUPERUSER_EMAIL=admin@example.com
    set SUPERUSER_PASSWORD=your-password
    python manage.py shell -c "exec(open('scripts/create_superuser.py').read())"

The SUPERUSER_SECRET in .env must be set before running this script.
"""
import os
import sys
import django

# Already bootstrapped by manage.py shell — just run the logic.
from django.contrib.auth import get_user_model

User = get_user_model()

# Guard: requires SUPERUSER_SECRET
secret = os.environ.get("SUPERUSER_SECRET", "")
if not secret:
    print("ERROR: Set SUPERUSER_SECRET in your .env file first.")
    sys.exit(1)

username = os.environ.get("SUPERUSER_USERNAME", "admin")
email = os.environ.get("SUPERUSER_EMAIL", "admin@example.com")
password = os.environ.get("SUPERUSER_PASSWORD", "")

if not password:
    print("ERROR: Set SUPERUSER_PASSWORD environment variable.")
    print("Example:  $env:SUPERUSER_PASSWORD='YourSecurePassword123'")
    sys.exit(1)

if User.objects.filter(username=username).exists():
    print(f"User '{username}' already exists. Updating password.")
    user = User.objects.get(username=username)
    user.set_password(password)
    user.is_staff = True
    user.is_superuser = True
    user.is_active = True
    user.save()
    print(f"Updated '{username}' as superuser.")
else:
    user = User.objects.create_superuser(
        username=username,
        email=email,
        password=password,
    )
    print(f"Created superuser '{username}'.")

print(f"  Username: {user.username}")
print(f"  Email:    {user.email}")
print(f"  ID:       {user.pk}")
print(f"  Is staff: {user.is_staff}")
print(f"  Is super: {user.is_superuser}")
