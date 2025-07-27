from django.shortcuts import render, get_object_or_404
from .models import RaceSession, Lap, TelemetryData
from django.db.models import Avg, Count
from .analysis import SessionAnalyzer
import os
import json
import math

TRACK_NAMES = {
    -1: "Bilinmiyor",
    0: "Melbourne",
    1: "Paul Ricard",
    2: "Shanghai",
    3: "Bahrain",
    4: "Catalunya",
    5: "Monaco",
    6: "Montreal",
    7: "Silverstone",
    8: "Hockenheim",
    9: "Hungaroring",
    10: "Spa",
    11: "Monza",
    12: "Singapore",
    13: "Suzuka",
    14: "Abu Dhabi",
    15: "Texas",
    16: "Brazil",
    17: "Austria",
    18: "Sochi",
    19: "Mexico",
    20: "Baku",
    21: "Sakhir (Short)",
    22: "Silverstone (Short)",
    23: "Texas (Short)",
    24: "Suzuka (Short)",
    25: "Hanoi", # F1 2020+
    26: "Zandvoort", # F1 2020+
    27: "Imola", # F1 2020+
    28: "Portimao", # F1 2020+
    29: "Jeddah", # F1 2021+
    30: "Miami", # F1 2022+
    31: "Las Vegas",
    32: "Losail" # F1 2023+
    # Diğer pistler için ID'leri buradan kontrol edebilirsin:
    # https://docs.google.com/spreadsheets/d/1Xy4Z6h1N4qP8_4_z1_hK0Q_N_X-f5D4j3-jN5_g5D5w/edit#gid=0 (F1 2023 UDP spec referansı)
    # F1 2024 için güncel bir liste bulunamıyorsa bu liste başlangıç için yeterlidir.
}

def dashboard_view(request):
    """
    Ana dashboard görünümü. Genel istatistikleri ve özetleri gösterir.
    """
    total_sessions = RaceSession.objects.count()
    total_laps = Lap.objects.count()
    total_telemetry_points = TelemetryData.objects.count()

    fastest_lap_overall = Lap.objects.order_by('lap_time_ms').first()
    fastest_lap_overall_str = "N/A"
    if fastest_lap_overall:
        total_seconds = fastest_lap_overall.lap_time_ms / 1000
        minutes = math.floor(total_seconds / 60)
        seconds = total_seconds % 60
        fastest_lap_overall_str = (
            f"{minutes}:{seconds:06.3f} (Tur {fastest_lap_overall.lap_number} - "
            f"Seans {fastest_lap_overall.session.session_uid[:8]}...)"
        )
    
    avg_speed_obj = TelemetryData.objects.aggregate(avg_speed=Avg('speed'))
    avg_speed = round(avg_speed_obj['avg_speed'], 2) if avg_speed_obj['avg_speed'] else 0

    track_distribution_data = RaceSession.objects.values('track_id').annotate(
        session_count=Count('track_id')
    ).order_by('-session_count')

    # Chart.js için etiketler (pist ID'leri/isimleri) ve veri (seans sayıları) hazırlayalım
    track_labels = []
    track_counts = []
    # YENİ EKLENEN: Template için birleşik liste hazırlıyoruz
    track_list_data = [] 

    most_played_track_name = "Bilinmiyor"
    
    for item in track_distribution_data:
        track_id = item['track_id']
        session_count = item['session_count']
        
        track_name = TRACK_NAMES.get(track_id, f"Bilinmiyor (ID: {track_id})")
        
        track_labels.append(track_name)
        track_counts.append(session_count)

        # YENİ EKLENEN: Birleşik listeye ekle
        track_list_data.append({'name': track_name, 'count': session_count})

        if most_played_track_name == "Bilinmiyor" and track_name != "Bilinmiyor (ID: None)": 
            most_played_track_name = track_name


    context = {
        'total_sessions': total_sessions,
        'total_laps': total_laps,
        'total_telemetry_points': total_telemetry_points,
        'fastest_lap_overall_str': fastest_lap_overall_str,
        'avg_speed': avg_speed,
        
        # Grafik verileri (hala Chart.js için lazım)
        'track_distribution_labels': track_labels,
        'track_distribution_counts': track_counts,

        # En çok oynanan pistin adı
        'most_played_track_name': most_played_track_name, 

        # YENİ EKLENEN: Listeyi göstermek için
        'track_list_data': track_list_data, 
    } 
    return render(request, 'dashboard/dashboard.html', context)

def session_list_view(request):
    """
    Veritabanındaki tüm yarış seanslarını, filtreleme özellikleriyle listeleyen bir view.
    """
    # Başlangıçta tüm seansları alıyoruz
    queryset = RaceSession.objects.all().order_by('-created_at')
    
    # GET request'ten gelen filtre parametrelerini alıyoruz
    selected_track = request.GET.get('track_id', '')
    selected_type = request.GET.get('session_type', '')

    # Eğer bir pist seçilmişse ve sayısal bir değerse, queryset'i filtrele
    if selected_track and selected_track.isdigit():
        queryset = queryset.filter(track_id=int(selected_track))

    # Eğer bir seans türü seçilmişse ve sayısal bir değerse, queryset'i filtrele
    if selected_type and selected_type.isdigit():
        queryset = queryset.filter(session_type=int(selected_type))

    context = {
        'sessions': queryset,
        'track_names': TRACK_NAMES, # Pist dropdown'ı için
        'session_types': RaceSession.SESSION_TYPE_CHOICES, # Tür dropdown'ı için
        'selected_track': selected_track, # Seçili değeri template'te göstermek için
        'selected_type': selected_type,   # Seçili değeri template'te göstermek için
    }
    return render(request, 'dashboard/session_list.html', context)

def session_detail_view(request, session_uid):
    """
    Bu view artık çok daha temiz. Sadece SessionAnalyzer'ı çağırıyor.
    """
    session = get_object_or_404(RaceSession, pk=session_uid)
    
    # 1. Analiz sınıfından bir nesne oluştur.
    analyzer = SessionAnalyzer(session_uid=session_uid)
    
    # 2. Tüm analizleri çalıştır ve sonuçları al.
    analysis_results = analyzer.run_full_analysis()
    
    track_name = TRACK_NAMES.get(session.track_id, f"Bilinmiyor (ID: {session.track_id})")
    

    context = {
        'session': session,
        'analysis': analysis_results,
        'track_name': track_name,
    }

    return render(request, 'dashboard/session_detail.html', context)