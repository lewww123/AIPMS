from django.contrib import admin
from .models import Farm, Block, SensorData, WaterLog, PumpControl, FarmerProfile, LGUProfile, MicrocontrollerDevice

admin.site.register(Farm)
admin.site.register(Block)
admin.site.register(PumpControl)
admin.site.register(FarmerProfile)
admin.site.register(LGUProfile)
admin.site.register(MicrocontrollerDevice)

# 🔒 SensorData (no manual add)
class SensorDataAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

admin.site.register(SensorData, SensorDataAdmin)


# 🔒 WaterLog (read-only)
class WaterLogAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    readonly_fields = [field.name for field in WaterLog._meta.fields]

admin.site.register(WaterLog, WaterLogAdmin)