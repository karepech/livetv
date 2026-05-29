import re
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pytz
import xml.etree.ElementTree as ET
from xml.dom import minidom

tz_wib = pytz.timezone('Asia/Jakarta')

# Daftar kata kunci untuk mendeteksi nama TV/Channel dari teks
TV_KEYWORDS = [
    'tv', 'espn', 'fox', 'bein', 'dazn', 'tsn', 'fubo', 'sports', 'network', 
    'fanatiz', 'peacock', 'paramount', 'bally', 'flo', 'ion', 'tnt', 'trutv', 
    'cbs', 'nbc', 'abc', 'hbo', 'sling', 'vix', 'apple', 'amazon', 'optus', 
    'sky', 'rds', 'sn ', 'now', 'mlb', 'media', 'masn', 'nesn', 'wkyc', 
    'marquee', 'matrix', 'midwest', 'chsn', 'disney+', 'accn', 'secn', 
    'wgnt', 'nwsl+', 'golazo', 'onesoccer', 'cfl+', 'golf channel', 'vision'
]

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
        
        # Bersihkan elemen yang tidak perlu
        for tag in soup(['head', 'header', 'footer', 'nav', 'script', 'style', 'svg', 'img']):
            tag.decompose()
            
        # Cari elemen berdasarkan jam
        time_pattern = re.compile(r'\b\d{1,2}:\d{2}\b')
        semua_teks_waktu = soup.find_all(string=time_pattern)
        
        diproses = set()
        
        for teks_waktu in semua_teks_waktu:
            waktu_teks = teks_waktu.strip()
            waktu_match = re.search(r'(\d{1,2}):(\d{2})', waktu_teks)
            if not waktu_match: continue
            
            # Ambil container baris utuh
            row = teks_waktu.parent
            for _ in range(4):
                if row.parent and row.parent.name in ['div', 'li', 'tr', 'a']:
                    if len(row.parent.get_text(strip=True)) < 300:
                        row = row.parent
            
            # Ambil semua teks yang ada di baris tersebut secara berurutan
            teks_array = list(row.stripped_strings)
            row_text_full = " ".join(teks_array)
            
            if row_text_full in diproses or "Live Sports" in row_text_full: continue
            diproses.add(row_text_full)
            
            # Hapus teks jam dan kata 'live' dari array agar tidak mengganggu
            teks_array = [t for t in teks_array if t != waktu_teks and t.lower() != 'live']
            
            channels = []
            acara_parts = []
            
            # TRIK: Baca teks dari belakang (Kanan ke Kiri)
            is_channel_zone = True
            for teks in reversed(teks_array):
                t_low = teks.lower()
                
                # Deteksi apakah teks ini adalah Channel TV
                is_kw_match = any(kw in t_low for kw in TV_KEYWORDS)
                is_short_channel = len(teks) <= 4 and teks.isupper() # Menangkap nama seperti ION, TSN
                
                if is_channel_zone and (is_kw_match or is_short_channel or t_low in ['dazn canada', 'fanatiz']):
                    channels.insert(0, teks) # Masukkan ke list channel (di depan)
                else:
                    # Kalau sudah nabrak nama tim, berarti sisa teks di depannya adalah acara
                    is_channel_zone = False
                    acara_parts.insert(0, teks)
                    
            acara = " ".join(acara_parts)
            tv_asli = ", ".join(channels) if channels else "TV Belum Tersedia"
            tv_bersih = format_nama_channel(tv_asli)
            
            if len(acara) < 5: continue
            
            # Konversi Jam
            sekarang = datetime.now(tz_wib)
            jam = int(waktu_match.group(1))
            menit = int(waktu_match.group(2))
            
            try:
                dt_event = sekarang.replace(hour=jam, minute=menit, second=0)
                jam_xmltv = dt_event.strftime('%Y%m%d%H%M%S %z')
            except:
                jam_xmltv = sekarang.strftime('%Y%m%d%H%M%S %z')
            
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
    tv = ET.Element('tv', {'generator-info-name': 'Auto EPG Smart Sports'})
    
    for item in data_jadwal:
        start_dt = datetime.strptime(item['start_xml'], '%Y%m%d%H%M%S %z')
        stop_dt = start_dt + timedelta(hours=2)
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
