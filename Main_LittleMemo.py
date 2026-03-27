__version__ = "1.0.0"
import sys
import json
import os
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QCheckBox, QScrollArea, QFrame, QMenu, QLabel, QSystemTrayIcon, QGraphicsOpacityEffect
)
from PySide6.QtCore import Qt, QPoint, QEvent, QRect, QSize, QPropertyAnimation, QEasingCurve, QTime, QSettings
from PySide6.QtGui import QPainter, QColor, QAction, QCursor, QPixmap, QPen, QPalette, QIcon

# 获取程序运行时的根目录（兼容打包后的 .exe）
if getattr(sys, 'frozen', False):
    # 打包后的路径：.exe 所在的文件夹
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # 开发环境路径：.py 所在的文件夹
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 重新定义文件路径为“绝对路径”
NOTES_FILE = os.path.join(BASE_DIR, "notes.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

# NOTES_FILE = "notes.json"
# CONFIG_FILE = "config.json"
MARGIN = 12 

THEMES = {
    "经典深": ("rgba(45, 45, 45, 200)", "#4facfe", "#00f2fe"),
    "午夜蓝": ("rgba(25, 35, 50, 200)", "#6a11cb", "#2575fc"),
    "薄暮红": ("rgba(60, 30, 30, 200)", "#ff0844", "#ffb199"),
    "森林绿": ("rgba(30, 50, 40, 200)", "#0ba360", "#3cba92"),
    "极客黑": ("rgba(10, 10, 10, 220)", "#434343", "#000000")
}

DEFAULT_W=287
DEFAULT_H=439
DEFAULT_X=1939
DEFAULT_Y=783

class StrikeoutLineEdit(QLineEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_strikeout = False
        self.setFrame(False) # 无边框
        self.setBackgroundRole(QPalette.NoRole) # 透明背景

    def set_strikeout(self, strikeout):
        self.is_strikeout = strikeout
        self.update() # 强制重绘

    def paintEvent(self, event):
        # 先让系统画好文字
        super().paintEvent(event)
        
        # 如果需要删除线，我们就动手画
        if self.is_strikeout and self.text():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            
            # 设置画笔：白色，粗细 1.5px，圆头（看起来更自然）
            pen = QPen(QColor(255, 255, 255, 180), 0.75, Qt.SolidLine, Qt.RoundCap)
            painter.setPen(pen)
            
            # 计算文字的实际宽度
            font_metrics = self.fontMetrics()
            text_width = font_metrics.horizontalAdvance(self.text())
            
            # 计算横线的y轴位置（文字中间偏下一点点，通常是高度的 0.6 倍）
            line_y = self.height() * 0.5
            
            # 计算横线的水平起止点：
            # 默认文字靠左对齐，padding 为 0
            # 我们让它从 -2px 开始，到 text_width + 2px 结束
            start_x = -8
            end_x = text_width + 5
            
            # 画横线
            painter.drawLine(start_x, line_y, end_x, line_y)
            painter.end()

class TaskItem(QWidget):
    def __init__(self, text, done, parent_window):
        super().__init__()
        self.parent_win = parent_window
        self.is_done = done
        # 清理掉可能存在的旧前缀，确保只存纯文本
        self.raw_text = text.lstrip("· ").lstrip("● ").strip()
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0) # 紧紧贴着

        # --- 左侧：专用圆点 Label ---
        self.bullet = QLabel("  ●  ")
        self.bullet.setAlignment(Qt.AlignCenter)
        self.bullet.setCursor(Qt.PointingHandCursor)
        # 圆点的颜色永远是淡淡的白色，无删除线
        self.bullet.setStyleSheet("QLabel { color: rgba(255, 255, 255, 150); font-size: 14px; background: transparent; padding: 5px 0px; }")

        # --- 右侧：自定义的 StrikeoutLineEdit ---
        self.label = StrikeoutLineEdit(self.raw_text)
        self.checkbox = self.label # 兼容旧代码调用
        self.label.setReadOnly(True)
        self.label.setCursor(Qt.PointingHandCursor)
        
        # 右键菜单适配
        self.label.setContextMenuPolicy(Qt.CustomContextMenu)
        self.label.customContextMenuRequested.connect(lambda pos: self.parent_win.show_item_menu(pos, self))
        
        layout.addWidget(self.bullet)
        layout.addWidget(self.label, 1) # 占据剩余所有空间

        self.update_style()

        # 事件过滤：单击切换，双击编辑
        self.bullet.installEventFilter(self)
        self.label.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj in (self.bullet, self.label):
            if event.type() == QEvent.MouseButtonPress:
                if event.button() == Qt.LeftButton:
                    # 1. 切换状态并立即更新视觉效果（变灰/加划线）
                    self.is_done = not self.is_done
                    self.update_style()
                    
                    # 2. 立即保存数据
                    self.parent_win.save_data()
                    
                    # 3. 重点：延迟 300ms 再执行排序沉底
                    # 这样你能看清“划掉”的动作，然后它才优雅地滑到下面
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(300, self.parent_win.reorder_tasks)
                    
                    return True
                    
            elif event.type() == QEvent.MouseButtonDblClick:
                self.start_edit()
                return True
                
        return super().eventFilter(obj, event)

    def start_edit(self):
        # 1. 进入编辑状态前，先断开之前的信号，防止多次绑定
        try:
            self.label.editingFinished.disconnect()
            self.label.returnPressed.disconnect()
        except:
            pass

        # 2. 设置状态
        self.label.set_strikeout(False)
        self.label.setReadOnly(False)
        self.label.setText(self.raw_text)
        
        # 3. 样式微调：编辑时给个淡淡的底色，让用户知道正在编辑
        self.label.setStyleSheet(f"""
            QLineEdit {{
                color: white;
                font-size: 14px;
                background: rgba(255, 255, 255, 30);
                border-radius: 3px;
                padding: 5px 5px;
            }}
        """)
        
        self.label.setFocus()
        self.label.selectAll()

        # 4. 关键：绑定信号
        # returnPressed 处理回车
        # editingFinished 处理点击空白处（失去焦点）
        self.label.returnPressed.connect(self.finish_edit)
        self.label.editingFinished.connect(self.finish_edit)

    def finish_edit(self):
        # 如果已经不是只读状态，说明正在编辑中，需要保存
        if not self.label.isReadOnly():
            self.label.setReadOnly(True)
            
            # 这里的断开连接很重要，防止下次编辑时逻辑混乱
            try:
                self.label.editingFinished.disconnect(self.finish_edit)
                self.label.returnPressed.disconnect(self.finish_edit)
            except:
                pass

            new_text = self.label.text().strip()
            if new_text:
                self.raw_text = new_text
            
            # 恢复正常样式和删除线状态
            self.update_style()
            self.parent_win.save_data()

    def update_style(self):
        # 根据状态决定颜色
        # 划掉后用 100 透明度（变灰），正常时用 255（纯白不透明）
        opacity = 100 if self.is_done else 255
        text_color = f"rgba(255, 255, 255, {opacity})"
        
        # 圆点的样式：颜色现在跟 opacity 挂钩
        self.bullet.setStyleSheet(f"""
            QLabel {{ 
                color: {text_color}; 
                font-size: 14px; 
                background: transparent; 
                padding: 5px 2px; 
            }}
        """)
        
        # 文字的样式和删除线
        self.label.set_strikeout(self.is_done)
        self.label.setStyleSheet(f"""
            QLineEdit {{
                color: {text_color};
                font-size: 14px;
                background: transparent;
                border: none;
                padding: 5px 0px;
            }}
        """)

class StickyNote(QWidget):
    def __init__(self):
        super().__init__()
        self._dir = None
        self.dragPos = None
        self.is_resizing = False
        self.current_theme = THEMES["经典深"]
        
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setMinimumSize(220, 150)
        
        self.setup_ui()
        self.load_config() 
        self.load_data()
        self.init_tray()

    def init_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base_path, "MemoIcon.ico")
        
        # 设置托盘图标
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
            self.setWindowIcon(QIcon(icon_path)) # 同时也设置窗口左上角的图标
        else:
            # 如果没找到图标，依然用亮蓝色方块保底，防止崩溃
            pixmap = QPixmap(16, 16)
            pixmap.fill(QColor("#42ced5"))
            self.tray_icon.setIcon(QIcon(pixmap))

        tray_menu = QMenu()
        # 稍微美化下菜单样式
        tray_menu.setStyleSheet("""
            QMenu { background-color: #2c2c2c; color: white; border: 1px solid #444; font-family: "Microsoft YaHei"; }
            QMenu::item:selected { background-color: #3d3d3d; }
        """)

        # 1. 显示便签
        show_action = tray_menu.addAction("显示便签")
        show_action.triggered.connect(self.show_normal) # 使用 showNormal 能从最小化恢复

        # 2. 开机自启 (根据当前状态设置初始文字)
        initial_text = "取消开机自启动" if self.check_autostart_status() else "开机自动启动"
        self.autostart_action = tray_menu.addAction(initial_text)
        # 点击时执行切换逻辑
        self.autostart_action.triggered.connect(self.toggle_autostart_dynamic)

        tray_menu.addSeparator()

        # 3. 彻底退出
        quit_action = tray_menu.addAction("退出程序")
        quit_action.triggered.connect(self.real_quit)

        self.tray_icon.setContextMenu(tray_menu)


        
        # 额外加分项：左键双击托盘图标也能显示便签
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        
        self.tray_icon.show()

    def show_normal(self):
        self.show()
        self.activateWindow() # 让窗口置顶并获得焦点

    def on_tray_icon_activated(self, reason):
        # 当双击托盘图标时
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_normal()

    def real_quit(self):
        # 真正的退出逻辑
        self.tray_icon.hide() # 先隐藏图标，防止残留
        QApplication.instance().quit() # 结束进程

    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.activateWindow()

    def check_autostart_status(self):
        """检查注册表是否已存在启动项"""
        import winreg as reg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            key = reg.OpenKey(reg.HKEY_CURRENT_USER, key_path, 0, reg.KEY_READ)
            reg.QueryValueEx(key, "LittleMemo")
            reg.CloseKey(key)
            return True
        except FileNotFoundError:
            return False
        except Exception:
            return False

    def toggle_autostart_dynamic(self):
        """根据当前菜单文字，动态切换注册表状态并更新 UI"""
        import winreg as reg
        import sys
        import os

        # 1. 获取程序真实路径 (兼容打包后的 exe)
        if getattr(sys, 'frozen', False):
            app_path = sys.executable
        else:
            app_path = os.path.abspath(sys.argv[0])

        app_name = "LittleMemo"
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"

        try:
            # 2. 打开注册表
            key = reg.OpenKey(reg.HKEY_CURRENT_USER, key_path, 0, reg.KEY_SET_VALUE)
            
            # 3. 根据当前文字判断操作
            if self.autostart_action.text() == "开机自动启动":
                # 执行开启操作
                reg.SetValueEx(key, app_name, 0, reg.REG_SZ, f'"{app_path}"')
                self.autostart_action.setText("取消开机自启动")
            else:
                # 执行关闭操作
                try:
                    reg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
                self.autostart_action.setText("开机自动启动")
            
            reg.CloseKey(key)
        except Exception as e:
            # 如果权限不足或路径错误，这里会捕获
            print(f"操作注册表失败: {e}")



    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        self.container = QFrame()
        self.container.setMouseTracking(True)
        
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(15, 10, 15, 15)
        container_layout.setSpacing(10)

        # 顶部栏
        top_layout = QHBoxLayout()
        self.menu_btn = QPushButton("🎨")
        self.menu_btn.setStyleSheet("font-size: 18 px; border: none;")
        self.close_btn = QPushButton("×")
        btn_style = "QPushButton { color: rgba(255, 255, 255, 150); border: none; font-size: 18px; background: transparent; } QPushButton:hover { color: white; background: rgba(255, 255, 255, 30); border-radius: 4px; }"
        self.menu_btn.setStyleSheet(btn_style)
        self.close_btn.setStyleSheet(btn_style)
        
        self.menu_btn.clicked.connect(self.show_theme_menu)
        self.close_btn.clicked.connect(self.close)
        top_layout.addWidget(self.menu_btn); top_layout.addStretch(); top_layout.addWidget(self.close_btn)
        container_layout.addLayout(top_layout)

        # 输入框
        input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("记点什么...")
        self.input_field.returnPressed.connect(self.add_task)
        self.input_field.setStyleSheet("QLineEdit { color: white; background: rgba(255, 255, 255, 20); border-radius: 6px; padding: 6px; border: none; }")
        self.add_btn = QPushButton("+")
        self.add_btn.setFixedSize(30, 30)
        self.add_btn.clicked.connect(self.add_task)
        input_layout.addWidget(self.input_field); input_layout.addWidget(self.add_btn)
        container_layout.addLayout(input_layout)

        # 列表区域
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        # 修改 self.scroll 的样式表
        self.scroll.setStyleSheet("""
            QScrollArea, QScrollArea > QWidget > QWidget {
                background: transparent;
                border: none;
            }
            #listWidget { background: transparent; }

            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 5px;
                margin: 0px;
            }

            /* 默认状态：全透明 */
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0); 
                min-height: 20px;
                border-radius: 2px;
            }

            /* 悬停状态：迅速变白（这里先设置颜色，动画由下面代码控制） */
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 150);
            }

            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        """)
        # 1. 创建透明度效果器并应用到滚动条上
        self.opacity_effect = QGraphicsOpacityEffect(self.scroll.verticalScrollBar())
        self.opacity_effect.setOpacity(0)  # 初始完全不可见
        self.scroll.verticalScrollBar().setGraphicsEffect(self.opacity_effect)

        # 2. 创建渐变动画
        self.scroll_fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.scroll_fade_anim.setDuration(200)  # 200毫秒，非常迅速
        self.scroll_fade_anim.setEasingCurve(QEasingCurve.InOutQuad)

        # 3. 让滚动区域监听鼠标事件
        self.scroll.installEventFilter(self)


        self.list_widget = QWidget()
        self.list_widget.setObjectName("listWidget") # 给它个名字，对应上面的 QSS

        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setAlignment(Qt.AlignTop)
        self.list_layout.setContentsMargins(0, 5, 0, 0)
        self.list_layout.setSpacing(2)

        self.list_layout.addStretch()
        
        self.scroll.setWidget(self.list_widget)
        container_layout.addWidget(self.scroll)

        self.main_layout.addWidget(self.container)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rgba = self.current_theme[0].replace("rgba(", "").replace(")", "").split(",")
        color = QColor(int(rgba[0]), int(rgba[1]), int(rgba[2]), int(rgba[3]))
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 12, 12)

    def _update_cursor(self, pos):
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        self._dir = ""
        if x < MARGIN: self._dir += "L"
        elif x > w - MARGIN: self._dir += "R"
        if y < MARGIN: self._dir += "T"
        elif y > h - MARGIN: self._dir += "B"
        cursors = {"L": Qt.SizeHorCursor, "R": Qt.SizeHorCursor, "T": Qt.SizeVerCursor, "B": Qt.SizeVerCursor,
                   "LT": Qt.SizeFDiagCursor, "RB": Qt.SizeFDiagCursor, "RT": Qt.SizeBDiagCursor, "LB": Qt.SizeBDiagCursor, "": Qt.ArrowCursor}
        self.setCursor(cursors.get(self._dir, Qt.ArrowCursor))

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        if not self.is_resizing and not self.dragPos: self._update_cursor(pos)
        if self.is_resizing:
            rect = self.geometry()
            gp = event.globalPosition().toPoint()
            if "L" in self._dir: rect.setLeft(gp.x())
            elif "R" in self._dir: rect.setRight(gp.x())
            if "T" in self._dir: rect.setTop(gp.y())
            elif "B" in self._dir: rect.setBottom(gp.y())
            if rect.width() >= self.minimumWidth() and rect.height() >= self.minimumHeight(): self.setGeometry(rect)
        elif self.dragPos: self.move(event.globalPosition().toPoint() - self.dragPos)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._dir: self.is_resizing = True
            elif event.position().y() < 50: self.dragPos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseReleaseEvent(self, event):
        self.is_resizing = False
        self.dragPos = None
        self._update_cursor(event.position().toPoint())

    def eventFilter(self, obj, event):
        if obj == self.scroll:
            # 鼠标进入/离开的渐变动画
            if event.type() == QEvent.Enter:
                self.scroll_fade_anim.stop()
                # 关键：确保使用 self.opacity_effect
                self.scroll_fade_anim.setStartValue(self.opacity_effect.opacity())
                self.scroll_fade_anim.setEndValue(1.0)
                self.scroll_fade_anim.start()
            elif event.type() == QEvent.Leave:
                self.scroll_fade_anim.stop()
                self.scroll_fade_anim.setStartValue(self.opacity_effect.opacity())
                self.scroll_fade_anim.setEndValue(0.0)
                self.scroll_fade_anim.start()
        return super().eventFilter(obj, event)
    
    def apply_theme(self, t):
        self.current_theme = t
        self.add_btn.setStyleSheet(f"QPushButton {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {t[1]},stop:1 {t[2]}); color: white; border-radius: 6px; font-weight: bold; border:none; }}")
        self.update() 

    def show_theme_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background: #333; color: white; border: 1px solid #555; } QMenu::item:selected { background: #555; }")
        for name, data in THEMES.items():
            a = QAction(name, self); a.triggered.connect(lambda _, d=data: self.change_theme(d))
            menu.addAction(a)
        menu.exec(QCursor.pos())

    def change_theme(self, d): self.apply_theme(d); self.save_config()

    def add_task(self):
        if t := self.input_field.text().strip():
            # 调用创建逻辑
            self.create_item(t, False)
            self.input_field.clear()
            self.save_data()

    def create_item(self, text, done):
        item = TaskItem(text, done, self)
        # 插入到弹簧之前
        idx = max(0, self.list_layout.count() - 1)
        self.list_layout.insertWidget(idx, item)
        
        # 强制让新条目更新一次样式，防止初始化颜色错误
        item.update_style()
        return item


    def show_item_menu(self, pos, w):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background: #333; color: white; border: 1px solid #555; }")
        act = QAction("删除任务", self); act.triggered.connect(lambda: self.delete_task(w))
        menu.addAction(act); menu.exec(QCursor.pos())

    def delete_task(self, w): self.list_layout.removeWidget(w); w.deleteLater(); self.save_data()

    def reorder_tasks(self):
        # 1. 找出所有 TaskItem 类型的组件
        items = []
        for i in range(self.list_layout.count()):
            widget = self.list_layout.itemAt(i).widget()
            if isinstance(widget, TaskItem):
                items.append(widget)
        
        # 2. 按照 is_done 排序：False (0) 在前，True (1) 在后
        # Python 的 sort 是稳定的，会保持原本的相对顺序
        items.sort(key=lambda x: x.is_done)
        
        # 3. 重新插入布局（insertWidget 会自动处理位置移动）
        for i, item in enumerate(items):
            self.list_layout.insertWidget(i, item)
            
        # 4. 确保弹簧永远在最后
        # 找到当前的弹簧索引并移动它（或者简单的，只要 insert 逻辑对，弹簧会自动往后挤）

    def save_data(self):
        tasks = []
        for i in range(self.list_layout.count()):
            item = self.list_layout.itemAt(i).widget()
            # 确保只处理 TaskItem 类型的组件
            if isinstance(item, TaskItem):
                tasks.append({
                    "text": item.raw_text,  # 使用我们在类里定义的纯文本属性
                    "done": item.is_done    # 使用我们在类里定义的布尔值状态
                })
        
        # 写入文件
        try:
            with open(NOTES_FILE, "w", encoding="utf-8") as f:
                json.dump(tasks, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"保存失败: {e}")

    def load_data(self):
        import os
        import json
        
        # 1. 如果文件不存在，先创建一个带初始数据的 notes.json
        if not os.path.exists(NOTES_FILE):
            initial_data = [
                {"text": "开始你的事项！", "done": False},
                {"text": "单击条目可划掉已完成事项", "done": False}
            ]
            try:
                with open(NOTES_FILE, "w", encoding="utf-8") as f:
                    json.dump(initial_data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"初始化数据失败: {e}")

        # 2. 正常读取文件（此时文件肯定已经存在了，除非上面写失败了）
        if os.path.exists(NOTES_FILE):
            try:
                with open(NOTES_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for i in data:
                        self.create_item(i["text"], i["done"])
            except Exception as e:
                print(f"加载数据失败: {e}")

    def save_config(self):
        name = next((k for k, v in THEMES.items() if v == self.current_theme), "经典深")
        conf = {"x": self.x(), "y": self.y(), "w": self.width(), "h": self.height(), "theme": name}
        with open(CONFIG_FILE, "w", encoding="utf-8") as f: json.dump(conf, f)

    def load_config(self):
        # 1. 尝试读取现有配置
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    c = json.load(f)
                    # 恢复位置和尺寸 (287x439 是你的黄金比例)
                    self.setGeometry(c.get("x", DEFAULT_X), c.get("y", DEFAULT_Y), c.get("w", DEFAULT_W), c.get("h", DEFAULT_H))
                    # 恢复主题
                    self.apply_theme(THEMES.get(c.get("theme"), THEMES["经典深"]))
                    return
            except: 
                pass
        
        # 2. 如果文件不存在或读取失败，执行初始化
        # 设置默认大小
        self.setGeometry(DEFAULT_X, DEFAULT_Y, DEFAULT_W, DEFAULT_H)
        # 设置默认主题
        self.apply_theme(THEMES["经典深"])
        
        # 3. 【关键】立刻生成配置文件，别等关闭程序再写
        try:
            self.save_config()
        except:
            pass

    def closeEvent(self, event):
        # 如果托盘图标还在，就只是隐藏窗口，而不是退出程序
        if self.tray_icon.isVisible():
            self.hide()
            event.ignore() # 忽略退出信号
        else:
            event.accept() # 如果托盘由于某种原因没了，才允许退出

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = StickyNote()
    w.show()
    sys.exit(app.exec())