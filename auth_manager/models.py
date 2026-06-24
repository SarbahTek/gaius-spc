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
    phone_number        = models.CharField(max_length=20, unique=True, null=True, blank=True)
    date_of_birth       = models.DateField(null=True, blank=True)
    profile_photo       = models.ImageField(upload_to='avatars/', null=True, blank=True)
    email_verified      = models.BooleanField(default=False)
    phone_verified      = models.BooleanField(default=False)
    terms_accepted      = models.BooleanField(default=False)
    terms_accepted_at   = models.DateTimeField(null=True, blank=True)
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


class OtpCode(models.Model):
    """
    A one-time numeric code for email verification or phone login.

    Codes are short-lived and single-use. We look them up by (identifier,
    purpose), where identifier is an email address or a phone number.
    """
    PURPOSE_EMAIL_VERIFY = "email_verify"
    PURPOSE_PHONE_LOGIN  = "phone_login"
    PURPOSE_PHONE_VERIFY = "phone_verify"

    PURPOSE_CHOICES = [
        (PURPOSE_EMAIL_VERIFY, "Email verification"),
        (PURPOSE_PHONE_LOGIN,  "Phone login"),
        (PURPOSE_PHONE_VERIFY, "Phone verification"),
    ]

    CHANNEL_EMAIL = "email"
    CHANNEL_SMS   = "sms"

    identifier = models.CharField(max_length=255, db_index=True)  # email or phone
    purpose    = models.CharField(max_length=20, choices=PURPOSE_CHOICES)
    channel    = models.CharField(max_length=10, default=CHANNEL_EMAIL)
    code       = models.CharField(max_length=10)
    attempts   = models.PositiveIntegerField(default=0)
    is_used    = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["-created_at"]
        indexes  = [models.Index(fields=["identifier", "purpose", "is_used"])]

    def __str__(self):
        return f"{self.purpose} → {self.identifier} ({'used' if self.is_used else 'active'})"

    def is_expired(self):
        from django.utils import timezone
        return timezone.now() >= self.expires_at