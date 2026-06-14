#!/usr/bin/env python3
"""测试光标位置输入功能"""

import os
import subprocess
import sys
import time

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from voice_input.typer import TextInput


def check_environment():
    """检测系统环境"""
    print("=" * 60)
    print("系统环境检测")
    print("=" * 60)
    
    # 检测桌面环境
    session = os.environ.get('XDG_SESSION_TYPE', 'unknown')
    desktop = os.environ.get('XDG_CURRENT_DESKTOP', 'unknown')
    print(f"会话类型: {session}")
    print(f"桌面环境: {desktop}")
    print(f"DISPLAY: {os.environ.get('DISPLAY', 'not set')}")
    print(f"WAYLAND_DISPLAY: {os.environ.get('WAYLAND_DISPLAY', 'not set')}")
    
    # 检测可用工具
    print("\n可用工具:")
    tools = ['xdotool', 'wtype', 'ydotool', 'wl-copy', 'xclip']
    for tool in tools:
        result = subprocess.run(['which', tool], capture_output=True)
        status = "✅" if result.returncode == 0 else "❌"
        print(f"  {status} {tool}")
    
    print()


def test_input_method(method_name, method_type):
    """测试单个输入方法"""
    print(f"\n{'=' * 60}")
    print(f"测试: {method_name}")
    print(f"{'=' * 60}")
    print(f"配置: method='{method_type}'")
    print("\n⏰ 5秒后开始测试，请将光标放在文本编辑器中...")
    
    for i in range(5, 0, -1):
        print(f"   {i}...", end='\r')
        time.sleep(1)
    
    print("\n🎯 开始输入测试文本...")
    
    typer = TextInput(method=method_type)
    test_text = "测试中文输入123 Test English"
    
    success = typer.input_text(test_text)
    
    if success:
        print(f"✅ {method_name} 输入成功")
    else:
        print(f"❌ {method_name} 输入失败")
    
    return success


def main():
    """主测试流程"""
    print("\n🎤 Voice Input - 光标位置输入测试\n")
    
    # 检测环境
    check_environment()
    
    # 测试方案
    tests = [
        ("xdotool (X11)", "xdotool"),
        ("wtype (Wayland)", "wtype"),
        ("自动检测", "type"),
    ]
    
    results = {}
    
    for test_name, method_type in tests:
        try:
            success = test_input_method(test_name, method_type)
            results[test_name] = success
        except KeyboardInterrupt:
            print("\n\n⚠️  测试中断")
            break
        except Exception as e:
            print(f"❌ 测试出错: {e}")
            results[test_name] = False
    
    # 总结
    print(f"\n{'=' * 60}")
    print("测试总结")
    print(f"{'=' * 60}")
    for test_name, success in results.items():
        status = "✅ 成功" if success else "❌ 失败"
        print(f"{status} - {test_name}")
    
    # 推荐配置
    print(f"\n{'=' * 60}")
    print("推荐配置")
    print(f"{'=' * 60}")
    
    session = os.environ.get('XDG_SESSION_TYPE', 'unknown')
    if session == 'x11':
        print("检测到 X11 环境，推荐配置:")
        print("  input:")
        print("    method: 'xdotool'")
    elif session == 'wayland':
        print("检测到 Wayland 环境，推荐配置:")
        print("  input:")
        print("    method: 'wtype'")
    else:
        print("未知环境，推荐使用自动检测:")
        print("  input:")
        print("    method: 'type'")
    
    print()


if __name__ == '__main__':
    main()
