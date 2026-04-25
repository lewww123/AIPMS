import json
from datetime import timedelta, datetime
from django.utils.timezone import now
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from core.decorators import lgu_required, farmer_required
from django.db.models import Avg, Q
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
import re

# --- Constants & Config ---
# Flow rate: 600L/hr = 0.1666 L/sec
FLOW_RATE_L_PER_SEC = 600 / 3600
FULL_VOLUME_LITERS = 1.5
REDUCED_VOLUME_LITERS = 0.5  # Top-up amount during rain

# Thresholds
MOISTURE_CRITICAL = 25  # Below this, water even if raining
MOISTURE_OK = 50        # Above this, skip if raining

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
    count = FarmerProfile.objects.count() + 1
    return f"F{1000 + count}"


def generate_pin():
    return str(random.randint(1000, 9999))


def lgu_create_farmer(request):
    if request.method == "POST":
        full_name = request.POST.get("full_name")
        contact_number = request.POST.get("contact_number")
        address = request.POST.get("address")
        farm_name = request.POST.get("farm_name")
        farm_location = request.POST.get("farm_location")
        block_count = int(request.POST.get("block_count", 1))

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

        farm = Farm.objects.create(
            name=farm_name,
            location=farm_location,
            farmer=user
        )

        for i in range(1, block_count + 1):
            Block.objects.create(
                farm=farm,
                name=f"Block {chr(64 + i)}"
            )

        return render(request, "lgu_farmer_created.html", {
            "farmer_id": farmer_id,
            "pin": pin,
            "full_name": full_name
        })

    return render(request, "lgu_create_farmer.html")
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
def auto_control_logic():
    current_time = now().time()
    farm, _ = Farm.objects.get_or_create(id=1)
    control, _ = PumpControl.objects.get_or_create(id=1, defaults={'farm': farm})
    latest_sensor = SensorData.objects.filter(farm=farm).last()

    if control.mode != "auto" or not latest_sensor:
        return

    # Define Windows
    morning_start, morning_end = datetime.strptime("06:00", "%H:%M").time(), datetime.strptime("07:00", "%H:%M").time()
    afternoon_start, afternoon_end = datetime.strptime("16:00", "%H:%M").time(), datetime.strptime("17:00", "%H:%M").time()

    is_morning = morning_start <= current_time <= morning_end
    is_afternoon = afternoon_start <= current_time <= afternoon_end

    if is_morning or is_afternoon:
        soil = latest_sensor.soil_moisture
        raining = latest_sensor.is_raining
        
        # DECISION LOGIC
        status_note = ""
        target_volume = 0

        if raining:
            if soil > MOISTURE_OK:
                target_volume = 0
                status_note = "Skipped: Raining & Sufficient Moisture"
            elif soil < MOISTURE_CRITICAL:
                target_volume = REDUCED_VOLUME_LITERS
                status_note = "Rain Top-up: Critical Moisture Bypass"
            else:
                target_volume = 0
                status_note = "Skipped: Raining"
        else:
            target_volume = FULL_VOLUME_LITERS
            status_note = "Scheduled Cycle"

        # Check if we already finished today
        hour_check = 6 if is_morning else 16
        already_done = WaterLog.objects.filter(
            farm=farm, 
            timestamp__date=now().date(), 
            timestamp__hour=hour_check,
            amount__gt=0 
        ).exists()

        if target_volume <= 0 and not already_done:
            # Log the skip if it's the first time in the window
            if not WaterLog.objects.filter(farm=farm, timestamp__date=now().date(), timestamp__hour=hour_check).exists():
                WaterLog.objects.create(
                    farm=farm, 
                    amount=0, 
                    moisture_at_time=soil,
                    mode="auto",
                    note=status_note
                )
                send_alert(f"Auto-Logic: {status_note}", "blue")
            return

        if not already_done and not control.status:
            # START PUMPING
            control.status = True
            control.save()
            WaterLog.objects.create(
                farm=farm, 
                amount=0, 
                moisture_at_time=soil,
                mode="auto",
                note="Started: " + status_note
            )
            send_alert(f"Pump Started: {status_note} ({soil}% moisture)", "green")
            
        elif control.status:
            # Check for STOP
            current_log = WaterLog.objects.filter(farm=farm).last()
            elapsed = (now() - current_log.timestamp).total_seconds()
            required_duration = target_volume / FLOW_RATE_L_PER_SEC

            if elapsed >= required_duration:
                control.status = False
                control.save()
                current_log.amount = target_volume / 1000
                current_log.note = f"Completed: {status_note}"
                current_log.save()
                send_alert(f"Pump Stopped: Applied {target_volume}L", "green")

# ================= ARDUINO / HARDWARE API =================
@csrf_exempt
def receive_data(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)

            # 🔥 GET DEVICE
            hardware_id = data.get("hardware_id")

            if not hardware_id:
                return JsonResponse({"error": "Missing hardware_id"}, status=400)

            device = MicrocontrollerDevice.objects.select_related("block").get(
                hardware_id=hardware_id,
                is_active=True
            )

            block = device.block
            device.save()  # update last_seen if you want

            # 🔥 SAVE SENSOR DATA
            SensorData.objects.create(
                block=block,
                soil_moisture=int(data.get("soil", 0)),
                ph_level=float(data.get("ph", 7.0)),
                temperature=float(data.get("temp", 0.0)),
                is_raining=bool(data.get("rain", False)),
                pump_status=bool(data.get("pump", False)),
                mode=str(data.get("mode", "auto"))
            )

            # 🔥 RUN CONTROL LOGIC
            auto_control_logic()

            # 🔥 GET CONTROL FOR THIS BLOCK
            control, _ = PumpControl.objects.get_or_create(block=block)

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
def get_live_data(request):
    try:
        block_id = request.GET.get("block")

        block = Block.objects.get(id=block_id)

        latest = block.sensor_readings.first()

        if latest:
            soil = latest.soil_moisture
            ph = latest.ph_level
            temp = latest.temperature
            rain = latest.is_raining
        else:
            soil = block.current_moisture
            ph = block.current_ph
            temp = block.current_temp
            rain = block.is_raining

        return JsonResponse({
            "soil": soil,
            "ph": ph,
            "temp": temp,
            "rain": rain,
            "pump": block.pump_status,
            "mode": block.mode
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@csrf_exempt
def control_pump(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)

            action = data.get("action")
            block_id = data.get("block_id")

            block = Block.objects.get(id=block_id)

            if action == "toggle_mode":
                block.mode = "manual" if block.mode == "auto" else "auto"

                if block.mode == "auto":
                    block.pump_status = False

                block.save()

            elif action == "toggle_pump":
                if block.mode == "manual":
                    block.pump_status = not block.pump_status
                    block.save()

                    if block.pump_status:
                        WaterLog.objects.create(
                            block=block,
                            amount=0,
                            moisture_at_time=block.current_moisture,
                            mode="manual",
                            note="Manual Start"
                        )

            return JsonResponse({
                "status": "success",
                "mode": block.mode,
                "pump": block.pump_status
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

    farms = user_obj.farms.prefetch_related("blocks")

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

    last_log = WaterLog.objects.filter(amount__gt=0).last()
    last_watered_time = (
        last_log.timestamp.strftime("%b %d, %I:%M %p")
        if last_log else "No data yet"
    )

    return render(request, 'farmer_dashboard.html', {
        'user_obj': user_obj,
        'farms': farms,
        'selected_block': selected_block,
        'last_watered': last_watered_time
    })
    
#_______________LGU DASHBOARDDDDD________________________#

@lgu_required
def lgu_dashboard(request):
    farmers = FarmerProfile.objects.select_related("user").all()
    farms = Farm.objects.prefetch_related("blocks__sensor_readings").select_related("farmer")

    farm_overview = []
    priority_alerts = []

    # Helper function
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

            # ALERTS
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

        # AVERAGES
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
            "farmer": farm.farmer,
            "block_count": count,
            "avg_moisture": round(avg_moisture, 1),
            "avg_ph": round(avg_ph, 1),
            "avg_temp": round(avg_temp, 1),
            "status": status,
        })

    # SORT + LIMIT (IMPORTANT)
    priority_alerts = sorted(
        priority_alerts,
        key=lambda a: (a["priority"], -a["timestamp"].timestamp())
    )[:5]

    return render(request, "lgu_dashboard.html", {
        "farmers": farmers,
        "farm_overview": farm_overview,
        "priority_alerts": priority_alerts,
    })
def list_farms(request):
    farms = Farm.objects.all().values('id', 'name', 'location')
    return JsonResponse(list(farms), safe=False)


def water_logs(request):
    """Returns the last 50 watering events for the logs table."""
    farm_id = request.GET.get('farm_id', 1)
    logs = WaterLog.objects.filter(farm_id=farm_id, amount__gt=0).order_by('-timestamp')[:50]
    
    log_data = []
    for l in logs:
        log_data.append({
            "time": l.timestamp.strftime("%b %d, %I:%M %p"),
            "amount": f"{l.amount * 1000:.1f}L", # Convert m3 to Liters for display
            "note": l.note or "Regular Cycle"
        })
        
    return JsonResponse({"logs": log_data})

#--------notipppppppppp_____________
def send_alert(message, alert_style):
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "farm_updates",
        {
            "type": "send_notification",
            "message": message,
            "notification_type": alert_style # 'red', 'green', or 'blue'
        }
    )
#_______________________LGU__________#
@lgu_required
def lgu_farm_detail(request, farm_id):
    farm = Farm.objects.prefetch_related("blocks").select_related("farmer").get(id=farm_id)
    blocks = farm.blocks.all()

    return render(request, "lgu_farm_detail.html", {
        "farm": farm,
        "blocks": blocks,
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

    farms = Farm.objects.select_related("farmer").prefetch_related("blocks").all()

    # SEARCH BY CATEGORY
    if search:
        if filter_by == "name":
            farms = farms.filter(name__icontains=search)

        elif filter_by == "location":
            farms = farms.filter(location__icontains=search)

        elif filter_by == "farmer":
            farms = farms.filter(farmer__farmer_profile__full_name__icontains=search)

        elif filter_by == "block":
            farms = farms.filter(blocks__name__icontains=search)

        else:  # ALL
            farms = farms.filter(
                Q(name__icontains=search) |
                Q(location__icontains=search) |
                Q(farmer__farmer_profile__full_name__icontains=search) |
                Q(blocks__name__icontains=search)
            )

    # LOCATION FILTER (separate dropdown)
    if location:
        farms = farms.filter(location__iexact=location)

    # REMOVE DUPLICATES (important when filtering by blocks)
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
    farms = Farm.objects.prefetch_related("blocks").select_related("farmer").all()

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
        "block__farm",
        "block__farm__farmer"
    ).order_by("-timestamp")[:100]

    return render(request, "lgu_logs.html", {
        "logs": logs
    })


    #____CRUD LGU_FARMERS____#
@lgu_required
def lgu_farm_detail(request, farm_id):
    farm = Farm.objects.prefetch_related("blocks").select_related("farmer").get(id=farm_id)
    blocks = farm.blocks.all()

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
        "avg_moisture": round(avg_moisture, 1),
        "avg_ph": round(avg_ph, 1),
        "avg_temp": round(avg_temp, 1),
        "active_pumps": active_pumps,
        "block_count": block_count,
    })


@lgu_required
def lgu_farmer_edit(request, farmer_id):
    farmer = FarmerProfile.objects.get(id=farmer_id)

    if request.method == "POST":
        farmer.full_name = request.POST.get("full_name")
        farmer.contact_number = request.POST.get("contact_number")
        farmer.address = request.POST.get("address")
        farmer.save()

        return redirect("lgu_farmers")

    return render(request, "lgu_farmer_edit.html", {
        "farmer": farmer
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

    # simple analytics logic
    if block.current_moisture < 35:
        moisture_status = "Needs Water"
    elif block.current_moisture > 70:
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

    return render(request, "lgu_block_detail.html", {
        "block": block,
        "moisture_status": moisture_status,
        "ph_status": ph_status,
        "temp_status": temp_status,
    })



