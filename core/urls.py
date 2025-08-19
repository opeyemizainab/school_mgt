from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from .views import teacher_view_results, promote_students
from . import views

urlpatterns = [
    # =========================
    # Admin site
    # =========================
    path('admin/', admin.site.urls),

    # =========================
    # Authentication
    # =========================
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # =========================
    # Dashboards
    # =========================
    path('admin_dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('teacher_dashboard/', views.teacher_dashboard, name='teacher_dashboard'),
    path('student_dashboard/', views.student_dashboard, name='student_dashboard'),

    # =========================
    # Student Views
    # =========================
    path('student/profile/', views.student_profile, name='student_profile'),
    path('student/view-results/', views.student_view_results, name='student_view_results'),
    path('download_report_card/', views.download_report_card, name='download_report_card'),
    path('upload_result/', views.upload_result, name='upload_result'),

    # =========================
    # Admin Panel - Students
    # =========================
    path('admin-panel/students/', views.manage_students, name='manage_students'),
    path('admin-panel/students/create-user/', views.create_student_user, name='create_student_user'),
    path('admin-panel/students/edit/<int:student_id>/', views.edit_student, name='edit_student'),
    path('admin-panel/students/delete/<int:student_id>/', views.delete_student, name='delete_student'),
    path('admin-panel/students/search/', views.search_students, name='search_students'),
    path('admin-panel/classes/<int:class_id>/students/', views.view_class_students, name='view_class_students'),

    # Promotion
    path('admin-panel/promote-students/', promote_students, name='promote_students'),

    path(
        'admin-panel/results/toggle-lock/class/<int:class_id>/<int:term_id>/<int:session_id>/',
        views.toggle_class_results_lock,
        name='toggle_class_results_lock'
    ),

    # =========================
    # Admin Panel - Teachers
    # =========================
    path('admin-panel/teachers/', views.manage_teachers, name='manage_teachers'),
    path('admin-panel/teachers/add/', views.add_teacher, name='add_teacher'),
    path('admin-panel/teachers/edit/<int:teacher_id>/', views.edit_teacher, name='edit_teacher'),
    path('admin-panel/teachers/delete/<int:teacher_id>/', views.delete_teacher, name='delete_teacher'),

    # =========================
    # Admin Panel - Classes
    # =========================
    path('admin-panel/classes/', views.manage_classes, name='manage_classes'),
    path('admin-panel/classes/add/', views.add_class, name='add_class'),
    path('admin-panel/classes/edit/<int:class_id>/', views.edit_class, name='edit_class'),
    path('admin-panel/classes/delete/<int:class_id>/', views.delete_class, name='delete_class'),

    # =========================
    # Admin Panel - Subjects
    # =========================
    path('admin-panel/subjects/', views.manage_subjects, name='manage_subjects'),
    path('admin-panel/subjects/delete/<int:subject_id>/', views.delete_subject, name='delete_subject'),
    path('teacher/assign-students/', views.assign_students_to_subject, name='assign_students_to_subject'),

    # =========================
    # Results Management
    # =========================
    path('admin-panel/view-results/', views.admin_view_results, name='admin_view_results'),
    path('teacher/view_results/', teacher_view_results, name='teacher_view_results'),
    path(
        'admin-panel/view-results/<int:student_id>/<int:term_id>/<int:session_id>/',
        views.admin_student_results_detail,
        name='admin_student_results_detail'
    ),
    path(
        'admin-panel/result/<int:result_id>/edit/',
        views.admin_edit_result,
        name='admin_edit_result'
    ),

    # =========================
    # Fee Management
    # =========================
    path('admin-panel/fees/', views.manage_fees, name='manage_fees'),
    path('admin-panel/fees/add/', views.add_fee, name='add_fee'),
    path('admin-panel/fees/edit/<int:fee_id>/', views.edit_fee, name='edit_fee'),
    path('admin-panel/fees/delete/<int:fee_id>/', views.delete_fee, name='delete_fee'),
    path('admin-panel/fees/invoice/<int:fee_id>/', views.generate_invoice, name='generate_invoice'),

    # =========================
    # CBT - Teacher
    # =========================
    path('teacher/cbt/', views.create_cbt_test, name='create_cbt_test'),
    path('teacher/cbt/create/', views.create_cbt_test, name='create_cbt_test'),
    path('teacher/cbt/manage/', views.manage_cbt_tests, name='manage_cbt_tests'),
    path('teacher/cbt/edit/<int:test_id>/', views.edit_cbt_test, name='edit_cbt_test'),
    path('teacher/cbt/delete/<int:test_id>/', views.delete_cbt_test, name='delete_cbt_test'),
    path('teacher/cbt/<int:test_id>/add-question/', views.add_cbt_question, name='add_cbt_question'),
    path('teacher/cbt/question/edit/<int:question_id>/', views.edit_cbt_question, name='edit_cbt_question'),
    path('teacher/cbt/question/delete/<int:question_id>/', views.delete_cbt_question, name='delete_cbt_question'),
    path('teacher/cbt/activate/<int:test_id>/', views.activate_cbt_test, name='activate_cbt_test'),
    path('teacher/cbt/results/<int:test_id>/', views.teacher_cbt_results, name='teacher_cbt_results'),

    # =========================
    # CBT - Student
    # =========================
    path('student/cbt/', views.available_cbts, name='available_cbts'),
    path('student/cbt/start/<int:test_id>/', views.start_cbt_test, name='start_cbt_test'),
    path('student/cbt/result/<int:submission_id>/', views.view_cbt_result, name='view_cbt_result'),
    path('student/cbt/results/', views.view_cbt_results, name='view_cbt_results'),

    # =========================
    # Session & Term Management
    # =========================
    path('admin-panel/sessions-terms/', views.manage_sessions_terms, name='manage_sessions_terms'),
    path('admin-panel/sessions/add/', views.add_session, name='add_session'),
    path('admin-panel/terms/add/', views.add_term, name='add_term'),
    path('admin-panel/sessions/set-current/<int:session_id>/', views.set_current_session, name='set_current_session'),
    path('admin-panel/terms/set-current/<int:term_id>/', views.set_current_term, name='set_current_term'),
    path('admin-panel/promote-students/', views.promote_students, name='promote_students'),


    # =========================
    # Library
    # =========================
    path('library/borrow/', views.borrow_book, name='borrow_book'),
    path('librarian/dashboard/', views.librarian_dashboard, name='librarian_dashboard'),
    path('librarian/add-book/', views.add_book, name='add_book'),
    path('librarian/view-books/', views.view_books, name='view_books'),
    path('librarian/borrow-book/', views.borrow_book, name='borrow_book'),
    path('librarian/return-book/', views.return_book, name='return_book'),
    path('librarian/borrow-history/', views.borrow_history, name='borrow_history'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
