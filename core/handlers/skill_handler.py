from lxml import etree
from pathlib import Path
from typing import Optional, List, Dict, TYPE_CHECKING
import re
import json
from models.problem_model import ProblemModel

if TYPE_CHECKING:
    from core.handlers.xml_handler import XMLHandler
    from core.handlers.scraper_handler import ScraperHandler
    from core.database import DatabaseManager

class SkillHandler:
    def __init__(self, xml_handler: "XMLHandler", scraper_handler: "ScraperHandler", database: "DatabaseManager"):
        self.xml_handler = xml_handler
        self.scraper_handler = scraper_handler
        self.database = database

    def calculate_chance(self, item_count: int, is_possible: bool = False) -> str:
        """Calcula chance conforme regras L2J."""
        if item_count == 0:
            return "0"
        
        base = 85 if is_possible else 100
        
        if item_count == 1:
            return str(base)
        
        chance = base / item_count
        
        if chance == int(chance):
            return str(int(chance))
        
        return f"{chance:.6f}"

    def generate_fixed_skill_xml(self, skill_id: str, scraper_data: dict, site_type: str = 'main') -> Optional[str]:
        """Gera XML corrigido para skills COM tails e comentários corretos"""
        try:
            skill_xml_data = self.xml_handler.load_skill_xml_data(skill_id, site_type)
            if not skill_xml_data:
                print(f"❌ Skill {skill_id} não encontrada")
                return None
            
            skill_elem = etree.fromstring(skill_xml_data['content'].encode('utf-8'))
            
            if not skill_elem.text or not skill_elem.text.strip():
                skill_elem.text = '\n\t\t'
                skill_elem.tail = '\n\t'

            item_id = scraper_data.get('item_id')
            if not item_id:
                print(f"❌ item_id não encontrado em scraper_data")
                return None
            
            # Garantir tags obrigatórias
            self._ensure_mandatory_skill_tags(skill_elem)
            
            box_data = scraper_data.get('box_data', {})
            
            # Filtrar container
            def filter_container(items):
                return [item for item in items if str(item.get('id', '')) != str(item_id)]
            
            guaranteed = filter_container(box_data.get('guaranteed_items', []))
            random_items = filter_container(box_data.get('random_items', []))
            possible = filter_container(box_data.get('possible_items', []))
            
            has_restoration_random = bool(random_items or possible)
            
            # ✅ LIMPAR TUDO itemConsume
            for tag in ['itemConsumeCount', 'itemConsumeId']:
                for old in skill_elem.findall(tag):
                    skill_elem.remove(old)
            
            # ✅ LIMPAR comentários órfãos (só os de itemConsume)
            for child in list(skill_elem):
                if isinstance(child, etree._Comment):
                    prev = child.getprevious()
                    if prev is None or not hasattr(prev, 'tag') or prev.tag not in ['itemConsumeId', 'isMagic']:
                        next_elem = child.getnext()
                        if next_elem is None or not hasattr(next_elem, 'tag') or next_elem.tag not in ['itemConsumeCount']:
                            skill_elem.remove(child)
            
            # ✅ ADICIONAR itemConsume se necessário
            if has_restoration_random:
                item_name = self.get_item_name_from_item_id(item_id, site_type) or f"Item {item_id}"
                
                insert_index = self._find_insert_position(skill_elem, ['magicCriticalRate', 'conditions'])
                
                # itemConsumeCount
                consume_count = etree.Element('itemConsumeCount')
                consume_count.text = '1'
                consume_count.tail = '\n\t\t'
                skill_elem.insert(insert_index, consume_count)
                insert_index += 1
                
                # itemConsumeId COM COMENTÁRIO INLINE
                consume_id = etree.Element('itemConsumeId')
                consume_id.text = str(item_id)
                consume_id.tail = ' '  # ✅ Espaço para comentário
                skill_elem.insert(insert_index, consume_id)
                
                # ✅ Comentário INLINE (não como próximo elemento, mas como irmão)
                comment = etree.Comment(f' {item_name} ')
                comment.tail = '\n\t\t'
                skill_elem.insert(insert_index + 1, comment)
            
            # ✅ REMOVER <effects> antigo COMPLETAMENTE
            effects_elem = skill_elem.find('effects')
            if effects_elem is not None:
                skill_elem.remove(effects_elem)
            
            # ✅ CRIAR <effects> NOVO do zero
            effects_elem = etree.Element('effects')
            effects_elem.text = '\n\t\t'
            effects_elem.tail = '\n\t'
            
            # ✅ RestorationRandom
            if has_restoration_random:
                random_effect = etree.SubElement(effects_elem, 'effect', {'name': 'RestorationRandom'})
                random_effect.text = '\n\t\t\t'
                random_effect.tail = '\n\t\t'
                
                items_container = etree.SubElement(random_effect, 'items')
                items_container.text = '\n\t\t\t\t'
                items_container.tail = '\n\t\t'
                
                # Random items
                random_chance = self.calculate_chance(len(random_items), is_possible=False)
                for item in random_items:
                    self._add_restoration_random_item(items_container, item, random_chance)
                
                # Possible items
                possible_chance = self.calculate_chance(len(possible), is_possible=True)
                for item in possible:
                    self._add_restoration_random_item(items_container, item, possible_chance)
                
                if len(items_container) > 0:
                    items_container[-1].tail = '\n\t\t\t'
            
            # ✅ Restoration (Guaranteed) - UM effect POR ITEM
            for item in guaranteed:
                restoration = etree.SubElement(effects_elem, 'effect', {'name': 'Restoration'})
                restoration.text = '\n\t\t\t'
                restoration.tail = '\n\t\t'
                
                # itemId com comentário inline
                item_id_elem = etree.SubElement(restoration, 'itemId')
                item_id_elem.text = str(item['id'])
                item_id_elem.tail = ' '
                
                item_name = item.get('name', f"Item {item['id']}")
                comment = etree.Comment(f' {item_name} ')
                comment.tail = '\n\t\t\t'
                restoration.append(comment)
                
                # itemCount
                item_count_elem = etree.SubElement(restoration, 'itemCount')
                item_count_elem.text = str(item['count']).replace(' ', '')
                item_count_elem.tail = '\n\t\t\t'
                
                # Enchant (opcional)
                enchant = item.get('enchant')
                if enchant is not None and str(enchant) not in ['0', '', 'None']:
                    enchant_elem = etree.SubElement(restoration, 'itemEnchantmentLevel')
                    enchant_elem.text = str(enchant)
                    enchant_elem.tail = '\n\t\t\t'
                
                # Ajustar tail do último elemento
                children = list(restoration)
                if children:
                    children[-1].tail = '\n\t\t'
            
            # Ajustar tail do último effect
            effects_children = list(effects_elem)
            if effects_children:
                effects_children[-1].tail = '\n\t\t'
            
            # ✅ ADICIONAR <effects> ao skill
            skill_elem.append(effects_elem)
            
            # ✅ Garantir tail da skill
            skill_elem.tail = '\n\t'
            
            # Verificar tails dos filhos diretos
            for child in skill_elem:
                if hasattr(child, 'tail'):
                    if child.tail is None or not child.tail.startswith('\n'):
                        if hasattr(child, 'tag') and child.tag == 'effects':
                            child.tail = '\n\t'
                        else:
                            child.tail = '\n\t\t'
            
            result = etree.tostring(skill_elem, encoding='unicode')
            
            if not result.endswith('\n\t'):
                result = result.rstrip() + '\n'
            
            # ✅ GARANTIR que isMagic tem comentário inline
            is_magic_elem = skill_elem.find('.//isMagic')
            if is_magic_elem is not None:
                next_elem = is_magic_elem.getnext()
                
                # Se próximo elemento NÃO é comentário " Static Skill "
                if not (next_elem is not None and isinstance(next_elem, etree._Comment) and 'Static Skill' in next_elem.text):
                    # Comentário tá no lugar errado ou não existe
                    
                    # Remover comentários órfãos próximos
                    parent = is_magic_elem.getparent()
                    if parent is not None:
                        idx = list(parent).index(is_magic_elem)
                        
                        # Checar próximos 2 elementos
                        for offset in range(1, 3):
                            if idx + offset < len(parent):
                                check_elem = parent[idx + offset]
                                if isinstance(check_elem, etree._Comment) and 'Static Skill' in check_elem.text:
                                    parent.remove(check_elem)
                                    break
                        
                        # Adicionar comentário inline correto
                        is_magic_elem.tail = ' '
                        comment = etree.Comment(' Static Skill ')
                        comment.tail = '\n\t\t'
                        parent.insert(idx + 1, comment)
                        
                        print("  ✅ Corrigido comentário do isMagic")

            return self._format_xml_final(skill_elem)
            
        except Exception as e:
            print(f"❌ Erro ao gerar skill XML: {e}")
            import traceback
            traceback.print_exc()
            return None

    def generate_fixed_skill_xml_single_level(self, skill_id: str, skill_level: int, scraper_data: dict, site_type: str) -> Optional[str]:
        """
        Edita skill XML in-place - preserva 100% do original.
        Só atualiza/adiciona o necessário.
        """
        try:
            skill_xml_data = self.xml_handler.load_skill_xml_data(skill_id, site_type)
            
            if not skill_xml_data:
                print(f"❌ Skill {skill_id} não encontrada")
                return None
            
            # ✅ CARREGAR ORIGINAL
            parser = etree.XMLParser(remove_blank_text=False, remove_comments=False)
            skill_elem = etree.fromstring(skill_xml_data['content'].encode('utf-8'), parser)
            
            # ✅ EDITAR IN-PLACE (preserva atributos, name, icon, operateType, etc)
            skill_elem.set('toLevel', str(skill_level))
            icon = ProblemModel.get_skill_icon(int(skill_id), site_type, scraper_data)

            # Atualizar/adicionar stats fixos
            self._update_or_add_element(skill_elem, 'icon', icon)
            self._update_or_add_element(skill_elem, 'operateType', 'A1')
            self._update_or_add_element(skill_elem, 'targetType', 'SELF')
            self._update_or_add_element(skill_elem, 'affectScope', 'SINGLE')
            self._update_or_add_element(skill_elem, 'isMagic', '2')
            self._update_or_add_element(skill_elem, 'magicCriticalRate', '5')
            self._update_or_add_element(skill_elem, 'magicLevel', '1')
            self._update_or_add_element(skill_elem, 'reuseDelay', '1000')
            self._update_or_add_element(skill_elem, 'coolTime', '500')
            self._update_or_add_element(skill_elem, 'hitTime', '0')
            self._update_or_add_element(skill_elem, 'hitCancelTime', '0')
            
            # Item Consume
            item_id = scraper_data.get('item_id')
            if item_id:
                item_name = self.get_item_name_from_item_id(item_id, site_type) or f"Item {item_id}"
                self._update_or_add_element(skill_elem, 'itemConsumeCount', '1')
                
                consume_id_elem = skill_elem.find('itemConsumeId')
                if consume_id_elem is None:
                    consume_id_elem = etree.SubElement(skill_elem, 'itemConsumeId')
                consume_id_elem.text = str(item_id)
            
            # Conditions
            self._update_or_add_conditions(skill_elem)
            
            # ✅ REMOVER effects antigas e adicionar novas
            for old_effects in skill_elem.xpath('./effects'):
                skill_elem.remove(old_effects)
            
            # Criar novo effects
            effects_elem = etree.SubElement(skill_elem, 'effects')
            
            box_data = scraper_data.get('box_data', {})
            
            # Filtrar container
            def filter_container(items):
                return [item for item in items if str(item.get('id', '')) != str(item_id)]
            
            guaranteed = filter_container(box_data.get('guaranteed_items', []))
            random_items = filter_container(box_data.get('random_items', []))
            possible = filter_container(box_data.get('possible_items', []))
            
            # ✅ Restoration (Guaranteed)
            for item in guaranteed:
                i_name = item.get('name', f"Item {item['id']}")
                effect_elem = etree.SubElement(effects_elem, 'effect')
                effect_elem.set('name', 'Restoration')
                
                item_id_elem = etree.SubElement(effect_elem, 'itemId')
                item_id_elem.text = str(item['id'])
                
                count_elem = etree.SubElement(effect_elem, 'itemCount')
                count_elem.text = str(item['count']).replace(' ', '')
                
                enchant = item.get('enchant')
                if enchant and str(enchant) not in ['0', '', 'None']:
                    enchant_elem = etree.SubElement(effect_elem, 'itemEnchantmentLevel')
                    enchant_elem.text = str(enchant)
            
            # ✅ RestorationRandom
            if random_items or possible:
                effect_elem = etree.SubElement(effects_elem, 'effect')
                effect_elem.set('name', 'RestorationRandom')
                
                items_elem = etree.SubElement(effect_elem, 'items')
                
                if random_items:
                    chance = self.calculate_chance(len(random_items), False)
                    for item in random_items:
                        self._create_restoration_random_item(items_elem, item, chance)
                
                if possible:
                    chance = self.calculate_chance(len(possible), True)
                    for item in possible:
                        self._create_restoration_random_item(items_elem, item, chance)
            
            # ✅ RETORNAR como string
            return self._format_xml_final(skill_elem)
            
        except Exception as e:
            print(f"❌ Erro generating single level skill XML: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _update_or_add_element(self, parent, tag_name, text_value):
            """Atualiza ou adiciona elemento com formatação"""
            # Se for uma função, chama ela
            if callable(text_value):
                text_value = text_value()
            
            # Converte para string
            text_value = str(text_value) if text_value else ""
            
            existing = parent.find(tag_name)
            if existing is not None:
                existing.text = text_value
            else:
                new_elem = etree.SubElement(parent, tag_name)
                new_elem.text = text_value

    def _format_xml_final(self, skill_elem) -> str:
        """Formata o XML com indentação correta (1 tab a mais)"""
        etree.indent(skill_elem, space="\t")
        
        # Adicionar 1 tab extra em tudo que vem depois do cabeçalho
        for child in skill_elem.iter():
            if child.text and child.text.startswith('\n'):
                # Adiciona um \t extra
                child.text = child.text.replace('\n', '\n\t', 1)
            if child.tail and child.tail.startswith('\n'):
                # Adiciona um \t extra
                child.tail = child.tail.replace('\n', '\n\t', 1)
        
        result = etree.tostring(skill_elem, encoding='unicode')
        
        # Garante que fechamento </skill> tenha tab correto
        result = result.replace('\n</skill>', '\n</skill>')
        
        return result

    def _update_or_add_conditions(self, parent):
        """Atualiza ou cria conditions com formatação"""
        conditions_elem = parent.find('conditions')
        if conditions_elem is None:
            conditions_elem = etree.SubElement(parent, 'conditions')
        
        conditions_elem.text = '\n\t\t\t'
        conditions_elem.tail = '\n\t\t'
        
        condition_elem = conditions_elem.find("condition[@name='OpEncumbered']")
        if condition_elem is None:
            condition_elem = etree.SubElement(conditions_elem, 'condition')
            condition_elem.set('name', 'OpEncumbered')
        
        condition_elem.text = '\n\t\t\t\t'
        condition_elem.tail = '\n\t\t'
        
        self._update_or_add_element(condition_elem, 'weightPercent', '10')
        self._update_or_add_element(condition_elem, 'slotsPercent', '10')

    def _create_effects_for_level(self, skill_elem, level: int, scraper_data: dict, site_type: str):
        """Cria <effects> para UM level específico"""
        item_id = scraper_data.get('item_id')
        box_data = scraper_data.get('box_data', {})
        
        # Filtrar container
        def filter_container(items):
            return [item for item in items if str(item.get('id', '')) != str(item_id)]
        
        guaranteed = filter_container(box_data.get('guaranteed_items', []))
        random_items = filter_container(box_data.get('random_items', []))
        possible = filter_container(box_data.get('possible_items', []))
        
        # Criar effects
        effects_elem = etree.Element('effects')
        effects_elem.text = '\n\t\t'
        effects_elem.tail = '\n\t'
        
        # Determinar se é single level
        to_level = skill_elem.get('toLevel')
        is_single_level = (level == 1 and (not to_level or to_level == '1'))
        
        # RestorationRandom
        if random_items or possible:
            attrs = {'name': 'RestorationRandom'}
            if not is_single_level:
                attrs['fromLevel'] = str(level)
                attrs['toLevel'] = str(level)
            
            random_effect = etree.SubElement(effects_elem, 'effect', attrs)
            random_effect.text = '\n\t\t\t'
            random_effect.tail = '\n\t\t'
            
            items_container = etree.SubElement(random_effect, 'items')
            items_container.text = '\n\t\t\t\t'
            items_container.tail = '\n\t\t'
            
            random_chance = self.calculate_chance(len(random_items), False)
            for item in random_items:
                self._add_restoration_random_item(items_container, item, random_chance)
            
            possible_chance = self.calculate_chance(len(possible), True)
            for item in possible:
                self._add_restoration_random_item(items_container, item, possible_chance)
            
            if len(items_container) > 0:
                items_container[-1].tail = '\n\t\t\t'
        
        # Restoration (Guaranteed)
        for item in guaranteed:
            attrs = {'name': 'Restoration'}
            if not is_single_level:
                attrs['fromLevel'] = str(level)
                attrs['toLevel'] = str(level)
            
            restoration = etree.SubElement(effects_elem, 'effect', attrs)
            restoration.text = '\n\t\t\t'
            restoration.tail = '\n\t\t'
            
            item_id_elem = etree.SubElement(restoration, 'itemId')
            item_id_elem.text = str(item['id'])
            item_id_elem.tail = ' '
            
            item_name = item.get('name', f"Item {item['id']}")
            comment = etree.Comment(f' {item_name} ')
            comment.tail = '\n\t\t\t'
            restoration.append(comment)
            
            item_count_elem = etree.SubElement(restoration, 'itemCount')
            item_count_elem.text = str(item['count']).replace(' ', '')
            item_count_elem.tail = '\n\t\t\t'
            
            enchant = item.get('enchant')
            if enchant is not None and str(enchant) not in ['0', '', 'None']:
                enchant_elem = etree.SubElement(restoration, 'itemEnchantmentLevel')
                enchant_elem.text = str(enchant)
                enchant_elem.tail = '\n\t\t\t'
            
            children = list(restoration)
            if children:
                children[-1].tail = '\n\t\t'
        
        # Ajustar tail do último effect
        if len(effects_elem) > 0:
            effects_elem[-1].tail = '\n\t\t'
        
        skill_elem.append(effects_elem)

    def _ensure_mandatory_skill_tags(self, skill_elem):
        """Garante tags obrigatórias COM INDENTAÇÃO E COMENTÁRIOS CORRETOS (INLINE)"""
        
        # ✅ Garantir text/tail da skill
        skill_elem.text = '\n\t\t'
        skill_elem.tail = '\n\t'

        mandatory_tags = [
            ('targetType', 'SELF'), 
            ('affectScope', 'SINGLE'), 
            ('coolTime', '500'),
            ('hitCancelTime', '0'), 
            ('hitTime', '0'), 
            ('isMagic', '2'),
            ('magicCriticalRate', '5'), 
            ('magicLevel', '1'), 
            ('reuseDelay', '1000')
        ]

        # ✅ PRIMEIRO: Corrigir TODAS as tags existentes (tail e posição)
        for tag_name, expected_value in mandatory_tags:
            elem = skill_elem.find(tag_name)
            
            if elem is not None:
                # Garantir valor correto
                if elem.text != expected_value:
                    elem.text = expected_value
                
                # ✅ TRATAMENTO ESPECIAL PARA isMagic - COMENTÁRIO NO TAIL!
                if tag_name == 'isMagic':
                    # ✅ Colocar comentário DIRETO no tail (INLINE)
                    elem.tail = ' <!-- Static Skill -->\n\t\t'
                    
                    # Remover comentário órfão se existir como elemento
                    parent = elem.getparent()
                    if parent is not None:
                        for child in list(parent):
                            if isinstance(child, etree._Comment) and 'Static Skill' in child.text:
                                parent.remove(child)
                else:
                    # Outras tags têm tail normal
                    elem.tail = '\n\t\t'

        # ✅ SEGUNDO: Encontrar posição de inserção para tags faltantes
        insert_pos = 0
        for i, child in enumerate(skill_elem):
            if hasattr(child, 'tag') and child.tag in ['operateType', 'icon']:
                insert_pos = i + 1
            if hasattr(child, 'tag') and child.tag in ['conditions', 'effects', 'itemConsumeCount', 'itemConsumeId']:
                break

        # ✅ TERCEIRO: Adicionar tags faltantes (ORDEM REVERSA para manter posição)
        existing_tags = {tag for tag, _ in mandatory_tags if skill_elem.find(tag) is not None}
        
        for tag_name, value in reversed(mandatory_tags):
            if tag_name not in existing_tags:
                elem = etree.Element(tag_name)
                elem.text = value
                
                if tag_name == 'isMagic':
                    # ✅ Comentário INLINE no tail
                    elem.tail = ' <!-- Static Skill -->\n\t\t'
                    skill_elem.insert(insert_pos, elem)
                    print(f"  ➕ Adicionada tag: <isMagic>2</isMagic> <!-- Static Skill -->")
                else:
                    elem.tail = '\n\t\t'
                    skill_elem.insert(insert_pos, elem)
                    print(f"  ➕ Adicionada tag: <{tag_name}>{value}</{tag_name}>")

        # ✅ QUARTO: Garantir <conditions>
        conditions_elem = skill_elem.find('conditions')
        if conditions_elem is None:
            pos = next((i for i, c in enumerate(skill_elem) if hasattr(c, 'tag') and c.tag == 'effects'), len(skill_elem))
            
            conditions_elem = etree.Element('conditions')
            conditions_elem.text = '\n\t\t\t'
            conditions_elem.tail = '\n\t\t'
            
            cond = etree.SubElement(conditions_elem, 'condition', name='OpEncumbered')
            cond.text = '\n\t\t\t\t'
            cond.tail = '\n\t\t\t'
            
            w = etree.SubElement(cond, 'weightPercent')
            w.text = '10'
            w.tail = '\n\t\t\t\t'
            
            s = etree.SubElement(cond, 'slotsPercent')
            s.text = '10'
            s.tail = '\n\t\t\t'
            
            skill_elem.insert(pos, conditions_elem)
            print("  ➕ Adicionada tag: <conditions>")
        else:
            conditions_elem.tail = '\n\t\t'

        # ✅ Garantir tail final
        skill_elem.tail = '\n\t'
        
        print("  ✅ Tags obrigatórias verificadas e corrigidas")

    def save_skill_xml_to_file(self, skill_id: str, xml_content: str, site_type: str, skip_confirmation: bool = False):
        """Salva skill via XMLHandler"""
        if self.xml_handler:
            return self.xml_handler.save_skill_xml_internal(skill_id, xml_content, site_type, skip_confirmation)
        return False

    def _update_item_consume_for_level(self, skill_elem, level: int, item_id: str, site_type: str):
        """Atualiza itemConsumeId/Count para um level COM COMENTÁRIO INLINE"""
        item_name = self.get_item_name_from_item_id(item_id, site_type) or f"Item {item_id}"
        
        to_level = skill_elem.get('toLevel')
        is_single_level = (level == 1 and (not to_level or to_level == '1'))
        
        # itemConsumeCount
        consume_count_elem = skill_elem.find('itemConsumeCount')
        if consume_count_elem is None:
            consume_count_elem = etree.Element('itemConsumeCount')
            consume_count_elem.tail = '\n\t\t'
            insert_index = self._find_insert_position(skill_elem, ['magicCriticalRate', 'conditions'])
            skill_elem.insert(insert_index, consume_count_elem)
        
        if is_single_level:
            consume_count_elem.text = '1'
            consume_count_elem.tail = '\n\t\t'
            for v in list(consume_count_elem):
                consume_count_elem.remove(v)
        else:
            consume_count_elem.text = '\n\t\t\t'
            if not consume_count_elem.find(f"value[@level='{level}']"):
                new_value = etree.SubElement(consume_count_elem, 'value', {'level': str(level)})
                new_value.text = '1'
                new_value.tail = '\n\t\t\t'
        
        # itemConsumeId COM COMENTÁRIO INLINE NO TAIL
        consume_id_elem = skill_elem.find('itemConsumeId')
        if consume_id_elem is None:
            consume_id_elem = etree.Element('itemConsumeId')
            insert_index = self._find_insert_position(skill_elem, ['magicCriticalRate', 'conditions'])
            skill_elem.insert(insert_index, consume_id_elem)
        
        if is_single_level:
            consume_id_elem.text = str(item_id)
            # ✅ COMENTÁRIO NO TAIL (INLINE)
            consume_id_elem.tail = f' <!-- {item_name} -->\n\t\t'
            
            # Limpar filhos
            for child in list(consume_id_elem):
                consume_id_elem.remove(child)
            
            # ✅ Remover comentários órfãos se existirem como elementos
            parent = consume_id_elem.getparent()
            if parent is not None:
                for child in list(parent):
                    if isinstance(child, etree._Comment) and item_name in child.text:
                        parent.remove(child)
        else:
            # Multi-level (com <value>)
            consume_id_elem.text = '\n\t\t\t'
            consume_id_elem.tail = '\n\t\t'
            
            for child in list(consume_id_elem):
                consume_id_elem.remove(child)
            
            # Coletar levels existentes
            values_data = []
            for v in skill_elem.findall('.//itemConsumeId/value'):
                lvl = int(v.get('level'))
                iid = v.text
                iname = self.get_item_name_from_item_id(iid, site_type) or f"Item {iid}"
                values_data.append((lvl, iid, iname))
            
            # Atualizar/adicionar level atual
            found = False
            for i, (lvl, _, _) in enumerate(values_data):
                if lvl == level:
                    values_data[i] = (level, str(item_id), item_name)
                    found = True
                    break
            if not found:
                values_data.append((level, str(item_id), item_name))
            
            values_data.sort(key=lambda x: x[0])
            
            # Reconstruir com comentários INLINE NO TAIL
            for lvl, iid, iname in values_data:
                value_elem = etree.SubElement(consume_id_elem, 'value', {'level': str(lvl)})
                value_elem.text = iid
                # ✅ COMENTÁRIO NO TAIL (INLINE)
                value_elem.tail = f' <!-- {iname} -->\n\t\t\t'
            
            # Ajustar tail do último
            if len(consume_id_elem) > 0:
                consume_id_elem[-1].tail = '\n\t\t'

    def _find_insert_position(self, parent, before_tags: list) -> int:
        """Encontra posição para inserir antes de tags específicas"""
        insert_index = len(list(parent))
        for i, child in enumerate(parent):
            if hasattr(child, 'tag') and child.tag in before_tags:
                insert_index = i
                break
        return insert_index
    
    def _create_restoration_random_item(self, parent, item: dict, chance: str):
        """Adiciona item ao RestorationRandom com estrutura correta"""
        # <item chance="16.7">
        outer_item = etree.SubElement(parent, 'item', {'chance': chance})
        outer_item.text = '\n\t\t\t\t\t'
        outer_item.tail = '\n\t\t\t\t'
        
        # <item id="93717" count="1" minEnchant="5" maxEnchant="5" />
        attrs = {
            'id': str(item['id']),
            'count': str(item['count']).replace(' ', '')
        }
        
        enchant_value = item.get('enchant')
        if enchant_value is not None and str(enchant_value) not in ['0', '', 'None']:
            attrs['minEnchant'] = str(enchant_value)
            attrs['maxEnchant'] = str(enchant_value)
        
        inner_item = etree.SubElement(outer_item, 'item', attrs)
        inner_item.text = None  # Self-closing
        inner_item.tail = ' '
        
        # Comentário INLINE (mesmo nível, não filho)
        item_name = item.get('name', f"Item {item['id']}")
        comment = etree.Comment(f' {item_name} ')
        comment.tail = '\n\t\t\t\t'
        
        # Inserir como irmão (não filho) do inner_item
        parent_idx = list(outer_item).index(inner_item)
        outer_item.insert(parent_idx + 1, comment)

    def get_item_name_from_item_id(self, item_id: str, site_type: str) -> Optional[str]:
        """Busca nome do item"""
        try:
            data_file = Path(f"html_items_{site_type}/{item_id}/data.json")
            if data_file.exists():
                with open(data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    name = data.get('item_name') or data.get('name') or data.get('item', {}).get('name')
                    if name:
                        return name
            return self.get_item_name_from_dat(item_id, site_type)
        except Exception:
            return f"Item {item_id}"

    def get_item_name_from_dat(self, item_id, site_type):
        """Busca nome do item no .dat"""
        if not self.database:
            return None
        
        raw = self.database.ITEM_INDEX_ESSENCE.get(int(item_id)) if site_type == 'essence' else self.database.ITEM_INDEX.get(int(item_id))
        if not raw:
            return None
        
        name = raw[0] if isinstance(raw, list) else raw
        if isinstance(name, str):
            name = name.strip()
            if name.startswith("['"):
                name = name[2:-2]
        return name
    
    def get_skill_name_from_skill_id(self, skill_id: str, site_type: str) -> Optional[str]:
        """Busca nome da skill no JSON do item atual ou no skillname.dat"""
        try:
            # Tentar do .dat direto (mais confiável)
            return self.get_skill_name_from_dat(skill_id, site_type)
        except Exception as e:
            print(f"Erro ao buscar skill {skill_id}: {e}")
            return None

    def get_skill_name_from_dat(self, skill_id, site_type):
        """Busca nome da skill no .dat"""
        if not self.database:
            return None
        
        raw = self.database.SKILL_INDEX_ESSENCE.get(int(skill_id)) if site_type == 'essence' else self.database.SKILL_INDEX.get(int(skill_id))
        
        if not raw:
            return None
        
        # Se for lista, pegar primeiro e limpar
        name = raw[0] if isinstance(raw, list) else raw
        
        # Limpar colchetes
        if isinstance(name, str):
            name = name.strip()
            if name.startswith("['") and name.endswith("']"):
                name = name[2:-2]
            elif name.startswith('[') and name.endswith(']'):
                name = name[1:-1]
        
        return name
    
    def _update_or_add_set_tag_lxml(self, parent, name: str, value: str):
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

    def _update_or_create_skills_lxml(self, parent, skill_id: str, site_type: str, original_tail: str = '\n\t', override_level=None):
        """
        Atualiza ou cria tag <skills> com indentação L2J HARDCODED.
        Garante:
            <skills>       (\t\t)
                <skill />  (\t\t\t)
            </skills>      (\t\t)
        """
        # 1. Encontrar ou Criar
        skills_elem = parent.find('skills')
        if skills_elem is None:
            skills_list = parent.xpath('./skills')
            if skills_list:
                skills_elem = skills_list[0]
        
        if skills_elem is not None:
            skills_elem.text = None
            for child in list(skills_elem):
                skills_elem.remove(child)
        else:
            skills_elem = etree.SubElement(parent, 'skills')
            # Preserva a indentação externa original (geralmente \n\t para fechar item ou \n\t\t para proximo set)
            skills_elem.tail = original_tail

        # 2. Definir Nível
        level_val = str(override_level) if override_level else "1"

        # 3. INDENTAÇÃO FORÇADA (PADRÃO L2J)
        # O conteúdo dentro de <skills> DEVE estar no nível 3 (3 tabs)
        skills_elem.text = '\n\t\t\t'

        # O fechamento </skills> DEVE estar no nível 2 (2 tabs)
        closing_indent = '\n\t\t'

        # 4. Criar a Tag <skill>
        skill = etree.SubElement(skills_elem, 'skill', {'id': skill_id, 'level': level_val})
        
        # 5. Adicionar Comentário
        skill_name = self.get_skill_name_from_skill_id(skill_id, site_type)
        
        if skill_name:
            skill.tail = ' ' 
            comment = etree.Comment(f' {skill_name} ')
            comment.tail = closing_indent 
            skills_elem.append(comment)
        else:
            skill.tail = closing_indent
            skills_elem.append(skill)

        return True
    
    def _build_effects_multi_level(self, skill_elem, items_by_level: list, site_type: str):
        """
        Constrói <effects> com fromLevel/toLevel por effect
        """
        try:
            # Ordenar por level
            sorted_items = sorted(items_by_level, key=lambda x: x['level'])
            
            # Criar effects element
            effects_elem = etree.Element('effects')
            effects_elem.text = '\n\t\t'
            effects_elem.tail = '\n\t'
            
            # ===== PROCESSAR CADA LEVEL INDIVIDUALMENTE =====
            for item_data in sorted_items:
                level = item_data['level']
                container_item_id = item_data['item_id']
                problem = item_data['problem']
                
                scraper_data = problem.get('scraper_data', {})
                box_data = scraper_data.get('box_data', {})
                
                # Filtrar container
                def filter_container(items):
                    return [item for item in items if str(item.get('id', '')) != str(container_item_id)]
                
                guaranteed = filter_container(box_data.get('guaranteed_items', []))
                random_items = filter_container(box_data.get('random_items', []))
                possible_items = filter_container(box_data.get('possible_items', []))
                
                print(f"  📦 Level {level}: {len(guaranteed)}G + {len(random_items)}R + {len(possible_items)}P")
                
                # ===== RestorationRandom para este level =====
                if random_items or possible_items:
                    restoration_random = etree.SubElement(
                        effects_elem, 
                        'effect', 
                        {
                            'name': 'RestorationRandom',
                            'fromLevel': str(level),
                            'toLevel': str(level)
                        }
                    )
                    restoration_random.text = '\n\t\t\t'
                    restoration_random.tail = '\n\t\t'
                    
                    items_container = etree.SubElement(restoration_random, 'items')
                    items_container.text = '\n\t\t\t\t'
                    items_container.tail = '\n\t\t'
                    
                    # Random items
                    random_chance = self.calculate_chance(len(random_items), is_possible=False)
                    for item in random_items:
                        self._add_restoration_random_item(items_container, item, random_chance)
                    
                    # Possible items
                    possible_chance = self.calculate_chance(len(possible_items), is_possible=True)
                    for item in possible_items:
                        self._add_restoration_random_item(items_container, item, possible_chance)
                    
                    # Ajustar tail do último item
                    if len(items_container) > 0:
                        items_container[-1].tail = '\n\t\t\t'
                
                # ===== Restoration (Guaranteed) - UM effect POR ITEM para este level =====
                for item in guaranteed:
                    restoration = etree.SubElement(
                        effects_elem, 
                        'effect', 
                        {
                            'name': 'Restoration',
                            'fromLevel': str(level),
                            'toLevel': str(level)
                        }
                    )
                    restoration.text = '\n\t\t\t'
                    restoration.tail = '\n\t\t'
                    
                    # itemId
                    item_id_elem = etree.SubElement(restoration, 'itemId')
                    item_id_elem.text = str(item['id'])
                    item_id_elem.tail = '\n\t\t\t'
                    
                    # itemCount
                    item_count_elem = etree.SubElement(restoration, 'itemCount')
                    item_count_elem.text = str(item['count']).replace(' ', '')
                    item_count_elem.tail = '\n\t\t\t'
                    
                    # itemEnchantmentLevel (se existir)
                    enchant_value = item.get('enchant')
                    if enchant_value is not None and str(enchant_value) not in ['0', '', 'None']:
                        enchant_elem = etree.SubElement(restoration, 'itemEnchantmentLevel')
                        enchant_elem.text = str(enchant_value)
                        enchant_elem.tail = '\n\t\t\t'
                    
                    # Comentário com nome
                    item_name = item.get('name', f"Item {item['id']}")
                    comment = etree.Comment(f' {item_name} ')
                    comment.tail = '\n\t\t'
                    restoration.append(comment)
            
            # Ajustar tail do último effect
            if len(effects_elem) > 0:
                effects_elem[-1].tail = '\n\t'
            
            skill_elem.append(effects_elem)
            print(f"  ✅ Effects com fromLevel/toLevel construído para {len(sorted_items)} levels")
            
        except Exception as e:
            print(f"  ❌ Erro ao construir effects: {e}")
            import traceback
            traceback.print_exc()

    def _fix_item_for_skill(self, item_elem, skill_id: str, skill_level: int, scraper_data: dict, site_type: str):
        """
        Corrige item para usar skill:
        - default_action = SKILL_REDUCE*
        - handler = ItemSkills
        - Remove capsuled_items
        - Remove extractableCount
        - Adiciona <skills> com skill e level correto
        """
        
        scraping_info = scraper_data.get('scraping_info', {})
        item_type = scraping_info.get('item_type', '')  # SKILL_REDUCE ou SKILL_REDUCE_ON_SKILL_SUCCESS
        
        # 1. default_action
        self._update_or_add_set_tag_lxml(item_elem, 'default_action', item_type)
        
        # 2. handler
        self._update_or_add_set_tag_lxml(item_elem, 'handler', 'ItemSkills')
        
        # 3. Remover capsuled_items
        for capsuled in item_elem.xpath('./capsuled_items'):
            item_elem.remove(capsuled)
        
        # 4. Remover extractableCount
        for tag in item_elem.xpath("./set[@name='extractableCountMin']"):
            item_elem.remove(tag)
        for tag in item_elem.xpath("./set[@name='extractableCountMax']"):
            item_elem.remove(tag)
        
        # 5. Adicionar/atualizar <skills>
        skills_elems = item_elem.xpath('./skills')
        
        if skills_elems:
            skills_elem = skills_elems[0]
            for child in list(skills_elem):
                skills_elem.remove(child)
        else:
            skills_elem = etree.SubElement(item_elem, 'skills')
            skills_elem.text = '\n\t\t\t'
            skills_elem.tail = '\n\t'
        
        # Buscar nome da skill
        skill_name = self.get_skill_name_from_skill_id(skill_id, site_type)

        # Adicionar skill com level correto
        skill = etree.SubElement(skills_elem, 'skill', {'id': skill_id, 'level': str(skill_level)})
        
        if skill_name:
            comment = etree.Comment(f' {skill_name} ')
            comment.tail = '\n\t\t'
            skill.tail = ' '
            skills_elem.append(skill)
            skills_elem.append(comment)
        else:
            skill.tail = '\n\t\t'
            skills_elem.append(skill)

    def generate_skill_xml_multi_level(self, skill_id: str, items_by_level: list, site_type: str) -> Optional[str]:
        """Generate skill with multiple levels"""
        
        try:
            # load base skill
            skill_xml_data = self.xml_handler.load_skill_xml_data(skill_id, site_type)
            
            if not skill_xml_data:
                print(f"❌ Skill {skill_id} not found creating from scratch")
                # create base skill
                skill_elem = etree.Element('skill', {'id': skill_id})
            else:
                skill_elem = etree.fromstring(skill_xml_data['content'].encode('utf-8'))
            
            # Define "toLevel" (max level)
            max_level = max(item['level'] for item in items_by_level)
            skill_elem.set('toLevel', str(max_level))
            
            # mandatory skill tags
            self._ensure_mandatory_skill_tags(skill_elem)
            
            # clean old xml tags with new ones
            for tag in ['itemConsumeCount', 'itemConsumeId', 'effects']:
                for old in skill_elem.findall(tag):
                    skill_elem.remove(old)
            
            # Construct new tags
            self._build_item_consume_tags_multi_level(skill_elem, items_by_level, site_type)
            self._build_effects_multi_level(skill_elem, items_by_level, site_type)
            
            return etree.tostring(skill_elem, encoding='unicode')
            
        except Exception as e:
            print(f"❌ Skill XMl Gen. Error: {e}")
            import traceback
            traceback.print_exc()
            return None
        
    def _build_item_consume_tags_multi_level(self, skill_elem, items_by_level: list, site_type: str):
        """
        Constrói tags itemConsumeCount/Id para múltiplos levels
        APENAS se houver RestorationRandom (random/possible items)
        """
        try:
            # Ordenar por level
            sorted_items = sorted(items_by_level, key=lambda x: x['level'])
            
            # Verificar se ALGUM level tem RestorationRandom
            has_any_restoration_random = False
            for item_data in sorted_items:
                problem = item_data['problem']
                scraper_data = problem.get('scraper_data', {})
                box_data = scraper_data.get('box_data', {})
                random_items = box_data.get('random_items', [])
                possible_items = box_data.get('possible_items', [])
                if random_items or possible_items:
                    has_any_restoration_random = True
                    break
            
            # Se nenhum level tem RestorationRandom, não adiciona as tags
            if not has_any_restoration_random:
                print(f"  ⏭️  Nenhum level tem RestorationRandom, pulando itemConsume tags")
                return
            
            insert_index = len(list(skill_elem))
            for i, child in enumerate(skill_elem):
                if hasattr(child, 'tag') and child.tag in ['magicCriticalRate', 'conditions']:
                    insert_index = i
                    break
            
            consume_count_elem = etree.Element('itemConsumeCount')
            consume_count_elem.text = '\n\t\t\t'
            consume_count_elem.tail = '\n\t\t'
            
            for item_data in sorted_items:
                level = item_data['level']
                
                value_elem = etree.SubElement(consume_count_elem, 'value', {'level': str(level)})
                value_elem.text = '1'
                value_elem.tail = '\n\t\t\t'
            
            if len(consume_count_elem) > 0:
                consume_count_elem[-1].tail = '\n\t\t'
            
            skill_elem.insert(insert_index, consume_count_elem)
            insert_index += 1
            
            consume_id_elem = etree.Element('itemConsumeId')
            consume_id_elem.text = '\n\t\t\t'
            consume_id_elem.tail = '\n\t\t'
            
            for item_data in sorted_items:
                level = item_data['level']
                item_id = item_data['item_id']
                
                # Buscar nome do item para comentário
                item_name = self.get_item_name_from_item_id(item_id, site_type) or f"Item {item_id}"
                
                value_elem = etree.SubElement(consume_id_elem, 'value', {'level': str(level)})
                value_elem.text = item_id
                value_elem.tail = ' '
                
                # Comentário inline
                comment = etree.Comment(f' {item_name} ')
                comment.tail = '\n\t\t\t'
                consume_id_elem.append(comment)
            
            # Ajustar tail do último comentário
            if len(consume_id_elem) > 0:
                consume_id_elem[-1].tail = '\n\t\t'
            
            skill_elem.insert(insert_index, consume_id_elem)
            
            print(f"  ✅ itemConsume tags multi-level adicionadas para {len(sorted_items)} levels")
            
        except Exception as e:
            print(f"  ❌ Erro ao construir itemConsume tags: {e}")
            import traceback
            traceback.print_exc()

    def generate_multilevel_xml_from_json(self, skill_id: str, skill_data: dict, scraper_data: dict, site_type: str = 'main') -> str:
        """
        Edita skill multilevel XML in-place - preserva 100% do original.
        Mantém toda lógica de agrupamento, values, comentários, etc.
        """
        try:
            # 1. CARREGAR ORIGINAL
            xml_info = self.xml_handler.load_skill_xml_data(skill_id, site_type)
            
            if not xml_info:
                print(f"❌ Skill {skill_id} não encontrada")
                return ""

            parser = etree.XMLParser(remove_blank_text=False, remove_comments=False)
            skill_elem = etree.fromstring(xml_info['content'].encode('utf-8'), parser)
            
            # 2. PREPARAR DADOS
            levels = skill_data.get('levels', [])
            levels.sort(key=lambda x: x['level'])
            max_level = skill_data.get('max_level', len(levels) if levels else 1)
            
            # Atualizar atributos
            skill_elem.set('toLevel', str(max_level))
            icon = ProblemModel.get_skill_icon(int(skill_id), site_type, scraper_data)

            # Atualizar/adicionar stats fixos
            self._update_or_add_element(skill_elem, 'icon', icon)
            self._update_or_add_element(skill_elem, 'operateType', 'A1')
            self._update_or_add_element(skill_elem, 'targetType', 'SELF')
            self._update_or_add_element(skill_elem, 'affectScope', 'SINGLE')
            self._update_or_add_element(skill_elem, 'isMagic', '2')
            self._update_or_add_element(skill_elem, 'magicCriticalRate', '5')
            self._update_or_add_element(skill_elem, 'magicLevel', '1')
            self._update_or_add_element(skill_elem, 'reuseDelay', '1000')
            self._update_or_add_element(skill_elem, 'coolTime', '500')
            self._update_or_add_element(skill_elem, 'hitTime', '0')
            self._update_or_add_element(skill_elem, 'hitCancelTime', '0')
            
            # 4. ATUALIZAR itemConsumeCount/itemConsumeId (MULTILEVEL)
            if levels:
                self._update_multilevel_item_consume(skill_elem, levels, site_type)
            
            # 5. ATUALIZAR Conditions
            self._update_or_add_conditions(skill_elem)
            
            # 6. PRÉ-PROCESSAMENTO: SEPARAR GUARANTEED PUROS DE ENCHANTADOS
            restoration_map = {}
            enchanted_guaranteed_per_level = {}
            
            for lvl_data in levels:
                lvl = lvl_data['level']
                enchanted_guaranteed_per_level[lvl] = []
                
                g_items = lvl_data.get('box_data', {}).get('guaranteed_items', [])
                
                for item in g_items:
                    i_id = str(item['id'])
                    if i_id == str(lvl_data['item_id']):
                        continue
                    
                    raw_enc = item.get('enchant', 0)
                    has_enchant = raw_enc and str(raw_enc) not in ['0', '', 'None']
                    
                    if has_enchant:
                        enchanted_guaranteed_per_level[lvl].append(item)
                    else:
                        if i_id not in restoration_map:
                            i_name = item.get('name')
                            if not i_name or i_name == "None":
                                i_name = self.get_item_name_from_dat(i_id, site_type)
                            restoration_map[i_id] = {
                                'id': i_id, 'name': i_name, 'levels': [], 'counts': {}
                            }
                        restoration_map[i_id]['levels'].append(lvl)
                        restoration_map[i_id]['counts'][lvl] = item['count']
            
            # 7. REMOVER effects antigas
            for old_effects in skill_elem.xpath('./effects'):
                skill_elem.remove(old_effects)
            
            # 8. CRIAR effects nova
            effects_elem = etree.SubElement(skill_elem, 'effects')
            
            # A) RESTORATION (Guaranteed puro)
            for i_id, data in restoration_map.items():
                min_l = min(data['levels'])
                max_l = max(data['levels'])
                
                counts = [data['counts'][lvl] for lvl in sorted(data['levels'])]
                is_variable_count = len(set(counts)) > 1
                
                effect_elem = etree.SubElement(effects_elem, 'effect')
                effect_elem.set('name', 'Restoration')
                
                if not is_variable_count:
                    effect_elem.set('fromLevel', str(min_l))
                    effect_elem.set('toLevel', str(max_l))
                
                item_id_elem = etree.SubElement(effect_elem, 'itemId')
                item_id_elem.text = str(i_id)
                
                if is_variable_count:
                    item_count_elem = etree.SubElement(effect_elem, 'itemCount')
                    for lvl in sorted(data['levels']):
                        val = str(data['counts'][lvl]).replace(' ', '')
                        value_elem = etree.SubElement(item_count_elem, 'value')
                        value_elem.set('level', str(lvl))
                        value_elem.text = val
                else:
                    count_elem = etree.SubElement(effect_elem, 'itemCount')
                    count_elem.text = str(counts[0]).replace(' ', '')
            
            # B) RESTORATIONRANDOM (Random + Possible + Guaranteed Enchantados)
            for lvl_data in levels:
                lvl = lvl_data['level']
                curr_id = str(lvl_data['item_id'])
                
                random_items = [x for x in lvl_data.get('box_data', {}).get('random_items', []) if str(x['id']) != curr_id]
                possible_items = [x for x in lvl_data.get('box_data', {}).get('possible_items', []) if str(x['id']) != curr_id]
                guaranteed_enchanted = enchanted_guaranteed_per_level.get(lvl, [])
                
                if random_items or possible_items or guaranteed_enchanted:
                    effect_elem = etree.SubElement(effects_elem, 'effect')
                    effect_elem.set('name', 'RestorationRandom')
                    effect_elem.set('level', str(lvl))
                    
                    items_elem = etree.SubElement(effect_elem, 'items')
                    
                    # Guaranteed Enchanted (Chance 100)
                    for item in guaranteed_enchanted:
                        self._create_restoration_random_item(items_elem, item, '100')
                    
                    # Random
                    if random_items:
                        chance = self.calculate_chance(len(random_items), False)
                        for item in random_items:
                            self._create_restoration_random_item(items_elem, item, chance)
                    
                    # Possible
                    if possible_items:
                        chance = self.calculate_chance(len(possible_items), True)
                        for item in possible_items:
                            self._create_restoration_random_item(items_elem, item, chance)
            
            # 9. RETORNAR como string COM CRLF (Windows)
            xml_str = self._format_xml_final(skill_elem)
            return xml_str.replace('\r\n', '\n').replace('\n', '\r\n') 
            
        except Exception as e:
            print(f"❌ Erro na geração Multilevel: {e}")
            import traceback
            traceback.print_exc()
            return ""

    def _update_multilevel_item_consume(self, skill_elem, levels, site_type):
        """Atualiza itemConsumeCount/itemConsumeId com values se multilevel"""
        
        # Remover antigas
        for old in skill_elem.xpath('./itemConsumeCount'):
            skill_elem.remove(old)
        for old in skill_elem.xpath('./itemConsumeId'):
            skill_elem.remove(old)
        
        # Criar novas
        if len(levels) == 1:
            # Single level - sem values
            consume_count = etree.SubElement(skill_elem, 'itemConsumeCount')
            consume_count.text = '1'
            consume_count.tail = '\n\t\t'
            
            consume_id = etree.SubElement(skill_elem, 'itemConsumeId')
            consume_id.text = str(levels[0]['item_id'])
            consume_id.tail = '\n\t\t'
        else:
            # Multilevel - com values
            consume_count = etree.SubElement(skill_elem, 'itemConsumeCount')
            consume_count.tail = '\n\t\t'
            
            for idx, lvl_data in enumerate(levels):
                value_elem = etree.SubElement(consume_count, 'value')
                value_elem.set('level', str(lvl_data['level']))
                value_elem.text = '1'
                value_elem.tail = '\n\t\t' if idx < len(levels) - 1 else '\n\t\t'
            
            consume_id = etree.SubElement(skill_elem, 'itemConsumeId')
            consume_id.tail = '\n\t\t'
            
            for idx, lvl_data in enumerate(levels):
                value_elem = etree.SubElement(consume_id, 'value')
                value_elem.set('level', str(lvl_data['level']))
                value_elem.text = str(lvl_data['item_id'])
                value_elem.tail = '\n\t\t' if idx < len(levels) - 1 else '\n\t\t'

    def _append_xml_item(self, lines_list, item, chance, indent):
        """Helper para item random com COMENTÁRIO INLINE"""
        i_id = item['id']
        i_count = item['count']
        i_name = item.get('name', f"Item {i_id}")
        i_enchant = item.get('enchant')
        
        # Sintaxe solicitada: minEnchant="x" maxEnchant="x" dentro da tag item
        enchant_str = ""
        if i_enchant and str(i_enchant) not in ['0', '', 'None']:
            enchant_str = f' minEnchant="{i_enchant}" maxEnchant="{i_enchant}"'

        lines_list.append(f'{indent}<item chance="{chance}">')
        # ✅ COMENTÁRIO INLINE AQUI
        lines_list.append(f'{indent}\t<item id="{i_id}" count="{i_count}"{enchant_str} /> <!-- {i_name} -->')
        lines_list.append(f'{indent}</item>')