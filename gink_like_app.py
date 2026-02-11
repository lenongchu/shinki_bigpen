import sys
import json
import os
from PyQt5.QtWidgets import (QApplication, QWidget, QSystemTrayIcon, QMenu, 
                             QAction, QDialog, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QSpinBox, QColorDialog, QCheckBox,
                             QKeySequenceEdit)
from PyQt5.QtCore import Qt, QTimer, QPoint, QRect, pyqtSignal, QEvent
from PyQt5.QtGui import (QPainter, QPen, QColor, QBrush, QCursor, QIcon, 
                         QPixmap, QImage, QPolygon, QKeySequence)
import ctypes
from ctypes import wintypes
import win32gui
import win32api
import win32con

# user32.RegisterHotKey / UnregisterHotKey（win32api 不提供，需用 ctypes 调用）
user32 = ctypes.windll.user32
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL

# Windows 全局热键
WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
ID_HOTKEY_CLEAR = 1
ID_HOTKEY_UNDO = 2
ID_HOTKEY_ZONE = 3
VK_F1, VK_F2, VK_F3, VK_F4, VK_F5, VK_F6 = 0x70, 0x71, 0x72, 0x73, 0x74, 0x75
VK_F7, VK_F8, VK_F9, VK_F10, VK_F11, VK_F12 = 0x76, 0x77, 0x78, 0x79, 0x7A, 0x7B


def create_pen_icon():
    """加载 pen_icon.png 并着色为蓝色；若无则用简单铅笔"""
    base = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base, "pen_icon.png"),
        os.path.join(base, "assets", "pen_icon.png"),
    ]
    img_path = None
    for p in candidates:
        if os.path.exists(p):
            img_path = p
            break
    if not img_path:
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(60, 115, 185))
        p.drawPolygon(QPolygon([QPoint(5, 4), QPoint(27, 16), QPoint(5, 28)]))
        p.end()
        return QIcon(pixmap)
    img = QImage(img_path)
    if img.isNull():
        return QIcon(QPixmap(32, 32))
    # 深色像素 → 蓝色
    tint = QColor(60, 115, 185)
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.alpha() < 10:
                continue
            gray = (c.red() + c.green() + c.blue()) / 3
            if gray < 200:
                ratio = min(1.0, (255 - gray) / 150)
                r = int(tint.red() * ratio + c.red() * (1 - ratio))
                g = int(tint.green() * ratio + c.green() * (1 - ratio))
                b = int(tint.blue() * ratio + c.blue() * (1 - ratio))
                img.setPixelColor(x, y, QColor(r, g, b, c.alpha()))
    return QIcon(QPixmap.fromImage(img))


def shortcut_to_mod_vk(seq_str):
    """将 QKeySequence 字符串转为 (mod, vk)，用于 RegisterHotKey。失败返回 None。"""
    if not seq_str or not seq_str.strip():
        return None
    s = seq_str.strip()
    parts = [p.strip() for p in s.replace("+", " + ").split("+") if p.strip()]
    if not parts:
        return None
    mod = 0
    key_part = parts[-1].upper()
    for p in parts[:-1]:
        if p.upper() in ("CTRL", "CONTROL"):
            mod |= MOD_CONTROL
        elif p.upper() == "ALT":
            mod |= MOD_ALT
        elif p.upper() == "SHIFT":
            mod |= MOD_SHIFT
    f_map = {"F1": VK_F1, "F2": VK_F2, "F3": VK_F3, "F4": VK_F4, "F5": VK_F5, "F6": VK_F6,
             "F7": VK_F7, "F8": VK_F8, "F9": VK_F9, "F10": VK_F10, "F11": VK_F11, "F12": VK_F12}
    if key_part in f_map:
        vk = f_map[key_part]
    elif len(key_part) == 1 and key_part.isalnum():
        vk = ord(key_part)
    else:
        return None
    return (mod | MOD_NOREPEAT, vk)


class HotkeyReceiver(QWidget):
    """用于接收 Windows 全局热键的隐藏窗口"""
    hotkey_activated = pyqtSignal(int)  # hotkey id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Tool)
        self.setFixedSize(1, 1)
        self.move(-10000, -10000)
        self._registered = {}  # id -> (mod, vk)

    def register(self, hotkey_id, mod, vk):
        try:
            hwnd = int(self.winId())
            user32.RegisterHotKey(hwnd, hotkey_id, mod, vk)
            self._registered[hotkey_id] = (mod, vk)
            print(f"[Gink] RegisterHotKey 成功: id={hotkey_id}, mod=0x{mod:x}, vk=0x{vk:x}")
            return True
        except Exception as e:
            print(f"[Gink] RegisterHotKey 失败: id={hotkey_id}, mod=0x{mod:x}, vk=0x{vk:x}, 错误={e}")
            return False

    def unregister_all(self):
        for hid in list(self._registered):
            try:
                user32.UnregisterHotKey(int(self.winId()), hid)
            except Exception:
                pass
        self._registered.clear()

    def show_receiver(self):
        """显示到屏幕外以便创建窗口并接收消息"""
        if not self.isVisible():
            self.show()

    def nativeEvent(self, eventType, message):
        # 兼容 bytes 和 str 类型的 eventType
        et = eventType.decode("utf-8") if isinstance(eventType, bytes) else str(eventType)
        if "windows" in et.lower() and "msg" in et.lower():
            try:
                import ctypes
                from ctypes import Structure, c_void_p, c_uint, c_long, POINTER
                class MSG(Structure):
                    _fields_ = [
                        ("hwnd", c_void_p), ("message", c_uint),
                        ("wParam", c_void_p), ("lParam", c_long),
                        ("time", c_uint), ("pt", c_long * 2),
                    ]
                try:
                    addr = int(message)
                except (TypeError, ValueError):
                    addr = int(getattr(message, "value", 0)) if hasattr(message, "value") else 0
                ptr = ctypes.c_void_p(addr) if addr else None
                if ptr is None:
                    return super().nativeEvent(eventType, message)
                msg = ctypes.cast(ptr, POINTER(MSG)).contents
                if msg.message == WM_HOTKEY and msg.wParam:
                    self.hotkey_activated.emit(int(msg.wParam))
                    return True, 0
            except Exception as ex:
                pass
        return super().nativeEvent(eventType, message)


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
            "clear_all": "Ctrl+Alt+C",
            "undo": "Ctrl+Alt+Z",
            "show_zone_setup": "Ctrl+Alt+S",
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
        self.tray_icon.setIcon(create_pen_icon())
        
        # 创建菜单
        tray_menu = QMenu()
        
        # 使用上次神奇区域
        use_last_action = QAction("使用上次神奇区域", self)
        use_last_action.triggered.connect(self.use_last_magic_zone)
        tray_menu.addAction(use_last_action)
        
        # 设置神奇区域
        zone_action = QAction("设置神奇区域", self)
        zone_action.triggered.connect(self.show_zone_setup)
        tray_menu.addAction(zone_action)
        
        # 隐藏绘制层
    #    hide_action = QAction("隐藏绘制层", self)
    #    hide_action.triggered.connect(self.toggle_overlay)
    #    tray_menu.addAction(hide_action)
        
        # 清除区域
        clear_zone_action = QAction("清除神奇区域", self)
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

        # 主窗口作为热键接收器：显示为 1x1 屏外 Tool 窗口，用于接收 WM_HOTKEY
        self.setWindowFlags(self.windowFlags() | Qt.Tool)
        self.setFixedSize(1, 1)
        self.move(-10000, -10000)
        self.show()
        QApplication.processEvents()

        # ----------------------
        # 配置（快捷键 + 上次神奇区域）
        # ----------------------
        self.shortcuts, self.saved_magic_zone = self._load_config()
        self._init_shortcuts()

    # ----------------------
    # 快捷键配置相关
    # ----------------------
    def _default_shortcuts(self):
        # 使用 Ctrl+Alt+ 组合，避免与浏览器等常用 F3/F4/F6 冲突
        return {
            "clear_all": "Ctrl+Alt+C",
            "undo": "Ctrl+Alt+Z",
            "show_zone_setup": "Ctrl+Alt+S",
        }

    def _load_config(self):
        """从配置文件加载快捷键和上次神奇区域"""
        shortcuts = self._default_shortcuts()
        saved_zone = None
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    for k, v in data.items():
                        if k == "activation_zone" and isinstance(v, dict):
                            x = v.get("x", 0)
                            y = v.get("y", 0)
                            w = v.get("width", 0)
                            h = v.get("height", 0)
                            if w > 0 and h > 0:
                                saved_zone = QRect(x, y, w, h)
                        else:
                            shortcuts[k] = str(v)
            except Exception as e:
                print(f"[Gink] 加载配置失败: {e}")
        return shortcuts, saved_zone

    def _save_config(self):
        """保存快捷键和神奇区域到配置文件"""
        data = dict(self.shortcuts)
        zone = self.overlay.activation_zone or self.saved_magic_zone
        if zone:
            data["activation_zone"] = {"x": zone.x(), "y": zone.y(), "width": zone.width(), "height": zone.height()}
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Gink] 保存配置失败: {e}")

    def _on_global_hotkey(self, hotkey_id):
        """全局热键按下时根据 id 分发到对应功能"""
        print(f"[Gink] 全局热键触发: id={hotkey_id}")
        if hotkey_id == ID_HOTKEY_CLEAR:
            self.clear_drawing()
        elif hotkey_id == ID_HOTKEY_UNDO:
            self.undo_drawing()
        elif hotkey_id == ID_HOTKEY_ZONE:
            self.show_zone_setup()

    def _unregister_hotkeys(self):
        """取消注册所有热键"""
        if not hasattr(self, "_registered_hotkeys"):
            return
        try:
            hwnd = int(self.winId())
            for hid in list(self._registered_hotkeys):
                try:
                    user32.UnregisterHotKey(hwnd, hid)
                except Exception:
                    pass
        except Exception:
            pass
        self._registered_hotkeys.clear()

    def _register_hotkey(self, hotkey_id, mod, vk):
        """注册单个全局热键"""
        if not hasattr(self, "_registered_hotkeys"):
            self._registered_hotkeys = set()
        try:
            hwnd = int(self.winId())
            ok = user32.RegisterHotKey(hwnd, hotkey_id, mod, vk)
            if ok:
                self._registered_hotkeys.add(hotkey_id)
                print(f"[Gink] RegisterHotKey 成功: id={hotkey_id}, mod=0x{mod:x}, vk=0x{vk:x}")
                return True
            err = ctypes.get_last_error()
            print(f"[Gink] RegisterHotKey 失败: id={hotkey_id}, 错误码={err} (可能快捷键被占用)")
            return False
        except Exception as e:
            print(f"[Gink] RegisterHotKey 失败: id={hotkey_id}, 错误={e}")
            return False

    def nativeEvent(self, eventType, message):
        """接收 Windows 原生消息，处理 WM_HOTKEY"""
        et = eventType.decode("utf-8") if isinstance(eventType, bytes) else str(eventType)
        if "windows" in et.lower() and "msg" in et.lower():
            try:
                import ctypes
                from ctypes import Structure, c_void_p, c_uint, c_long, POINTER
                class MSG(Structure):
                    _fields_ = [
                        ("hwnd", c_void_p), ("message", c_uint),
                        ("wParam", c_void_p), ("lParam", c_long),
                        ("time", c_uint), ("pt", c_long * 2),
                    ]
                try:
                    addr = int(message)
                except (TypeError, ValueError):
                    addr = int(getattr(message, "value", 0)) if hasattr(message, "value") else 0
                if addr:
                    ptr = ctypes.c_void_p(addr)
                    msg = ctypes.cast(ptr, POINTER(MSG)).contents
                    if msg.message == WM_HOTKEY and msg.wParam:
                        self._on_global_hotkey(int(msg.wParam))
                        return True, 0
            except Exception:
                pass
        return super().nativeEvent(eventType, message)

    def _init_shortcuts(self):
        """使用 Windows RegisterHotKey 注册全局热键（任意窗口下生效）"""
        self._unregister_hotkeys()
        if not hasattr(self, "_registered_hotkeys"):
            self._registered_hotkeys = set()
        print(f"[Gink] 正在注册全局热键，当前配置: {self.shortcuts}")
        # 清除所有
        seq = self.shortcuts.get("clear_all", "").strip()
        if seq:
            r = shortcut_to_mod_vk(seq)
            if r:
                mod, vk = r
                self._register_hotkey(ID_HOTKEY_CLEAR, mod, vk)
        # 撤销
        seq = self.shortcuts.get("undo", "").strip()
        if seq:
            r = shortcut_to_mod_vk(seq)
            if r:
                mod, vk = r
                self._register_hotkey(ID_HOTKEY_UNDO, mod, vk)
        # 设置激活区域
        seq = self.shortcuts.get("show_zone_setup", "").strip()
        if seq:
            r = shortcut_to_mod_vk(seq)
            if r:
                mod, vk = r
                self._register_hotkey(ID_HOTKEY_ZONE, mod, vk)

    def show_shortcut_settings(self):
        """显示快捷键设置对话框"""
        dlg = ShortcutConfigDialog(self.shortcuts, self)
        if dlg.exec_() == QDialog.Accepted:
            new_shortcuts = dlg.get_shortcuts()
            # 允许用户清空某个快捷键（表示禁用）
            self.shortcuts.update(new_shortcuts)
            self._init_shortcuts()
            self._save_config()
        
    def toggle_overlay(self):
        """切换绘制层显示/隐藏"""
        if self.overlay_visible:
            self.overlay.hide()
            self.overlay_visible = False
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
    
    def show_zone_setup(self):
        """直接开始设置激活区域（无需弹窗）；若绘制层未显示则先自动显示"""
        if not self.overlay_visible:
            self.toggle_overlay()
        self.start_zone_setup()
    
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
        rect = rect.normalized()
        self.overlay.set_activation_zone(rect)
        self.overlay.toggle_zone_visibility(True)
        self.overlay.mode = 'pointer'
        self.overlay.setCursor(Qt.ArrowCursor)
        self.overlay.set_mouse_transparent(True)
        self.saved_magic_zone = rect
        self._save_config()
    
    def clear_activation_zone(self):
        """清除激活区域"""
        self.overlay.clear_activation_zone()
        self.overlay.toggle_zone_visibility(False)
        self.saved_magic_zone = None
        self._save_config()

    def use_last_magic_zone(self):
        """使用上次保存的神奇区域，立即开始画画"""
        if self.saved_magic_zone is None:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self, "提示", "暂无上次神奇区域，请先设置神奇区域。")
            return
        if not self.overlay_visible:
            self.toggle_overlay()
        self.overlay.set_activation_zone(self.saved_magic_zone)
        self.overlay.toggle_zone_visibility(True)
        self.overlay.mode = 'pointer'
        self.overlay.setCursor(Qt.ArrowCursor)
        self.overlay.set_mouse_transparent(True)
    
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
