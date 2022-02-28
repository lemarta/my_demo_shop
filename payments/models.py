import weasyprint

from datetime import datetime
from io import BytesIO
from os import path
from re import match, search

from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.core.validators import MinValueValidator
from django.db.models import F
from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string

from users.models import User

# Create your models here.

mail_sender = settings.DEFAULT_FROM_EMAIL

company_details = settings.COMPANY_DETAILS

class TopUp(models.Model):
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    #details taken from payment_intent object
    payment_intent_id = models.CharField(max_length=250, blank=True)
    is_successful = models.BooleanField(default=False)
    #details taken from payment_intent.created event
    currency = models.CharField(max_length=3, blank=True)
    amount = models.IntegerField(null=True, validators=[MinValueValidator(15)])
    live_mode = models.BooleanField(null=True)

    def __str__(self, *args, **kwargs):
        return str(self.pk)

    @property
    def amount_full_units(self):
        if self.amount:
            return f'{self.amount / 100:.2f}'
    
    def create_invoice(self, event_body):
        address_pk = event_body.metadata.address_pk
        try:
            address = Address.objects.get(pk=address_pk)
        except Address.DoesNotExist:
            return HttpResponse(status=404)
        invoice = Invoice.objects.create(user=self.user, address=address, topup=self)
        return invoice

    def save_id_and_status(self, event_body):
        self.payment_intent_id = event_body.id
        if event_body.status == 'succeeded':
            self.is_successful == True
        return self

    def save_email(self, event_body):
        self.customer_email = event_body.email
        return self

    def save_amount_data(self, event_body):
        self.amount = event_body.amount
        self.currency = event_body.currency
        return self

    def is_live_mode(self, event_body):
        self.live_mode = event_body.livemode
        return self

    def increase_balance(self, request, event_body):
        amount_received = event_body.amount
        user = self.user
        if user.is_anonymous == True:
            return render(request, template_name='payments/payment_failure.html')
        user.money = F('money') + amount_received
        user.save()
        return True

class Address(models.Model):

    def postal_code_validator(value):
        if not bool(match(r'\d{2}-\d{3}', value)):
            message = '"{}" is not a valid postal code.'.format(value)
            raise ValidationError(message=message)

    date_created = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=128)
    surname = models.CharField(max_length=128)
    street_and_number = models.CharField(max_length=256)
    city = models.CharField(max_length=128)
    country = models.CharField(max_length=128)
    postal_code = models.CharField(max_length=6, validators=[postal_code_validator])

    def __str__(self, *args, **kwargs):
        return '{} {}, {} {} {}, {}'.format(
            self.name,
            self.surname,
            self.street_and_number,
            self.postal_code,
            self.city,
            self.country
        )


class Invoice(models.Model):
    date_created = models.DateTimeField(auto_now_add=True)
    name = models.CharField(max_length=32)
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    address = models.ForeignKey(Address, on_delete=models.PROTECT)
    topup = models.OneToOneField(TopUp, on_delete=models.PROTECT)

    @classmethod
    def get_name(cls, invoice, *args, **kwargs):
        current_month, current_year = invoice.date_created.month, invoice.date_created.year
        current_month_formatted = '{:02d}'.format(current_month)
        previous_invoice_this_month = cls.objects.filter(
            date_created__month=current_month,
            date_created__year=current_year,
        ).exclude(pk=invoice.pk).order_by('date_created').last()
        this_num = 1
        if previous_invoice_this_month:
            last_num = int(search(f'MDS/(.*?)/{current_month_formatted}/{current_year}', previous_invoice_this_month.name).group(1))
            this_num = last_num + 1
        name = 'MDS/{}/{}/{}'.format(this_num, current_month_formatted, current_year)
        return name
    
    def __str__(self, *args, **kwargs):
        return self.name

    def write_invoice_to_pdf(self, request, target):
        html = render_to_string('payments/invoice_pdf.html', {'invoice': self, 'company': company_details,})
        weasyprint.HTML(string=html, base_url=request.build_absolute_uri()).write_pdf(target)
        return target

    def send_email_with_invoice(self, request):
        subject = f'My Demo Shop - invoice {self.name}'
        message = 'Thank you for choosing our service. Attached you will find an invoice.'
        email = EmailMessage(subject=subject, body=message, from_email=mail_sender, to=[self.user.email])
        out = BytesIO()
        self.write_invoice_to_pdf(request, out)
        email.attach(filename=self.name, content=out.getvalue(), mimetype='application/pdf')
        email.send()
        return True