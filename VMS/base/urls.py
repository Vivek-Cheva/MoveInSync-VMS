from django.urls import path
from .views import *
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', home, name='home'),
    path('signup/<str:role>/', signup, name='signup'),
    path('login/', login_view, name='login'),
    path('accounts/login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('visit-request/', visitor_request_view, name='visitor_request'),
    path('visit-status/', visit_status_view, name='visit_status'),
    path('approve/<uuid:ref>/', approve_visit, name='approve_visit'),
    path('reject/<uuid:ref>/', reject_visit, name='reject_visit'),
    path('guard/check/', guard_check_view, name='guard_check'),
    path('staff/', admin_view, name='staff'),
  
    path('host/', host_dashboard_view, name='host_dashboard'),
    path('host/pre-approve/', host_pre_approve_view, name='host_pre_approve'),
   
    
   
    
    
]



if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)