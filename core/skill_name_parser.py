import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Tuple, List, Optional
from dataclasses import dataclass

@dataclass
class SkillMatch:
    """Representa um match de skill encontrado"""
    skill_id: str
    skill_name: str
    sublevel: str
    description: str 
    desc_params: str 
    level: str
    confidence: float = 1.0

class SkillNameParser:
    """Lê skill names de XMLs L2 ou .dat com validação e fuzzy search"""
    
    def __init__(self, dat_file: str = "databases/skills_main.dat"):
        self.dat_file = Path(dat_file)
        self.skill_map = {}  # name_lower -> [(id, name, level), ...]
        self.id_map = {}     # id -> [(name, level), ...]
        self._load_from_dat()
    
    def _load_from_dat(self):
        """Tenta carregar de arquivo .dat ou busca em XMLs"""
        if self.dat_file.exists():
            self._parse_dat_file()
        else:
            print(f"⚠️ {self.dat_file} não encontrado, buscando XMLs...")
            self._load_from_xml_folder()
    
    def _parse_dat_file(self):
        """Parser direto para .dat - 1 skill por linha"""
        try:
            with open(self.dat_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or not line.startswith('skill_begin'):
                        continue
                    
                    # Inicialização limpa para garantir o tamanho da tupla
                    s_id = None
                    s_lvl = '1'
                    s_sub = '0'
                    s_name = "Unknown"
                    s_desc = ""
                    s_param = ""

                    # Extração individual para não sobrescrever variáveis
                    if 'skill_id=' in line:
                        start = line.find('skill_id=') + 9
                        end = line.find('\t', start)
                        if end == -1: end = line.find(' ', start)
                        s_id = line[start:end].strip()
                    
                    if 'skill_level=' in line:
                        start = line.find('skill_level=') + 12
                        end = line.find('\t', start)
                        if end == -1: end = line.find(' ', start)
                        s_lvl = line[start:end].strip()

                    if 'skill_sublevel=' in line:
                        start = line.find('skill_sublevel=') + 15
                        end = line.find('\t', start)
                        if end == -1: end = line.find(' ', start)
                        s_sub = line[start:end].strip()
                    
                    if 'name=[' in line:
                        start = line.find('name=[') + 6
                        end = line.find(']', start)
                        s_name = line[start:end].strip()

                    if 'desc=[' in line:
                        start = line.find('desc=[') + 6
                        end = line.find(']', start)
                        s_desc = line[start:end].strip()

                    if 'desc_param=[' in line:
                        start = line.find('desc_param=[') + 12
                        end = line.find(']', start)
                        s_param = line[start:end].strip()
                    
                    # Indexação mantendo os índices [0, 1, 2] originais
                    if s_id and s_name:
                        name_key = s_name.lower()
                        full_data = (s_id, s_name, s_lvl, s_sub, s_desc, s_param)
                        
                        # Garante que a chave exista como lista ANTES de dar append
                        if name_key not in self.skill_map:
                            self.skill_map[name_key] = []
                        self.skill_map[name_key].append(full_data)
                        
                        # MESMA COISA AQUI PARA O ID_MAP
                        if s_id not in self.id_map:
                            self.id_map[s_id] = []
                        
                        # IMPORTANTE: Verifique se este nível já não existe para não duplicar
                        # mas sempre dê o append para acumular os níveis 1, 2, 3...
                        self.id_map[s_id].append(full_data)
            
            print(f"✅ Parser concluído: {len(self.id_map)} skills carregadas.")
                
        except Exception as e:
            print(f"❌ Erro ao carregar {self.dat_file}: {e}")
            import traceback
            traceback.print_exc()
    
    def _load_from_xml_folder(self):
        """Carrega skill names de todos os XMLs na pasta skilltree"""
        try:
            skilltree_dir = Path("skilltree")
            if not skilltree_dir.exists():
                print(f"⚠️ Pasta {skilltree_dir} não encontrada")
                return
            
            xml_files = list(skilltree_dir.rglob("*.xml"))
            print(f"📂 Encontrados {len(xml_files)} arquivos XML")
            
            for xml_file in xml_files:
                try:
                    tree = ET.parse(xml_file)
                    root = tree.getroot()
                    
                    for skill in root.findall('.//skill'):
                        skill_id = skill.get('skillId')
                        skill_name = skill.get('skillName')
                        skill_level = skill.get('skillLevel', '1')
                        
                        if skill_id and skill_name:
                            name_key = skill_name.lower()
                            if name_key not in self.skill_map:
                                self.skill_map[name_key] = []
                            
                            # Evitar duplicatas
                            if not any(s[0] == skill_id and s[2] == skill_level for s in self.skill_map[name_key]):
                                self.skill_map[name_key].append((skill_id, skill_name, skill_level))
                            
                            if skill_id not in self.id_map:
                                self.id_map[skill_id] = []
                            if not any(s[0] == skill_name and s[1] == skill_level for s in self.id_map[skill_id]):
                                self.id_map[skill_id].append((skill_name, skill_level))
                
                except Exception:
                    pass
            
            if len(self.skill_map) > 0:
                print(f"✅ Carregadas {len(self.skill_map)} skills dos XMLs")
            else:
                print(f"⚠️ Nenhuma skill carregada dos XMLs")
                
        except Exception as e:
            print(f"❌ Erro ao carregar XMLs: {e}")
    
    def get_skill_id_by_name(self, skill_name: str) -> str:
        """Retorna ID da skill dado o nome (primeiro match, menor level)"""
        matches = self.skill_map.get(skill_name.lower(), [])
        if matches:
            # Ordenar por level e retornar o primeiro
            sorted_matches = sorted(matches, key=lambda x: int(x[2]))
            return sorted_matches[0][0]
        return None
    
    def get_skill_ids_by_names(self, skill_names: List[str]) -> Tuple[List[str], List[str]]:
        """Retorna (IDs encontradas, nomes não encontrados)"""
        found_ids = []
        unfound_names = []
        
        for name in skill_names:
            skill_id = self.get_skill_id_by_name(name)
            if skill_id:
                if skill_id not in found_ids:
                    found_ids.append(skill_id)
            else:
                unfound_names.append(name)
        
        return found_ids, unfound_names
    
    def get_skill_name_by_id(self, skill_id: str) -> str:
        """Retorna nome da skill dado o ID (primeiro match)"""
        matches = self.id_map.get(str(skill_id), [])
        if matches:
            return matches[0][0]
        return None
    
    # ====== NOVAS FUNCIONALIDADES ======
    
    def find_by_name(self, skill_name: str, fuzzy: bool = True) -> List[SkillMatch]:
        """Busca skills pelo nome (exato ou fuzzy)"""
        name_key = skill_name.lower().strip()
        
        # Busca exata
        exact_matches = self.skill_map.get(name_key, [])
        if exact_matches:
            results = []
            for skill_id, name, level in sorted(exact_matches, key=lambda x: int(x[2])):
                results.append(SkillMatch(
                    skill_id=skill_id,
                    skill_name=name,
                    level=level,
                    confidence=1.0
                ))
            return results
        
        if not fuzzy:
            return []
        
        # Busca fuzzy
        similar_matches = []
        for cached_name, skills in self.skill_map.items():
            confidence = self._calculate_similarity(name_key, cached_name)
            if confidence > 0.7:
                for skill_id, name, level in skills:
                    similar_matches.append(SkillMatch(
                        skill_id=skill_id,
                        skill_name=name,
                        level=level,
                        confidence=confidence
                    ))
        
        return sorted(similar_matches, key=lambda x: (-x.confidence, int(x.level)))
    
    def find_by_id(self, skill_id: str) -> List[SkillMatch]:
        """Busca skills pelo ID"""
        matches = self.id_map.get(skill_id, [])
        results = []
        for name, level in matches:
            results.append(SkillMatch(
                skill_id=skill_id,
                skill_name=name,
                level=level,
                confidence=1.0
            ))
        return results
    
    def validate_skill(self, skill_name: str, skill_id: str, skill_level: str = "1") -> bool:
        """Valida se nome, ID e level batem"""
        matches = self.skill_map.get(skill_name.lower(), [])
        
        for sid, sname, slevel in matches:
            if sid == skill_id and slevel == skill_level:
                return True
        
        return False
    
    def get_best_match(self, skill_name: str, preferred_level: str = "1") -> Optional[SkillMatch]:
        """Retorna o melhor match para um nome de skill"""
        matches = self.find_by_name(skill_name)
        
        if not matches:
            return None
        
        # Tentar achar o nível preferido
        for match in matches:
            if match.level == preferred_level:
                return match
        
        # Se não achou, retornar o primeiro (menor nível)
        return matches[0]
    
    def resolve_removed_skills(self, removed_names: List[str]) -> dict:
        """Resolve múltiplos nomes de skills removidas"""
        results = {}
        
        for name in removed_names:
            matches = self.find_by_name(name)
            results[name] = matches if matches else []
        
        return results
    
    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """Calcula similaridade entre duas strings (Levenshtein)"""
        if str1 == str2:
            return 1.0
        
        # Substring check
        if str1 in str2 or str2 in str1:
            return 0.85
        
        # Levenshtein distance
        len1, len2 = len(str1), len(str2)
        if len1 == 0 or len2 == 0:
            return 0.0
        
        matrix = [[0] * (len2 + 1) for _ in range(len1 + 1)]
        
        for i in range(len1 + 1):
            matrix[i][0] = i
        for j in range(len2 + 1):
            matrix[0][j] = j
        
        for i in range(1, len1 + 1):
            for j in range(1, len2 + 1):
                cost = 0 if str1[i-1] == str2[j-1] else 1
                matrix[i][j] = min(
                    matrix[i-1][j] + 1,
                    matrix[i][j-1] + 1,
                    matrix[i-1][j-1] + cost
                )
        
        distance = matrix[len1][len2]
        max_len = max(len1, len2)
        similarity = 1.0 - (distance / max_len)
        
        return similarity