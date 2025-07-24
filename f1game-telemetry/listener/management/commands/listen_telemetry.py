# listener/management/commands/listen_telemetry.py

import socket
import os
import json
import signal # Sinyal yakalama için bu modülü import ediyoruz
import sys
from django.core.management.base import BaseCommand, CommandError

from listener.parser24 import PacketHeader, HEADER_FIELD_TO_PACKET_TYPE, PacketSessionData
from dashboard.models import RaceSession

DATA_DIR = 'data'

# Programın durması gerektiğini belirten bir global bayrak (flag)
shutdown_flag = False

def signal_handler(sig, frame):
    """
    Ctrl+C (SIGINT sinyali) yakalandığında bu fonksiyon çalışacak.
    """
    global shutdown_flag
    print('\nCtrl+C algılandı! Dinleyici güvenli bir şekilde durduruluyor...')
    shutdown_flag = True

class Command(BaseCommand):
    help = 'F1 24 UDP telemetri verilerini dinler ve seansları otomatik olarak veritabanına ve dosyalara kaydeder.'

    def handle(self, *args, **options):
        # Program başlarken, Ctrl+C sinyali için kendi fonksiyonumuzu kaydediyoruz.
        signal.signal(signal.SIGINT, signal_handler)

        udp_socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        udp_socket.bind(('', 20777))
        udp_socket.settimeout(1.0)

        self.stdout.write(self.style.SUCCESS('UDP Dinleyici başlatıldı. Port 20777 dinleniyor...'))
        self.stdout.write(self.style.NOTICE('Durdurmak için CTRL+C\'ye basın.'))

        # Ana döngü artık "shutdown_flag" false olduğu sürece çalışacak.
        while not shutdown_flag:
            try:
                packet_data, addr = udp_socket.recvfrom(2048)
                
                header = PacketHeader.from_buffer_copy(packet_data)
                packet_id = header.m_packet_id

                if packet_id in HEADER_FIELD_TO_PACKET_TYPE:
                    packet = HEADER_FIELD_TO_PACKET_TYPE[packet_id].from_buffer_copy(packet_data)
                    session_uid = header.m_session_uid

                    if session_uid == 0:
                        continue 

                    session_obj, created = RaceSession.objects.get_or_create(session_uid=str(session_uid))

                    if created:
                        self.stdout.write(self.style.SUCCESS(f"Yeni seans (ID: {session_uid}) veritabanına kaydedildi!"))
                    
                    if isinstance(packet, PacketSessionData) and session_obj.track_id is None:
                        session_obj.track_id = packet.m_track_id
                        session_obj.save()
                        self.stdout.write(self.style.SUCCESS(f"Seans (ID: {session_uid}) için pist ID ({packet.m_track_id}) güncellendi."))

                    session_dir = os.path.join(DATA_DIR, f"session_{session_uid}")
                    os.makedirs(session_dir, exist_ok=True)
                    log_file_path = os.path.join(session_dir, "telemetry_log.jsonl")
                    
                    with open(log_file_path, "a") as log_file:
                        packet_dict = packet.to_dict()
                        log_file.write(json.dumps(packet_dict) + "\n")
                    
                    self.stdout.write(f'Paket {packet.__class__.__name__} -> {log_file_path} dosyasına kaydedildi.')
            
            except socket.timeout:
                # Zaman aşımı olduğunda hiçbir şey yapma, döngü devam etsin.
                # Bu sayede "shutdown_flag" kontrol edilebilir.
                continue
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Döngü içinde bir hata oluştu: {e}'))
                # Ciddi bir hata varsa döngüyü kır.
                break
        
        # Döngü bittikten sonra (shutdown_flag True olduğunda) soketi kapat.
        udp_socket.close()
        self.stdout.write(self.style.SUCCESS('Soket başarıyla kapatıldı.'))