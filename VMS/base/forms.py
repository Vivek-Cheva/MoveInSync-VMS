from django import forms

from .models import Visitor, VisitRequest, UserProfile
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from django.contrib.auth.models import User
from django.forms import DateTimeInput

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['department'] 
        

     
class VisitorForm(forms.ModelForm):
    class Meta:
        model = Visitor
        fields = ['full_name', 'contact_number', 'email', 'organization','purpose'] 

class VisitRequestForm(forms.ModelForm):
    class Meta:
        model = VisitRequest
        fields = ['host','scheduled_start', 'scheduled_end']  # ✅ Must include these

        widgets = {
            'scheduled_start': DateTimeInput(attrs={'type': 'datetime-local'}),
            'scheduled_end': DateTimeInput(attrs={'type': 'datetime-local'}),
        }