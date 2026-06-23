# dependency-graph

生成并解读代码库的文件级有向依赖关系图。

## 功能

- 自动生成代码库的依赖关系图
- 支持多种编程语言：C/C++ (`#include`)、Python (`import`)、JavaScript/TypeScript (`import`)
- 输出多种格式：SVG、HTML、DOT、Mermaid、JSON
- 帮助识别架构问题：循环依赖、高耦合模块、职责边界不清

## 快速开始

### 生成依赖图

```bash
python scripts/generate_dependency_graph.py \
  --root . \
  --scope <目标目录> \
  --direction TB \
  --output deps.svg \
  --json deps.json
```

### 常用参数

- `--scope PATH`：指定扫描目录（可重复）
- `--include GLOB`：额外包含的文件 glob，如 `src/**/*.h`
- `--exclude GLOB`：排除的路径，如 `build/**`
- `--output PATH`：输出文件路径（`.svg`、`.html`、`.dot`、`.mmd`、`.json`）
- `--json PATH`：额外输出原始图数据
- `--external`：显示外部依赖为灰色节点
- `--no-tests`：忽略测试目录和文件
- `--cpp-view`：C/C++ 模式 (`headers` 或 `all`)
- `--direction`：图布局方向 (`TB` 上下、`LR` 左右、`BT` 下上、`RL` 右左)

## 图的方向

依赖图的边方向定义为：

```
使用者文件 → 被依赖文件
```

例如：`Hasher.h` 包含 `FileInfo.h`，则边为 `Hasher.h → FileInfo.h`

## 架构分析

使用依赖图可以：

- **识别高 fan-in 的文件**：往往是共享模型或稳定接口
- **识别高 fan-out 的文件**：可能是协调者或承担过多职责
- **发现循环依赖**：暗示声明位置不当或职责边界不清
- **验证依赖方向**：底层工具不应反向依赖高层流程

## 目录结构

```
dependency-graph/
├── scripts/
│   └── generate_dependency_graph.py    # 依赖图生成脚本
├── agents/
│   └── openai.yaml                     # Agent 配置
├── evals/
│   └── evals.json                      # 评估数据
├── SKILL.md                            # 详细技能文档
└── README.md                           # 本文件
```

## 技能描述

此技能适用于以下场景：

- 需要"依赖关系图"或"架构可视化"
- 分析"文件之间的依赖"或"谁依赖谁"
- 判断代码是否应该拆分、合并或移动
- 生成 include/import 依赖图

## 许可证

见项目许可证文件。
