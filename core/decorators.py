from functools import wraps
from django.shortcuts import redirect

def lgu_required(view_func):
    def wrapper(request, *args, **kwargs):

        if not request.user.is_authenticated:
            return redirect("lgu_login")  # ✔ correct

        if not request.user.groups.filter(name="LGU").exists():
            return redirect("farmer_login")

        return view_func(request, *args, **kwargs)

    return wrapper


def farmer_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):

        if not request.user.is_authenticated:
            return redirect("farmer_login")

        if not request.user.groups.filter(name="Farmers").exists():
            return redirect("lgu_login")

        return view_func(request, *args, **kwargs)

    return wrapper