import stripe

from django import views
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import F
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView, ListView, FormView
from django.urls import reverse
from django.utils.decorators import method_decorator

from payments.forms import AmountAddressForm
from payments.models import Address, TopUp, Invoice
from payments.schemas import (
    ProductData, 
    PriceData, 
    LineItems, 
    LineItemsSchema, 
    Metadata, 
    MetadataSchema, 
    PaymentIntentData, 
    PaymentIntentDataSchema
)

# Create your views here.
stripe.api_key = settings.STRIPE_SECRET_KEY

endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

topup_data = settings.TOPUP_DATA

class TopUpView(LoginRequiredMixin, FormView):
    related_field = 'redirect_to'
    form_class = AmountAddressForm
    extra_context = {
            'STRIPE_PUBLIC_KEY': settings.STRIPE_PUBLIC_KEY,
        }
    template_name = 'payments/top_up.html'

    def get_last_address(self, request):
        return Address.objects.filter(user=request.user).order_by('date_created').last()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['last_address'] = self.get_last_address(request=self.request)
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        last_address = self.get_last_address(request=self.request)
        if not last_address:
            kwargs['address_choice_is_hidden'] = True
        return kwargs

    def get_initial(self):
        """Return the initial data to use for forms on this view."""
        initial = super().get_initial()
        last_address = self.get_last_address(request=self.request)
        if not last_address:
            initial['address_choice'] = self.form_class.ADDRESS_NEW
        return initial

    def form_valid(self, form):
        user = self.request.user
        last_address = self.get_last_address(self.request)
        # get the address for invoice
        if last_address:
            address_choice = form.cleaned_data['address_choice']
            if address_choice == form.ADDRESS_NEW:
                address = form.save(commit=False)
                address.user = user
                address.save()
            elif address_choice == form.ADDRESS_LAST:
                address = last_address
        else:
            address = form.save(commit=False)
            address.user = user
            address.save()
        # get the amount that customer wants to top up his account with
        topup_value = form.cleaned_data['top_up_amount']
        # assign all values needed to open a checkout session with Stripe
        # get success and cancel url
        success_url = self.request.build_absolute_uri(reverse('payments:success'))
        cancel_url = self.request.build_absolute_uri(reverse('payments:cancel'))
        # get line items json
        intent_value = int(topup_value) * 100
        product_data = ProductData(name=topup_data['name'])
        price_data = PriceData(currency=topup_data['currency'], unit_amount=intent_value, product_data=product_data)
        line_items = LineItems(price_data=price_data, quantity=topup_data['quantity'])
        line_items_json = LineItemsSchema().dump(line_items)
        # get metadatas with id of empty transaction for currently logged in user to retrieve it back in wehbhooks
        topup_pk = TopUp.objects.create(user=user).pk
        metadata = Metadata(topup_pk=topup_pk, address_pk=address.pk)
        metadata_json = MetadataSchema().dump(metadata)
        payment_intent_data = PaymentIntentData(metadata=metadata)
        payment_intent_data_json = PaymentIntentDataSchema().dump(payment_intent_data)
        # open checkout session with Stripe with jsons
        checkout_session = stripe.checkout.Session.create(
            line_items=[line_items_json,],
            metadata=metadata_json,
            mode=topup_data['mode'],
            payment_intent_data=payment_intent_data_json,
            success_url=success_url,
            cancel_url=cancel_url,
        )
        # redirect to Stripe's checkout session 

        return redirect(checkout_session.url, code=303)


class SuccessView(TemplateView):
    template_name = 'payments/success.html'


class CancelView(TemplateView):
    template_name = 'payments/cancel.html'


@method_decorator(csrf_exempt, name='dispatch')
class WebhookView(View):

    def post(self, request, *args, **kwargs):
        payload = request.body
        # header in the response that is coming from Stripe
        sig_header = request.META['HTTP_STRIPE_SIGNATURE']
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, endpoint_secret
            )
        except (ValueError, stripe.error.SignatureVerificationError):
            # Invalid payload or signature
            return HttpResponse(status=400)

        # get payload and type of object that came in the event
        event_body, object_type = get_event_payload_and_type(event)
        # only checkout_session, payment_intent and charge objects come back with metadata
        if getattr(event_body.metadata, 'topup_pk', None) and object_type == 'payment_intent':
            topup = get_transaction_record(event_body)
            # find transaction's record in database
            topup.save_id_and_status(event_body)  # save event's id and status
            if event.type == 'payment_intent.created':
                topup.save_amount_data(event_body)
                topup.is_live_mode(event_body)  # flags if test or live
            elif event.type == 'payment_intent.succeeded':
                topup.increase_balance(request, event_body) # add funds to user's account
                invoice = topup.create_invoice(event_body)
                invoice.name = Invoice.get_name(invoice)
                invoice.save()
                invoice.send_email_with_invoice(request) # send invoice to currently logged user's (! )e-mail

            topup.save()
        return HttpResponse(status=200)

def get_event_payload_and_type(event):
    event_body = event.data.object
    object_type = event_body.object
    return event_body, object_type

def get_transaction_record(event_body):
    topup_pk = event_body.metadata.topup_pk
    try:
        topup = TopUp.objects.get(pk=topup_pk)
        return topup
    except TopUp.DoesNotExist:
        return HttpResponse(status=404)


class GetInvoiceView(LoginRequiredMixin, views.View):
    def get(self, request, *args, **kwargs):
        if request.user.is_staff:
            invoice_pk = self.kwargs['invoice_pk']
            invoice = get_object_or_404(Invoice, pk=invoice_pk)
            response = HttpResponse(content=b'',headers={
                'Content-Type': 'application/pdf',
                'Content-Disposition': 'attachment; filename={}'.format(invoice.name),
            })
            invoice.write_invoice_to_pdf(request, response)
            return response
        else:
            return HttpResponse(status=403, content="Sorry, you're not authorised to see this content.")