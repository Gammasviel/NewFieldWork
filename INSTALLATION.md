# 外部依赖安装指南

本文档说明如何在 Linux 系统上安装项目所需的外部工具和依赖。这些工具无法通过 `pip install -r requirements.txt` 自动安装，需要手动安装。

---

## 📋 依赖清单

| 工具 | 用途 | 是否必需 |
|------|------|---------|
| Playwright 浏览器 | 导出网页图表截图 | 推荐（有备选方案） |
| Pandoc | Markdown 转 PDF | **必需** |
| XeLaTeX (TeX Live) | PDF 生成引擎 | **必需** |
| Noto Sans CJK SC 字体 | PDF 中文显示 | **必需** |

---

## 🐧 安装步骤 (Ubuntu/Debian)

### 1. 安装 Pandoc

```bash
sudo apt-get update
sudo apt-get install pandoc
```

验证安装：
```bash
pandoc --version
```

### 2. 安装 XeLaTeX 和 TeX Live

```bash
# 安装 XeLaTeX 和必要的 TeX 包
sudo apt-get install texlive-xetex texlive-fonts-recommended texlive-lang-chinese texlive-latex-extra

# 如果需要完整的 TeX Live（可选，体积较大）
# sudo apt-get install texlive-full
```

验证安装：
```bash
xelatex --version
```

**注意**:
- `texlive-latex-extra` 包含了 `float`、`caption`、`sectsty` 等宏包
- `float` 宏包用于控制图表位置，确保图表在正文中显示
- `caption` 宏包用于自定义图表标题格式（图1、图2 等）
- `sectsty` 宏包用于设置标题居中显示

### 3. 安装中文字体

```bash
# 安装 Noto CJK 字体
sudo apt-get install fonts-noto-cjk

# 刷新字体缓存
fc-cache -fv
```

验证安装：
```bash
fc-list | grep -i "noto.*cjk"
```

### 4. 安装 Playwright 浏览器

```bash
# 首先确保已通过 pip 安装 playwright
pip install playwright

# 安装 Chromium 浏览器（推荐）
playwright install chromium

# 或安装所有浏览器（可选）
# playwright install

# 如果遇到依赖问题，安装系统依赖
playwright install-deps chromium
```

验证安装：
```bash
playwright --version
ls ~/.cache/ms-playwright/
```

---

## ✅ 验证所有依赖

创建并运行以下检查脚本 `check_dependencies.sh`:

```bash
#!/bin/bash
echo "=========================================="
echo "  外部依赖检查"
echo "=========================================="
echo ""

# 检查 Pandoc
echo "1. Pandoc:"
if command -v pandoc &> /dev/null; then
    echo "   ✓ 已安装: $(pandoc --version | head -1)"
else
    echo "   ✗ 未安装"
fi
echo ""

# 检查 XeLaTeX
echo "2. XeLaTeX:"
if command -v xelatex &> /dev/null; then
    echo "   ✓ 已安装: $(xelatex --version | head -1)"
else
    echo "   ✗ 未安装"
fi
echo ""

# 检查 Playwright 浏览器
echo "3. Playwright Chromium:"
if [ -d "$HOME/.cache/ms-playwright/chromium-"* ] 2>/dev/null; then
    echo "   ✓ 已安装"
else
    echo "   ✗ 未安装 (运行: playwright install chromium)"
fi
echo ""

# 检查中文字体
echo "4. Noto Sans CJK SC 字体:"
if fc-list 2>/dev/null | grep -i "noto.*cjk" &> /dev/null; then
    echo "   ✓ 已安装"
else
    echo "   ✗ 未安装或 fc-list 不可用"
fi
echo ""

echo "=========================================="
```

运行：
```bash
chmod +x check_dependencies.sh
./check_dependencies.sh
```

---

## 🔧 常见问题

### Q1: Playwright 安装后仍然报错 "Browser not found"

**解决方案**:
```bash
# 重新安装浏览器
playwright install chromium --force

# 或安装系统依赖（Linux）
playwright install-deps chromium
```

### Q2: XeLaTeX 找不到中文字体

**解决方案**:
```bash
# 刷新字体缓存（Linux/macOS）
fc-cache -fv

# 检查字体是否正确安装
fc-list | grep -i "noto"

# 如果使用其他字体，修改 app/core/utils.py:294 中的字体名称
```

### Q3: Pandoc 转换 PDF 时出错

**解决方案**:
1. 确保 XeLaTeX 已正确安装
2. 确保中文字体已安装
3. 检查日志文件 `logs/` 目录中的错误信息
4. 手动测试转换：
   ```bash
   pandoc test.md -o test.pdf --pdf-engine=xelatex
   ```

### Q4: 磁盘空间不足

**精简安装建议**:
```bash
# 只安装必要的 TeX 包
sudo apt-get install texlive-xetex texlive-fonts-recommended

# 只安装 Chromium 浏览器
playwright install chromium

# 只安装必要的中文字体
sudo apt-get install fonts-noto-cjk-sc
```

---

## 📚 参考链接

- **Pandoc**: https://pandoc.org/
- **TeX Live**: https://www.tug.org/texlive/
- **Playwright**: https://playwright.dev/python/docs/intro
- **Noto Fonts**: https://fonts.google.com/noto/specimen/Noto+Sans+SC

---

## 💡 备选方案

如果无法安装某些工具，可以考虑以下备选方案：

### 不安装 Playwright
- 系统会自动降级使用 matplotlib 生成图表
- 图表质量略有下降，但功能完整

### 不安装 Pandoc/XeLaTeX
- 只能导出 Markdown 格式报告
- 无法生成 PDF 报告
- 需要修改代码跳过 PDF 转换步骤

---

## 📝 安装顺序建议

1. **先安装 Python 依赖**: `pip install -r requirements.txt`
2. **安装 Pandoc**: 最小依赖，快速安装
3. **安装 XeLaTeX**: 可能需要较长时间
4. **安装中文字体**: 确保 PDF 中文显示
5. **安装 Playwright 浏览器**: 最后安装，可选

---

**最后更新**: 2025-10-29
