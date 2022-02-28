from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy

# Create your views here.


class CustomLoginView(LoginView):
    template_name='users/login.html'
    next_page = reverse_lazy('homepage')

class CustomLogoutView(LogoutView):
    template_name='users/logout.html'