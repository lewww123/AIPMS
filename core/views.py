import json
from datetime import timedelta, datetime
from django.utils.timezone import now
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from core.decorators import lgu_required, farmer_required
from django.db.models import Avg, Q, Count, Sum
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import User, Group
from .models import SensorData, PumpControl, WaterLog, Farm, Block, FarmerProfile, LGUProfile, MicrocontrollerDevice
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from functools import wraps
from core.utils import redirect_by_role
from django.utils import timezone
import random
from django.db.models.functions import TruncDate, TruncMonth, TruncYear
import re

# --- Constants & Config ---
# Flow rate: 600L/hr = 0.1666 L/sec
FLOW_RATE_L_PER_SEC = 600 / 3600
FULL_VOLUME_LITERS = 1.5
REDUCED_VOLUME_LITERS = 0.5  # Top-up amount during rain

#notification
def send_alert(message, alert_style):
    print("SEND ALERT CALLED:", message, alert_style)

    channel_layer = get_channel_layer()

    if channel_layer is None:
        print(f"Alert skipped: {message}")
        return

    async_to_sync(channel_layer.group_send)(
        "farm_updates",
        {
            "type": "send_notification",
            "message": message,
            "notification_type": alert_style
        }
    )

def farmer_entry(request):
    if request.user.is_authenticated:
        if request.user.groups.filter(name="Farmers").exists():
            return redirect("farmer_dashboard")
        else:
            return redirect("farmer_login")

    return redirect("farmer_login")


def lgu_entry(request):
    if request.user.is_authenticated:
        if request.user.groups.filter(name="LGU").exists():
            return redirect("lgu_dashboard")
        else:
            return redirect("lgu_login")

    return redirect("lgu_login")

def lgu_logout(request):
    logout(request)
    return redirect("lgu_login")

############LGU SING UP_
def lgu_signup(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")

        # Check match
        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, "lgu_signup.html")

        # Minimum length
        if len(password) < 8:
            messages.error(request, "Password must be at least 8 characters.")
            return render(request, "lgu_signup.html")

        # Must contain uppercase
        if not re.search(r'[A-Z]', password):
            messages.error(request, "Password must include at least one uppercase letter.")
            return render(request, "lgu_signup.html")

        # Must contain lowercase
        if not re.search(r'[a-z]', password):
            messages.error(request, "Password must include at least one lowercase letter.")
            return render(request, "lgu_signup.html")

        # Must contain number
        if not re.search(r'[0-9]', password):
            messages.error(request, "Password must include at least one number.")
            return render(request, "lgu_signup.html")
        
        office_name = request.POST.get("office_name")
        municipality = request.POST.get("municipality")
        contact_number = request.POST.get("contact_number")

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
            return render(request, "lgu_signup.html")

        user = User.objects.create_user(
            username=username,
            password=password
        )

        lgu_group, _ = Group.objects.get_or_create(name="LGU")
        user.groups.add(lgu_group)

        LGUProfile.objects.create(
            user=user,
            office_name=office_name,
            municipality=municipality,
            contact_number=contact_number,
            full_name = request.POST.get("full_name"),
            role = request.POST.get("role"),
            status="pending"
        )

        messages.success(request, "LGU account submitted. Please wait for admin approval.")
        return redirect("lgu_login")

    return render(request, "lgu_signup.html")


######################
def check_lgu_status(request):
    username = request.GET.get("username")

    try:
        user = User.objects.get(username=username)

        if hasattr(user, "lgu_profile"):
            status = user.lgu_profile.status
        else:
            status = "Not an LGU account"

        return JsonResponse({"status": status})

    except User.DoesNotExist:
        return JsonResponse({"status": "User not found"})
#____________________LGU GAWA ACCOUNT_______________#
def generate_farmer_id():
    number = 1001

    while True:
        farmer_id = f"F{number}"

        if (
            not FarmerProfile.objects.filter(farmer_id=farmer_id).exists()
            and not User.objects.filter(username=farmer_id).exists()
        ):
            return farmer_id

        number += 1

def generate_pin():
    return str(random.randint(1000, 9999))


@lgu_required
def lgu_create_farmer(request):
    farms = Farm.objects.all()

    if request.method == "POST":
        full_name = request.POST.get("full_name", "").strip()
        contact_number = request.POST.get("contact_number", "").strip()
        address = request.POST.get("address", "").strip()
        selected_farm_ids = request.POST.getlist("farms")

        existing_farmer = FarmerProfile.objects.filter(
            full_name__iexact=full_name,
            contact_number=contact_number
        ).first()

        if existing_farmer:
            selected_farms = Farm.objects.filter(id__in=selected_farm_ids)

            for farm in selected_farms:
                if not farm.farmer.filter(id=existing_farmer.user.id).exists():
                    farm.farmer.add(existing_farmer.user)

            messages.success(
                request,
                f"{existing_farmer.full_name} already has Farmer ID {existing_farmer.farmer_id}. Selected farms were assigned to the existing account."
            )

            return redirect("lgu_farmer_detail", farmer_id=existing_farmer.id)

        farmer_id = generate_farmer_id()
        pin = generate_pin()

        user = User.objects.create_user(
            username=farmer_id,
            password=pin
        )

        user.first_name = full_name
        user.save()

        farmer_group, _ = Group.objects.get_or_create(name="Farmers")
        user.groups.add(farmer_group)

        FarmerProfile.objects.create(
            user=user,
            farmer_id=farmer_id,
            full_name=full_name,
            contact_number=contact_number,
            address=address
        )

        selected_farms = Farm.objects.filter(id__in=selected_farm_ids)

        for farm in selected_farms:
            if not farm.farmer.filter(id=user.id).exists():
                farm.farmer.add(user)

        return render(request, "lgu_farmer_created.html", {
            "farmer_id": farmer_id,
            "pin": pin,
            "full_name": full_name
        })

    return render(request, "lgu_create_farmer.html", {
        "farms": farms
    })
#________________________FARMER_LOG INN________________#

def farmer_login(request):
    if request.method == "POST":
        farmer_id = request.POST.get("farmer_id")
        pin = request.POST.get("pin")

        user = authenticate(request, username=farmer_id, password=pin)

        if user is not None:
            profile = user.farmer_profile 

            login(request, user)

            # 🔐 Check if temporary PIN
            if profile.is_temporary_pin:
                return redirect("change_pin")

            return redirect("farmer_dashboard")

        else:
            messages.error(request, "Invalid Farmer ID or PIN")

    return render(request, "farmer_login.html")

def farmer_logout(request):
    logout(request)
    return redirect("farmer_login")

#_________lgu login_________
def lgu_login(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user and user.groups.filter(name="LGU").exists():
            if not hasattr(user, "lgu_profile") or user.lgu_profile.status != "approved":
                messages.error(request, "Your LGU account is still pending admin approval.")
                return render(request, "lgu_login.html")

            login(request, user)
            return redirect("lgu_dashboard")

        messages.error(request, "Invalid LGU account.")

    return render(request, "lgu_login.html")

#__________________________change pin_______________________#

@farmer_required
def change_pin(request):
    if request.method == "POST":
        new_pin = request.POST.get("new_pin")

        user = request.user
        user.set_password(new_pin)
        user.save()

        profile = user.farmer_profile
        profile.is_temporary_pin = False
        profile.save()

        login(request, user)  # re-login after password change

        return redirect("farmer_dashboard")

    return render(request, "change_pin.html")

# ================= AUTO CONTROL ENGINE =================
def auto_control_logic(block):
    current_time = now().time()

    control, _ = PumpControl.objects.get_or_create(block=block)
    latest_sensor = block.sensor_readings.first()

    if control.mode != "auto" or not latest_sensor:
        return

    # Watering schedule
    morning_start = datetime.strptime("06:00", "%H:%M").time()
    morning_end = datetime.strptime("07:00", "%H:%M").time()

    afternoon_start = datetime.strptime("10:40", "%H:%M").time()
    afternoon_end = datetime.strptime("11:00", "%H:%M").time()

    is_morning = morning_start <= current_time <= morning_end
    is_afternoon = afternoon_start <= current_time <= afternoon_end

    # Outside schedule: keep pump off in auto mode, but still keep storing sensor data
    if not is_morning and not is_afternoon:
        if control.status:
            control.status = False
            control.save()

            block.pump_status = False
            block.save()

            send_alert(
                f"Pump Stopped: {block.farm.name} - {block.name} stopped because it is outside the watering schedule.",
                "blue"
            )

        return

    soil = latest_sensor.soil_moisture
    raining = latest_sensor.is_raining
    tank_level = latest_sensor.water_tank_level
    
    critical_threshold = block.critical_threshold
    dry_threshold = block.dry_threshold
    wet_threshold = block.wet_threshold

    hour_check = 6 if is_morning else 16

    already_done = WaterLog.objects.filter(
        block=block,
        timestamp__date=now().date(),
        timestamp__hour=hour_check,
        amount__gt=0
    ).exists()

    already_logged_skip = WaterLog.objects.filter(
        block=block,
        timestamp__date=now().date(),
        timestamp__hour=hour_check,
        amount=0,
        note__icontains="Skipped"
    ).exists()

    # Tank safety
    if tank_level <= 20:
        if control.status:
            control.status = False
            control.save()

            block.pump_status = False
            block.save()

        if not already_logged_skip and not already_done:
            WaterLog.objects.create(
                block=block,
                amount=0,
                moisture_at_time=soil,
                mode="auto",
                note=f"Skipped: Low water tank level ({tank_level:.0f}%)"
            )

            send_alert(
                f"Low Water Tank Level: {block.farm.name} - {block.name} tank is at {tank_level:.0f}%. Irrigation skipped.",
                "red"
            )

        return

    # Decide watering amount
    target_volume = 0
    status_note = ""

    if raining:
        if soil > wet_threshold:
            target_volume = 0
            status_note = "Skipped: Rain detected and soil moisture is sufficient"

        elif soil < critical_threshold:
            target_volume = REDUCED_VOLUME_LITERS
            status_note = "Reduced irrigation: Rain detected but soil is still critically dry"

        else:
            target_volume = REDUCED_VOLUME_LITERS
            status_note = "Reduced irrigation: Light rain detected but soil still needs water"

    else:
        if soil < dry_threshold:
            target_volume = FULL_VOLUME_LITERS
            status_note = "Normal scheduled irrigation"
        else:
            target_volume = 0
            status_note = "Skipped: Soil moisture is sufficient"

    # If no watering is needed, log once
    if target_volume <= 0:
        if not already_logged_skip and not already_done:
            WaterLog.objects.create(
                block=block,
                amount=0,
                moisture_at_time=soil,
                mode="auto",
                note=status_note
            )

            send_alert(
                f"Auto Irrigation: {block.farm.name} - {block.name}: {status_note}.",
                "blue"
            )

        if control.status:
            control.status = False
            control.save()

            block.pump_status = False
            block.save()

        return

    # If watering was already completed for this schedule, keep pump off
    if already_done:
        if control.status:
            control.status = False
            control.save()

            block.pump_status = False
            block.save()

        return

    # Start pump
    if not control.status:
        control.status = True
        control.save()

        block.pump_status = True
        block.save()

        WaterLog.objects.create(
            block=block,
            amount=0,
            moisture_at_time=soil,
            mode="auto",
            note="Started: " + status_note
        )

        if raining:
            send_alert(
                f"Pump Started: {block.farm.name} - {block.name} started reduced irrigation because rain was detected but soil is still dry.",
                "green"
            )
        else:
            send_alert(
                f"Pump Started: {block.farm.name} - {block.name} started normal scheduled irrigation.",
                "green"
            )

        return

    # Stop pump after required duration
    if control.status:
        current_log = WaterLog.objects.filter(
            block=block,
            amount=0,
            note__startswith="Started"
        ).order_by("-timestamp").first()

        if not current_log:
            return

        elapsed = (now() - current_log.timestamp).total_seconds()
        required_duration = target_volume / FLOW_RATE_L_PER_SEC

        if elapsed >= required_duration:
            control.status = False
            control.save()

            block.pump_status = False
            block.save()

            current_log.amount = target_volume / 1000
            current_log.moisture_at_time = soil
            current_log.note = f"Completed: {status_note}"
            current_log.save()

            send_alert(
                f"Pump Stopped: {block.farm.name} - {block.name} irrigation completed. Applied {target_volume}L.",
                "green"
            )

# ================= ARDUINO / HARDWARE API =================

@csrf_exempt
def receive_data(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)

            hardware_id = data.get("hardware_id")

            if not hardware_id:
                return JsonResponse({"error": "Missing hardware_id"}, status=400)

            device = MicrocontrollerDevice.objects.select_related("block").get(
                hardware_id=hardware_id,
                is_active=True
            )

            block = device.block
            device.save()

            def to_bool(value):
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    return value.lower() in ["true", "1", "yes", "on"]
                return bool(value)

            soil = int(data.get("soil", 0))
            ph = float(data.get("ph", 7.0))
            temp = float(data.get("temp", 0.0))
            rain = to_bool(data.get("rain", False))
            pump = to_bool(data.get("pump", False))
            tank_level = float(data.get("tank_level", 0.0))

            control, _ = PumpControl.objects.get_or_create(block=block)
            mode = control.mode

            # Get previous rain status BEFORE saving new sensor data
            previous_sensor = block.sensor_readings.first()
            previous_rain = previous_sensor.is_raining if previous_sensor else False

            SensorData.objects.create(
                block=block,
                soil_moisture=soil,
                ph_level=ph,
                temperature=temp,
                is_raining=rain,
                water_tank_level=tank_level,
                pump_status=control.status,
                mode=mode
            )

            block.current_moisture = soil
            block.current_ph = ph
            block.current_temp = temp
            block.is_raining = rain
            block.water_tank_level = tank_level
            block.mode = control.mode
            block.pump_status = control.status
            block.save()

            # Rain detected notification
            if rain and not previous_rain:
                WaterLog.objects.create(
                    block=block,
                    amount=0,
                    moisture_at_time=soil,
                    mode=control.mode,
                    note="Rain detected alert"
                )

                send_alert(
                    f"Rain Detected: {block.farm.name} - {block.name}. Irrigation may be paused or reduced.",
                    "blue"
                )

            # Clear skies notification
            if not rain and previous_rain:
                WaterLog.objects.create(
                    block=block,
                    amount=0,
                    moisture_at_time=soil,
                    mode=control.mode,
                    note="Clear skies alert"
                )

                send_alert(
                    f"Clear Skies: {block.farm.name} - {block.name}. Rain is no longer detected.",
                    "green"
                )

            # Low water tank notification, once every 5 minutes
            recent_low_tank_alert = WaterLog.objects.filter(
                block=block,
                note__icontains="Low water tank alert",
                timestamp__gte=now() - timedelta(seconds=30)
            ).exists()

            if tank_level <= 20 and not recent_low_tank_alert:
                WaterLog.objects.create(
                    block=block,
                    amount=0,
                    moisture_at_time=soil,
                    mode=control.mode,
                    note=f"Low water tank alert: Tank level is {tank_level:.0f}%"
                )

                send_alert(
                    f"Low Water Tank Level: {block.farm.name} - {block.name} tank is at {tank_level:.0f}%. Please refill the water tank.",
                    "red"
                )

            auto_control_logic(block)

            control.refresh_from_db()
            block.refresh_from_db()

            return JsonResponse({
                "status": control.status,
                "mode": control.mode
            })

        except MicrocontrollerDevice.DoesNotExist:
            return JsonResponse({"error": "Device not registered"}, status=400)

        except Exception as e:
            print(f"SERVER ERROR: {e}")
            return JsonResponse({"error": str(e)}, status=400)

    return JsonResponse({"error": "POST only"}, status=405)
# ================= DASHBOARD ROUTING =================
@farmer_required
def dashboard_router(request):
    if request.user.groups.filter(name='LGU').exists():
        return render(request, 'lgu_dashboard.html')
    elif request.user.groups.filter(name='Farmers').exists():
        try:
            farm = Farm.objects.get(farmer=request.user)
            return render(request, 'core/farmer_dashboard.html', {'farm': farm})
        except Farm.DoesNotExist:
            return render(request, 'error.html', {'message': 'No farm assigned.'})
    return render(request, 'error.html', {'message': 'Unassigned Role'})


# ================= FARMER UI API ENDPOINTS =================
@farmer_required
def get_live_data(request):
    try:
        block_id = request.GET.get("block")

        if not block_id:
            return JsonResponse({"error": "Missing block ID"}, status=400)

        block = Block.objects.select_related("farm").filter(
            id=block_id,
            farm__farmer=request.user
        ).first()

        if not block:
            return JsonResponse({"error": "Block not found or not assigned to this farmer"}, status=403)

        latest = block.sensor_readings.first()

        if latest:
            soil = latest.soil_moisture
            ph = latest.ph_level
            temp = latest.temperature
            rain = latest.is_raining
            tank_level = latest.water_tank_level
        else:
            soil = block.current_moisture
            ph = block.current_ph
            temp = block.current_temp
            rain = block.is_raining
            tank_level = block.water_tank_level

        return JsonResponse({
            "soil": soil,
            "ph": ph,
            "temp": temp,
            "rain": rain,
            "tank_level": tank_level,
            "pump": block.pump_status,
            "mode": block.mode
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@csrf_exempt
@farmer_required
def control_pump(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)

            action = data.get("action")
            block_id = data.get("block_id")

            if not block_id:
                return JsonResponse({
                    "status": "error",
                    "message": "Missing block ID"
                }, status=400)

            block = Block.objects.select_related("farm").filter(
                id=block_id,
                farm__farmer=request.user
            ).first()

            if not block:
                return JsonResponse({
                    "status": "error",
                    "message": "Block not found or not assigned to this farmer"
                }, status=403)

            control, _ = PumpControl.objects.get_or_create(block=block)

            if action == "toggle_mode":
                new_mode = "manual" if control.mode == "auto" else "auto"

                control.mode = new_mode
                block.mode = new_mode

                if new_mode == "auto":
                    control.status = False
                    block.pump_status = False

                control.save()
                block.save()

            elif action == "toggle_pump":
                if control.mode == "manual":
                    control.status = not control.status
                    block.pump_status = control.status

                    control.save()
                    block.save()

                    if control.status:
                        WaterLog.objects.create(
                            block=block,
                            amount=0,
                            moisture_at_time=block.current_moisture,
                            mode="manual",
                            note="Manual Start"
                        )

                        send_alert(
                            f"Water Pump Started: {block.farm.name} - {block.name} pump was turned ON manually.",
                            "green"
                        )

                    else:
                        WaterLog.objects.create(
                            block=block,
                            amount=0,
                            moisture_at_time=block.current_moisture,
                            mode="manual",
                            note="Manual Stop"
                        )

                        send_alert(
                            f"Water Pump Stopped: {block.farm.name} - {block.name} pump was turned OFF manually.",
                            "blue"
                        )

                else:
                    return JsonResponse({
                        "status": "error",
                        "message": "Pump can only be controlled in manual mode",
                        "mode": control.mode,
                        "pump": control.status
                    }, status=400)

            else:
                return JsonResponse({
                    "status": "error",
                    "message": "Invalid action"
                }, status=400)

            return JsonResponse({
                "status": "success",
                "mode": control.mode,
                "pump": control.status
            })

        except Exception as e:
            return JsonResponse({
                "status": "error",
                "message": str(e)
            }, status=500)

    return JsonResponse({
        "status": "error",
        "message": "Invalid method"
    }, status=400)
    
# ================= LGU ANALYTICS & LOGS =================
def last_watered(request):
    last = WaterLog.objects.filter(amount__gt=0).last()
    if not last:
        return JsonResponse({"last_watered_time": "No data", "amount_m3": 0})
    return JsonResponse({
        "last_watered_time": last.timestamp.strftime("%b %d, %I:%M %p"),
        "amount_m3": last.amount,
        "display_text": f"{last.amount * 1000} Liters" # Convert back to Liters for UI
    })

# ================= LGU ANALYTICS & LOGS =================
def last_watered(request):
    last = WaterLog.objects.filter(amount__gt=0).last()
    if not last:
        return JsonResponse({"last_watered_time": "No data", "amount_m3": 0})
    return JsonResponse({
        "last_watered_time": last.timestamp.strftime("%b %d, %I:%M %p"),
        "amount_m3": last.amount,
        "display_text": f"{last.amount * 1000} Liters"
    })


def list_farms(request):
    farms = Farm.objects.all().values("id", "name", "location")
    return JsonResponse(list(farms), safe=False)

@farmer_required
def water_logs(request):
    block_id = request.GET.get("block_id")

    logs = WaterLog.objects.select_related(
        "block",
        "block__farm"
    ).order_by("-timestamp")

    if request.user.groups.filter(name="Farmers").exists():
        logs = logs.filter(block__farm__farmer=request.user)

    if block_id:
        logs = logs.filter(block_id=block_id)

    logs = logs[:50]

    log_data = []

    for log in logs:
        if log.amount and log.amount > 0:
            volume_display = f"{log.amount * 1000:.1f} L estimated"
        else:
            volume_display = "-"

        log_data.append({
            "time": timezone.localtime(log.timestamp).strftime("%b %d, %I:%M %p"),
            "farm": log.block.farm.name if log.block and log.block.farm else "Unknown Farm",
            "block": log.block.name if log.block else "Unknown Block",
            "moisture": log.moisture_at_time if log.moisture_at_time is not None else "-",
            "mode": log.mode or "-",
            "note": log.note or "Regular Cycle",
            "amount": volume_display
        })

    return JsonResponse({"logs": log_data})
def daily_water_count(request):
    farm_id = request.GET.get('farm_id', 1)
    today = now().date()
    count = WaterLog.objects.filter(farm_id=farm_id, timestamp__date=today, amount__gt=0).count()
    avg_soil = SensorData.objects.filter(farm_id=farm_id, timestamp__date=today).aggregate(Avg('soil_moisture'))['soil_moisture__avg']
    return JsonResponse({
        "count": count,
        "avg_soil": round(avg_soil, 1) if avg_soil else 0
    })

def analytics(request):
    today = now()
    week = today - timedelta(days=7)
    return JsonResponse({
        "weekly": WaterLog.objects.filter(timestamp__gte=week, amount__gt=0).count(),
        "avg_ph": SensorData.objects.filter(timestamp__gte=week).aggregate(Avg('ph_level'))['ph_level__avg']
    })

def soil_history(request):
    farm_id = request.GET.get('farm_id', 1)
    data = SensorData.objects.filter(farm_id=farm_id).order_by('-timestamp')[:20]
    data = list(reversed(data))
    return JsonResponse({
        "labels": [d.timestamp.strftime("%H:%M") for d in data],
        "values": [d.soil_moisture for d in data],
        "temp_values": [d.temperature for d in data],
        "ph_values": [d.ph_level for d in data]
    })

@farmer_required
def farmer_dashboard(request):
    user_obj = request.user

    farms = user_obj.farms.prefetch_related("blocks").distinct()

    block_id = request.GET.get("block")

    selected_block = None

    if block_id:
        for farm in farms:
            selected_block = farm.blocks.filter(id=block_id).first()
            if selected_block:
                break

    if not selected_block:
        for farm in farms:
            selected_block = farm.blocks.first()
            if selected_block:
                break

    last_log = WaterLog.objects.filter(
        block__farm__farmer=user_obj,
        amount__gt=0
    ).order_by("-timestamp").first()
    
    last_watered_time = (
        timezone.localtime(last_log.timestamp).strftime("%b %d, %I:%M %p")
        if last_log else "No data yet"
    )

    return render(request, 'farmer_dashboard.html', {
        'user_obj': user_obj,
        'farms': farms,
        'selected_block': selected_block,
        'last_watered': last_watered_time
    })


@farmer_required
def update_thresholds(request):
    if request.method == "POST":
        block_id = request.POST.get("block_id")

        block = Block.objects.select_related("farm").filter(
            id=block_id,
            farm__farmer=request.user
        ).first()

        if not block:
            messages.error(request, "You are not allowed to edit this block.")
            return redirect("farmer_dashboard")

        try:
            critical_threshold = int(request.POST.get("critical_threshold"))
            dry_threshold = int(request.POST.get("dry_threshold"))
            wet_threshold = int(request.POST.get("wet_threshold"))

            if critical_threshold < 0 or dry_threshold < 0 or wet_threshold < 0:
                messages.error(request, "Threshold values cannot be negative.")
                return redirect(f"/farmer-dashboard/?block={block.id}")

            if wet_threshold > 100 or dry_threshold > 100 or critical_threshold > 100:
                messages.error(request, "Threshold values cannot exceed 100%.")
                return redirect(f"/farmer-dashboard/?block={block.id}")

            if not critical_threshold < dry_threshold < wet_threshold:
                messages.error(request, "Threshold must follow: Critical < Dry < Wet.")
                return redirect(f"/farmer-dashboard/?block={block.id}")

            block.critical_threshold = critical_threshold
            block.dry_threshold = dry_threshold
            block.wet_threshold = wet_threshold
            block.save()

            messages.success(request, "Threshold settings updated successfully.")
            return redirect(f"/farmer-dashboard/?block={block.id}")

        except ValueError:
            messages.error(request, "Please enter valid numbers.")
            return redirect(f"/farmer-dashboard/?block={block.id}")

    return redirect("farmer_dashboard")

#_______________LGU DASHBOARDDDDD________________________#

@lgu_required
def lgu_dashboard(request):
    farmers = FarmerProfile.objects.select_related("user").all()
    farms = Farm.objects.prefetch_related("farmer", "blocks__sensor_readings").all()

    farm_overview = []
    priority_alerts = []

    def add_alert(alert_type, message, timestamp=None):
        priority_map = {
            "danger": 1,
            "warning": 2,
            "info": 3,
        }

        priority_alerts.append({
            "type": alert_type,
            "message": message,
            "timestamp": timestamp or timezone.now(),
            "priority": priority_map.get(alert_type, 4),
        })

    for farm in farms:
        blocks = farm.blocks.all()

        moisture_list = []
        ph_list = []
        temp_list = []

        for block in blocks:
            latest = block.sensor_readings.first()

            moisture = latest.soil_moisture if latest else block.current_moisture
            ph = latest.ph_level if latest else block.current_ph
            temp = latest.temperature if latest else block.current_temp
            rain = latest.is_raining if latest else block.is_raining

            timestamp = latest.timestamp if latest else timezone.now()

            moisture_list.append(moisture)
            ph_list.append(ph)
            temp_list.append(temp)

            if moisture < 35:
                add_alert(
                    "danger",
                    f"{farm.name} - {block.name}: Low moisture ({moisture}%). Immediate irrigation required.",
                    timestamp
                )

            elif moisture > 70:
                add_alert(
                    "warning",
                    f"{farm.name} - {block.name}: Too wet ({moisture}%). Irrigation should be paused.",
                    timestamp
                )

            if rain:
                add_alert(
                    "info",
                    f"{farm.name} - {block.name}: Rain detected. Irrigation skipped.",
                    timestamp
                )

            if ph < 6:
                add_alert(
                    "warning",
                    f"{farm.name} - {block.name}: Acidic soil (pH {ph}).",
                    timestamp
                )

            elif ph > 7.5:
                add_alert(
                    "warning",
                    f"{farm.name} - {block.name}: Alkaline soil (pH {ph}).",
                    timestamp
                )

            if temp > 35:
                add_alert(
                    "warning",
                    f"{farm.name} - {block.name}: High temperature ({temp}°C).",
                    timestamp
                )

            if block.pump_status:
                add_alert(
                    "info",
                    f"{farm.name} - {block.name}: Pump is active.",
                    timestamp
                )

        count = len(moisture_list)

        avg_moisture = sum(moisture_list) / count if count else 0
        avg_ph = sum(ph_list) / count if count else 0
        avg_temp = sum(temp_list) / count if count else 0

        if avg_moisture < 35:
            status = "Needs Water"
        elif avg_moisture > 70:
            status = "Too Wet"
        else:
            status = "Healthy"

        farm_overview.append({
            "farm": farm,
            "farmer": farm.farmer.all(),
            "block_count": count,
            "avg_moisture": round(avg_moisture, 1),
            "avg_ph": round(avg_ph, 1),
            "avg_temp": round(avg_temp, 1),
            "status": status,
        })
    all_alerts = sorted(
        priority_alerts,
        key=lambda a: (a["priority"], -a["timestamp"].timestamp())
        )

    top_priority_alerts = all_alerts[:5]

    return render(request, "lgu_dashboard.html", {
        "farmers": farmers,
        "farm_overview": farm_overview,
        "priority_alerts": top_priority_alerts,
        "all_alerts": all_alerts,
    })
        
#-----sidebar_________________#
@lgu_required
def lgu_farmers(request):
    search = request.GET.get("search", "")
    status = request.GET.get("status", "")

    farmers = FarmerProfile.objects.select_related("user").all()

    if search:
        farmers = farmers.filter(
            full_name__icontains=search
        ) | farmers.filter(
            farmer_id__icontains=search
        ) | farmers.filter(
            contact_number__icontains=search
        )

    if status == "active":
        farmers = farmers.filter(is_locked=False)

    elif status == "locked":
        farmers = farmers.filter(is_locked=True)

    elif status == "temporary":
        farmers = farmers.filter(is_temporary_pin=True)

    return render(request, "lgu_farmers.html", {
        "farmers": farmers,
        "search": search,
        "status": status,
    })

#----

@lgu_required
def lgu_farms(request):
    search = request.GET.get("search", "").strip()
    filter_by = request.GET.get("filter_by", "all")
    location = request.GET.get("location", "").strip()

    farms = Farm.objects.prefetch_related("farmer", "blocks").all()

    if search:
        if filter_by == "name":
            farms = farms.filter(name__icontains=search)

        elif filter_by == "location":
            farms = farms.filter(location__icontains=search)

        elif filter_by == "farmer":
            farms = farms.filter(farmer__farmer_profile__full_name__icontains=search)

        elif filter_by == "block":
            farms = farms.filter(blocks__name__icontains=search)

        else:
            farms = farms.filter(
                Q(name__icontains=search) |
                Q(location__icontains=search) |
                Q(farmer__farmer_profile__full_name__icontains=search) |
                Q(blocks__name__icontains=search)
            )

    if location:
        farms = farms.filter(location__iexact=location)

    farms = farms.distinct()

    locations = Farm.objects.values_list("location", flat=True).distinct()

    return render(request, "lgu_farms.html", {
        "farms": farms,
        "search": search,
        "filter_by": filter_by,
        "location": location,
        "locations": locations,
    })
    
@lgu_required
def lgu_analytics(request):
    farms = Farm.objects.prefetch_related("farmer", "blocks").all()

    total_farms = farms.count()
    total_blocks = 0
    active_pumps = 0

    all_moisture = []
    all_ph = []
    all_temp = []

    for farm in farms:
        for block in farm.blocks.all():
            total_blocks += 1

            all_moisture.append(block.current_moisture)
            all_ph.append(block.current_ph)
            all_temp.append(block.current_temp)

            if block.pump_status:
                active_pumps += 1

    avg_moisture = round(sum(all_moisture) / len(all_moisture), 1) if all_moisture else 0
    avg_ph = round(sum(all_ph) / len(all_ph), 1) if all_ph else 0
    avg_temp = round(sum(all_temp) / len(all_temp), 1) if all_temp else 0

    return render(request, "lgu_analytics.html", {
        "total_farms": total_farms,
        "total_blocks": total_blocks,
        "active_pumps": active_pumps,
        "avg_moisture": avg_moisture,
        "avg_ph": avg_ph,
        "avg_temp": avg_temp,
    })
    
@lgu_required
def lgu_logs(request):
    logs = WaterLog.objects.select_related(
        "block",
        "block__farm"
    ).prefetch_related(
        "block__farm__farmer"
    ).order_by("-timestamp")[:100]

    return render(request, "lgu_logs.html", {
        "logs": logs
    })


    #____CRUD LGU_FARMERS____#
@lgu_required
def lgu_farm_detail(request, farm_id):
    farm = Farm.objects.prefetch_related(
        "farmer",
        "blocks",
        "blocks__sensor_readings"
    ).get(id=farm_id)

    blocks = farm.blocks.all()
    assigned_farmers = farm.farmer.all()

    block_count = blocks.count()

    if block_count > 0:
        avg_moisture = sum(block.current_moisture for block in blocks) / block_count
        avg_ph = sum(block.current_ph for block in blocks) / block_count
        avg_temp = sum(block.current_temp for block in blocks) / block_count
        active_pumps = blocks.filter(pump_status=True).count()
    else:
        avg_moisture = 0
        avg_ph = 0
        avg_temp = 0
        active_pumps = 0

    return render(request, "lgu_farm_detail.html", {
        "farm": farm,
        "blocks": blocks,
        "assigned_farmers": assigned_farmers,
        "avg_moisture": round(avg_moisture, 1),
        "avg_ph": round(avg_ph, 1),
        "avg_temp": round(avg_temp, 1),
        "active_pumps": active_pumps,
        "block_count": block_count,
    })
    

@lgu_required
def lgu_farmer_edit(request, farmer_id):
    farmer = FarmerProfile.objects.select_related("user").get(id=farmer_id)
    farms = Farm.objects.all()

    if request.method == "POST":
        farmer.full_name = request.POST.get("full_name")
        farmer.contact_number = request.POST.get("contact_number")
        farmer.address = request.POST.get("address")
        farmer.save()

        selected_farm_ids = request.POST.getlist("farms")

        # Clear old farm assignments
        for farm in Farm.objects.filter(farmer=farmer.user):
            farm.farmer.remove(farmer.user)

        # Add new farm assignments
        selected_farms = Farm.objects.filter(id__in=selected_farm_ids)

        for farm in selected_farms:
            farm.farmer.add(farmer.user)

        return redirect("lgu_farmers")

    assigned_farm_ids = list(
        Farm.objects.filter(farmer=farmer.user).values_list("id", flat=True)
    )

    return render(request, "lgu_farmer_edit.html", {
        "farmer": farmer,
        "farms": farms,
        "assigned_farm_ids": assigned_farm_ids
    })

@lgu_required
def lgu_farmer_delete(request, farmer_id):
    farmer = FarmerProfile.objects.get(id=farmer_id)

    if request.method == "POST":
        farmer.user.delete()
        return redirect("lgu_farmers")

    return render(request, "lgu_farmer_delete.html", {
        "farmer": farmer
    })


@lgu_required
def lgu_farmer_detail(request, farmer_id):
    farmer = FarmerProfile.objects.select_related("user").get(id=farmer_id)

    farms = Farm.objects.filter(farmer=farmer.user).prefetch_related("blocks")

    return render(request, "lgu_farmer_detail.html", {
        "farmer": farmer,
        "farms": farms,
    })
    
@lgu_required
def lgu_reset_pin(request, farmer_id):
    import random

    farmer = FarmerProfile.objects.get(id=farmer_id)
    new_pin = str(random.randint(1000, 9999))

    farmer.user.set_password(new_pin)
    farmer.user.save()

    farmer.is_temporary_pin = True
    farmer.failed_attempts = 0
    farmer.is_locked = False
    farmer.save()

    return render(request, "lgu_reset_pin.html", {
        "farmer": farmer,
        "new_pin": new_pin
    })

@lgu_required
def lgu_unlock_farmer(request, farmer_id):
    farmer = FarmerProfile.objects.get(id=farmer_id)

    farmer.is_locked = False
    farmer.failed_attempts = 0
    farmer.save()

    return redirect("lgu_farmers")

@lgu_required
def lgu_block_detail(request, block_id):
    block = Block.objects.select_related("farm").get(id=block_id)

    # Current status
    if block.current_moisture < block.dry_threshold:
        moisture_status = "Needs Water"
    elif block.current_moisture > block.wet_threshold:
        moisture_status = "Too Wet"
    else:
        moisture_status = "Healthy"

    if block.current_ph < 6:
        ph_status = "Acidic"
    elif block.current_ph > 7.5:
        ph_status = "Alkaline"
    else:
        ph_status = "Neutral"

    if block.current_temp < 20:
        temp_status = "Cool"
    elif block.current_temp > 35:
        temp_status = "Hot"
    else:
        temp_status = "Normal"

    # History logs for this specific block
    sensor_history = SensorData.objects.filter(
        block=block
    ).order_by("-timestamp")[:100]
    
    dry_peak = SensorData.objects.filter(
    block=block,
    soil_moisture__lte=block.dry_threshold
    ).order_by("soil_moisture", "timestamp").first()

    water_logs = WaterLog.objects.filter(
        block=block
    ).order_by("-timestamp")[:100]

    # Daily analytics
    daily_analytics = SensorData.objects.filter(block=block).annotate(
        period=TruncDate("timestamp")
    ).values("period").annotate(
        avg_moisture=Avg("soil_moisture"),
        avg_ph=Avg("ph_level"),
        avg_temp=Avg("temperature"),
        avg_tank=Avg("water_tank_level"),
        rain_count=Count("id", filter=Q(is_raining=True)),
        pump_count=Count("id", filter=Q(pump_status=True)),
    ).order_by("-period")[:30]

    # Monthly analytics
    monthly_analytics = SensorData.objects.filter(block=block).annotate(
        period=TruncMonth("timestamp")
    ).values("period").annotate(
        avg_moisture=Avg("soil_moisture"),
        avg_ph=Avg("ph_level"),
        avg_temp=Avg("temperature"),
        avg_tank=Avg("water_tank_level"),
        rain_count=Count("id", filter=Q(is_raining=True)),
        pump_count=Count("id", filter=Q(pump_status=True)),
    ).order_by("-period")[:12]

    # Yearly analytics
    yearly_analytics = SensorData.objects.filter(block=block).annotate(
        period=TruncYear("timestamp")
    ).values("period").annotate(
        avg_moisture=Avg("soil_moisture"),
        avg_ph=Avg("ph_level"),
        avg_temp=Avg("temperature"),
        avg_tank=Avg("water_tank_level"),
        rain_count=Count("id", filter=Q(is_raining=True)),
        pump_count=Count("id", filter=Q(pump_status=True)),
    ).order_by("-period")

    # Water usage analytics
    daily_water = WaterLog.objects.filter(block=block).annotate(
        period=TruncDate("timestamp")
    ).values("period").annotate(
        total_water=Sum("amount"),
        irrigation_count=Count("id")
    ).order_by("-period")[:30]

    monthly_water = WaterLog.objects.filter(block=block).annotate(
        period=TruncMonth("timestamp")
    ).values("period").annotate(
        total_water=Sum("amount"),
        irrigation_count=Count("id")
    ).order_by("-period")[:12]

    yearly_water = WaterLog.objects.filter(block=block).annotate(
        period=TruncYear("timestamp")
    ).values("period").annotate(
        total_water=Sum("amount"),
        irrigation_count=Count("id")
    ).order_by("-period")

    return render(request, "lgu_block_detail.html", {
        "block": block,
        "moisture_status": moisture_status,
        "ph_status": ph_status,
        "temp_status": temp_status,
        "sensor_history": sensor_history,
        "water_logs": water_logs,
        "daily_analytics": daily_analytics,
        "monthly_analytics": monthly_analytics,
        "yearly_analytics": yearly_analytics,
        "daily_water": daily_water,
        "monthly_water": monthly_water,
        "yearly_water": yearly_water,
    })

@lgu_required
def lgu_add_farm(request):
    farmer = FarmerProfile.objects.select_related("user").all()

    if request.method == "POST":
        farm_name = request.POST.get("farm_name")
        farm_location = request.POST.get("farm_location")
        farmer_ids = request.POST.getlist("farmer")

        try:
            block_count = int(request.POST.get("block_count", 1))
        except ValueError:
            block_count = 1

        farm = Farm.objects.create(
            name=farm_name,
            location=farm_location
        )

        selected_farmers = FarmerProfile.objects.filter(id__in=farmer_ids)

        for profile in selected_farmers:
            farm.farmer.add(profile.user)

        for i in range(1, block_count + 1):
            Block.objects.create(
                farm=farm,
                name=f"Block {chr(64 + i)}"
            )

        return redirect("lgu_farms")

    return render(request, "lgu_add_farm.html", {
        "farmer": farmer
    })
    
@lgu_required
def lgu_farm_edit(request, farm_id):
    farm = Farm.objects.prefetch_related("farmer", "blocks").get(id=farm_id)
    farmer = FarmerProfile.objects.select_related("user").all()

    if request.method == "POST":
        farm.name = request.POST.get("farm_name")
        farm.location = request.POST.get("farm_location")
        farm.save()

        selected_farmer_ids = request.POST.getlist("farmer")

        farm.farmer.clear()

        selected_farmers = FarmerProfile.objects.filter(id__in=selected_farmer_ids)

        for profile in selected_farmers:
            farm.farmer.add(profile.user)

        try:
            new_block_count = int(request.POST.get("block_count", farm.blocks.count()))
        except ValueError:
            new_block_count = farm.blocks.count()

        if new_block_count < 1:
            new_block_count = 1

        current_blocks = list(farm.blocks.all().order_by("id"))
        current_block_count = len(current_blocks)

        if new_block_count > current_block_count:
            for i in range(current_block_count + 1, new_block_count + 1):
                Block.objects.create(
                    farm=farm,
                    name=f"Block {chr(64 + i)}"
                )

        elif new_block_count < current_block_count:
            blocks_to_delete = current_blocks[new_block_count:]
            for block in blocks_to_delete:
                block.delete()

        return redirect("lgu_farms")

    assigned_farmer_ids = list(
        FarmerProfile.objects.filter(user__in=farm.farmer.all()).values_list("id", flat=True)
    )

    block_count = farm.blocks.count()

    return render(request, "lgu_farm_edit.html", {
        "farm": farm,
        "farmer": farmer,
        "assigned_farmer_ids": assigned_farmer_ids,
        "block_count": block_count,
    })


@lgu_required
def lgu_farm_delete(request, farm_id):
    farm = Farm.objects.get(id=farm_id)

    if request.method == "POST":
        farm.delete()
        return redirect("lgu_farms")

    return render(request, "lgu_farm_delete.html", {
        "farm": farm
    })
