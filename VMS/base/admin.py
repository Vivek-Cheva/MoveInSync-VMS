from django.contrib import admin
from .models import AdminConfig, Visitor, VisitRequest, UserProfile

admin.site.register(AdminConfig)
admin.site.register(Visitor)
admin.site.register(VisitRequest)
admin.site.register(UserProfile)