
from django.utils.crypto import get_random_string
from django.shortcuts import redirect
from django.core.cache import cache
from urllib.parse import urlencode, quote
from django.conf import settings
from django.http import HttpResponse
from django.urls import reverse
import http.client
import json


LINE_CHANNEL_ID = settings.LINELOGIN_CHANNEL_ID
LINE_SECRET = settings.LINELOGIN_SECRET
CALLBACK_URL = settings.LINGLOGIN_CALLBACK_URL
LINE_ENDPOINT = 'https://access.line.me/dialog/oauth/weblogin?response_type=code&client_id=%s&redirect_uri=%s&state=%s'


def nav(request, label):
    if label == 'join':
        return redirect(reverse('line_association') + '?url=' + quote(request.get_full_path()))
    elif label == 'dairy_reports':
        return redirect(reverse('patient_dairly_reports') + '?url=' + quote(request.get_full_path()))
    else:
        return HttpResponse(label)


def login(request):
    url = request.GET.get('url', '/')
    state = get_random_string(16)
    cache.set('_linelogin:%s' % state, url, 600)
    url = LINE_ENDPOINT % (LINE_CHANNEL_ID, CALLBACK_URL, state)
    return redirect(url)


def final(request):
    state = request.GET.get('state')
    code = request.GET.get('code')

    if 'HTTP_AWS_GATEWAY' in request.META:
        return redirect(request.build_absolute_uri(reverse('linelogin_final')) + "?state=%s&code=%s" % (state, code))

    url = cache.get('_linelogin:%s' % state)
    if not url:
        return HttpResponse('timeout')

    conn = http.client.HTTPSConnection('api.line.me')
    conn.request('POST', '/v2/oauth/accessToken',
                 urlencode({'grant_type': 'authorization_code', 'client_id': str(LINE_CHANNEL_ID),
                            'client_secret': LINE_SECRET, 'code': code, 'redirect_uri': CALLBACK_URL}),
                 {'Content-Type': 'application/x-www-form-urlencoded'})

    resp = conn.getresponse()
    if resp.status != 200:
        return HttpResponse('line server login error')

    access_token = json.loads(resp.read().decode())['access_token']
    conn.request('GET', '/v2/profile', None, {'Authorization': 'Bearer %s' % access_token})
    resp = conn.getresponse()
    if resp.status != 200:
        return HttpResponse('line server auth error')

    line_id = json.loads(resp.read().decode())['userId']
    request.session['line_id'] = line_id
    return redirect(url)
