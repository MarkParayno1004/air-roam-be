from django.contrib import admin

from accounts.models import User

# Developer-only emergency tool (superusers). Staff use the admin dashboard.
admin.site.register(User, search_fields=["email", "first_name", "last_name"], list_display=["email", "permissions", "deleted_at"])
