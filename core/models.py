from django.db import models
from django.contrib.auth.models import User
from django.http import JsonResponse

class IrrigationSettings(models.Model):
    dry_level = models.IntegerField(default=30)
    wet_level = models.IntegerField(default=70)
    auto_mode = models.BooleanField(default=True)
    manual_mode = models.BooleanField(default=False)

    # Note: With the new time-based logic, these levels act more as 
    # safety thresholds rather than the primary trigger.

class Farm(models.Model):
    name = models.CharField(max_length=100, default="My Farm")
    location = models.CharField(max_length=200, default="Puerto Princesa City")
    farmer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="farms")

    def __str__(self):
        return f"{self.name} - {self.location}"
    
class Block(models.Model):
    """A specific section of the farm (e.g., Block A, North Field)"""
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name="blocks")
    name = models.CharField(max_length=100) # e.g., "Block 1"
    
    # Each block has its own real-time state
    current_moisture = models.FloatField(default=0.0)
    current_ph = models.FloatField(default=7.0)
    current_temp = models.FloatField(default=0.0)
    is_raining = models.BooleanField(default=False)
    
    # Independent Control per Block
    MODE_CHOICES = [('manual', 'Manual'), ('auto', 'Auto')]
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default='auto')
    pump_status = models.BooleanField(default=False)
    
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.farm.name} - {self.name}"

class SensorData(models.Model):
    block = models.ForeignKey(Block, on_delete=models.CASCADE, related_name="sensor_readings")
    soil_moisture = models.IntegerField()
    ph_level = models.FloatField(default=7.0)
    temperature = models.FloatField(default=0.0)
    is_raining = models.BooleanField(default=False)
    pump_status = models.BooleanField(default=False)
    mode = models.CharField(max_length=10, default="auto")
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"Farm: {self.block.farm.name} | Block: {self.block.name} | Soil: {self.soil_moisture}%"

class WaterLog(models.Model):
    block = models.ForeignKey(Block, on_delete=models.CASCADE, related_name="water_logs")
    timestamp = models.DateTimeField(auto_now_add=True)
    amount = models.FloatField(default=0.0)
    moisture_at_time = models.IntegerField(default=0)
    mode = models.CharField(max_length=10, default="auto")
    note = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"{self.block.farm.name} - {self.block.name} - {self.amount}m3"
    
class PumpControl(models.Model):
    block = models.OneToOneField(Block, on_delete=models.CASCADE, related_name="pump_control")
    status = models.BooleanField(default=False)
    mode = models.CharField(max_length=10, default="auto")
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.block.farm.name} - {self.block.name} Pump Control - {self.mode}"

#_______________________LOGGGGGG INNNNNNNNNNNNNN___________________________#

class FarmerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="farmer_profile")

    farmer_id = models.CharField(max_length=20, unique=True)
    full_name = models.CharField(max_length=150)
    contact_number = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)

    is_temporary_pin = models.BooleanField(default=True)
    failed_attempts = models.IntegerField(default=0)
    is_locked = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.full_name} - {self.farmer_id}"
    
class LGUProfile(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="lgu_profile")

    office_name = models.CharField(max_length=150)
    municipality = models.CharField(max_length=100)
    contact_number = models.CharField(max_length=20, blank=True, null=True)
    full_name = models.CharField(max_length=150)
    role = models.CharField(max_length=100)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    def __str__(self):
        return f"{self.office_name} - {self.status}"