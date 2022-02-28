from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.utils.translation import ugettext_lazy as _

# Create your models here.


class User(AbstractUser):
    """
    Overrides default User model
    """
    email = models.EmailField(_('email address'), unique=True)
    money = models.PositiveIntegerField(default=0) # caution - grosze!

    def __str__(self):
        return self.email

    @property
    def money_full_units(self):
        return f'{self.money / 100:.2f}'