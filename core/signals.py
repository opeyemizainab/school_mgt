from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import User, StudentProfile, TeacherProfile
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import User, LibrarianProfile

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        if instance.user_type == 'student':
            StudentProfile.objects.create(user=instance)
        elif instance.user_type == 'teacher':
            TeacherProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def create_librarian_profile(sender, instance, created, **kwargs):
    if created and instance.user_type == 'librarian':
        LibrarianProfile.objects.create(user=instance)

