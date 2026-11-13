from django.db import models
from django.conf import settings


class Member(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("inactive", "Inactive"),
        ("suspended", "Suspended"),
    ]

    GENDER_CHOICES = [
        ("male", "Male"),
        ("female", "Female"),
        ("other", "Other"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="member_profile",
    )

    member_number = models.CharField(
        max_length=20,
        unique=True,
    )

    national_id = models.CharField(
        max_length=20,
        unique=True,
    )

    phone_number = models.CharField(
        max_length=15,
    )

    gender = models.CharField(
        max_length=10,
        choices=GENDER_CHOICES,
    )

    date_of_birth = models.DateField()

    county = models.CharField(
        max_length=100,
    )

    address = models.TextField()

    date_joined = models.DateField(
        auto_now_add=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active",
    )

    # True once the member's first M-Pesa payment (registration fee) clears via
    # Daraja.  Set to False for members who joined before Daraja integration or
    # who have not yet completed their first payment.
    daraja_registered = models.BooleanField(
        default=False,
        help_text="Member has completed their first Daraja/M-Pesa payment "
                  "(registration fee).  Required before further SACCO payments "
                  "can be made via M-Pesa.",
    )

    def __str__(self):
        return f"{self.member_number} - {self.user.get_full_name()}"
