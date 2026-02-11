from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QListWidget, QStackedWidget,
                           QLabel, QGroupBox, QMessageBox, QToolBar, QListWidgetItem)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QFont
from utils.theme import DarkTheme
from tabs.essence_tab import EssenceTab
from tabs.main_tab import MainTab
from tabs.relics_tab import RelicsTab
from tabs.skillstree_tab import SkillTreeTab
from tabs.skilltreebuilder_tab import SkillTreeBuilderTab  # 🆕 NOVA IMPORTAÇÃO
from tabs.skill_analyser import SkillParserTab
from config.config_manager import ConfigManager
from utils.audit_window import AuditWindow
from tabs.item_builder_tab import ItemBuilderTab
from core.database import DatabaseManager
from core.handlers.skill_handler import SkillHandler
from core.handlers.scraper_handler import ScraperHandler
from core.handlers.xml_handler import XMLHandler
from tabs.skill_enchant_tab import SkillEnchantTab

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.app_config = ConfigManager()
        self.scraper_handler = ScraperHandler()
        self.xml_handler = XMLHandler()
        self.database = DatabaseManager(self.app_config)
        self.audit_window = AuditWindow()
        self.skill_handler = SkillHandler(
            xml_handler=self.xml_handler,
            scraper_handler=self.scraper_handler,
            database=self.database
        )
        self.setup_ui()
        self.setup_connections()
        
        # 🎯 Timer para atualizar stats globais periodicamente
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self.update_global_stats)
        self.stats_timer.start(10000)  # Atualiza a cada 10 segundos
        
        # Atualizar stats globais no início
        self.update_global_stats()
        
    def setup_ui(self):
        self.setWindowTitle("L2Wiki Mass Scraper - Modern")
        self.resize(1200, 800)
        self.setMinimumSize(1024, 720)
        self.setStyleSheet(DarkTheme.get_stylesheet())
        
        self.setup_toolbar()
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        
        # ===== BARRA LATERAL =====
        sidebar = QWidget()
        sidebar.setFixedWidth(250)
        sidebar_layout = QVBoxLayout(sidebar)
        
        title = QLabel("L2Wiki Scraper")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; padding: 20px;")
        sidebar_layout.addWidget(title)
        
        # Lista de abas com categorias
        self.tab_list = QListWidget()
        self.tab_list.setSpacing(2)
        
        # ========== CATEGORIA: BUILDERS ==========
        builders_header = QListWidgetItem("═══ BUILDERS ═══")
        builders_header.setFlags(Qt.ItemFlag.NoItemFlags)  # Não selecionável
        font = QFont()
        font.setBold(True)
        font.setPointSize(10)
        builders_header.setFont(font)
        builders_header.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tab_list.addItem(builders_header)
        
        self.tab_list.addItem("🔧 Relics XML Builder")
        self.tab_list.addItem("🔧 Extractable Builder")
        self.tab_list.addItem("⚙️ SkillTree XML Builder")  # 🆕 NOVA ABA
        
        # Espaçador
        spacer1 = QListWidgetItem("")
        spacer1.setFlags(Qt.ItemFlag.NoItemFlags)
        self.tab_list.addItem(spacer1)
        
        # ========== CATEGORIA: SCRAPERS ==========
        scrapers_header = QListWidgetItem("═══ SCRAPERS ═══")
        scrapers_header.setFlags(Qt.ItemFlag.NoItemFlags)
        scrapers_header.setFont(font)
        scrapers_header.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tab_list.addItem(scrapers_header)
        
        self.tab_list.addItem("📦 Essence Items")
        self.tab_list.addItem("📦 Main Items")
        self.tab_list.addItem("🎯 Skills Index")
        
        # Espaçador
        spacer2 = QListWidgetItem("")
        spacer2.setFlags(Qt.ItemFlag.NoItemFlags)
        self.tab_list.addItem(spacer2)
        
        # ========== CATEGORIA: TOOLS ==========
        tools_header = QListWidgetItem("═══ TOOLS ═══")
        tools_header.setFlags(Qt.ItemFlag.NoItemFlags)
        tools_header.setFont(font)
        tools_header.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tab_list.addItem(tools_header)
        
        self.tab_list.addItem("⚡ Skill Analyser")
        self.tab_list.addItem("🪄 Enchant Exporter") # Adicione este item
        
        # Selecionar primeiro item clicável (Relics Builder)
        self.tab_list.setCurrentRow(1)
        
        sidebar_layout.addWidget(self.tab_list)
        sidebar_layout.addStretch()
        
        # Estatísticas globais
        stats_group = QGroupBox("Global Stats")
        stats_layout = QVBoxLayout(stats_group)
        
        self.global_total = QLabel("Total: 0")
        self.global_processed = QLabel("Processed: 0")
        self.global_success = QLabel("Success: 0")
        self.global_failed = QLabel("Failed: 0")
        
        for widget in [self.global_total, self.global_processed, 
                      self.global_success, self.global_failed]:
            stats_layout.addWidget(widget)
        
        sidebar_layout.addWidget(stats_group)
        
        # ===== ÁREA DE CONTEÚDO =====
        content_area = QWidget()
        content_layout = QVBoxLayout(content_area)
        
        self.stacked_widget = QStackedWidget()

        # SCRAPERS (criar primeiro para passar referência)
        self.essence_tab = EssenceTab(self.app_config, self.database)
        self.main_tab = MainTab(self.app_config, self.database)
        self.skilltree_tab = SkillTreeTab(self.app_config, self.database)
        
        # BUILDERS
        self.relics_builder_tab = RelicsTab(self.app_config)
        self.item_builder_tab = ItemBuilderTab(
            self.app_config, 
            self.database,
            self.xml_handler,
            self.scraper_handler,
            self.skill_handler
        )
        self.skilltree_builder_tab = SkillTreeBuilderTab(  # 🆕 NOVA
            self.app_config,
            self.database,
            self.skilltree_tab  # 📌 Passar referência do scraper
        )
        
        # TOOLS
        self.skill_analyser_tab = SkillParserTab(self.app_config, self.database)
        self.skill_enchant_tab = SkillEnchantTab(
            self.app_config,
            self.database, 
            self.skilltree_tab,
            self.scraper_handler)

        # Adicionar todas as tabs ao stacked widget
        self.stacked_widget.addWidget(self.relics_builder_tab)         # Index 0
        self.stacked_widget.addWidget(self.item_builder_tab)           # Index 1
        self.stacked_widget.addWidget(self.skilltree_builder_tab)      # Index 2 🆕
        self.stacked_widget.addWidget(self.essence_tab)                # Index 3
        self.stacked_widget.addWidget(self.main_tab)                   # Index 4
        self.stacked_widget.addWidget(self.skilltree_tab)              # Index 5
        self.stacked_widget.addWidget(self.skill_analyser_tab)         # Index 6
        self.stacked_widget.addWidget(self.skill_enchant_tab) # Será o index 7
        
        content_layout.addWidget(self.stacked_widget)
        
        main_layout.addWidget(sidebar)
        main_layout.addWidget(content_area, 1)
        self.showMaximized()
        
    def setup_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        
        audit_action = QAction("🔍 Auditoria", self)
        audit_action.setStatusTip("Abrir janela de auditoria em tempo real")
        audit_action.triggered.connect(self.show_audit_window)
        toolbar.addAction(audit_action)
        
        toolbar.addSeparator()
        
        export_audit_action = QAction("💾 Exportar Auditoria", self)
        export_audit_action.setStatusTip("Exportar relatório de auditoria completo")
        export_audit_action.triggered.connect(self.export_audit_report)
        toolbar.addAction(export_audit_action)
        
    def setup_connections(self):
        # Conectar lista de abas com filtro de headers
        self.tab_list.currentRowChanged.connect(self.on_tab_changed)
        
        self.essence_tab.stats_updated.connect(self.update_global_stats)
        self.main_tab.stats_updated.connect(self.update_global_stats)
        self.skilltree_tab.stats_updated.connect(self.update_global_stats)
        
        self.connect_audit_signals()
    
    def on_tab_changed(self, row):
        """Mapeia row da lista para index do stacked widget, ignorando headers"""
        # Mapeamento: row da lista -> index do stacked widget
        tab_mapping = {
            1: 0,  # Relics Builder
            2: 1,  # Extractable Builder
            3: 2,  # 🆕 SkillTree XML Builder
            6: 3,  # Essence Items (pula spacer no index 4)
            7: 4,  # Main Items
            8: 5,  # Skills Index
            11: 6, # Skill Analyser (pula spacer no index 9)
            12: 7, # ✨ Nova aba: Enchant Exporter
        }
        
        if row in tab_mapping:
            self.stacked_widget.setCurrentIndex(tab_mapping[row])
       
    def connect_audit_signals(self):
        self.essence_tab.worker_created.connect(self.on_worker_created)
        self.main_tab.worker_created.connect(self.on_worker_created)
        self.skilltree_tab.worker_created.connect(self.on_worker_created)
    
    def on_worker_created(self, worker, site_type):
        worker.audit_signal.connect(self.audit_window.add_audit_entry)
        print(f"✅ Conectado worker de {site_type} à auditoria")
    
    def show_audit_window(self):
        if self.audit_window.isHidden():
            self.audit_window.show()
            self.audit_window.raise_()
            self.audit_window.activateWindow()
        else:
            self.audit_window.hide()
    
    def export_audit_report(self):
        try:
            self.audit_window.export_audit()
            QMessageBox.information(self, "Exportação Concluída", 
                                  "Relatório de auditoria exportado para 'auditoria.txt'")
        except Exception as e:
            QMessageBox.warning(self, "Erro na Exportação", 
                              f"Erro ao exportar auditoria: {str(e)}")
    
    def update_global_stats(self):
        """Carrega stats diretamente do config (fonte da verdade)"""
        try:
            # Carregar stats salvos de cada site
            essence_stats = self.app_config.load_stats('essence')
            main_stats = self.app_config.load_stats('main')
            
            # Somar totais
            total = (essence_stats.get('total_items', 0) + 
                    main_stats.get('total_items', 0))
            processed = (essence_stats.get('processed_items', 0) + 
                        main_stats.get('processed_items', 0))
            success = (essence_stats.get('successful_items', 0) + 
                      main_stats.get('successful_items', 0))
            failed = (essence_stats.get('failed_items', 0) + 
                     main_stats.get('failed_items', 0))
            
            # Atualizar labels
            self.global_total.setText(f"Total: {total}")
            self.global_processed.setText(f"Processed: {processed}")
            self.global_success.setText(f"Success: {success}")
            self.global_failed.setText(f"Failed: {failed}")
        except Exception as e:
            print(f"⚠️ Erro ao atualizar global stats: {e}")
    
    def closeEvent(self, event):
        # Parar o timer
        if hasattr(self, 'stats_timer'):
            self.stats_timer.stop()
        
        if hasattr(self, 'audit_window'):
            self.audit_window.close()
        event.accept()