# dashboard/analysis.py

import os
import json
import math
from .models import RaceSession, Lap, TelemetryData # Modelleri import ettik

class SessionAnalyzer:
    """
    Bir seansın veritabanındaki loglarını okuyan ve çeşitli analizler yapan bir sınıf.
    """
    def __init__(self, session_uid):
        self.session_uid = session_uid
        # Artık log_file_path kullanmıyoruz, doğrudan veritabanından çekeceğiz.
        self.session_obj = self._get_session_object() # RaceSession objesini alıyoruz
        self.all_laps = self._get_all_laps_from_db() # Veritabanından turları çekiyoruz
        self.fastest_lap = self._get_fastest_lap_from_db() # Veritabanından en hızlı turu çekiyoruz

    def _get_session_object(self):
        """RaceSession objesini veritabanından döndürür."""
        try:
            return RaceSession.objects.get(session_uid=self.session_uid)
        except RaceSession.DoesNotExist:
            return None

    def _get_all_laps_from_db(self):
        """Veritabanındaki tüm tamamlanmış turları bulur."""
        if not self.session_obj:
            return []
        
        # Session objesine bağlı tüm Lap objelerini çekiyoruz
        laps_queryset = self.session_obj.laps.all().order_by('lap_number')
        
        laps = []
        for lap_obj in laps_queryset:
            laps.append({
                'lap': lap_obj.lap_number,
                'time_ms': lap_obj.lap_time_ms,
                'start_time': lap_obj.start_time,
                'end_time': lap_obj.end_time
            })
        return laps

    def _get_fastest_lap_from_db(self):
        """Veritabanındaki turlar arasından en hızlısını döndürür."""
        if not self.all_laps:
            return None
        return min(self.all_laps, key=lambda x: x['time_ms'])

    def get_telemetry_for_fastest_lap(self):
        """En hızlı turun telemetri verilerini veritabanından filtreler."""
        if not self.fastest_lap or not self.session_obj:
            return []
        
        telemetry_data = []
        fastest_lap_number = self.fastest_lap['lap']

        # En hızlı tura ait TelemetryData'yı veritabanından çekiyoruz
        # Burada lap__lap_number__exact kullanarak Lap ForeignKey üzerinden filtreliyoruz
        telemetry_queryset = TelemetryData.objects.filter(
            session=self.session_obj, 
            lap__lap_number=fastest_lap_number
        ).order_by('session_time')

        # Alternatif olarak, eğer Lap modeline lap_time_start ve lap_time_end eklediysek,
        # session_time ile de filtreleyebiliriz:
        # telemetry_queryset = TelemetryData.objects.filter(
        #     session=self.session_obj,
        #     session_time__gte=self.fastest_lap['start_time'],
        #     session_time__lte=self.fastest_lap['end_time']
        # ).order_by('session_time')


        for telemetry_obj in telemetry_queryset:
            # lap_time'ı doğrudan modelden alıyoruz, çünkü import ederken hesaplamıştık
            telemetry_data.append({
                'lap_time': telemetry_obj.lap_time, 
                'speed': telemetry_obj.speed,
                'throttle': telemetry_obj.throttle, 
                'brake': telemetry_obj.brake,
                'gear': telemetry_obj.gear # Gear'ı da ekleyelim
            })
        return telemetry_data
    
    def get_fuel_data_for_session(self):
        """Tüm seans boyunca yakıt verisini veritabanından çeker."""
        if not self.session_obj: return []
        
        # Sadece `fuel_in_tank` alanı dolu olan kayıtları, zaman ve yakıt değeri olarak çekiyoruz.
        # .values() kullanmak, sadece ihtiyacımız olan sütunları alarak sorguyu daha verimli hale getirir.
        fuel_data = TelemetryData.objects.filter(
            session=self.session_obj, 
            fuel_in_tank__isnull=False
        ).order_by('session_time').values('session_time', 'fuel_in_tank')
        print(f"Yakıt verisi: {list(fuel_data)}")  # Debug için yazdırıyoruz
        
        return list(fuel_data)
    
    def run_full_analysis(self):
        """Tüm analizleri çalıştırır ve sonuçları bir sözlükte toplar."""
        if not self.session_obj:
            return {'error': f'Seans (UID: {self.session_uid}) veritabanında bulunamadı.'}

        fastest_lap_str = "Geçerli tur bulunamadı."
        if self.fastest_lap:
            total_seconds = self.fastest_lap['time_ms'] / 1000
            minutes = math.floor(total_seconds / 60)
            seconds = total_seconds % 60
            fastest_lap_str = f"Tur {self.fastest_lap['lap']}: {minutes}:{seconds:06.3f}"

        return {
            'lap_times_chart_data': self.all_laps,
            'telemetry_chart_data': self.get_telemetry_for_fastest_lap(),
            'fastest_lap_str': fastest_lap_str,
            'fuel_chart_data': self.get_fuel_data_for_session(),
            'error': None
        }