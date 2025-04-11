from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
import uuid

class UserProfile(models.Model):
    ROLE_CHOICES = (
        ('host', 'Host'),
        ('guard', 'Guard'),
        ('admin', 'Admin'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    department = models.CharField(max_length=100, blank=True, null=True)  # only for Host

    def __str__(self):
        return f"{self.user.username} - {self.role}"
    
    
class Visitor(models.Model):
    full_name = models.CharField(max_length=255)
    contact_number = models.CharField(max_length=20)
    email = models.EmailField()
    organization = models.CharField(max_length=255, blank=True, null=True)
    purpose = models.CharField(max_length=255)
    photo = models.ImageField(upload_to='visitor_photos/', null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name


class VisitRequest(models.Model):
    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE)
    reference_code = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    host = models.ForeignKey(UserProfile, on_delete=models.CASCADE, limit_choices_to={'role': 'host'})
    scheduled_time = models.DateTimeField(null=True, blank=True)
    approved = models.BooleanField(null=True)  # None = pending
    approved_at = models.DateTimeField(null=True, blank=True)
    qr_code = models.ImageField(upload_to='qr_codes/', null=True, blank=True)
    check_in_time = models.DateTimeField(null=True, blank=True)
    check_out_time = models.DateTimeField(null=True, blank=True)
    scheduled_start = models.DateTimeField(default=timezone.now)
    scheduled_end = models.DateTimeField(default=timezone.now)
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('checked_in', 'Checked In'),
            ('completed', 'Completed')
        ],
        default='pending'
    )

    def is_expired(self):
        return self.scheduled_time and self.scheduled_time < timezone.now()

    def __str__(self):
        return f"Visit by {self.visitor.full_name} to {self.host.user.username}"
    
class AdminConfig(models.Model):
    max_pre_approvals_per_day = models.PositiveIntegerField(default=5)

    def __str__(self):
        return f"System Settings (Max Pre-Approvals: {self.max_pre_approvals_per_day})"

    class Meta:
        verbose_name = "System Setting"
        verbose_name_plural = "System Settings"

