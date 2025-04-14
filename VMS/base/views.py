# myapp/views.py
from django.contrib import messages
from django.shortcuts import render, redirect,get_object_or_404
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from .forms import UserProfileForm,VisitorForm,VisitRequestForm,CustomUserCreationForm
from .models import UserProfile, VisitRequest,AdminConfig
from django.core.mail import send_mail
import uuid
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from datetime import timedelta
from django.core.mail import EmailMessage
import qrcode
from io import BytesIO
from django.core.files import File
from django.core.exceptions import PermissionDenied
from django.utils.timezone import localdate
from django.core.files.base import ContentFile



def get_max_pre_approvals():
    config = AdminConfig.objects.first()
    return config.max_pre_approvals_per_day if config else 5

def generate_qr_code(visit):
    qr_data = f"VisitRef:{visit.reference_code}"  
    qr_image = qrcode.make(qr_data)

    buffer = BytesIO()
    qr_image.save(buffer, format='PNG')
    file_name = f"qr_{visit.reference_code}.png"
    visit.qr_code.save(file_name, File(buffer), save=True)


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


@login_required(login_url='login')
@user_passes_test(is_admin)
def signup(request, role):
  
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





def visitor_request_view(request):
    if request.method == 'POST':
        visitor_form = VisitorForm(request.POST, request.FILES)
        request_form = VisitRequestForm(request.POST)
        photo_data = request.POST.get('photo_data')

        if visitor_form.is_valid() and request_form.is_valid():
           
            if not photo_data and not request.FILES.get('photo'):
                return render(request, 'visitor_request.html', {
                    'visitor_form': visitor_form,
                    'request_form': request_form,
                    'error': "⚠ A photo is required. Please capture or upload one."
                })

            visitor = visitor_form.save(commit=False)

            # If photo was captured via webcam (base64)
            if photo_data:
                try:
                    format, imgstr = photo_data.split(';base64,')
                    ext = format.split('/')[-1]
                    visitor.photo.save(
                        f"photo_{uuid.uuid4()}.{ext}",
                        ContentFile(base64.b64decode(imgstr)),
                        save=True
                    )
                except Exception as e:
                    return render(request, 'visitor_request.html', {
                        'visitor_form': visitor_form,
                        'request_form': request_form,
                        'error': "Error saving captured photo. Please try again."
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

          
            send_mail(
                subject="Your Visit Request Has Been Submitted",
                message=f"Hi {visitor.full_name},\n\nYour visit request has been submitted.\n\n"
                        f"You can track the status here:\n{tracking_url}\n\n"
                        "Thank you!",
                from_email="vivek.cheva@gmail.com",
                recipient_list=[visitor.email],
                fail_silently=False
            )

            
            host_email = visit.host.user.email
            approve_url = request.build_absolute_uri(f"/approve/{visit.reference_code}/")
            reject_url = request.build_absolute_uri(f"/reject/{visit.reference_code}/")

            send_mail(
                subject="New Visit Request for Approval",
                message=(
                    f"You have a new visit request from {visitor.full_name}.\n"
                    f"Visit slot: {visit.scheduled_start.strftime('%I:%M %p')} to {visit.scheduled_end.strftime('%I:%M %p')}\n\n"
                    f"Approve: {approve_url}\n"
                    f"Reject: {reject_url}"
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
def visit_status_view(request):
    ref = request.GET.get('ref')
    visit = get_object_or_404(VisitRequest, reference_code=ref)

    return render(request, 'visit_status.html', {'visit': visit})

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            print("hello3")

            try:
                role = user.userprofile.role
                if role == 'guard':
                    return redirect('guard_check')
                elif role == 'host':
                    return redirect('host_dashboard') 
                elif role == 'admin':
                    print("hello1")
                    return redirect('staff') 
                else:
                    print("hello2")
                    return redirect('home') 
            except UserProfile.DoesNotExist:
                return redirect('home')

    else:
        form = AuthenticationForm()

    return render(request, 'login.html', {'form': form})
def logout_view(request):
    logout(request)
    return redirect('login') 

def home(request):
    return render(request, 'home.html')

def admin_view(request): 
    return render(request, 'admin.html')


@login_required(login_url='login')
@user_passes_test(is_guard, login_url='login')
def guard_check_view(request):
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
            result['error'] = f"Too early! Visit starts at {timezone.localtime(visit.scheduled_start).strftime('%I:%M %p')}."
        elif now > visit.scheduled_end:
            result['error'] = f"This QR code has expired. Visit slot ended at {timezone.localtime(visit.scheduled_end).strftime('%I:%M %p')}."
        else:
            visit.check_in_time = now
            visit.status = 'checked_in'
            visit.save()
            result['success'] = f"{visit.visitor.full_name} has been checked in successfully."

    elif action == 'out':
        if not visit.check_in_time:
            result['error'] = f"{visit.visitor.full_name} has not checked in yet."
        elif visit.check_out_time:
            result['error'] = f"{visit.visitor.full_name} has already checked out."
        else:
            visit.check_out_time = now
            visit.status = 'completed'
            visit.save()
            result['success'] = f"{visit.visitor.full_name} has checked out. Visit marked completed."

    return result

@login_required
@user_passes_test(is_host)
def host_dashboard_view(request):
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


@login_required(login_url='login')
@user_passes_test(is_host)
def host_approve_view(request, ref):
    visit = VisitRequest.objects.get(reference_code=ref)
    if request.user.userprofile != visit.host:
        raise PermissionDenied

    visit.approved = True
    visit.save()
    return redirect('host_dashboard')


@login_required(login_url='login')
@user_passes_test(is_host)
def host_reject_view(request, ref):
    visit = VisitRequest.objects.get(reference_code=ref)
    if request.user.userprofile != visit.host:
        raise PermissionDenied

    visit.approved = False
    visit.save()
    return redirect('host_dashboard')



@login_required
@user_passes_test(is_host)
def host_pre_approve_view(request):
    host = request.user.userprofile
    today = localdate()
    today_approvals = VisitRequest.objects.filter(
        host=host,
        approved=True,
        scheduled_start__date=today
    ).count()
    max_limit = get_max_pre_approvals()

    if request.method == 'POST':
        visitor_form = VisitorForm(request.POST, request.FILES)
        request_form = VisitRequestForm(request.POST)

        if visitor_form.is_valid() and request_form.is_valid():
            if today_approvals >= max_limit:
                messages.error(request, f"You have reached your daily limit of {max_limit} pre-approved visitors.")
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
                    subject='Pre-Approved Visit - QR Pass',
                    body=(
                        f"Hello {visitor.full_name},\n\n"
                        f"You've been pre-approved for a visit.\n"
                        f"Your visit slot is from {visit.scheduled_start.strftime('%I:%M %p')} to {visit.scheduled_end.strftime('%I:%M %p')}.\n\n"
                        "Please show the attached QR code at the gate.\n\n"
                        "Thank you!"
                    ),
                    from_email='noreply@yourdomain.com',
                    to=[visitor.email]
                )
                if visit.qr_code:
                    email.attach_file(visit.qr_code.path)
                email.send(fail_silently=False)

                messages.success(request, "Pre-approval successful!")
                return redirect('host_dashboard')
        else:
            print("Visitor Form Errors:", visitor_form.errors)
            print("Request Form Errors:", request_form.errors)

    else:
        visitor_form = VisitorForm()
        request_form = VisitRequestForm()

    return render(request, 'host_pre_approve.html', {
        'visitor_form': visitor_form,
        'request_form': request_form,
        'max_limit': max_limit,
        'used_today': today_approvals
    })