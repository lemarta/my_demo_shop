from django.conf import settings
from django.shortcuts import render
from django.views.generic import TemplateView

# Create your views here.


class HomepageView(TemplateView):
    template_name = 'store/about-me.html'