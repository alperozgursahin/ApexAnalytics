# dashboard/analysis.py

import math
from .models import RaceSession, Lap, TelemetryData

class SessionAnalyzer:
    """
    Bir seansın veritabanındaki loglarını okuyan ve çeşitli analizler yapan bir sınıf.
    """
    def __init__(self, session_uid):
        self.session_uid = session_uid
        self.session_obj = self._get_session_object()

    def _get_session_object(self):
        try:
            return RaceSession.objects.get(session_uid=self.session_uid)
        except RaceSession.DoesNotExist:
            return None

    def _get_all_laps_from_db(self):
        """Veritabanındaki tüm tamamlanmış turları ve lastik bilgilerini bulur."""
        if not self.session_obj:
            return []
        
        laps_queryset = self.session_obj.laps.all().order_by('lap_number')
        
        laps = []
        for lap_obj in laps_queryset:
            laps.append({
                'lap': lap_obj.lap_number,
                'time_ms': lap_obj.lap_time_ms,
                'tyre_compound': lap_obj.tyre_compound # <-- Bu satırın olması kritik
            })
        return laps

    def _get_fastest_lap_from_db(self):
        if not self.session_obj:
            return None
        return self.session_obj.laps.order_by('lap_time_ms').first()

    def get_telemetry_for_lap(self, lap_number: int):
        """
        Belirli bir turun TÜM telemetri verilerini (RPM dahil) tek seferde alır.
        """
        if not self.session_obj or not lap_number:
            return []
        
        return list(TelemetryData.objects.filter(
            session=self.session_obj,
            lap__lap_number=lap_number
        ).order_by('lap_time').values('lap_time', 'speed', 'throttle', 'brake', 'rpm'))

    def get_fuel_data_for_session(self):
        """
        Tüm seans boyunca yakıt verisini alır.
        """
        if not self.session_obj: return []
        
        return list(TelemetryData.objects.filter(
            session=self.session_obj, 
            fuel_in_tank__isnull=False
        ).order_by('session_time').values('session_time', 'fuel_in_tank'))

    def run_full_analysis(self):
        """
        Tüm analizleri çalıştırır ve view'a tek bir sözlük olarak döndürür.
        """
        if not self.session_obj:
            return {'error': f'Seans (UID: {self.session_uid}) veritabanında bulunamadı.'}

        all_laps = self._get_all_laps_from_db()
        fastest_lap_obj = self._get_fastest_lap_from_db()
        
        fastest_lap_telemetry = []
        fastest_lap_str = "Geçerli tur bulunamadı."

        if fastest_lap_obj:
            # En hızlı turun telemetrisini al
            fastest_lap_telemetry = self.get_telemetry_for_lap(fastest_lap_obj.lap_number)
            
            # En hızlı tur zamanını formatla
            total_seconds = fastest_lap_obj.lap_time_ms / 1000
            minutes = math.floor(total_seconds / 60)
            seconds = total_seconds % 60
            fastest_lap_str = f"Tur {fastest_lap_obj.lap_number}: {minutes}:{seconds:06.3f}"

        return {
            'lap_times_chart_data': all_laps,
            'telemetry_chart_data': fastest_lap_telemetry, # <-- RPM dahil tüm telemetri burada
            'fastest_lap_str': fastest_lap_str,
            'fuel_chart_data': self.get_fuel_data_for_session(),
            'error': None
        }