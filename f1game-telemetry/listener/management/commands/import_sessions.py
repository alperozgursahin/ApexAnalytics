import os
import json
from collections import defaultdict
from django.core.management.base import BaseCommand
from dashboard.models import RaceSession, Lap, TelemetryData
# Gerekli sabitleri ve modelleri import ediyoruz
from django.db import transaction
from dashboard.constants import TRACK_NAMES

class Command(BaseCommand):
    help = 'data/ klasöründeki tüm seans loglarını okur, eski veriyi temizler ve yeniden veritabanına aktarır.'

    def print_header(self, text):
        """Ana başlıklar için şık bir çıktı oluşturur."""
        self.stdout.write("="*70)
        self.stdout.write(self.style.SUCCESS(text.center(70)))
        self.stdout.write("="*70)

    def print_subheader(self, text):
        """Alt başlıklar için çıktı oluşturur."""
        self.stdout.write(self.style.HTTP_INFO(f"\n>> {text}\n"))

    @transaction.atomic
    def handle(self, *args, **options):
        self.print_header("ApexAnalytics Veri Aktarım Script'i Başlatıldı")
        data_dir = 'data'
        if not os.path.isdir(data_dir):
            self.stdout.write(self.style.ERROR(f"'{data_dir}' klasörü bulunamadı. Script durduruluyor."))
            return

        # --- 1. Veritabanını Temizleme ---
        self.print_subheader("1. Eski Veritabanı Kayıtları Temizleniyor")
        TelemetryData.objects.all().delete()
        Lap.objects.all().delete()
        RaceSession.objects.all().delete()
        self.stdout.write(self.style.SUCCESS('✓ Veritabanı başarıyla temizlendi.'))

        # --- 2. Seans Dosyalarını İşleme ---
        self.print_subheader("2. Seans Log Dosyaları Okunuyor ve İşleniyor")
        session_folders = [d for d in os.listdir(data_dir) if d.startswith('session_')]

        if not session_folders:
            self.stdout.write(self.style.WARNING("İşlenecek seans dosyası bulunamadı."))
            return
            
        # ID'leri isimlere çevirmek için sözlükler oluşturalım
        session_type_map = dict(RaceSession.SESSION_TYPE_CHOICES)
        game_mode_map = dict(RaceSession.GAME_MODE_CHOICES)

        for folder_name in session_folders:
            session_uid_str = folder_name.split('_')[1]
            log_file_path = os.path.join(data_dir, folder_name, "telemetry_log.jsonl")

            if not os.path.exists(log_file_path):
                continue
            
            try:
                # Önce paketleri okuyup temel bilgileri alalım
                with open(log_file_path, 'r') as f:
                    packets = [json.loads(line) for line in f]
                
                # Geçici olarak session bilgilerini alalım, henüz kaydetmiyoruz
                temp_session_info = self._get_session_info(packets)
                
                # --- KULLANICI DOSTU MESAJ BURADA OLUŞTURULUYOR ---
                track_name = TRACK_NAMES.get(temp_session_info['track_id'], "Bilinmeyen Pist")
                game_mode_name = game_mode_map.get(temp_session_info['game_mode'], "Bilinmiyor")
                session_type_name = session_type_map.get(temp_session_info['session_type'], "Bilinmiyor")

                self.stdout.write("-" * 50)
                self.stdout.write(f"🏎️  {self.style.WARNING(track_name)} pistindeki {self.style.SUCCESS(game_mode_name)} seansı işleniyor...")
                self.stdout.write(f"   ({self.style.NOTICE(session_type_name)} - UID: {session_uid_str[:12]}...)")
                
                # Şimdi veritabanı işlemlerini yapabiliriz
                session = RaceSession.objects.create(
                    session_uid=session_uid_str,
                    track_id=temp_session_info['track_id'],
                    session_type=temp_session_info['session_type'],
                    game_mode=temp_session_info['game_mode']
                )

                player_car_index = self._get_player_car_index(packets)
                if player_car_index is None:
                    self.stdout.write(self.style.WARNING("  -> ↳ Oyuncu indeksi bulunamadı, bu seans atlanıyor."))
                    continue

                laps_info = self._process_laps(packets, session, player_car_index)
                self._process_combined_data(packets, session, player_car_index, laps_info)

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Hata oluştu {session_uid_str} seansı işlenirken: {e}"))
                continue 
        
        self.print_header("Tüm Seanslar Başarıyla Veritabanına Aktarıldı!")


    def _get_session_info(self, packets):
        """Paketleri okuyarak pist, tür ve mod ID'lerini döndürür."""
        info = {'track_id': -1, 'session_type': 0, 'game_mode': None}
        for p in packets:
            if p.get('m_header', {}).get('m_packet_id') == 1:
                info['track_id'] = p.get('m_track_id')
                info['session_type'] = p.get('m_session_type')
                info['game_mode'] = p.get('m_game_mode')
                return info
        return info

    def _get_player_car_index(self, packets):
        if packets: return packets[0].get('m_header', {}).get('m_player_car_index')
        return None

    def _process_laps(self, packets, session, player_car_index):
        laps_info, recorded_laps, laps_to_create = {}, set(), []
        for p in packets:
            h = p.get('m_header', {})
            if h.get('m_packet_id') == 2:
                lap_data = p['m_lap_data'][player_car_index]
                lap_to_record, last_lap_ms, session_time = lap_data.get('m_current_lap_num', 1) - 1, lap_data.get('m_last_lap_time_in_ms', 0), h.get('m_session_time', 0)
                if lap_to_record > 0 and last_lap_ms > 0 and lap_to_record not in recorded_laps:
                    start_time = session_time - (last_lap_ms / 1000.0)
                    laps_info[lap_to_record] = {'start_time': start_time, 'end_time': session_time}
                    # Lastik bilgisi olmadan Lap nesnesi oluşturuyoruz
                    laps_to_create.append(Lap(session=session, lap_number=lap_to_record, lap_time_ms=last_lap_ms, start_time=start_time, end_time=session_time))
                    recorded_laps.add(lap_to_record)
        if laps_to_create:
            Lap.objects.bulk_create(laps_to_create)
            self.stdout.write(f"  -> ↳ {self.style.SUCCESS(f'{len(laps_to_create)} tur verisi')} eklendi.")
        return laps_info

    def _process_combined_data(self, packets, session, player_car_index, laps_info):
        """
        Tüm telemetri ve durum verilerini (ERS ve DRS dahil) birleştirir,
        TelemetryData nesneleri oluşturur ve Lap nesnelerinin lastik bilgisini günceller.
        """
        time_data = defaultdict(dict)
        for p in packets:
            h = p.get('m_header', {})
            t = h.get('m_session_time')
            if t is None: continue
            
            key = round(t * 50) / 50 
            
            if h.get('m_packet_id') == 6: # CarTelemetryData
                tel = p['m_car_telemetry_data'][player_car_index]
                time_data[key].update({
                    'speed': tel.get('m_speed'), 
                    'throttle': tel.get('m_throttle'), 
                    'brake': tel.get('m_brake'), 
                    'gear': tel.get('m_gear'), 
                    'rpm': tel.get('m_engine_rpm'),
                    'drs': tel.get('m_drs') == 1 # <-- YENİ: DRS verisi (1 ise True, değilse False)
                })
            elif h.get('m_packet_id') == 7: # CarStatusData
                stat = p['m_car_status_data'][player_car_index]
                time_data[key].update({
                    'fuel_in_tank': stat.get('m_fuel_in_tank'),
                    'tyre_compound': stat.get('m_visual_tyre_compound'),
                    'ers_store_energy': stat.get('m_ers_store_energy'), # <-- YENİ: ERS Batarya
                    'ers_deploy_mode': stat.get('m_ers_deploy_mode')    # <-- YENİ: ERS Modu
                })

        # 1. Adım: Tüm TelemetryData nesnelerini oluştur
        telemetry_to_create = []
        laps_in_session = {lap.lap_number: lap for lap in Lap.objects.filter(session=session)}
        sorted_laps = sorted(laps_info.items())
        
        # Son bilinen değerleri saklamak için değişkenler
        last_known_data = {
            'fuel': None,
            'compound': None,
            'ers_store': None,
            'ers_mode': None
        }

        for time, data in sorted(time_data.items()):
            # Mevcut zaman diliminde veri yoksa, son bilinen değeri kullan
            last_known_data['fuel'] = data.get('fuel_in_tank', last_known_data['fuel'])
            last_known_data['compound'] = data.get('tyre_compound', last_known_data['compound'])
            last_known_data['ers_store'] = data.get('ers_store_energy', last_known_data['ers_store'])
            last_known_data['ers_mode'] = data.get('ers_deploy_mode', last_known_data['ers_mode'])

            # Sadece telemetri verisi (hız, rpm vb.) olan zaman noktalarını kaydet
            if 'speed' in data or 'rpm' in data:
                lap_obj, lap_time = None, None
                for num, times in sorted_laps:
                    if times['start_time'] <= time < times['end_time']:
                        lap_obj = laps_in_session.get(num)
                        lap_time = time - times['start_time']
                        break
                
                td = TelemetryData(
                    session=session, lap=lap_obj, session_time=time, 
                    lap_time=lap_time if lap_time is not None else time,
                    speed=data.get('speed', 0), 
                    throttle=data.get('throttle', 0.0), 
                    brake=data.get('brake', 0.0), 
                    gear=data.get('gear', 0), 
                    rpm=data.get('rpm', 0), 
                    fuel_in_tank=last_known_data['fuel'],
                    # --- YENİ ALANLARI EKLE ---
                    drs=data.get('drs', False),
                    ers_store_energy=last_known_data['ers_store'],
                    ers_deploy_mode=last_known_data['ers_mode']
                )
                # Geçici lastik verisini ekle
                td._tyre_compound = last_known_data['compound'] 
                telemetry_to_create.append(td)
        
        if telemetry_to_create:
            TelemetryData.objects.bulk_create([td for td in telemetry_to_create], batch_size=500)
            self.stdout.write(f"  -> ↳ {self.style.SUCCESS(f'{len(telemetry_to_create)} telemetri noktası')} birleştirildi.")

        # 2. Adım: Her bir turun lastik bilgisini güncelle
        for lap_num, lap_obj in laps_in_session.items():
            compounds_in_lap = [
                td._tyre_compound for td in telemetry_to_create 
                if td.lap and td.lap.lap_number == lap_num and hasattr(td, '_tyre_compound') and td._tyre_compound is not None
            ]
            
            if compounds_in_lap:
                most_common_compound = max(set(compounds_in_lap), key=compounds_in_lap.count)
                lap_obj.tyre_compound = most_common_compound
                lap_obj.save()