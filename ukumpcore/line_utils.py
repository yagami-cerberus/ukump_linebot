
from django.shortcuts import redirect
from django.urls import reverse

from urllib.parse import quote


def require_lineid(fn):
    def wrapper(request, *args, **kw):
        if 'line_id' not in request.session:
            return redirect(reverse('linelogin') + '?url=' + quote(request.get_full_path()))
        else:
            return fn(request, *args, **kw)
    return wrapper
