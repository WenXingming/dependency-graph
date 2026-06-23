# dependency-graph Skill

Agent Skill，用于生成并解读代码库的文件级有向依赖关系图。

## 功能

- 自动生成代码库的依赖关系图
- 支持多种编程语言：C/C++ (`#include`)、Python (`import`)、JavaScript/TypeScript (`import`)
- 输出多种格式：SVG、HTML、DOT、Mermaid、JSON
- 帮助识别架构问题：循环依赖、高耦合模块、职责边界不清

## 使用场景

触发此 skill 的关键词：

- "依赖关系图"、"架构可视化"
- "文件之间的依赖"、"谁依赖谁"
- "include/import graph"、"dependency graph"
- 需要判断某个模块是否应该拆分/合并/移动

## 工作流程

1. **生成依赖图**

```bash
python scripts/generate_dependency_graph.py \
  --root . \
  --scope <目标目录> \
  --direction TB \
  --output deps.svg \
  --json deps.json
```

2. **常用参数**

   - `--scope PATH`：指定扫描目录（可重复）
   - `--output PATH`：输出文件 (`.svg`、`.html`、`.dot`、`.mmd`)
   - `--json PATH`：额外输出 JSON 数据
   - `--direction TB|LR`：图布局方向（默认 `TB` 自上而下）
   - `--cpp-view headers|all`：C/C++ 模式
   - `--exclude GLOB`：排除路径

3. **分析依赖图**

   - 边方向：`使用者文件 → 被依赖文件`
   - 高 fan-in 的文件：共享接口或稳定模型
   - 高 fan-out 的文件：协调者或可能承担过多职责
   - 循环依赖：需要重构

## 详细文档

更详细的说明和高级用法见 [SKILL.md](skills/dependency-graph/SKILL.md)。
