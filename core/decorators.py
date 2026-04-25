from functools import wraps
from django.shortcuts import redirect


def lgu_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("/lgu-login/")
        
        if not hasattr(request.user, "lgu_profile"):
            return redirect("/farmer-login/")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def farmer_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("/farmer-login/")
        
        if not hasattr(request.user, 'farmer_profile'):
            return redirect("/lgu-login/")
        
        return view_func(request, *args, **kwargs)
    return wrapper