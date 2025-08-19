from django import forms
from django.contrib.auth import get_user_model
from .models import StudentProfile, Fee

User = get_user_model()  # ✅ Uses your custom core.User model
from django import forms
from .models import CBTTest, CBTQuestion



class FeeForm(forms.ModelForm):
    class Meta:
        model = Fee
        fields = ['student', 'amount', 'payment_date', 'term', 'session', 'status', 'description', 'due_date']
        widgets = {
            'payment_date': forms.DateInput(attrs={'type': 'date'}),
            'term': forms.Select(attrs={'class': 'form-select'}),
            'session': forms.TextInput(attrs={'placeholder': 'e.g. 2024/2025'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }




class CBTTestForm(forms.ModelForm):
    class Meta:
        model = CBTTest
        fields = [
            'title', 'subject', 'classroom', 'term', 'session',
            'duration_minutes', 'total_questions', 'start_time', 'end_time'
        ]
        widgets = {
            'start_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'end_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }


class CBTQuestionForm(forms.ModelForm):
    class Meta:
        model = CBTQuestion
        fields = ['question_text', 'option_a', 'option_b', 'option_c', 'option_d', 'correct_option']
