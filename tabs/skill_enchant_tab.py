from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QTextEdit, QHBoxLayout, QLineEdit, QLabel, QProgressBar, QComboBox
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from bs4 import BeautifulSoup
import asyncio
import re
from pathlib import Path
import json


class EnchantScraperWorker(QThread):
    """Worker thread para buscar dados de enchantment usando o motor existente"""
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(dict)
    
    def __init__(self, skill_id, skill_level, skill_sublevel, skill_class_slug, scraper_handler, site_type="essence"):
        super().__init__()
        self.skill_id = skill_id
        self.skill_level = skill_level
        self.skill_sublevel = skill_sublevel
        self.skill_class_slug = skill_class_slug
        self.scraper_handler = scraper_handler
        self.site_type = site_type
        
        class DummyConfig:
            def update_stats_from_files(self, site_type):
                return {}
            def get_site_stats(self, site_type):
                return {'total_in_dat': 0, 'extractable_count': 0}
        
        dummy_config = DummyConfig()
        self.scraper = scraper_handler(site_type, dummy_config, initial_stats={}, full_scan=False, max_workers=1)
        self.base_url = self.scraper.base_url
        
    def run(self):
        try:
            asyncio.run(self.fetch_enchantment_data())
        except Exception as e:
            self.log_signal.emit(f"❌ Erro crítico: {e}")
            self.finished_signal.emit({})
        finally:
            asyncio.run(self.scraper.client.aclose())
    
    async def fetch_enchantment_data(self):
        """Busca os dados de enchantment da skill usando o client HTTP existente"""
        
        # Monta a URL do enchantment usando o slug da classe
        url = f"{self.base_url}/{self.site_type}/tabs/skills/enchantment/?id={self.skill_id}_{self.skill_level}_{self.skill_sublevel}&class={self.skill_class_slug}"
        
        self.log_signal.emit(f"🔍 Buscando: {url}")
        
        try:
            async with self.scraper.semaphore:
                response = await self.scraper.client.get(url)
            
            if response.status_code != 200:
                self.log_signal.emit(f"❌ HTTP {response.status_code}")
                self.finished_signal.emit({})
                return
            
            if len(response.text) < 500:
                self.log_signal.emit(f"⚠️ Resposta muito curta ({len(response.text)} bytes)")
                self.finished_signal.emit({})
                return
            
            # Parse do HTML
            enchant_data = self.parse_enchantment_page(response.text)
            
            if enchant_data:
                self.log_signal.emit(f"✅ Encontrados {len(enchant_data)} níveis de enchant")
                self.finished_signal.emit(enchant_data)
            else:
                self.log_signal.emit("⚠️ Nenhum dado de enchantment encontrado")
                self.finished_signal.emit({})
                
        except Exception as e:
            self.log_signal.emit(f"❌ Erro na requisição: {e}")
            self.finished_signal.emit({})
    
    def parse_enchantment_page(self, html):
        """Extrai os dados de enchantment do HTML incluindo TODOS os custos - parser resiliente"""
        soup = BeautifulSoup(html, 'html.parser')
        enchant_data = {}
        
        # Verifica se a skill pode ser encantada
        description_tab = soup.find('div', class_='description-tab')
        if description_tab:
            desc_text = description_tab.get_text(strip=True)
            if "cannot be enchanted" in desc_text.lower():
                return {}
        
        # Busca a lista de enchantments
        skill_list = soup.find('div', class_='skill-ench-list')
        if not skill_list:
            return {}
        
        # Itera sobre cada linha de enchantment
        rows = skill_list.find_all('div', class_='list-row')
        
        for row in rows:
            try:
                if 'head-row' in row.get('class', []):
                    continue
                
                title_col = row.find('div', class_='title-col')
                if not title_col:
                    continue
                
                enchant_link = title_col.find('a')
                if not enchant_link:
                    continue
                
                enchant_text = enchant_link.get_text(strip=True)
                enchant_match = re.search(r'\+(\d+)', enchant_text)
                
                if not enchant_match:
                    continue
                
                enchant_level = int(enchant_match.group(1))
                
                # Extrai informações de custo - PARSER RESILIENTE
                cost_col = row.find('div', class_='cost-col')
                success_rate = None
                enchant_xp = None
                enchant_xp_on_fail = None
                required_items = []
                
                if cost_col:
                    # Taxa de sucesso - tenta múltiplos padrões
                    h5 = cost_col.find('h5')
                    if h5:
                        h5_text = h5.get_text(strip=True)
                        # Padrão: "General Enchantment (50%)"
                        rate_match = re.search(r'\((\d+)%\)', h5_text)
                        if rate_match:
                            success_rate = int(rate_match.group(1))
                    
                    # Enchant XP - busca TODOS os elementos com exp-cost
                    exp_costs = cost_col.find_all('p', class_='exp-cost')
                    for exp_cost in exp_costs:
                        try:
                            exp_span = exp_cost.find('span', {'data-desc': True})
                            if exp_span:
                                desc = exp_span.get('data-desc', '').lower()
                                
                                # Busca o valor dentro do span interno
                                value_span = exp_span.find('span', class_='light-font')
                                if value_span:
                                    exp_text = value_span.get_text(strip=True)
                                    # Remove × e espaços
                                    exp_match = re.search(r'×?\s*([\d\s]+)', exp_text)
                                    if exp_match:
                                        exp_value = int(exp_match.group(1).replace(' ', ''))
                                        
                                        if 'enchant xp' in desc or 'exp' in desc:
                                            enchant_xp = exp_value
                            
                            # Captura XP on fail (se houver)
                            failed_exp = exp_cost.find('span', class_='failed-exp')
                            if failed_exp:
                                fail_text = failed_exp.get('data-title', '')
                                fail_match = re.search(r'(\d[\d\s]*)', fail_text)
                                if fail_match:
                                    enchant_xp_on_fail = int(fail_match.group(1).replace(' ', ''))
                        except Exception as e:
                            continue
                    
                    # Itens necessários - CAPTURA TODOS
                    item_costs = cost_col.find_all('div', class_='item-cost')
                    for item_cost in item_costs:
                        try:
                            # Busca TODOS os links com /items/
                            item_links = item_cost.find_all('a', href=re.compile(r'/items/(\d+)\.html'))
                            
                            if not item_links:
                                continue
                            
                            # Pega o primeiro link para o ID (geralmente no ícone)
                            first_link = item_links[0]
                            href = first_link.get('href', '')
                            item_id_match = re.search(r'/items/(\d+)\.html', href)
                            
                            if not item_id_match:
                                continue
                            
                            item_id = item_id_match.group(1)
                            
                            # Busca o link com class="name" para nome e quantidade
                            name_link = item_cost.find('a', class_='name')
                            if name_link:
                                # Pega todos os spans
                                spans = name_link.find_all('span')
                                
                                item_name = None
                                quantity = None
                                
                                # Itera pelos spans para pegar nome e quantidade
                                for span in spans:
                                    span_text = span.get_text(strip=True)
                                    
                                    # Se tem × é quantidade
                                    if '×' in span_text or span.get('class') and 'light-font' in span.get('class'):
                                        quantity_match = re.search(r'×?\s*([\d\s]+)', span_text)
                                        if quantity_match:
                                            try:
                                                quantity = int(quantity_match.group(1).replace(' ', ''))
                                            except ValueError:
                                                pass
                                    # Senão é nome
                                    elif span_text and not item_name:
                                        item_name = span_text
                                
                                # Se não achou quantidade, assume 1
                                if quantity is None:
                                    quantity = 1
                                
                                # Se não achou nome, tenta pegar do alt da imagem
                                if not item_name:
                                    img = item_cost.find('img')
                                    if img and img.get('alt'):
                                        item_name = img.get('alt')
                                
                                # Se ainda não tem nome, usa o ID
                                if not item_name:
                                    item_name = f"Item {item_id}"
                                
                                required_items.append({
                                    'item_id': item_id,
                                    'name': item_name,
                                    'count': quantity
                                })
                        except Exception as e:
                            # Se falhar em algum item, continua para o próximo
                            continue
                
                # Extrai o sublevel do link
                href = enchant_link.get('href', '')
                sublevel_match = re.search(r'_(\d+)\.html', href)
                sublevel = int(sublevel_match.group(1)) if sublevel_match else 1000 + enchant_level
                
                # Monta os dados do enchant level
                enchant_data[enchant_level] = {
                    'sublevel': sublevel,
                    'success_rate': success_rate,
                    'enchant_level': enchant_level,
                    'enchant_xp': enchant_xp,
                    'enchant_xp_on_fail': enchant_xp_on_fail,
                    'required_items': required_items
                }
                
            except Exception as e:
                # Se falhar em algum nível, continua para o próximo
                continue
        
        return enchant_data


class SkillEnchantTab(QWidget):
    def __init__(self, config, database_manager, skilltree_tab, scraper_handler): # Adicione o handler aqui
        """
        Aba para gerar XML de skills encantadas e verificar com dados do site.
        @param database_manager Referência ao database para acessar dados do DAT.
        @param scraper_worker_class Classe ScraperWorker (opcional se só usar geração de XML)
        @param skill_tree_tab Referência à SkillTreeTab (opcional se só usar geração de XML)
        """
        super().__init__()
        self.config = config
        self.database = database_manager
        self.scraper_handler = scraper_handler
        self.skill_tree_tab = skilltree_tab
        self.current_worker = None
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Área de busca por skill específica
        search_layout = QHBoxLayout()
        
        search_layout.addWidget(QLabel("Skill ID:"))
        self.skill_id_input = QLineEdit()
        self.skill_id_input.setPlaceholderText("45401")
        self.skill_id_input.setFixedWidth(80)
        search_layout.addWidget(self.skill_id_input)
        
        search_layout.addWidget(QLabel("Level:"))
        self.skill_level_input = QLineEdit()
        self.skill_level_input.setPlaceholderText("2")
        self.skill_level_input.setFixedWidth(60)
        search_layout.addWidget(self.skill_level_input)
        
        search_layout.addWidget(QLabel("Sublevel:"))
        self.skill_sublevel_input = QLineEdit()
        self.skill_sublevel_input.setPlaceholderText("1001")
        self.skill_sublevel_input.setFixedWidth(80)
        search_layout.addWidget(self.skill_sublevel_input)
        
        # Dropdown para selecionar a classe
        search_layout.addWidget(QLabel("Class:"))
        self.class_combo = QComboBox()
        self.class_combo.setFixedWidth(200)
        self.populate_class_combo()
        search_layout.addWidget(self.class_combo)
        
        self.btn_check_site = QPushButton("Verificar no Site")
        self.btn_check_site.setFixedWidth(150)
        self.btn_check_site.clicked.connect(self.check_enchantment_on_site)
        search_layout.addWidget(self.btn_check_site)
        
        search_layout.addStretch()
        
        layout.addLayout(search_layout)
        
        # Barra de progresso
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Output window
        self.output_view = QTextEdit()
        self.output_view.setReadOnly(True)
        self.output_view.setPlaceholderText("O XML de skills encantadas aparecerá aqui...")
        self.output_view.setStyleSheet("""
            background-color: #1e1e1e; 
            color: #d4d4d4; 
            font-family: 'Consolas', monospace;
            font-size: 10pt;
        """)
        
        layout.addWidget(self.output_view, stretch=1)
        
        # Botões de ação
        buttons_layout = QHBoxLayout()
        
        self.btn_generate = QPushButton("Gerar XML do DAT")
        self.btn_generate.setFixedHeight(40)
        self.btn_generate.clicked.connect(self.generate_xml)
        buttons_layout.addWidget(self.btn_generate)
        
        self.btn_clear = QPushButton("Limpar")
        self.btn_clear.setFixedHeight(40)
        self.btn_clear.setFixedWidth(100)
        self.btn_clear.clicked.connect(self.output_view.clear)
        buttons_layout.addWidget(self.btn_clear)
        
        layout.addLayout(buttons_layout)

    def populate_class_combo(self):
        """Popula o combo box com as classes do skill tree"""
        self.class_combo.clear()
        
        # Só popula se tiver referência ao skill_tree_tab
        if not self.skill_tree_tab:
            self.class_combo.addItem("(Scraper não configurado)", "")
            self.btn_check_site.setEnabled(False)
            return
        
        # Pega o mapeamento de classes do skill tree
        if hasattr(self.skill_tree_tab, 'class_mapping_essence'):
            class_mapping = self.skill_tree_tab.class_mapping_essence
            
            # Adiciona todas as classes ordenadas
            for class_name, data in sorted(class_mapping.items()):
                slug = data.get('slug', '')
                self.class_combo.addItem(class_name, slug)
        else:
            self.output_view.append("⚠️ Mapeamento de classes não encontrado no SkillTreeTab")
            self.btn_check_site.setEnabled(False)

    def check_enchantment_on_site(self):
        """Verifica os dados de enchantment de uma skill específica no site"""
        
        # Verifica se o scraper está configurado
        if not self.scraper_handler or not self.skill_tree_tab:
            self.output_view.append("⚠️ Scraper não configurado. Esta funcionalidade não está disponível.")
            return
        
        skill_id = self.skill_id_input.text().strip()
        skill_level = self.skill_level_input.text().strip()
        skill_sublevel = self.skill_sublevel_input.text().strip()
        
        if not skill_id or not skill_level or not skill_sublevel:
            self.output_view.append("⚠️ Preencha todos os campos (ID, Level, Sublevel)")
            return
        
        if self.class_combo.currentIndex() == -1:
            self.output_view.append("⚠️ Selecione uma classe")
            return
        
        try:
            skill_id = int(skill_id)
            skill_level = int(skill_level)
            skill_sublevel = int(skill_sublevel)
        except ValueError:
            self.output_view.append("❌ IDs devem ser números")
            return
        
        # Pega o slug da classe selecionada
        skill_class_slug = self.class_combo.currentData()
        class_name = self.class_combo.currentText()
        
        if not skill_class_slug:
            self.output_view.append("⚠️ Classe inválida selecionada")
            return
        
        self.output_view.append(f"\n{'='*60}")
        self.output_view.append(f"🔍 Verificando Skill {skill_id}_{skill_level}_{skill_sublevel}")
        self.output_view.append(f"📚 Classe: {class_name} ({skill_class_slug})")
        self.output_view.append(f"{'='*60}\n")
        
        # Inicia o worker usando o slug da classe
        self.current_worker = EnchantScraperWorker(
            skill_id, 
            skill_level, 
            skill_sublevel,
            skill_class_slug,
            self.scraper_handler
        )
        self.current_worker.log_signal.connect(self.append_log)
        self.current_worker.finished_signal.connect(self.on_site_data_received)
        
        self.btn_check_site.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        
        self.current_worker.start()
    
    def on_site_data_received(self, enchant_data):
        """Callback quando dados do site são recebidos"""
        self.btn_check_site.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        if not enchant_data:
            self.output_view.append("\n⚠️ Nenhum dado de enchantment encontrado no site")
            return
        
        self.compare_with_dat(enchant_data)
    
    def compare_with_dat(self, site_data):
        """Compara dados do site com dados do DAT e exibe itens necessários"""
        skill_id = int(self.skill_id_input.text().strip())
        
        main_window = self.window()
        analyser = getattr(main_window, 'skill_analyser_tab', None)
        
        if not analyser or not hasattr(analyser, 'skill_name_parser'):
            self.output_view.append("\n⚠️ DAT não carregado no Analyser")
            return
        
        id_map = analyser.skill_name_parser.id_map
        
        if skill_id not in id_map:
            self.output_view.append(f"\n⚠️ Skill {skill_id} não encontrada no DAT")
            return
        
        # Coleta dados do DAT
        dat_enchants = {}
        for entry in id_map[skill_id]:
            try:
                sublevel = int(entry[3])
                if 1001 <= sublevel <= 1040:
                    enchant_level = sublevel - 1000
                    dat_enchants[enchant_level] = sublevel
            except (IndexError, ValueError):
                continue
        
        # Exibe comparação
        self.output_view.append("\n" + "="*60)
        self.output_view.append("📊 COMPARAÇÃO DAT vs SITE")
        self.output_view.append("="*60 + "\n")
        
        all_levels = sorted(set(list(site_data.keys()) + list(dat_enchants.keys())))
        
        self.output_view.append(f"{'Level':<8} {'DAT Sublevel':<15} {'Site Sublevel':<15} {'Taxa':<10} {'Status'}")
        self.output_view.append("-" * 70)
        
        for level in all_levels:
            dat_sub = dat_enchants.get(level, None)
            site_sub = site_data.get(level, {}).get('sublevel', None)
            success_rate = site_data.get(level, {}).get('success_rate', 'N/A')
            
            if dat_sub is None and site_sub is not None:
                status = "⚠️ Falta no DAT"
            elif dat_sub is not None and site_sub is None:
                status = "⚠️ Falta no Site"
            elif dat_sub == site_sub:
                status = "✅ OK"
            else:
                status = "❌ DIVERGENTE"
            
            dat_str = str(dat_sub) if dat_sub else "-"
            site_str = str(site_sub) if site_sub else "-"
            rate_str = f"{success_rate}%" if isinstance(success_rate, int) else str(success_rate)
            
            self.output_view.append(f"+{level:<7} {dat_str:<15} {site_str:<15} {rate_str:<10} {status}")
        
        # Resumo
        max_dat = max(dat_enchants.keys()) if dat_enchants else 0
        max_site = max(site_data.keys()) if site_data else 0
        
        self.output_view.append("\n" + "-" * 70)
        self.output_view.append(f"Max Enchant DAT:  +{max_dat}")
        self.output_view.append(f"Max Enchant Site: +{max_site}")
        
        if max_dat != max_site:
            self.output_view.append(f"\n⚠️ ATENÇÃO: Diferença detectada! DAT pode estar desatualizado.")
        else:
            self.output_view.append(f"\n✅ Máximos coincidem!")
        
        # Seção de itens necessários
        self.output_view.append("\n" + "="*60)
        self.output_view.append("💎 ITENS NECESSÁRIOS PARA ENCHANTMENT")
        self.output_view.append("="*60 + "\n")
        
        for level in sorted(site_data.keys()):
            data = site_data[level]
            self.output_view.append(f"\n🔸 Enchant +{level}:")
            
            if data.get('enchant_xp'):
                self.output_view.append(f"   📚 Enchant XP: {data['enchant_xp']:,}")
            
            if data.get('enchant_xp_on_fail'):
                self.output_view.append(f"   💔 XP ao falhar: {data['enchant_xp_on_fail']:,}")
            
            if data.get('required_items'):
                self.output_view.append(f"   📦 Itens necessários:")
                for item in data['required_items']:
                    self.output_view.append(f"      • {item['name']} (ID: {item['item_id']}) x{item['count']:,}")
            else:
                self.output_view.append(f"   📦 Nenhum item necessário")
            
            if data.get('success_rate'):
                self.output_view.append(f"   🎲 Taxa de sucesso: {data['success_rate']}%")

    def append_log(self, message):
        """Adiciona mensagem de log na saída"""
        self.output_view.append(message)

    def generate_xml(self):
        """Gera XML de skills encantadas a partir do DAT"""
        main_window = self.window()
        analyser = getattr(main_window, 'skill_analyser_tab', None)
        
        if not analyser or not hasattr(analyser, 'skill_name_parser'):
            self.output_view.setPlainText("❌ Erro: DAT não carregado no Analyser.")
            return

        id_map = analyser.skill_name_parser.id_map
        enchanted = {}

        for skill_id, entries in id_map.items():
            for data in entries:
                try:
                    sublevel = int(data[3])
                    
                    if 1001 <= sublevel <= 1040:
                        current_ench = sublevel - 1000
                        raw_name = str(data[1]).replace('[', '').replace(']', '')
                        
                        if skill_id not in enchanted or current_ench > enchanted[skill_id]['max']:
                            desc = data[4].lower() if len(data) > 4 else ""
                            star_level = 4 if "ff8000" in desc else 0
                            
                            enchanted[skill_id] = {
                                'max': current_ench,
                                'name': raw_name,
                                'stars': star_level
                            }
                except (IndexError, ValueError):
                    continue

        if not enchanted:
            self.output_view.setPlainText("⚠️ Nenhuma skill com enchantment (1001+) encontrada.")
            return

        xml_lines = ["\t<skills>"]
        for sid in sorted(enchanted.keys(), key=int):
            info = enchanted[sid]
            line = f'\t\t<skill id="{sid}" starLevel="{info["stars"]}" maxEnchantLevel="{info["max"]}" /> <!-- {info["name"]} -->'
            xml_lines.append(line)
            
        xml_lines.append("\t</skills>")
        
        self.output_view.setPlainText("\n".join(xml_lines))
        self.output_view.append(f"\n✅ Total de skills encantáveis: {len(enchanted)}")