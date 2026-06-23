from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Central user model. Lives in accounts — everything else FKs to this.
    curriculum app imports this via settings.AUTH_USER_MODEL, never directly.
    """
    ROLE_STUDENT    = "student"
    ROLE_INSTRUCTOR = "instructor"
    ROLE_ADMIN      = "admin"

    ROLE_CHOICES = [
        (ROLE_STUDENT,    "Student"),
        (ROLE_INSTRUCTOR, "Instructor"),
        (ROLE_ADMIN,      "Admin"),
    ]

    LANG_EN  = 'en'
    LANG_TW  = 'ak'
    LANG_EWE = 'ee'
    LANG_HA  = 'ha'
    LANG_GA  = 'gaa'
    LANG_DAG = 'dag'
    LANG_FAT = 'fat'

    LANGUAGE_CHOICES = [
        (LANG_EN,  'English'),
        (LANG_TW,  'Twi'),
        (LANG_EWE, 'Ewe'),
        (LANG_HA,  'Hausa'),
        (LANG_GA,  'Ga'),
        (LANG_DAG, 'Dagbani'),
        (LANG_FAT, 'Fante'),
    ]

    role                = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_STUDENT)
    bio                 = models.TextField(blank=True)
    avatar              = models.URLField(blank=True)
    language_preference = models.CharField(max_length=10, choices=LANGUAGE_CHOICES, default=LANG_EN)
    created_at          = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.username} ({self.role})"

    @property
    def is_student(self):
        return self.role == self.ROLE_STUDENT

    @property
    def is_instructor(self):
        return self.role == self.ROLE_INSTRUCTOR