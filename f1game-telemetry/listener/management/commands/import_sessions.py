import os
import json
from collections import defaultdict
from django.core.management.base import BaseCommand
from dashboard.models import RaceSession, Lap, TelemetryData, RawPacket 
from django.db import transaction

class Command(BaseCommand):
    help = 'data/ klasöründeki mevcut seans loglarını okur ve veritabanına aktarır.'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Mevcut seans logları veritabanına aktarılıyor...'))
        data_dir = 'data'
        if not os.path.isdir(data_dir):
            self.stdout.write(self.style.WARNING(f"'{data_dir}' klasörü bulunamadı."))
            return

        RawPacket.objects.all().delete()
        TelemetryData.objects.all().delete()
        Lap.objects.all().delete()
        self.stdout.write(self.style.SUCCESS('Eski RawPacket, Lap ve Telemetry verileri temizlendi.'))

        session_folders = [d for d in os.listdir(data_dir) if d.startswith('session_')]

        for folder_name in session_folders:
            session_uid_str = folder_name.split('_')[1]
            log_file_path = os.path.join(data_dir, folder_name, "telemetry_log.jsonl")

            try:
                session, _ = RaceSession.objects.get_or_create(session_uid=session_uid_str)
                self.stdout.write(f"İşleniyor: {session_uid_str}")

                with open(log_file_path, 'r') as f:
                    packets = [json.loads(line) for line in f]
                
                player_car_index = self._get_player_car_index(packets)
                if player_car_index is None:
                    continue

                self._update_session_info(packets, session)
                self._save_raw_packets(packets, session)
                laps_info = self._process_laps(packets, session, player_car_index)
                
                # Eski _process_telemetry yerine bu yeni metodu kullanıyoruz
                self._process_combined_data(packets, session, player_car_index, laps_info)

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Hata oluştu {session_uid_str} seansı işlenirken: {e}"))
                continue 

        self.stdout.write(self.style.SUCCESS('Tüm seanslar başarıyla veritabanına aktarıldı.'))

    def _get_player_car_index(self, packets):
        if packets: return packets[0].get('m_header', {}).get('m_player_car_index')
        return None

    def _update_session_info(self, packets, session):
        """
        Seans paketini (ID=1) bulur ve hem track_id hem de session_type
        alanlarını günceller.
        """
        for p in packets:
            if p.get('m_header', {}).get('m_packet_id') == 1:
                track_id = p.get('m_track_id')
                session_type = p.get('m_session_type') # <-- YENİ
                
                updated = False
                if track_id is not None and session.track_id != track_id:
                    session.track_id = track_id
                    updated = True
                
                if session_type is not None and session.session_type != session_type:
                    session.session_type = session_type # <-- YENİ
                    updated = True

                if updated:
                    session.save()
                    self.stdout.write(self.style.NOTICE(f'  -> Seans bilgileri güncellendi (Pist: {track_id}, Tür: {session_type})'))
                return

    def _save_raw_packets(self, packets, session):
        raw_to_create = [RawPacket(session=session, packet_id=p['m_header']['m_packet_id'], session_time=p['m_header']['m_session_time'], json_data=p) for p in packets if 'm_header' in p]
        if raw_to_create:
            RawPacket.objects.bulk_create(raw_to_create)
            self.stdout.write(self.style.SUCCESS(f'  -> {len(raw_to_create)} adet ham paket kaydedildi.'))

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
                    laps_to_create.append(Lap(session=session, lap_number=lap_to_record, lap_time_ms=last_lap_ms, start_time=start_time, end_time=session_time))
                    recorded_laps.add(lap_to_record)
        if laps_to_create:
            Lap.objects.bulk_create(laps_to_create)
            self.stdout.write(self.style.SUCCESS(f'  -> {len(laps_to_create)} adet tur veritabanına eklendi.'))
        return laps_info

    def _process_combined_data(self, packets, session, player_car_index, laps_info):
        time_data = defaultdict(dict)
        for p in packets:
            h = p.get('m_header', {})
            t = h.get('m_session_time')
            if t is None: continue
            key = round(t * 50) / 50
            if h.get('m_packet_id') == 6: # CarTelemetryData
                tel = p['m_car_telemetry_data'][player_car_index]
                # ÖNEMLİ: parser24.py'deki alan adının 'm_engine_rpm' olduğunu varsayıyoruz
                time_data[key].update({'speed': tel.get('m_speed'), 'throttle': tel.get('m_throttle'), 'brake': tel.get('m_brake'), 'gear': tel.get('m_gear'), 'rpm': tel.get('m_engine_rpm')})
            elif h.get('m_packet_id') == 7: # CarStatusData
                stat = p['m_car_status_data'][player_car_index]
                time_data[key].update({'fuel_in_tank': stat.get('m_fuel_in_tank')})

        # Veritabanına yazılacak nesneleri hazırla
        telemetry_to_create = []
        lap_db_objects = {lap.lap_number: lap for lap in Lap.objects.filter(session=session)}
        sorted_laps = sorted(laps_info.items())
        last_known_fuel = None

        for time, data in sorted(time_data.items()):
            # Yakıt verisi geldiyse güncelle, gelmediyse son bilineni kullan
            last_known_fuel = data.get('fuel_in_tank', last_known_fuel)
            
            # Sadece telemetri verisi (hız, rpm vb.) olan zaman noktalarını kaydet
            if 'speed' in data or 'rpm' in data:
                lap_obj, lap_time = None, None
                for num, times in sorted_laps:
                    if times['start_time'] <= time < times['end_time']:
                        lap_obj = lap_db_objects.get(num)
                        lap_time = time - times['start_time']
                        break
                
                telemetry_to_create.append(TelemetryData(
                    session=session, 
                    lap=lap_obj, 
                    session_time=time, 
                    lap_time=lap_time if lap_time is not None else time,
                    speed=data.get('speed', 0), 
                    throttle=data.get('throttle', 0.0), 
                    brake=data.get('brake', 0.0),
                    gear=data.get('gear', 0), 
                    rpm=data.get('rpm', 0),
                    fuel_in_tank=last_known_fuel
                ))
        
        if telemetry_to_create:
            # Eski veriyi silmek, tekrar import ederken tutarlılık sağlar
            TelemetryData.objects.filter(session=session).delete()
            TelemetryData.objects.bulk_create(telemetry_to_create, batch_size=500)
            self.stdout.write(self.style.SUCCESS(f'  -> {len(telemetry_to_create)} adet birleşik telemetri noktası eklendi.'))
