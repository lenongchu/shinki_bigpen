import sys
import json
import os
from PyQt5.QtWidgets import (QApplication, QWidget, QSystemTrayIcon, QMenu, 
                             QAction, QDialog, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QSpinBox, QColorDialog, QCheckBox,
                             QShortcut, QKeySequenceEdit)
from PyQt5.QtCore import Qt, QTimer, QPoint, QRect, pyqtSignal, QEvent
from PyQt5.QtGui import (QPainter, QPen, QColor, QBrush, QCursor, QIcon, 
                         QPixmap, QPolygon, QKeySequence)
import win32gui
import win32api
import win32con

class DrawingOverlay(QWidget):
    """全屏透明绘制覆盖层"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint | 
            Qt.FramelessWindowHint | 
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)
        
        # 绘制数据
        self.drawing = False
        self.last_point = QPoint()
        self.pen_color = QColor(255, 0, 0)  # 默认红色
        self.pen_width = 3
        self.paths = []  # 存储所有绘制路径
        self.current_path = []
        
        # 激活区域设置
        self.activation_zone = None  # QRect(x, y, width, height)
        self.show_zone = False  # 是否显示区域边界
        
        # 模式：'pointer' 或 'pen'
        self.mode = 'pointer'
        self.setCursor(Qt.ArrowCursor)
        
        # 鼠标位置监控
        self.mouse_timer = QTimer()
        self.mouse_timer.timeout.connect(self.check_mouse_position)
        self.mouse_timer.start(100)  # 每100ms检查一次（更省算力）
        
        # Windows 句柄，用于设置鼠标穿透
        self.hwnd = None
        
    def showEvent(self, event):
        """窗口显示时获取句柄"""
        super().showEvent(event)
        self.hwnd = int(self.winId())
        
    def set_mouse_transparent(self, transparent):
        """设置窗口鼠标事件穿透"""
        if self.hwnd:
            style_ex = win32gui.GetWindowLong(self.hwnd, win32con.GWL_EXSTYLE)
            if transparent:
                # 启用鼠标穿透
                style_ex |= win32con.WS_EX_TRANSPARENT
            else:
                # 禁用鼠标穿透
                style_ex &= ~win32con.WS_EX_TRANSPARENT
            win32gui.SetWindowLong(self.hwnd, win32con.GWL_EXSTYLE, style_ex)
        
    def set_activation_zone(self, rect):
        """设置激活区域"""
        self.activation_zone = rect
        self.update()
        
    def clear_activation_zone(self):
        """清除激活区域"""
        self.activation_zone = None
        self.update()
        
    def toggle_zone_visibility(self, show):
        """切换区域可见性"""
        self.show_zone = show
        self.update()
        
    def check_mouse_position(self):
        """检查鼠标位置，决定是否切换模式"""
        if self.activation_zone is None:
            # 没有激活区域时，默认指针模式，启用鼠标穿透
            if self.mode != 'pointer':
                self.mode = 'pointer'
                self.setCursor(Qt.ArrowCursor)
                self.set_mouse_transparent(True)
            return
            
        pos = QCursor.pos()
        
        # 转换为窗口坐标
        window_pos = self.mapFromGlobal(pos)
        
        if self.activation_zone.contains(window_pos):
            if self.mode != 'pen':
                self.mode = 'pen'
                self.setCursor(Qt.CrossCursor)
                # 在激活区域内，禁用鼠标穿透，接收鼠标事件
                self.set_mouse_transparent(False)
        else:
            if self.mode != 'pointer':
                self.mode = 'pointer'
                self.setCursor(Qt.ArrowCursor)
                # 在激活区域外，启用鼠标穿透
                self.set_mouse_transparent(True)
    
    def mousePressEvent(self, event):
        """鼠标按下事件"""
        # 只在笔模式下绘制
        if self.mode == 'pen' and event.button() == Qt.LeftButton:
            print(f"[Gink] mousePressEvent: start drawing at {event.pos()}, mode={self.mode}")
            self.drawing = True
            self.last_point = event.pos()
            self.current_path = [(event.pos(), self.pen_color, self.pen_width)]
            event.accept()
        else:
            print(f"[Gink] mousePressEvent: ignored, mode={self.mode}, button={event.button()}")
            event.ignore()
    
    def mouseMoveEvent(self, event):
        """鼠标移动事件"""
        if self.drawing and self.mode == 'pen':
            # 可选：调试输出频率较高，必要时可注释掉
            # print(f"[Gink] mouseMoveEvent: {event.pos()}")
            current_point = event.pos()
            self.current_path.append((current_point, self.pen_color, self.pen_width))
            self.last_point = current_point
            self.update()
            event.accept()
        else:
            event.ignore()
    
    def mouseReleaseEvent(self, event):
        """鼠标释放事件"""
        if self.drawing and event.button() == Qt.LeftButton:
            self.drawing = False
            if self.current_path:
                self.paths.append(self.current_path.copy())
                self.current_path = []
                self.update()
            event.accept()
        else:
            event.ignore()
    
    def paintEvent(self, event):
        """绘制事件"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 绘制激活区域边界（如果启用）
        if self.activation_zone and self.show_zone:
            # 边框 + 内部约 99% 透明填充（保留极淡色以便命中检测、不影响写字）
            painter.setPen(QPen(QColor(0, 150, 255), 2, Qt.DashLine))
            painter.setBrush(QBrush(QColor(0, 150, 255, 3)))  # alpha≈3，约 99% 透明
            painter.drawRect(self.activation_zone)
        
        # 绘制所有路径
        for path in self.paths:
            if len(path) < 2:
                continue
            points = [p[0] for p in path]
            color = path[0][1]
            width = path[0][2]
            
            painter.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            for i in range(len(points) - 1):
                painter.drawLine(points[i], points[i + 1])
        
        # 绘制当前路径
        if self.current_path and len(self.current_path) >= 2:
            points = [p[0] for p in self.current_path]
            color = self.current_path[0][1]
            width = self.current_path[0][2]
            
            painter.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            for i in range(len(points) - 1):
                painter.drawLine(points[i], points[i + 1])
    
    def clear(self):
        """清除所有绘制"""
        self.paths = []
        self.current_path = []
        self.update()
    
    def undo(self):
        """撤销最后一条路径"""
        if self.paths:
            self.paths.pop()
            self.update()
    
    def set_pen_color(self, color):
        """设置笔颜色"""
        self.pen_color = color
    
    def set_pen_width(self, width):
        """设置笔宽度"""
        self.pen_width = width


class ShortcutConfigDialog(QDialog):
    """快捷键配置对话框"""

    def __init__(self, shortcuts, parent=None):
        """
        shortcuts: dict，包含当前快捷键设置
            {
                'toggle_overlay': 'F2',
                'clear_all': 'F3',
                'undo': 'F4',
                'show_zone_setup': 'F6',
            }
        """
        super().__init__(parent)
        self.setWindowTitle("快捷键设置")
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setModal(True)

        self._shortcuts = shortcuts.copy()

        layout = QVBoxLayout()

        # 说明文字
        info = QLabel("点击下方快捷键编辑框，然后按下你想要的键位组合。")
        layout.addWidget(info)

        # 各个功能的快捷键编辑
        self.editors = {}

        def add_row(label_text, key_name):
            row = QHBoxLayout()
            label = QLabel(label_text)
            editor = QKeySequenceEdit()
            editor.setKeySequence(QKeySequence(self._shortcuts.get(key_name, "")))
            row.addWidget(label)
            row.addWidget(editor)
            layout.addLayout(row)
            self.editors[key_name] = editor

        add_row("显示/隐藏绘制层：", "toggle_overlay")
        add_row("清除所有标注：", "clear_all")
        add_row("撤销上一次绘制：", "undo")
        add_row("设置激活区域：", "show_zone_setup")

        # 按钮区
        btn_row = QHBoxLayout()
        self.ok_btn = QPushButton("确定")
        self.cancel_btn = QPushButton("取消")
        self.reset_btn = QPushButton("恢复默认")

        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        self.reset_btn.clicked.connect(self.reset_to_default)

        btn_row.addWidget(self.ok_btn)
        btn_row.addWidget(self.reset_btn)
        btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)

        self.setLayout(layout)

    def reset_to_default(self):
        """恢复默认快捷键"""
        defaults = {
            "toggle_overlay": "F2",
            "clear_all": "F3",
            "undo": "F4",
            "show_zone_setup": "F6",
        }
        for key, seq in defaults.items():
            if key in self.editors:
                self.editors[key].setKeySequence(QKeySequence(seq))

    def get_shortcuts(self):
        """返回用户设置后的快捷键字典"""
        result = {}
        for key, editor in self.editors.items():
            seq = editor.keySequence().toString()
            # 允许为空（表示禁用该快捷键）
            result[key] = seq
        return result


class ZoneSetupDialog(QDialog):
    """激活区域设置对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置激活区域")
        # 保证在托盘应用场景下也能正常显示在最前面
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setModal(True)
        
        layout = QVBoxLayout()
        
        # 说明
        info_label = QLabel("点击'开始设置'后，用鼠标拖拽选择激活区域")
        layout.addWidget(info_label)
        
        # 按钮
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("开始设置")
        self.start_btn.clicked.connect(self.start_setup)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        self.clear_btn = QPushButton("清除区域")
        self.clear_btn.clicked.connect(self.clear_zone)
        
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.clear_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)
        
        self.zone_rect = None
        self.setting = False
        
    def start_setup(self):
        """开始设置区域"""
        print("[Gink] ZoneSetupDialog.start_setup clicked")
        self.setting = True
        self.hide()
        self.parent().start_zone_setup()
        
    def clear_zone(self):
        """清除区域"""
        self.zone_rect = None
        self.parent().clear_activation_zone()
        self.accept()


class ZoneSetupOverlay(QWidget):
    """区域设置时的临时覆盖层"""
    
    zone_set = pyqtSignal(object)  # QRect
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint | 
            Qt.FramelessWindowHint | 
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.drawing = False
        self.start_point = QPoint()
        self.end_point = QPoint()
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            print("[Gink] ZoneSetupOverlay.mousePressEvent")
            self.drawing = True
            self.start_point = event.pos()
            self.end_point = event.pos()
    
    def mouseMoveEvent(self, event):
        if self.drawing:
            self.end_point = event.pos()
            self.update()
    
    def mouseReleaseEvent(self, event):
        if self.drawing and event.button() == Qt.LeftButton:
            print("[Gink] ZoneSetupOverlay.mouseReleaseEvent")
            self.drawing = False
            rect = QRect(self.start_point, self.end_point).normalized()
            if rect.width() > 10 and rect.height() > 10:  # 最小尺寸
                print(f"[Gink] ZoneSetupOverlay emit rect: {rect}")
                self.zone_set.emit(rect)
            self.hide()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        # 始终轻微变暗背景，方便用户确认当前在“设置模式”
        painter.fillRect(self.rect(), QBrush(QColor(0, 0, 0, 80)))

        if self.drawing:
            painter.setPen(QPen(QColor(0, 150, 255), 2, Qt.DashLine))
            painter.setBrush(QBrush(QColor(0, 150, 255, 50)))
            rect = QRect(self.start_point, self.end_point).normalized()
            painter.drawRect(rect)


class MainWindow(QWidget):
    """主窗口（系统托盘应用）"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gink-like 屏幕标注工具")

        # 配置文件路径（与脚本同目录）
        self.config_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "gink_like_config.json"
        )
        
        # 创建系统托盘图标
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.style().standardIcon(self.style().SP_ComputerIcon))
        
        # 创建菜单
        tray_menu = QMenu()
        
        # 显示/隐藏绘制层
        self.show_action = QAction("显示绘制层", self)
        self.show_action.triggered.connect(self.toggle_overlay)
        tray_menu.addAction(self.show_action)
        
        # 设置激活区域
        zone_action = QAction("设置激活区域", self)
        zone_action.triggered.connect(self.show_zone_setup)
        tray_menu.addAction(zone_action)
        
        # 清除区域
        clear_zone_action = QAction("清除激活区域", self)
        clear_zone_action.triggered.connect(self.clear_activation_zone)
        tray_menu.addAction(clear_zone_action)
        
        tray_menu.addSeparator()

        # 快捷键设置
        shortcut_action = QAction("快捷键设置", self)
        shortcut_action.triggered.connect(self.show_shortcut_settings)
        tray_menu.addAction(shortcut_action)
        
        tray_menu.addSeparator()
        
        # 笔设置
        pen_menu = tray_menu.addMenu("笔设置")
        
        color_action = QAction("选择颜色", self)
        color_action.triggered.connect(self.choose_color)
        pen_menu.addAction(color_action)
        
        width_action = QAction("设置宽度", self)
        width_action.triggered.connect(self.set_width)
        pen_menu.addAction(width_action)
        
        tray_menu.addSeparator()
        
        # 清除
        clear_action = QAction("清除所有", self)
        clear_action.triggered.connect(self.clear_drawing)
        tray_menu.addAction(clear_action)
        
        undo_action = QAction("撤销", self)
        undo_action.triggered.connect(self.undo_drawing)
        tray_menu.addAction(undo_action)
        
        tray_menu.addSeparator()
        
        # 退出
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(QApplication.quit)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        
        # 创建绘制覆盖层
        self.overlay = DrawingOverlay()
        self.overlay.hide()
        
        # 创建区域设置覆盖层
        self.zone_setup_overlay = ZoneSetupOverlay()
        self.zone_setup_overlay.zone_set.connect(self.on_zone_set)
        
        # 区域设置对话框
        self.zone_dialog = ZoneSetupDialog(self)
        
        self.overlay_visible = False

        # ----------------------
        # 键盘快捷键（在绘制层激活时生效）
        # ----------------------
        # 加载或初始化快捷键配置
        self.shortcuts = self._load_shortcuts()
        self._init_shortcuts()

    # ----------------------
    # 快捷键配置相关
    # ----------------------
    def _default_shortcuts(self):
        return {
            "toggle_overlay": "F2",
            "clear_all": "F3",
            "undo": "F4",
            "show_zone_setup": "F6",
        }

    def _load_shortcuts(self):
        """从配置文件加载快捷键，如果失败则使用默认值"""
        defaults = self._default_shortcuts()
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    defaults.update({k: str(v) for k, v in data.items()})
            except Exception as e:
                print(f"[Gink] 加载快捷键配置失败: {e}")
        return defaults

    def _save_shortcuts(self):
        """保存当前快捷键到配置文件"""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.shortcuts, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Gink] 保存快捷键配置失败: {e}")

    def _init_shortcuts(self):
        """根据当前配置创建/更新 QShortcut"""
        # 如果已经存在，则更新键；否则创建
        if hasattr(self, "shortcut_toggle_overlay"):
            self.shortcut_toggle_overlay.setKey(QKeySequence(self.shortcuts.get("toggle_overlay", "")))
        else:
            # 将快捷键挂到主窗口上，并使用 ApplicationShortcut，避免仅限覆盖层有焦点时才生效
            self.shortcut_toggle_overlay = QShortcut(QKeySequence(self.shortcuts.get("toggle_overlay", "")), self)
            self.shortcut_toggle_overlay.setContext(Qt.ApplicationShortcut)
            self.shortcut_toggle_overlay.activated.connect(self.toggle_overlay)

        if hasattr(self, "shortcut_clear_all"):
            self.shortcut_clear_all.setKey(QKeySequence(self.shortcuts.get("clear_all", "")))
        else:
            self.shortcut_clear_all = QShortcut(QKeySequence(self.shortcuts.get("clear_all", "")), self)
            self.shortcut_clear_all.setContext(Qt.ApplicationShortcut)
            self.shortcut_clear_all.activated.connect(self.clear_drawing)

        if hasattr(self, "shortcut_undo"):
            self.shortcut_undo.setKey(QKeySequence(self.shortcuts.get("undo", "")))
        else:
            self.shortcut_undo = QShortcut(QKeySequence(self.shortcuts.get("undo", "")), self)
            self.shortcut_undo.setContext(Qt.ApplicationShortcut)
            self.shortcut_undo.activated.connect(self.undo_drawing)

        if hasattr(self, "shortcut_zone_dialog"):
            self.shortcut_zone_dialog.setKey(QKeySequence(self.shortcuts.get("show_zone_setup", "")))
        else:
            self.shortcut_zone_dialog = QShortcut(QKeySequence(self.shortcuts.get("show_zone_setup", "")), self)
            self.shortcut_zone_dialog.setContext(Qt.ApplicationShortcut)
            self.shortcut_zone_dialog.activated.connect(self.show_zone_setup)

    def show_shortcut_settings(self):
        """显示快捷键设置对话框"""
        dlg = ShortcutConfigDialog(self.shortcuts, self)
        if dlg.exec_() == QDialog.Accepted:
            new_shortcuts = dlg.get_shortcuts()
            # 允许用户清空某个快捷键（表示禁用）
            self.shortcuts.update(new_shortcuts)
            self._init_shortcuts()
            self._save_shortcuts()
        
    def toggle_overlay(self):
        """切换绘制层显示/隐藏"""
        if self.overlay_visible:
            self.overlay.hide()
            self.overlay_visible = False
            self.show_action.setText("显示绘制层")
        else:
            # 在多屏环境下，覆盖整个虚拟桌面，坐标系与 ZoneSetupOverlay 保持一致
            desktop = QApplication.desktop()
            geom = desktop.geometry()
            print(f"[Gink] DrawingOverlay geometry set to: {geom}")
            self.overlay.setGeometry(geom)
            self.overlay.show()
            # 强制设置为画笔光标，方便确认是否在覆盖层上
            self.overlay.setCursor(Qt.CrossCursor)
            self.overlay.raise_()
            self.overlay.activateWindow()
            # 初始状态：如果没有激活区域，启用鼠标穿透
            if self.overlay.activation_zone is None:
                self.overlay.set_mouse_transparent(True)
            self.overlay_visible = True
            self.show_action.setText("隐藏绘制层")
    
    def show_zone_setup(self):
        """显示区域设置对话框；若绘制层未显示则先自动显示绘制层"""
        # 与“设置激活区域”绑定：点击设置激活区域时自动开启显示绘制层
        if not self.overlay_visible:
            self.toggle_overlay()

        # 将对话框移动到主屏幕中央，避免多屏环境下跑到看不见的位置
        screen_geom = QApplication.primaryScreen().geometry()
        dlg_size = self.zone_dialog.sizeHint()
        x = screen_geom.x() + (screen_geom.width() - dlg_size.width()) // 2
        y = screen_geom.y() + (screen_geom.height() - dlg_size.height()) // 2
        self.zone_dialog.move(x, y)

        # 显示对话框时，确保它在所有窗口最前面并获得焦点
        self.zone_dialog.show()
        self.zone_dialog.raise_()
        self.zone_dialog.activateWindow()
    
    def start_zone_setup(self):
        """开始区域设置"""
        print("[Gink] MainWindow.start_zone_setup called")
        # 在多屏环境下，使用所有屏幕的外接矩形，覆盖整个虚拟桌面
        desktop = QApplication.desktop()
        geom = desktop.geometry()
        print(f"[Gink] ZoneSetupOverlay geometry set to: {geom}")
        self.zone_setup_overlay.setGeometry(geom)
        self.zone_setup_overlay.show()
        self.zone_setup_overlay.raise_()
        self.zone_setup_overlay.activateWindow()
    
    def on_zone_set(self, rect):
        """区域设置完成"""
        # 注意：`DrawingOverlay.check_mouse_position()` 用的是 `mapFromGlobal()`
        # 得到的是“overlay 窗口坐标”，因此激活区域也必须存成 overlay 坐标。
        self.overlay.set_activation_zone(rect.normalized())
        self.overlay.toggle_zone_visibility(True)
        # 设置完区域后，默认先让鼠标可穿透（等鼠标进入区域再自动切回笔模式接管鼠标）
        self.overlay.mode = 'pointer'
        self.overlay.setCursor(Qt.ArrowCursor)
        self.overlay.set_mouse_transparent(True)
        self.zone_dialog.accept()
    
    def clear_activation_zone(self):
        """清除激活区域"""
        self.overlay.clear_activation_zone()
        self.overlay.toggle_zone_visibility(False)
    
    def choose_color(self):
        """选择笔颜色"""
        color = QColorDialog.getColor(self.overlay.pen_color, self, "选择笔颜色")
        if color.isValid():
            self.overlay.set_pen_color(color)
    
    def set_width(self):
        """设置笔宽度"""
        from PyQt5.QtWidgets import QInputDialog
        width, ok = QInputDialog.getInt(
            self, "设置笔宽度", "宽度 (1-20):", 
            self.overlay.pen_width, 1, 20, 1
        )
        if ok:
            self.overlay.set_pen_width(width)
    
    def clear_drawing(self):
        """清除所有绘制"""
        self.overlay.clear()
    
    def undo_drawing(self):
        """撤销绘制"""
        self.overlay.undo()


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    # 检查是否只有一个实例
    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("系统托盘不可用")
        return
    
    window = MainWindow()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
