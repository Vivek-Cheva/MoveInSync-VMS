from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from django.utils.timezone import localdate
from django.core.mail import send_mail, EmailMessage
from django.core.files import File
from django.core.files.base import ContentFile

from .forms import UserProfileForm, VisitorForm, VisitRequestForm, CustomUserCreationForm
from .models import UserProfile, VisitRequest, AdminConfig

import uuid
import base64
import qrcode
from io import BytesIO
from datetime import timedelta


# Utility Functions
def get_max_pre_approvals():
    # Fetch maximum daily visit pre-approval limit from admin configuration.
    config = AdminConfig.objects.first()
    return config.max_pre_approvals_per_day if config else 5


def generate_qr_code(visit):
    # # Generate a QR code for the visit reference and save to the model.
    qr_data = f"VisitRef:{visit.reference_code}"
    qr_image = qrcode.make(qr_data)

    buffer = BytesIO()
    qr_image.save(buffer, format='PNG')
    file_name = f"qr_{visit.reference_code}.png"
    visit.qr_code.save(file_name, File(buffer), save=True)


# Role Check Helpers
def is_admin(user):
    return user.is_authenticated and user.is_staff

def is_guard(user):
    return user.is_authenticated and hasattr(user, 'userprofile') and user.userprofile.role == 'guard'

def is_host(user):
    return user.is_authenticated and hasattr(user, 'userprofile') and user.userprofile.role == 'host'


# Admin: Sign up host or guard
@login_required(login_url='login')
@user_passes_test(is_admin)
def signup(request, role):
    # # Admin creates host or guard users with respective profiles.
    if role not in ['host', 'guard']:
        return redirect('home')

    if request.method == 'POST':
        user_form = CustomUserCreationForm(request.POST)
        profile_form = UserProfileForm(request.POST)
        if user_form.is_valid() and profile_form.is_valid():
            user = user_form.save(commit=False)
            user.email = user_form.cleaned_data['email']
            user.save()

            profile = profile_form.save(commit=False)
            profile.user = user
            profile.role = role
            profile.save()

            return redirect('home')
    else:
        user_form = CustomUserCreationForm()
        profile_form = UserProfileForm()

    return render(request, 'signup.html', {
        'user_form': user_form,
        'profile_form': profile_form,
        'role': role
    })


# Visitor: Submit a visit request
def visitor_request_view(request):
    # # Allow a visitor to submit a new visit request, with webcam/photo support.
    if request.method == 'POST':
        visitor_form = VisitorForm(request.POST, request.FILES)
        request_form = VisitRequestForm(request.POST)
        photo_data = request.POST.get('photo_data')

        if visitor_form.is_valid() and request_form.is_valid():
            if not photo_data and not request.FILES.get('photo'):
                return render(request, 'visitor_request.html', {
                    'visitor_form': visitor_form,
                    'request_form': request_form,
                    'error': "A photo is required. Please capture or upload one."
                })

            visitor = visitor_form.save(commit=False)

            if photo_data:
                try:
                    format, imgstr = photo_data.split(';base64,')
                    ext = format.split('/')[-1]
                    visitor.photo.save(
                        f"photo_{uuid.uuid4()}.{ext}",
                        ContentFile(base64.b64decode(imgstr)),
                        save=True
                    )
                except Exception:
                    return render(request, 'visitor_request.html', {
                        'visitor_form': visitor_form,
                        'request_form': request_form,
                        'error': " Error saving captured photo. Please try again."
                    })
            else:
                visitor.photo = request.FILES.get('photo')

            visitor.save()

            visit = request_form.save(commit=False)
            visit.visitor = visitor
            visit.scheduled_start = timezone.now()
            visit.scheduled_end = visit.scheduled_start + timedelta(hours=1)
            visit.approved = None
            visit.reference_code = uuid.uuid4()
            visit.save()

            tracking_url = request.build_absolute_uri(f"/visit-status/?ref={visit.reference_code}")

            # Notify visitor
            send_mail(
                subject="Your Visit Request Has Been Submitted",
                message=f"Hi {visitor.full_name},\n\nTrack your visit here:\n{tracking_url}\n\nThank you!",
                from_email="vivek.cheva@gmail.com",
                recipient_list=[visitor.email],
                fail_silently=False
            )

            # Notify host
            host_email = visit.host.user.email
            approve_url = request.build_absolute_uri(f"/approve/{visit.reference_code}/")
            reject_url = request.build_absolute_uri(f"/reject/{visit.reference_code}/")

            send_mail(
                subject="New Visit Request for Approval",
                message=(
                    f"Visitor: {visitor.full_name}\n"
                    f"Time: {visit.scheduled_start.strftime('%I:%M %p')} - {visit.scheduled_end.strftime('%I:%M %p')}\n"
                    f"Approve: {approve_url}\nReject: {reject_url}"
                ),
                from_email="vivek.cheva@gmail.com",
                recipient_list=[host_email],
                fail_silently=False
            )

            return render(request, 'visitor_success.html', {'tracking_url': tracking_url})

    else:
        visitor_form = VisitorForm()
        request_form = VisitRequestForm()

    return render(request, 'visitor_request.html', {
        'visitor_form': visitor_form,
        'request_form': request_form
    })

def reject_visit(request, ref):
    visit = get_object_or_404(VisitRequest, reference_code=ref)
    visit.approved = False
    visit.save()

    send_mail(
        'Visit Request Rejected',
        'Your visit request has been rejected.',
        'noreply@yourdomain.com',
        [visit.visitor.email],
        fail_silently=True,
    )

    messages.error(request, "Visit request rejected.")
    return redirect('home')

def approve_visit(request, ref):
    visit = get_object_or_404(VisitRequest, reference_code=ref)
    visit.approved = True
    visit.save()

    # Generate QR code and attach to model
    generate_qr_code(visit)

    # Send QR code to visitor
    
    email = EmailMessage(
        'Visit Request Approved - QR Code Attached',
        'Your visit request has been approved. Show the attached QR code to the security guard when you arrive.',
        'noreply@yourdomain.com',
        [visit.visitor.email]
    )
    if visit.qr_code:
        email.attach_file(visit.qr_code.path)
    email.send(fail_silently=True)

    messages.success(request, "Visit approved and QR code sent to visitor.")
    return redirect('host_dashboard')
def is_admin(user):
    return user.is_authenticated and user.is_staff

def is_guard(user):
    return user.is_authenticated and hasattr(user, 'userprofile') and user.userprofile.role == 'guard'
def is_host(user):
    return user.is_authenticated and hasattr(user, 'userprofile') and user.userprofile.role == 'host'


def visit_status_view(request):
    # # Allow visitors to check the status of their visit via reference code.
    ref = request.GET.get('ref')
    visit = get_object_or_404(VisitRequest, reference_code=ref)
    return render(request, 'visit_status.html', {'visit': visit})


# Authentication Views
def login_view(request):
    # # Login user and redirect based on role.
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)

            try:
                role = user.userprofile.role
                if role == 'guard':
                    return redirect('guard_check')
                elif role == 'host':
                    return redirect('host_dashboard')
                elif role == 'admin':
                    return redirect('staff')
                else:
                    return redirect('home')
            except UserProfile.DoesNotExist:
                return redirect('home')
    else:
        form = AuthenticationForm()

    return render(request, 'login.html', {'form': form})


def logout_view(request):
    # # Log out current user.
    logout(request)
    return redirect('login')


def home(request):
    # # Render the home page.
    return render(request, 'home.html')


def admin_view(request):
    # # Render the admin dashboard.
    return render(request, 'admin.html')


# Guard View
@login_required(login_url='login')
@user_passes_test(is_guard)
def guard_check_view(request):
    # # View for guards to check visitors in and out using QR code reference.
    context = {}
    if request.method == 'POST':
        in_code = request.POST.get('check_in_code')
        out_code = request.POST.get('check_out_code')

        if in_code:
            context.update(process_visit_code(in_code, action='in'))
        elif out_code:
            context.update(process_visit_code(out_code, action='out'))

    return render(request, 'guard_check.html', context)


def process_visit_code(code, action):
    # # Check-in or check-out a visit using the QR reference code.
    result = {}

    try:
        ref_uuid = uuid.UUID(code)
    except (ValueError, TypeError):
        result['error'] = f"Invalid {action} reference code format."
        return result

    try:
        visit = VisitRequest.objects.get(reference_code=ref_uuid)
    except VisitRequest.DoesNotExist:
        result['error'] = "No visit found for this reference code."
        return result

    now = timezone.now()

    if not visit.approved:
        result['error'] = "This visit has not been approved."
        return result

    if action == 'in':
        if visit.check_in_time:
            result['error'] = f"{visit.visitor.full_name} has already checked in."
        elif now < visit.scheduled_start:
            result['error'] = f"Too early! Visit starts at {visit.scheduled_start.strftime('%I:%M %p')}."
        elif now > visit.scheduled_end:
            result['error'] = f"Visit slot ended at {visit.scheduled_end.strftime('%I:%M %p')}."
        else:
            visit.check_in_time = now
            visit.status = 'checked_in'
            visit.save()
            result['success'] = f"{visit.visitor.full_name} checked in successfully."

    elif action == 'out':
        if not visit.check_in_time:
            result['error'] = f"{visit.visitor.full_name} has not checked in yet."
        elif visit.check_out_time:
            result['error'] = f"{visit.visitor.full_name} already checked out."
        else:
            visit.check_out_time = now
            visit.status = 'completed'
            visit.save()
            result['success'] = f"{visit.visitor.full_name} checked out. Visit completed."

    return result


# Host Dashboard and Approvals
@login_required
@user_passes_test(is_host)
def host_dashboard_view(request):
    # # Display dashboard with all visit requests for a host.
    host = request.user.userprofile
    today = localdate()

    visit_requests = VisitRequest.objects.filter(host=host).order_by('-scheduled_start')
    max_limit = get_max_pre_approvals()
    today_count = visit_requests.filter(approved=True, scheduled_start__date=today).count()

    return render(request, 'host_dashboard.html', {
        'visit_requests': visit_requests,
        'max_limit': max_limit,
        'used_today': today_count
    })



@login_required
@user_passes_test(is_host)
def host_approve_view(request, ref):
    # # Allow host to approve a visit.
    visit = get_object_or_404(VisitRequest, reference_code=ref)
    if request.user.userprofile != visit.host:
        raise PermissionDenied

    visit.approved = True
    visit.save()
    return redirect('host_dashboard')


@login_required
@user_passes_test(is_host)
def host_reject_view(request, ref):
    # # Allow host to reject a visit.
    visit = get_object_or_404(VisitRequest, reference_code=ref)
    if request.user.userprofile != visit.host:
        raise PermissionDenied

    visit.approved = False
    visit.save()
    return redirect('host_dashboard')


@login_required
@user_passes_test(is_host)
def host_pre_approve_view(request):
    # # Allow host to pre-approve visitors with QR code generation.
    host = request.user.userprofile
    today = localdate()
    today_approvals = VisitRequest.objects.filter(
        host=host, approved=True, scheduled_start__date=today).count()

    max_limit = get_max_pre_approvals()

    if request.method == 'POST':
        visitor_form = VisitorForm(request.POST, request.FILES)
        request_form = VisitRequestForm(request.POST)

        if visitor_form.is_valid() and request_form.is_valid():
            if today_approvals >= max_limit:
                messages.error(request, f"Daily limit of {max_limit} pre-approved visitors reached.")
            else:
                visitor = visitor_form.save()
                visit = request_form.save(commit=False)
                visit.visitor = visitor
                visit.host = host
                visit.approved = True
                visit.reference_code = uuid.uuid4()
                visit.save()

                generate_qr_code(visit)

                email = EmailMessage(
                    subject='Pre-Approved Visit – QR Pass',
                    body=(
                        f"Hello {visitor.full_name},\n\n"
                        f"Visit slot: {visit.scheduled_start.strftime('%I:%M %p')} - {visit.scheduled_end.strftime('%I:%M %p')}\n"
                        f"QR code attached.\n\nThank you!"
                    ),
                    from_email='noreply@yourdomain.com',
                    to=[visitor.email]
                )
                if visit.qr_code:
                    email.attach_file(visit.qr_code.path)
                email.send(fail_silently=False)

                messages.success(request, " Pre-approval successful!")
                return redirect('host_dashboard')

    else:
        visitor_form = VisitorForm()
        request_form = VisitRequestForm()

    return render(request, 'host_pre_approve.html', {
        'visitor_form': visitor_form,
        'request_form': request_form,
        'max_limit': max_limit,
        'used_today': today_approvals
    })
