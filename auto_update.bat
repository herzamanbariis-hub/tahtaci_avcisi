@echo off
echo ====================================================
echo TAHTACI AVCISI - BIST 100 OTOMATIK GUNCELLEME MOTORU
echo ====================================================
echo Sistem arka planda calisiyor. Lutfen pencereyi kapatmayin...

cd /d "C:\Users\asus\Desktop\tahtaci_avcisi"
python data_ingestion.py --group BIST100

echo ====================================================
echo Islem tamamlandi. Pencere otomatik kapanacaktir.
timeout /t 5
