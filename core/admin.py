from django.contrib import admin
from .models import Farm, Block, SensorData, WaterLog, PumpControl, IrrigationSettings, FarmerProfile, LGUProfile, MicrocontrollerDevice

admin.site.register(Farm)
admin.site.register(Block)
admin.site.register(SensorData)
admin.site.register(WaterLog)
admin.site.register(PumpControl)
admin.site.register(FarmerProfile)
admin.site.register(LGUProfile)
admin.site.register(IrrigationSettings)
admin.site.register(MicrocontrollerDevice)