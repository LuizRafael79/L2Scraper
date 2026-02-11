from lxml import etree
from typing import Optional, TYPE_CHECKING
import re

if TYPE_CHECKING:
    from config.config_manager import ConfigManager
    from core.database import DatabaseManager
    from core.handlers.xml_handler import XMLHandler
    from core.handlers.scraper_handler import ScraperHandler
    from core.handlers.skill_handler import SkillHandler

class ItemHandler:
    def __init__(self, site_type, config, database, skill_handler, scraper_handler, xml_handler):
        self.site_type = site_type
        self.config = config
        self.database = database
        self.skill_handler = skill_handler
        self.scraper_handler = scraper_handler
        self.xml_handler = xml_handler

    def generate_fixed_xml(self, item_id: str, scraper_data: dict, site_type: str = 'main', xml_data: dict = None) -> str: #type: ignore
        """Gera XML corrigido usando LXML - APENAS EDITA, NÃO RECONSTRÓI"""
        try:
            scraping_info = scraper_data.get('scraping_info', {})
            item_type = scraping_info.get('item_type', '')
            has_skills = scraping_info.get('has_skills', False)
            skill_id = self.scraper_handler.get_skill_id(scraper_data)

            # ✅ SEMPRE partir do XML existente
            if xml_data is not None and xml_data.get('content'):
                base_elem = etree.fromstring(xml_data['content'].encode('utf-8'))
            else:
                # Fallback: criar mínimo
                base_elem = etree.Element('item', {'id': item_id, 'name': 'TODO', 'type': 'EtcItem'})
            
            print(f"\n🔧 Fixing item {item_id}: type={item_type}, has_skills={has_skills}, skill_id={skill_id}")

            # Determinar action correta
            if has_skills and skill_id:
                correct_action = item_type  # SKILL_REDUCE*
                correct_handler = 'ItemSkills'
            else:
                correct_action = 'PEEL'
                correct_handler = 'ExtractableItems'

            # ✅ Atualizar/adicionar tags básicas
            self._update_or_add_set_tag(base_elem, 'default_action', correct_action)
            self._update_or_add_set_tag(base_elem, 'handler', correct_handler)
            
            # ✅ LÓGICA CLARA: Skill vs Box
            if has_skills and skill_id:
                # ========== ITEM COM SKILL ==========
                
                # 1. REMOVER capsuled_items (incompatível com skills)
                for capsuled in base_elem.xpath('./capsuled_items'): #type: ignore
                    base_elem.remove(capsuled)
                    print(f"  ✅ Removido <capsuled_items>")
                
                # 2. REMOVER extractableCount (incompatível com skills)
                for tag_name in ['extractableCountMin', 'extractableCountMax']:
                    for old in base_elem.xpath(f"./set[@name='{tag_name}']"): #type: ignore
                        base_elem.remove(old)
                        print(f"  ✅ Removido {tag_name}")
                
                # 3. ADICIONAR/ATUALIZAR <skills>
                self._update_or_create_skills(base_elem, skill_id, site_type)
                print(f"  ✅ Configurado <skills> com skill {skill_id}")
                
            else:
                # ========== ITEM SEM SKILL (BOX) ==========
                
                # 1. REMOVER <skills> (incompatível com box)
                for skills in base_elem.xpath('./skills'): #type: ignore
                    base_elem.remove(skills)
                    print(f"  ✅ Removido <skills>")
                
                # 2. ADICIONAR/ATUALIZAR capsuled_items
                box_data = scraper_data.get('box_data', {})
                self._update_capsuled_items(base_elem, box_data, item_id)
                
                # 3. ADICIONAR/ATUALIZAR extractableCount
                self._update_extractable_count(base_elem, box_data)
            
            xml_str = etree.tostring(base_elem, encoding='unicode')
            print(f"  ✅ XML gerado ({len(xml_str)} chars)")
            return xml_str

        except Exception as e:
            print(f"❌ Erro: {e}")
            import traceback
            traceback.print_exc()
            return ""
    
    def edit_item_inplace(self, item_elem, scraper_data: dict, item_id: str, site_type: str):
        """
        Edita item in-place DIRETAMENTE no elemento (para batch processing)
        NÃO retorna string, modifica o elemento direto
        """
        scraping_info = scraper_data.get('scraping_info', {})
        item_type = scraping_info.get('item_type', '')
        has_skills = scraping_info.get('has_skills', False)
        skill_id = self.scraper_handler.get_skill_id(scraper_data)

        print(f"  📝 Editando item {item_id} in-place...")

        # Determinar action correta
        if has_skills and skill_id:
            correct_action = item_type
            correct_handler = 'ItemSkills'
        else:
            correct_action = 'PEEL'
            correct_handler = 'ExtractableItems'

        # Atualizar tags
        self._update_or_add_set_tag(item_elem, 'default_action', correct_action)
        self._update_or_add_set_tag(item_elem, 'handler', correct_handler)
        
        if has_skills and skill_id:
            # REMOVER capsuled_items
            for capsuled in item_elem.xpath('./capsuled_items'):
                item_elem.remove(capsuled)
            
            # REMOVER extractableCount
            for tag in item_elem.xpath("./set[@name='extractableCountMin']"):
                item_elem.remove(tag)
            for tag in item_elem.xpath("./set[@name='extractableCountMax']"):
                item_elem.remove(tag)
            
            # ADICIONAR skills
            self._update_or_create_skills(item_elem, skill_id, site_type)
            
        else:
            # REMOVER skills
            for skills in item_elem.xpath('./skills'):
                item_elem.remove(skills)
            
            # ADICIONAR capsuled_items
            box_data = scraper_data.get('box_data', {})
            self._update_capsuled_items(item_elem, box_data, item_id)
            self._update_extractable_count(item_elem, box_data)
        
        print(f"  ✅ Item {item_id} editado com sucesso")
    
    # ========== MÉTODOS PRIVADOS ==========
    
    def _update_or_add_set_tag(self, parent, name: str, value: str):
        """Atualiza ou adiciona tag <set>"""
        existing = parent.xpath(f"./set[@name='{name}']")
        
        if existing:
            existing[0].set('val', value)
        else:
            # Encontrar posição (antes de capsuled_items/skills)
            insert_pos = len(list(parent))
            for i, child in enumerate(parent):
                if hasattr(child, 'tag') and child.tag in ['capsuled_items', 'skills']:
                    insert_pos = i
                    break
            
            new_set = etree.Element('set', {'name': name, 'val': value})
            new_set.tail = '\n\t\t'
            parent.insert(insert_pos, new_set)
            print(f"DEBUG: {name} tail depois de insert = {repr(new_set.tail)}")  # ← Print aqui

            # ✅ FORÇA o tail de TUDO que vier depois
            for i in range(insert_pos + 1, len(parent)):
                child = parent[i]
                if hasattr(child, 'tag') and child.tag in ['capsuled_items', 'skills']:
                    child.tail = '\n\t'  # ← Esses ficam com 1 tab
                    break
                elif hasattr(child, 'tag') and child.tag == 'set':
                    child.tail = '\n\t\t'  # ← Outras sets ficam com 2 tabs
    
    def _update_or_create_skills(self, parent, skill_id: str, site_type: str, original_tail: str = '\n\t'):
        """Atualiza ou cria tag <skills>"""
        skills_elem = parent.find('skills')
        
        if skills_elem is None:
            skills_list = parent.xpath('./skills')
            if skills_list:
                skills_elem = skills_list[0]
        
        if skills_elem is not None:
            # Limpar skills existentes
            for child in list(skills_elem):
                skills_elem.remove(child)
        else:
            skills_elem = etree.SubElement(parent, 'skills')
            skills_elem.text = '\n\t\t\t'
            skills_elem.tail = original_tail
        
        # Buscar nome da skill
        if site_type == 'essence':
            skill_name_raw = self.database.SKILL_INDEX_ESSENCE.get(int(skill_id))
        else:
            skill_name_raw = self.database.SKILL_INDEX.get(int(skill_id))
        
        # Limpar nome
        skill_name = None
        if skill_name_raw:
            if isinstance(skill_name_raw, list):
                skill_name = skill_name_raw[0] if skill_name_raw else None
            else:
                skill_name = skill_name_raw
            
            if skill_name and isinstance(skill_name, str):
                skill_name = skill_name.strip()
                if skill_name.startswith("['") and skill_name.endswith("']"):
                    skill_name = skill_name[2:-2]
                elif skill_name.startswith('[') and skill_name.endswith(']'):
                    skill_name = skill_name[1:-1]
        
        # Adicionar skill
        skill = etree.SubElement(skills_elem, 'skill', {'id': skill_id, 'level': '1'})
        
        if skill_name:
            comment = etree.Comment(f' {skill_name} ')
            comment.tail = '\n\t\t'
            skill.tail = ' '
            skills_elem.append(skill)
            skills_elem.append(comment)
        else:
            skill.tail = '\n\t\t'
            skills_elem.append(skill)
        
        return True

    def _update_capsuled_items(self, parent, box_data: dict, container_item_id: str):
        """Atualiza capsuled_items"""
        old_capsuled = parent.find('./capsuled_items')
        original_tail = old_capsuled.tail if old_capsuled is not None else '\n\t'
        
        # Remover antigo
        for old in parent.xpath('./capsuled_items'):
            parent.remove(old)
        
        # ✅ FORÇA tail de TODAS as sets pra 2 tabs
        for child in parent:
            if hasattr(child, 'tag') and child.tag == 'set':
                child.tail = '\n\t\t'
        
        # Criar novo capsuled
        capsuled = etree.SubElement(parent, 'capsuled_items')
        capsuled.text = '\n\t\t\t'
        capsuled.tail = original_tail

        # Filtrar items
        def filter_items(items):
            return [item for item in items if str(item.get('id', '')) != str(container_item_id)]
        
        guaranteed = filter_items(box_data.get('guaranteed_items', []))
        random_items = filter_items(box_data.get('random_items', []))
        possible = filter_items(box_data.get('possible_items', []))
        
        print(f"📦 Container {container_item_id}: {len(guaranteed)} guaranteed, {len(random_items)} random, {len(possible)} possible")
        
        # Random → Possible → Guaranteed
        if random_items:
            chance = self.skill_handler.calculate_chance(len(random_items), False)
            for item in random_items:
                self._add_item_to_capsuled(capsuled, item, chance)
        
        if possible:
            chance = self.skill_handler.calculate_chance(len(possible), True)
            for item in possible:
                self._add_item_to_capsuled(capsuled, item, chance)
        
        for item in guaranteed:
            self._add_item_to_capsuled(capsuled, item, '100')

        # Ajustar tail do último elemento
        if len(capsuled) > 0:
            last_elem = capsuled[-1]
            if isinstance(last_elem, etree._Comment):
                last_elem.tail = '\n\t\t'
            else:
                last_elem.tail = '\n\t\t'
    
    def _add_item_to_capsuled(self, parent, item_data: dict, chance: str):
        """Adiciona item ao capsuled_items COM COMENTÁRIO"""
        item_id = str(item_data.get('id', ''))
        
        # Atributos
        attrs = {'id': item_id}
        
        # Count
        if 'min' in item_data and 'max' in item_data:
            attrs['min'] = str(item_data['min']).strip()
            attrs['max'] = str(item_data['max']).strip()
        else:
            count = str(item_data.get('count', '1')).strip()
            attrs['min'] = count
            attrs['max'] = count
        
        # Enchant
        enchant = item_data.get('enchant')
        min_ench = item_data.get('minEnchant')
        max_ench = item_data.get('maxEnchant')
        
        if min_ench is not None and max_ench is not None:
            attrs['minEnchant'] = str(min_ench)
            attrs['maxEnchant'] = str(max_ench)
        elif enchant is not None and str(enchant) not in ['0', '', 'None']:
            attrs['minEnchant'] = str(enchant)
            attrs['maxEnchant'] = str(enchant)
        
        # Chance
        attrs['chance'] = str(chance)
        
        # Criar elemento
        item_elem = parent.makeelement('item', attrs, nsmap={})
        
        # Comentário com nome
        item_name = item_data.get('name', '').strip()
        if item_name:
            enchant_val = attrs.get('minEnchant')
            if enchant_val and str(enchant_val) not in ['0', '']:
                comment_text = f" {item_name} "
            else:
                comment_text = f" {item_name} "
            
            item_elem.tail = ' '
            comment = etree.Comment(comment_text)
            comment.tail = '\n\t\t\t'
            
            parent.append(item_elem)
            parent.append(comment)
        else:
            item_elem.tail = '\n\t\t\t'
            parent.append(item_elem)
    
    def _update_extractable_count(self, parent, box_data: dict):
        """Atualiza extractableCount"""
        guaranteed = box_data.get('guaranteed_items', [])
        random_items = box_data.get('random_items', [])
        possible = box_data.get('possible_items', [])
        
        count = self._calculate_extractable_count(len(guaranteed), len(random_items), len(possible))

        # Remover antigas
        for old in parent.xpath("./set[@name='extractableCountMin']"):
            parent.remove(old)
        for old in parent.xpath("./set[@name='extractableCountMax']"):
            parent.remove(old)
        
        # Adicionar novas se necessário
        if count is not None:
            self._update_or_add_set_tag(parent, 'extractableCountMin', str(count))
            self._update_or_add_set_tag(parent, 'extractableCountMax', str(count))
    
    def _calculate_extractable_count(self, guaranteed_count: int, random_count: int, possible_count: int) -> Optional[int]:
        """Calcula extractableCount"""
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
    
    # ========== ALIASES PARA COMPATIBILIDADE ==========
    
    def _update_capsuled_items_lxml(self, parent, box_data: dict, container_item_id: str, original_tail: str = '\n\t'):
        """Alias para compatibilidade"""
        return self._update_capsuled_items(parent, box_data, container_item_id)
    
    def _update_extractable_count_lxml(self, parent, box_data: dict):
        """Alias para compatibilidade"""
        return self._update_extractable_count(parent, box_data)
    
    def _add_item_to_capsuled_lxml(self, parent, item_data: dict, chance: str):
        """Alias para compatibilidade"""
        return self._add_item_to_capsuled(parent, item_data, chance)