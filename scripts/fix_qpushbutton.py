# -*- coding: utf-8 -*-
"""
智能替换 QPushButton 为 PushButton
只替换实例化调用，不替换字符串/注释里的样式选择器
"""
import re
import os

# 需要处理的文件列表
FILES = [
    "app/ui/activity_panel.py",
    "app/ui/category_dialog.py",
    "app/ui/dialogs.py",
    "app/ui/goals_panel.py",
]

# fluent_theme.py 里的 QPushButton 是样式表字符串，不替换

def fix_file(path):
    """智能替换单个文件"""
    if not os.path.exists(path):
        print(f"❌ 文件不存在：{path}")
        return

    with open(path, encoding='utf-8') as f:
        content = f.read()

    original = content

    # 1. 移除 QPushButton 的 import
    # 处理单独一行的情况
    content = re.sub(r'from PyQt6\.QtWidgets import QPushButton\n', '', content)
    # 处理在列表中的情况（后面有逗号）
    content = re.sub(r'QPushButton,\s*', '', content)
    # 处理在列表中的情况（前面有逗号）
    content = re.sub(r',\s*QPushButton(?=\s*[,\)])', '', content)

    # 2. 确保 qfluentwidgets import 存在
    if 'from qfluentwidgets import' in content:
        # 在现有 import 里加 PushButton（如果还没有）
        if 'PushButton' not in content.split('from qfluentwidgets import')[1].split('\n')[0]:
            content = re.sub(
                r'(from qfluentwidgets import )([^\n]+)',
                lambda m: m.group(1) + 'PushButton, ' + m.group(2),
                content,
                count=1
            )
    else:
        # 在文件开头的 import 区域添加
        # 找到第一个 from PyQt6 import 的位置
        match = re.search(r'(from PyQt6\.QtWidgets import[^\n]+\n)', content)
        if match:
            insert_pos = match.end()
            content = content[:insert_pos] + 'from qfluentwidgets import PushButton\n' + content[insert_pos:]
        else:
            # 如果找不到 PyQt6 import，就加在文件开头
            content = 'from qfluentwidgets import PushButton\n\n' + content

    # 3. 替换实例化（不在字符串/注释里的）
    # 使用更精确的正则表达式
    # 匹配 QPushButton( 但不在引号内
    lines = content.split('\n')
    new_lines = []

    for line in lines:
        # 跳过注释行
        if line.strip().startswith('#'):
            new_lines.append(line)
            continue

        # 检查是否在字符串中（简单检查：如果 QPushButton 在引号内）
        # 这个方法不完美，但对大多数情况有效
        if 'QPushButton' in line:
            # 如果这行包含 setStyleSheet 或在三引号字符串中，不替换
            if 'setStyleSheet' in line or '"""' in line or "'''" in line:
                new_lines.append(line)
                continue

            # 检查 QPushButton 是否在引号内
            in_string = False
            quote_char = None
            result = []
            i = 0

            while i < len(line):
                char = line[i]

                # 处理引号
                if char in ('"', "'") and (i == 0 or line[i-1] != '\\'):
                    if not in_string:
                        in_string = True
                        quote_char = char
                    elif char == quote_char:
                        in_string = False
                        quote_char = None

                # 如果不在字符串中，替换 QPushButton
                if not in_string and line[i:i+11] == 'QPushButton':
                    result.append('PushButton')
                    i += 11
                else:
                    result.append(char)
                    i += 1

            new_lines.append(''.join(result))
        else:
            new_lines.append(line)

    content = '\n'.join(new_lines)

    # 检查是否有修改
    if content != original:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ 已处理：{path}")
        return True
    else:
        print(f"⏭️ 无需修改：{path}")
        return False

# 主程序
print("=" * 60)
print("开始批量替换 QPushButton → PushButton")
print("=" * 60)

modified_count = 0
for filepath in FILES:
    if fix_file(filepath):
        modified_count += 1

print("\n" + "=" * 60)
print(f"处理完成！共修改 {modified_count} 个文件")
print("=" * 60)

# 验证结果
print("\n验证残留的 QPushButton（排除注释和样式表）：")
print("-" * 60)
os.system('powershell -Command "Get-ChildItem app/ui -Recurse -Filter *.py | Select-String -Pattern \'QPushButton\' | Where-Object { $_.Line -notmatch \'#\' -and $_.Line -notmatch \'setStyleSheet\' -and $_.Path -notmatch \'fluent_theme\' } | Select-Object Path, LineNumber, Line | Format-Table -AutoSize"')
