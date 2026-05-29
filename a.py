from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pytz
import xml.etree.ElementTree as ET
from xml.dom import minidom

tz_wib = pytz.timezone('Asia/Jakarta')

URLS = {
    'Soccer': 'https://www.livesportsontv.com/sport/soccer',
    'Racing': 'https://www.livesportsontv.com/sport/motorsport'
}

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
        
        for kategori, url in URLS.items():
            print(f"Membuka {kategori}...")
            try:
                # PERBAIKAN: Hapus networkidle, ubah jadi domcontentloaded
                # Perpanjang waktu tunggu maksimal jadi 60 detik (60000ms)
                page.goto(url, timeout=60000, wait_until='domcontentloaded')
                
                # Paksa bot menunggu 5 detik agar JavaScript merender jadwal TV
                page.wait_for_timeout(5000) 
            except Exception as e:
                print(f"Timeout atau gagal memuat {url}: {e}")
                continue # Kalau satu URL error, lanjut ke URL berikutnya, jangan berhenti total

            html = page.content()
            soup = BeautifulSoup(html, 'html.parser')
            
            matches = soup.find_all('div', class_=lambda c: c and ('match' in c.lower() or 'event' in c.lower()))
            
            for match in matches:
                acara_elem = match.find(class_=lambda c: c and 'title' in c.lower())
                waktu_elem = match.find(class_=lambda c: c and 'time' in c.lower())
                channel_elem = match.find(class_=lambda c: c and 'channel' in c.lower())
                status_elem = match.find(class_=lambda c: c and 'live' in c.lower())
                
                if not channel_elem or not acara_elem: continue
                    
                acara = acara_elem.get_text(strip=True)
                tv_asli = channel_elem.get_text(strip=True)
                status_teks = status_elem.get_text(strip=True) if status_elem else ''
                waktu_teks = waktu_elem.get_text(strip=True) if waktu_elem else ''
                
                is_live = 'live' in status_teks.lower() or 'live' in match.get('class', [])
                if not is_live: continue
                    
                kategori_epg = 'Grand Prix' if kategori == 'Racing' else 'Olahraga'
                tv_bersih = format_nama_channel(tv_asli)
                
                sekarang = datetime.now(tz_wib)
                jam_xmltv = sekarang.strftime('%Y%m%d%H%M%S %z')
                
                if waktu_teks:
                    try:
                        jam, menit = map(int, waktu_teks.split(':'))
                        dt_event = sekarang.replace(hour=jam, minute=menit, second=0)
                        jam_xmltv = dt_event.strftime('%Y%m%d%H%M%S %z')
                    except: pass
                
                jadwal_ekstrak.append({
                    'acara': acara,
                    'kategori': kategori_epg,
                    'status': 'Sedang Tayang',
                    'tv': tv_bersih,
                    'start_xml': jam_xmltv
                })
        browser.close()
    return jadwal_ekstrak

def generate_xmltv(data_jadwal):
    tv = ET.Element('tv', {'generator-info-name': 'Auto EPG'})
    
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
    if data:
        generate_xmltv(data)
