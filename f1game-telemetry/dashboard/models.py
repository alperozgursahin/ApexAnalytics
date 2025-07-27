# f1-telemetry-project/dashboard/models.py
from django.db import models

class RaceSession(models.Model):
    # --- YENİ EKLENEN SEÇENEKLER ---
    SESSION_TYPE_CHOICES = [
        (0, 'Bilinmiyor'),
        (1, 'Antrenman 1'),
        (2, 'Antrenman 2'),
        (3, 'Antrenman 3'),
        (4, 'Kısa Antrenman'),
        (5, 'Sıralama 1'),
        (6, 'Sıralama 2'),
        (7, 'Sıralama 3'),
        (8, 'Kısa Sıralama'),
        (9, 'Tek Turlu Sıralama'),
        (10, 'Sprint Shootout 1'),
        (11, 'Sprint Shootout 2'),
        (12, 'Sprint Shootout 3'),
        (13, 'Kısa Sprint Shootout'),
        (14, 'Tek Turlu Sprint Shootout'),
        (15, 'Yarış'),
        (16, 'Yarış 2'),
        (17, 'Yarış 3'),
        (18, 'Zamana Karşı'),
    ]
    # Oyun tarafından sağlanan benzersiz seans kimliği. CharField olarak tutuyoruz
    # çünkü bu ID çok büyük bir sayı olabilir.
    session_uid = models.CharField(max_length=25, primary_key=True, unique=True)
    
    # Seansın gerçekleştiği pistin oyun içi ID'si
    track_id = models.IntegerField(null=True, blank=True)

    session_type = models.IntegerField(
        choices=SESSION_TYPE_CHOICES, 
        default=0, 
        null=True, 
        blank=True,
        help_text="Seansın türü (Antrenman, Sıralama, Yarış vb.)"
    )
    
    # Seansın veritabanına kaydedildiği zaman (otomatik olarak atanır)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Seans ID: {self.session_uid} (Pist: {self.track_id or 'Bilinmiyor'})"

    class Meta:
        verbose_name = "Yarış Seansı"
        verbose_name_plural = "Yarış Seansları"
        ordering = ['-created_at'] # En yeni seanslar liste başında gözüksün

class Lap(models.Model):
    # Bu turu içeren seans
    session = models.ForeignKey(RaceSession, on_delete=models.CASCADE, related_name='laps')
    
    # Tur numarası (1, 2, 3...)
    lap_number = models.IntegerField()
    
    # Tur zamanı milisaniye cinsinden
    lap_time_ms = models.IntegerField()
    
    # Turun seans içindeki başlangıç zamanı (saniye). Telemetri bağlamak için kritik.
    start_time = models.FloatField(null=True, blank=True) 
    
    # Turun seans içindeki bitiş zamanı (saniye). Telemetri bağlamak için kritik.
    end_time = models.FloatField(null=True, blank=True)   

    class Meta:
        # Bir seansta aynı tur numarasından sadece bir tane olabilir
        unique_together = ('session', 'lap_number') 
        ordering = ['lap_number'] # Tur numarasına göre sırala

    def __str__(self):
        return f"Seans {self.session.session_uid} - Tur {self.lap_number} ({self.lap_time_ms / 1000:.3f}s)"

class TelemetryData(models.Model):
    # Bu telemetri noktasının ait olduğu seans
    session = models.ForeignKey(RaceSession, on_delete=models.CASCADE, related_name='telemetry_data')
    
    # Bu telemetri noktasının ait olduğu tur (opsiyonel olabilir, pit yolunda tur yoksa null)
    lap = models.ForeignKey(Lap, on_delete=models.CASCADE, related_name='telemetry_points', null=True, blank=True) 
    
    # Paketin seansın başlangıcından itibaren geçen toplam zamanı (saniye)
    session_time = models.FloatField() 
    
    # Turun başlangıcından itibaren geçen süre (saniye). Her tur için 0'dan başlar.
    lap_time = models.FloatField()     
    
    # Anlık hız (km/s)
    speed = models.IntegerField()      
    
    # Gaz pedalına basma oranı (0.0 - 1.0)
    throttle = models.FloatField()     
    
    # Fren pedalına basma oranı (0.0 - 1.0)
    brake = models.FloatField()        
    
    # Anlık vites (-1: Geri, 0: Nötr, 1-8: İleri). Bu alanı null=True yaptık.
    gear = models.IntegerField(null=True, blank=True) 

    # Depodaki anlık yakıt miktarı (kg). Her telemetri anında bu veri olmayacağı için
    fuel_in_tank = models.FloatField(null=True, blank=True)

    rpm = models.PositiveIntegerField(null=True, blank=True, help_text="Motor Devri (RPM)")

    class Meta:
        ordering = ['session_time'] # Zaman sırasına göre sırala

    def __str__(self):
        return f"Seans {self.session.session_uid} - Zaman {self.session_time:.2f}s - Hız: {self.speed} km/s"

# Ham Veri Modeli
# Oyundan gelen tüm UDP paketlerini, türü ne olursa olsun, bir kopya olarak saklar.
# Gelecekte farklı analizler yapmak veya orijinal paketin tüm detaylarına ihtiyacın olduğunda değerlidir.
class RawPacket(models.Model):
    # Bu paketin ait olduğu seans
    session = models.ForeignKey(RaceSession, on_delete=models.CASCADE, related_name='raw_packets')
    
    # Paketin türünü belirten ID (0-16 arası değerler)
    packet_id = models.IntegerField()       
    
    # Paketin gönderildiği andaki seans içindeki toplam zaman (saniye)
    session_time = models.FloatField()      
    
    # Paketin tüm içeriği ham JSON formatında saklanır.
    # JSONField, veritabanına JSON nesnesi olarak kaydeder ve Python sözlükleri/listeleri olarak döner.
    json_data = models.JSONField()          
    
    # Paketin veritabanına kaydedilme zamanı (otomatik olarak atanır)
    created_at = models.DateTimeField(auto_now_add=True) 

    class Meta:
        ordering = ['session_time'] # Zaman sırasına göre sırala
        verbose_name = "Ham UDP Paket"
        verbose_name_plural = "Ham UDP Paketleri"

    def __str__(self):
        # Human-readable bir string döndür. json_data'nın tamamı çok uzun olabilir.
        first_part_of_data = str(self.json_data)[:50] 
        return f"Seans {self.session.session_uid} - ID: {self.packet_id} - Zaman: {self.session_time:.2f}s - Veri: {first_part_of_data}..."