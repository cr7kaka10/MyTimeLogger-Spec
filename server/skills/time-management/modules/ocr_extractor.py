#!/usr/bin/env python3
"""
OCR 图片识别模块

功能：
- 使用 PaddleOCR 识别华为运动健康截图
- 提取睡眠相关数据
- 支持中英文混合识别
"""

import os
import sys
from pathlib import Path


class OCRExtractor:
    """OCR 图片识别器"""

    def __init__(self, use_gpu=False, lang='ch'):
        """
        初始化 OCR 识别器

        Args:
            use_gpu: 是否使用 GPU 加速
            lang: 语言，'ch' 表示中英文混合
        """
        self.use_gpu = use_gpu
        self.lang = lang
        self.ocr = None

    def _init_ocr(self):
        """延迟初始化 PaddleOCR"""
        if self.ocr is None:
            try:
                from paddleocr import PaddleOCR

                print("🔧 初始化 PaddleOCR...")
                # use_angle_cls=True 可以识别倾斜文字
                # lang='ch' 支持中英文混合
                self.ocr = PaddleOCR(
                    use_angle_cls=True,
                    lang=self.lang,
                    use_gpu=self.use_gpu,
                    show_log=False  # 关闭 PaddleOCR 的日志输出
                )
                print("✅ PaddleOCR 初始化成功")

            except ImportError:
                raise ImportError(
                    "未安装 PaddleOCR，请运行: pip install paddleocr paddlepaddle"
                )

    def extract_text_from_image(self, image_path):
        """
        从图片中提取文本

        Args:
            image_path: 图片路径

        Returns:
            str: 提取的文本内容
        """
        self._init_ocr()

        if not os.path.exists(image_path):
            raise FileNotFoundError(f"图片文件不存在: {image_path}")

        print(f"📷 正在识别图片: {image_path}")

        try:
            # 执行 OCR 识别
            result = self.ocr.ocr(image_path, cls=True)

            # 提取所有识别到的文本
            text_lines = []
            for idx in range(len(result)):
                res = result[idx]
                if res:
                    for line in res:
                        text = line[1][0]  # 获取识别的文本
                        confidence = line[1][1]  # 获取置信度
                        position = line[0]  # 获取位置坐标

                        # 只保留置信度较高的文本
                        if confidence > 0.5:
                            text_lines.append(text)

            # 合并所有文本
            full_text = '\n'.join(text_lines)

            print(f"✅ 识别完成，共提取 {len(text_lines)} 行文本")

            return full_text

        except Exception as e:
            print(f"❌ OCR 识别失败: {e}")
            raise

    def extract_text_with_positions(self, image_path):
        """
        从图片中提取文本（带位置信息）

        Args:
            image_path: 图片路径

        Returns:
            list: 文本列表，每个元素包含文本和位置信息
        """
        self._init_ocr()

        if not os.path.exists(image_path):
            raise FileNotFoundError(f"图片文件不存在: {image_path}")

        print(f"📷 正在识别图片（带位置）: {image_path}")

        try:
            # 执行 OCR 识别
            result = self.ocr.ocr(image_path, cls=True)

            # 提取所有识别到的文本（带位置）
            text_with_positions = []
            for idx in range(len(result)):
                res = result[idx]
                if res:
                    for line in res:
                        text = line[1][0]
                        confidence = line[1][1]
                        position = line[0]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]

                        if confidence > 0.5:
                            # 计算文本框的中心位置（用于排序）
                            center_y = sum([p[1] for p in position]) / 4
                            center_x = sum([p[0] for p in position]) / 4

                            text_with_positions.append({
                                'text': text,
                                'confidence': confidence,
                                'position': position,
                                'center': (center_x, center_y)
                            })

            # 按照从上到下、从左到右排序
            text_with_positions.sort(key=lambda x: (x['center'][1], x['center'][0]))

            print(f"✅ 识别完成，共提取 {len(text_with_positions)} 个文本块")

            return text_with_positions

        except Exception as e:
            print(f"❌ OCR 识别失败: {e}")
            raise

    def extract_sleep_data_from_image(self, image_path):
        """
        从华为运动健康截图中提取睡眠数据

        Args:
            image_path: 图片路径

        Returns:
            dict: 提取的睡眠数据
        """
        # 先提取文本
        text = self.extract_text_from_image(image_path)

        # 导入解析器
        from .screenshot_parser import ScreenshotParser

        # 使用解析器解析文本
        parser = ScreenshotParser()
        sleep_data = parser.parse_sleep_data(text)

        return sleep_data

    def batch_extract(self, image_dir, output_dir=None):
        """
        批量识别图片

        Args:
            image_dir: 图片目录
            output_dir: 输出目录（可选）

        Returns:
            list: 所有图片的识别结果
        """
        image_dir = Path(image_dir)

        if not image_dir.exists():
            raise FileNotFoundError(f"目录不存在: {image_dir}")

        # 支持的图片格式
        image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}

        # 查找所有图片
        image_files = [
            f for f in image_dir.iterdir()
            if f.suffix.lower() in image_extensions
        ]

        if not image_files:
            print(f"⚠️ 未找到图片文件: {image_dir}")
            return []

        print(f"📂 找到 {len(image_files)} 张图片")

        results = []
        for i, image_file in enumerate(image_files, 1):
            print(f"\n[{i}/{len(image_files)}] 处理: {image_file.name}")

            try:
                text = self.extract_text_from_image(str(image_file))
                results.append({
                    'file': str(image_file),
                    'text': text,
                    'success': True
                })
            except Exception as e:
                print(f"❌ 处理失败: {e}")
                results.append({
                    'file': str(image_file),
                    'error': str(e),
                    'success': False
                })

        return results


def check_paddleocr_installed():
    """检查 PaddleOCR 是否已安装"""
    try:
        import paddleocr
        return True
    except ImportError:
        return False


def install_paddleocr():
    """安装 PaddleOCR"""
    import subprocess

    print("📦 正在安装 PaddleOCR...")

    # 安装 paddlepaddle（CPU 版本）
    print("  安装 PaddlePaddle...")
    subprocess.run([
        sys.executable, '-m', 'pip', 'install',
        'paddlepaddle', '-i',
        'https://mirror.baidu.com/pypi/simple'
    ], check=True)

    # 安装 paddleocr
    print("  安装 PaddleOCR...")
    subprocess.run([
        sys.executable, '-m', 'pip', 'install',
        'paddleocr', '-i',
        'https://mirror.baidu.com/pypi/simple'
    ], check=True)

    print("✅ PaddleOCR 安装完成")


if __name__ == '__main__':
    # 测试代码
    import sys

    if len(sys.argv) < 2:
        print("用法: python ocr_extractor.py <图片路径>")
        sys.exit(1)

    image_path = sys.argv[1]

    # 检查是否安装
    if not check_paddleocr_installed():
        print("⚠️ PaddleOCR 未安装")
        response = input("是否安装? (y/n): ")
        if response.lower() == 'y':
            install_paddleocr()
        else:
            sys.exit(1)

    # 创建 OCR 识别器
    extractor = OCRExtractor()

    # 提取文本
    print("\n" + "="*70)
    print("📄 识别结果:")
    print("="*70)

    text = extractor.extract_text_from_image(image_path)
    print(text)

    print("\n" + "="*70)
    print("📍 文本位置信息:")
    print("="*70)

    text_with_positions = extractor.extract_text_with_positions(image_path)
    for item in text_with_positions[:10]:  # 只显示前10个
        print(f"  {item['text']} (置信度: {item['confidence']:.2f})")
