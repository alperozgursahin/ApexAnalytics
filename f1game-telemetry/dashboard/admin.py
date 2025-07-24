# dashboard/admin.py
from django.contrib import admin
from .models import RaceSession # Kendi modelimizi import ediyoruz

# Bu tek satır, RaceSession modelini admin arayüzüne ekler.
admin.site.register(RaceSession)