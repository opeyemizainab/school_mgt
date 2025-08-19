from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta





# =========================
# User Model
# =========================
class User(AbstractUser):
    USER_TYPE_CHOICES = (
        ('admin', 'Admin'),
        ('teacher', 'Teacher'),
        ('student', 'Student'),
        ('librarian', 'Librarian'),
    )
    user_type = models.CharField(max_length=10, choices=USER_TYPE_CHOICES)

    def __str__(self):
        return f"{self.username} ({self.user_type})"


# =========================
# Academic Structure
# =========================
class ClassRoom(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class Session(models.Model):
    name = models.CharField(max_length=20, unique=True)  # e.g. "2024/2025"
    is_current = models.BooleanField(default=False)

    class Meta:
        ordering = ['-name']
        verbose_name = 'Session'
        verbose_name_plural = 'Sessions'

    def save(self, *args, **kwargs):
        if self.is_current:
            Session.objects.exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    @classmethod
    def get_current(cls):
        return cls.objects.filter(is_current=True).first()


class Term(models.Model):
    name = models.CharField(max_length=50, unique=True)   # e.g. "First Term"
    is_current = models.BooleanField(default=False)

    class Meta:
        ordering = ['name']
        verbose_name = 'Term'
        verbose_name_plural = 'Terms'

    def save(self, *args, **kwargs):
        if self.is_current:
            Term.objects.exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    @classmethod
    def get_current(cls):
        return cls.objects.filter(is_current=True).first()


# =========================
# Profiles
# =========================
class StudentProfile(models.Model):
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
    ]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    classroom = models.ForeignKey(ClassRoom, on_delete=models.SET_NULL, null=True, blank=True)
    session = models.ForeignKey(Session, on_delete=models.SET_NULL, null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    address = models.TextField(blank=True)
    photo = models.ImageField(upload_to='student_photos/', null=True, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, null=True, blank=True)
    graduated = models.BooleanField(default=False)  # ✅ Track if the student has graduated

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class TeacherProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    gender = models.CharField(max_length=10)
    phone = models.CharField(max_length=20)
    photo = models.ImageField(upload_to='teacher_photos/', blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    department = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class LibrarianProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.user.get_full_name()


# =========================
# Subjects & Assignments
# =========================
class Subject(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class ClassAssignment(models.Model):
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE)
    classroom = models.ForeignKey(ClassRoom, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.teacher.user.username} teaches {self.subject.name} in {self.classroom.name}"


# =========================
# Results
# =========================
class Result(models.Model):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    test_score = models.DecimalField(max_digits=5, decimal_places=2)
    exam_score = models.DecimalField(max_digits=5, decimal_places=2)
    term = models.ForeignKey(Term, on_delete=models.SET_NULL, null=True, blank=True)
    session = models.ForeignKey(Session, on_delete=models.SET_NULL, null=True, blank=True)

    GRADE_CHOICES = [
        ('A', 'A'),
        ('B', 'B'),
        ('C', 'C'),
        ('D', 'D'),
        ('F', 'F'),
    ]
    grade = models.CharField(max_length=2, choices=GRADE_CHOICES, blank=True)
    comment = models.TextField(blank=True)
    locked = models.BooleanField(default=False)  # For locking results

    def total_score(self):
        return self.test_score + self.exam_score

    def __str__(self):
        term_display = self.term.name if self.term else "No Term"
        session_display = self.session.name if self.session else "No Session"
        return f"{self.student} - {self.subject} - {term_display} {session_display}"


# =========================
# Fees
# =========================
class Fee(models.Model):
    STATUS_CHOICES = [
        ('paid', 'Paid'),
        ('unpaid', 'Unpaid'),
        ('partial', 'Partial'),
    ]
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    term = models.ForeignKey(Term, on_delete=models.SET_NULL, null=True, blank=True)
    session = models.ForeignKey(Session, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, blank=True)
    is_paid = models.BooleanField(default=False)
    due_date = models.DateField(null=True, blank=True)
    payment_date = models.DateField(null=True, blank=True)
    date_paid = models.DateField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.is_paid:
            self.status = 'paid'
        elif self.amount == 0:
            self.status = 'unpaid'
        else:
            self.status = 'partial'
        super().save(*args, **kwargs)

    def __str__(self):
        term_display = self.term.name if self.term else "No Term"
        session_display = self.session.name if self.session else "No Session"
        return f"{self.student.user.get_full_name()} - ₦{self.amount} - {term_display} - {session_display} - {self.status.title()}"


# =========================
# CBT
# =========================
class CBTTest(models.Model):
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    classroom = models.ForeignKey(ClassRoom, on_delete=models.CASCADE)
    term = models.CharField(max_length=20)
    session = models.CharField(max_length=20)
    duration_minutes = models.PositiveIntegerField()
    total_questions = models.PositiveIntegerField()
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.title} - {self.classroom.name}"


class CBTQuestion(models.Model):
    test = models.ForeignKey(CBTTest, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    option_a = models.CharField(max_length=255)
    option_b = models.CharField(max_length=255)
    option_c = models.CharField(max_length=255)
    option_d = models.CharField(max_length=255)
    correct_option = models.CharField(max_length=1, choices=[
        ('A', 'Option A'),
        ('B', 'Option B'),
        ('C', 'Option C'),
        ('D', 'Option D')
    ])

    def __str__(self):
        return self.question_text[:50]


class CBTSubmission(models.Model):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE)  # ✅ Changed to StudentProfile
    test = models.ForeignKey(CBTTest, on_delete=models.CASCADE)
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.student.user.username} - {self.test.title}"


class CBTAnswer(models.Model):
    submission = models.ForeignKey(CBTSubmission, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(CBTQuestion, on_delete=models.CASCADE)
    selected_option = models.CharField(max_length=1, choices=[
        ('A', 'A'),
        ('B', 'B'),
        ('C', 'C'),
        ('D', 'D'),
    ])


# =========================
# Enrollments
# =========================
class StudentSubjectEnrollment(models.Model):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    classroom = models.ForeignKey(ClassRoom, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('student', 'subject', 'classroom')

    def __str__(self):
        return f"{self.student} - {self.subject} ({self.classroom})"


# =========================
# Library
# =========================
class Book(models.Model):
    title = models.CharField(max_length=200)
    author = models.CharField(max_length=200)
    isbn = models.CharField(max_length=13, unique=True)
    category = models.CharField(max_length=100)
    quantity = models.PositiveIntegerField(default=1)
    barcode = models.CharField(max_length=100, unique=True)
    shelf_location = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"{self.title} ({self.barcode})"


def default_due_date():
    return timezone.now() + timedelta(days=14)


class BorrowRecord(models.Model):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE)
    book = models.ForeignKey(Book, on_delete=models.CASCADE)
    borrow_date = models.DateTimeField(default=timezone.now)
    due_date = models.DateTimeField(default=default_due_date)
    return_date = models.DateTimeField(null=True, blank=True)
    fine = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)

    def is_overdue(self):
        return not self.return_date and timezone.now() > self.due_date

    def __str__(self):
        return f"{self.student.user.get_full_name()} borrowed {self.book.title}"










##################################

