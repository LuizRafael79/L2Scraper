from PyQt6.QtCore import QThread, pyqtSignal
import logging
from lxml import etree
from pathlib import Path
from typing import Optional, List, cast
from core.handlers.scraper_handler import ScraperHandler
from core.handlers.xml_handler import XMLHandler

class ItemBuilderWorker(QThread):
    progress_signal = pyqtSignal(int, int, str)
    log_signal = pyqtSignal(str)
    items_loaded_signal = pyqtSignal(list)

    def __init__(self, config, site_type):
        super().__init__()
        self.config = config
        self.scraper_handler = ScraperHandler()
        self.xml_handler = XMLHandler()
        self.site_types = site_type or ["essence", "main"]  # Lista de sites para escanear
        self.is_running = True
        self.problems = []
        self.logger = logging.getLogger(__name__)

    def run(self):
        self.log_signal.emit(f"🔍 Scanning {', '.join(self.site_types).upper()} for extractable items...")
        self.problems = self.scan_all_items()
        self.items_loaded_signal.emit(self.problems)

    def normalize_action(self, action_value):
        """
        Normaliza action value removendo espaços em branco
        Ex: 'PEEL ' -> 'PEEL'
        """
        if action_value:
            return action_value.strip()
        return action_value

    def scan_all_items(self):
        """
        Escaneia TODOS os itens com default_action de extração na XML
        Retorna TODOS (ok + problemas) para visualização completa
        """
        all_items = []  # ✅ MUDA PARA RETORNAR TODOS
        total_items = 0
        skill_items = 0
        items_ok = 0
        items_with_problems = 0
        
        # Lista de actions que indicam item extraível (SEM ESPAÇOS)
        EXTRACTABLE_ACTIONS = [
            'PEEL',
            'SKILL_REDUCE',
            'SKILL_REDUCE_ON_SKILL_SUCCESS'
        ]

        self.log_signal.emit(f"🔍 Scanning XMLs for items with extractable actions...")

        for site_type in self.site_types:
            # Determinar pastas baseado no site_type
            if site_type == "essence":
                xml_folder = Path("items_essence")
                output_folder = Path("output_items_essence")
            else:
                xml_folder = Path("items_main")
                output_folder = Path("output_items_main")
            
            # Procurar todos os arquivos XML
            xml_files = list(xml_folder.glob("*.xml"))
            
            self.log_signal.emit(f"📦 {site_type.upper()}: Scanning {len(xml_files)} XML files...")
            
            items_found = 0
            
            for xml_file in xml_files:
                if not self.is_running:
                    break
                
                # Priorizar output se existir
                output_file = output_folder / xml_file.name
                file_to_scan = output_file if output_file.exists() else xml_file
                
                try:
                    parser = etree.XMLParser(remove_blank_text=False, remove_comments=False)
                    tree = etree.parse(str(file_to_scan), parser)
                    root = tree.getroot()
                    
                    xpath = ".//item[@id][@name][@type]/set[@name='default_action']/.."
                    all_items_with_action = root.xpath(xpath)
                    all_items_with_action = cast(List[etree._Element], all_items_with_action)
                    
                    for item_elem in all_items_with_action: #type_ignore
                        item_id = item_elem.get('id')
                        
                        # Pegar o valor do default_action E LIMPAR ESPAÇOS
                        action_elem = item_elem.find("set[@name='default_action']")
                        current_action = action_elem.get('val', '').strip() if action_elem is not None else False
                        
                        # Verificar se é uma action extraível
                        if current_action not in EXTRACTABLE_ACTIONS:
                            continue
                            
                        items_found += 1
                        
                        self.progress_signal.emit(
                            items_found, 
                            items_found + 100,  # Estimativa
                            f"Checking {item_id} ({site_type}) - action: {current_action}"
                        )
                        
                        # Carregar JSON do scraper
                        scraper_data = self.scraper_handler.load_scraper_data(item_id, site_type)
                        
                        if not scraper_data:
                            # ✅ ADICIONA MESMO SEM SCRAPER DATA
                            all_items.append({
                                'item_id': item_id,
                                'site_type': site_type,
                                'needs_fix': True,
                                'issues': ['❌ Dados do scraper não encontrados'],
                                'scraper_data': None,
                                'xml_data': None,
                                'has_scraper_data': False,
                                'has_xml': True,
                                'xml_correct': False,
                                'current_action': current_action,
                                'validation_status': 'INVALID'
                            })
                            items_with_problems += 1
                            total_items += 1
                            continue
                        
                        # Verificar o que o JSON ESPERA
                        scraping_info = scraper_data.get('scraping_info', {})
                        is_extractable = scraping_info.get('is_extractable', False)
                        has_skills = scraping_info.get('has_skills', False)
                        item_type = scraping_info.get('item_type', '')
                        skill_id = self.scraper_handler.get_skill_id(scraper_data)

                        # Determinar action e handler baseado em has_skills
                        if has_skills and skill_id:
                            expected_action = self.normalize_action(item_type)
                            expected_handler = 'ItemSkills'
                        else:
                            expected_action = 'PEEL'
                            expected_handler = 'ExtractableItems'
                        
                        # Se não é mais extraível no site, pular
                        if not is_extractable:
                            self.log_signal.emit(f"⏭️ Item {item_id} não é mais extraível no site - pulado")
                            continue
                        
                        # ✅ VALIDAR TODOS
                        result = self.validate_item_comprehensive_1to1(item_id, site_type)
                        result['current_action'] = current_action
                        result['expected_action'] = expected_action
                        result['expected_handler'] = expected_handler
                        result['site_type'] = site_type 
                        
                        # Adicionar issues específicas de comparação
                        if current_action != expected_action:
                            result['issues'].insert(0, f"⚠️ Action atual: '{current_action}', esperado: '{expected_action}'")
                            result['needs_fix'] = True
                        
                        # Verificar handler atual
                        handler_elem = item_elem.find("set[@name='handler']")
                        current_handler = handler_elem.get('val') if handler_elem is not None else None
                        
                        if current_handler != expected_handler:
                            result['issues'].insert(0, f"⚠️ Handler atual: {current_handler}, esperado: {expected_handler}")
                            result['needs_fix'] = True
                        
                        # ✅ ADICIONA TODOS (ok + problema)
                        all_items.append(result)
                        
                        if result['needs_fix']:
                            items_with_problems += 1
                        else:
                            items_ok += 1
                        
                        total_items += 1
                        
                        if has_skills and skill_id:
                            skill_items += 1
                            
                except Exception as e:
                    self.log_signal.emit(f"❌ Erro ao processar {file_to_scan}: {e}")
                    continue
            
            self.log_signal.emit(f"✅ {site_type.upper()}: {items_found} items com actions extraíveis encontrados")
        
        # ✅ LOG ATUALIZADO
        self.log_signal.emit(f"✅ Scan complete: {items_with_problems} items need fixing, {items_ok} items OK")
        self.log_signal.emit(f"📊 Total items: {total_items} | Items with skills: {skill_items}")

        return all_items  # ✅ RETORNA TODOS

    def get_skill_level(self, scraper_data: dict) -> Optional[int]:
        """Extrai skill_level dos dados do scraper"""
        if not scraper_data:
            return None
        
        skill_data = scraper_data.get('skill_data', {})
        if skill_data:
            skill_level = skill_data.get('skill_level')
            if skill_level is not None:
                return int(skill_level)
        
        return None
    
    def verify_item_consistency(self, item_id, site_type):
        """Verifica um item específico"""
        result = {
            'item_id': item_id,
            'site_type': site_type,
            'needs_fix': False,
            'issues': [],
            'scraper_data': None,
            'xml_data': None,
            'has_scraper_data': False,
            'has_xml': False,
            'xml_correct': False
        }
        
        # 1. Verificar dados do scraper
        scraper_data = self.scraper_handler.load_scraper_data(item_id, site_type)
        if scraper_data:
            result['scraper_data'] = scraper_data
            result['has_scraper_data'] = True
            
            # Se não é extraível, não precisa de fix no XML
            if not scraper_data.get('scraping_info', {}).get('is_extractable', False):
                result['issues'].append("⚠️ Item não tem conteúdo extraível")
                result['needs_fix'] = False
                return result
        else:
            result['issues'].append("❌ Dados do scraper não encontrados")
            result['needs_fix'] = True
            
        # 2. Verificar XML do item (agora passa site_type)
        xml_data = self.xml_handler.load_xml_data(item_id, site_type)
        if xml_data:
            result['xml_data'] = xml_data
            result['has_xml'] = True
            
            # Verificar se XML está correto
            xml_check = self.check_xml_consistency(xml_data, scraper_data)
            result['xml_correct'] = xml_check['is_correct']
            
            if not xml_check['is_correct']:
                result['issues'].extend(xml_check['issues'])
                result['needs_fix'] = True
        else:
            result['issues'].append("❌ XML não encontrado")
            result['needs_fix'] = True
            
        return result

    def check_xml_consistency(self, xml_data, scraper_data):
        """Verifica se o XML está consistente com os dados do scraper"""
        issues = []
        is_correct = True

        if not scraper_data:
            return {'is_correct': False, 'issues': ['Sem dados do scraper para comparar']}

        item_elem = xml_data['element']
        scraping_info = scraper_data.get('scraping_info', {})
        item_type = scraping_info.get('item_type', '')
        has_skills = scraping_info.get('has_skills', False)
        skill_id = self.scraper_handler.get_skill_id(scraper_data)

        # Determinar action esperada
        if has_skills and skill_id:
            expected_action = item_type  # SKILL_REDUCE*
        else:
            expected_action = 'PEEL'

        # Verificar action
        action_elem = item_elem.find("set[@name='default_action']")
        if action_elem is None:
            issues.append("❌ Falta 'default_action'")
            is_correct = False
        else:
            current_action = self.normalize_action(action_elem.get('val'))
            expected_action_normalized = self.normalize_action(expected_action)
            
            if current_action != expected_action_normalized:
                issues.append(f"❌ Action deveria ser '{expected_action}', está '{current_action}'")
                is_correct = False

        # Verificar handler
        handler_elem = item_elem.find("set[@name='handler']")
        expected_handler = 'ItemSkills' if (has_skills and skill_id) else 'ExtractableItems'
        if handler_elem is None:
            issues.append(f"❌ Falta 'handler' (esperado: {expected_handler})")
            is_correct = False
        elif handler_elem.get('val') != expected_handler:
            issues.append(f"❌ Handler deveria ser '{expected_handler}', está '{handler_elem.get('val')}'")
            is_correct = False

        # Verificar tags conflitantes
        skills_elem = item_elem.find('skills')
        capsuled_elem = item_elem.find('capsuled_items')

        if has_skills and skill_id:
            # Deve ter skills, não capsuled_items
            if skills_elem is None:
                issues.append("❌ Falta tag <skills>")
                is_correct = False
            if capsuled_elem is not None:
                issues.append("⚠️ Item com skills não deveria ter <capsuled_items>")
                is_correct = False
        else:
            # Deve ter capsuled_items, não skills
            if capsuled_elem is None:
                issues.append("❌ Falta 'capsuled_items'")
                is_correct = False
            if skills_elem is not None:
                issues.append("⚠️ Item sem skills não deveria ter tag <skills>")
                is_correct = False

        # Só continua verificando se é item normal (não skills)
        if not (has_skills and skill_id):
            # Analisar contadores
            box_data = scraper_data.get('box_data', {})
            guaranteed_count = len(box_data.get('guaranteed_items', []))
            random_count = len(box_data.get('random_items', []))
            possible_count = len(box_data.get('possible_items', []))

            # Verificar extractableCount
            expected_count = self.calculate_extractable_count_for_validation(
                guaranteed_count, random_count, possible_count
            )

            min_elem = item_elem.find("set[@name='extractableCountMin']")
            max_elem = item_elem.find("set[@name='extractableCountMax']")

            if expected_count is None:
                # Não deveria ter extractableCount
                if min_elem is not None or max_elem is not None:
                    issues.append("⚠️ Não deveria ter extractableCount (só guaranteed)")
                    is_correct = False
            else:
                # Deveria ter extractableCount
                if min_elem is None or max_elem is None:
                    issues.append(f"❌ Falta extractableCount (esperado: {expected_count})")
                    is_correct = False
                else:
                    min_val = min_elem.get('val')
                    max_val = max_elem.get('val')
                    if min_val != str(expected_count) or max_val != str(expected_count):
                        issues.append(f"❌ extractableCount incorreto: min={min_val}, max={max_val}, esperado={expected_count}")
                        is_correct = False

            # Verificar capsuled_items
            if capsuled_elem is not None:
                # Contar itens no XML
                xml_items = len(capsuled_elem.findall('item'))

                # Contar itens no scraper
                total_scraped = guaranteed_count + random_count + possible_count

                if xml_items != total_scraped:
                    issues.append(f"⚠️ XML tem {xml_items} itens, scraper encontrou {total_scraped}")
                    is_correct = False

                # Verificar chances (básico)
                self.validate_item_chances(capsuled_elem, box_data, issues)

                self.validate_enchant_attributes(capsuled_elem, item_elem, handler_elem, box_data, issues)

        if len(issues) > 0:
            is_correct = False

        return {'is_correct': is_correct, 'issues': issues}
    
    def validate_enchant_attributes(self, capsuled_elem, item_elem, handler_name, box_data: dict, issues: list):
        """
        Validação de enchants - CÓPIA EXATA DO MÉTODO ANTIGO
        Suporta Restoration global e outros handlers
        """
        expected_variants = {}
        max_enchant_found = 0
        
        all_scraper_items = (
            box_data.get('guaranteed_items', []) + 
            box_data.get('random_items', []) + 
            box_data.get('possible_items', [])
        )
        
        for item in all_scraper_items:
            item_id = str(item.get('id'))
            
            raw_enchant = item.get('enchant', 0)
            if raw_enchant in [None, '', 'None']:
                val_str = '0'
                val_int = 0
            else:
                val_str = str(raw_enchant)
                val_int = int(raw_enchant)
            
            if item_id not in expected_variants:
                expected_variants[item_id] = []
            expected_variants[item_id].append(val_str)
            
            if val_int > max_enchant_found:
                max_enchant_found = val_int

        # LÓGICA A: Restoration (Global Tag)
        if handler_name == 'Restoration':
            enchant_tag = item_elem.find("itemEnchantmentLevel")
            
            if enchant_tag is not None:
                xml_val = enchant_tag.text.strip() if (enchant_tag.text and enchant_tag.text.strip()) else '0'
            else:
                xml_val = '0'

            if max_enchant_found > 0:
                if enchant_tag is None:
                    issues.append(f"❌ (FIX NEEDED) Restoration +{max_enchant_found}, mas falta tag <itemEnchantmentLevel>")
                elif str(xml_val) != str(max_enchant_found):
                    issues.append(f"⚠️ itemEnchantmentLevel valor incorreto: XML='{xml_val}', Esperado='{max_enchant_found}'")
            else:
                if xml_val != '0':
                    issues.append(f"⚠️ Itens são +0, mas itemEnchantmentLevel está configurado para '{xml_val}'")

        # LÓGICA B: Outros Handlers (RestorationRandom, etc) - Por Item
        else:
            import copy
            remaining_variants = copy.deepcopy(expected_variants)

            for child_item in capsuled_elem if isinstance(capsuled_elem, list) else capsuled_elem.findall('item'):
                item_id = child_item.get('id')
                
                if item_id not in remaining_variants:
                    continue
                
                xml_min = child_item.get('minEnchant')
                xml_max = child_item.get('maxEnchant')
                
                if xml_min is None or xml_max is None:
                    current_xml_enchant = '0'
                else:
                    if xml_min != xml_max:
                        issues.append(f"⚠️ Item {item_id}: minEnchant ({xml_min}) != maxEnchant ({xml_max})")
                    current_xml_enchant = str(xml_min)

                if current_xml_enchant in remaining_variants[item_id]:
                    if current_xml_enchant != '0' and (xml_min is None or xml_max is None):
                        issues.append(f"❌ (FIX NEEDED) Item {item_id} é +{current_xml_enchant}, mas faltam atributos minEnchant/maxEnchant")
                    elif current_xml_enchant == '0' and xml_min is not None and xml_min != '0':
                        issues.append(f"⚠️ Item {item_id}: Deveria ser +0, mas tem minEnchant='{xml_min}'")

                    remaining_variants[item_id].remove(current_xml_enchant)
                else:
                    issues.append(f"⚠️ Item {item_id}: Enchant XML=+{current_xml_enchant} não esperado (ou duplicado). Esperados: {remaining_variants[item_id]}")

            for r_id, r_enchants in remaining_variants.items():
                if r_enchants:
                    issues.append(f"⚠️ Item {r_id}: Faltam itens no XML com enchants: {r_enchants}")

    def validate_enchant_attributes(self, capsuled_elem, item_elem, handler_name, box_data: dict, issues: list):
        """
        Validação de enchants - CÓPIA EXATA DO MÉTODO ANTIGO
        Suporta Restoration global e outros handlers
        """
        expected_variants = {}
        max_enchant_found = 0
        
        all_scraper_items = (
            box_data.get('guaranteed_items', []) + 
            box_data.get('random_items', []) + 
            box_data.get('possible_items', [])
        )
        
        for item in all_scraper_items:
            item_id = str(item.get('id'))
            
            raw_enchant = item.get('enchant', 0)
            if raw_enchant in [None, '', 'None']:
                val_str = '0'
                val_int = 0
            else:
                val_str = str(raw_enchant)
                val_int = int(raw_enchant)
            
            if item_id not in expected_variants:
                expected_variants[item_id] = []
            expected_variants[item_id].append(val_str)
            
            if val_int > max_enchant_found:
                max_enchant_found = val_int

        # LÓGICA A: Restoration (Global Tag)
        if handler_name and handler_name.get('val') == 'Restoration':
            enchant_tag = item_elem.find("itemEnchantmentLevel")
            
            if enchant_tag is not None:
                xml_val = enchant_tag.text.strip() if (enchant_tag.text and enchant_tag.text.strip()) else '0'
            else:
                xml_val = '0'

            if max_enchant_found > 0:
                if enchant_tag is None:
                    issues.append(f"❌ (FIX NEEDED) Restoration +{max_enchant_found}, mas falta tag <itemEnchantmentLevel>")
                elif str(xml_val) != str(max_enchant_found):
                    issues.append(f"⚠️ itemEnchantmentLevel valor incorreto: XML='{xml_val}', Esperado='{max_enchant_found}'")
            else:
                if xml_val != '0':
                    issues.append(f"⚠️ Itens são +0, mas itemEnchantmentLevel está configurado para '{xml_val}'")

        # LÓGICA B: Outros Handlers (RestorationRandom, etc) - Por Item
        else:
            import copy
            remaining_variants = copy.deepcopy(expected_variants)

            for child_item in capsuled_elem if isinstance(capsuled_elem, list) else capsuled_elem.findall('item'):
                item_id = child_item.get('id')
                
                if item_id not in remaining_variants:
                    continue
                
                xml_min = child_item.get('minEnchant')
                xml_max = child_item.get('maxEnchant')
                
                if xml_min is None or xml_max is None:
                    current_xml_enchant = '0'
                else:
                    if xml_min != xml_max:
                        issues.append(f"⚠️ Item {item_id}: minEnchant ({xml_min}) != maxEnchant ({xml_max})")
                    current_xml_enchant = str(xml_min)

                if current_xml_enchant in remaining_variants[item_id]:
                    if current_xml_enchant != '0' and (xml_min is None or xml_max is None):
                        issues.append(f"❌ (FIX NEEDED) Item {item_id} é +{current_xml_enchant}, mas faltam atributos minEnchant/maxEnchant")
                    elif current_xml_enchant == '0' and xml_min is not None and xml_min != '0':
                        issues.append(f"⚠️ Item {item_id}: Deveria ser +0, mas tem minEnchant='{xml_min}'")

                    remaining_variants[item_id].remove(current_xml_enchant)
                else:
                    issues.append(f"⚠️ Item {item_id}: Enchant XML=+{current_xml_enchant} não esperado (ou duplicado). Esperados: {remaining_variants[item_id]}")

            for r_id, r_enchants in remaining_variants.items():
                if r_enchants:
                    issues.append(f"⚠️ Item {r_id}: Faltam itens no XML com enchants: {r_enchants}")

    def validate_item_chances(self, capsuled_elem, box_data: dict, issues: list):
        """
        Validação de chances - CÓPIA DO MÉTODO ANTIGO
        """
        guaranteed_items = box_data.get('guaranteed_items', [])
        random_items = box_data.get('random_items', [])
        possible_items = box_data.get('possible_items', [])
        
        guaranteed_ids = {item['id']: '100' for item in guaranteed_items}
        
        random_chance = self.calculate_chance_for_validation(len(random_items), False)
        random_ids = {item['id']: random_chance for item in random_items}
        
        possible_chance = self.calculate_chance_for_validation(len(possible_items), True)
        possible_ids = {item['id']: possible_chance for item in possible_items}
        
        wrong_chances = []
        for item_elem in capsuled_elem.findall('item'):
            item_id = item_elem.get('id')
            xml_chance = item_elem.get('chance', '')
            
            expected_chance = None
            if item_id in guaranteed_ids:
                expected_chance = guaranteed_ids[item_id]
            elif item_id in random_ids:
                expected_chance = random_ids[item_id]
            elif item_id in possible_ids:
                expected_chance = possible_ids[item_id]
            
            if expected_chance and xml_chance != expected_chance:
                wrong_chances.append(f"Item {item_id}: chance={xml_chance}, esperado={expected_chance}")
        
        if wrong_chances:
            issues.append(f"⚠️ Chances incorretas: {', '.join(wrong_chances[:3])}")
    
    def calculate_extractable_count_for_validation(self, guaranteed_count: int, random_count: int, possible_count: int) -> Optional[int]:
        """Versão da função calculate_extractable_count para validação"""
        has_guaranteed = guaranteed_count > 0
        has_random = random_count > 0
        has_possible = possible_count > 0
        
        if has_guaranteed and not has_random and not has_possible:
            return None
        
        if not has_guaranteed and (has_random or has_possible) and not (has_random and has_possible):
            return 1
        
        if not has_guaranteed and has_random and has_possible:
            return 2
        
        if has_guaranteed and has_random and has_possible:
            return guaranteed_count + 2
        
        if has_guaranteed and (has_random or has_possible):
            return guaranteed_count + 1
        
        return None
    
    def calculate_chance_for_validation(self, item_count: int, is_possible: bool = False) -> str:
        """Versão da função calculate_chance para validação"""
        if item_count == 0:
            return "0"
        
        base = 85 if is_possible else 100
        
        if item_count == 1:
            return str(base)
        
        chance = base / item_count
        
        if chance == int(chance):
            return str(int(chance))
        
        return f"{chance:.6f}" 
    
    def validate_item_comprehensive_1to1(self, item_id, site_type):
        """
        Validação 1:1 COMPLETA - copia lógica do antigo check_xml_consistency
        mas compara CADA ITEM do JSON contra o XML de forma detalhada.
        Também valida Skills se tiver.
        """
        result = {
            'item_id': item_id,
            'site_type': site_type,
            'validation_status': 'VALID',
            'summary': {},
            'issues': [],  # ✅ COMPATÍVEL COM ProblemModel
            'scraper_data': None,
            'xml_data': None,
            'has_scraper_data': False,
            'has_xml': False,
            'xml_correct': False,
            'needs_fix': False
        }
        
        # 1. Carregar dados
        scraper_data = self.scraper_handler.load_scraper_data(item_id, site_type)
        xml_data = self.xml_handler.load_xml_data(item_id, site_type)
        
        if not scraper_data:
            result['issues'].append("❌ Dados do scraper não encontrados")
            result['needs_fix'] = True
            return result
        
        result['has_scraper_data'] = True
        result['scraper_data'] = scraper_data
        
        if not xml_data:
            result['issues'].append("❌ XML não encontrado")
            result['needs_fix'] = True
            return result
        
        result['has_xml'] = True
        result['xml_data'] = xml_data
        
        # 2. Se não é extraível, pula
        scraping_info = scraper_data.get('scraping_info', {})
        is_extractable = scraping_info.get('is_extractable', False)
        
        if not is_extractable:
            result['issues'].append("⚠️ Item não tem conteúdo extraível")
            result['xml_correct'] = True
            return result
        
        # 3. Executar validação completa (cópia do check_xml_consistency)
        item_elem = xml_data['element']
        
        # --- VALIDAR ACTION ---
        item_type = scraping_info.get('item_type', '')
        has_skills = scraping_info.get('has_skills', False)
        skill_id = self.scraper_handler.get_skill_id(scraper_data)
        
        if has_skills and skill_id:
            expected_action = item_type
        else:
            expected_action = 'PEEL'
        
        action_elem = item_elem.find("set[@name='default_action']")
        if action_elem is None:
            result['issues'].append("❌ Falta 'default_action'")
            result['needs_fix'] = True
        else:
            current_action = self.normalize_action(action_elem.get('val'))
            expected_action_normalized = self.normalize_action(expected_action)
            
            if current_action != expected_action_normalized:
                result['issues'].append(f"❌ Action deveria ser '{expected_action}', está '{current_action}'")
                result['needs_fix'] = True
        
        # --- VALIDAR HANDLER ---
        handler_elem = item_elem.find("set[@name='handler']")
        expected_handler = 'ItemSkills' if (has_skills and skill_id) else 'ExtractableItems'
        
        if handler_elem is None:
            result['issues'].append(f"❌ Falta 'handler' (esperado: {expected_handler})")
            result['needs_fix'] = True
        elif handler_elem.get('val') != expected_handler:
            result['issues'].append(f"❌ Handler deveria ser '{expected_handler}', está '{handler_elem.get('val')}'")
            result['needs_fix'] = True
        
        # --- VALIDAR TAGS CONFLITANTES ---
        skills_elem = item_elem.find('skills')
        capsuled_elem = item_elem.find('capsuled_items')
        
        if has_skills and skill_id:
            if skills_elem is None:
                result['issues'].append("❌ Falta tag <skills>")
                result['needs_fix'] = True
            if capsuled_elem is not None:
                result['issues'].append("⚠️ Item com skills não deveria ter <capsuled_items>")
        else:
            if capsuled_elem is None:
                result['issues'].append("❌ Falta 'capsuled_items'")
                result['needs_fix'] = True
            if skills_elem is not None:
                result['issues'].append("⚠️ Item sem skills não deveria ter tag <skills>")
        
        # --- SE TEM SKILLS, VALIDAR SKILL XML ---
        if has_skills and skill_id:
            self._validate_skill_xml_1to1(skill_id, scraper_data, site_type, result)
        
        # --- SE NÃO TEM SKILLS, VALIDAR ITEMS COMPLETO ---
        else:
            box_data = scraper_data.get('box_data', {})
            guaranteed_count = len(box_data.get('guaranteed_items', []))
            random_count = len(box_data.get('random_items', []))
            possible_count = len(box_data.get('possible_items', []))
            
            # --- VALIDAR EXTRACTABLE COUNT ---
            expected_count = self.calculate_extractable_count_for_validation(
                guaranteed_count, random_count, possible_count
            )
            
            min_elem = item_elem.find("set[@name='extractableCountMin']")
            max_elem = item_elem.find("set[@name='extractableCountMax']")
            
            if expected_count is None:
                if min_elem is not None or max_elem is not None:
                    result['issues'].append("⚠️ Não deveria ter extractableCount (só guaranteed)")
            else:
                if min_elem is None or max_elem is None:
                    result['issues'].append(f"❌ Falta extractableCount (esperado: {expected_count})")
                    result['needs_fix'] = True
                else:
                    min_val = min_elem.get('val')
                    max_val = max_elem.get('val')
                    if min_val != str(expected_count) or max_val != str(expected_count):
                        result['issues'].append(f"❌ extractableCount incorreto: min={min_val}, max={max_val}, esperado={expected_count}")
                        result['needs_fix'] = True
            
            # --- VALIDAR CAPSULED ITEMS 1:1 ---
            if capsuled_elem is not None:
                xml_items = capsuled_elem.findall('item')
                
                # Contar itens
                all_scraped = (
                    box_data.get('guaranteed_items', []) +
                    box_data.get('random_items', []) +
                    box_data.get('possible_items', [])
                )
                
                if len(xml_items) != len(all_scraped):
                    result['issues'].append(f"❌ Contagem: XML tem {len(xml_items)} itens, scraper tem {len(all_scraped)}")
                    result['needs_fix'] = True
                
                # --- VALIDAR CADA ITEM 1:1 COM ENCHANTS ---
                self._validate_capsuled_items_1to1(xml_items, all_scraped, item_elem, handler_elem, box_data, result)
                
                # --- VALIDAR CHANCES ---
                self.validate_item_chances(capsuled_elem, box_data, result['issues'])
        
        # 4. Compilar resultado
        result['xml_correct'] = len([i for i in result['issues'] if i.startswith('❌')]) == 0
        result['validation_status'] = 'INVALID' if result['needs_fix'] else 'VALID'
        
        result['summary'] = {
            'total_issues': len(result['issues']),
            'is_valid': result['validation_status'] == 'VALID'
        }
        
        return result
    
    def _validate_skill_xml_1to1(self, skill_id, scraper_data, site_type, result):
        """
        Valida skill XML 1:1 contra JSON
        - Restoration: <itemEnchantmentLevel> (tag única, global)
        - RestorationRandom: minEnchant/maxEnchant nos items (como capsuled)
        """
        try:
            # Carregar skill XML
            skill_xml_data = self.xml_handler.load_skill_xml_data(skill_id, site_type)
            
            if not skill_xml_data:
                result['issues'].append(f"❌ Skill XML {skill_id} não encontrado")
                result['needs_fix'] = True
                return
            
            # Parse skill XML
            skill_elem = etree.fromstring(skill_xml_data['content'].encode('utf-8'))
            effects = skill_elem.findall('.//effect')
            
            if not effects:
                result['issues'].append(f"❌ Skill {skill_id}: Nenhum efeito encontrado")
                result['needs_fix'] = True
                return
            
            box_data = scraper_data.get('box_data', {})
            guaranteed = box_data.get('guaranteed_items', [])
            random_items = box_data.get('random_items', [])
            possible = box_data.get('possible_items', [])
            
            # --- VALIDAR RESTORATION (GUARANTEED) ---
            restoration_effects = [e for e in effects if e.get('name') == 'Restoration']
            
            if guaranteed and not restoration_effects:
                result['issues'].append(f"❌ Skill {skill_id}: Tem {len(guaranteed)} guaranteed items mas nenhum <Restoration>")
                result['needs_fix'] = True
            elif not guaranteed and restoration_effects:
                result['issues'].append(f"❌ Skill {skill_id}: Tem <Restoration> mas JSON não tem guaranteed items")
                result['needs_fix'] = True
            
            # Validar cada Restoration
            matched_guaranteed = set()
            for rest_elem in restoration_effects:
                item_id_elem = rest_elem.find('.//itemId')
                item_count_elem = rest_elem.find('.//itemCount')
                enchant_elem = rest_elem.find('.//itemEnchantmentLevel')  # ✅ TAG ÚNICA
                
                if item_id_elem is None or item_id_elem.text is None:
                    result['issues'].append(f"❌ Skill {skill_id}: <Restoration> sem itemId")
                    result['needs_fix'] = True
                    continue
                
                xml_item_id = str(item_id_elem.text)
                xml_count = item_count_elem.text if item_count_elem is not None else '1'
                xml_enchant = enchant_elem.text if enchant_elem is not None else '0'
                
                # Procurar no JSON (com enchant)
                json_item = None
                for g_item in guaranteed:
                    if str(g_item.get('id', '')) == xml_item_id:
                        g_enchant = str(g_item.get('enchant', 0))
                        if g_enchant == xml_enchant:
                            json_item = g_item
                            break
                
                if json_item is None:
                    result['issues'].append(f"❌ Skill {skill_id}: Restoration itemId={xml_item_id}, +{xml_enchant} não está no JSON")
                    result['needs_fix'] = True
                else:
                    matched_guaranteed.add((xml_item_id, xml_enchant))
                    expected_count = str(json_item['count'])
                    if xml_count != expected_count:
                        result['issues'].append(f"⚠️ Skill {skill_id}: Restoration {xml_item_id} count={xml_count}, esperado={expected_count}")
            
            # Itens guaranteed não encontrados na skill
            for guar_item in guaranteed:
                guar_id = str(guar_item.get('id', ''))
                guar_enchant = str(guar_item.get('enchant', 0))
                if (guar_id, guar_enchant) not in matched_guaranteed:
                    result['issues'].append(f"❌ Skill {skill_id}: JSON tem guaranteed {guar_id}, +{guar_enchant} mas não está em <Restoration>")
                    result['needs_fix'] = True
            
            # --- VALIDAR RESTORATIONRANDOM (RANDOM + POSSIBLE) ---
            restoration_random = [e for e in effects if e.get('name') == 'RestorationRandom']
            
            all_random = random_items + possible
            
            if all_random and not restoration_random:
                result['issues'].append(f"❌ Skill {skill_id}: Tem {len(all_random)} random+possible items mas nenhum <RestorationRandom>")
                result['needs_fix'] = True
            elif not all_random and restoration_random:
                result['issues'].append(f"❌ Skill {skill_id}: Tem <RestorationRandom> mas JSON não tem random+possible items")
                result['needs_fix'] = True
            
            # Validar items dentro de RestorationRandom
            for rest_random in restoration_random:
                items_elem = rest_random.find('.//items')
                if items_elem is None:
                    result['issues'].append(f"❌ Skill {skill_id}: <RestorationRandom> sem <items>")
                    result['needs_fix'] = True
                    continue
                
                xml_items = items_elem.findall('.//item')
                
                # Construir mapa esperado (random + possible)
                expected_random_map = {}
                for item in all_random:
                    item_id = str(item.get('id', ''))
                    enchant = str(item.get('enchant', 0))
                    key = (item_id, enchant)
                    if key not in expected_random_map:
                        expected_random_map[key] = []
                    expected_random_map[key].append(item)
                
                # Validar contagem
                if len(xml_items) != len(all_random):
                    result['issues'].append(f"⚠️ Skill {skill_id}: RestorationRandom tem {len(xml_items)} items, JSON tem {len(all_random)}")
                
                # Validar cada item
                matched_random = set()
                for xml_idx, xml_item in enumerate(xml_items):
                    item_id_elem = xml_item.find('.//itemId')
                    if item_id_elem is None or item_id_elem.text is None:
                        result['issues'].append(f"❌ Skill {skill_id}: RestorationRandom item[{xml_idx}] sem itemId")
                        result['needs_fix'] = True
                        continue
                    
                    xml_item_id = str(item_id_elem.text)
                    xml_min_enchant = xml_item.get('minEnchant')
                    xml_max_enchant = xml_item.get('maxEnchant')
                    
                    # Determinar enchant (RestorationRandom usa minEnchant/maxEnchant como capsuled)
                    if xml_min_enchant is None and xml_max_enchant is None:
                        xml_enchant = '0'
                    else:
                        xml_enchant = str(xml_min_enchant) if xml_min_enchant else '0'
                    
                    key = (xml_item_id, xml_enchant)
                    
                    if key not in expected_random_map:
                        result['issues'].append(f"❌ Skill {skill_id}: RestorationRandom item[{xml_idx}] ID={xml_item_id}, +{xml_enchant} não está no JSON")
                        result['needs_fix'] = True
                    else:
                        matched_random.add(key)
                
                # Items não encontrados
                for key in expected_random_map:
                    if key not in matched_random:
                        item_id, enchant = key
                        result['issues'].append(f"❌ Skill {skill_id}: JSON tem item {item_id}, +{enchant} mas não está em <RestorationRandom>")
                        result['needs_fix'] = True
        
        except Exception as e:
            result['issues'].append(f"❌ Erro validando skill {skill_id}: {str(e)}")
            result['needs_fix'] = True
            print(f"Erro: {e}")
            import traceback
            traceback.print_exc()
    
    def _validate_capsuled_items_1to1(self, xml_items, all_scraped, item_elem, handler_elem, box_data, result):
        """
        Validação 1:1 de cada item no capsuled_items
        Compara com JSON item-por-item, levando em conta:
        - ID
        - Enchant (minEnchant/maxEnchant)
        - Count (min/max)
        """
        import copy
        
        # --- PREPARAR MAPA DE ITENS ESPERADOS ---
        expected_map = {}
        
        for json_item in all_scraped:
            item_id = str(json_item.get('id', ''))
            enchant = str(json_item.get('enchant', 0))
            count = str(json_item.get('count', '1'))
            
            key = (item_id, enchant)
            if key not in expected_map:
                expected_map[key] = []
            
            expected_map[key].append({
                'id': item_id,
                'enchant': enchant,
                'count': count,
                'matched': False
            })
        
        # --- VALIDAR CADA ITEM NO XML ---
        for xml_idx, xml_item in enumerate(xml_items):
            xml_id = xml_item.get('id', '')
            xml_min_enchant = xml_item.get('minEnchant')
            xml_max_enchant = xml_item.get('maxEnchant')
            
            # Determinar enchant
            if xml_min_enchant is None and xml_max_enchant is None:
                xml_enchant = '0'
            else:
                xml_enchant = str(xml_min_enchant) if xml_min_enchant else '0'
            
            key = (xml_id, xml_enchant)
            
            # Item esperado?
            if key not in expected_map:
                result['issues'].append(f"❌ XML item[{xml_idx}]: ID={xml_id}, +{xml_enchant} NÃO está no JSON")
                result['needs_fix'] = True
                continue
            
            # Procurar variante não matchada
            variant = None
            for v in expected_map[key]:
                if not v['matched']:
                    variant = v
                    v['matched'] = True
                    break
            
            if variant is None:
                result['issues'].append(f"❌ XML item[{xml_idx}]: ID={xml_id}, +{xml_enchant} DUPLICADA ou não no JSON")
                result['needs_fix'] = True
                continue
            
            # --- VALIDAR ATRIBUTOS DO ITEM ---
            # min/max vs count
            xml_min = xml_item.get('min')
            xml_max = xml_item.get('max')
            json_count = variant['count']
            
            if xml_min and xml_max:
                if xml_min != json_count or xml_max != json_count:
                    result['issues'].append(f"⚠️ XML item[{xml_idx}] ID={xml_id}: min/max='{xml_min}/{xml_max}', esperado count='{json_count}'")
            
            # minEnchant/maxEnchant
            if xml_enchant == '0':
                if xml_min_enchant is not None or xml_max_enchant is not None:
                    result['issues'].append(f"⚠️ XML item[{xml_idx}] ID={xml_id}: É +0, mas tem minEnchant/maxEnchant")
            else:
                if xml_min_enchant is None or xml_max_enchant is None:
                    result['issues'].append(f"❌ XML item[{xml_idx}] ID={xml_id}: É +{xml_enchant}, FALTAM minEnchant/maxEnchant")
                    result['needs_fix'] = True
                else:
                    if xml_min_enchant != xml_enchant or xml_max_enchant != xml_enchant:
                        result['issues'].append(f"❌ XML item[{xml_idx}] ID={xml_id}: minEnchant/maxEnchant incorretos, esperado +{xml_enchant}")
                        result['needs_fix'] = True
        
        # --- ITENS FALTANDO NO XML ---
        for key, variants in expected_map.items():
            unmatched = [v for v in variants if not v['matched']]
            if unmatched:
                item_id, enchant = key
                result['issues'].append(f"❌ JSON tem ID={item_id}, +{enchant}, MAS NÃO ESTÁ NO XML")
                result['needs_fix'] = True
        
        # --- VALIDAR ENCHANTS (lógica antiga - Restoration vs outros) ---
        self.validate_enchant_attributes(xml_items, item_elem, handler_elem.get('val') if handler_elem else None, box_data, result['issues'])

    def _validate_scraping_info_1to1(self, scraper_data, xml_data, result):
        """Valida scraping_info contra XML"""
        scraping_info = scraper_data.get('scraping_info', {})
        item_elem = xml_data['element']
        
        # Validar item_type vs default_action
        item_type = scraping_info.get('item_type', '')
        action_elem = item_elem.find("set[@name='default_action']")
        
        if action_elem is None:
            msg = f"❌ Falta 'default_action' no XML (JSON diz: {item_type})"
            result['all_issues'].append(msg)
            result['comparison']['scraping_info'].append(msg)
        else:
            xml_action = self.normalize_action(action_elem.get('val', ''))
            expected_action = self.normalize_action(item_type)
            if xml_action != expected_action:
                msg = f"❌ default_action: XML='{xml_action}', JSON='{item_type}'"
                result['all_issues'].append(msg)
                result['comparison']['scraping_info'].append(msg)
        
        # Validar has_skills
        has_skills = scraping_info.get('has_skills', False)
        
        skills_elem = item_elem.find('skills')
        if has_skills and skills_elem is None:
            msg = f"❌ JSON diz has_skills=true, XML não tem <skills>"
            result['all_issues'].append(msg)
            result['comparison']['scraping_info'].append(msg)
        elif not has_skills and skills_elem is not None:
            msg = f"❌ JSON diz has_skills=false, XML tem <skills>"
            result['all_issues'].append(msg)
            result['comparison']['scraping_info'].append(msg)


    def _validate_items_1to1_detailed(self, capsuled_elem, all_scraped_items, item_elem, result):
        """Validação item-por-item 1:1"""
        xml_items = capsuled_elem.findall('item')
        
        # --- VALIDAR CONTAGEM TOTAL ---
        if len(xml_items) != len(all_scraped_items):
            msg = f"❌ Contagem: XML tem {len(xml_items)} itens, JSON tem {len(all_scraped_items)}"
            result['all_issues'].append(msg)
            result['comparison']['items_count'].append(msg)
        
        # --- CONSTRUIR MAPA DE ITENS ESPERADOS ---
        expected_map = {}
        
        for json_item in all_scraped_items:
            item_id = str(json_item.get('id', ''))
            enchant = str(json_item.get('enchant', 0))
            count = str(json_item.get('count', '1'))
            name = json_item.get('name', '')
            
            key = (item_id, enchant)
            if key not in expected_map:
                expected_map[key] = []
            
            expected_map[key].append({
                'id': item_id,
                'enchant': enchant,
                'count': count,
                'name': name,
                'matched': False
            })
        
        # --- VALIDAR CADA ITEM NO XML ---
        for xml_idx, xml_item in enumerate(xml_items):
            xml_id = xml_item.get('id', '')
            xml_min_enchant = xml_item.get('minEnchant')
            xml_max_enchant = xml_item.get('maxEnchant')
            
            # Determinar enchant do XML
            if xml_min_enchant is None and xml_max_enchant is None:
                xml_enchant = '0'
            else:
                xml_enchant = str(xml_min_enchant) if xml_min_enchant else '0'
            
            key = (xml_id, xml_enchant)
            
            # --- ITEM ID + ENCHANT ESPERADO? ---
            if key not in expected_map:
                msg = f"❌ XML item[{xml_idx}]: ID={xml_id}, Enchant=+{xml_enchant} NÃO está no JSON"
                result['all_issues'].append(msg)
                result['comparison']['items_detail'].append(msg)
                continue
            
            # --- PROCURAR VARIANTE NÃO MATCHADA ---
            variant = None
            for v in expected_map[key]:
                if not v['matched']:
                    variant = v
                    v['matched'] = True
                    break
            
            if variant is None:
                msg = f"❌ XML item[{xml_idx}]: ID={xml_id}, +{xml_enchant} aparece DUPLICADA no XML (ou não no JSON)"
                result['all_issues'].append(msg)
                result['comparison']['items_detail'].append(msg)
                continue
            
            # --- VALIDAR ATRIBUTOS ---
            self._validate_item_attributes_1to1(xml_item, variant, xml_idx, result)
            self._validate_enchant_tags_1to1(xml_item, xml_enchant, xml_idx, result)
        
        # --- ITENS FALTANDO NO XML ---
        for key, variants in expected_map.items():
            unmatched = [v for v in variants if not v['matched']]
            if unmatched:
                for v in unmatched:
                    msg = f"❌ JSON tem item ID={v['id']}, +{v['enchant']}, MAS NÃO ESTÁ NO XML"
                    result['all_issues'].append(msg)
                    result['comparison']['items_detail'].append(msg)


    def _validate_item_attributes_1to1(self, xml_item, json_variant, xml_idx, result):
        """Valida count (min/max) entre XML e JSON"""
        xml_id = xml_item.get('id', '')
        
        # --- MIN/MAX (= COUNT no JSON) ---
        xml_min = xml_item.get('min')
        xml_max = xml_item.get('max')
        json_count = json_variant['count']
        
        # Se tem min/max no XML, deve bater com count do JSON
        if xml_min is not None and xml_max is not None:
            if xml_min != json_count or xml_max != json_count:
                msg = f"⚠️ XML item[{xml_idx}] ID={xml_id}: min/max XML='{xml_min}/{xml_max}', JSON count='{json_count}'"
                result['all_issues'].append(msg)
                result['comparison']['items_detail'].append(msg)

    def _validate_enchant_tags_1to1(self, xml_item, expected_enchant, xml_idx, result):
        """Valida se os atributos minEnchant/maxEnchant estão corretos"""
        xml_id = xml_item.get('id', '')
        xml_min = xml_item.get('minEnchant')
        xml_max = xml_item.get('maxEnchant')
        
        # Se é +0, não deveria ter os atributos
        if expected_enchant == '0':
            if xml_min is not None or xml_max is not None:
                msg = f"⚠️ XML item[{xml_idx}] ID={xml_id}: É +0, mas tem minEnchant={xml_min}, maxEnchant={xml_max}"
                result['all_issues'].append(msg)
                result['comparison']['enchants_mapping'].append(msg)
        
        # Se é > 0, PRECISA ter os atributos e devem ser iguais
        else:
            if xml_min is None or xml_max is None:
                msg = f"❌ XML item[{xml_idx}] ID={xml_id}: É +{expected_enchant}, FALTAM atributos minEnchant/maxEnchant"
                result['all_issues'].append(msg)
                result['comparison']['enchants_mapping'].append(msg)
            else:
                if xml_min != expected_enchant or xml_max != expected_enchant:
                    msg = f"❌ XML item[{xml_idx}] ID={xml_id}: Enchant XML=+{xml_min}, JSON=+{expected_enchant}"
                    result['all_issues'].append(msg)
                    result['comparison']['enchants_mapping'].append(msg)
                
                if xml_min != xml_max:
                    msg = f"⚠️ XML item[{xml_idx}] ID={xml_id}: minEnchant={xml_min} != maxEnchant={xml_max}"
                    result['all_issues'].append(msg)
                    result['comparison']['enchants_mapping'].append(msg)
