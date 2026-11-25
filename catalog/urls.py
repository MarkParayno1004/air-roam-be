from django.urls import path

from catalog import views

urlpatterns = [
    path("products", views.ProductListView.as_view()),
    path("products/<uuid:pk>", views.ProductDetailView.as_view()),
    path("destinations", views.DestinationsView.as_view()),
]
