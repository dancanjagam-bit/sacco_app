from accounts.access import access_snapshot, staff_roles_for_user
from django.contrib.auth import get_user_model

User = get_user_model()
users = User.objects.filter(is_active=True).exclude(username__startswith='ws_demo_').order_by('id')[:30]
for u in users:
    snap = access_snapshot(u)
    roles = staff_roles_for_user(u)
    ws = [w['id'] for w in snap['workspaces']]
    print(u.username, '| member=', u.is_member, '| super=', u.is_superuser, '| roles=', roles, '| ws=', ws, '| default=', snap['default_workspace'])
