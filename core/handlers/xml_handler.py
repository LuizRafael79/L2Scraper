from PyQt6.QtWidgets import QMessageBox
from lxml import etree
from pathlib import Path
from typing import Optional, Dict, Any
import re

class XMLHandler:
    def __init__(self, site_type='main'):
        self.site_type = site_type

    def load_xml_data(self, item_id, site_type):
        """Encontra e carrega o XML do item preservando comentários"""
        # Cálculo de blocos (ex: item 150 fica em 00100-00199)
        block_num = int(item_id) // 100
        block_start = block_num * 100
        block_end = block_start + 99
        
        filename = f"{block_start:05d}-{block_end:05d}.xml"

        if site_type == "essence":
            xml_file = Path(f"items_essence/{filename}")
            output_file = Path(f"output_items_essence/{filename}")
        else:
            xml_file = Path(f"items_main/{filename}")
            output_file = Path(f"output_items_main/{filename}")

        # PRIORIZAR OUTPUT SE EXISTIR
        file_to_load = output_file if output_file.exists() else xml_file

        if file_to_load.exists():
            try:
                parser = etree.XMLParser(
                    remove_blank_text=False, 
                    remove_comments=False
                )
                tree = etree.parse(str(file_to_load), parser)
                root = tree.getroot()
                
                items = root.xpath(f".//item[@id='{item_id}'][@name][@type]")
                if items:
                    item_elem = items[0]
                    
                    content_str = etree.tostring(item_elem, encoding='unicode', method='xml', pretty_print=False)

                    # Remove namespace sujo se houver
                    content_str = re.sub(r'\s+xmlns(?::[^=]+)?="[^"]*"', '', content_str)
                    
                    return {
                        'file': str(file_to_load),
                        'tree': tree,
                        'root': root,
                        'element': item_elem,
                        'content': content_str
                    }
            except Exception as e:
                print(f"Erro ao carregar {file_to_load}: {e}")

        return None

    def load_skill_xml_data(self, skill_id: str, site_type: str = 'main'):
        """Carrega XML da skill do arquivo correto"""
        block_num = int(skill_id) // 100
        block_start = block_num * 100
        block_end = block_start + 99
        
        filename = f"{block_start:05d}-{block_end:05d}.xml"

        if site_type == "essence":
            xml_file = Path(f"skills_essence/{filename}")
            output_file = Path(f"output_skills_essence/{filename}")
        else:
            xml_file = Path(f"skills_main/{filename}")
            output_file = Path(f"output_skills_main/{filename}")
        
        file_to_load = output_file if output_file.exists() else xml_file
        
        if not file_to_load.exists():
            return None
        
        try:
            skill_parser = etree.XMLParser(remove_blank_text=False, remove_comments=False)
            tree = etree.parse(str(file_to_load), skill_parser)
            root = tree.getroot()
            skill_elem = root.find(f".//skill[@id='{skill_id}']")
            
            if skill_elem is not None:
                content_str = etree.tostring(
                    skill_elem,
                    method='xml',
                    encoding='unicode',
                    pretty_print=False  
                )
                content_str = re.sub(r'\s+xmlns(?::[^=]+)?="[^"]*"', '', content_str)
                
                return {
                    'file': str(file_to_load),
                    'tree': tree,
                    'root': root,
                    'element': skill_elem,
                    'content': content_str
                }
            return None
                
        except Exception as e:
            print(f"❌ Erro ao carregar skill XML {file_to_load}: {e}")
            return None

    def save_skill_xml_internal(self, skill_id: str, skill_xml_content: str, site_type: str = 'main', skip_confirmation: bool = False):
        """Salva skill preservando TODOS os comentários inline"""
        try:
            # 1. Determinar diretório de saída
            if site_type == "essence":
                output_dir = Path("output_skills_essence")
            else:
                output_dir = Path("output_skills_main")
            
            output_dir.mkdir(exist_ok=True)
            
            # 2. Carregar skill original para pegar o caminho do arquivo
            skill_xml_data = self.load_skill_xml_data(skill_id, site_type)
            if not skill_xml_data:
                if not skip_confirmation:
                    from PyQt6.QtWidgets import QMessageBox
                    QMessageBox.warning(None, "Save Error", f"Could not load original skill XML for {skill_id}")
                return False
            
            original_file = Path(skill_xml_data['file'])
            output_file = output_dir / original_file.name
            
            # 3. Carregar conteúdo do arquivo (output se existir, original se não)
            file_to_load = output_file if output_file.exists() else original_file
            
            with open(file_to_load, 'r', encoding='utf-8') as f:
                full_content = f.read()
            
            # 4. Backup de segurança
            backup_file = output_file.with_suffix('.xml.backup')
            with open(backup_file, 'w', encoding='utf-8') as f:
                f.write(full_content)
            print(f"💾 Backup criado: {backup_file}")
            
            # 5. Preparar o novo conteúdo
            # ✅ NÃO TOCAR em nada! Só garantir terminação correta
            if not skill_xml_content.endswith('\n\t'):
                skill_xml_content = skill_xml_content.rstrip() + '\n\t'
            
            # ✅ Garante espaço em self-closing tags (<tag/> -> <tag />)
            # MAS: preserva comentários inline! A regex abaixo só toca em /> que NÃO tá em comentário
            skill_xml_content = re.sub(r'(?<!\s)(?<!-)/>(?!-)', ' />', skill_xml_content)
            
            # 6. ✅ REGEX que CAPTURA comentários inline
            # Procura: <skill ... > ... </skill>
            # E também: comentários que estejam LOGO após o </skill>
            pattern = rf'(<skill[^>]*\sid="{re.escape(skill_id)}"[^>]*>.*?</skill>)(\s*<!--[^-]*?-->)?'
            
            match = re.search(pattern, full_content, flags=re.DOTALL)
            
            if not match:
                print(f"❌ Skill {skill_id} NÃO encontrada no arquivo!")
                return False
            
            print(f"✅ Skill {skill_id} encontrada!")
            
            # 7. Substituir no conteúdo total
            # ✅ Preserva comentários que estavam ANTES
            new_content = full_content[:match.start()] + skill_xml_content + full_content[match.end():]
            
            # 8. Validações de sanidade
            if new_content.count('<skill') != full_content.count('<skill'):
                print(f"❌ ERRO CRÍTICO: Número de skills mudou após salvar!")
                return False
            
            # 9. Salvar Arquivo Final
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            print(f"✅ Skill {skill_id} salva com sucesso em {output_file}")
            
            if not skip_confirmation:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(
                    None, 
                    "Success", 
                    f"✓ Skill XML saved!\nOutput: {output_file}"
                )
            
            return True
                
        except Exception as e:
            print(f"❌ ERRO FATAL: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _fix_inline_comments_in_skill(self, skill_elem):
        """Corrige comentários inline ANTES de salvar"""
        
        # ✅ CORRIGIR isMagic
        is_magic_elem = skill_elem.find('.//isMagic')
        if is_magic_elem is not None:
            next_elem = is_magic_elem.getnext()
            
            # ✅ Verificar se próximo é comentário inline (com validação de .text)
            is_inline_comment = (
                next_elem is not None and 
                isinstance(next_elem, etree._Comment) and 
                next_elem.text is not None and  # ← ADICIONAR ESSA LINHA
                'Static Skill' in next_elem.text
            )
            
            if not is_inline_comment:
                # Remover comentário órfão
                parent = is_magic_elem.getparent()
                if parent is not None:
                    for child in list(parent):
                        if (isinstance(child, etree._Comment) and 
                            child.text is not None and  # ← ADICIONAR ESSA LINHA
                            'Static Skill' in child.text):
                            parent.remove(child)
                    
                    # Adicionar comentário inline correto
                    idx = list(parent).index(is_magic_elem)
                    is_magic_elem.tail = ' '
                    
                    comment = etree.Comment(' Static Skill ')
                    comment.tail = '\n\t\t'
                    parent.insert(idx + 1, comment)
                    
                    print("  ✅ Corrigido comentário inline de isMagic")
        
        # ✅ CORRIGIR itemConsumeId
        consume_id_elem = skill_elem.find('.//itemConsumeId')
        if consume_id_elem is not None:
            # Se é texto direto (single level)
            if consume_id_elem.text and consume_id_elem.text.strip().isdigit():
                next_elem = consume_id_elem.getnext()
                
                # Verificar se próximo é comentário (com validação)
                if next_elem is not None and isinstance(next_elem, etree._Comment):
                    # Garantir tail correto
                    consume_id_elem.tail = ' '
                    if next_elem.tail is None or not next_elem.tail.startswith('\n'):
                        next_elem.tail = '\n\t\t'
            
            # Se tem <value> (multi-level)
            for value_elem in consume_id_elem.findall('.//value'):
                next_elem = value_elem.getnext()
                
                if next_elem is not None and isinstance(next_elem, etree._Comment):
                    value_elem.tail = ' '
                    if next_elem.tail is None or not next_elem.tail.startswith('\n'):
                        next_elem.tail = '\n\t\t\t'
        
    def fix_self_closing_tags(self, xml_string: str) -> str:
        """Garante espaço antes de /> (Ex: <tag/> vira <tag />)"""
        return re.sub(r'(?<!\s)/>', ' />', xml_string)
        
    def format_xml_string(self, xml_string):
        """
        Valida e retorna XML.
        NÃO REFORMATA, pois isso quebraria os comentários inline.
        """
        try:
            # Apenas faz o parse para ver se o XML é válido
            parser = etree.XMLParser(remove_blank_text=False, remove_comments=False)
            etree.fromstring(xml_string.encode('utf-8'), parser)
            
            # Se não deu erro, retorna a string original (não toca nela!)
            # Se quisermos indentar, teríamos que fazer regex, lxml pretty_print estraga inline comments.
            return xml_string
            
        except Exception as e:
            print(f"Erro ao validar XML: {e}")
            return xml_string
        
    def update_or_add_set_tag_lxml(self, parent, name: str, value: str):
        """
        Atualiza ou adiciona tag <set>.
        Nome público (sem _) para ser usado por outros handlers.
        """
        existing = parent.xpath(f"./set[@name='{name}']")
        
        if existing:
            existing[0].set('val', value)
        else:
            # Encontrar posição (antes de tags complexas)
            insert_pos = len(list(parent))
            for i, child in enumerate(parent):
                if hasattr(child, 'tag') and child.tag in ['capsuled_items', 'skills', 'cond', 'enchant', 'unequip_skills']:
                    insert_pos = i
                    break
            
            new_set = etree.Element('set', {'name': name, 'val': value})
            new_set.tail = '\n\t\t'
            parent.insert(insert_pos, new_set)