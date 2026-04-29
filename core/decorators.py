from functools import wraps
from django.shortcuts import redirect
from django.http import JsonResponse


def lgu_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            if request.path.startswith("/api/"):
                return JsonResponse({
                    "status": "error",
                    "message": "LGU login required."
                }, status=403)

            return redirect("/lgu-login/")

        if not hasattr(request.user, "lgu_profile"):
            if request.path.startswith("/api/"):
                return JsonResponse({
                    "status": "error",
                    "message": "LGU account required."
                }, status=403)

            return redirect("/farmer-login/")

        return view_func(request, *args, **kwargs)

    return wrapper


def farmer_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            if request.path.startswith("/api/"):
                return JsonResponse({
                    "status": "error",
                    "message": "Farmer login required."
                }, status=403)

            return redirect("/farmer-login/")

        if not hasattr(request.user, "farmer_profile"):
            if request.path.startswith("/api/"):
                return JsonResponse({
                    "status": "error",
                    "message": "Farmer account required."
                }, status=403)

            return redirect("/lgu-login/")

        return view_func(request, *args, **kwargs)

    return wrapper