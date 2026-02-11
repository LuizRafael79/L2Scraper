from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                           QPushButton, QLabel, QProgressBar, QTextEdit,
                           QGroupBox, QGridLayout, QCheckBox, QFrame)
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QTextCursor
from workers.scraper_worker import ScraperWorker
from utils.scraping_stats import ScrapingStats

class EssenceTab(QWidget):
    stats_updated = pyqtSignal()
    worker_created = pyqtSignal(object, str)
    
    def __init__(self, config, database):
        super().__init__()
        self.config = config
        self.database = database
        self.scraper_worker = None
        self.site_type = "essence"
        
        # 🎯 CORRIGIDO: Carregar stats salvos do config
        self.stats = ScrapingStats()
        saved_stats = self.config.load_stats(self.site_type)
        for key, value in saved_stats.items():
            if hasattr(self.stats, key):
                setattr(self.stats, key, value)
        
        self.setup_ui()
        self.update_site_stats()  # ← Varre JSONs ao abrir!

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Controles
        controls_layout = QHBoxLayout()

        # 🆕 NOVO BOTÃO: Generate Items Lists
        self.generate_items_btn = QPushButton("🔧 Generate Items Lists")
        self.generate_items_btn.setToolTip("Generate item lists from DAT file (run after updating DAT)")
        controls_layout.addWidget(self.generate_items_btn)
        
        # Separador visual
        separator = QLabel("|")
        separator.setStyleSheet("color: gray; font-weight: bold;")
        controls_layout.addWidget(separator)

        self.full_scan_check = QCheckBox("🔄 Full Scan (all items)")
        self.full_scan_check.setToolTip("Check to scan ALL items from DAT, uncheck for incremental (only new/failed)")
        controls_layout.addWidget(self.full_scan_check)
        
        self.start_btn = QPushButton("🚀 Start Essence Scraping")
        self.pause_btn = QPushButton("⏸️ Pause")
        self.stop_btn = QPushButton("🛑 Stop")
        self.retry_btn = QPushButton("🔄 Retry Failed")
        
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.retry_btn.setEnabled(False)
        
        controls_layout.addWidget(self.start_btn)
        controls_layout.addWidget(self.pause_btn)
        controls_layout.addWidget(self.stop_btn)
        controls_layout.addWidget(self.retry_btn)
        controls_layout.addStretch()
        
        # Progresso
        progress_layout = QVBoxLayout()
        self.progress_bar = QProgressBar()
        self.status_label = QLabel("Ready")
        progress_layout.addWidget(QLabel("Progress:"))
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.status_label)
        
        # Estatísticas
        stats_group = QGroupBox("📊 Essence Statistics")
        stats_main_layout = QVBoxLayout(stats_group)
        
        # Estatísticas gerais
        general_layout = QGridLayout()
        
        self.total_label = QLabel("Total: 0")
        self.processed_label = QLabel("Processed: 0")
        self.success_label = QLabel("✅ Extractable: 0")
        self.not_found_label = QLabel("❌ Not Found: 0")
        self.failed_label = QLabel("⚠️ Failed: 0")
        self.rate_label = QLabel("Success Rate: 0%")
        
        general_layout.addWidget(self.total_label, 0, 0)
        general_layout.addWidget(self.processed_label, 0, 1)
        general_layout.addWidget(self.success_label, 1, 0)
        general_layout.addWidget(self.not_found_label, 1, 1)
        general_layout.addWidget(self.failed_label, 2, 0)
        general_layout.addWidget(self.rate_label, 2, 1)
        
        stats_main_layout.addLayout(general_layout)
        
        # Separador
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        stats_main_layout.addWidget(line)
        
        # Boxes layout
        boxes_layout = QHBoxLayout()
        
        # Item Boxes
        item_box_group = QGroupBox("📦 Item Boxes")
        item_box_layout = QVBoxLayout(item_box_group)
        
        self.item_box_count_label = QLabel("Total: 0")
        self.item_box_count_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        
        self.item_guaranteed_label = QLabel("  └─ Guaranteed: 0")
        self.item_random_label = QLabel("  └─ Random: 0")
        self.item_possible_label = QLabel("  └─ Possible: 0")
        
        item_box_layout.addWidget(self.item_box_count_label)
        item_box_layout.addWidget(self.item_guaranteed_label)
        item_box_layout.addWidget(self.item_random_label)
        item_box_layout.addWidget(self.item_possible_label)
        item_box_layout.addStretch()
        
        # Skill Boxes
        skill_box_group = QGroupBox("⚔️ Skill Boxes")
        skill_box_layout = QVBoxLayout(skill_box_group)
        
        self.skill_box_count_label = QLabel("Total: 0")
        self.skill_box_count_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        
        self.skill_guaranteed_label = QLabel("  └─ Guaranteed: 0")
        self.skill_random_label = QLabel("  └─ Random: 0")
        self.skill_possible_label = QLabel("  └─ Possible: 0")
        
        skill_box_layout.addWidget(self.skill_box_count_label)
        skill_box_layout.addWidget(self.skill_guaranteed_label)
        skill_box_layout.addWidget(self.skill_random_label)
        skill_box_layout.addWidget(self.skill_possible_label)
        skill_box_layout.addStretch()
        
        boxes_layout.addWidget(item_box_group)
        boxes_layout.addWidget(skill_box_group)
        
        stats_main_layout.addLayout(boxes_layout)
        
        # Log
        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(300)
        log_layout.addWidget(self.log_text)
        
        # Montagem final
        layout.addLayout(controls_layout)
        layout.addLayout(progress_layout)
        layout.addWidget(stats_group)
        layout.addWidget(log_group, 1)
        
        # Conexões
        self.setup_connections()
        
    def setup_connections(self):
        self.generate_items_btn.clicked.connect(self.generate_items_lists)  # 🆕
        self.start_btn.clicked.connect(self.start_scraping)
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.stop_btn.clicked.connect(self.stop_scraping)
        self.retry_btn.clicked.connect(self.retry_failed)

    # 🆕 NOVO MÉTODO: Generate Items Lists
    def generate_items_lists(self):
        """Gera os 3 JSONs de items a partir do DAT"""
        self.log("🔧 Generating items lists from DAT...")
        self.generate_items_btn.setEnabled(False)
        
        try:
            counts = self.database.generate_items_lists(self.site_type)
            self.log(f"✅ Items lists generated successfully:")
            self.log(f"   📝 items_{self.site_type}_action_skill_reduce_on_skill_success.json: {counts['skill_reduce_on_skill_success']} items")
            self.log(f"   📝 items_{self.site_type}_action_skill_reduce.json: {counts['skill_reduce']} items")
            self.log(f"   📝 items_{self.site_type}_action_peel.json: {counts['peel']} items")
            self.log(f"   🎯 Total extractable items: {sum(counts.values())}")
            
            # Atualizar stats display
            site_stats = self.config.get_site_stats(self.site_type)
            self.update_site_stats(site_stats)
            
        except FileNotFoundError as e:
            self.log(f"❌ Error: {str(e)}")
            self.log("Make sure the DAT file exists in databases/ folder")
        except Exception as e:
            self.log(f"❌ Error generating lists: {str(e)}")
        finally:
            self.generate_items_btn.setEnabled(True)

    def update_site_stats(self, site_stats):
        """Atualiza estatísticas do site na UI"""
        self.log(f"📊 {self.site_type.upper()} - Total in dat: {site_stats['total_in_dat']}, Extractable: {site_stats['extractable_count']}")
        self.log(f"📈 Previously: {site_stats['processed']} processed, {site_stats['failed']} failed, {site_stats['not_found']} not found")       

    def start_scraping(self):
        if not self.scraper_worker or not self.scraper_worker.isRunning():
            self.scraper_worker = ScraperWorker(
                self.site_type,
                self.config,
                full_scan=self.full_scan_check.isChecked()
                )
            
            self.scraper_worker.log_signal.connect(self.log)
            self.scraper_worker.progress_signal.connect(self.update_progress)
            self.scraper_worker.stats_signal.connect(self.update_stats)
            self.scraper_worker.finished.connect(self.scraping_finished)
            
            self.worker_created.emit(self.scraper_worker, self.site_type)
            
            self.scraper_worker.start()
            self.update_controls(True)
            self.log("🚀 Starting Essence site scraping...")
            
    def toggle_pause(self):
        if self.scraper_worker:
            self.scraper_worker.is_paused = not self.scraper_worker.is_paused
            self.pause_btn.setText("▶️ Resume" if self.scraper_worker.is_paused else "⏸️ Pause")
            self.log("⏸️ Scraping paused" if self.scraper_worker.is_paused else "▶️ Scraping resumed")
            
    def stop_scraping(self):
        if self.scraper_worker:
            self.scraper_worker.is_running = False
            if self.scraper_worker.isRunning():
                self.scraper_worker.wait(5000)
            self.update_controls(False)
            self.log("🛑 Scraping stopped - Progress Saved")
            
    def retry_failed(self):
        self.config.clear_failed_items("essence")
        self.start_scraping()
        self.log("🔄 Retrying failed items for Essence site...")
        
    def update_controls(self, running):
        self.start_btn.setEnabled(not running)
        self.pause_btn.setEnabled(running)
        self.stop_btn.setEnabled(running)
        self.retry_btn.setEnabled(not running)
        self.generate_items_btn.setEnabled(not running)  # 🆕 Desabilita durante scraping
        
    def log(self, message):
        self.log_text.append(message)
        scrollbar = self.log_text.verticalScrollBar()
        if scrollbar is not None and scrollbar.value() == scrollbar.maximum():
            cursor = self.log_text.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.log_text.setTextCursor(cursor)
        
    def update_progress(self, current, total, status):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_label.setText(status)
        
    def update_stats(self, stats_data):
        """🎯 CORRIGIDO: Atualiza stats E salva no config"""
        self.stats.update_from_dict(stats_data)
        self.update_stats_display()
        
        # Salvar no config para persistência
        self.config.save_stats(self.site_type, stats_data)
        
        # Notificar que stats foram atualizados (para Global Stats)
        self.stats_updated.emit()
        
    def update_stats_display(self):
        # Gerais
        self.total_label.setText(f"Total: {self.stats.total_items}")
        self.processed_label.setText(f"Processed: {self.stats.processed_items}")
        self.success_label.setText(f"✅ Extractable: {self.stats.successful_items}")
        self.not_found_label.setText(f"❌ Not Found: {self.stats.not_found_items}")
        self.failed_label.setText(f"⚠️ Failed: {self.stats.failed_items}")
        
        rate = (self.stats.successful_items / self.stats.processed_items * 100) if self.stats.processed_items > 0 else 0
        self.rate_label.setText(f"Success Rate: {rate:.1f}%")
        
        # Item Boxes
        self.item_box_count_label.setText(f"Total: {self.stats.item_box_found}")
        self.item_guaranteed_label.setText(f"  └─ Guaranteed: {self.stats.item_guaranteed}")
        self.item_random_label.setText(f"  └─ Random: {self.stats.item_random}")
        self.item_possible_label.setText(f"  └─ Possible: {self.stats.item_possible}")
        
        # Skill Boxes
        self.skill_box_count_label.setText(f"Total: {self.stats.skill_box_found}")
        self.skill_guaranteed_label.setText(f"  └─ Guaranteed: {self.stats.skill_guaranteed}")
        self.skill_random_label.setText(f"  └─ Random: {self.stats.skill_random}")
        self.skill_possible_label.setText(f"  └─ Possible: {self.stats.skill_possible}")
        
    def scraping_finished(self):
        """🎯 CORRIGIDO: Recarregar stats ao finalizar"""
        # Recarregar stats do config (em caso de ter sido atualizado externamente)
        saved_stats = self.config.load_stats(self.site_type)
        for key, value in saved_stats.items():
            if hasattr(self.stats, key):
                setattr(self.stats, key, value)
        
        self.update_stats_display()
        self.update_controls(False)
        self.status_label.setText("Finished")
        self.log("✅ Essence site scraping completed!")
        self.stats_updated.emit()

    def update_site_stats(self):
        """Varre JSONs e atualiza estatísticas REAIS da UI"""
        import json
        from pathlib import Path
        
        try:
            self.log(f"📊 Scanning JSON statistics for {self.site_type.upper()}...")
            
            # Diretório base dos items
            items_dir = Path(f"html_items_{self.site_type}")
            
            if not items_dir.exists():
                self.log(f"⚠️ Directory not found: {items_dir}")
                return
            
            # Contadores
            stats = {
                'item_box_found': 0,
                'skill_box_found': 0,
                'item_guaranteed': 0,
                'item_random': 0,
                'item_possible': 0,
                'skill_guaranteed': 0,
                'skill_random': 0,
                'skill_possible': 0,
            }
            
            # Varrer todos os JSONs
            json_files = list(items_dir.glob('*/data.json'))
            
            for json_file in json_files:
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # Verificar se é item ou skill box
                    scraping_info = data.get('scraping_info', {})
                    has_skills = scraping_info.get('has_skills', False)
                    
                    box_data = data.get('box_data', {})
                    guaranteed = len(box_data.get('guaranteed_items', []))
                    random_items = len(box_data.get('random_items', []))
                    possible = len(box_data.get('possible_items', []))
                    
                    # Contabilizar
                    if has_skills:
                        stats['skill_box_found'] += 1
                        stats['skill_guaranteed'] += guaranteed
                        stats['skill_random'] += random_items
                        stats['skill_possible'] += possible
                    else:
                        stats['item_box_found'] += 1
                        stats['item_guaranteed'] += guaranteed
                        stats['item_random'] += random_items
                        stats['item_possible'] += possible
                    
                except Exception as e:
                    self.log(f"⚠️ Error reading {json_file.name}: {e}")
                    continue
            
            # Atualizar ScrapingStats
            self.stats.item_box_found = stats['item_box_found']
            self.stats.skill_box_found = stats['skill_box_found']
            self.stats.item_guaranteed = stats['item_guaranteed']
            self.stats.item_random = stats['item_random']
            self.stats.item_possible = stats['item_possible']
            self.stats.skill_guaranteed = stats['skill_guaranteed']
            self.stats.skill_random = stats['skill_random']
            self.stats.skill_possible = stats['skill_possible']
            
            # Atualizar UI
            self.update_stats_display()
            
            # Log resumido
            total_items = stats['item_box_found']
            total_skills = stats['skill_box_found']
            
            self.log(f"✅ Scan complete:")
            self.log(f"   📦 Item Boxes: {total_items}")
            self.log(f"      └─ Guaranteed: {stats['item_guaranteed']}, Random: {stats['item_random']}, Possible: {stats['item_possible']}")
            self.log(f"   ⚔️ Skill Boxes: {total_skills}")
            self.log(f"      └─ Guaranteed: {stats['skill_guaranteed']}, Random: {stats['skill_random']}, Possible: {stats['skill_possible']}")
            
        except Exception as e:
            self.log(f"❌ Error scanning statistics: {e}")
            import traceback
            traceback.print_exc()