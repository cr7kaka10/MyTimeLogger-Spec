#!/usr/bin/env python3
"""
处理华为运动健康截图
用法: python process_image.py <图片路径> [日期]
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.ocr_extractor import OCRExtractor, check_paddleocr_installed
from modules.screenshot_parser import ScreenshotParser
from generate_full_report import generate_comprehensive_report


def process_image(image_path, date_str=None):
    """处理华为运动健康截图"""

    print(f"\n{'='*70}")
    print("📊 处理华为运动健康截图")
    print(f"{'='*70}\n")

    # 检查图片是否存在
    if not os.path.exists(image_path):
        print(f"❌ 图片文件不存在: {image_path}")
        return None

    # 检查 PaddleOCR
    if not check_paddleocr_installed():
        print("⚠️ PaddleOCR 未安装")
        print("\n安装方法:")
        print("  pip install paddlepaddle paddleocr")
        print("\n注意: PaddlePaddle 需要 Python 3.7-3.12")
        print(f"当前 Python 版本: {sys.version}")
        return None

    # 1. OCR 识别
    print(f"📷 正在识别图片: {image_path}")
    ocr = OCRExtractor()
    text = ocr.extract_text_from_image(image_path)

    print(f"\n📄 OCR 识别结果:")
    print("-" * 70)
    print(text)

    # 2. 解析睡眠数据
    print(f"\n\n{'='*70}")
    print("🔍 解析睡眠数据")
    print(f"{'='*70}\n")

    parser = ScreenshotParser()
    sleep_data = parser.parse_sleep_data(text, image_date=date_str)

    # 如果没有指定日期，使用识别到的日期
    if not date_str:
        date_str = sleep_data.get('date')

    print(parser.format_sleep_summary(sleep_data))

    # 3. 保存睡眠数据
    print(f"\n{'='*70}")
    print("💾 保存睡眠数据")
    print(f"{'='*70}\n")

    output_file = parser.save_sleep_data(sleep_data)
    print(f"✅ 睡眠数据已保存: {output_file}")

    # 4. 提取 aTimeLogger 数据并生成报告
    if date_str:
        print(f"\n{'='*70}")
        print(f"📊 生成 {date_str} 的完整报告")
        print(f"{'='*70}\n")

        try:
            report_path = generate_comprehensive_report(date_str)
            if report_path:
                print(f"\n✅ 报告生成完成!")
                print(f"📄 报告路径: {report_path}")
        except Exception as e:
            print(f"⚠️ 生成报告失败: {e}")
            print("   可能需要配置 aTimeLogger 账号信息")

    return sleep_data


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python process_image.py <图片路径> [日期]")
        print("\n示例:")
        print("  python process_image.py screenshot.png")
        print("  python process_image.py screenshot.png 2026-03-20")
        sys.exit(1)

    image_path = sys.argv[1]
    date_str = sys.argv[2] if len(sys.argv) > 2 else None

    process_image(image_path, date_str)
