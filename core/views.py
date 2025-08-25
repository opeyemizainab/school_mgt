# Django core imports
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string, get_template
from django.utils import timezone
from django.urls import reverse
from django.db import transaction, IntegrityError
from django.db.models import Q, Sum, Count, Prefetch
from django.core.paginator import Paginator
from django import forms
# Python standard library
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO

# Third-party imports
from xhtml2pdf import pisa

# Local imports
from .models import (
    User,
    ClassRoom,
    StudentProfile,
    Term,
    Session,
    Result,
    Subject,
    ClassAssignment,
    TeacherProfile,
    Fee,
    Book,
    BorrowRecord,
    CBTTest,
    CBTQuestion,
    CBTSubmission,
    CBTAnswer,
    StudentSubjectEnrollment,
)
from .forms import FeeForm, StudentCreationForm, AdminResultEditForm
from .forms_cbt import CBTTestForm, CBTQuestionForm


# Utility functions
def is_admin(user):
    return hasattr(user, 'user_type') and user.user_type == 'admin'


# Initialize User model
User = get_user_model()


# --- Authentication ---

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            # Redirect based on user type
            if user.user_type == 'admin':
                return redirect('admin_dashboard')
            elif user.user_type == 'teacher':
                return redirect('teacher_dashboard')
            elif user.user_type == 'student':
                return redirect('student_dashboard')
            elif user.user_type == 'librarian':
                return redirect('librarian_dashboard')
            else:
                messages.error(request, "Unknown user type.")
                return redirect('login')
        else:
            messages.error(request, "Invalid username or password.")
            return redirect('login')

    return render(request, 'login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


# --- Dashboards ---
@login_required
def dashboard(request):
    return render(request, 'dashboard.html')


@login_required
def admin_dashboard(request):
    if request.user.user_type != 'admin':
        return HttpResponse("Unauthorized", status=401)

    students = StudentProfile.objects.count()
    teachers = TeacherProfile.objects.count()
    classes = ClassRoom.objects.count()
    subjects = Subject.objects.count()

    context = {
        'students': students,
        'teachers': teachers,
        'classes': classes,
        'subjects': subjects,
    }
    return render(request, 'admin_dashboard.html', context)

User = get_user_model()


class TeacherProfileForm(forms.ModelForm):
    class Meta:
        model = TeacherProfile
        fields = ['gender', 'phone', 'address', 'department', 'photo',]



@login_required
def teacher_dashboard(request):
    if request.user.user_type != 'teacher':
        return HttpResponse("Unauthorized", status=401)

    teacher_profile = get_object_or_404(TeacherProfile, user=request.user)
    assignments = ClassAssignment.objects.filter(teacher=teacher_profile)

    context = {
        'assignments': assignments
    }
    return render(request, 'teacher_dashboard.html', context)

@login_required
def librarian_dashboard(request):
    if request.user.user_type != 'librarian':
        return HttpResponse("Unauthorized", status=401)
    return render(request, "librarian/dashboard.html")


@login_required
def student_dashboard(request):
    return render(request, 'student_dashboard.html')


@login_required
def upload_result(request):
    if request.user.user_type not in ['teacher', 'admin']:
        return HttpResponse("Unauthorized", status=401)

    # Form for selecting filters
    class SelectionForm(forms.Form):
        classroom = forms.ModelChoiceField(queryset=ClassRoom.objects.none(), required=True)
        subject = forms.ModelChoiceField(queryset=Subject.objects.none(), required=True)
        term = forms.ModelChoiceField(queryset=Term.objects.all(), required=True)
        session = forms.ModelChoiceField(queryset=Session.objects.all(), required=True)

        def __init__(self, *args, **kwargs):
            user = kwargs.pop('user')
            super().__init__(*args, **kwargs)
            if getattr(user, 'user_type', None) == 'teacher':
                try:
                    teacher_profile = user.teacherprofile
                    assigned_classes = ClassAssignment.objects.filter(
                        teacher=teacher_profile
                    ).values_list('classroom', flat=True)
                    assigned_subjects = ClassAssignment.objects.filter(
                        teacher=teacher_profile
                    ).values_list('subject', flat=True)

                    self.fields['classroom'].queryset = ClassRoom.objects.filter(id__in=assigned_classes)
                    self.fields['subject'].queryset = Subject.objects.filter(id__in=assigned_subjects)
                except TeacherProfile.DoesNotExist:
                    self.fields['classroom'].queryset = ClassRoom.objects.none()
                    self.fields['subject'].queryset = Subject.objects.none()
            else:
                self.fields['classroom'].queryset = ClassRoom.objects.all()
                self.fields['subject'].queryset = Subject.objects.all()

    # -------------------
    # Save results
    # -------------------
    if "save_results" in request.POST:
        classroom_id = request.POST.get("classroom_id")
        subject_id = request.POST.get("subject_id")
        term_id = request.POST.get("term_id")
        session_id = request.POST.get("session_id")

        term_obj = get_object_or_404(Term, pk=term_id)
        session_obj = get_object_or_404(Session, pk=session_id)

        # --- LOCK CHECK ---
        if request.user.user_type == 'teacher':
            existing_locked = Result.objects.filter(
                term=term_obj,
                session=session_obj,
                subject_id=subject_id,
                student__classroom_id=classroom_id,
                locked=True
            ).exists()

            if existing_locked:
                messages.error(request, "❌ These results are locked. Contact admin to unlock.")
                return redirect('upload_result')

        # Students assigned to this subject/class
        enrolled_student_ids = StudentSubjectEnrollment.objects.filter(
            classroom_id=classroom_id,
            subject_id=subject_id
        ).values_list('student_id', flat=True)

        students = StudentProfile.objects.filter(id__in=enrolled_student_ids)

        for student in students:
            test_score_raw = request.POST.get(f"test_score_{student.id}")
            exam_score_raw = request.POST.get(f"exam_score_{student.id}")

            if not test_score_raw or not exam_score_raw:
                continue

            try:
                test_score = Decimal(test_score_raw)
                exam_score = Decimal(exam_score_raw)
            except InvalidOperation:
                messages.error(request, f"Invalid score for {student.user.get_full_name()}. Skipped.")
                continue

            total = test_score + exam_score

            # Grade & comment logic
            if total <= 39:
                grade, comment = 'F', "Poor performance. Needs improvement."
            elif total <= 44:
                grade, comment = 'E', "Below average. Put in more effort."
            elif total <= 49:
                grade, comment = 'D', "Fair, but can do better."
            elif total <= 59:
                grade, comment = 'C', "Average, needs improvement."
            elif total <= 69:
                grade, comment = 'B', "Good performance."
            elif total <= 89:
                grade, comment = 'A', "Very good! Keep it up."
            elif total <= 100:
                grade, comment = 'A*', "Excellent! Outstanding performance."
            else:
                grade, comment = '', ''

            Result.objects.update_or_create(
                student=student,
                subject_id=subject_id,
                term=term_obj,
                session=session_obj,
                defaults={
                    'test_score': test_score,
                    'exam_score': exam_score,
                    'grade': grade,
                    'comment': comment
                }
            )

        messages.success(request, "✅ Results uploaded successfully!")
        return redirect('upload_result')

    # -------------------
    # Filter students for bulk entry
    # -------------------
    elif "filter_students" in request.POST:
        selection_form = SelectionForm(request.POST, user=request.user)
        if selection_form.is_valid():
            classroom = selection_form.cleaned_data['classroom']
            subject = selection_form.cleaned_data['subject']
            term = selection_form.cleaned_data['term']
            session_val = selection_form.cleaned_data['session']

            # Check if locked for teacher
            locked = False
            if request.user.user_type == 'teacher':
                locked = Result.objects.filter(
                    term=term,
                    session=session_val,
                    subject=subject,
                    student__classroom=classroom,
                    locked=True
                ).exists()

            # Get students
            students = StudentProfile.objects.filter(
                id__in=StudentSubjectEnrollment.objects.filter(
                    classroom=classroom,
                    subject=subject
                ).values_list('student_id', flat=True)
            )

            # Preload existing scores if any
            existing_scores = Result.objects.filter(
                term=term,
                session=session_val,
                subject=subject,
                student__in=students
            ).select_related('student')

            scores_dict = {res.student_id: res for res in existing_scores}

            return render(request, "upload_result_bulk.html", {
                "students": students,
                "classroom": classroom,
                "subject": subject,
                "term": term,
                "session_val": session_val,
                "locked": locked,
                "scores": scores_dict
            })
    else:
        selection_form = SelectionForm(user=request.user)

    return render(request, "upload_result_select.html", {"form": selection_form})


# Page 1 – List students with results (filtered)
def admin_view_results(request):
    classes = ClassRoom.objects.all()
    terms = Term.objects.all()
    sessions = Session.objects.all()

    class_id = request.GET.get('class_id')
    term_id = request.GET.get('term_id')
    session_id = request.GET.get('session_id')

    students = []
    class_obj = term_obj = session_obj = None
    has_results = False
    all_locked = False

    if class_id and term_id and session_id:
        # Resolve selected objects (optional, nice for labels)
        class_obj = ClassRoom.objects.filter(pk=class_id).first()
        term_obj = Term.objects.filter(pk=term_id).first()
        session_obj = Session.objects.filter(pk=session_id).first()

        # Students who actually have results in this scope
        students = (
            StudentProfile.objects
            .filter(
                classroom_id=class_id,
                result__term_id=term_id,
                result__session_id=session_id
            )
            .distinct()
            .select_related('user', 'classroom')
        )

        # Class-wide result set for lock status computation
        qs = Result.objects.filter(
            student__classroom_id=class_id,
            term_id=term_id,
            session_id=session_id
        )
        has_results = qs.exists()
        all_locked = has_results and not qs.filter(locked=False).exists()

    context = {
        'classes': classes,
        'terms': terms,
        'sessions': sessions,
        'selected_class_id': class_id,
        'selected_term_id': term_id,
        'selected_session_id': session_id,
        'class_obj': class_obj,
        'term_obj': term_obj,
        'session_obj': session_obj,
        'students': students,
        'has_results': has_results,
        'all_locked': all_locked,
    }
    return render(request, 'admin/view_results_students.html', context)


# Page 2 – Single student's compiled results for that term/session
@login_required
def admin_student_results_detail(request, student_id, term_id, session_id):
    if request.user.user_type != 'admin':
        return HttpResponse("Unauthorized", status=401)

    student = get_object_or_404(StudentProfile, id=student_id)
    term = get_object_or_404(Term, id=term_id)
    session = get_object_or_404(Session, id=session_id)

    results = Result.objects.filter(
        student_id=student_id,
        term_id=term_id,
        session_id=session_id
    ).select_related('subject')

    return render(request, 'admin/view_single_student_results.html', {
        'student': student,
        'term': term,
        'session': session,
        'results': results,
    })

# Class-wide lock/unlock (keeps filters on redirect)
def toggle_class_results_lock(request, class_id, term_id, session_id):
    classroom = get_object_or_404(ClassRoom, pk=class_id)
    term = get_object_or_404(Term, pk=term_id)
    session = get_object_or_404(Session, pk=session_id)

    results = Result.objects.filter(
        student__classroom=classroom,
        term=term,
        session=session
    )

    if results.exists():
        # If any unlocked exists, lock all; otherwise unlock all.
        any_unlocked = results.filter(locked=False).exists()
        new_status = True if any_unlocked else False
        results.update(locked=new_status)
        action = "locked" if new_status else "unlocked"
        messages.success(
            request,
            f"Results for {classroom.name} — {term.name} — {session.name} have been {action}."
        )
    else:
        messages.warning(request, "No results found to update.")

    # Preserve filters on return
    url = f"{reverse('admin_view_results')}?class_id={class_id}&term_id={term_id}&session_id={session_id}"
    return redirect(url)


def admin_edit_result(request, result_id):
    result = get_object_or_404(Result, id=result_id)

    # Prevent editing if locked
    if result.locked:
        messages.warning(request, "This result is locked and cannot be edited.")
        return redirect(
            'admin_student_results_detail',
            student_id=result.student.id,
            term_id=result.term.id,
            session_id=result.session.id
        )

    if request.method == 'POST':
        form = AdminResultEditForm(request.POST, instance=result)
        if form.is_valid():
            updated_result = form.save(commit=False)

            # Auto calculate grade
            total = updated_result.test_score + updated_result.exam_score
            if total >= 70:
                updated_result.grade = 'A'
                updated_result.comment = "Excellent performance."
            elif total >= 60:
                updated_result.grade = 'B'
                updated_result.comment = "Very good work."
            elif total >= 50:
                updated_result.grade = 'C'
                updated_result.comment = "Good effort, can improve."
            elif total >= 45:
                updated_result.grade = 'D'
                updated_result.comment = "Needs improvement."
            else:
                updated_result.grade = 'F'
                updated_result.comment = "Poor performance. Extra effort required."

            updated_result.save()
            messages.success(request, "Result updated successfully.")
            return redirect(
                'admin_student_results_detail',
                student_id=result.student.id,
                term_id=result.term.id,
                session_id=result.session.id
            )
    else:
        form = AdminResultEditForm(instance=result)

    return render(request, 'admin/edit_result.html', {'form': form, 'result': result})

@login_required
def teacher_view_results(request):
    if request.user.user_type != 'teacher':
        return HttpResponse("Unauthorized", status=401)

    # Step 1: Selection form
    class SelectionForm(forms.Form):
        classroom = forms.ModelChoiceField(queryset=ClassRoom.objects.none(), required=True)
        subject = forms.ModelChoiceField(queryset=Subject.objects.none(), required=True)
        term = forms.ModelChoiceField(queryset=Term.objects.all(), required=True)
        session = forms.ModelChoiceField(queryset=Session.objects.all(), required=True)

        def __init__(self, *args, **kwargs):
            user = kwargs.pop('user')
            super().__init__(*args, **kwargs)

            try:
                teacher_profile = user.teacherprofile
                assigned_classes = ClassAssignment.objects.filter(
                    teacher=teacher_profile
                ).values_list('classroom', flat=True)

                assigned_subjects = ClassAssignment.objects.filter(
                    teacher=teacher_profile
                ).values_list('subject', flat=True)

                self.fields['classroom'].queryset = ClassRoom.objects.filter(id__in=assigned_classes)
                self.fields['subject'].queryset = Subject.objects.filter(id__in=assigned_subjects)
            except TeacherProfile.DoesNotExist:
                self.fields['classroom'].queryset = ClassRoom.objects.none()
                self.fields['subject'].queryset = Subject.objects.none()

    results_data = None
    no_results_message = None

    # Step 2: Handle form submission
    if request.method == "POST":
        form = SelectionForm(request.POST, user=request.user)
        if form.is_valid():
            classroom = form.cleaned_data['classroom']
            subject = form.cleaned_data['subject']
            term = form.cleaned_data['term']        # Model instance
            session = form.cleaned_data['session']  # Model instance

            results_data = Result.objects.filter(
                student__classroom=classroom,
                subject=subject,
                term=term,
                session=session
            ).select_related('student__user').order_by(
                'student__user__last_name', 'student__user__first_name'
            )

            if not results_data.exists():
                no_results_message = "No results found for the selected class, subject, term, and session."
    else:
        form = SelectionForm(user=request.user)

    return render(request, "teacher_view_results.html", {
        "form": form,
        "results_data": results_data,
        "no_results_message": no_results_message
    })

# --- Student: View & Download Results ---

@login_required
def download_report_card(request):
    if request.user.user_type != 'student':
        return HttpResponse("Unauthorized", status=401)

    student = request.user.studentprofile
    term = request.GET.get('term')
    session = request.GET.get('session')

    results = Result.objects.filter(student=student)
    if term:
        results = results.filter(term=term)
    if session:
        results = results.filter(session=session)

    html_string = render_to_string('report_card.html', {
        'student': student,
        'term': term,
        'session': session,
        'results': results,
    })

    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html_string.encode("UTF-8")), result)

    if not pdf.err:
        return HttpResponse(result.getvalue(), content_type='application/pdf')
    else:
        return HttpResponse("Error generating PDF", status=500)


# --- Student Profile ---
@login_required
def student_profile(request):
    if request.user.user_type != 'student':
        return HttpResponse("Unauthorized", status=401)

    student = request.user.studentprofile
    return render(request, 'student_profile.html', {'student': student})


@login_required
def create_student_user(request):
    if request.user.user_type != 'admin':
        return HttpResponse("Unauthorized", status=401)

    class StudentUserForm(forms.ModelForm):
        password = forms.CharField(widget=forms.PasswordInput)

        class Meta:
            model = User
            fields = ['username', 'password', 'first_name', 'last_name', 'email']

    if request.method == 'POST':
        form = StudentUserForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            user.user_type = 'student'
            user.save()

            # ✅ Check if profile exists
            from .models import StudentProfile
            if not StudentProfile.objects.filter(user=user).exists():
                # Redirect to edit student view to fill profile
                messages.success(request, "Student user created. Now complete the profile.")
                return redirect('edit_student', student_id=user.id)
            else:
                messages.warning(request, "Student user already has a profile.")
                return redirect('manage_students')
    else:
        form = StudentUserForm()

    return render(request, 'admin/create_student_user.html', {'form': form})

#admin functionalities


@login_required
@user_passes_test(is_admin)
def manage_students(request):
    selected_class_id = request.GET.get('class_id')
    classes = ClassRoom.objects.all()

    if selected_class_id:
        students = StudentProfile.objects.filter(classroom_id=selected_class_id)
    else:
        students = StudentProfile.objects.all()

    return render(request, 'admin/manage_students.html', {
        'students': students,
        'classes': classes,
    })

@login_required
def search_students(request):
    query = request.GET.get('q', '')
    if query:
        students = StudentProfile.objects.filter(
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(user__username__icontains=query)
        )
    else:
        students = StudentProfile.objects.all()

    html = render_to_string('admin/student_table_rows.html', {'students': students})
    return JsonResponse({'html': html})


@login_required
def manage_sessions_terms(request):
    sessions = Session.objects.all()
    terms = Term.objects.all()

    return render(request, 'admin/manage_sessions_terms.html', {
        'sessions': sessions,
        'terms': terms
    })


@login_required
def add_session(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        if name:
            Session.objects.create(name=name)
            messages.success(request, f"Session '{name}' created successfully.")
        return redirect('manage_sessions_terms')


@login_required
def add_term(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        if name:
            Term.objects.create(name=name)
            messages.success(request, f"Term '{name}' created successfully.")
        return redirect('manage_sessions_terms')


@login_required
def set_current_session(request, session_id):
    session = get_object_or_404(Session, id=session_id)
    session.is_current = True
    session.save()
    messages.success(request, f"Session '{session.name}' is now current.")
    return redirect('manage_sessions_terms')



@login_required

def set_current_term(request, term_id):
    term = get_object_or_404(Term, id=term_id)
    term.is_current = True
    term.save()
    messages.success(request, f"Term '{term.name}' is now current.")
    return redirect('manage_sessions_terms')


@login_required
def view_class_students(request, class_id):
    classroom = get_object_or_404(ClassRoom, id=class_id)
    students = StudentProfile.objects.filter(classroom=classroom)
    return render(request, 'admin/view_class_students.html', {
        'classroom': classroom,
        'students': students
    })

# Helper to check admin
def is_admin(user):
    return user.is_authenticated and user.user_type == 'admin'


@login_required
@user_passes_test(is_admin)
def promote_students(request):
    classes = ClassRoom.objects.all()
    from_class_id = request.GET.get('from_class')
    to_class_id = request.POST.get('to_class')
    students = []

    # Get students of the selected class
    if from_class_id:
        students = StudentProfile.objects.filter(classroom_id=from_class_id)

    if request.method == 'POST':
        selected_students = request.POST.getlist('students')

        # Prevent promoting to the same class
        if to_class_id and to_class_id == from_class_id:
            messages.error(request, "⚠ You cannot promote students to the same class.")
            return redirect(f"{request.path}?from_class={from_class_id}")

        # Graduate students (remove classroom)
        if to_class_id == "graduate":
            StudentProfile.objects.filter(id__in=selected_students).update(classroom=None)
            messages.success(request, "🎓 Selected students have been graduated successfully.")
            return redirect('manage_students')

        # Normal promotion
        if to_class_id:
            StudentProfile.objects.filter(id__in=selected_students).update(classroom_id=to_class_id)
            messages.success(request, "✅ Selected students have been promoted successfully.")
            return redirect('manage_students')

    return render(request, 'admin/promote_students.html', {
        'classes': classes,
        'students': students,
        'from_class_id': from_class_id,
    })


@login_required
def edit_student(request, student_id):
    if request.user.user_type != 'admin':
        return HttpResponse("Unauthorized", status=401)

    student = get_object_or_404(StudentProfile, id=student_id)
    user = student.user

    class UserForm(forms.ModelForm):
        class Meta:
            model = User
            fields = ['username', 'first_name', 'last_name', 'email']

    class StudentProfileForm(forms.ModelForm):
        class Meta:
            model = StudentProfile
            fields = ['classroom', 'date_of_birth', 'address', 'photo', 'gender']

    if request.method == 'POST':
        user_form = UserForm(request.POST, instance=user)
        profile_form = StudentProfileForm(request.POST, request.FILES, instance=student)

        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, 'Student updated successfully.')
            return redirect('manage_students')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        user_form = UserForm(instance=user)
        profile_form = StudentProfileForm(instance=student)

    return render(request, 'admin/edit_student.html', {
        'user_form': user_form,
        'profile_form': profile_form,
        'student': student
    })

@login_required
def delete_student(request, student_id):
    if request.user.user_type != 'admin':
        return HttpResponse("Unauthorized", status=401)

    student = get_object_or_404(StudentProfile, id=student_id)
    student.delete()
    messages.success(request, 'Student deleted successfully.')
    return redirect('manage_students')


#manage Teachers


@login_required
def manage_teachers(request):
    if request.user.user_type != 'admin':
        return HttpResponse("Unauthorized", status=401)

    teachers = TeacherProfile.objects.prefetch_related(
        Prefetch(
            'classassignment_set',
            queryset=ClassAssignment.objects.select_related('classroom', 'subject'),
            to_attr='class_assignments'
        )
    )

    return render(request, 'admin/manage_teachers.html', {'teachers': teachers})

#new ADD TEACHERS

@login_required
def add_teacher(request):
    if request.user.user_type != 'admin':
        return HttpResponse("Unauthorized", status=401)

    class UserForm(forms.ModelForm):
        password = forms.CharField(widget=forms.PasswordInput)

        class Meta:
            model = User
            fields = ['username', 'password', 'first_name', 'last_name', 'email']

    if request.method == 'POST':
        user_form = UserForm(request.POST)

        if user_form.is_valid():
            username = user_form.cleaned_data['username']

            if User.objects.filter(username=username).exists():
                messages.error(request, f"Username '{username}' already exists.")
            else:
                user = user_form.save(commit=False)
                user.set_password(user_form.cleaned_data['password'])
                user.user_type = 'teacher'
                user.save()

                # Create empty TeacherProfile
                from .models import TeacherProfile
                profile = TeacherProfile.objects.create(user=user)

                messages.success(request, "Teacher user created. Now complete the profile.")
                return redirect('edit_teacher', teacher_id=profile.id)
        else:
            messages.error(request, "Please correct the form errors.")
    else:
        user_form = UserForm()

    return render(request, 'admin/add_teacher.html', {
        'user_form': user_form,
    })


#new edit teachers
        
@login_required
def delete_teacher(request, teacher_id):
    if request.user.user_type != 'admin':
        return HttpResponse("Unauthorized", status=401)

    teacher = get_object_or_404(TeacherProfile, id=teacher_id)
    teacher.delete()
    messages.success(request, 'Teacher deleted successfully.')
    return redirect('manage_teachers')


@login_required
def edit_teacher(request, teacher_id):
    if request.user.user_type != 'admin':
        return HttpResponse("Unauthorized", status=401)

    profile = get_object_or_404(TeacherProfile, id=teacher_id)
    teacher_user = profile.user

    # --- Forms for basic info ---
    class TeacherUserForm(forms.ModelForm):
        class Meta:
            model = User
            fields = ['username', 'first_name', 'last_name', 'email']

    class TeacherProfileForm(forms.ModelForm):
        GENDER_CHOICES = [('Male', 'Male'), ('Female', 'Female')]
        gender = forms.ChoiceField(choices=GENDER_CHOICES)

        class Meta:
            model = TeacherProfile
            fields = ['gender', 'phone', 'address', 'department', 'photo']

    # Fetch lists used in the template
    all_classes = ClassRoom.objects.all()
    all_subjects = Subject.objects.all()

    # Build a set of assigned "class_subject" keys for pre-checking (e.g. "3_5")
    existing_assignments = ClassAssignment.objects.filter(teacher=profile)
    assigned_keys = { f"{a.classroom_id}_{a.subject_id}" for a in existing_assignments }

    if request.method == 'POST':
        user_form = TeacherUserForm(request.POST, instance=teacher_user)
        profile_form = TeacherProfileForm(request.POST, request.FILES, instance=profile)

        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()

            # Update assignments in a transaction: delete old -> create new from submitted checkboxes
            with transaction.atomic():
                # Remove all existing assignments for this teacher
                ClassAssignment.objects.filter(teacher=profile).delete()

                # For every class, read the list of selected subject ids from POST:
                for classroom in all_classes:
                    selected_subject_ids = request.POST.getlist(f"subjects_{classroom.id}")  # list of strings
                    for subj_id in selected_subject_ids:
                        try:
                            subject_obj = Subject.objects.get(id=int(subj_id))
                        except (Subject.DoesNotExist, ValueError):
                            # ignore invalid ids
                            continue
                        ClassAssignment.objects.create(
                            teacher=profile,
                            classroom=classroom,
                            subject=subject_obj
                        )

            messages.success(request, 'Teacher updated successfully.')
            return redirect('manage_teachers')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        user_form = TeacherUserForm(instance=teacher_user)
        profile_form = TeacherProfileForm(instance=profile)

    context = {
        'user_form': user_form,
        'profile_form': profile_form,
        'all_classes': all_classes,
        'all_subjects': all_subjects,
        # pass assigned keys as list of strings like "classid_subjectid"
        'assigned_keys': list(assigned_keys),
        'teacher': profile,
    }
    return render(request, 'admin/edit_teacher.html', context)

# --- Admin: Manage Classes ---

@login_required
def manage_classes(request):
    if request.user.user_type != 'admin':
        return HttpResponse("Unauthorized", status=401)

    classes = ClassRoom.objects.all()
    return render(request, 'admin/manage_classes.html', {'classes': classes})


@login_required
def add_class(request):
    if request.user.user_type != 'admin':
        return HttpResponse("Unauthorized", status=401)

    class ClassForm(forms.ModelForm):
        class Meta:
            model = ClassRoom
            fields = ['name']

    if request.method == 'POST':
        form = ClassForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Class added successfully.')
            return redirect('manage_classes')
    else:
        form = ClassForm()

    return render(request, 'admin/add_class.html', {'form': form})


@login_required
def edit_class(request, class_id):
    if request.user.user_type != 'admin':
        return HttpResponse("Unauthorized", status=401)

    classroom = get_object_or_404(ClassRoom, id=class_id)

    class ClassForm(forms.ModelForm):
        class Meta:
            model = ClassRoom
            fields = ['name']

    if request.method == 'POST':
        form = ClassForm(request.POST, instance=classroom)
        if form.is_valid():
            form.save()
            messages.success(request, 'Class updated successfully.')
            return redirect('manage_classes')
    else:
        form = ClassForm(instance=classroom)

    return render(request, 'admin/edit_class.html', {'form': form, 'classroom': classroom})


@login_required
def delete_class(request, class_id):
    if request.user.user_type != 'admin':
        return HttpResponse("Unauthorized", status=401)

    classroom = get_object_or_404(ClassRoom, id=class_id)
    classroom.delete()
    messages.success(request, 'Class deleted successfully.')
    return redirect('manage_classes')

@login_required
def manage_subjects(request):
    if request.user.user_type != 'admin':
        return HttpResponse("Unauthorized", status=401)

    # Add new subject
    if request.method == 'POST' and request.POST.get('action') == 'add':
        subject_name = request.POST.get('name')
        if subject_name:
            Subject.objects.create(name=subject_name)
            messages.success(request, f'Subject "{subject_name}" added successfully.')
        else:
            messages.error(request, "Please enter a subject name.")
        return redirect('manage_subjects')

    # Edit subject
    if request.method == 'POST' and request.POST.get('action') == 'edit':
        subject_id = request.POST.get('subject_id')
        subject_name = request.POST.get('name')
        subject = get_object_or_404(Subject, id=subject_id)
        if subject_name:
            subject.name = subject_name
            subject.save()
            messages.success(request, f'Subject updated to "{subject_name}".')
        else:
            messages.error(request, "Please enter a subject name.")
        return redirect('manage_subjects')

    subjects = Subject.objects.all().order_by('name')
    return render(request, 'admin/manage_subjects.html', {'subjects': subjects})

@login_required
def delete_subject(request, subject_id):
    if request.user.user_type != 'admin':
        return HttpResponse("Unauthorized", status=401)
    subject = get_object_or_404(Subject, id=subject_id)
    subject.delete()
    messages.success(request, f'Subject "{subject.name}" deleted successfully.')
    return redirect('manage_subjects')

@login_required
def assign_students_to_subject(request):
    if request.user.user_type != 'teacher':
        return HttpResponse("Unauthorized", status=401)

    teacher = request.user.teacherprofile
    assigned_subjects = ClassAssignment.objects.filter(teacher=teacher).values_list('subject', flat=True)
    assigned_classes = ClassAssignment.objects.filter(teacher=teacher).values_list('classroom', flat=True)

    subjects = Subject.objects.filter(id__in=assigned_subjects)
    classes = ClassRoom.objects.filter(id__in=assigned_classes)

    students = []
    selected_subject = None
    selected_class = None
    enrolled_student_ids = []

    # Save assignments
    if request.method == "POST" and "save_assignments" in request.POST:
        subject_id = request.POST.get('subject')
        class_id = request.POST.get('classroom')

        if subject_id and class_id:
            selected_subject = Subject.objects.get(id=subject_id)
            selected_class = ClassRoom.objects.get(id=class_id)

            StudentSubjectEnrollment.objects.filter(
                subject=selected_subject,
                classroom=selected_class
            ).delete()

            selected_students = request.POST.getlist('students')
            for sid in selected_students:
                StudentSubjectEnrollment.objects.create(
                    student_id=sid,
                    subject=selected_subject,
                    classroom=selected_class
                )

            messages.success(request, "✅ Students assigned successfully!")
            return redirect("teacher_dashboard")  # Go back to dashboard

    # Filter
    subject_id = request.GET.get('subject')
    class_id = request.GET.get('classroom')

    if subject_id and class_id:
        selected_subject = Subject.objects.get(id=subject_id)
        selected_class = ClassRoom.objects.get(id=class_id)
        students = StudentProfile.objects.filter(classroom=selected_class)

        enrolled_student_ids = list(
            StudentSubjectEnrollment.objects.filter(
                subject=selected_subject,
                classroom=selected_class
            ).values_list('student_id', flat=True)
        )

    return render(request, 'assign_students_to_subject.html', {
        'subjects': subjects,
        'classes': classes,
        'students': students,
        'selected_subject': selected_subject,
        'selected_class': selected_class,
        'enrolled_student_ids': enrolled_student_ids
    })

# views.py


def is_admin(user):
    return user.is_authenticated and user.user_type == 'admin'

# View all fees
def manage_fees(request):
    fees = Fee.objects.select_related('student').all()
    return render(request, 'admin/manage_fees.html', {'fees': fees})

# Add a fee
def add_fee(request):
    if request.method == 'POST':
        form = FeeForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('manage_fees')
    else:
        form = FeeForm()
    return render(request, 'admin/add_fee.html', {'form': form})

# Edit a fee
def edit_fee(request, fee_id):
    fee = get_object_or_404(Fee, id=fee_id)
    if request.method == 'POST':
        form = FeeForm(request.POST, instance=fee)
        if form.is_valid():
            form.save()
            return redirect('manage_fees')
    else:
        form = FeeForm(instance=fee)
    return render(request, 'admin/edit_fee.html', {'form': form, 'fee': fee})

# Delete a fee
def delete_fee(request, fee_id):
    fee = get_object_or_404(Fee, id=fee_id)
    if request.method == 'POST':
        fee.delete()
        return redirect('manage_fees')
    return render(request, 'admin/delete_fee.html', {'fee': fee})

@login_required
@user_passes_test(is_admin)
def fee_summary_view(request):
    summary = Fee.objects.values('term').annotate(
        total_paid = Sum('amount', filter=Q(status='paid')),
        total_unpaid = Sum('amount', filter=Q(status='unpaid')),
        total_partial = Sum('amount', filter=Q(status='partial'))
    )
    return render(request, 'admin/fee_summary.html', {'summary': summary})


def generate_invoice(request, fee_id):
    fee = get_object_or_404(Fee, id=fee_id)
    template_path = 'admin/invoice.html'
    context = {'fee': fee}
    
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'filename=invoice_{fee.id}.pdf'
    
    template = get_template(template_path)
    html = template.render(context)
    
    pisa_status = pisa.CreatePDF(html, dest=response)
    
    if pisa_status.err:
        return HttpResponse('We had some errors with the invoice <pre>' + html + '</pre>')
    return response

@login_required
def create_cbt_test(request):
    try:
        teacher_profile = TeacherProfile.objects.get(user=request.user)
    except TeacherProfile.DoesNotExist:
        return HttpResponse("Teacher profile not found", status=404)

    assignments = ClassAssignment.objects.filter(teacher=teacher_profile)
    subjects = [a.subject for a in assignments]
    classes = [a.classroom for a in assignments]

    if request.method == 'POST':
        try:
            title = request.POST.get('title')
            subject_id = request.POST.get('subject')
            class_id = request.POST.get('classroom')
            term = request.POST.get('term')
            session = request.POST.get('session')
            duration = request.POST.get('duration_minutes')
            total_questions = request.POST.get('total_questions')
            start_time = request.POST.get('start_time')
            end_time = request.POST.get('end_time')

            if not all([title, subject_id, class_id, term, session, duration, total_questions, start_time, end_time]):
                messages.error(request, "All fields are required.")
                raise ValueError("Missing fields")

            subject = Subject.objects.get(id=subject_id)
            classroom = ClassRoom.objects.get(id=class_id)

            CBTTest.objects.create(
                teacher=teacher_profile,
                title=title,
                subject=subject,
                classroom=classroom,
                term=term,
                session=session,
                duration_minutes=int(duration),
                total_questions=int(total_questions),
                start_time=start_time,
                end_time=end_time
            )

            messages.success(request, "Test created successfully!")
            return redirect('manage_cbt_tests')

        except Exception as e:
            print(f"[ERROR creating CBT test]: {e}")
            messages.error(request, "An error occurred while creating the test.")

    return render(request, 'teacher/create_cbt_test.html', {
        'subjects': subjects,
        'classes': classes,
    })


# Edit CBT Test
@login_required
def edit_cbt_test(request, test_id):
    test = get_object_or_404(CBTTest, id=test_id, teacher__user=request.user)

    if request.method == 'POST':
        test.title = request.POST.get('title')
        test.term = request.POST.get('term')
        test.session = request.POST.get('session')
        test.duration_minutes = request.POST.get('duration_minutes')
        test.total_questions = request.POST.get('total_questions')
        test.start_time = request.POST.get('start_time')
        test.end_time = request.POST.get('end_time')
        test.save()
        messages.success(request, 'Test updated successfully.')
        return redirect('manage_cbt_tests')

    return render(request, 'teacher/edit_cbt_test.html', {'test': test})


# Delete CBT Test
@login_required
def delete_cbt_test(request, test_id):
    test = get_object_or_404(CBTTest, id=test_id, teacher__user=request.user)

    if request.method == 'POST':
        test.delete()
        messages.success(request, 'Test deleted successfully.')
        return redirect('manage_cbt_tests')

    return render(request, 'teacher/delete_cbt_test.html', {'test': test})


@login_required
def add_cbt_question(request, test_id):
    test = get_object_or_404(CBTTest, id=test_id, teacher__user=request.user)
    questions = CBTQuestion.objects.filter(test=test)
    
    if request.method == 'POST':
        form = CBTQuestionForm(request.POST)
        if form.is_valid():
            if questions.count() >= test.total_questions:
                messages.warning(request, "You have reached the maximum number of questions.")
            else:
                question = form.save(commit=False)
                question.test = test
                question.save()
                messages.success(request, "Question added successfully.")
            return redirect('add_cbt_question', test_id=test.id)
    else:
        form = CBTQuestionForm()
    
    return render(request, 'teacher/add_cbt_question.html', {
        'test': test,
        'form': form,
        'questions': questions
    })

@login_required
def edit_cbt_question(request, question_id):
    question = get_object_or_404(CBTQuestion, id=question_id, test__teacher__user=request.user)
    test = question.test

    if request.method == 'POST':
        form = CBTQuestionForm(request.POST, instance=question)
        if form.is_valid():
            form.save()
            messages.success(request, 'Question updated successfully.')
            return redirect('add_cbt_question', test_id=test.id)
    else:
        form = CBTQuestionForm(instance=question)

    return render(request, 'teacher/edit_cbt_question.html', {'form': form, 'test': test})


@login_required
def delete_cbt_question(request, question_id):
    question = get_object_or_404(CBTQuestion, id=question_id, test__teacher__user=request.user)
    test = question.test

    if request.method == 'POST':
        question.delete()
        messages.success(request, 'Question deleted successfully.')
        return redirect('add_cbt_question', test_id=test.id)

    return render(request, 'teacher/delete_cbt_question.html', {'question': question, 'test': test})

@login_required
def activate_cbt_test(request, test_id):
    test = get_object_or_404(CBTTest, id=test_id, teacher__user=request.user)
    test.is_active = True
    test.save()
    messages.success(request, 'Test activated successfully.')
    return redirect('manage_cbt_tests')

# =========================
# CBT - Student Views
# =========================

@login_required
def available_cbts(request):
    if request.user.user_type != 'student':
        return HttpResponse("Unauthorized", status=401)

    # ✅ Get StudentProfile
    student_profile = get_object_or_404(StudentProfile, user=request.user)

    # ✅ Show only tests for the student's classroom
    class_cbts = CBTTest.objects.filter(
        is_active=True,
        classroom=student_profile.classroom
    ).order_by('-start_time')

    return render(request, 'student/available_cbts.html', {
        'cbts': class_cbts
    })


@login_required
def start_cbt_test(request, test_id):
    test = get_object_or_404(CBTTest, id=test_id, is_active=True)

    # ✅ Get StudentProfile
    student_profile = get_object_or_404(StudentProfile, user=request.user)

    # ✅ Prevent multiple submissions
    if CBTSubmission.objects.filter(student=student_profile, test=test).exists():
        return render(request, 'student/cbt_already_taken.html', {'test': test})

    questions = CBTQuestion.objects.filter(test=test)

    if request.method == 'POST':
        submission = CBTSubmission.objects.create(student=student_profile, test=test)
        for question in questions:
            answer_key = f"question_{question.id}"
            selected_option = request.POST.get(answer_key)
            if selected_option:
                CBTAnswer.objects.create(
                    submission=submission,
                    question=question,
                    selected_option=selected_option
                )
        return redirect('view_cbt_result', submission_id=submission.id)

    return render(request, 'student/start_cbt_test.html', {'test': test, 'questions': questions})


@login_required
def view_cbt_result(request, submission_id):
    # ✅ Get StudentProfile
    student_profile = get_object_or_404(StudentProfile, user=request.user)

    submission = get_object_or_404(CBTSubmission, id=submission_id, student=student_profile)
    answers = CBTAnswer.objects.filter(submission=submission)

    total_questions = answers.count()
    correct_answers = sum(1 for ans in answers if ans.selected_option == ans.question.correct_option)
    score_percentage = (correct_answers / total_questions) * 100 if total_questions > 0 else 0

    return render(request, 'student/cbt_result.html', {
        'submission': submission,
        'answers': answers,
        'score': correct_answers,
        'total': total_questions,
        'percentage': round(score_percentage, 2),
    })


@login_required
def view_cbt_results(request):
    if request.user.user_type != 'student':
        return HttpResponse("Unauthorized", status=401)

    # ✅ Get StudentProfile
    student_profile = get_object_or_404(StudentProfile, user=request.user)

    submissions = CBTSubmission.objects.filter(student=student_profile).order_by('-submitted_at')

    return render(request, 'student/cbt_results_list.html', {
        'submissions': submissions
    })


from operator import itemgetter

# =========================
# CBT - Teacher Views
# =========================

@login_required
def manage_cbt_tests(request):
    try:
        teacher_profile = TeacherProfile.objects.get(user=request.user)
    except TeacherProfile.DoesNotExist:
        return HttpResponse("Teacher profile not found", status=404)

    tests = CBTTest.objects.filter(teacher=teacher_profile).order_by('-created_at')
    return render(request, 'teacher/manage_cbt_tests.html', {'tests': tests})


@login_required
def teacher_cbt_results(request, test_id):
    test = get_object_or_404(CBTTest, id=test_id, teacher__user=request.user)

    submissions = CBTSubmission.objects.filter(test=test).select_related('student__user')
    result_data = []

    for sub in submissions:
        answers = CBTAnswer.objects.filter(submission=sub)
        total = answers.count()
        correct = sum(1 for ans in answers if ans.selected_option == ans.question.correct_option)
        percentage = (correct / total) * 100 if total > 0 else 0

        result_data.append({
            'student': sub.student.user.get_full_name() or sub.student.user.username,  # ✅ fixed
            'submitted_at': sub.submitted_at,
            'score': correct,
            'total': total,
            'percentage': round(percentage, 2),
        })

    # Sort result_data by score descending
    result_data.sort(key=lambda x: x['score'], reverse=True)

    # Assign ranks
    rank = 1
    previous_score = None
    for i, result in enumerate(result_data):
        if previous_score is None or result['score'] < previous_score:
            rank = i + 1
        result['rank'] = rank
        previous_score = result['score']

    return render(request, 'teacher/cbt_results_by_test.html', {
        'test': test,
        'results': result_data,
    })

# Library

@login_required
def librarian_dashboard(request):
    if request.user.user_type != 'librarian':
        return redirect('login')  

    total_books = Book.objects.count()
    borrowed_books = BorrowRecord.objects.filter(return_date__isnull=True).count()
    overdue_books = BorrowRecord.objects.filter(
        return_date__isnull=True,
        due_date__lt=timezone.now()
    ).count()

    return render(request, 'librarian/dashboard.html', {
        'total_books': total_books,
        'borrowed_books': borrowed_books,
        'overdue_books': overdue_books,
    })


@login_required
def add_book(request):
    if request.method == "POST":
        title = request.POST.get("title")
        author = request.POST.get("author")
        isbn = request.POST.get("isbn")
        category = request.POST.get("category")
        quantity = request.POST.get("quantity")
        barcode = request.POST.get("barcode")
        shelf_location = request.POST.get("shelf_location")

        if Book.objects.filter(barcode=barcode).exists():
            messages.error(request, "⚠ Book with this barcode already exists.")
        else:
            Book.objects.create(
                title=title,
                author=author,
                isbn=isbn,
                category=category,
                quantity=quantity,
                barcode=barcode,
                shelf_location=shelf_location
            )
            messages.success(request, "✅ Book added successfully!")
            return redirect('view_books')

    return render(request, 'librarian/add_book.html')


@login_required
def view_books(request):
    books = Book.objects.all()
    return render(request, 'librarian/view_books.html', {'books': books})


@login_required
def borrow_book(request):
    if request.method == "POST":
        student_barcode = request.POST.get("student_barcode")
        book_barcode = request.POST.get("book_barcode")

        try:
            student = StudentProfile.objects.get(barcode=student_barcode)
            book = Book.objects.get(barcode=book_barcode)

            if book.quantity < 1:
                messages.error(request, "❌ Book not available.")
            else:
                BorrowRecord.objects.create(
                    student=student,
                    book=book,
                    borrow_date=timezone.now(),
                    due_date=timezone.now() + timedelta(days=14)
                )
                book.quantity -= 1
                book.save()
                messages.success(
                    request,
                    f"✅ {book.title} borrowed by {student.user.get_full_name()}"
                )

        except StudentProfile.DoesNotExist:
            messages.error(request, "⚠ Student not found.")
        except Book.DoesNotExist:
            messages.error(request, "⚠ Book not found.")

    return render(request, 'librarian/borrow_book.html')


@login_required
def return_book(request):
    if request.method == "POST":
        borrow_id = request.POST.get("borrow_id")
        try:
            record = BorrowRecord.objects.get(id=borrow_id, return_date__isnull=True)
            record.return_date = timezone.now()
            record.book.quantity += 1
            record.book.save()
            record.save()
            messages.success(request, "✅ Book returned successfully!")
        except BorrowRecord.DoesNotExist:
            messages.error(request, "⚠ Borrow record not found or already returned.")

    borrow_records = BorrowRecord.objects.filter(return_date__isnull=True)
    return render(request, 'librarian/return_book.html', {'borrow_records': borrow_records})


@login_required
def borrow_history(request):
    records = BorrowRecord.objects.all().order_by('-borrow_date')
    return render(request, 'librarian/borrow_history.html', {'records': records})


def view_results(request):
    # Get filter values from GET parameters
    class_id = request.GET.get('class_id')
    term_id = request.GET.get('term_id')
    session_id = request.GET.get('session_id')

    # Fetch all filter options
    classes = ClassRoom.objects.all()
    terms = Term.objects.all()
    sessions = Session.objects.all()

    # Start with all results
    results = Result.objects.all()

    # Apply filters
    if class_id:
        results = results.filter(student__classroom_id=class_id)
    if term_id:
        results = results.filter(term_id=term_id)
    if session_id:
        results = results.filter(session_id=session_id)

    # Pass data to the template
    context = {
        'results': results,
        'classes': classes,
        'terms': terms,
        'sessions': sessions,
        'selected_class_id': class_id,
        'selected_term_id': term_id,
        'selected_session_id': session_id,
    }
    return render(request, 'admin/view_results.html', context)


from django.template.loader import get_template
from xhtml2pdf import pisa

@login_required
def student_view_results(request):
    student_profile = get_object_or_404(StudentProfile, user=request.user)

    sessions = Session.objects.all()
    terms = Term.objects.all()

    selected_session = request.GET.get("session")
    selected_term = request.GET.get("term")

    results = Result.objects.filter(student=student_profile)

    # Apply filters
    if selected_session or selected_term:
        if selected_session:
            results = results.filter(session_id=selected_session)
        if selected_term:
            results = results.filter(term_id=selected_term)
    else:
        results = Result.objects.none()

    # Handle PDF download
    if "download" in request.GET:
        template_path = "student/result_pdf.html"
        context = {
            "student": student_profile,
            "results": results,
            "selected_session": selected_session,
            "selected_term": selected_term,
        }
        template = get_template(template_path)
        html = template.render(context)

        response = HttpResponse(content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="results_{student_profile.user.username}.pdf"'

        pisa_status = pisa.CreatePDF(html, dest=response)
        if pisa_status.err:
            return HttpResponse("Error generating PDF")
        return response

    return render(request, "student/view_results.html", {
        "student": student_profile,
        "results": results,
        "sessions": sessions,
        "terms": terms,
        "selected_session": selected_session,
        "selected_term": selected_term,
    })
