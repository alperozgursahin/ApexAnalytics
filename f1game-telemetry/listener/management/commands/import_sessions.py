
import os
import json
import math 
from django.core.management.base import BaseCommand
from dashboard.models import RaceSession, Lap, TelemetryData, RawPacket 

# PacketSessionData'yı import etmeliyiz ki track_id'ye erişebilelim
from listener.parser24 import PacketSessionData # BU SATIRI EKLEDİK/KONTROL ETTİK

from django.db import transaction

class Command(BaseCommand):
    help = 'data/ klasöründeki mevcut seans loglarını okur ve veritabanına aktarır.'

    @transaction.atomic # Tüm aktarımın tek bir veritabanı işlemi olarak yapılmasını sağlar
    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Mevcut seans logları veritabanına aktarılıyor...'))
        data_dir = 'data'

        if not os.path.isdir(data_dir):
            self.stdout.write(self.style.WARNING(f"'{data_dir}' klasörü bulunamadı."))
            return

        # Önce tüm RawPacket, TelemetryData ve Lap verilerini temizle
        # RaceSession'ları silmiyoruz, çünkü onlar session_uid'leri ile primary key.
        RawPacket.objects.all().delete() 
        TelemetryData.objects.all().delete()
        Lap.objects.all().delete()
        self.stdout.write(self.style.SUCCESS('Eski RawPacket, Lap ve Telemetry verileri temizlendi.'))

        # 'session_' ile başlayan tüm klasörleri bul
        session_folders = [d for d in os.listdir(data_dir) if d.startswith('session_')]

        for folder_name in session_folders:
            session_uid_str = folder_name.split('_')[1] # Klasör adından session_uid'yi al
            log_file_path = os.path.join(data_dir, folder_name, "telemetry_log.jsonl")

            try:
                # RaceSession objesini al veya oluştur
                session, created = RaceSession.objects.get_or_create(session_uid=session_uid_str)
                # Yeni bir seans oluşturulduysa bilgi ver
                if created:
                     self.stdout.write(f"Yeni seans oluşturuldu: {session_uid_str}")

                self.stdout.write(f"İşleniyor: {session_uid_str}")

                # Tüm paketleri dosyadan oku
                with open(log_file_path, 'r') as f:
                    packets = [json.loads(line) for line in f]
                
                player_car_index = self._get_player_car_index(packets)
                if player_car_index is None:
                    self.stdout.write(self.style.WARNING('   -> Oyuncu araç indeksi bulunamadı, bu seans atlanıyor.'))
                    continue

                # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
                # YENİ/GÜNCELLENMİŞ KISIM: SessionData'dan track_id'yi alıp kaydet
                # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
                track_id_updated_for_session = False
                for p in packets:
                    header = p.get('m_header', {})
                    if header.get('m_packet_id') == 1: # PacketSessionData'nın ID'si 1
                        track_id_from_packet = p.get('m_track_id')
                        # Eğer m_track_id varsa VE veritabanındaki track_id ile farklıysa veya boşsa güncelle
                        if track_id_from_packet is not None:
                            # Eğer session.track_id daha önce hiç ayarlanmamışsa (None ise) veya farklı bir değerse güncelle
                            if session.track_id is None or session.track_id != track_id_from_packet:
                                session.track_id = track_id_from_packet
                                session.save()
                                self.stdout.write(self.style.NOTICE(f'   -> Seans {session.session_uid[:8]}... için Pist ID güncellendi: {session.track_id}'))
                            track_id_updated_for_session = True
                            break # Pist ID'yi bulduktan sonra döngüden çık
                
                if not track_id_updated_for_session and session.track_id is None:
                     self.stdout.write(self.style.WARNING(f'   -> Seans {session.session_uid[:8]}... için PacketSessionData bulunamadı veya track_id boş.'))
                # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

                # Tüm ham paketleri RawPacket modeline kaydet
                self._save_raw_packets(packets, session)

                # Tur verilerini işle ve tur bilgilerini (başlangıç/bitiş zamanları) al
                laps_info = self._process_laps_from_lap_data(packets, session, player_car_index)
                
                # Telemetri verilerini işle
                self._process_telemetry(packets, session, player_car_index, laps_info)

            except FileNotFoundError:
                self.stdout.write(self.style.WARNING(f"{log_file_path} bulunamadı."))
                continue
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Hata oluştu {session_uid_str} seansı işlenirken: {e}"))
                continue 

        self.stdout.write(self.style.SUCCESS('Tüm seanslar başarıyla veritabanına aktarıldı.'))

    def _get_player_car_index(self, packets):
        """
        Paketler listesinden oyuncu araç indeksini bulur.
        Genellikle ilk PacketSessionData (ID 1) veya PacketCarTelemetryData (ID 6) paketinde bulunur.
        """
        for packet in packets:
            header = packet.get('m_header', {})
            player_index = header.get('m_player_car_index')
            if player_index is not None:
                return player_index
        return None

    def _save_raw_packets(self, packets, session):
        """
        Gelen tüm paketleri RawPacket modeline kaydeder.
        """
        raw_packets_to_create = []
        for packet in packets:
            header = packet.get('m_header', {})
            packet_id = header.get('m_packet_id')
            session_time = header.get('m_session_time')

            if packet_id is not None and session_time is not None:
                raw_packets_to_create.append(
                    RawPacket(
                        session=session,
                        packet_id=packet_id,
                        session_time=session_time,
                        json_data=packet # Ham JSON olarak kaydet
                    )
                )
        
        if raw_packets_to_create:
            RawPacket.objects.bulk_create(raw_packets_to_create)
            self.stdout.write(self.style.SUCCESS(f'   -> {len(raw_packets_to_create)} adet ham paket RawPacket tablosuna eklendi.'))
        else:
            self.stdout.write(self.style.WARNING('   -> Hiç ham paket bulunamadı veya kaydedilemedi.'))


    def _process_laps_from_lap_data(self, packets, session, player_car_index):
        """
        PacketLapData (ID 2) paketlerini kullanarak tur bilgilerini çıkarır ve Lap modeline kaydeder.
        """
        laps_to_create = []
        recorded_laps = set() 
        laps_info = {} 
        
        for packet in packets:
            header = packet.get('m_header', {})
            if header.get('m_packet_id') == 2: 
                player_lap_data = packet.get('m_lap_data', [])
                if not player_lap_data or len(player_lap_data) <= player_car_index:
                    continue 

                lap_data = player_lap_data[player_car_index]
                
                current_lap_num = lap_data.get('m_current_lap_num', 0)
                last_lap_time_in_ms = lap_data.get('m_last_lap_time_in_ms', 0)
                current_session_time = header.get('m_session_time', 0.0)

                if last_lap_time_in_ms > 0 and (current_lap_num - 1) not in recorded_laps:
                    lap_number = current_lap_num - 1 
                    
                    lap_end_session_time = current_session_time 
                    lap_start_session_time = lap_end_session_time - (last_lap_time_in_ms / 1000.0)

                    if lap_start_session_time < 0:
                        lap_start_session_time = 0.0

                    laps_to_create.append(
                        Lap(
                            session=session, 
                            lap_number=lap_number, 
                            lap_time_ms=last_lap_time_in_ms,
                            start_time=lap_start_session_time,
                            end_time=lap_end_session_time
                        )
                    )
                    recorded_laps.add(lap_number)
                    laps_info[lap_number] = {
                        'start_time': lap_start_session_time,
                        'end_time': lap_end_session_time
                    }
        
        if laps_to_create:
            Lap.objects.bulk_create(laps_to_create, ignore_conflicts=True)
            self.stdout.write(self.style.SUCCESS(f'   -> {len(laps_to_create)} adet tur bulundu ve veritabanına eklendi.'))
        else:
            self.stdout.write(self.style.WARNING('   -> Hiç tur bulunamadı veya kaydedilemedi.'))

        return laps_info

    def _process_telemetry(self, packets, session, player_car_index, laps_info):
        """
        PacketCarTelemetryData (ID 6) paketlerini kullanarak telemetri verilerini çıkarır ve TelemetryData modeline kaydeder.
        """
        telemetry_to_create = []
        
        sorted_laps = sorted(laps_info.items()) 

        for packet in packets:
            header = packet.get('m_header', {})
            if header.get('m_packet_id') == 6: 
                player_telemetry_data = packet.get('m_car_telemetry_data', [])
                if not player_telemetry_data or len(player_telemetry_data) <= player_car_index:
                    continue 

                telemetry = player_telemetry_data[player_car_index]
                current_session_time = header.get('m_session_time', 0.0)

                current_lap_obj = None
                current_lap_start_time = None

                for lap_num, lap_data in sorted_laps:
                    # Bir turun zaman aralığına düşen telemetriyi yakala
                    # `end_time`'ı dahil etmiyoruz, çünkü o anda bir sonraki tura geçilmiş olabilir.
                    if lap_data['start_time'] <= current_session_time < lap_data['end_time']:
                        try:
                            current_lap_obj = Lap.objects.get(session=session, lap_number=lap_num)
                            current_lap_start_time = lap_data['start_time']
                            break 
                        except Lap.DoesNotExist:
                            current_lap_obj = None
                            break

                if current_lap_obj:
                    lap_time_relative = current_session_time - current_lap_start_time
                    
                    telemetry_to_create.append(
                        TelemetryData(
                            session=session,
                            lap=current_lap_obj,
                            session_time=current_session_time,
                            lap_time=lap_time_relative,
                            speed=telemetry.get('m_speed', 0),
                            throttle=telemetry.get('m_throttle', 0.0),
                            brake=telemetry.get('m_brake', 0.0),
                            gear=telemetry.get('m_gear', 0)
                        )
                    )
        
        if telemetry_to_create:
            TelemetryData.objects.bulk_create(telemetry_to_create)
            self.stdout.write(self.style.SUCCESS(f'   -> {len(telemetry_to_create)} adet telemetri noktası veritabanına eklendi.'))
        else:
            self.stdout.write(self.style.WARNING('   -> Hiç telemetri noktası bulunamadı veya kaydedilemedi.'))
