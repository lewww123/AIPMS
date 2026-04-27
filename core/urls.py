from django.urls import path
from . import views

urlpatterns = [
     # ================= WEB DASHBOARDS =================
     # Bypassing the router so it goes directly to the Farmer Dashboard!
        path('', views.farmer_dashboard, name='home'),
        path('dashboard/', views.farmer_dashboard, name='dashboard'),
        path('lgu/', views.lgu_dashboard, name='lgu_dashboard'),
        
     

        # ================= FARMER UI API ENDPOINTS =================
        path('api/live-data/', views.get_live_data, name='get_live_data'),
        path('api/control-pump/', views.control_pump, name='control_pump'),

        # ================= ARDUINO / HARDWARE API =================
        path('api/data/', views.receive_data, name='receive_data'),

        # ================= LGU ANALYTICS & LOGS =================
        path('api/last-watered/', views.last_watered, name='last_watered'),
        path('api/daily/', views.daily_water_count, name='daily_water_count'),
        path('api/analytics/', views.analytics, name='analytics'),
        path('api/soil-history/', views.soil_history, name='soil_history'),
        path('api/water-logs/', views.water_logs, name='water_logs'),
        
           
        path("farmer/", views.farmer_entry, name="farmer_entry"),
        path("lgu/", views.lgu_entry, name="lgu_entry"),
        path("lgu-signup/", views.lgu_signup, name="lgu_signup"),
        path("check-lgu-status/", views.check_lgu_status, name="check_lgu_status"),
        
        path("lgu-logout/", views.lgu_logout, name="lgu_logout"),
        
        path("lgu/farms/add/", views.lgu_add_farm, name="lgu_add_farm"),
        path("lgu/farms/<int:farm_id>/edit/", views.lgu_farm_edit, name="lgu_farm_edit"),
        path("lgu/farms/<int:farm_id>/delete/", views.lgu_farm_delete, name="lgu_farm_delete"),
    ]