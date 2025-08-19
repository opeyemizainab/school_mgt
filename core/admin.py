from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    User, ClassRoom, StudentProfile, Subject, Result,
    TeacherProfile, ClassAssignment, Session, Term
)


class CustomUserAdmin(UserAdmin):
    model = User
    list_display = ('username', 'email', 'user_type', 'is_staff', 'is_active')
    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('user_type',)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (None, {'fields': ('user_type',)}),
    )


# Register models
admin.site.register(User, CustomUserAdmin)
admin.site.register(ClassRoom)
admin.site.register(StudentProfile)
admin.site.register(Subject)
admin.site.register(TeacherProfile)
admin.site.register(ClassAssignment)


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_current')
    list_editable = ('is_current',)
    search_fields = ('name',)


@admin.register(Term)
class TermAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_current')
    list_editable = ('is_current',)
    search_fields = ('name',)


@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
    list_display = ('student', 'subject', 'term', 'session', 'test_score', 'exam_score', 'locked')
    list_filter = ('term', 'session', 'subject', 'locked')
    search_fields = ('student__user__first_name', 'student__user__last_name', 'subject__name')

    actions = ['lock_results', 'unlock_results']

    def lock_results(self, request, queryset):
        updated = queryset.update(locked=True)
        self.message_user(request, f"✅ {updated} result(s) locked successfully.")
    lock_results.short_description = "Lock selected results (teachers cannot edit them)"

    def unlock_results(self, request, queryset):
        updated = queryset.update(locked=False)
        self.message_user(request, f"✅ {updated} result(s) unlocked successfully.")
    unlock_results.short_description = "Unlock selected results (teachers can edit them)"
