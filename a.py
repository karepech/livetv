from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pytz
import xml.etree.ElementTree as ET
from xml.dom import minidom
import re

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
        print(f"Membuka halaman utama: {url}")
        
        try:
            # Waktu tunggu diperpanjang, menunggu struktur dasar web dimuat
            page.goto(url, timeout=60000, wait_until='domcontentloaded')
            # Paksa bot menunggu 8 detik agar javascript merender daftar jadwal
            page.wait_for_timeout(8000) 
        except Exception as e:
            print(f"Error memuat halaman: {e}")
        
        html = page.content()
        soup = BeautifulSoup(html, 'html.parser')
        
        # Pencarian elemen diperluas untuk menangkap list atau div jadwal apapun
        matches = soup.find_all(['div', 'li'], class_=lambda c: c and ('match' in c.lower() or 'event' in c.lower() or 'fixture' in c.lower() or 'item' in c.lower()))
        
        for match in matches:
            acara_elem = match.find(class_=lambda c: c and ('title' in c.lower() or 'team' in c.lower() or 'name' in c.lower()))
            waktu_elem = match.find(class_=lambda c: c and ('time' in c.lower() or 'date' in c.lower()))
            channel_elem = match.find(class_=lambda c: c and ('channel' in c.lower() or 'network' in c.lower() or 'broadcaster' in c.lower() or 'tv' in c.lower()))
            
            # Abaikan jika tidak ada nama acara atau channel TV
            if not channel_elem or not acara_elem: continue
                
            acara = acara_elem.get_text(strip=True)
            tv_asli = channel_elem.get_text(strip=True)
            waktu_teks = waktu_elem.get_text(strip=True) if waktu_elem else ''
            
            # Cek status (Apakah Live atau hanya jadwal biasa)
            status_tayang = 'Akan Tayang'
            status_elem = match.find(class_=lambda c: c and 'live' in c.lower())
            if status_elem or 'live' in match.get('class', []):
                status_tayang = 'Sedang Tayang'
                
            tv_bersih = format_nama_channel(tv_asli)
            
            sekarang = datetime.now(tz_wib)
            jam_xmltv = sekarang.strftime('%Y%m%d%H%M%S %z')
            
            # Ekstraksi jam tayang jika formatnya HH:MM
            if waktu_teks:
                try:
                    waktu_match = re.search(r'(\d{1,2}):(\d{2})', waktu_teks)
                    if waktu_match:
                        jam = int(waktu_match.group(1))
                        menit = int(waktu_match.group(2))
                        dt_event = sekarang.replace(hour=jam, minute=menit, second=0)
                        jam_xmltv = dt_event.strftime('%Y%m%d%H%M%S %z')
                except: pass
            
            jadwal_ekstrak.append({
                'acara': acara,
                'kategori': 'Olahraga', # Menjaga kategori terpisah dari TV Lokal
                'status': status_tayang,
                'tv': tv_bersih,
                'start_xml': jam_xmltv
            })
            
        browser.close()
    return jadwal_ekstrak

def generate_xmltv(data_jadwal):
    print(f"Menyimpan {len(data_jadwal)} jadwal ke XML...")
    tv = ET.Element('tv', {'generator-info-name': 'Auto EPG All Sports'})
    
    for item in data_jadwal:
        start_dt = datetime.strptime(item['start_xml'], '%Y%m%d%H%M%S %z')
        stop_dt = start_dt + timedelta(hours=2) # Asumsi durasi 2 jam
        stop_xml = stop_dt.strftime('%Y%m%d%H%M%S %z')
        channel_id = item['tv'].replace(' ', '').replace(',', '').lower()
        
        prog = ET.SubElement(tv, 'programme', {'start': item['start_xml'], 'stop': stop_xml, 'channel': channel_id})
        ET.SubElement(prog, 'title', {'lang': 'id'}).text = item['acara']
        ET.SubElement(prog, 'desc', {'lang': 'id'}).text = f"[{item['status']}] Disiarkan di: {item['tv']}"
        ET.SubElement(prog, 'category', {'lang': 'id'}).text = item['kategori']

    xmlstr = minidom.parseString(ET.tostring(tv)).toprettyxml(indent="  ")
    
    # PERBAIKAN: Selalu tulis file meskipun data kosong, agar git add tidak error
    with open("epg-sports.xml", "w", encoding="utf-8") as f:
        f.write(xmlstr)

if __name__ == "__main__":
    data = scrape_livesports()
    generate_xmltv(data) # Eksekusi tanpa syarat if data:
