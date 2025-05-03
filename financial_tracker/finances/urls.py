from django.contrib import admin
from django.urls import path
from finances import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('logout/', views.logout_view, name='logout'),
    
    # API Endpoints
    
    path('api/categories/', views.get_categories, name='get_categories'),
    path('api/transactions/', views.get_transactions, name='get_transactions'),
    path('api/transactions/add/', views.add_transaction, name='add_transaction'),
    path('api/transactions/<int:pk>/update/', views.update_transaction, name='update_transaction'),
    path('api/transactions/<int:pk>/delete/', views.delete_transaction, name='delete_transaction'),
    path('api/transactions/<int:pk>/', views.get_transaction, name='get_transaction'),
    path('api/budgets/', views.get_budgets, name='get_budgets'),
    path('api/budgets/add/', views.add_budget, name='add_budget'),
    path('api/summary/', views.financial_summary, name='financial_summary'),
    path('api/report/', views.generate_report, name='generate_report'),
    path('api/upload-receipt/', views.upload_file, name='upload-receipt'),
]