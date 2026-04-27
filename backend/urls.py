"""
URL configuration for backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from core import views   


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/data/', views.receive_data),
    path("", include("core.urls")),
    path("lgu/create-farmer/", views.lgu_create_farmer, name="lgu_create_farmer"),
    path("farmer-login/", views.farmer_login, name="farmer_login"),
    path("logout/", views.farmer_logout, name="farmer_logout"),
    path("farmer-dashboard/", views.farmer_dashboard, name="farmer_dashboard"),
    path("change-pin/", views.change_pin, name="change_pin"),
   
    path("lgu/", views.lgu_dashboard, name="lgu_dashboard"),
    path("lgu/farm/<int:farm_id>/", views.lgu_farm_detail, name="lgu_farm_detail"),
    path("lgu/block/<int:block_id>/", views.lgu_block_detail, name="lgu_block_detail"),
    path("lgu-login/", views.lgu_login, name="lgu_login"),
    
    #________sidebar______________#
    path("lgu/farms/", views.lgu_farms, name="lgu_farms"),
    path("lgu/farmers/", views.lgu_farmers, name="lgu_farmers"),
    path("lgu/analytics/", views.lgu_analytics, name="lgu_analytics"),
    path("lgu/logs/", views.lgu_logs, name="lgu_logs"),
 
    
    #___________________CRUUUUUUUUUUUUUUUUUUDDDDDDDDDD_________#
    path("lgu/farmers/<int:farmer_id>/", views.lgu_farmer_detail, name="lgu_farmer_detail"),
    path("lgu/farmers/<int:farmer_id>/edit/", views.lgu_farmer_edit, name="lgu_farmer_edit"),
    path("lgu/farmers/<int:farmer_id>/delete/", views.lgu_farmer_delete, name="lgu_farmer_delete"),
    path("lgu/farmers/<int:farmer_id>/reset-pin/", views.lgu_reset_pin, name="lgu_reset_pin"),
    path("lgu/farmers/<int:farmer_id>/unlock/", views.lgu_unlock_farmer, name="lgu_unlock_farmer"),
    
    path('farmer/update-thresholds/', views.update_thresholds, name='update_thresholds'),
 
]


