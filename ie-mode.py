import os
import sys
import xml.etree.ElementTree as ET
from xml.dom import minidom
import ctypes
import subprocess
from datetime import datetime
from ctypes import wintypes
import time

# ========================
# Windows API 常量与函数（全版本兼容）
# ========================
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# 核心常量（全版本兼容）
MB_OK = 0x0
MB_YESNO = 0x04
MB_ICONWARNING = 0x30
MB_ICONINFORMATION = 0x40
HWND_TOPMOST = -1
IDYES = 6  # YES按钮返回值
IDNO = 7   # NO按钮返回值

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin():
    """恢复旧版本逻辑：保证普通CMD执行能弹出独立管理员窗口"""
    if not is_admin():
        print("需要管理员权限来修改系统配置...")
        # 旧版参数拼接方式（放弃list2cmdline，优先保证弹窗）
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        sys.exit()

# 安全提示：明确改为按回车Enter继续
def show_security_notice():
    notice = r"""
============================================================
                      【安全与权限说明】
============================================================
  本工具将对系统进行以下必要修改：
  1. 创建配置文件：C:\ProgramData\Microsoft\Edge\ie-sitelist.xml
  2. 写入注册表策略：HKLM\SOFTWARE\Policies\Microsoft\Edge

  【注意事项】
  • 因涉及系统级修改，部分杀毒软件可能拦截/报毒，建议：
    - 运行前临时关闭杀毒软件，或
    - 将本程序加入杀毒软件信任/白名单

  【透明性承诺】
  • 开源脚本，无隐藏行为、无网络请求，可审查/修改源码
  • https://github.com/lwjmm/edge-ie-mode-config/blob/main/ie-mode.py   
============================================================
"""
    print(notice)
    input("请仔细阅读以上说明，按【回车Enter】继续...")

def parse_xml(xml_path):
    if not os.path.exists(xml_path):
        return []
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        return [site.get('url') for site in root.findall('site') if site.get('url')]
    except Exception as e:
        print(f"解析XML失败: {e}")
        return []

def load_deleted_records(txt_path):
    if not os.path.exists(txt_path):
        return []
    records = []
    seen = set()
    with open(txt_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    for line in reversed(lines):
        line = line.strip()
        if ' | ' in line:
            try:
                _, url = line.split(' | ', 1)
                if url and url not in seen:
                    records.append((line, url))
                    seen.add(url)
            except:
                continue
    records.reverse()
    return [(item[1], item[0]) for item in records]

def save_deleted_record(txt_path, url):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(txt_path, 'a', encoding='utf-8') as f:
        f.write(f"{timestamp} | {url}\n")

def remove_url_from_deleted(txt_path, target_url):
    if not os.path.exists(txt_path):
        return
    with open(txt_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    with open(txt_path, 'w', encoding='utf-8') as f:
        for line in lines:
            if ' | ' in line:
                _, url = line.strip().split(' | ', 1)
                if url != target_url:
                    f.write(line)
            else:
                f.write(line)

def clear_all_deleted_records(txt_path):
    """清空所有已删除记录"""
    if os.path.exists(txt_path):
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write("")
    print("已清空所有已删除记录")

def display_list(items, title, show_index=True):
    print(f"\n\n{title}\n")
    print("-" * 50)
    if not items:
        print("  (无)")
    else:
        for i, item in enumerate(items, 1):
            if show_index:
                print(f"  {i}. {item}")
            else:
                print(f"  {item}")
    print("-" * 50 + "\n")

def get_action():
    print("\n\n请选择操作：")
    print("  [A] 添加新网址")
    print("  [D] 删除已有网址")
    print("  [R] 从已删除列表恢复/管理")
    print("  [F] 完成并保存")
    while True:
        choice = input("输入选项 (A/D/R/F): ").strip().upper()
        if choice in ['A', 'D', 'R', 'F']:
            return choice
        print("无效选项，请重新输入")

# 强化URL校验：必须带http/https
def add_new_url(current_urls):
    print("\n\n注意：添加新网址")
    print("格式示例: https://intranet.example.com 或 http://intranet.example.com")
    print("⚠️  必须包含 http:// 或 https:// 前缀，否则Edge无法识别！")
    print("不要包含端口号（如 :8080）")
    
    while True:
        url = input("请输入网址 (或输入 'back' 返回): ").strip()
        if url.lower() == 'back':
            return current_urls
        
        if not url.startswith(('http://', 'https://')):
            print("❌ 错误：网址必须以 http:// 或 https:// 开头！")
            print("示例：https://oa.company.com、http://192.168.1.100")
            continue
        
        if ':' in url[8:]:
            proto = url.split('://')[0]
            host_part = url.split('://')[1]
            host = host_part.split(':')[0]
            path = '/' + '/'.join(host_part.split('/')[1:]) if '/' in host_part else ''
            clean_url = f"{proto}://{host}{path}" if path else f"{proto}://{host}"
            print(f"✅ 已自动清理端口号 → {clean_url}")
            url = clean_url
        
        if url in current_urls:
            print("❌ 该网址已存在！")
            continue
        
        current_urls.append(url)
        print(f"✅ 已添加: {url}")
        return current_urls

def delete_urls(current_urls, deleted_txt_path):
    if not current_urls:
        print("没有可删除的网址")
        return current_urls
    
    display_list(current_urls, "当前配置的网址")
    print("\n输入序号删除（多个用空格分隔），或输入 'all' 删除全部")
    choice = input("选择: ").strip()
    
    if choice.lower() == 'all':
        to_delete = current_urls[:]
        current_urls.clear()
    else:
        indices = []
        try:
            indices = [int(x) - 1 for x in choice.split() if x.isdigit()]
        except:
            pass
        if not indices:
            print("未选择有效序号")
            return current_urls
        
        to_delete = []
        for idx in sorted(indices, reverse=True):
            if 0 <= idx < len(current_urls):
                to_delete.append(current_urls.pop(idx))
    
    for url in to_delete:
        save_deleted_record(deleted_txt_path, url)
        print(f"已删除: {url}")
    
    return current_urls

def restore_from_deleted(current_urls, deleted_list, deleted_txt_path):
    """重构：新增删除/清空已删除记录功能"""
    if not deleted_list:
        print("没有可管理的已删除网址")
        return current_urls
    
    urls_only = [item[0] for item in deleted_list]
    display_list(urls_only, "已删除的网址管理")
    print("请选择操作：")
    print("  [1] 恢复指定网址")
    print("  [2] 删除指定已删除记录")
    print("  [3] 清空所有已删除记录")
    print("  [0] 返回")
    
    while True:
        try:
            sub_choice = int(input("输入选项 (0/1/2/3): ").strip())
            if sub_choice == 0:
                return current_urls
            elif sub_choice == 1:
                idx = int(input("输入序号恢复: ")) - 1
                if 0 <= idx < len(urls_only):
                    url = urls_only[idx]
                    if url not in current_urls:
                        current_urls.append(url)
                        remove_url_from_deleted(deleted_txt_path, url)
                        print(f"已恢复: {url}")
                    else:
                        print("该网址已在当前列表中")
                else:
                    print("序号无效")
                break
            elif sub_choice == 2:
                idx = int(input("输入序号删除该记录: ")) - 1
                if 0 <= idx < len(urls_only):
                    url = urls_only[idx]
                    remove_url_from_deleted(deleted_txt_path, url)
                    print(f"已删除记录: {url}")
                else:
                    print("序号无效")
                break
            elif sub_choice == 3:
                confirm = input("确认清空所有已删除记录？(y/n): ").strip().lower()
                if confirm == 'y':
                    clear_all_deleted_records(deleted_txt_path)
                break
            else:
                print("无效选项，请输入 0/1/2/3")
        except ValueError:
            print("请输入数字")
    
    deleted_list = load_deleted_records(deleted_txt_path)
    return current_urls

def create_xml(urls, xml_path):
    """优化：XML version使用时间戳，提高Edge重新解析概率"""
    # 生成唯一版本号（年月日时分秒）
    version_str = datetime.now().strftime("%Y%m%d%H%M%S")
    root = ET.Element("site-list", version=version_str)
    for url in urls:
        site = ET.SubElement(root, "site", url=url)
        ET.SubElement(site, "compat-mode").text = "IE11"
        ET.SubElement(site, "open-in").text = "IE11"
    
    rough = ET.tostring(root, encoding='utf-8')
    reparsed = minidom.parseString(rough)
    pretty = reparsed.toprettyxml(indent="  ")
    lines = [line for line in pretty.split('\n') if line.strip()]
    
    with open(xml_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

def set_registry_via_cmd(xml_path):
    """修复：InternetExplorerIntegrationLevel类型改为REG_DWORD（官方标准）"""
    try:
        cmd1 = [
            "reg", "add",
            r"HKLM\SOFTWARE\Policies\Microsoft\Edge",
            "/v", "InternetExplorerIntegrationSiteList",
            "/t", "REG_SZ",
            "/d", xml_path,
            "/f"
        ]
        cmd2 = [
            "reg", "add",
            r"HKLM\SOFTWARE\Policies\Microsoft\Edge",
            "/v", "InternetExplorerIntegrationLevel",
            "/t", "REG_DWORD",  # 核心修复：从REG_SZ改为REG_DWORD
            "/d", "1",
            "/f"
        ]
        r1 = subprocess.run(cmd1, capture_output=True, text=True, shell=True)
        r2 = subprocess.run(cmd2, capture_output=True, text=True, shell=True)
        return r1.returncode == 0 and r2.returncode == 0
    except Exception as e:
        print(f"注册表写入失败: {e}")
        return False

def clear_registry_keys():
    keys = [
        "InternetExplorerIntegrationSiteList", 
        "InternetExplorerIntegrationLevel"
    ]
    for key in keys:
        try:
            subprocess.run([
                "reg", "delete",
                r"HKLM\SOFTWARE\Policies\Microsoft\Edge",
                "/v", key,
                "/f"
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True)
        except:
            pass

def export_registry_backup(xml_path):
    reg_file = os.path.join(os.path.dirname(xml_path), "ie_mode_registry_backup.reg")
    try:
        subprocess.run([
            "reg", "export",
            r"HKLM\SOFTWARE\Policies\Microsoft\Edge",
            reg_file,
            "/y"
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return reg_file
    except:
        return None

def get_desktop_path():
    try:
        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        ctypes.windll.shell32.SHGetFolderPathW(None, 0x0000, None, 0, buf)
        return buf.value
    except:
        return os.path.join(os.path.expanduser("~"), "Desktop")

def create_desktop_guide(urls, xml_dir):
    """生成简化版说明文档，补充exe化相关提示"""
    desktop = get_desktop_path()
    guide_path = os.path.join(desktop, "Edge浏览器IE模式说明.md")
    
    with open(guide_path, 'w', encoding='utf-8') as f:
        f.write("# Microsoft Edge 浏览器 IE 模式配置说明\n\n")
        
        # 新增exe化提示（符合GPT建议）
        f.write("## ⚠️ 工具使用说明\n")
        f.write("文件名：Edge浏览器IE模式说明.md，存放位置：桌面\n")
        f.write("本工具适合「自己使用 / 内部 IT / 明确知道用途的人」，不适合普通用户下载即用；\n")
        f.write("exe版本可能被杀毒软件误报，建议使用源码版或加入信任列表。\n\n")
        
        if urls:
            f.write("## 已启用 IE 兼容模式的站点\n\n")
            for url in urls:
                f.write(f"- `{url}`\n")
            f.write("\n> ⚠️ 配置生效说明：\n")
            f.write("> 1. 请完全关闭Edge浏览器后重新打开（可多重启几次）；\n")
            f.write("> 2. 若仍未生效，可等待几分钟后再次尝试。\n")
        else:
            f.write("## 当前状态\n\n")
            f.write("未配置任何 IE 兼容模式站点。\n\n")
            f.write("如需添加，请重新运行本工具。\n")
        
        f.write("\n## 配置文件位置\n\n")
        f.write("所有相关文件存储于以下目录：\n\n")
        f.write("```\n")
        f.write(f"{xml_dir}\n")
        f.write("```\n\n")
        f.write("包含：\n\n")
        f.write("- `ie-sitelist.xml`：当前生效的站点列表（UTF-8编码，URL必须带http/https）\n")
        f.write("- `old-site.txt`：历史删除记录（支持恢复/审计）\n")
        f.write("- `ie_mode_registry_backup.reg`：注册表备份（用于回滚）\n\n")
        
        f.write("## 技术支持\n\n")
        f.write("更多办公效率技巧 & 工具分享\n")
        f.write("欢迎关注公众号「明明见自己」，回复“社群”加入【AGL·明说】。\n")
    
    return guide_path

# 简化版Edge进程提示框：仅提示重启，不执行杀进程/刷新策略
def show_edge_process_prompt():
    prompt_msg = (
        "IE模式配置即将保存！\n\n"
        "【重要提示】\n"
        "1. 配置保存后不会实时生效；\n"
        "2. 请手动关闭所有Edge窗口后重新打开（可多重启几次）；\n"
        "3. 若仍未生效，可等待几分钟后再次尝试。\n\n"
        "点击确定继续保存配置"
    )
    # 仅显示确认弹窗
    user32.MessageBoxW(
        None,
        prompt_msg,
        "配置保存提示",
        MB_OK | MB_ICONINFORMATION | 0x1000  # 0x1000=MB_TOPMOST 强制置顶
    )
    print("\n👉 已确认配置保存提示，开始写入配置...")

def bring_message_box_to_front(title, message):
    console_hwnd = kernel32.GetConsoleWindow()
    if console_hwnd:
        user32.ShowWindow(console_hwnd, 0)

    import threading
    result = [None]
    def show_msg():
        result[0] = user32.MessageBoxW(None, message, title, MB_OK | MB_ICONINFORMATION)
    
    thread = threading.Thread(target=show_msg, daemon=True)
    thread.start()
    
    start = time.time()
    while time.time() - start < 2.0:
        hwnd = user32.FindWindowW(None, title)
        if hwnd:
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                0x0001 | 0x0002 | 0x0010)
            break
        time.sleep(0.1)
    
    thread.join()
    return result[0]

def show_completion_message():
    bring_message_box_to_front(
        "配置成功",
        "IE 模式配置已完成！\n\n"
        "⚠️  配置不会实时生效，请按以下操作：\n"
        "1. 完全关闭所有Edge浏览器窗口；\n"
        "2. 重新打开Edge（可多重启几次）；\n"
        "3. 若仍未生效，可等待几分钟后再次尝试。\n\n"
        "确保所有URL都包含 http:// 或 https:// 前缀！"
    )

def main():
    run_as_admin()
    
    # 显示安全提示（按回车Enter继续）
    show_security_notice()
    
    xml_dir = r"C:\ProgramData\Microsoft\Edge"
    xml_path = os.path.join(xml_dir, "ie-sitelist.xml")
    deleted_txt_path = os.path.join(xml_dir, "old-site.txt")
    os.makedirs(xml_dir, exist_ok=True)
    
    current_urls = parse_xml(xml_path)
    deleted_records = load_deleted_records(deleted_txt_path)
    
    display_list(current_urls, "当前配置的网址")
    if deleted_records:
        deleted_urls = [r[0] for r in deleted_records]
        display_list(deleted_urls, "已删除的网址（可恢复/管理）")
    
    while True:
        action = get_action()
        if action == 'A':
            current_urls = add_new_url(current_urls)
        elif action == 'D':
            current_urls = delete_urls(current_urls, deleted_txt_path)
        elif action == 'R':
            current_urls = restore_from_deleted(current_urls, deleted_records, deleted_txt_path)
            deleted_records = load_deleted_records(deleted_txt_path)
        elif action == 'F':
            break
        
        display_list(current_urls, "当前配置的网址")
        deleted_records = load_deleted_records(deleted_txt_path)
        if deleted_records:
            deleted_urls = [r[0] for r in deleted_records]
            display_list(deleted_urls, "已删除的网址（可恢复/管理）")
    
    # 弹出简化版提示框：仅提示重启，不执行杀进程/刷新策略
    print("\n📌 准备保存配置...")
    show_edge_process_prompt()
    
    # 仅执行核心配置写入逻辑
    if current_urls:
        create_xml(current_urls, xml_path)
        print(f"\n✅ 配置已保存至: {xml_path}\n")
        
        if set_registry_via_cmd(xml_path):
            print("✅ 注册表已更新（符合官方标准类型）\n")
            reg_backup = export_registry_backup(xml_path)
            if reg_backup:
                print(f"✅ 注册表备份: {reg_backup}\n")
        else:
            print("❌ 注册表更新失败！请确保以管理员身份运行。\n")
    else:
        if os.path.exists(xml_path):
            os.remove(xml_path)
            print("\n✅ 所有网址已删除，配置文件已清理\n")
        clear_registry_keys()
        print("✅ IE 模式注册表配置已清除\n")
    
    guide_file = create_desktop_guide(current_urls, xml_dir)
    show_completion_message()
    os.startfile(guide_file)
    sys.exit(0)

if __name__ == "__main__":

    main()
