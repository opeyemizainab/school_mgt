from django import forms
from .models import Fee
from django import forms
from .models import StudentProfile
from django import forms
from django.contrib.auth import get_user_model  # ✅ Correct import
from .models import StudentProfile, Fee

User = get_user_model()  # ✅ Now uses core.User


class FeeForm(forms.ModelForm):
    class Meta:
        model = Fee
        fields = ['student', 'amount', 'payment_date', 'term', 'session', 'status', 'description','due_date']
        widgets = {
            'payment_date': forms.DateInput(attrs={'type': 'date'}),
            'term': forms.Select(attrs={'class': 'form-select'}),
            'session': forms.TextInput(attrs={'placeholder': 'e.g. 2024/2025'}),
            'status': forms.Select(attrs={'class': 'form-select'}),



            
        }



from django import forms
from .models import StudentProfile, Fee
from django.contrib.auth import get_user_model

User = get_user_model()


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


class StudentCreationForm(forms.ModelForm):
    # Add User fields
    username = forms.CharField()
    password = forms.CharField(widget=forms.PasswordInput)
    first_name = forms.CharField()
    last_name = forms.CharField()
    email = forms.EmailField()

    class Meta:
        model = StudentProfile
        fields = ['classroom', 'date_of_birth', 'address', 'photo', 'gender']

    def save(self, commit=True):
        # Create the user
        user = User.objects.create_user(
            username=self.cleaned_data['username'],
            password=self.cleaned_data['password'],
            first_name=self.cleaned_data['first_name'],
            last_name=self.cleaned_data['last_name'],
            email=self.cleaned_data['email'],
            user_type='student'
        )

        # Create the StudentProfile and assign all fields manually
        student_profile = StudentProfile(
            user=user,
            classroom=self.cleaned_data['classroom'],
            date_of_birth=self.cleaned_data['date_of_birth'],
            address=self.cleaned_data['address'],
            gender=self.cleaned_data['gender'],
            photo=self.cleaned_data.get('photo')  # optional field
        )

        if commit:
            student_profile.save()

        return student_profile


from django import forms
from .models import Result

class AdminResultEditForm(forms.ModelForm):
    class Meta:
        model = Result
        fields = ['test_score', 'exam_score','comment']
        widgets = {
            'comment': forms.Textarea(attrs={'rows': 2}),
        }

