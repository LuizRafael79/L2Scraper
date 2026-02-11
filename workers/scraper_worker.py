from PyQt6.QtCore import QThread, pyqtSignal, QMutex
import time
import httpx
import asyncio
import re
from pathlib import Path
import json
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from utils.scraping_stats import ScrapingStats
import threading
from asyncio import Semaphore


class ScraperWorker(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int, str)
    stats_signal = pyqtSignal(dict)
    site_stats_signal = pyqtSignal(dict)
    audit_signal = pyqtSignal(dict)

    def __init__(self, site_type, config, initial_stats=None, full_scan=False, max_workers=5):
        super().__init__()
        self.site_type = site_type
        self.config = config
        self.is_running = True
        self.is_paused = False
        self.failed_attempts = 0
        self.full_scan = full_scan
        self.max_workers = max_workers

        self.stats_mutex = QMutex()
        self.log_mutex = QMutex()

        self.stats = ScrapingStats()
        if initial_stats:
            for key, value in initial_stats.items():
                if hasattr(self.stats, key):
                    setattr(self.stats, key, value)

        self.base_url = "https://l2wiki.com"
        self.processed_count = 0
        self.count_lock = threading.Lock()

        self.client = httpx.AsyncClient(
            http2=True,
            timeout=15.0,
            limits=httpx.Limits(max_connections=16, max_keepalive_connections=7),
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://l2wiki.com/",
                "Origin": "https://l2wiki.com",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
            },
            follow_redirects=True,
            transport=httpx.AsyncHTTPTransport(retries=1)
      )

        self.semaphore = Semaphore(15)

    def thread_safe_log(self, message):
        #if any(x in message for x in ["Using local", "Skills"]):
            #return
        self.log_mutex.lock()
        try:
            self.log_signal.emit(message)
        finally:
            self.log_mutex.unlock()

    def needs_json_update(self, item_dir, item_id):
        json_file = item_dir / "data.json"
        
        if not json_file.exists():
            return True
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            needs_update = False
            
            if 'box_data' in data:
                for box_type in ['guaranteed_items', 'random_items', 'possible_items']:
                    for item in data['box_data'].get(box_type, []):
                        if 'enchant' not in item:
                            needs_update = True
                            self.thread_safe_log(f"    Missing 'enchant' in {box_type}")
                            break
                    if needs_update:
                        break
            
            if 'audit_data' not in data:
                needs_update = True
                self.thread_safe_log("    Missing 'audit_data'")
                
            scraping_info = data.get('scraping_info', {})
            if 'is_extractable' not in scraping_info:
                needs_update = True
                self.thread_safe_log("    Outdated scraping_info")

            if scraping_info.get('has_skills') and 'skill_data' not in data:
                needs_update = True
                self.thread_safe_log("    Missing 'skill_data'")

            return needs_update
            
        except Exception as e:
            self.thread_safe_log(f"    Error reading JSON: {e}")
            return True

    def run(self):
        self.thread_safe_log(f"Starting scraper with {self.max_workers} workers")
        
        self.thread_safe_log("Loading stats...")
        file_stats = self.config.update_stats_from_files(self.site_type)
        
        for key, value in file_stats.items():
            if hasattr(self.stats, key):
                setattr(self.stats, key, value)
        
        site_stats = self.config.get_site_stats(self.site_type)
        self.stats.total_items = site_stats['extractable_count']
    
        self.stats_signal.emit(self.stats.__dict__)
        self.site_stats_signal.emit(site_stats)
        self.thread_safe_log(f"{self.site_type} - Total in dat: {site_stats['total_in_dat']}, Extractable: {site_stats['extractable_count']}")
        self.thread_safe_log(f"Stats: {self.stats.successful_items} {self.stats.failed_items} {self.stats.not_found_items}")
        self.thread_safe_log(f"Using at {self.max_workers} simultaneous workers")

        try:
            asyncio.run(self.scrape_site_async())
        except Exception as e:
            self.thread_safe_log(f"Critical error: {e}")
        finally:
            asyncio.run(self.client.aclose())
            self.thread_safe_log("Scraping finalized")

    async def scrape_site_async(self):
        items = self.load_items()
        total_items = len(items)
        
        if total_items == 0:
            self.thread_safe_log("No items to proccess!")
            return
        
        self.thread_safe_log(f"Initializing scrape of {total_items} extractable items...")
        
        output_dir = Path(f"html_items_{self.site_type}")
        output_dir.mkdir(exist_ok=True)
        
        items_to_process = []
        for item_data in items:
            if not self.is_running:
                break
                
            item_id = item_data['id']
            item_dir = output_dir / item_id
            json_file = item_dir / "data.json"
            
            if json_file.exists():
                if not self.needs_json_update(item_dir, item_id):
                    self.thread_safe_log(f"JSON up-to-date: {item_id}")
                    continue
                else:
                    self.thread_safe_log(f"JSON needs update: {item_id}")
            else:
                self.thread_safe_log(f"First time processing: {item_id}")
            
            items_to_process.append(item_data)
        
        total_to_process = len(items_to_process)
        self.thread_safe_log(f"{total_to_process} items to process (skipped {total_items - total_to_process} updated items)")
        
        if total_to_process == 0:
            return
        
        self.processed_count = 0
        
        for i in range(0, total_to_process, 50):
            if not self.is_running:
                break
            batch = items_to_process[i:i+50]
            tasks = []
            for idx, item_data in enumerate(batch):
                tasks.append(self.process_item_with_retry_async(item_data, i + idx + 1, total_to_process))
            await asyncio.gather(*tasks)

    async def process_item_with_retry_async(self, item_data, current, total):
        item_id = item_data['id']
        retry_delay = 5
        max_retries = 10
        
        for retry_count in range(max_retries):
            if not self.is_running:
                return False, False
                    
            while self.is_paused:
                await asyncio.sleep(0.5)
                if not self.is_running:
                    return False, False
                    
            self.progress_signal.emit(current, total, f"Processando {item_id}")
            
            async with self.semaphore:
                success, is_found = await self.process_single_item_async(item_data)
            
            if success:
                self.failed_attempts = 0
                self.config.add_processed_item(self.site_type, item_id)
                with self.count_lock:
                    self.processed_count += 1
                self.thread_safe_log(f"Success {item_id} ({current}/{total})")
                self.recalculate_stats()
                return True, is_found
                
            elif not is_found:
                self.config.add_not_found_item(self.site_type, item_id)
                with self.count_lock:
                    self.processed_count += 1
                self.thread_safe_log(f"Not found: {item_id} ({current}/{total})")
                self.recalculate_stats()
                return False, False
                
            else:
                self.failed_attempts += 1
                retry_delay = min(300, 5 * (2 ** self.failed_attempts))
                self.thread_safe_log(f"  Temporary Fail, retry in {retry_delay}s... ({retry_count + 1}/{max_retries})")
                await asyncio.sleep(retry_delay)
                
        self.thread_safe_log(f"  Max retries reached for {item_id}")
        self.save_failed_item(item_id, "Max retries reached")
        self.config.add_failed_item(self.site_type, item_id)
        return False, True

    def recalculate_stats(self):
        file_stats = self.config.update_stats_from_files(self.site_type)
        self.stats_mutex.lock()
        try:
            for key, value in file_stats.items():
                if hasattr(self.stats, key):
                    setattr(self.stats, key, value)
            self.config.save_current_state(self.site_type, self.stats.__dict__)
            self.stats_signal.emit(self.stats.__dict__)
            self.config.save_stats(self.site_type, self.stats.__dict__)
        finally:
            self.stats_mutex.unlock()

    async def check_item_exists_on_site_async(self, item_id):
        try:
            main_url = f"{self.base_url}/{self.site_type}/tabs/items/?id={item_id}"
            resp = await self.client.get(main_url)
            
            if resp.status_code != 200:
                self.thread_safe_log(f"  ⚠️ Item {item_id}: HTTP {resp.status_code}")
                return False
            
            if len(resp.text) < 500:
                self.thread_safe_log(f"  ⚠️ Item {item_id}: Short response ({len(resp.text)} bytes) - possível erro de rede")
                return False
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            phantom_item = soup.find('div', class_="not-found-page")
            if phantom_item:
                self.thread_safe_log(f"  👻 Soft 404 - Phantom Item: {item_id}")
                return False
            
            main_menu = soup.find('nav', class_='outer-tabs-menu')
            if not main_menu:
                self.thread_safe_log(f"  ❌ Not a extractable item: {item_id}")
                return False
            
            tab_links = main_menu.find_all('a', href=re.compile(r'tabs/items/'))
            tab_wrapper = soup.find('div', class_='tab-wrapper')
            content_elements = soup.find_all(['div', 'p', 'table'], class_=re.compile(
                r'description|list-wrap|list-row|item-icon', re.I
            ))
            
            has_content = len(content_elements) > 0
            exists = main_menu and tab_links and tab_wrapper and has_content
            
            if not exists:
                self.thread_safe_log(f"  ❌ Extractable not found: {item_id}")
            
            return exists
            
        except Exception as e:
            self.thread_safe_log(f"  ⚠️ Error in verifying {item_id}: {e}")
            return False

    async def process_single_item_async(self, item_data):
        """Processa item com verificação de existência e contadores completos"""
        item_id = item_data['id']
        dat_action = item_data['default_action']
        
        output_dir = Path(f"html_items_{self.site_type}")
        item_dir = output_dir / item_id
        
        try:
            item_exists = await self.check_item_exists_on_site_async(item_id)
            
            if not item_exists:
                return False, False
            
            item_dir.mkdir(exist_ok=True)
            
            audit_data = {
                'default_action': {
                    'dat': dat_action,
                    'site': None,
                    'expected': None,
                    'found': None,
                    'status': 'pending'
                }
            }
            
            is_extractable = False
            box_data = {"guaranteed_items": [], "random_items": [], "possible_items": []}
            site_action = "NONE"
            has_skills = False
            skill_data = None
            
            urls = {
                "skills": f"{self.base_url}/{self.site_type}/tabs/items/skills/?id={item_id}&size=1000",
                "guaranteed": f"{self.base_url}/{self.site_type}/tabs/items/box/guaranteed/?id={item_id}&size=1000",
                "random": f"{self.base_url}/{self.site_type}/tabs/items/box/random/?id={item_id}&size=1000",
                "possible": f"{self.base_url}/{self.site_type}/tabs/items/box/possible/?id={item_id}&size=1000",
            }

            responses = await asyncio.gather(*[self.client.get(url) for url in urls.values()], return_exceptions=True)

            # SKILLS
            resp = responses[0]
            skills_html = resp.text if isinstance(resp, httpx.Response) and resp.status_code == 200 and len(resp.text) > 100 else None
            
            if skills_html:
                temp_skill_data = self.extract_skill_id(skills_html)
                
                if temp_skill_data:
                    (item_dir / "skills.html").write_text(skills_html, encoding="utf-8")
                    skill_data = temp_skill_data
                    has_skills = True
                    site_action = "SKILL_REDUCE"

            # BOXES
            for idx, box_type in enumerate(["guaranteed", "random", "possible"]):
                resp = responses[idx + 1]
                html = resp.text if isinstance(resp, httpx.Response) and resp.status_code == 200 and len(resp.text) > 100 else None
                
                if html:
                    items = self.extract_items_from_html(html, box_type, item_id)
                    
                    if items:
                        file_path = item_dir / f"box_{box_type}.html"
                        file_path.write_text(html, encoding="utf-8")
                        
                        box_data[f"{box_type}_items"] = items
                        is_extractable = True
                        
                        item_count = len(items)
                        if box_type == "guaranteed":
                            self.stats.total_guaranteed_items += item_count
                        elif box_type == "random":
                            self.stats.total_random_items += item_count
                        elif box_type == "possible":
                            self.stats.total_possible_items += item_count
                        
                        if not has_skills:
                            site_action = "PEEL"
            
            # CONTADORES SEPARADOS ITEM BOX vs SKILL BOX
            if is_extractable:
                guaranteed_local = len(box_data.get("guaranteed_items", []))
                random_local = len(box_data.get("random_items", []))
                possible_local = len(box_data.get("possible_items", []))
                
                if has_skills:
                    self.stats.skill_guaranteed += guaranteed_local
                    self.stats.skill_random += random_local
                    self.stats.skill_possible += possible_local
                else:
                    self.stats.item_guaranteed += guaranteed_local
                    self.stats.item_random += random_local
                    self.stats.item_possible += possible_local

            audit_data['default_action']['site'] = site_action
            
            if audit_data['default_action']['site'] != "NONE":
                audit_data['default_action']['expected'] = audit_data['default_action']['site']
            else:
                audit_data['default_action']['expected'] = "NONE"
            
            xml_action_found = self.check_xml_action(item_id, self.site_type)
            audit_data['default_action']['found'] = xml_action_found
            
            if audit_data['default_action']['expected'] == audit_data['default_action']['found']:
                audit_data['default_action']['status'] = 'consistent'
            elif audit_data['default_action']['found'] is None:
                audit_data['default_action']['status'] = 'missing'
            else:
                audit_data['default_action']['status'] = 'inconsistent'
            
            if not is_extractable:
                self.thread_safe_log(f"  🔍 Item exists, but not extractable: {item_id}")
                
                item_data_save = {
                    "item_id": item_id,
                    "scraping_info": {
                        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "is_extractable": False,
                        "site_type": self.site_type,
                        "has_skills": has_skills,
                        "skill_data": skill_data
                    },
                    "audit_data": audit_data
                }
                
                with open(item_dir / "data.json", 'w', encoding='utf-8') as f:
                    json.dump(item_data_save, f, indent=2, ensure_ascii=False)
                    
                self.emit_audit_data(item_id, audit_data, False)
                return True, True
            
            item_type = "SKILL_REDUCE" if has_skills else "PEEL"
            box_type_str = "Skill Box" if has_skills else "Item Box"
            
            self.thread_safe_log(f"  ✅ {box_type_str} - Status: {audit_data['default_action']['status']}")
            
            item_full_data = {
                "item_id": item_id,
                "skill_data": skill_data,
                "scraping_info": {
                    "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "item_type": item_type,
                    "has_skills": has_skills,
                    "is_extractable": True,
                    "site_type": self.site_type
                },
                "box_data": box_data,
                "audit_data": audit_data
            }
            
            with open(item_dir / "data.json", 'w', encoding='utf-8') as f:
                json.dump(item_full_data, f, indent=2, ensure_ascii=False)
            
            if has_skills:
                self.stats.skill_box_found += 1
            else:
                self.stats.item_box_found += 1
            
            self.emit_audit_data(item_id, audit_data, True)
            return True, True
                
        except Exception as e:
            self.thread_safe_log(f"  💥 Critical error in {item_id}: {e}")
            return False, True

    def check_xml_action(self, item_id, site_type):
        try:
            block_num = int(item_id) // 100
            block_start = block_num * 100
            block_end = block_start + 99
            
            if site_type == "essence":
                xml_file = Path(f"items_essence/{block_start:05d}-{block_end:05d}.xml")
            else:
                xml_file = Path(f"items/{block_start:05d}-{block_end:05d}.xml")
            
            if xml_file.exists():
                tree = ET.parse(xml_file)
                root = tree.getroot()
                item_elem = root.find(f".//item[@id='{item_id}'][@name][@type]")
                
                if item_elem is not None:
                    action_elem = item_elem.find("set[@name='default_action']")
                    if action_elem is not None:
                        return action_elem.get('val')
            
            return None
            
        except Exception:
            return None
    
    def emit_audit_data(self, item_id, audit_data, is_extractable):
        audit_result = {
            'item_id': item_id,
            'site_type': self.site_type,
            'dat_action': audit_data['default_action']['dat'],
            'site_action': audit_data['default_action']['site'],
            'expected_action': audit_data['default_action']['expected'],
            'xml_action': audit_data['default_action']['found'],
            'status': audit_data['default_action']['status'],
            'is_extractable': is_extractable
        }
        self.audit_signal.emit(audit_result)
    
    def extract_skill_id(self, html):
        try:
            soup = BeautifulSoup(html, 'html.parser')
            skill_links = soup.find_all('a', href=re.compile(r'skills/items/\d+'))
            for link in skill_links:
                href = link.get('href', '')
                match = re.search(r'/(\d{4,5})_(\d+)_(\d+)\.html', str(href))
                if match:
                    return {
                        "skill_id": match.group(1),
                        "skill_level": match.group(2),
                        "skill_sublevel": match.group(3)
                    }
            return None
        except:
            return None
    
    def extract_items_from_html(self, html, box_type, item_id):
        items = []
        try:
            if not html or len(html) < 100:
                return items
                
            soup = BeautifulSoup(html, 'html.parser')
            item_wraps = soup.find_all('div', class_='item-wrap')
            
            for item_wrap in item_wraps:
                if item_wrap.get('data-item'):
                    item_data = self.extract_single_item_data(item_wrap)
                    if item_data:
                        items.append(item_data)
            
            return items
        except:
            return items

    def extract_single_item_data(self, item_wrap):
        try:
            item_id = item_wrap.get('data-item', '')
            if not item_id:
                return None

            name_elem = item_wrap.select_one('.name a')
            if not name_elem:
                return None
            
            name_parts = []
            for content in name_elem.contents:
                if content.name is None:
                    text = content.strip()
                    if text:
                        name_parts.append(text)
                else:
                    span_text = content.get_text(strip=True)
                    if span_text:
                        name_parts.append(span_text)
            
            name_text = ' '.join(name_parts).strip()

            if not name_text or name_text.lower() == "not available":
                return None

            count_elem = item_wrap.select_one('.count-col div')
            count = count_elem.get_text(strip=True) if count_elem else "1"

            item = {
                "id": item_id,
                "name": name_text,
                "count": count
            }
            
            enchant_elem = name_elem.select_one('.enchant')
            if enchant_elem:
                enchant_value = enchant_elem.get_text(strip=True)
                if enchant_value.startswith('+'):
                    enchant_value = enchant_value[1:]
                try:
                    item["enchant"] = int(enchant_value)
                except ValueError:
                    item["enchant"] = enchant_value
            
            name_container = item_wrap.select_one('.name')
            if name_container and name_container.get('data-rank'):
                item["grade"] = name_container.get('data-rank')
            
            return item
        except:
            return None

    def save_failed_item(self, item_id: str, error: str):
        output_dir = Path(f"html_items_{self.site_type}")
        item_dir = output_dir / item_id
        item_dir.mkdir(exist_ok=True)
        
        error_data = {
            "item_id": item_id,
            "error": error,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "site_type": self.site_type
        }
        
        try:
            with open(item_dir / "failed.json", 'w', encoding='utf-8') as f:
                json.dump(error_data, f, indent=2, ensure_ascii=False)
        except:
            pass

    @staticmethod
    def find_ghost_items_in_xml(site_type="main"):
        """Encontra itens que estão no XML mas não existem no site"""
        ghost_items = []
        
        if site_type == "essence":
            xml_dir = Path("items_essence")
        else:
            xml_dir = Path("items")
        
        if not xml_dir.exists():
            return []
        
        for xml_file in xml_dir.glob("*.xml"):
            try:
                tree = ET.parse(xml_file)
                root = tree.getroot()
                
                for item_elem in root.findall('.//item'):
                    item_id = item_elem.get('id')
                    if item_id:
                        data_file = Path(f"html_items_{site_type}/{item_id}/data.json")
                        if data_file.exists():
                            with open(data_file, 'r') as f:
                                data = json.load(f)
                            
                            if data.get('scraping_info', {}).get('is_ghost_item'):
                                ghost_items.append(item_id)
                                
            except Exception as e:
                print(f"Erro em {xml_file}: {e}")
        
        return ghost_items

    def load_items(self):
        """🆕 Carrega items dos JSONs gerados"""
        try:
            return self.config.get_items_to_process(self.site_type, full_scan=self.full_scan)
        except FileNotFoundError as e:
            self.thread_safe_log(f"❌ {str(e)}")
            self.thread_safe_log("Please click 'Generate Items Lists' button first!")
            return []
    
    def stop(self):
        self.is_running = False
    
    def pause(self):
        self.is_paused = True
    
    def resume(self):
        self.is_paused = False