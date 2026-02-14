import sys
import json
import os


def _get_app_base():
    """脚本/资源所在目录（开发时=脚本目录，打包后=解压临时目录）"""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def _get_config_base():
    """配置文件所在目录（打包后=exe 所在目录，便于持久化）"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


from PyQt5.QtWidgets import (QApplication, QWidget, QSystemTrayIcon, QMenu, 
                             QAction, QDialog, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QSpinBox, QColorDialog, QCheckBox,
                             QKeySequenceEdit, QComboBox)
from PyQt5.QtCore import Qt, QTimer, QPoint, QRect, pyqtSignal, QEvent
from PyQt5.QtGui import (QPainter, QPen, QColor, QBrush, QCursor, QIcon, 
                         QPixmap, QImage, QPolygon, QKeySequence)
import ctypes
from ctypes import wintypes
import win32gui
import win32api
import win32con

# user32.RegisterHotKey / UnregisterHotKey / GetAsyncKeyState
user32 = ctypes.windll.user32
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = wintypes.SHORT

VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt

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
# Windows VK 码：标点与符号（美式键盘布局）
VK_OEM_1 = 0xBA    # ; :
VK_OEM_PLUS = 0xBB  # = +
VK_OEM_COMMA = 0xBC # , <
VK_OEM_MINUS = 0xBD # - _
VK_OEM_PERIOD = 0xBE # . >
VK_OEM_2 = 0xBF    # / ?
VK_OEM_3 = 0xC0    # ` ~
VK_OEM_4 = 0xDB    # [ {
VK_OEM_5 = 0xDC    # \ |
VK_OEM_6 = 0xDD    # ] }
VK_OEM_7 = 0xDE    # ' "


def create_pen_icon():
    """加载 pen_icon.png 并着色为蓝色；若无则用简单铅笔"""
    base = _get_app_base()
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
        p.setBrush(QColor(115, 115, 185))
        p.drawPolygon(QPolygon([QPoint(5, 4), QPoint(27, 16), QPoint(5, 28)]))
        p.end()
        return QIcon(pixmap)
    img = QImage(img_path)
    if img.isNull():
        return QIcon(QPixmap(32, 32))
    # 深色像素 → 蓝色
    tint = QColor(115, 115, 185)
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


def is_modifier_key_pressed(qt_modifier):
    """用 GetAsyncKeyState 检测修饰键物理状态，不依赖应用是否收到事件"""
    if qt_modifier == Qt.AltModifier:
        vk = VK_MENU
    elif qt_modifier == Qt.ControlModifier:
        vk = VK_CONTROL
    elif qt_modifier == Qt.ShiftModifier:
        vk = VK_SHIFT
    else:
        return False
    st = user32.GetAsyncKeyState(vk)
    return (st & 0x8000) != 0  # 高位置 1 表示当前按下


def parse_click_through_modifier(s):
    """将字符串转为 Qt 修饰键，如 'alt'->Qt.AltModifier。无效返回 None，使用默认 Alt。"""
    if not s or not isinstance(s, str):
        return Qt.AltModifier
    low = s.strip().lower()
    if low in ("alt",):
        return Qt.AltModifier
    if low in ("ctrl", "control"):
        return Qt.ControlModifier
    if low in ("shift",):
        return Qt.ShiftModifier
    return Qt.AltModifier


def modifier_to_str(mod):
    """Qt 修饰键转为配置字符串"""
    if mod == Qt.AltModifier:
        return "alt"
    if mod == Qt.ControlModifier:
        return "ctrl"
    if mod == Qt.ShiftModifier:
        return "shift"
    return "alt"


def shortcut_to_mod_vk(seq_str):
    """将 QKeySequence 字符串转为 (mod, vk)，用于 RegisterHotKey。失败返回 None。"""
    if not seq_str or not seq_str.strip():
        return None
    s = seq_str.strip()
    parts = [p.strip() for p in s.replace("+", " + ").split("+") if p.strip()]
    if not parts:
        return None
    mod = 0
    key_raw = parts[-1]
    key_part = key_raw.upper()
    for p in parts[:-1]:
        if p.upper() in ("CTRL", "CONTROL"):
            mod |= MOD_CONTROL
        elif p.upper() == "ALT":
            mod |= MOD_ALT
        elif p.upper() == "SHIFT":
            mod |= MOD_SHIFT
    f_map = {"F1": VK_F1, "F2": VK_F2, "F3": VK_F3, "F4": VK_F4, "F5": VK_F5, "F6": VK_F6,
             "F7": VK_F7, "F8": VK_F8, "F9": VK_F9, "F10": VK_F10, "F11": VK_F11, "F12": VK_F12}
    oem_map = {";": VK_OEM_1, ":": VK_OEM_1, "=": VK_OEM_PLUS, "+": VK_OEM_PLUS,
               ",": VK_OEM_COMMA, "<": VK_OEM_COMMA, "-": VK_OEM_MINUS, "_": VK_OEM_MINUS,
               ".": VK_OEM_PERIOD, ">": VK_OEM_PERIOD, "/": VK_OEM_2, "?": VK_OEM_2,
               "`": VK_OEM_3, "~": VK_OEM_3, "[": VK_OEM_4, "{": VK_OEM_4,
               "\\": VK_OEM_5, "|": VK_OEM_5, "]": VK_OEM_6, "}": VK_OEM_6,
               "'": VK_OEM_7, '"': VK_OEM_7}
    if key_part in f_map:
        vk = f_map[key_part]
    elif len(key_raw) == 1 and key_raw.isalnum():
        vk = ord(key_part)
    elif len(key_raw) == 1 and key_raw in oem_map:
        vk = oem_map[key_raw]
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
        
        # 临时穿透修饰键：按住时全屏鼠标穿透，松开恢复（默认 Alt）
        self.click_through_modifier = Qt.AltModifier
        
    def set_click_through_modifier(self, modifier):
        """设置临时穿透修饰键，如 Qt.AltModifier、Qt.ControlModifier"""
        self.click_through_modifier = modifier
        
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
        # 按住修饰键时，临时全屏穿透；用 GetAsyncKeyState 检测物理状态，否则穿透后收不到事件会误判
        if self.click_through_modifier and is_modifier_key_pressed(self.click_through_modifier):
            self.set_mouse_transparent(True)
            if self.mode != 'pointer':
                self.mode = 'pointer'
                self.setCursor(Qt.ArrowCursor)
            return
        
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
        if self.mode != 'pen':
            event.ignore()
            return
        if event.button() == Qt.LeftButton:
            self.drawing = True
            self.last_point = event.pos()
            self.current_path = [(event.pos(), self.pen_color, self.pen_width)]
            event.accept()
        elif event.button() == Qt.RightButton:
            # 右键：在点击位置生成当前笔色的圆点
            radius = max(4, self.pen_width * 2)
            dot_path = [(event.pos(), self.pen_color, radius)]  # 单点表示圆点，第三项为半径
            self.paths.append(dot_path)
            self.update()
            event.accept()
        else:
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
        
        # 绘制所有路径（包括圆点）
        for path in self.paths:
            if len(path) == 1:
                # 单点表示右键生成的圆点：(pos, color, radius)
                pt, color, radius = path[0]
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(color))
                rect = QRect(pt.x() - radius, pt.y() - radius, radius * 2, radius * 2)
                painter.drawEllipse(rect)
            elif len(path) >= 2:
                points = [p[0] for p in path]
                color = path[0][1]
                width = path[0][2]
                painter.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                painter.setBrush(Qt.NoBrush)
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

    def __init__(self, shortcuts, click_through_modifier=Qt.AltModifier, parent=None):
        """
        shortcuts: dict，包含当前快捷键设置
        click_through_modifier: 临时穿透修饰键
        """
        super().__init__(parent)
        self.setWindowTitle("快捷键设置")
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setModal(True)

        self._shortcuts = shortcuts.copy()
        self._click_through_modifier = click_through_modifier

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

        # 临时穿透修饰键
        mod_row = QHBoxLayout()
        mod_row.addWidget(QLabel("临时穿透修饰键："))
        self.modifier_combo = QComboBox()
        self.modifier_combo.addItems(["Alt", "Ctrl", "Shift"])
        mod_str = modifier_to_str(click_through_modifier)
        idx = {"alt": 0, "ctrl": 1, "shift": 2}.get(mod_str, 0)
        self.modifier_combo.setCurrentIndex(idx)
        mod_row.addWidget(self.modifier_combo)
        layout.addLayout(mod_row)
        tip = QLabel("提示：按住该修饰键可临时穿透点击神奇区域内的控件，无需清除区域。")
        tip.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(tip)

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
        self.modifier_combo.setCurrentIndex(0)  # Alt

    def get_shortcuts(self):
        """返回用户设置后的快捷键字典"""
        result = {}
        for key, editor in self.editors.items():
            seq = editor.keySequence().toString()
            # 允许为空（表示禁用该快捷键）
            result[key] = seq
        return result

    def get_click_through_modifier(self):
        """返回用户设置的临时穿透修饰键"""
        idx = self.modifier_combo.currentIndex()
        mods = [Qt.AltModifier, Qt.ControlModifier, Qt.ShiftModifier]
        return mods[idx] if 0 <= idx < len(mods) else Qt.AltModifier


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

        # 配置文件路径（打包后=exe 所在目录）
        self.config_path = os.path.join(_get_config_base(), "shinki_bigpen_config.json")
        
        # 创建系统托盘图标
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(create_pen_icon())
        
        # 创建菜单
        tray_menu = QMenu()
        
        # 保存当前神奇区域（书签，关闭软件后仍可还原）
        save_zone_action = QAction("保存当前神奇区域", self)
        save_zone_action.triggered.connect(self.save_current_magic_zone)
        tray_menu.addAction(save_zone_action)
        
        # 还原已保存的神奇区域
        restore_zone_action = QAction("还原神奇区域", self)
        restore_zone_action.triggered.connect(self.restore_pinned_magic_zone)
        tray_menu.addAction(restore_zone_action)
        
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
        
        # 临时穿透提示（不可点击）
        passthrough_tip = QAction("按住修饰键可临时穿透点击", self)
        passthrough_tip.setEnabled(False)
        tray_menu.addAction(passthrough_tip)
        
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
        # 配置（快捷键 + 上次神奇区域 + 临时穿透修饰键 + 已保存的书签区域）
        # ----------------------
        self.shortcuts, self.saved_magic_zone, self.click_through_modifier, self.pinned_magic_zone = self._load_config()
        self.overlay.set_click_through_modifier(self.click_through_modifier)
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
        """从配置文件加载快捷键、上次神奇区域、临时穿透修饰键、已保存的书签区域"""
        shortcuts = self._default_shortcuts()
        saved_zone = None
        pinned_zone = None
        click_through_modifier = Qt.AltModifier
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
                        elif k == "pinned_magic_zone" and isinstance(v, dict):
                            x = v.get("x", 0)
                            y = v.get("y", 0)
                            w = v.get("width", 0)
                            h = v.get("height", 0)
                            if w > 0 and h > 0:
                                pinned_zone = QRect(x, y, w, h)
                        elif k == "click_through_modifier" and isinstance(v, str):
                            click_through_modifier = parse_click_through_modifier(v)
                        elif k not in ("activation_zone", "pinned_magic_zone", "click_through_modifier"):
                            shortcuts[k] = str(v)
            except Exception as e:
                print(f"[Gink] 加载配置失败: {e}")
        return shortcuts, saved_zone, click_through_modifier, pinned_zone

    def _save_config(self):
        """保存快捷键、神奇区域、已保存书签区域、临时穿透修饰键到配置文件"""
        data = dict(self.shortcuts)
        zone = self.overlay.activation_zone or self.saved_magic_zone
        if zone:
            data["activation_zone"] = {"x": zone.x(), "y": zone.y(), "width": zone.width(), "height": zone.height()}
        if getattr(self, "pinned_magic_zone", None):
            p = self.pinned_magic_zone
            data["pinned_magic_zone"] = {"x": p.x(), "y": p.y(), "width": p.width(), "height": p.height()}
        mod = getattr(self, "click_through_modifier", None) or self.overlay.click_through_modifier
        data["click_through_modifier"] = modifier_to_str(mod)
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
        dlg = ShortcutConfigDialog(self.shortcuts, self.click_through_modifier, self)
        if dlg.exec_() == QDialog.Accepted:
            new_shortcuts = dlg.get_shortcuts()
            self.shortcuts.update(new_shortcuts)
            self.click_through_modifier = dlg.get_click_through_modifier()
            self.overlay.set_click_through_modifier(self.click_through_modifier)
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

    def save_current_magic_zone(self):
        """将当前神奇区域保存为书签，关闭软件后仍可还原"""
        from PyQt5.QtWidgets import QMessageBox
        zone = self.overlay.activation_zone or self.saved_magic_zone
        if zone is None:
            QMessageBox.information(self, "提示", "请先设置或使用一个神奇区域后再保存。")
            return
        self.pinned_magic_zone = QRect(zone)
        self._save_config()
        QMessageBox.information(self, "提示", "已保存当前神奇区域，可随时通过「还原神奇区域」恢复。")

    def restore_pinned_magic_zone(self):
        """还原已保存的神奇区域并立即使用"""
        from PyQt5.QtWidgets import QMessageBox
        if getattr(self, "pinned_magic_zone", None) is None:
            QMessageBox.information(self, "提示", "尚未保存过神奇区域，请先使用「保存当前神奇区域」。")
            return
        if not self.overlay_visible:
            self.toggle_overlay()
        self.overlay.set_activation_zone(self.pinned_magic_zone)
        self.overlay.toggle_zone_visibility(True)
        self.overlay.mode = 'pointer'
        self.overlay.setCursor(Qt.ArrowCursor)
        self.overlay.set_mouse_transparent(True)
        self.saved_magic_zone = self.pinned_magic_zone
        self._save_config()
    
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
