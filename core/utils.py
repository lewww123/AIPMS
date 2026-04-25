from django.shortcuts import redirect

def redirect_by_role(user):
    if user.groups.filter(name="LGU").exists():
        return redirect("lgu_dashboard")

    elif user.groups.filter(name="Farmers").exists():
        return redirect("farmer_dashboard")

    return redirect("lgu_login")