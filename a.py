import re
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pytz
import xml.etree.ElementTree as ET
from xml.dom import minidom

tz_wib = pytz.timezone('Asia/Jakarta')

def format_nama_channel(channel_asli):
    ch = channel_asli.strip().lower()
    if ch in ['bein sports 1', 'bein sports']: return 'beIN Sports 1 Indonesia'
    elif ch == 'bein sports 1 au': return 'beIN Sports 1 AU'
    elif ch == 'bein sports 2': return 'beIN Sports 2 Indonesia'
    elif ch == 'spotv': return 'SPOTV Asia'
    return channel_asli.strip()

def scrape_livesports():
    jadwal_ekstrak = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        url = 'https://www.livesportsontv.com/'
        
        try:
            page.goto(url, timeout=60000, wait_until='domcontentloaded')
            page.wait_for_timeout(8000)
        except Exception as e:
            print(f"Peringatan muat halaman: {e}")
        
        html = page.content()
        soup = BeautifulSoup(html, 'html.parser')
        
        # 1. HAPUS SAMPAH: Buang Header, Judul Web, dan Menu agar tidak ikut tersedot
        for tag in soup(['head', 'header', 'footer', 'nav', 'script', 'style', 'svg']):
            tag.decompose()
            
        # 2. JANGKAR WAKTU: Cari semua teks yang mirip jam (Misal 14:00, 02:30)
        time_pattern = re.compile(r'\b\d{1,2}:\d{2}\b')
        semua_teks_waktu = soup.find_all(string=time_pattern)
        
        diproses = set() # Untuk mencegah jadwal ganda
        
        for teks_waktu in semua_teks_waktu:
            waktu_teks = teks_waktu.strip()
            waktu_match = re.search(r'(\d{1,2}):(\d{2})', waktu_teks)
            if not waktu_match: continue
            
            # 3. CARI BUNGKUSNYA: Naik ke elemen HTML di atasnya untuk mengambil 1 baris jadwal utuh
            parent = teks_waktu.parent
            row = parent
            for _ in range(4): # Naik maksimal 4 tingkat
                if parent.parent and parent.parent.name in ['div', 'li', 'tr', 'a']:
                    if len(parent.parent.get_text(strip=True)) < 300: # Asumsi 1 baris tidak lebih dari 300 huruf
                        row = parent.parent
                parent = parent.parent
            
            # Hindari memproses baris yang sama berulang kali
            row_text_full = row.get_text(separator=" ", strip=True)
            if row_text_full in diproses: continue
            diproses.add(row_text_full)
            
            # 4. EKSTRAK NAMA ACARA
            teks_waktu.extract() # Cabut teks waktu agar tidak menyatu dengan nama pertandingan
            sisa_teks = list(row.stripped_strings)
            acara = " ".join(sisa_teks)
            
            # Filter agar judul web tidak lolos
            if len(acara) < 5 or "Live Sports" in acara: continue
            
            # 5. EKSTRAK LOGO TV (Membaca gambar alt/title)
            channels = []
            for img in row.find_all('img'):
                alt = img.get('alt', '').strip()
                title = img.get('title', '').strip()
                # Ambil nama TV dari logo jika ada
                if alt and len(alt) < 25: channels.append(alt)
                elif title and len(title) < 25: channels.append(title)
            
            if not channels:
                channels = ["TV Belum Diketahui"]
            
            tv_asli = ", ".join(set(channels)) # Gabungkan jika disiarkan di banyak TV
            tv_bersih = format_nama_channel(tv_asli)
            
            # 6. KONVERSI JAM
            sekarang = datetime.now(tz_wib)
            jam = int(waktu_match.group(1))
            menit = int(waktu_match.group(2))
            
            try:
                dt_event = sekarang.replace(hour=jam, minute=menit, second=0)
                jam_xmltv = dt_event.strftime('%Y%m%d%H%M%S %z')
            except:
                jam_xmltv = sekarang.strftime('%Y%m%d%H%M%S %z')
            
            # 7. CEK STATUS LIVE
            status_tayang = 'Sedang Tayang' if 'live' in row_text_full.lower() else 'Akan Tayang'
            
            jadwal_ekstrak.append({
                'acara': acara,
                'kategori': 'Olahraga',
                'status': status_tayang,
                'tv': tv_bersih,
                'start_xml': jam_xmltv
            })
            
        browser.close()
    return jadwal_ekstrak

def generate_xmltv(data_jadwal):
    print(f"Berhasil menarik {len(data_jadwal)} pertandingan. Membuat XML...")
    tv = ET.Element('tv', {'generator-info-name': 'Auto EPG Smart Sports'})
    
    for item in data_jadwal:
        start_dt = datetime.strptime(item['start_xml'], '%Y%m%d%H%M%S %z')
        stop_dt = start_dt + timedelta(hours=2) # Durasi default 2 jam
        stop_xml = stop_dt.strftime('%Y%m%d%H%M%S %z')
        
        channel_id = item['tv'].replace(' ', '').replace(',', '').lower()
        
        prog = ET.SubElement(tv, 'programme', {'start': item['start_xml'], 'stop': stop_xml, 'channel': channel_id})
        ET.SubElement(prog, 'title', {'lang': 'id'}).text = item['acara']
        ET.SubElement(prog, 'desc', {'lang': 'id'}).text = f"[{item['status']}] Disiarkan di: {item['tv']}"
        ET.SubElement(prog, 'category', {'lang': 'id'}).text = item['kategori']

    xmlstr = minidom.parseString(ET.tostring(tv)).toprettyxml(indent="  ")
    
    with open("epg-sports.xml", "w", encoding="utf-8") as f:
        f.write(xmlstr)

if __name__ == "__main__":
    data = scrape_livesports()
    generate_xmltv(data)
