from django.urls import path

from accounts import views

urlpatterns = [
    path("auth/csrf", views.CsrfView.as_view()),
    path("auth/register", views.RegisterView.as_view()),
    path("auth/login", views.LoginView.as_view()),
    path("auth/refresh", views.RefreshView.as_view()),
    path("auth/logout", views.LogoutView.as_view()),
    path("auth/web/login", views.CookieLoginView.as_view()),
    path("auth/web/refresh", views.CookieRefreshView.as_view()),
    path("auth/web/logout", views.CookieLogoutView.as_view()),
    path("me", views.MeView.as_view()),
]
