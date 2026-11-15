import customtkinter as ctk
from tkinter import messagebox
import ctypes
from ctypes import wintypes
import threading
import time
import pystray
from PIL import Image, ImageDraw
import os

# --- Windows API 核心逻辑 ---
user32 = ctypes.windll.user32
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
SWP_NOMOVE = 0x0001
SWP_NOSIZE = 0x0002
GA_ROOT = 2

user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
user32.SetWindowLongW.restype = ctypes.c_long

pinned_windows = {}
ui_buttons = {}
current_hwnd = None
my_hwnd = None
is_running = True
tray_icon = None

def get_window_under_mouse():
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    hwnd = user32.WindowFromPoint(pt)
    if hwnd:
        hwnd = user32.GetAncestor(hwnd, GA_ROOT)
    return hwnd

def get_window_title(hwnd):
    if not hwnd: return ""
    length = user32.GetWindowTextLengthW(hwnd)
    buff = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buff, length + 1)
    return buff.value

def force_topmost(hwnd, topmost=True):
    ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if topmost:
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_TOPMOST)
        user32.SetWindowPos(hwnd, wintypes.HWND(HWND_TOPMOST), 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
    else:
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style & ~WS_EX_TOPMOST)
        user32.SetWindowPos(hwnd, wintypes.HWND(HWND_NOTOPMOST), 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)

def daemon_thread():
    while is_running:
        for hwnd in list(pinned_windows.keys()):
            if not user32.IsWindow(hwnd):
                # 如果窗口被关了，从 UI 和字典里清理
                del pinned_windows[hwnd]
                if hwnd in ui_buttons:
                    ui_buttons[hwnd].destroy()
                    del ui_buttons[hwnd]
                continue
            user32.SetWindowPos(hwnd, wintypes.HWND(HWND_TOPMOST), 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
        time.sleep(0.5)

# --- UI 交互逻辑 ---
def update_mouse_info():
    global current_hwnd
    if not is_running: return
    
    hwnd = get_window_under_mouse()
    if hwnd != my_hwnd and hwnd != 0:
        current_hwnd = hwnd
        title = get_window_title(hwnd)
        if title:
            lbl_target.configure(text=f"🎯 当前指向: {title[:20]}..." if len(title) > 20 else f"🎯 当前指向: {title}", text_color="#4CAF50")
        else:
            lbl_target.configure(text="🎯 当前指向: (无标题窗口)", text_color="gray")
    elif hwnd == my_hwnd:
        lbl_target.configure(text="🎯 当前指向: 本工具窗口", text_color="gray")
    else:
        current_hwnd = None
        lbl_target.configure(text="🎯 当前指向: 桌面", text_color="gray")
    app.after(100, update_mouse_info)

def unpin_window(hwnd):
    if hwnd in pinned_windows:
        force_topmost(hwnd, False)
        del pinned_windows[hwnd]
        if hwnd in ui_buttons:
            ui_buttons[hwnd].destroy()
            del ui_buttons[hwnd]

def action_pin():
    if not current_hwnd or current_hwnd == my_hwnd:
        messagebox.showwarning("提示", "请把鼠标移动到其它软件界面上！")
        return
    title = get_window_title(current_hwnd)
    if current_hwnd in pinned_windows:
        return

    force_topmost(current_hwnd, True)
    pinned_windows[current_hwnd] = title
    
    # 动态生成带叉的按钮
    display_title = title[:15] + "..." if len(title) > 15 else title
    btn = ctk.CTkButton(frame_list, text=f"❌ {display_title}", fg_color="#C62828", hover_color="#E53935", 
                        anchor="w", height=30, command=lambda h=current_hwnd: unpin_window(h))
    btn.pack(fill="x", pady=2, padx=5)
    ui_buttons[current_hwnd] = btn

def on_closing():
    global is_running
    is_running = False
    for hwnd in list(pinned_windows.keys()):
        if user32.IsWindow(hwnd):
            force_topmost(hwnd, False)
    app.destroy()
    if tray_icon:
        tray_icon.stop()
    os._exit(0) # 强制清理所有线程

# --- 托盘逻辑 ---
def setup_tray():
    global tray_icon
    # 如果没有图标，自动用代码画一个纯色圆形当托盘图标，防报错
    try:
        image = Image.open("icon.ico")
    except:
        image = Image.new('RGB', (64, 64), color = (30, 30, 30))
        d = ImageDraw.Draw(image)
        d.ellipse((10, 10, 54, 54), fill='#0078D7')

    def show_window(icon, item):
        app.deiconify()

    def quit_app(icon, item):
        on_closing()

    def tray_pin_current(icon, item):
        if current_hwnd and current_hwnd not in pinned_windows and current_hwnd != my_hwnd:
            title = get_window_title(current_hwnd)
            force_topmost(current_hwnd, True)
            pinned_windows[current_hwnd] = title
            # 要在主线程更新 UI，防止报错
            app.after(0, lambda: action_pin()) 

    menu = pystray.Menu(
        pystray.MenuItem('显示主界面', show_window),
        pystray.MenuItem('锁定当前指向窗口', tray_pin_current),
        pystray.MenuItem('退出', quit_app)
    )
    tray_icon = pystray.Icon("TopmostTool", image, "万能置顶工具", menu)
    threading.Thread(target=tray_icon.run, daemon=True).start()

# --- 界面构建 ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

app = ctk.CTk()
app.title("万能窗口置顶器")
app.geometry("400x480")
app.protocol("WM_DELETE_WINDOW", lambda: app.withdraw()) # 点叉时直接隐藏到托盘，不要退出！

app.update_idletasks()
my_hwnd = user32.GetParent(app.winfo_id())

lbl_target = ctk.CTkLabel(app, text="🎯 当前指向: (等待获取)", font=("微软雅黑", 15, "bold"))
lbl_target.pack(pady=20)

btn_pin = ctk.CTkButton(app, text="📌 强制置顶当前窗口", font=("微软雅黑", 14, "bold"), height=40, command=action_pin)
btn_pin.pack(pady=5)

frame_list = ctk.CTkScrollableFrame(app, label_text="已置顶窗口（点击叉号取消）", label_font=("微软雅黑", 12), corner_radius=10)
frame_list.pack(pady=15, padx=20, fill="both", expand=True)

setup_tray()
threading.Thread(target=daemon_thread, daemon=True).start()
update_mouse_info()

if __name__ == "__main__":
    app.mainloop()