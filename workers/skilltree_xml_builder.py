import json
import time
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from PyQt6.QtCore import QThread, pyqtSignal


@dataclass
class SkillDiff:
    skill_id: str
    level: str
    field: str
    old_value: str
    new_value: str
    change_type: str


class SkillTreeXMLBuilder(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)
    comparison_signal = pyqtSignal(dict)
    finished_signal = pyqtSignal(dict)

    def __init__(self, json_path: str, xml_path: str, output_path: str = None, 
                 auto_merge=False, dat_file: str = None, skilltree_path: str = None):
        super().__init__()
        self.json_path = Path(json_path)
        self.xml_path = Path(xml_path)
        self.output_path = Path(output_path) if output_path else self.xml_path.parent / f"{self.xml_path.stem}_updated.xml"
        self.auto_merge = auto_merge
        self.dat_file = dat_file or "databases/skills_main.dat"
        self.skilltree_path = skilltree_path or "skilltree"
        self.skill_parser = None
        self.common_skills_detector = None
        
        self.xml_content = ""
        self.xml_root = None  # Compatibilidade com código antigo
        self.xml_text_preview = ""  # Texto para preview com comentários
        self.diffs = []
        self.id_validation_issues = []  # Problemas de validação de IDs
        self.stats = {
            'total_skills_json': 0,
            'total_skills_xml': 0,
            'skills_added': 0,
            'skills_removed': 0,
            'skills_modified': 0,
            'duration': 0,
            'skipped_common': 0
        }

    def run(self):
        start_time = time.time()
        
        try:
            # Carregar SkillNameParser com capacidades estendidas
            try:
                from core.skill_name_parser import SkillNameParser
                self.skill_parser = SkillNameParser(self.dat_file)
                self.thread_safe_log(f"✅ Skill database loaded: {len(self.skill_parser.skill_map)} skills")
            except Exception as e:
                self.thread_safe_log(f"⚠️ Warning: Could not load skill database: {e}")
                self.skill_parser = None
            
            # Carregar detector de skills comuns
            try:
                from core.common_skills_detector import CommonSkillsDetector
                site_type = self.xml_path.parts[-3] if len(self.xml_path.parts) >= 3 else "main"
                self.common_skills_detector = CommonSkillsDetector(self.skilltree_path, site_type)
                self.thread_safe_log(f"✅ Common skills: {len(self.common_skills_detector.get_common_skills())}")
            except Exception as e:
                self.thread_safe_log(f"⚠️ Warning: {e}")
                self.common_skills_detector = None
            
            self.thread_safe_log("🚀 Iniciando processamento...")
            
            # Ler JSON
            json_data = self.read_json_data()
            if not json_data:
                self.thread_safe_log("❌ Falha ao ler JSON")
                return

            # Ler XML como texto puro
            self.xml_content = self.read_xml_text()
            if not self.xml_content:
                self.thread_safe_log("❌ Falha ao ler XML")
                return

            self.thread_safe_log(f"📄 JSON: {self.stats['total_skills_json']} skills")
            self.thread_safe_log(f"📋 XML: {self.stats['total_skills_xml']} skills")
            self.thread_safe_log("=" * 60)

            # Comparar dados
            xml_skills = self.extract_xml_skills()
            self.compare_data(json_data, xml_skills)
            
            # Validar IDs de skills
            if self.skill_parser:
                self.validate_skill_ids(json_data, xml_skills)
            
            self.generate_comparison_report()

            # Atualizar XML
            self.thread_safe_log("\n🔄 Atualizando XML...")
            self.update_xml_text(json_data, xml_skills)
            
            if self.auto_merge:
                backup_path = self.xml_path.parent / f"{self.xml_path.stem}_backup_{int(time.time())}.xml"
                shutil.copy(self.xml_path, backup_path)
                self.thread_safe_log(f"📦 Backup: {backup_path}")
                
                self.save_xml()
                self.thread_safe_log(f"✅ XML atualizado: {self.output_path}")

        except Exception as e:
            self.thread_safe_log(f"💥 Erro: {e}")
            import traceback
            self.thread_safe_log(traceback.format_exc())
        finally:
            self.stats['duration'] = time.time() - start_time
            self.finished_signal.emit(self.stats)

    def read_xml_text(self) -> str:
        """Lê XML como texto puro"""
        try:
            if not self.xml_path.exists():
                self.thread_safe_log(f"❌ XML file not found: {self.xml_path}")
                return ""
            
            with open(self.xml_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            self.thread_safe_log(f"📖 XML loaded: {len(content)} characters")
            
            # Debug: verificar se tem skills
            skill_count = content.count('<skill')
            self.thread_safe_log(f"🔍 Found {skill_count} occurrences of '<skill' in XML")
            
            return content
        except Exception as e:
            self.thread_safe_log(f"❌ Erro ao ler XML: {e}")
            import traceback
            self.thread_safe_log(traceback.format_exc())
            return ""

    def extract_xml_skills(self) -> Dict[str, Dict]:
        """Extrai skills do XML como texto, mantendo posições"""
        skills = {}
        
        # Debug: verificar se tem conteúdo
        if not self.xml_content:
            self.thread_safe_log("⚠️ XML content is empty!")
            return skills
        
        # Encontrar todas as tags <skill>
        pos = 0
        found_count = 0
        
        while True:
            # Buscar <skill com espaço OU <skill> OU <skill/>
            start = self.xml_content.find('<skill', pos)
            if start == -1:
                break
            
            # Verificar se é realmente uma tag skill (não skillTree)
            after_skill = start + 6
            if after_skill < len(self.xml_content):
                next_char = self.xml_content[after_skill]
                if next_char not in [' ', '>', '/']:
                    # É algo como <skillTree>, pular
                    pos = after_skill
                    continue
            
            # Encontrar o fim da tag
            end = self.xml_content.find('>', start)
            if end == -1:
                break
            
            # Verificar se é self-closing ou tem </skill>
            is_self_closing = self.xml_content[end-1:end] == '/' or self.xml_content[end-2:end] == '/>'
            
            if is_self_closing:
                skill_end = end + 1
            else:
                # Procurar </skill>
                skill_end = self.xml_content.find('</skill>', end)
                if skill_end == -1:
                    # Não achou fechamento, assumir self-closing
                    skill_end = end + 1
                else:
                    skill_end += 8  # len('</skill>')
            
            # Extrair conteúdo completo da skill
            skill_text = self.xml_content[start:skill_end]
            
            # Extrair atributos
            skill_id = self._extract_attr(skill_text, 'skillId')
            level = self._extract_attr(skill_text, 'skillLevel') or '1'
            name = self._extract_attr(skill_text, 'skillName')
            
            if skill_id:
                key = f"{skill_id}_{level}"
                skills[key] = {
                    'skill_id': skill_id,
                    'level': level,
                    'name': name or '',
                    'start_pos': start,
                    'end_pos': skill_end,
                    'original_text': skill_text
                }
                found_count += 1
            
            pos = skill_end
        
        self.stats['total_skills_xml'] = found_count
        
        if found_count == 0:
            self.thread_safe_log(f"⚠️ Debug: XML has {len(self.xml_content)} chars but no skills found")
            # Mostrar primeiras linhas para debug
            lines = self.xml_content.split('\n')[:10]
            for i, line in enumerate(lines, 1):
                if '<skill' in line.lower():
                    self.thread_safe_log(f"  Line {i}: {line[:100]}")
        
        return skills

    def _extract_attr(self, text: str, attr_name: str) -> str:
        """Extrai valor de atributo XML"""
        # Procurar attr="value" ou attr='value'
        for quote in ['"', "'"]:
            pattern = f'{attr_name}={quote}'
            start = text.find(pattern)
            if start != -1:
                start += len(pattern)
                end = text.find(quote, start)
                if end != -1:
                    return text[start:end]
        return ""

    def _update_attr(self, text: str, attr_name: str, new_value: str) -> str:
        """Atualiza valor de atributo preservando quote style"""
        for quote in ['"', "'"]:
            pattern = f'{attr_name}={quote}'
            start = text.find(pattern)
            if start != -1:
                start += len(pattern)
                end = text.find(quote, start)
                if end != -1:
                    old_value = text[start:end]
                    return text.replace(f'{attr_name}={quote}{old_value}{quote}', 
                                      f'{attr_name}={quote}{new_value}{quote}')
        
        # Se não existe, adicionar no final da tag de abertura
        tag_end = text.find('>')
        if tag_end != -1:
            insert_pos = tag_end
            if text[tag_end-1] == '/':
                insert_pos = tag_end - 1
            return text[:insert_pos] + f' {attr_name}="{new_value}"' + text[insert_pos:]
        
        return text

    def read_json_data(self) -> Dict:
        """Lê dados do JSON"""
        try:
            with open(self.json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            skills_dict = {}
            for category, skills_list in data.get('categories', {}).items():
                for skill in skills_list:
                    key = f"{skill['skill_id']}_{skill.get('level', '1')}"
                    skills_dict[key] = {
                        'skill_id': skill['skill_id'],
                        'name': skill.get('name', ''),
                        'level': skill.get('level', '1'),
                        'sublevel': skill.get('sublevel', '1'),
                        'type': skill.get('type', 'ACTIVE'),
                        'category': category,
                        'required_level': skill.get('required_level', ''),
                        'sp_consumption': skill.get('sp_consumption', ''),
                        'autoget': skill.get('autoget', False),
                        'items': skill.get('items', [])
                    }
                    self.stats['total_skills_json'] += 1
            
            return skills_dict
        except Exception as e:
            self.thread_safe_log(f"❌ Erro ao ler JSON: {e}")
            return {}

    def compare_data(self, json_data: Dict, xml_skills: Dict):
        """Compara JSON vs XML"""
        # Skills adicionadas
        for key, json_skill in json_data.items():
            if key not in xml_skills:
                self.diffs.append(SkillDiff(
                    skill_id=json_skill['skill_id'],
                    level=json_skill['level'],
                    field='skill',
                    old_value='',
                    new_value=json_skill['name'],
                    change_type='added'
                ))
                self.stats['skills_added'] += 1

        # Skills removidas
        for key, xml_skill in xml_skills.items():
            if key not in json_data:
                self.diffs.append(SkillDiff(
                    skill_id=xml_skill['skill_id'],
                    level=xml_skill['level'],
                    field='skill',
                    old_value=xml_skill['name'],
                    new_value='',
                    change_type='removed'
                ))
                self.stats['skills_removed'] += 1

        # Skills modificadas
        for key in xml_skills.keys() & json_data.keys():
            json_skill = json_data[key]
            xml_skill = xml_skills[key]

            if json_skill['name'] != xml_skill['name']:
                self.diffs.append(SkillDiff(
                    skill_id=json_skill['skill_id'],
                    level=json_skill['level'],
                    field='skillName',
                    old_value=xml_skill['name'],
                    new_value=json_skill['name'],
                    change_type='modified'
                ))
                self.stats['skills_modified'] += 1

    def generate_comparison_report(self):
        """Gera relatório de comparação"""
        report = {
            'total_diffs': len(self.diffs),
            'added': [],
            'removed': [],
            'modified': []
        }

        for diff in self.diffs:
            entry = {
                'skill_id': diff.skill_id,
                'level': diff.level,
                'field': diff.field,
                'old': diff.old_value,
                'new': diff.new_value
            }
            
            if diff.change_type == 'added':
                report['added'].append(entry)
            elif diff.change_type == 'removed':
                report['removed'].append(entry)
            else:
                report['modified'].append(entry)

        if report['added']:
            self.thread_safe_log(f"➕ {len(report['added'])} skills adicionadas")
        if report['removed']:
            self.thread_safe_log(f"➖ {len(report['removed'])} skills removidas")
        if report['modified']:
            self.thread_safe_log(f"✏️ {len(report['modified'])} skills modificadas")

        self.comparison_signal.emit(report)

    def update_xml_text(self, json_data: Dict, xml_skills: Dict):
        """Atualiza XML via substituição de texto"""
        updated = 0
        added = 0
        skipped = 0
        
        # Lista de modificações a fazer (da última pra primeira pra não bagunçar posições)
        modifications = []
        
        # 1. ATUALIZAR skills existentes
        for key, xml_skill in xml_skills.items():
            if key not in json_data:
                continue
                
            json_skill = json_data[key]
            skill_id = json_skill['skill_id']
            
            # Pular skills comuns
            if self.common_skills_detector and self.common_skills_detector.is_common_skill(skill_id):
                skipped += 1
                continue
            
            # Preparar novo texto da skill
            new_text = xml_skill['original_text']
            
            # Atualizar atributos
            new_text = self._update_attr(new_text, 'skillName', json_skill['name'])
            
            if json_skill.get('required_level'):
                new_text = self._update_attr(new_text, 'getLevel', json_skill['required_level'])
            
            if json_skill.get('sp_consumption'):
                sp = json_skill['sp_consumption'].replace(' ', '')
                if sp.isdigit():
                    new_text = self._update_attr(new_text, 'levelUpSp', sp)
            
            # Adicionar modificação à lista
            if new_text != xml_skill['original_text']:
                modifications.append({
                    'start': xml_skill['start_pos'],
                    'end': xml_skill['end_pos'],
                    'new_text': new_text,
                    'name': json_skill['name']
                })
                updated += 1
        
        # 2. ADICIONAR skills novas no final
        # Encontrar posição do </skillTree>
        skilltree_end = self.xml_content.rfind('</skillTree>')
        if skilltree_end == -1:
            self.thread_safe_log("❌ Não encontrou </skillTree>")
            return
        
        # Detectar indentação antes do </skillTree>
        indent = self._detect_indent()
        
        new_skills_text = ""
        added_keys = set(json_data.keys()) - set(xml_skills.keys())
        
        for key in sorted(added_keys):
            json_skill = json_data[key]
            skill_id = json_skill['skill_id']
            
            # Pular skills comuns
            if self.common_skills_detector and self.common_skills_detector.is_common_skill(skill_id):
                skipped += 1
                continue
            
            # Criar nova skill com indentação correta
            skill_text = f'{indent}<skill'
            skill_text += f' skillName="{json_skill["name"]}"'
            skill_text += f' skillId="{json_skill["skill_id"]}"'
            skill_text += f' skillLevel="{json_skill["level"]}"'
            
            if json_skill.get('required_level'):
                skill_text += f' getLevel="{json_skill["required_level"]}"'
            
            if json_skill.get('sp_consumption'):
                sp = json_skill['sp_consumption'].replace(' ', '')
                if sp.isdigit():
                    skill_text += f' levelUpSp="{sp}"'
            
            if json_skill.get('autoget'):
                skill_text += ' autoGet="true"'
            
            # Se tem items, adicionar
            if json_skill.get('items'):
                skill_text += '>\n'
                for item_data in json_skill['items']:
                    skill_text += f'{indent}\t<item id="{item_data.get("id", "")}" count="{item_data.get("count", "1")}" />\n'
                skill_text += f'{indent}</skill>\n'
            else:
                skill_text += ' />\n'
            
            new_skills_text += skill_text
            added += 1
            self.thread_safe_log(f"   ➕ {json_skill['name']}")
        
        # Aplicar modificações (da última pra primeira)
        for mod in sorted(modifications, key=lambda x: x['start'], reverse=True):
            self.xml_content = (
                self.xml_content[:mod['start']] +
                mod['new_text'] +
                self.xml_content[mod['end']:]
            )
            self.thread_safe_log(f"   ✏️ {mod['name']}")
        
        # Adicionar novas skills ANTES do </skillTree> com linha extra no final
        if new_skills_text:
            # Adicionar comentário identificador
            comment = f'{indent}<!-- Samurai Crow -->\n'
            new_skills_text = comment + new_skills_text
            
            # Encontrar o início da linha do </skillTree> (incluindo whitespace)
            line_start = self.xml_content.rfind('\n', 0, skilltree_end)
            if line_start == -1:
                line_start = 0
            else:
                line_start += 1  # Pular o \n
            
            # Inserir antes da linha do </skillTree>
            self.xml_content = (
                self.xml_content[:line_start] +
                new_skills_text +
                self.xml_content[line_start:]
            )
        
        self.thread_safe_log(f"\n✏️ Atualizadas: {updated}")
        self.thread_safe_log(f"✅ Adicionadas: {added}")
        self.thread_safe_log(f"⏭️ Puladas: {skipped}")
        
        self.stats['skills_modified'] = updated
        self.stats['skills_added'] = added
        self.stats['skipped_common'] = skipped
        
        # Guardar texto para preview (com comentários)
        self.xml_text_preview = self.xml_content
        
        # Criar xml_root fake para compatibilidade (parse do conteúdo atualizado)
        try:
            self.xml_root = ET.fromstring(self.xml_content)
        except:
            # Se falhar, criar um elemento vazio
            self.xml_root = ET.Element('root')

    def _detect_indent(self) -> str:
        """Detecta indentação usada no XML"""
        # Procurar primeira skill e ver quantos tabs/espaços tem antes
        skill_pos = self.xml_content.find('<skill ')
        if skill_pos == -1:
            return '\t\t'
        
        # Voltar até achar newline
        line_start = self.xml_content.rfind('\n', 0, skill_pos)
        if line_start == -1:
            return '\t\t'
        
        indent = self.xml_content[line_start+1:skill_pos]
        return indent if indent.strip() == '' else '\t\t'

    def save_xml(self, xml_content=None):
        """Salva XML preservando estrutura original
        
        Args:
            xml_content: Se for string, salva ela (edições manuais do preview)
                        Se for None, salva self.xml_content (processado)
                        Se for Element, IGNORA (não preserva comentários)
        """
        try:
            if xml_content is not None and isinstance(xml_content, str):
                # Edição manual do preview - salvar o que foi editado
                content = xml_content
                self.thread_safe_log("📝 Salvando edições manuais do preview...")
            elif isinstance(xml_content, ET.Element):
                # Element da UI - IGNORAR e usar texto puro
                content = self.xml_content
                self.thread_safe_log("📝 Ignorando Element, usando texto puro...")
            else:
                # Padrão - usa o conteúdo processado
                content = self.xml_content
                self.thread_safe_log("📝 Salvando XML processado...")
            
            if not content:
                self.thread_safe_log("❌ Nenhum conteúdo XML em memória")
                return
            
            with open(self.output_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            self.thread_safe_log(f"✅ XML salvo: {self.output_path}")
        except Exception as e:
            self.thread_safe_log(f"❌ Erro ao salvar: {e}")
            import traceback
            self.thread_safe_log(traceback.format_exc())

    def thread_safe_log(self, message):
        self.log_signal.emit(message)

    def stop(self):
        self.is_running = False

    def get_diff_summary(self):
        return {
            'total_differences': len(self.diffs),
            'additions': sum(1 for d in self.diffs if d.change_type == 'added'),
            'removals': sum(1 for d in self.diffs if d.change_type == 'removed'),
            'modifications': sum(1 for d in self.diffs if d.change_type == 'modified'),
            'details': [
                {
                    'id': d.skill_id,
                    'level': d.level,
                    'type': d.change_type,
                    'field': d.field,
                    'before': d.old_value,
                    'after': d.new_value
                }
                for d in self.diffs
            ]
        }
    
    def get_preview_text(self):
        """Retorna texto completo para preview (com comentários)"""
        return self.xml_text_preview if self.xml_text_preview else self.xml_content
    
    def validate_skill_ids(self, json_data: Dict, xml_skills: Dict):
        """Valida se os IDs e nomes das skills batem com o database"""
        self.thread_safe_log("\n🔍 Validando IDs de skills...")
        
        issues_found = 0
        
        for key, json_skill in json_data.items():
            skill_name = json_skill['name']
            skill_id = json_skill['skill_id']
            skill_level = json_skill['level']
            
            # Validar se ID bate com o nome
            is_valid = self.skill_parser.validate_skill(skill_name, skill_id, skill_level)
            
            if not is_valid:
                # Buscar matches possíveis
                matches = self.skill_parser.find_by_name(skill_name)
                
                if matches:
                    self.id_validation_issues.append({
                        'skill_name': skill_name,
                        'current_id': skill_id,
                        'current_level': skill_level,
                        'suggested_matches': matches,
                        'severity': 'warning'
                    })
                    
                    issues_found += 1
                    self.thread_safe_log(f"  ⚠️ '{skill_name}' (ID:{skill_id}, Lv:{skill_level}) - ID may be incorrect")
                    self.thread_safe_log(f"     Suggested: ID:{matches[0].skill_id}, Lv:{matches[0].level}")
                else:
                    self.id_validation_issues.append({
                        'skill_name': skill_name,
                        'current_id': skill_id,
                        'current_level': skill_level,
                        'suggested_matches': [],
                        'severity': 'error'
                    })
                    
                    issues_found += 1
                    self.thread_safe_log(f"  ❌ '{skill_name}' - NOT FOUND in database")
        
        if issues_found == 0:
            self.thread_safe_log("  ✅ All skill IDs validated successfully")
        else:
            self.thread_safe_log(f"  ⚠️ Found {issues_found} validation issues")