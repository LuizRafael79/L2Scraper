from PyQt6.QtCore import QThread, pyqtSignal, QMutex
import time
import httpx
import asyncio
import re
from pathlib import Path
import json
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import threading
from asyncio import Semaphore

class SkillTreeScraperWorker(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int, str)
    stats_signal = pyqtSignal(dict)
    audit_signal = pyqtSignal(dict)
    finished_signal = pyqtSignal(dict)

    def __init__(self, site_type, class_slug, xml_folder, xml_class_name, config=None, max_workers=5):
        super().__init__()
        self.site_type = site_type.lower() 
        # Depois criamos o path baseado nele
        self.site_path = "Main" if self.site_type == "main" else "Essence"
        self.class_slug = class_slug
        self.xml_folder = xml_folder
        self.xml_class_name = xml_class_name 
        self.config = config
        self.is_running = True
        self.is_paused = False
        self.max_workers = max_workers

        self.stats_mutex = QMutex()
        self.log_mutex = QMutex()

        self.stats = {
            'total_categories': 0, 'total_skills': 0, 'skills_by_category': {},
            'start_time': time.time(), 'end_time': None, 'xml_class_id': None,
            'xml_total_skills': 0, 'total_removed_found': 0
        }

        self.base_url = "https://l2wiki.com"
        self.processed_count = 0
        self.count_lock = threading.Lock()

        # HEADERS MANTIDOS EXATAMENTE COMO VOCÊ TESTOU
        self.client = httpx.AsyncClient(
            http2=True, timeout=15.0,
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
        self.log_mutex.lock()
        try:
            self.log_signal.emit(message)
        finally:
            self.log_mutex.unlock()

    def run(self):
        try:
            asyncio.run(self.scrape_and_cleanup())
        except Exception as e:
            self.thread_safe_log(f"💥 Critical error: {e}")
            import traceback
            self.thread_safe_log(traceback.format_exc())
        finally:
            self.stats['end_time'] = time.time()
            self.stats['duration'] = self.stats['end_time'] - self.stats['start_time']
            self.finished_signal.emit(self.stats)

    async def scrape_and_cleanup(self):
        try:
            await self.scrape_skills_deep_async()
        finally:
            await self.client.aclose()

    async def scrape_skills_deep_async(self):
        output_dir = Path(f"output_skilltree/{self.site_type}")
        output_dir.mkdir(parents=True, exist_ok=True)
        class_dir = output_dir / self.class_slug
        class_dir.mkdir(exist_ok=True)

        xml_data = self.read_xml_skilltree()
        if xml_data:
            self.stats['xml_total_skills'] = xml_data['total_skills']
            self.thread_safe_log(f"📖 <b>XML Loaded:</b> {xml_data['total_skills']} skills found locally.")

        # 1. PEGAR ÍNDICES ACTIVE/PASSIVE
        types = ["active", "passive"]
        initial_tasks = []
        for t in types:
            url = f"{self.base_url}/{self.site_type}/skills/{self.class_slug}?mode=type&type={t}"
            async with self.semaphore:
                response = await self.client.get(url)
                if response.status_code == 200:
                    skills = self.extract_skills_from_html(response.text)
                    for cat, s_list in skills.items():
                        for s in s_list:
                            s['type'] = t.upper()
                            initial_tasks.append((cat, s))

        total_unique_base_skills = len(initial_tasks)
        self.thread_safe_log(f"📦 <b>Wiki:</b> Found {total_unique_base_skills} base skills. Starting Deep-Level Scraping...")

        # 2. WRAPPER PARA FEEDBACK E NAVEGAÇÃO POR NÍVEL
        async def wrapped_process(cat, skill_basic):
            # Obtém todos os níveis daquela skill
            levels_results = await self.process_all_levels(cat, skill_basic)
            
            # Feedback Visual
            first_lvl = levels_results[0]
            s_type = first_lvl.get('type', 'N/A')
            # Alterado para checar a nova lista de nomes raw
            has_removed = "removed_skills_names" in first_lvl and len(first_lvl["removed_skills_names"]) > 0
            
            color = "#4CAF50" if s_type == "ACTIVE" else "#2196F3"
            log_msg = f"<b style='color: {color};'>[{s_type}]</b> <b>Skill:</b> {first_lvl.get('name', 'Unknown')} - <b>Id:</b> {first_lvl['skill_id']} (Levels: {len(levels_results)})\n"
            log_msg += f"Learning this skill remove old skills? <b>\"{has_removed}\"</b>"
            
            if has_removed:
                log_msg += f"\n   ↳ 📝 Rows Found: {len(first_lvl['removed_skills_names'])}"
            
            self.thread_safe_log(log_msg + "\n" + "-"*50)
            
            self.processed_count += 1
            self.progress_signal.emit(self.processed_count, total_unique_base_skills, f"Processed: {first_lvl['skill_id']}")
            return cat, levels_results

        self.processed_count = 0
        all_results_grouped = await asyncio.gather(*(wrapped_process(c, s) for c, s in initial_tasks))

        # 3. FINALIZAR E CONSOLIDAR
        await self.finalize_data(all_results_grouped, xml_data, class_dir)

    async def process_all_levels(self, category, skill_basic):
        """Entra no Level 1, detecta a level-ui e busca os outros níveis"""
        first_url = f"{self.base_url}{skill_basic['href']}"
        
        async with self.semaphore:
            res = await self.client.get(first_url)
        
        if res.status_code != 200:
            return [skill_basic]

        soup = BeautifulSoup(res.text, 'html.parser')
        
        # Busca links extras na level-ui
        level_links = []
        level_ui = soup.find('div', class_='level-ui')
        if level_ui:
            level_wrap = level_ui.find('div', class_='level-wrap')
            if level_wrap:
                for a in level_wrap.find_all('a', href=True):
                    # Filtra para garantir que pegamos links de skills
                    if f"/{self.site_type.lower()}/skills/" in a['href']:
                        level_links.append(a['href'])
        
        if not level_links:
            # Processa apenas a página única
            data = await self.parse_skill_page(category, skill_basic, soup)
            return [data]
        
        # Se houver múltiplos níveis, processa todos
        tasks = []
        # O nível que já baixamos (soup inicial)
        tasks.append(self.parse_skill_page(category, skill_basic, soup))
        
        # Demais níveis (novas requisições)
        for href in level_links:
            if href == skill_basic['href']: continue
            new_skill_entry = skill_basic.copy()
            new_skill_entry['href'] = href
            tasks.append(self.process_single_level_request(category, new_skill_entry))

        return await asyncio.gather(*tasks)

    async def process_single_level_request(self, category, skill_data):
        url = f"{self.base_url}{skill_data['href']}"
        async with self.semaphore:
            res = await self.client.get(url)
        if res.status_code == 200:
            return await self.parse_skill_page(category, skill_data, BeautifulSoup(res.text, 'html.parser'))
        return skill_data

    async def parse_skill_page(self, category, skill_data, soup):
        """Extrai os dados de um nível específico"""
        # Sincroniza level pelo href
        match = re.search(r'_(\d+)_(\d+)\.html', skill_data['href'])
        if match:
            skill_data['level'] = match.group(1)
            skill_data['sublevel'] = match.group(2)

        name_h1 = soup.find('h1', class_='skill-desc')
        skill_data['name'] = name_h1.get_text(strip=True) if name_h1 else "Unknown"

        options = soup.find('div', class_='skill-options')
        if options:
            # Classes como lista real
            class_container = options.find('span', class_='classes-list')
            if class_container:
                classes = class_container.find_all(['a', 'span'])
                skill_data['full_class_name'] = [c.get_text(strip=True) for c in classes] if classes else [class_container.get_text(strip=True)]

            for row in options.find_all(['p', 'div'], class_='value-row'):
                label = row.find('span')
                if not label: continue
                l_text = label.get_text(strip=True).lower()
                v_text = row.get_text(strip=True).replace(label.get_text(strip=True), "").strip()
                
                if "character level" in l_text: 
                    skill_data['required_level'] = re.sub(r'\D', '', v_text)
                elif "sp consumption" in l_text: 
                    skill_data['sp_consumption'] = re.sub(r'\D', '', v_text)
                elif "auto get" in l_text and v_text.lower() == "yes": 
                    skill_data['autoget'] = True

                elif l_text.startswith('с'):  # Começa com 'с' cirílico
                    consume_items = []
                    # Pegar todos os <a> com /items/
                    for link in row.find_all('a', href=re.compile(r'/items/\d+')):
                        href = link.get('href', '')
                        item_id = re.search(r'/items/(\d+)', href).group(1)
                        
                        # Pegar o nome: é o segundo <span> dentro do <a>
                        spans = link.find_all('span')
                        item_name = spans[1].get_text(strip=True) if len(spans) > 1 else link.get_text(strip=True)
                        
                        consume_items.append({
                            'item_id': item_id,
                            'item_name': item_name
                        })
                    
                    if consume_items:
                        skill_data['consume_items'] = consume_items

        # ABA REMOVED SKILLS - Lógica de extração bruta por nomes
        removed_tab = soup.find('a', string=re.compile(r"Removed Skills", re.I))
        if removed_tab:
            id_full = skill_data['href'].split('/')[-1].replace('.html', '')
            rep_url = f"{self.base_url}/{self.site_type.lower()}/tabs/skills/replaceable/?id={id_full}&class={self.class_slug}&size=1000"
            async with self.semaphore:
                tab_res = await self.client.get(rep_url)
            
            if tab_res.status_code == 200:
                skill_data['removed_skills_names'] = [] 
                tab_soup = BeautifulSoup(tab_res.text, 'html.parser')
                rows = tab_soup.find_all('div', class_='list-row')
                
                for row in rows:
                    if 'head-row' in row.get('class', []): continue
                    name_div = row.find('div', class_='name')
                    if name_div:
                        # Extração bruta de cada linha da tabela
                        full_text = name_div.get_text(strip=True)
                        clean_name = re.sub(r'\(Lv\.\s*\d+\)\s*', '', full_text).strip()
                        if clean_name:
                            skill_data['removed_skills_names'].append(clean_name)
        return skill_data

    async def finalize_data(self, all_results_grouped, xml_data, class_dir):
        final_categories = {}
        all_removed_names = set()

        for cat, levels_list in all_results_grouped:
            if cat not in final_categories:
                final_categories[cat] = []
            
            final_categories[cat].extend(levels_list)
            for lvl in levels_list:
                if "removed_skills_names" in lvl:
                    all_removed_names.update(lvl["removed_skills_names"])

        output_json = {
            "class_slug": self.class_slug,
            "xml_class_name": self.xml_class_name,
            "removed_session": {
                "unique_names": sorted(list(all_removed_names)),
                "note": "Resolve names via skillname.dat in builder"
            },
            "categories": final_categories
        }

        with open(class_dir / "skills_deep_data.json", 'w', encoding='utf-8') as f:
            json.dump(output_json, f, indent=2, ensure_ascii=False)

        # Atualiza Stats finais
        self.stats['total_skills'] = sum(len(s) for s in final_categories.values())
        self.stats['total_removed_found'] = len(all_removed_names)
        self.stats['total_categories'] = len(final_categories)
        self.stats['skills_by_category'] = {cat: len(s) for cat, s in final_categories.items()}
        self.stats_signal.emit(self.stats)
        
        self.audit_signal.emit(output_json)

    def read_xml_skilltree(self):
        xml_path = Path(f"skilltree/{self.site_path}/{self.xml_folder}/{self.xml_class_name}.xml")
        if not xml_path.exists(): return None
        try:
            tree = ET.parse(xml_path)
            st = tree.getroot().find('.//skillTree[@type="classSkillTree"]')
            if st is None: return None
            skills = [s for s in st.findall('skill') if not s.get('getDualClassLevel')]
            return {'class_id': st.get('classId'), 'total_skills': len(skills)}
        except: return None

    def extract_skills_from_html(self, html):
        data = {}
        soup = BeautifulSoup(html, 'html.parser')
        for w in soup.find_all('div', class_='spoiler-wrapper'):
            t = w.find('div', class_='spoiler-title')
            c = w.find('div', class_='spoiler-content')
            if t and c:
                k = self.normalize_category_name(t.get_text(strip=True))
                skills = []
                for link in c.find_all('a', class_='icon'):
                    m = re.search(r'/(\d+)_(\d+)_(\d+)\.html', link.get('href', ''))
                    if m: skills.append({"skill_id": m.group(1), "level": m.group(2), "sublevel": m.group(3), "href": link.get('href')})
                if skills: data[k] = skills
        return data

    def normalize_category_name(self, n):
        return re.sub(r'\s+', '_', re.sub(r'[^\w\s]', '', n.lower().strip()))

    def stop(self): self.is_running = False